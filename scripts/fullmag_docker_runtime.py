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
import time
import uuid
from pathlib import Path

import fullmag_storage as storage
from local_runner.runtime_use import runtime_package_use, register_runtime_reference_root
from local_runner.worker_entrypoint import verify_source
from run_managed_browser import digest, host_path, read_json, validate_managed_build

PROFILE = "docker-all-gpu"
STARTUP_READY_TIMEOUT_SECONDS = 2100
STARTUP_DOCKER_CLIENT_TIMEOUT_SECONDS = 2160
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


class StartupOutcomeUnknown(RuntimeError):
    """The container remained owned but did not publish startup activation."""

    def __init__(self, request_id, timeout):
        super().__init__(f"Startup activation {request_id!r} did not reach a durable ready receipt within {timeout}s")
        self.operation = ["startup-activation", request_id]
        self.timeout_seconds = timeout


def _startup_process_receipt_path(state):
    return Path(state) / ".fullmag/runtime-service/process-tree.json"


def _validate_startup_process_receipt(value, authorization=None):
    if not isinstance(value, dict) or value.get("schema") != "fullmag.docker-process-tree.v1":
        raise ValueError("Runtime process-tree receipt schema mismatch")
    if value.get("state") != "ready":
        raise ValueError("Runtime process-tree receipt is not ready")
    if authorization is None:
        return value
    activation = value.get("startup_activation")
    if not isinstance(activation, dict):
        raise ValueError("Runtime process-tree receipt has no startup activation")
    if (activation.get("schema") != "fullmag.startup-script-activation.v1"
            or activation.get("state") != "activated"
            or activation.get("request_id") != authorization.get("request_id")
            or activation.get("source_sha256") != authorization.get("source_sha256")
            or activation.get("source_relative") != authorization.get("source_relative")):
        raise ValueError("Runtime startup activation fence differs from the host authorization")
    response = activation.get("response")
    if not isinstance(response, dict):
        raise ValueError("Runtime startup activation response is missing")
    # Reuse the exact request/response contract; this does not create a second
    # endpoint or relax the API's live-v2 execution policy.
    import docker_startup_script as startup_helper
    startup_helper.validate_activation_response(response, authorization)
    return value


def _wait_for_startup_ready(state, authorization=None, *, timeout=90):
    if timeout <= 0:
        raise ValueError("Startup activation observation timeout must be positive")
    path = _startup_process_receipt_path(state)
    deadline = time.monotonic() + timeout
    while True:
        if path.exists():
            value = read_json(path)
            if value.get("state") in {"failed_outcome_retained", "shutdown_unknown"}:
                raise ValueError("Runtime process-tree receipt records an unconfirmed startup outcome")
            if value.get("state") == "ready":
                return _validate_startup_process_receipt(value, authorization)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            request_id = authorization.get("request_id") if authorization is not None else "runtime-ready"
            raise StartupOutcomeUnknown(request_id, timeout)
        time.sleep(min(0.25, remaining))


def _runtime_ready_timeouts(inputs, startup):
    """Return bounded wait/client budgets for the actual startup contract."""

    if inputs is not None or startup is not None:
        return STARTUP_READY_TIMEOUT_SECONDS, STARTUP_DOCKER_CLIENT_TIMEOUT_SECONDS
    return 90, 150


def docker(*args, combined=False, timeout=60, environment=None):
    # Windows talks directly to Desktop; Linux uses its active Linux socket.
    command = ["docker"]
    if os.name == "nt":
        command += ["--context", "desktop-linux"]
    try:
        result = subprocess.run([*command, *args], text=True, capture_output=True, timeout=timeout,
                                env=None if environment is None else {**os.environ, **environment})
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


def compose_spec(image, state, port, host_certificate=None, *, repo=None, inputs=None,
                 inputs_path=None, package=None, provenance=None, toolchain_image=None,
                 project="fullmag-config-check", template=None, host_ledger=None,
                 startup=None):
    """Resolve the versioned Compose definition; do not generate service topology."""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("A full immutable image ID is required")
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be between 1024 and 65535")
    if host_certificate is None:
        raise ValueError("Windows host certificate is required")
    repo = Path(repo or Path(__file__).resolve().parents[1])
    template = Path(template) if template is not None else repo / ("compose.dev.yaml" if inputs is not None else "compose.static.yaml")
    environment = {
        "FULLMAG_RELEASE_IMAGE": image, "FULLMAG_DEV_IMAGE": image,
        "FULLMAG_TOOLCHAIN_IMAGE": toolchain_image or image,
        "FULLMAG_TOOLCHAIN_IMAGE_ID": toolchain_image or image,
        "FULLMAG_STATE_ROOT": str(state), "FULLMAG_HTTP_PORT": str(port),
        "FULLMAG_HOST_CERTIFICATE": str(host_certificate),
        "FULLMAG_BACKEND_HOSTNAME": "fullmag-" + state.parent.name,
    }
    if inputs is not None:
        if package is None or provenance is None or inputs_path is None:
            raise ValueError("Development Compose requires a managed package and provenance")
        environment.update(FULLMAG_SOURCE_ROOT=str(inputs["source_root"]),
                           FULLMAG_BACKEND_PACKAGE=str(package),
                           FULLMAG_PACKAGE_PROVENANCE=str(provenance),
                           FULLMAG_DEVELOPMENT_INPUTS=str(inputs_path))
    definitions = ["-f", str(template)]
    if host_ledger is not None:
        environment.update(host_ledger["environment"])
        definitions.extend(["-f", host_ledger["compose_overlay"]])
    if startup is not None:
        overlay = startup.get("compose_overlay")
        if not isinstance(overlay, str) or not Path(overlay).is_file():
            raise ValueError("Startup script Compose overlay is missing")
        definitions.extend(["-f", overlay])
    configured = json.loads(docker("compose", "--project-name", project,
                                   "--project-directory", str(repo), *definitions,
                                   "config", "--format", "json", environment=environment))
    if host_ledger is not None:
        configured.get("services", {}).pop("host-ledger-maintenance", None)
    expected = {"backend", "frontend"} if inputs is not None else {"backend"}
    if set(configured.get("services", {})) != expected:
        raise ValueError("Versioned Compose has unexpected services")
    # A running configuration pins an existing image and never triggers a build.
    # Keep the original YAML beside it for review and future image preparation.
    for service in configured["services"].values():
        service.pop("build", None)
    return configured


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


def submit_build(repo, commit=None, *, development=False, source_root=None):
    if not development and not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        raise ValueError("A full commit SHA is required")
    from local_runner.build_executor import configured_build
    from local_runner.build_source import native_identity, bind_identity
    from local_runner.container_client import request
    from local_runner.source import capture_source

    if development:
        from docker_development_inputs import select_checkout
        source_repo = select_checkout(repo, source_root)
        required_helpers = ("Dockerfile", "Dockerfile.dev", "entrypoint.py", "windows_folder_probe.py",
                            "runtime_service.py", "frontend_dev.py", "healthcheck.py")
        for name in required_helpers:
            relative = "docker/all-in-one/" + name
            if storage.git(source_repo, "ls-files", "--", relative) != relative:
                raise ValueError("Integrate the Docker runtime into the selected checkout before its backend snapshot build")
        for relative in ("scripts/docker_startup_script.py", "scripts/fullmag_storage.py"):
            if storage.git(source_repo, "ls-files", "--", relative) != relative:
                raise ValueError("Integrate the pinned Docker startup helper dependencies into the selected checkout before its backend snapshot build")
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
            raise ValueError("Selected checkout changed during backend snapshot capture")
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
        receipt.update(state="submitted", result=result,
                       queue_state_at_submission=result.get("state", "unconfirmed"),
                       build_claimed_at_submission=result.get("state") == "running",
                       build_qualification="NOT VERIFIED",
                       next_step="Use runner-status/runner-wait; assemble only a terminal succeeded build",
                       queue_policy="Running Fullmag runtime containers postpone the heavy build; submission never stops or restarts them")
    except Exception as error:
        receipt.update(state="submission_unconfirmed", error=str(error))
        raise
    finally:
        storage.atomic_json(receipt_path, receipt)
        print(json.dumps(receipt, indent=2))


def stage_image_context(capsule, package, stage, *, development):
    """Stage operational helpers; application inputs are mounted in development."""
    if not development:
        shutil.copytree(capsule / "tree", stage / "source", symlinks=False)
        shutil.copytree(package, stage / "package", symlinks=False)
    for name in ("entrypoint.py", "windows_folder_probe.py", "runtime_service.py", "frontend_dev.py", "healthcheck.py"):
        shutil.copyfile(capsule / "tree/docker/all-in-one" / name, stage / name)
    for name in ("docker_startup_script.py", "fullmag_storage.py"):
        source = capsule / "tree/scripts" / name
        if not source.is_file():
            raise ValueError(f"Missing pinned Docker startup helper dependency: scripts/{name}")
        shutil.copyfile(source, stage / name)
    shutil.copyfile(capsule / "tree/docker/all-in-one" / ("Dockerfile.dev" if development else "Dockerfile"),
                    stage / "Dockerfile")
    return {path.name: digest(path) for path in (package / "bin").iterdir() if path.is_file()}


def build_image(repo, job_id, commit, *, source_digest=None, native_snapshot_sha256=None, development=False, source_root=None):
    if source_root is not None or source_digest is not None:
        from docker_development_inputs import select_checkout
        repo = select_checkout(repo, source_root)
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
                   "output": str(output), "unit_tests_compiled": False,
                   "runtime_mode": "development_source_bind" if development else "packaged_release",
                   "package_root": str(package)}
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
            receipt["binary_hashes"] = stage_image_context(capsule, package, stage, development=development)
            receipt["startup_helper_hashes"] = {
                name: digest(stage / name)
                for name in ("docker_startup_script.py", "fullmag_storage.py")
            }
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
                          "RUNTIME_BASE=" + alias, "--build-arg",
                          "FULLMAG_TOOLCHAIN_IMAGE_ID=" + context["image_digest"], "--iidfile", str(iid), str(stage), combined=True, timeout=1800)
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


def _write_startup_overlay(path, authorization, *, include_source,
                           provenance_sha256=None, helper_sha256=None):
    """Create a JSON Compose overlay for one already-admitted script.

    The base Compose files intentionally have no optional host path.  This
    overlay is created only after the bounded source admission succeeds, so an
    ordinary runtime has exactly the old mounts and environment.
    """
    source_root = Path(authorization["source_root"])
    provenance = Path(path).with_name("startup-provenance.json")
    volumes = [
        {
            "type": "bind",
            "source": str(provenance),
            "target": "/run/fullmag/startup-provenance.json",
            "read_only": True,
            "bind": {"create_host_path": False},
        }
    ]
    if include_source:
        volumes.insert(0, {
            "type": "bind",
            "source": str(source_root),
            "target": "/opt/fullmag/source",
            "read_only": True,
            "bind": {"create_host_path": False},
        })
    environment = {
        "FULLMAG_STARTUP_ENABLED": "1",
        "FULLMAG_STARTUP_SCRIPT": authorization["container_script_path"],
        "FULLMAG_STARTUP_PROVENANCE": "/run/fullmag/startup-provenance.json",
        "FULLMAG_STARTUP_API": "http://127.0.0.1:8081",
    }
    if provenance_sha256 is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", provenance_sha256):
            raise ValueError("Startup provenance digest is invalid")
        environment["FULLMAG_STARTUP_PROVENANCE_SHA256"] = provenance_sha256
    if helper_sha256 is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", helper_sha256):
            raise ValueError("Startup helper digest is invalid")
        environment["FULLMAG_STARTUP_HELPER_SHA256"] = helper_sha256
    overlay = {
        "services": {
            "backend": {
                "environment": environment,
                "volumes": volumes,
            }
        }
    }
    storage.atomic_json(path, overlay)


def start(repo, assembly_receipt, port, frontend="static", source_root=None,
          startup_script=None):
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
    helper_hashes = assembly.get("startup_helper_hashes")
    if (not isinstance(helper_hashes, dict)
            or set(helper_hashes) != {"docker_startup_script.py", "fullmag_storage.py"}
            or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                   for value in helper_hashes.values())):
        raise ValueError("Assembly receipt has no complete pinned startup helper inventory")
    if observed.get("Config", {}).get("Labels", {}).get("org.fullmag.runtime") != "docker-all-gpu-v1":
        raise ValueError("Image is not a Fullmag all-in-Docker GPU runtime")
    if frontend == "dev":
        if (assembly.get("runtime_mode") != "development_source_bind"
                or observed["Config"].get("Labels", {}).get("org.fullmag.development") != "source-bind-v1"):
            raise ValueError("Development requires a source-bind image without copied application sources")
        package = storage.validate_path(Path(assembly["package_root"]), Path(layout["storage_root"]))
        validate_runtime_artifacts(package)
        if any(digest(package / "bin" / name) != assembly["binary_hashes"].get(name)
               for name in REQUIRED_BINARIES):
            raise ValueError("Mounted backend package changed since image assembly")
    elif assembly.get("runtime_mode") == "development_source_bind":
        raise ValueError("Static mode requires a packaged release image")
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
    host_ledger = None
    startup = None
    inputs_path = root / "development-inputs.json"
    try:
        if frontend not in {"static", "dev"}:
            raise ValueError("Frontend mode must be static or dev")
        args = ["compose", "-f", str(spec), "--project-name", project]
        if frontend == "dev":
            from docker_development_inputs import seed, select_checkout
            inputs = seed(select_checkout(repo, source_root), state, port)
            storage.atomic_json(inputs_path, inputs)
            from local_runner.build_source import native_identity
            receipt["mounted_source_identity_at_start"] = native_identity(Path(inputs["source_root"]), "snapshot")
            receipt["source_selection"] = "live_windows_selected_checkout"
            receipt["source_root"] = inputs["source_root"]
            receipt["compiled_source_commit"] = assembly["commit"]
            receipt["frontend_source_root"] = inputs["source_root"]
            receipt["frontend_source_commit"] = inputs["source_commit"]
            receipt["frontend_inputs"] = str(inputs_path)
            receipt["frontend_inputs_sha256"] = digest(inputs_path)

        if startup_script is not None:
            from docker_development_inputs import select_checkout
            import docker_startup_script as startup_helper

            selected_source = (
                Path(inputs["source_root"])
                if inputs is not None
                else select_checkout(repo, source_root)
            )
            source_commit = (
                inputs.get("source_commit")
                if inputs is not None
                else storage.git(selected_source, "rev-parse", "HEAD")
            )
            startup_authorization = startup_helper.prepare(
                selected_source,
                startup_script,
                request_id="startup-" + root.name,
                source_commit=source_commit,
            )
            if inputs is not None and startup_authorization.source_root != Path(inputs["source_root"]).resolve():
                raise ValueError("Startup script checkout differs from the mounted development checkout")
            startup_provenance = root / "startup-provenance.json"
            provenance_sha256 = startup_helper.write_provenance(startup_provenance, startup_authorization)
            helper_hashes = assembly.get("startup_helper_hashes", {})
            helper_sha256 = helper_hashes.get("docker_startup_script.py")
            if not re.fullmatch(r"[0-9a-f]{64}", helper_sha256 or ""):
                raise ValueError("Assembly receipt has no pinned startup helper digest")
            startup_overlay = root / "compose.startup.json"
            authorization = startup_authorization.as_dict()
            _write_startup_overlay(
                startup_overlay,
                authorization,
                include_source=inputs is None,
                provenance_sha256=provenance_sha256,
                helper_sha256=helper_sha256,
            )
            startup = {"authorization": authorization, "compose_overlay": str(startup_overlay),
                       "provenance_sha256": provenance_sha256, "helper_sha256": helper_sha256}
            receipt["startup_script"] = {
                "source_relative": authorization["source_relative"],
                "source_sha256": authorization["source_sha256"],
                "source_size_bytes": authorization["source_size_bytes"],
                "source_commit": authorization["source_commit"],
                "source_root": authorization["source_root"],
                "source_path": authorization["source_path"],
                "container_script_path": authorization["container_script_path"],
                "request_id": authorization["request_id"],
                "provenance": str(startup_provenance),
                "provenance_sha256": provenance_sha256,
                "helper_sha256": helper_sha256,
                "compose_overlay": str(startup_overlay),
                "execution_policy": authorization["execution_policy"],
            }

        def configured_spec():
            return compose_spec(image, state.resolve(), port, host_certificate.resolve(),
                                repo=repo, inputs=inputs, inputs_path=inputs_path.resolve(),
                                package=assembly.get("package_root"),
                                provenance=assembly_receipt, project=project,
                                toolchain_image=assembly.get("base_image"), template=root / "compose.source.yaml",
                                host_ledger=host_ledger, startup=startup)
        if os.name != "nt":
            raise ValueError("This Windows-folder launcher requires native Windows host attestation")
        from windows_folder_host import attest, local_volume, publish_evidence, read_owned_regular
        from docker_host_ledger import prepare as prepare_host_ledger
        host_ledger = prepare_host_ledger(layout, repo, image, root, docker)
        receipt["host_ledger"] = host_ledger
        storage.atomic_json(root / "receipt.json", receipt)
        certificate = attest(state, assembly, docker("info", "--format", "{{.ID}}"), assembly["binary_hashes"])
        publish_evidence(host_certificate, certificate)
        shutil.copyfile(repo / ("compose.dev.yaml" if inputs is not None else "compose.static.yaml"),
                        root / "compose.source.yaml")
        receipt["compose_source"] = str(root / "compose.source.yaml")
        receipt["compose_source_sha256"] = digest(root / "compose.source.yaml")
        configured = configured_spec()
        probe_service = configured["services"]["backend"]
        probe_service["command"] = ["--storage-probe"]
        probe_service["healthcheck"] = {"disable": True}
        storage.atomic_json(spec, configured)
        docker(*args, "config", "--quiet")
        docker(*args, "up", "--detach", "--no-build", "--pull", "never", "backend")
        probe_container = docker(*args, "ps", "--all", "--quiet", "backend")
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
        publish_evidence(state / ".fullmag-windows-folder-owner.json", certificate)
        publish_evidence(host_certificate, certificate)
        receipt["storage_operational_checks"] = probe["checks"]
        receipt["storage_power_loss"] = "NOT VERIFIED"
        storage.atomic_json(spec, configured_spec())
        ready_timeout, docker_client_timeout = _runtime_ready_timeouts(inputs, startup)
        docker(*args, "up", "--detach", "--no-build", "--pull", "never", "--wait", "--wait-timeout",
               str(ready_timeout), timeout=docker_client_timeout)
        container = docker(*args, "ps", "--quiet", "backend")
        receipt["container_id"] = container
        actual = json.loads(docker("inspect", container))[0]
        from docker_host_ledger import validate_container as validate_host_ledger
        receipt["host_ledger_attestation"] = validate_host_ledger(actual, host_ledger, docker)
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
        from docker_compose_attestation import service_network, network_owner
        network_id = service_network(actual, project, hostname="fullmag-" + root.name)
        if inputs is not None and service_network(front, project) != network_id:
            raise ValueError("Frontend and backend are attached to different networks")
        network_owner(json.loads(docker("network", "inspect", network_id))[0], project, network_id)
        receipt["network_id"] = network_id
        receipt["network_name"] = project + "_fullmag"
        host = actual["HostConfig"]
        if actual["Image"] != image or (host.get("PortBindings") or {}) != bindings:
            raise ValueError("Runtime image or loopback port attestation mismatch")
        if inputs is not None:
            expected_readonly = {"/opt/fullmag/source": Path(inputs["source_root"]).resolve(),
                                 "/opt/fullmag/package": package.resolve(),
                                 "/opt/fullmag/provenance.json": assembly_receipt.resolve()}
        elif startup is not None:
            expected_readonly = {"/opt/fullmag/source": Path(startup["authorization"]["source_root"]).resolve()}
        else:
            expected_readonly = {}
        if inputs is not None or startup is not None:
            for destination, source in expected_readonly.items():
                bound = [m for m in actual["Mounts"] if m["Destination"] == destination]
                if (len(bound) != 1 or bound[0]["Type"] != "bind" or bound[0]["RW"]
                        or host_path(bound[0]["Source"]) != source):
                    raise ValueError("Development readonly bind differs: " + destination)
        if startup is not None:
            startup_mounts = [m for m in actual["Mounts"]
                              if m["Destination"] == "/run/fullmag/startup-provenance.json"]
            if (len(startup_mounts) != 1 or startup_mounts[0]["Type"] != "bind"
                    or startup_mounts[0]["RW"]
                    or host_path(startup_mounts[0]["Source"]) != (root / "startup-provenance.json").resolve()):
                raise ValueError("Startup provenance must be a readonly run-owned bind")
            environment = dict(
                value.split("=", 1)
                for value in actual["Config"].get("Env", [])
                if "=" in value
            )
            expected_environment = {
                "FULLMAG_STARTUP_ENABLED": "1",
                "FULLMAG_STARTUP_SCRIPT": startup["authorization"]["container_script_path"],
                "FULLMAG_STARTUP_PROVENANCE": "/run/fullmag/startup-provenance.json",
                "FULLMAG_STARTUP_API": "http://127.0.0.1:8081",
                "FULLMAG_STARTUP_PROVENANCE_SHA256": startup["provenance_sha256"],
                "FULLMAG_STARTUP_HELPER_SHA256": startup["helper_sha256"],
            }
            if any(environment.get(key) != value for key, value in expected_environment.items()):
                raise ValueError("Startup activation environment attestation mismatch")
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
               ("commit", "job_id", "source_digest", "base_image", "native_source_identity",
                "binary_hashes", "startup_helper_hashes", "build_receipt_sha256")):
            raise ValueError("Runtime image provenance differs from assembly receipt")
        for name, expected in helper_hashes.items():
            observed_helper = docker("exec", container, "sha256sum", "/opt/fullmag/" + name).split()[0]
            if observed_helper != expected:
                raise ValueError("Runtime image startup helper differs from assembly inventory: " + name)
        process_tree_receipt = _wait_for_startup_ready(
            state, startup["authorization"] if startup is not None else None,
            timeout=ready_timeout,
        )
        receipt["process_tree_receipt"] = str(_startup_process_receipt_path(state))
        receipt["process_tree_receipt_sha256"] = digest(_startup_process_receipt_path(state))
        if startup is not None:
            receipt["startup_process_tree_receipt"] = str(_startup_process_receipt_path(state))
            receipt["startup_process_tree_receipt_sha256"] = receipt["process_tree_receipt_sha256"]
            receipt["startup_activation"] = process_tree_receipt["startup_activation"]
        receipt.update(state="running", health="PASS", gpu_preflight="PASS",
                       attestation="image, provenance, port, storage, GPU request, isolation")
    except Exception as error:
        receipt.update(state="failed_resources_retained", error=str(error))
        if isinstance(error, DockerOutcomeUnknown):
            receipt.update(operation_outcome="unknown", timed_out_operation=error.operation,
                           client_timeout_seconds=error.timeout_seconds)
        elif isinstance(error, StartupOutcomeUnknown):
            receipt.update(startup_activation_outcome="unknown",
                           timed_out_operation=error.operation,
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
    development = commands.add_parser("submit-development")
    development.add_argument("--source-root", type=Path)
    build = commands.add_parser("build-image")
    build.add_argument("--job-id", required=True)
    build.add_argument("--commit", required=True)
    build.add_argument("--development", action="store_true")
    build.add_argument("--source-root", type=Path)
    build.add_argument("--source-digest")
    build.add_argument("--native-snapshot-sha256")
    launch = commands.add_parser("start")
    launch.add_argument("--assembly-receipt", type=Path, required=True)
    launch.add_argument("--port", type=int, default=3197)
    launch.add_argument("--source-root", type=Path)
    launch.add_argument("--frontend", choices=("static", "dev"), default="static")
    launch.add_argument("--startup-script", type=Path)
    args = parser.parse_args()
    if args.action == "submit":
        submit_build(args.repo_root.resolve(), args.commit)
    elif args.action == "submit-development":
        submit_build(args.repo_root.resolve(), development=True, source_root=args.source_root)
    elif args.action == "build-image":
        build_image(args.repo_root.resolve(), args.job_id, args.commit,
                    source_digest=args.source_digest, native_snapshot_sha256=args.native_snapshot_sha256, development=args.development, source_root=args.source_root)
    else:
        start(args.repo_root.resolve(), args.assembly_receipt, args.port, args.frontend,
              args.source_root, args.startup_script)
