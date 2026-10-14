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


def docker(*args, combined=False):
    # Windows talks directly to Desktop; Linux uses its active Linux socket.
    command = ["docker"]
    if os.name == "nt":
        command += ["--context", "desktop-linux"]
    result = subprocess.run([*command, *args], text=True, capture_output=True)
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


def compose_spec(image, state, port, host_certificate=None):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("A full immutable image ID is required")
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be between 1024 and 65535")
    result = {"services": {"fullmag": {
        "image": image, "pull_policy": "never", "init": True,
        "read_only": True, "user": "65532:65532", "gpus": "all",
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "ports": [f"127.0.0.1:{port}:8081"],
        "volumes": [{"type": "bind", "source": str(state), "target": "/state"}],
        "tmpfs": ["/tmp:rw,nosuid,nodev,size=512m"],
        "stop_grace_period": "30s",
    }}}
    if host_certificate is not None:
        service = result["services"]["fullmag"]
        service["volumes"].append({"type": "bind", "source": str(host_certificate),
                                   "target": "/run/fullmag/windows-folder-host.json", "read_only": True})
        service["environment"] = {"FULLMAG_SESSION_STORAGE_PROFILE": "windows-folder-v1",
                                   "FULLMAG_RUNTIME_IMAGE_ID": image}
        service["hostname"] = "fullmag-" + Path(state).parent.name
    return result


def prepare_gpu_release(layout, job_id, commit):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise ValueError("A full managed job ID is required")
    root = storage.validate_path(Path(layout["runs_root"]) / job_id, Path(layout["storage_root"]))
    context, built = validate_managed_build(root, commit, expected_profile="fem-gpu-release")
    mounts = [m for m in read_json(root / "receipt.json").get("mounts", [])
              if len(m) == 4 and m[0] == "bind" and m[2] == "/source" and m[3] is False]
    if len(mounts) != 1:
        raise ValueError("Managed source capsule mount missing or ambiguous")
    capsule = storage.validate_path(host_path(mounts[0][1]), Path(layout["storage_root"]))
    manifest = verify_source(capsule, context["source_digest"])
    if manifest.get("resolved_commit") != commit or manifest.get("source_mode") != "commit":
        raise ValueError("A clean commit build is required for the distributable image")
    package = storage.validate_path(root / "artifacts/outputs/.fullmag/local", root)
    for relative in ("bin/fullmag-api", "bin/fullmag-bin", "web/index.html", "_fullmag_core.so"):
        if not (package / relative).is_file():
            raise ValueError(f"Missing runtime artifact: {relative}")
    image_id(context["image_digest"])
    return root, context, built, capsule, package


def submit_build(repo, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full commit SHA is required")
    from local_runner.build_executor import configured_build
    from local_runner.build_source import native_identity, bind_identity
    from local_runner.container_client import request
    from local_runner.source import capture_source

    layout = storage.resolve_layout(repo, PROFILE)
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
        manifest = capture_source(repo, destination, mode="commit", ref=commit, content_store=None)
        native = bind_identity(native_identity(repo, "commit", manifest["resolved_commit"]), manifest)
    submitted = {"worktree_id": layout["worktree_id"], "source_digest": manifest["source_digest"],
                 "profile": "fem-gpu-release", "operation": "build", "request_key": capture_id,
                 "payload": {"source_mode": "commit", "origin_repo": layout["repo_root"],
                             "capture_id": capture_id, "native_source_identity": native,
                             "capsule_relative": destination.relative_to(Path(layout["storage_root"])).as_posix()}}
    receipt = {"schema": "fullmag.docker-all-submission.v1", "state": "submitting",
               "source_storage": "independent-copy", "capture_id": capture_id,
               "request_key": submitted["request_key"], "capsule_relative": submitted["payload"]["capsule_relative"],
               "commit": commit, "source_digest": manifest["source_digest"], "submission": submitted}
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


def build_image(repo, job_id, commit):
    layout = storage.resolve_layout(repo, PROFILE)
    # Resolve before the first write, then retain the package-use lease during copy.
    with runtime_package_use(layout):
        root, context, built, capsule, package = prepare_gpu_release(layout, job_id, commit)
        storage.initialize(layout)
        output = storage.validate_path(Path(layout["build_root"]) / "images" / uuid.uuid4().hex,
                                       Path(layout["build_storage_root"]))
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        receipt = {"schema": "fullmag.docker-all-image.v1", "state": "assembling",
                   "qualification": "NOT VERIFIED", "job_id": job_id, "commit": commit,
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
            for name in ("Dockerfile", "entrypoint.py", "windows_folder_probe.py"):
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
                          "RUNTIME_BASE=" + alias, "--iidfile", str(iid), str(stage), combined=True)
            (output / "assembly.log").write_text(logs)
            immutable = iid.read_text().strip()
            image_id(immutable)
            verify_source(capsule, context["source_digest"])
            receipt.update(state="succeeded", image_id=immutable, exit_code=0)
        except Exception as error:
            receipt.update(state="failed", error=str(error))
            raise
        finally:
            storage.atomic_json(receipt_path, receipt)
            print(json.dumps(receipt, indent=2))


def start(repo, assembly_receipt, port):
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be between 1024 and 65535")
    layout = storage.resolve_layout(repo, PROFILE)
    assembly_receipt = storage.validate_path(assembly_receipt, Path(layout["build_storage_root"]))
    assembly = read_json(assembly_receipt)
    if assembly.get("schema") != "fullmag.docker-all-image.v1" or assembly.get("state") != "succeeded" or assembly.get("exit_code") != 0:
        raise ValueError("A successful all-in-Docker assembly receipt is required")
    image = assembly.get("image_id", "")
    observed = image_id(image)
    if observed.get("Config", {}).get("Labels", {}).get("org.fullmag.runtime") != "docker-all-gpu-v1":
        raise ValueError("Image is not a Fullmag all-in-Docker GPU runtime")
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
               "url": f"http://localhost:{port}/workspace", "qualification": "NOT VERIFIED"}
    storage.atomic_json(root / "receipt.json", receipt)
    try:
        args = ["compose", "-f", str(spec), "--project-name", project]
        if os.name != "nt":
            raise ValueError("This Windows-folder launcher requires native Windows host attestation")
        from windows_folder_host import attest, local_volume, read_owned_regular
        certificate = attest(state, assembly, docker("info", "--format", "{{.ID}}"), assembly["binary_hashes"])
        storage.atomic_json(host_certificate, certificate)
        configured = compose_spec(image, state.resolve(), port, host_certificate.resolve())
        probe_service = configured["services"]["fullmag"]
        probe_service["command"] = ["--storage-probe"]
        probe_service["healthcheck"] = {"disable": True}
        storage.atomic_json(spec, configured)
        docker(*args, "config", "--quiet")
        docker(*args, "up", "--detach", "--no-build", "--pull", "never")
        probe_container = docker(*args, "ps", "--all", "--quiet", "fullmag")
        receipt["probe_container_id"] = probe_container
        receipt["first_probe_exit_code"] = docker("wait", probe_container)
        (root / "storage-first.log").write_text(docker("logs", probe_container, combined=True))
        if receipt["first_probe_exit_code"] != "0":
            raise ValueError("Windows storage first probe failed: " + docker("logs", probe_container, combined=True))
        docker("start", probe_container)
        receipt["restart_probe_exit_code"] = docker("wait", probe_container)
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
        storage.atomic_json(spec, compose_spec(image, state.resolve(), port, host_certificate.resolve()))
        docker(*args, "up", "--detach", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "90")
        container = docker(*args, "ps", "--quiet", "fullmag")
        receipt["container_id"] = container
        actual = json.loads(docker("inspect", container))[0]
        bindings = {"8081/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(port)}]}
        host = actual["HostConfig"]
        if actual["Image"] != image or host.get("PortBindings") != bindings:
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
    build = commands.add_parser("build-image")
    build.add_argument("--job-id", required=True)
    build.add_argument("--commit", required=True)
    launch = commands.add_parser("start")
    launch.add_argument("--assembly-receipt", type=Path, required=True)
    launch.add_argument("--port", type=int, default=3197)
    args = parser.parse_args()
    if args.action == "submit":
        submit_build(args.repo_root.resolve(), args.commit)
    elif args.action == "build-image":
        build_image(args.repo_root.resolve(), args.job_id, args.commit)
    else:
        start(args.repo_root.resolve(), args.assembly_receipt, args.port)
