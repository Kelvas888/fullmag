"""Assemble a complete Docker runtime from a verified managed GPU release.

No compiler is invoked here. Full builds remain owned by Fullmag_build_runner.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import fullmag_storage as storage
from local_runner.runtime_use import runtime_package_use, register_runtime_reference_root
from local_runner.worker_entrypoint import verify_source
from run_managed_browser import digest, host_path, read_json, validate_managed_build

PROFILE = "docker-all-gpu"
REQUIRED_BINARIES = (
    "fullmag-api", "fullmag-bin", "fullmag-runtime-service",
    "fullmag-api-resource-pool", "fullmag-api-preparation-resource-pool",
    "fullmag-api-accepted-scheduler", "fullmag-api-accepted-fem-preparation-scheduler",
    "fullmag-api-accepted-worker", "fullmag-api-accepted-supervisor",
    "fullmag-api-accepted-fem-preparer", "fullmag-api-accepted-fem-preparation-supervisor",
    "fullmag-api-preparation-retry",
)


def validate_runtime_artifacts(package):
    for relative in (*("bin/" + name for name in REQUIRED_BINARIES),
                     "web/index.html", "_fullmag_core.so"):
        if not (package / relative).is_file():
            raise ValueError(f"Missing runtime artifact: {relative}")


class DockerOutcomeUnknown(RuntimeError):
    def __init__(self, args, timeout):
        super().__init__(f"Docker client timed out after {timeout}s; container/build outcome is unconfirmed")
        self.operation = list(args)
        self.timeout_seconds = timeout


def docker(*args, combined=False, timeout=60):
    # Windows talks directly to Desktop; Linux uses its active Linux socket.
    command = ["docker"]
    if os.name == "nt":
        command += ["--context", "desktop-linux"]
    try:
        result = subprocess.run([*command, *args], text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        # Only the client is bounded. Docker-managed resources may still exist;
        # callers retain evidence and must not infer failure or retry mutation.
        raise DockerOutcomeUnknown(args, timeout) from error
    if result.returncode:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "Docker operation failed")
    return (result.stdout + result.stderr if combined else result.stdout).strip()


def image_id(value):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError("A full immutable image ID is required")
    observed = json.loads(docker("image", "inspect", value))[0]
    if observed["Id"] != value or observed.get("Config", {}).get("Volumes"):
        raise ValueError("Image identity mismatch or implicit anonymous volumes")
    return observed


def validate_workspace_environment(config):
    environment = dict(value.split("=", 1) for value in config.get("Env", []) if "=" in value)
    if (any(name in environment for name in ("FULLMAG_FDM_EXECUTION", "FULLMAG_FEM_EXECUTION"))
            or environment.get("FULLMAG_FEM_REQUIRE_GPU", "0") != "0"
            or environment.get("FULLMAG_FEM_ALL_IN_GPU", "0") != "0"
            or environment.get("FULLMAG_FEM_MFEM_DEVICE", "") != ""):
        raise ValueError("Runtime toolchain environment overrides model execution intent")


def compose_spec(image, state, port, host_certificate=None):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("A full immutable image ID is required")
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be between 1024 and 65535")
    result = {"services": {"fullmag": {
        "image": image, "pull_policy": "never", "init": True,
        "read_only": True, "user": "65532:65532", "gpus": "all",
        "cpus": 4, "mem_limit": "8g", "pids_limit": 512,
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "ports": [f"127.0.0.1:{port}:8081"],
        "volumes": [{"type": "bind", "source": str(state), "target": "/state"}],
        "tmpfs": ["/tmp:rw,nosuid,nodev,size=512m"],
        "stop_grace_period": "60s",
    }}}
    if host_certificate is not None:
        service = result["services"]["fullmag"]
        service["volumes"].append({"type": "bind", "source": str(host_certificate),
                                   "target": "/run/fullmag/windows-folder-host.json", "read_only": True})
        service["environment"] = {"FULLMAG_SESSION_STORAGE_PROFILE": "windows-folder-v1",
                                   "FULLMAG_RUNTIME_IMAGE_ID": image}
        service["hostname"] = "fullmag-" + Path(state).parent.name
    return result


def prepare_gpu_release(layout, job_id, commit, *, source_digest=None, native_snapshot_sha256=None):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise ValueError("A full managed job ID is required")
    root = storage.validate_path(Path(layout["runs_root"]) / job_id, Path(layout["storage_root"]))
    context, built = validate_managed_build(root, commit, expected_profile="fem-gpu-release",
                                            source_digest=source_digest, native_snapshot_sha256=native_snapshot_sha256)
    mounts = [m for m in read_json(root / "receipt.json").get("mounts", [])
              if len(m) == 4 and m[0] == "bind" and m[2] == "/source" and m[3] is False]
    if len(mounts) != 1:
        raise ValueError("Managed source capsule mount missing or ambiguous")
    capsule = storage.validate_path(host_path(mounts[0][1]), Path(layout["storage_root"]))
    manifest = verify_source(capsule, context["source_digest"])
    mode = "snapshot" if source_digest is not None else "commit"
    if manifest.get("resolved_commit") != commit or manifest.get("source_mode") != mode:
        raise ValueError("Managed source selection differs from the requested image identity")
    package = storage.validate_path(root / "artifacts/outputs/.fullmag/local", root)
    validate_runtime_artifacts(package)
    image_id(context["image_digest"])
    return root, context, built, capsule, package


def submit_build(repo, commit=None, *, development=False):
    if not development and not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        raise ValueError("A full commit SHA is required")
    from local_runner.build_executor import configured_build
    from local_runner.build_source import native_identity, bind_identity
    from local_runner.container_client import request
    from local_runner.source import capture_source

    if development:
        from docker_development_inputs import main_checkout
        source_repo = main_checkout(repo)
        required_helpers = ("Dockerfile", "entrypoint.py", "windows_folder_probe.py",
                            "runtime_service.py", "frontend_dev.py", "healthcheck.py")
        for name in required_helpers:
            relative = "docker/all-in-one/" + name
            if storage.git(source_repo, "ls-files", "--", relative) != relative:
                raise ValueError("Integrate the Docker runtime into the main checkout before its backend snapshot build")
        mode = "snapshot"
    else:
        source_repo = repo
        mode = "commit"
    # The canonical runner binds origin_repo to the registered worktree.
    # A main-checkout snapshot must use the main layout and registration too.
    layout = storage.resolve_layout(source_repo, PROFILE)
    owner = getpass.getuser()
    configured_build(layout, owner, "fem-gpu-release")
    health = request(layout, owner=owner, method="GET", path="/health")
    if health.get("accepting_jobs") is not True or "fem-gpu-release" not in health.get("allowed_profiles", []):
        raise ValueError("The existing runner is not accepting the GPU release profile")
    registration_path = storage.validate_path(Path(layout["storage_root"]) / "index" / (layout["worktree_id"] + ".json"),
                                              Path(layout["storage_root"]))
    registration = read_json(registration_path)
    if registration.get("worktree_id") != layout["worktree_id"] or Path(registration.get("repo_root", "")) != Path(layout["repo_root"]):
        raise ValueError("The source worktree must be registered before build submission")
    storage.initialize(layout)
    capture_id = uuid.uuid4().hex
    destination = storage.validate_path(Path(layout["runs_root"]) / capture_id / "source",
                                        Path(layout["storage_root"]))
    with storage.build_lock(layout):
        destination.mkdir(parents=True, exist_ok=False)
        # Independent immutable copies are an existing capsule contract. Never
        # weaken or repair a rejected shared CAS object during task submission.
        before = native_identity(source_repo, "snapshot") if development else None
        manifest = capture_source(source_repo, destination, mode=mode, ref=commit, content_store=None)
        after = native_identity(source_repo, mode, manifest["resolved_commit"])
        if before is not None and before != after:
            raise ValueError("Main checkout changed during backend snapshot capture")
        native = bind_identity(after, manifest)
        commit = manifest["resolved_commit"]
    submitted = {"worktree_id": layout["worktree_id"], "source_digest": manifest["source_digest"],
                 "profile": "fem-gpu-release", "operation": "build", "request_key": capture_id,
                 "payload": {"source_mode": mode, "origin_repo": str(source_repo),
                             "capture_id": capture_id, "native_source_identity": native,
                             "capsule_relative": destination.relative_to(Path(layout["storage_root"])).as_posix()}}
    receipt = {"schema": "fullmag.docker-all-submission.v1", "state": "submitting",
               "source_storage": "independent-copy", "capture_id": capture_id,
               "request_key": submitted["request_key"], "capsule_relative": submitted["payload"]["capsule_relative"],
               "commit": commit, "source_mode": mode, "source_root": str(source_repo),
               "native_source_identity": native, "source_digest": manifest["source_digest"], "submission": submitted}
    receipt_path = destination.parent / "submission.json"
    storage.atomic_json(receipt_path, receipt)
    try:
        result = request(layout, owner=owner, method="POST", path="/jobs", payload=submitted)
        receipt.update(state="submitted", result=result)
    except Exception as error:
        receipt.update(state="submission_unconfirmed", error=str(error))
        raise
    finally:
        storage.atomic_json(receipt_path, receipt)
        print(json.dumps(receipt, indent=2))


def build_image(repo, job_id, commit, *, source_digest=None, native_snapshot_sha256=None):
    if source_digest is not None or native_snapshot_sha256 is not None:
        from docker_development_inputs import main_checkout
        repo = main_checkout(repo)
    layout = storage.resolve_layout(repo, PROFILE)
    # Resolve before the first write, then retain the package-use lease during copy.
    with runtime_package_use(layout):
        root, context, built, capsule, package = prepare_gpu_release(layout, job_id, commit, source_digest=source_digest,
                                                                         native_snapshot_sha256=native_snapshot_sha256)
        storage.initialize(layout)
        output = storage.validate_path(Path(layout["build_root"]) / "images" / uuid.uuid4().hex,
                                       Path(layout["build_storage_root"]))
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        receipt = {"schema": "fullmag.docker-all-image.v1", "state": "assembling",
                   "qualification": "NOT VERIFIED", "job_id": job_id, "commit": commit,
                   "source_mode": "snapshot" if source_digest is not None else "commit",
                   "source_digest": context["source_digest"], "base_image": context["image_digest"],
                   "native_source_identity": built["native_source_identity"],
                   "build_receipt_sha256": digest(root / "artifacts/build-receipt.json"),
                   "output": str(output), "unit_tests_compiled": False}
        consumer = storage.validate_path(Path(layout["runtime_root"]) / "docker-all-images" / output.name,
                                         Path(layout["build_storage_root"]))
        consumer.mkdir(parents=True, exist_ok=False)
        register_runtime_reference_root(layout, consumer)
        receipt_path = consumer / "receipt.json"
        receipt["receipt"] = str(receipt_path)
        storage.atomic_json(receipt_path, receipt)
        try:
            stage = output / "context"
            stage.mkdir()
            # The trusted capsule excludes .env, Git internals and host caches.
            shutil.copytree(capsule / "tree", stage / "source", symlinks=False)
            shutil.copytree(package, stage / "package", symlinks=False)
            receipt["binary_hashes"] = {path.name: digest(path) for path in (stage / "package/bin").iterdir() if path.is_file()}
            for name in ("Dockerfile", "entrypoint.py", "windows_folder_probe.py", "runtime_service.py", "frontend_dev.py", "healthcheck.py"):
                shutil.copyfile(capsule / "tree/docker/all-in-one" / name, stage / name)
            (stage / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")
            # Docker FROM expects a repository reference, so create an explicit
            # local alias and attest its ID immediately before the offline build.
            alias = "fullmag/docker-all-base:" + output.name
            docker("tag", context["image_digest"], alias)
            if json.loads(docker("image", "inspect", alias))[0]["Id"] != context["image_digest"]:
                raise ValueError("Local base image alias changed")
            builder = "desktop-linux" if os.name == "nt" else docker("context", "show")
            description = docker("buildx", "inspect", builder)
            if not re.search(r"^Driver:\s+docker\s*$", description, re.MULTILINE):
                raise ValueError("Offline assembly requires the existing engine-integrated Docker builder")
            iid = output / "image-id.txt"
            logs = docker("build", "--builder", builder, "--network", "none", "--pull=false", "--build-arg",
                          "RUNTIME_BASE=" + alias, "--iidfile", str(iid), str(stage), combined=True, timeout=1800)
            (output / "assembly.log").write_text(logs)
            immutable = iid.read_text().strip()
            validate_workspace_environment(image_id(immutable)["Config"])
            verify_source(capsule, context["source_digest"])
            receipt.update(state="succeeded", image_id=immutable, exit_code=0)
        except Exception as error:
            receipt.update(state="failed", error=str(error))
            if isinstance(error, DockerOutcomeUnknown):
                receipt.update(state="assembly_outcome_unknown_resources_retained",
                               timed_out_operation=error.operation,
                               client_timeout_seconds=error.timeout_seconds)
            raise
        finally:
            storage.atomic_json(receipt_path, receipt)
            print(json.dumps(receipt, indent=2))


def start(repo, assembly_receipt, port, frontend="static"):
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be between 1024 and 65535")
    layout = storage.resolve_layout(repo, PROFILE)
    assembly_receipt = storage.validate_path(assembly_receipt, Path(layout["build_storage_root"]))
    assembly = read_json(assembly_receipt)
    if assembly.get("schema") != "fullmag.docker-all-image.v1" or assembly.get("state") != "succeeded" or assembly.get("exit_code") != 0:
        raise ValueError("A successful all-in-Docker assembly receipt is required")
    image = assembly.get("image_id", "")
    observed = image_id(image)
    validate_workspace_environment(observed["Config"])
    if observed.get("Config", {}).get("Labels", {}).get("org.fullmag.runtime") != "docker-all-gpu-v1":
        raise ValueError("Image is not a Fullmag all-in-Docker GPU runtime")
    if frontend == "dev" and observed["Config"].get("Labels", {}).get("org.fullmag.development") != "two-container-hmr-v1":
        raise ValueError("Image does not contain the two-container HMR development runtime")
    storage.initialize(layout)
    root = storage.validate_path(Path(layout["runs_root"]) / "docker-all" / uuid.uuid4().hex,
                                 Path(layout["build_storage_root"]))
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    state = root / "state"
    state.mkdir(mode=0o777)
    state.chmod(0o777)
    register_runtime_reference_root(layout, root)
    project = "fullmag-all-" + root.name
    spec = root / "compose.json"
    host_certificate = root / "windows-folder-host.json"
    receipt = {"schema": "fullmag.docker-all-run.v1", "state": "starting", "image_id": image,
               "compose_project": project, "compose_file": str(spec), "state_root": str(state),
               "assembly_receipt": str(assembly_receipt), "assembly_receipt_sha256": digest(assembly_receipt),
               "native_source_identity": assembly["native_source_identity"],
               "url": f"http://localhost:{port}/workspace", "qualification": "NOT VERIFIED",
               "frontend_mode": frontend, "container_http_port": 8080 if frontend == "dev" else 8081}
    storage.atomic_json(root / "receipt.json", receipt)
    inputs = None
    inputs_path = root / "development-inputs.json"
    try:
        if frontend not in {"static", "dev"}:
            raise ValueError("Frontend mode must be static or dev")
        args = ["compose", "-f", str(spec), "--project-name", project]
        if frontend == "dev":
            from docker_development_inputs import seed, main_checkout
            inputs = seed(main_checkout(repo), state, port)
            storage.atomic_json(inputs_path, inputs)
            receipt["frontend_source_root"] = inputs["source_root"]
            receipt["frontend_source_commit"] = inputs["source_commit"]
            receipt["frontend_inputs"] = str(inputs_path)
            receipt["frontend_inputs_sha256"] = digest(inputs_path)

        def configured_spec():
            configured = compose_spec(image, state.resolve(), port, host_certificate.resolve())
            if inputs is not None:
                from docker_development_inputs import extend_compose
                extend_compose(configured, inputs, inputs_path.resolve())
            return configured
        if os.name != "nt":
            raise ValueError("This Windows-folder launcher requires native Windows host attestation")
        from windows_folder_host import attest, local_volume, read_owned_regular
        certificate = attest(state, assembly, docker("info", "--format", "{{.ID}}"), assembly["binary_hashes"])
        storage.atomic_json(host_certificate, certificate)
        configured = configured_spec()
        probe_service = configured["services"]["fullmag"]
        probe_service["command"] = ["--storage-probe"]
        probe_service["healthcheck"] = {"disable": True}
        storage.atomic_json(spec, configured)
        docker(*args, "config", "--quiet")
        docker(*args, "up", "--detach", "--no-build", "--pull", "never", "fullmag")
        probe_container = docker(*args, "ps", "--all", "--quiet", "fullmag")
        receipt["probe_container_id"] = probe_container
        receipt["first_probe_exit_code"] = docker("wait", probe_container, timeout=120)
        (root / "storage-first.log").write_text(docker("logs", probe_container, combined=True))
        if receipt["first_probe_exit_code"] != "0":
            raise ValueError("Windows storage first probe failed: " + docker("logs", probe_container, combined=True))
        docker("start", probe_container)
        receipt["restart_probe_exit_code"] = docker("wait", probe_container, timeout=120)
        (root / "storage-restart.log").write_text(docker("logs", probe_container, combined=True))
        if receipt["restart_probe_exit_code"] != "0":
            raise ValueError("Windows storage restart probe failed: " + docker("logs", probe_container, combined=True))
        probe = json.loads(read_owned_regular(state / ".windows-folder-probe/probe-restart.json"))
        CHECKS = ("file_sync", "directory_sync", "atomic_replace", "atomic_directory_publish",
                  "process_lock", "no_follow_symlink", "no_follow_junction",
                  "sqlite_transactions", "restart_readback")
        if set(probe["checks"]) != set(CHECKS) or not all(value is True for value in probe["checks"].values()):
            raise ValueError("Windows session storage probes were not all successful")
        import hashlib
        if hashlib.sha256(read_owned_regular(state / ".windows-folder-probe/restart-sentinel.bin")).hexdigest() != certificate["restart_expected_sha256"]:
            raise ValueError("Native Windows restart readback differs from the guest")
        if any(certificate[key] != value for key, value in local_volume(state).items()):
            raise ValueError("Native Windows volume identity changed during preflight")
        certificate["restart_verified"] = True
        storage.atomic_json(state / ".fullmag-windows-folder-owner.json", certificate)
        storage.atomic_json(host_certificate, certificate)
        receipt["storage_operational_checks"] = probe["checks"]
        receipt["storage_power_loss"] = "NOT VERIFIED"
        storage.atomic_json(spec, configured_spec())
        docker(*args, "up", "--detach", "--no-build", "--pull", "never", "--wait", "--wait-timeout",
               "2100" if inputs is not None else "90", timeout=2160 if inputs is not None else 150)
        container = docker(*args, "ps", "--quiet", "fullmag")
        receipt["container_id"] = container
        actual = json.loads(docker("inspect", container))[0]
        bindings = {str(receipt["container_http_port"]) + "/tcp":
                    [{"HostIp": "127.0.0.1", "HostPort": str(port)}]}
        if inputs is not None:
            from docker_development_inputs import attest_mounts
            frontend_container = docker(*args, "ps", "--quiet", "frontend")
            receipt["frontend_container_id"] = frontend_container
            front = json.loads(docker("inspect", frontend_container))[0]
            attest_mounts(front, inputs, inputs_path)
            front_host = front["HostConfig"]
            if (front["Image"] != image or front_host.get("PortBindings") != bindings
                    or not front_host.get("ReadonlyRootfs") or front_host.get("Privileged")
                    or front["Config"].get("User") != "65532:65532"
                    or front_host.get("DeviceRequests")):
                raise ValueError("Frontend image, loopback port or isolation attestation mismatch")
            writable = [m for m in front["Mounts"] if m.get("RW") and m["Type"] == "bind"]
            if (len(writable) != 1 or writable[0]["Destination"] != "/state/development"
                    or writable[0]["Type"] != "bind"
                    or host_path(writable[0]["Source"]) != (state / "development").resolve()):
                raise ValueError("Frontend writable mount must be its isolated development directory")
            bindings = {}
        host = actual["HostConfig"]
        if actual["Image"] != image or (host.get("PortBindings") or {}) != bindings:
            raise ValueError("Runtime image or loopback port attestation mismatch")
        mounts = [m for m in actual["Mounts"] if m["Destination"] == "/state"]
        if len(mounts) != 1 or mounts[0]["Type"] != "bind" or not mounts[0]["RW"] or host_path(mounts[0]["Source"]) != state.resolve():
            raise ValueError("Runtime state mount attestation mismatch")
        certificates = [m for m in actual["Mounts"] if m["Destination"] == "/run/fullmag/windows-folder-host.json"]
        if (len(certificates) != 1 or certificates[0]["Type"] != "bind" or certificates[0]["RW"]
                or host_path(certificates[0]["Source"]) != host_certificate.resolve()):
            raise ValueError("Readonly Windows host attestation mount mismatch")
        if not host.get("ReadonlyRootfs") or host.get("Privileged") or actual["Config"].get("User") != "65532:65532":
            raise ValueError("Runtime isolation attestation mismatch")
        if not any(d.get("Count") == -1 and ["gpu"] in d.get("Capabilities", []) for d in host.get("DeviceRequests", [])):
            raise ValueError("Runtime NVIDIA GPU request is missing")
        provenance = json.loads(docker("exec", container, "cat", "/opt/fullmag/provenance.json"))
        if any(provenance.get(key) != assembly.get(key) for key in
               ("commit", "job_id", "source_digest", "base_image", "native_source_identity", "binary_hashes", "build_receipt_sha256")):
            raise ValueError("Runtime image provenance differs from assembly receipt")
        receipt.update(state="running", health="PASS", gpu_preflight="PASS",
                       attestation="image, provenance, port, storage, GPU request, isolation")
    except Exception as error:
        receipt.update(state="failed_resources_retained", error=str(error))
        if isinstance(error, DockerOutcomeUnknown):
            receipt.update(operation_outcome="unknown", timed_out_operation=error.operation,
                           client_timeout_seconds=error.timeout_seconds)
        try:
            receipt["retained_container_ids"] = docker(*args, "ps", "--all", "--quiet").splitlines()
        except Exception as inspection_error:
            receipt["container_inspection_error"] = str(inspection_error)
        raise
    finally:
        storage.atomic_json(root / "receipt.json", receipt)
        print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    commands = parser.add_subparsers(dest="action", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--commit", required=True)
    commands.add_parser("submit-development")
    build = commands.add_parser("build-image")
    build.add_argument("--job-id", required=True)
    build.add_argument("--commit", required=True)
    build.add_argument("--source-digest")
    build.add_argument("--native-snapshot-sha256")
    launch = commands.add_parser("start")
    launch.add_argument("--assembly-receipt", type=Path, required=True)
    launch.add_argument("--port", type=int, default=3197)
    launch.add_argument("--frontend", choices=("static", "dev"), default="static")
    args = parser.parse_args()
    if args.action == "submit":
        submit_build(args.repo_root.resolve(), args.commit)
    elif args.action == "submit-development":
        submit_build(args.repo_root.resolve(), development=True)
    elif args.action == "build-image":
        build_image(args.repo_root.resolve(), args.job_id, args.commit,
                    source_digest=args.source_digest, native_snapshot_sha256=args.native_snapshot_sha256)
    else:
        start(args.repo_root.resolve(), args.assembly_receipt, args.port, args.frontend)
