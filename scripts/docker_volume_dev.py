"""Volume-only orchestration for the existing fixed DEV backend/frontend."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time

import fullmag_storage as storage
from docker_build_control import (BuildControl, BuildControlError, canonical, docker_capture,
                                  compose_capture, build_volume_toolchain, build_volume_runtime_images, bounded_capture)


def docker_text(*args, timeout=90, combined=False):
    result = docker_capture(*args, timeout=timeout)
    return (result.stdout + (result.stderr if combined else b"")).decode("utf-8", "replace")


def consumers():
    ids = docker_text("ps", "--quiet", "--no-trunc").split()
    return json.loads(docker_text("inspect", *ids)) if ids else []


def _owned_volume(control, role, key):
    name = "fullmag-dev-" + role + "-v1-" + key[:24]
    labels = {**{k: v for k, v in control.labels.items() if k.startswith("org.fullmag.")},
              "org.fullmag.build.role": role, "org.fullmag.build.cache-key": key}
    found = docker_capture("volume", "inspect", name, allow_failure=True)
    if found.returncode:
        names = docker_text("volume", "ls", "--format", "{{.Name}}").splitlines()
        if name in names:
            raise BuildControlError("Existing data volume could not be inspected")
        arguments = ["volume", "create", "--driver", "local"]
        for label, value in labels.items():
            arguments += ["--label", label + "=" + value]
        docker_capture(*arguments, name)
        found = docker_capture("volume", "inspect", name)
    records = json.loads(found.stdout)
    if len(records) != 1:
        raise BuildControlError("Ambiguous build-data volume")
    observed = records[0]
    if (observed.get("Name") != name or observed.get("Driver") != "local"
            or observed.get("Options")
            or any((observed.get("Labels") or {}).get(k) != v for k, v in labels.items())):
        raise BuildControlError("Build-data volume ownership differs; retained")
    if any(m.get("Name") == name for c in consumers() for m in c.get("Mounts", [])):
        raise BuildControlError("Cannot initialize a build-data volume with active consumers")
    script = "test $(stat -c %u /data) = 0 -o $(stat -c %u /data) = 65532; chown 65532:65532 /data; chmod 0750 /data"
    args = control.helper_args(script, initialize=True)
    args[args.index("--entrypoint"):args.index("--entrypoint")] = ["--mount", "type=volume,src=" + name + ",dst=/data,volume-nocopy"]
    result = bounded_capture(args, data=b"", timeout=90)
    if result.returncode:
        raise BuildControlError(result.stderr.decode("utf-8", "replace"))
    return name


def _frontend(control, operation, selected, state, port, image):
    from docker_development_inputs import seed
    files = []
    inputs = seed(selected, state, port, write_file=lambda relative, data: files.append({
        "relative": relative, "data": base64.b64encode(data).decode("ascii")}))
    previous_inputs = control.read("frontend/development-inputs.json", optional=True)
    if (isinstance(previous_inputs, dict)
            and all(previous_inputs.get(key) == inputs.get(key) for key in
                ("source_root", "worktree_id", "dependency_seed_sha256", "toolpins_sha256", "host_port", "files", "live_directories"))):
        inputs = previous_inputs
    key = hashlib.sha256(canonical({"project": control.project,
        "dependencies": inputs["dependency_seed_sha256"], "tools": inputs["toolpins_sha256"]})).hexdigest()
    volume = _owned_volume(control, "frontend", key)
    operation["receipt"]["frontend_volume"] = volume
    request = canonical({"files": files, "inputs": inputs})
    if len(request) > 8 * 1024 * 1024:
        raise BuildControlError("Frontend metadata exceeds transfer budget")
    # Metadata only: the four application directories stay live readonly binds.
    script = r'''
import base64, hashlib, json, os, pathlib, sys
root=pathlib.Path('/data/workspace')
request=json.load(sys.stdin)
root.mkdir(parents=True,exist_ok=True)
cache=pathlib.Path('/data/cache')
if cache.is_symlink(): raise RuntimeError('Frontend cache is a link')
cache.mkdir(exist_ok=True)
lock=cache/'.fullmag-frontend-runtime.lock'
if lock.is_symlink(): raise RuntimeError('Frontend runtime lock is a link')
with lock.open('ab'): pass
for record in request['files']:
    relative=pathlib.PurePosixPath(record['relative'])
    if relative.is_absolute() or '..' in relative.parts:
        raise RuntimeError('Unsafe frontend seed path')
    target=root.joinpath(*relative.parts)
    parent=root
    for part in relative.parts[:-1]:
        parent=parent/part
        if parent.is_symlink(): raise RuntimeError('Frontend parent is a link')
        parent.mkdir(exist_ok=True)
    data=base64.b64decode(record['data'],validate=True)
    if target.is_symlink(): raise RuntimeError('Frontend seed is a link')
    if target.exists():
        if target.read_bytes()!=data and record['relative'] not in ('apps/control-room/tsconfig.json','apps/control-room/next-env.d.ts'):
            raise RuntimeError('Frontend metadata changed; cache retained')
    else:
        with target.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
for name in ('app','src','public','scripts'):
    target=root/'apps/control-room'/name
    if target.is_symlink(): raise RuntimeError('Live directory is a link')
    target.mkdir(exist_ok=True)
print(json.dumps({'state':'seeded','files':len(request['files'])}))
'''
    args = control.helper_args("exec /usr/local/bin/python3 -I -c " + __import__('shlex').quote(script))
    args[args.index("--entrypoint"):args.index("--entrypoint")] = ["--mount", "type=volume,src=" + volume + ",dst=/data,volume-nocopy"]
    args[args.index(control.image)] = image
    result = bounded_capture(args, data=request, timeout=120)
    if result.returncode:
        raise BuildControlError(result.stderr.decode("utf-8", "replace"))
    control.write(operation["root"] + "/frontend-seed.json", json.loads(result.stdout))
    control.write("frontend/development-inputs.json", inputs)
    return inputs, volume


def _backend_cache(control, operation, layout, selected, image, toolchain):
    import docker_backend_volume_cache as cache
    def volume_docker(*args):
        result = docker_capture(*args, allow_failure=True)
        if result.returncode:
            if args[:2] == ("volume", "inspect") and "no such volume" in result.stderr.decode().lower():
                raise cache.VolumeNotFound(result.stderr.decode())
            raise BuildControlError(result.stderr.decode())
        return result.stdout.decode()
    relative = operation["root"] + "/backend-cache.json"
    layout = {**layout, "compose_project": control.project}
    profile = cache.prepare(layout, selected, image, layout["storage_root"], volume_docker,
        source_root=selected, toolchain_image=toolchain, active_consumers=consumers,
        control_volume_name=control.volume)
    overlay = cache.maintenance_overlay(profile)
    overlay["name"] = control.project
    control.write(operation["root"] + "/cache-maintenance-compose.json", overlay)
    output = compose_capture(overlay, "run", "--rm", "--no-deps", cache.MAINTENANCE_SERVICE, timeout=180)
    receipt = cache._read_json_output(output.decode())
    result = cache.validate(profile, profile["volume_documents"], receipt, consumers)
    control.write(relative, result)
    return result


def _host_ledger(control, operation, layout, selected, image):
    import docker_host_ledger as ledger
    values = ledger._resolve_values(layout)
    daemon = ledger._daemon_info(docker_text)
    ledger._image_attestation(image, docker_text)
    helper = selected / "scripts/lib/docker_host_ledger.sh"
    from windows_folder_host import read_owned_regular
    helper_bytes = read_owned_regular(helper, maximum=ledger.MAX_HELPER_BYTES)
    helper_hash = hashlib.sha256(helper_bytes).hexdigest()
    helper_relative = operation["root"] + "/docker_host_ledger.sh"
    control.write_bytes(helper_relative, helper_bytes)
    env = {
        "FULLMAG_HOST_LEDGER_PROFILE": ledger.PROFILE,
        "FULLMAG_HOST_LEDGER_PROJECT_ID": values["project_id"],
        "FULLMAG_HOST_LEDGER_STORAGE_ROOT": ledger._daemon_path(values["storage_root"], "storage root"),
        "FULLMAG_HOST_LEDGER_BACKING_IMAGE": ledger._daemon_path(values["backing_image"], "backing image"),
        "FULLMAG_HOST_LEDGER_MOUNT_ROOT": values["mount_root"],
        "FULLMAG_HOST_LEDGER_LOCK_PATH": ledger._daemon_path(values["lock_path"], "lock path"),
        "FULLMAG_HOST_LEDGER_OWNER_MARKER": values["owner_marker"],
        "FULLMAG_HOST_LEDGER_SIZE_BYTES": str(ledger.IMAGE_SIZE_BYTES),
        "FULLMAG_HOST_LEDGER_MOUNT_TARGET": ledger.MOUNT_TARGET,
        "FULLMAG_HOST_LEDGER_ROOT": ledger.LEDGER_ROOT,
        "FULLMAG_HOST_LEDGER_LEDGER_ROOT": values["ledger_root_daemon"],
        "FULLMAG_HOST_LEDGER_HELPER_PATH": ledger._daemon_path(helper, "readonly helper source"),
        "FULLMAG_HOST_LEDGER_HELPER_IMAGE": image,
        "FULLMAG_HOST_LEDGER_HOST_PID": "1",
        "FULLMAG_HOST_LEDGER_RUNTIME_UID": "65532", "FULLMAG_HOST_LEDGER_RUNTIME_GID": "65532",
        "FULLMAG_HOST_LEDGER_LOCK_WAIT_SECONDS": "120", "FULLMAG_DOCKER_HOST_ID": daemon["id_sha256"],
    }
    command = ["docker", "--context", "desktop-linux", "compose", "--project-name", control.project,
               "-f", "-", "-f", str(selected / "compose.host-ledger.yaml"), "--profile", "host-ledger-maintenance", "config", "--format", "json"]
    result = bounded_capture(command, data=canonical({"name": control.project,
        "services": {"backend": {"image": image}}}),
        env={**os.environ, **env}, timeout=90)
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise BuildControlError("Host-ledger Compose rendering failed: " + result.stderr.decode("utf-8", "replace"))
    rendered = json.loads(result.stdout)
    service = rendered["services"]["host-ledger-maintenance"]
    service["volumes"] = [mount for mount in service["volumes"]
                          if mount["target"] != "/usr/local/sbin/docker_host_ledger.sh"]
    service["volumes"].append({"type": "volume", "source": "build-control",
        "target": "/fullmag-build-control", "read_only": True, "volume": {"nocopy": True}})
    service["entrypoint"] = ["/bin/bash", "/fullmag-build-control/" + helper_relative]
    spec = {"name": control.project, "services": {"host-ledger-maintenance": service},
            "volumes": {"build-control": {"name": control.volume, "external": True}}}
    control.write(operation["root"] + "/ledger-maintenance-compose.json", spec)
    name = "fullmag-ledger-" + operation["receipt"]["attempt"]
    output = compose_capture(spec, "run", "--name", name, "--no-deps", "host-ledger-maintenance", "ensure", timeout=360)
    observed = json.loads(docker_text("inspect", name))
    if (len(observed) != 1 or observed[0].get("Image") != image
            or observed[0].get("State", {}).get("ExitCode") != 0
            or observed[0].get("State", {}).get("Running")
            or observed[0].get("Config", {}).get("Labels", {}).get("com.docker.compose.project") != control.project):
        raise BuildControlError("Host-ledger helper identity/outcome differs; resources retained")
    if hashlib.sha256(read_owned_regular(helper, maximum=ledger.MAX_HELPER_BYTES)).hexdigest() != helper_hash:
        raise BuildControlError("Host-ledger helper changed during maintenance")
    host_receipt = ledger._parse_json_lines(output.decode(), ledger.HOST_RECEIPT_SCHEMA)
    ledger._validate_host_receipt(host_receipt, {"project_id": values["project_id"],
        "mount_root": values["mount_root"], "backing_image": env["FULLMAG_HOST_LEDGER_BACKING_IMAGE"]})
    control.write(operation["root"] + "/host-ledger.json", host_receipt)
    control.write(operation["root"] + "/ledger-helper-log.json",
                  {"log": docker_text("logs", name, combined=True)})
    docker_capture("rm", observed[0]["Id"])
    backend = rendered["services"]["backend"]
    return backend, {"profile": ledger.PROFILE, "image_id": image, "environment": env,
        "mount_root": values["mount_root"], "project_id": values["project_id"],
        "backing_image": env["FULLMAG_HOST_LEDGER_BACKING_IMAGE"], "host_receipt": host_receipt,
        "maintenance_document": spec}



def _startup_helper(control, selected, image):
    """Execute host admission code only when both helper bytes match the image."""
    import fullmag_docker_runtime as runtime
    names = ("docker_startup_script.py", "fullmag_storage.py")
    command = "sha256sum " + " ".join("/opt/fullmag/" + name for name in names)
    arguments = control.helper_args(command)
    arguments[arguments.index(control.image)] = image
    result = bounded_capture(arguments, data=b"", timeout=90)
    if result.returncode:
        raise BuildControlError("Image startup-helper attestation failed")
    hashes = {}
    for line in result.stdout.decode().splitlines():
        digest, path = line.split()
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or path not in {"/opt/fullmag/" + name for name in names}:
            raise BuildControlError("Image startup-helper inventory differs")
        hashes[PurePosixPath(path).name] = digest
    if set(hashes) != set(names):
        raise BuildControlError("Image startup-helper inventory is incomplete")
    verified = {}
    for name in names:
        path = selected / "scripts" / name
        data, matches, _ = runtime._verified_startup_helper(path, hashes[name])
        if not matches:
            raise BuildControlError("Startup helper changed since image preparation: " + name)
        verified[name] = (path, data)
    return runtime._exec_verified_startup_helpers(verified), hashes


def start(args, *, reuse_state=None):
    from docker_dev import (_require_native_windows, _select_source, _compose_identity,
        _assert_no_running_fullmag, _source_git_common_directory, _workspace_state_root)
    import fullmag_docker_runtime as runtime
    from windows_folder_host import attest, publish_evidence, local_volume
    _require_native_windows()
    selected, layout = _select_source(Path(args.repo_root).resolve(strict=True), args.source_root or args.repo_root)
    identity = _compose_identity(layout)
    _assert_no_running_fullmag(identity["project_name"], identity)
    runtime.assert_loopback_port_available(args.port, identity["project_name"])
    if args.profile != "dev":
        raise BuildControlError("Volume DEV supports backend-dev; release uses its explicit managed recipe")
    if args.image or args.toolchain_image or args.source_manifest or args.include_untracked:
        raise BuildControlError("Volume DEV requires its attested dependency/image route; explicit overrides are not qualified")
    from docker_dev import _resolve_gpu_access, _verify_docker_gpu_access
    policy = getattr(args, "gpu_access", None) or "auto"
    device_access = _resolve_gpu_access(policy)
    toolchain = build_volume_toolchain(selected)
    control = BuildControl(identity, toolchain["inputs"]["build_args"]["FULLMAG_CUDA_BASE_IMAGE"])
    images = build_volume_runtime_images(selected, control, toolchain)
    image = images["backend"]["image_id"]
    device_access = _verify_docker_gpu_access(device_access, policy, image, control.project)
    _assert_no_running_fullmag(control.project, identity)
    with control.operation("development", {"source_root": str(selected), "image_id": image}) as operation:
        token = operation["receipt"]["attempt"]
        if reuse_state is None:
            state = storage.validate_path(Path(layout["runtime_root"]) / "docker-volume-dev" / token,
                                          layout["storage_root"], "Windows session storage")
            state.mkdir(parents=True, exist_ok=False)
            certificate_path = state / "windows-folder-host.json"
            certificate_path.touch(exist_ok=False)
        else:
            state = reuse_state["state"]
            certificate_path = reuse_state["host_certificate"]
        operation["receipt"]["state_root"] = str(state)
        local_volume(state)
        cache = _backend_cache(control, operation, layout, selected, image, toolchain["image_id"])
        operation["receipt"]["backend_volumes"] = cache["volume_names"]
        frontend_inputs, frontend_volume = _frontend(control, operation, selected, state, args.port, image)
        ledger_backend, ledger_profile = _host_ledger(control, operation, layout, selected, image)
        inputs = {"image_id": image, "toolchain_image_id": toolchain["image_id"],
                  "guest_provenance_path": "/opt/fullmag/control/backend/runtime-provenance.json"}
        provisional, hashes, delegation = runtime._provisional_development_certificate(inputs, identity)
        provisional["binary_hashes"] = hashes
        engine_id = docker_text("info", "--format", "{{.ID}}").strip()
        if reuse_state is None:
            certificate = attest(state, provisional, engine_id, hashes, development_build=delegation)
            publish_evidence(certificate_path, certificate)
        else:
            certificate = runtime._reuse_host_certificate(reuse_state, provisional, engine_id,
                                                         development_build=delegation)
        startup = None
        if args.script is not None:
            startup_helper, startup_hashes = _startup_helper(control, selected, image)
            authorization = startup_helper.prepare(selected, args.script,
                request_id="docker-volume-" + token, source_commit=storage.git(selected, "rev-parse", "HEAD"))
            startup_path = state / "startup-provenance.json"
            startup_digest = startup_helper.write_provenance(startup_path, authorization)
            startup = {"authorization": authorization.as_dict(), "path": str(startup_path),
                       "provenance_sha256": startup_digest, "helper_hashes": startup_hashes}
        user_data = _workspace_state_root(layout, control.project)
        git_common = _source_git_common_directory(selected)
        environment = {**os.environ, "FULLMAG_COMPOSE_PROJECT": control.project,
            "FULLMAG_COMPOSE_NETWORK": identity["network_name"],
            "FULLMAG_DOCKER_DEVICE_ACCESS": device_access,
            "FULLMAG_BUILD_CONTROL_VOLUME": control.volume,
            "FULLMAG_SOURCE_COMMIT": storage.git(selected, "rev-parse", "HEAD"),
            "FULLMAG_DEVELOPMENT_INPUTS_PATH": "/opt/fullmag/control/frontend/development-inputs.json",
            "FULLMAG_SOURCE_ROOT": str(selected), "FULLMAG_SOURCE_GIT_COMMON": str(git_common),
            "FULLMAG_DEV_IMAGE": image, "FULLMAG_TOOLCHAIN_IMAGE_ID": toolchain["image_id"],
            "FULLMAG_TOOLCHAIN_IMAGE": toolchain["image_id"],
            "FULLMAG_BACKEND_HOSTNAME": "fullmag-direct-backend-" + token[:12],
            "FULLMAG_STATE_ROOT": str(state), "FULLMAG_HOST_CERTIFICATE": str(certificate_path),
            "FULLMAG_PACKAGE_PROVENANCE": str(certificate_path),
            "FULLMAG_WORKSPACE_STATE_ROOT": str(user_data),
            "FULLMAG_DEVELOPMENT_INPUTS": str(certificate_path), "FULLMAG_HTTP_PORT": str(args.port),
            "FULLMAG_SOURCE_PROJECT_ID": identity["project_id"],
            "FULLMAG_SOURCE_WORKTREE_ID": identity["worktree_id"],
            "FULLMAG_SOURCE_CHECKOUT_KIND": identity["checkout_kind"]}
        configured = bounded_capture(["docker", "--context", "desktop-linux", "compose",
            "--project-name", control.project, "-f", str(selected / "compose.dev.yaml"),
            "config", "--format", "json"], env=environment, timeout=90)
        if configured.returncode or len(configured.stdout) > 1024 * 1024:
            raise BuildControlError("DEV Compose render failed: " + configured.stderr.decode("utf-8", "replace"))
        document = json.loads(configured.stdout)
        if device_access == "gpu":
            document["services"]["backend"]["gpus"] = [{"count": "all"}]
        backend, frontend = (document["services"][name] for name in ("backend", "frontend"))
        backend.pop("build", None)
        backend["environment"].update(cache["environment"])
        backend["environment"].update(ledger_backend["environment"])
        backend["environment"]["FULLMAG_PACKAGE_PROVENANCE"] = runtime.BACKEND_PROVENANCE_PATH
        backend["environment"]["FULLMAG_RUNTIME_PROVENANCE"] = runtime.BACKEND_PROVENANCE_PATH
        backend["environment"]["CUDA_CACHE_PATH"] = "/build/cuda-cache"
        if startup is not None:
            backend["environment"].update(FULLMAG_STARTUP_ENABLED="1",
                FULLMAG_STARTUP_SCRIPT=startup["authorization"]["container_script_path"],
                FULLMAG_STARTUP_PROVENANCE="/run/fullmag/startup-provenance.json",
                FULLMAG_STARTUP_PROVENANCE_SHA256=startup["provenance_sha256"],
                FULLMAG_STARTUP_HELPER_SHA256=startup["helper_hashes"]["docker_startup_script.py"],
                FULLMAG_STARTUP_API="http://127.0.0.1:8081")
            backend["volumes"].append({"type": "bind", "source": startup["path"],
                "target": "/run/fullmag/startup-provenance.json", "read_only": True,
                "bind": {"create_host_path": False}})
        backend["labels"].update(cache["overlay"]["services"]["backend"]["labels"])
        backend["volumes"] = [m for m in backend["volumes"]
                              if m["target"] not in {"/opt/fullmag/provenance.json", "/build", "/opt/fullmag/package", "/opt/fullmag/control"}]
        backend["volumes"] += cache["overlay"]["services"]["backend"]["volumes"] + ledger_backend["volumes"]
        frontend["volumes"] = [m for m in frontend["volumes"]
                               if m["target"] not in {"/state/development", "/run/fullmag/development-inputs.json"}]
        frontend["volumes"] += [
            {"type": "volume", "source": "frontend-build", "target": "/state/development", "volume": {"nocopy": True}},
            {"type": "volume", "source": "build-control", "target": "/opt/fullmag/control", "read_only": True, "volume": {"nocopy": True}}]
        document["volumes"] = {**cache["overlay"]["volumes"],
            "frontend-build": {"name": frontend_volume, "external": True},
            "build-control": {"name": control.volume, "external": True}}
        for service in (backend, frontend):
            service["logging"] = {"driver": "local", "options": {"max-size": "10m", "max-file": "3"}}
        # All writable bind destinations are runtime/user stores, never build data.
        for service in (backend, frontend):
            for mount in service["volumes"]:
                if mount["type"] == "bind" and not mount.get("read_only") and mount["target"] not in {"/state", "/user-data", "/host-ledger"}:
                    raise BuildControlError("Unexpected writable host bind: " + mount["target"])
        control.write(operation["root"] + "/compose.json", document)
        operation["receipt"].update(state="starting-services", state_root=str(state),
            frontend_volume=frontend_volume, backend_volumes=cache["volume_names"])
        operation["daemon_pending"] = True
        compose_capture(document, "up", "--detach", "--no-build", "--pull", "never", timeout=180)
        operation["daemon_pending"] = False
        backend_id = compose_capture(document, "ps", "--all", "--quiet", "backend").decode().strip()
        frontend_id = compose_capture(document, "ps", "--all", "--quiet", "frontend").decode().strip()
        if not backend_id or not frontend_id:
            raise BuildControlError("Compose did not return both fixed services")
        import docker_backend_volume_cache as backend_cache
        backend_cache.validate_container(json.loads(docker_text("inspect", backend_id))[0], cache)
        _finish(control, operation, document, backend_id, frontend_id, selected, state,
                certificate_path, certificate, cache, toolchain, image, git_common, ledger_profile, args.port)



def _wait_for_publication(control, operation, backend_id, *, timeout=14400):
    """A previous succeeded package is not evidence that this start finished."""
    import fullmag_docker_runtime as runtime
    deadline = time.monotonic() + timeout
    started_at = None
    handoff_seen = False
    last_report = 0.0
    while time.monotonic() < deadline:
        actual = json.loads(docker_text("inspect", backend_id))[0]
        current_start = actual.get("State", {}).get("StartedAt")
        if started_at is None:
            started_at = current_start
            operation["receipt"]["backend_started_at"] = started_at
        elif current_start != started_at:
            raise BuildControlError("Backend incarnation changed during build observation")
        if not actual["State"]["Running"]:
            logs = docker_text("logs", "--tail", "200", backend_id, combined=True)
            control.write(operation["root"] + "/backend-failure-log.json", {"log": logs})
            raise BuildControlError("Backend exited during build; logs and volumes retained: " + logs[-4000:])
        if not handoff_seen:
            logs = docker_text("logs", "--since", started_at, "--tail", "200", backend_id, combined=True)
            handoff_seen = "phase=start state=handoff" in logs
            if handoff_seen:
                operation["receipt"]["backend_package_cache_hit"] = "phase=start state=cache-hit" in logs
                control.write(operation["root"] + "/handoff-log.json", {"started_at": started_at, "log": logs})
        if handoff_seen:
            raw = docker_capture("exec", backend_id, "/usr/local/bin/python3", "-c",
                runtime._BACKEND_BUILD_DOCUMENTS_SCRIPT)
            observed = json.loads(raw.stdout)
            receipt, provenance = observed["receipt"]["value"], observed["provenance"]["value"]
            if (receipt.get("state") != "succeeded" or provenance.get("state") != "succeeded"
                    or provenance.get("build_receipt_sha256") != observed["receipt"]["sha256"]):
                raise BuildControlError("Current handoff has no matching succeeded package/provenance")
            return receipt, provenance
        if time.monotonic() - last_report > 45:
            print("Backend is building in its persistent Compose service; Docker data retained.", flush=True)
            last_report = time.monotonic()
        time.sleep(3)
    raise BuildControlError("Backend publication observation timed out; services and volumes retained")


def _finish(control, operation, document, backend_id, frontend_id, selected, state,
            certificate_path, certificate, cache, toolchain, image, git_common, ledger_profile, port):
    import fullmag_docker_runtime as runtime
    token = operation["receipt"]["attempt"]
    inputs = {"image_id": image, "toolchain_image_id": toolchain["image_id"],
              "guest_provenance_path": "/opt/fullmag/control/backend/runtime-provenance.json"}
    receipt, provenance = _wait_for_publication(control, operation, backend_id)
    control.write(operation["root"] + "/backend-build-receipt.json", receipt)
    control.write(operation["root"] + "/provenance.json", provenance)
    operation["receipt"]["config_sha256"] = hashlib.sha256(canonical(document)).hexdigest()
    operation["receipt"]["windows_storage_delegation_reused"] = certificate.get("restart_verified") is True
    # Use the existing source/binary validation before rotating Windows admission.
    inputs.update(device_access=document["services"]["backend"]["environment"]["FULLMAG_DOCKER_DEVICE_ACCESS"],
        backend_cache=cache, package_root="/opt/fullmag/package", run_id=token,
        source_root=str(selected), git_common_dir=str(git_common), build_profile="dev",
        startup_helper_hashes={}, backend_start_receipt="docker-volume://" + control.volume + "/" + operation["root"] + "/receipt.json",
        helper_context="image-owned")
    assembly = runtime._assembly_from_backend_start(inputs, receipt, provenance, container_id=backend_id)
    # An admitted delegation intentionally permits subsequent live builds.
    # Rotating it back to unverified after handoff races the serving process.
    if certificate.get("restart_verified") is not True:
        certificate = runtime._refresh_development_certificate(certificate, assembly, inputs)
        runtime._publish_bound_development_certificate(certificate_path, state / ".fullmag-windows-folder-owner.json", certificate)
    runtime._complete_backend_storage_preflight(docker_text, backend_id, state, certificate_path, certificate, None,
        log_writer=lambda output: control.write(operation["root"] + "/storage-probe-log.json", {"log": output}))
    import docker_host_ledger as ledger
    verify_spec = ledger_profile["maintenance_document"]
    verify_name = "fullmag-ledger-verify-" + token
    output = compose_capture(verify_spec, "run", "--name", verify_name, "--no-deps", "host-ledger-maintenance", "verify", timeout=240)
    actual_verify = json.loads(docker_text("inspect", verify_name))
    if (len(actual_verify) != 1 or actual_verify[0].get("Image") != image
            or actual_verify[0].get("State", {}).get("Running")
            or actual_verify[0].get("State", {}).get("ExitCode") != 0
            or actual_verify[0].get("Config", {}).get("Labels", {}).get("com.docker.compose.project") != control.project):
        raise BuildControlError("Fresh host-ledger verification identity/outcome differs")
    host_receipt = ledger._parse_json_lines(output.decode(), ledger.HOST_RECEIPT_SCHEMA)
    ledger._validate_host_receipt(host_receipt, {"project_id": ledger_profile["project_id"],
        "mount_root": ledger_profile["mount_root"], "backing_image": ledger_profile["backing_image"]})
    ledger_profile["host_receipt"] = host_receipt
    ledger_attestation = ledger.validate_container(json.loads(docker_text("inspect", backend_id))[0], ledger_profile, docker_text)
    control.write(operation["root"] + "/host-ledger-attestation.json", ledger_attestation)
    control.write(operation["root"] + "/ledger-verify-log.json",
                  {"log": docker_text("logs", verify_name, combined=True)})
    docker_capture("rm", actual_verify[0]["Id"])
    # Observe the existing incarnations; a readiness check must never run up
    # again or wait an hour after the supervisor has already closed admission.
    process_script = """import json,pathlib,sys
sys.path.insert(0,'/opt/fullmag')
import runtime_service
try:
 raw=runtime_service._bounded_regular(pathlib.Path('/state/.fullmag/runtime-service/process-tree.json'),'process receipt')
except FileNotFoundError:
 print(json.dumps({'state':'not-published'}))
else:
 print(raw.decode('utf-8'))
"""
    image_config = json.loads(docker_text("image", "inspect", image))[0]["Config"]
    readiness_deadline = time.monotonic() + 3900
    while time.monotonic() < readiness_deadline:
        services = json.loads(docker_text("inspect", backend_id, frontend_id))
        for service, observed in zip(("backend", "frontend"), services):
            _validate_retained_service(document, observed, service, image_config,
                expected_started_at=operation["receipt"]["backend_started_at"] if service == "backend" else None)
            if not observed.get("State", {}).get("Running"):
                raise BuildControlError("DEV service exited before readiness: " + service)
        process_receipt = json.loads(docker_text("exec", backend_id, "/usr/local/bin/python3", "-B", "-c", process_script))
        if str(process_receipt.get("state", "")).startswith("failed"):
            logs = docker_text("logs", "--since", operation["receipt"]["backend_started_at"],
                               "--tail", "100", backend_id, combined=True)
            if "Startup or runtime failed; admission closed:" in logs:
                control.write(operation["root"] + "/process-failure.json", process_receipt)
                raise BuildControlError("Runtime admission failed; services retained: " + str(process_receipt.get("error", "unknown failure"))[:4096])
        if all(service.get("State", {}).get("Health", {}).get("Status") == "healthy" for service in services):
            break
        time.sleep(3)
    else:
        raise BuildControlError("API/frontend readiness timed out; services and Docker data retained")
    startup_environment = document["services"]["backend"]["environment"]
    if startup_environment.get("FULLMAG_STARTUP_ENABLED") == "1":
        from windows_folder_host import read_owned_regular
        startup_path = state / "startup-provenance.json"
        data = read_owned_regular(startup_path, maximum=256 * 1024)
        if hashlib.sha256(data).hexdigest() != startup_environment["FULLMAG_STARTUP_PROVENANCE_SHA256"]:
            raise BuildControlError("Startup authorization changed after admission")
        authorization = json.loads(data)
        helper, hashes = _startup_helper(control, selected, image)
        if hashes["docker_startup_script.py"] != startup_environment["FULLMAG_STARTUP_HELPER_SHA256"]:
            raise BuildControlError("Startup helper differs from retained service")
        operation["receipt"]["startup"] = runtime._wait_for_startup_ready(state, authorization, startup_helper=helper)
    operation["receipt"].update(state="succeeded", backend_container=backend_id,
        frontend_container=frontend_id, url="http://127.0.0.1:" + str(port),
        source_commit=provenance["commit"], source_digest=provenance["source_digest"],
        source_snapshot_sha256=provenance["source_snapshot_sha256"],
        backend_build_receipt_sha256=provenance["build_receipt_sha256"])



def _validate_retained_service(document, actual, service, image_config, *, expected_started_at=None):
    """Reject configuration/mount drift and a replaced observed incarnation."""
    if expected_started_at is not None and actual.get("State", {}).get("StartedAt") != expected_started_at:
        raise BuildControlError("Backend incarnation changed during readiness observation")
    from run_managed_browser import host_path
    expected = document["services"][service]
    config, host = actual.get("Config", {}), actual.get("HostConfig", {})
    environment = dict(item.split("=", 1) for item in config.get("Env", []) if "=" in item)
    if any(environment.get(key) != str(value) for key, value in expected.get("environment", {}).items()):
        raise BuildControlError("Retained service environment differs: " + service)
    if any(config.get("Labels", {}).get(key) != value for key, value in expected.get("labels", {}).items()):
        raise BuildControlError("Retained service source/cache labels differ: " + service)
    for field, observed in (("hostname", config.get("Hostname")), ("user", config.get("User"))):
        if field in expected and expected[field] != observed:
            raise BuildControlError("Retained service configuration differs: " + service + "/" + field)
    for field, image_field in (("entrypoint", "Entrypoint"), ("command", "Cmd")):
        resolved = expected.get(field)
        if resolved is None:
            resolved = image_config.get(image_field)
        if (resolved or None) != (config.get(image_field) or None):
            raise BuildControlError("Retained service image command differs: " + service + "/" + field)
    if host.get("ReadonlyRootfs") is not True or host.get("Privileged") is not False:
        raise BuildControlError("Retained service isolation differs: " + service)
    mounts = {mount["Destination"]: mount for mount in actual.get("Mounts", [])}
    if len(mounts) != len(actual.get("Mounts", [])):
        raise BuildControlError("Retained service has duplicate mount destinations")
    targets = {mount["target"] for mount in expected["volumes"]}
    temporary = {value.split(":", 1)[0] for value in expected.get("tmpfs", [])}
    if (targets - set(mounts) or set(mounts) - targets - temporary
            or set(host.get("Tmpfs") or {}) != temporary
            or any(mounts[target].get("Type") != "tmpfs" for target in set(mounts) - targets)):
        raise BuildControlError("Retained service has missing or extra mounts: " + service)
    for mount in expected["volumes"]:
        observed = mounts[mount["target"]]
        if observed.get("Type") != mount["type"] or bool(observed.get("RW")) == bool(mount.get("read_only", False)):
            raise BuildControlError("Retained mount type/access differs: " + mount["target"])
        if mount["type"] == "volume":
            name = document["volumes"][mount["source"]]["name"]
            if observed.get("Name") != name:
                raise BuildControlError("Retained named-volume identity differs: " + mount["target"])
        elif mount["type"] == "bind" and host_path(observed["Source"]) != Path(mount["source"]).resolve():
            raise BuildControlError("Retained source/runtime bind differs: " + mount["target"])


def _assert_private_restart_network(actual, ids, project):
    """Only the pinned frontend may expose this backend to browser commands."""
    backend = actual["backend"]
    if backend.get("HostConfig", {}).get("PortBindings") or backend.get("HostConfig", {}).get("NetworkMode") in {"host", "none"}:
        raise BuildControlError("Idle restart requires an unpublished private backend")
    networks = backend.get("NetworkSettings", {}).get("Networks", {})
    if len(networks) != 1:
        raise BuildControlError("Idle restart requires one private application bridge")
    observed = json.loads(docker_text("network", "inspect", next(iter(networks))))
    if (len(observed) != 1 or observed[0].get("Driver") != "bridge"
            or observed[0].get("Labels", {}).get("com.docker.compose.project") != project
            or set(observed[0].get("Containers", {})) - set(ids.values())):
        raise BuildControlError("Idle restart bridge has unknown consumers; no backend will be stopped")


def restart_idle(args):
    return _retained_operation(args, recreate_services=False, restart_idle_service=True)


def recreate(args):
    return _retained_operation(args, recreate_services=True)


def resume(args):
    return _retained_operation(args, recreate_services=False)


def _retained_operation(args, *, recreate_services, restart_idle_service=False):
    """Resume observation/admission of one exact failed start; never restart the backend."""
    from docker_dev import _require_native_windows, _select_source, _compose_identity
    from windows_folder_host import read_owned_regular
    _require_native_windows()
    selected, layout = _select_source(Path(args.repo_root).resolve(strict=True), args.source_root)
    identity = _compose_identity(layout)
    from docker_build_control import toolchain_configuration
    configured = toolchain_configuration(selected, identity)
    control = BuildControl(identity, configured["services"]["fem-gpu-toolchain"]["build"]["args"]["FULLMAG_CUDA_BASE_IMAGE"])
    control.prepare()
    if not re.fullmatch(r"[0-9a-f]{32}", args.attempt):
        raise BuildControlError("Resume requires an exact attempt UUID")
    previous_root = "development/attempts/" + args.attempt
    previous = control.read(previous_root + "/terminal.json")
    allowed = {"failed-confirmed", "succeeded"} if recreate_services or restart_idle_service or getattr(args, "restart_backend", False) else {"failed-confirmed"}
    if previous.get("state") not in allowed or previous.get("compose_project") != control.project:
        raise BuildControlError("Retained start has no admissible terminal outcome")
    document = control.read(previous_root + "/compose.json")
    if hashlib.sha256(canonical(document)).hexdigest() != args.config_sha256 or document.get("name") != control.project:
        raise BuildControlError("Resume Compose identity/CAS differs")
    image = previous["inputs"]["image_id"]
    if previous["inputs"]["source_root"] != str(selected):
        raise BuildControlError("Resume source selection differs")
    ids = {service: compose_capture(document, "ps", "--all", "--quiet", service).decode().strip()
           for service in ("backend", "frontend")}
    actual = {}
    image_config = json.loads(docker_text("image", "inspect", image))[0]["Config"]
    for service, identifier in ids.items():
        records = json.loads(docker_text("inspect", identifier))
        if len(records) != 1:
            raise BuildControlError("Ambiguous retained service")
        observed = actual[service] = records[0]
        labels = observed.get("Config", {}).get("Labels", {})
        if (observed.get("Image") != image or labels.get("com.docker.compose.project") != control.project
                or labels.get("com.docker.compose.service") != service
                or labels.get("org.fullmag.source.worktree-id") != identity["worktree_id"]):
            raise BuildControlError("Retained container ownership differs")
        recorded_id = previous.get(service + "_container")
        if recorded_id is not None and observed.get("Id") != recorded_id:
            raise BuildControlError("Recorded container incarnation differs")
        _validate_retained_service(document, observed, service, image_config)
    if restart_idle_service:
        if (not actual["backend"]["State"]["Running"]
                or actual["backend"]["State"].get("Health", {}).get("Status") != "healthy"):
            raise BuildControlError("Idle restart requires a healthy backend; an active build is never interrupted")
        state = storage.validate_path(Path(previous["state_root"]), layout["runtime_root"], "retained Windows sessions")
        certificate_path = state / "windows-folder-host.json"
        certificate = json.loads(read_owned_regular(certificate_path))
        if json.loads(read_owned_regular(state / ".fullmag-windows-folder-owner.json")) != certificate:
            raise BuildControlError("Retained Windows owner/certificate differs")
        environment = document["services"]["backend"]["environment"]
        if environment.get("FULLMAG_STARTUP_ENABLED") == "1":
            raise BuildControlError("Startup activation requires dedicated recovery; idle restart will not repeat Solve")
        cache = control.read(previous_root + "/backend-cache.json")
        import docker_backend_volume_cache as cache_adapter
        cache_adapter.validate_container(actual["backend"], cache)
        ledger_profile = {"profile": "host-ledger-v1", "image_id": image, "environment": environment,
            "mount_root": environment["FULLMAG_HOST_LEDGER_MOUNT_ROOT"],
            "project_id": environment["FULLMAG_HOST_LEDGER_PROJECT_ID"],
            "backing_image": environment["FULLMAG_HOST_LEDGER_BACKING_IMAGE"],
            "host_receipt": control.read(previous_root + "/host-ledger.json"),
            "maintenance_document": control.read(previous_root + "/ledger-maintenance-compose.json")}
        with control.operation("iteration", {"source_root": str(selected), "image_id": image,
                                            "attempt": args.attempt, "config_sha256": args.config_sha256}) as operation:
            _assert_private_restart_network(actual, ids, control.project)
            operation["daemon_pending"] = True
            docker_capture("stop", "--time", "60", ids["frontend"], timeout=90)
            operation["daemon_pending"] = False
            _assert_private_restart_network(actual, ids, control.project)
            probe = """import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:8081/v2/platform/health',timeout=5) as response:
 document=json.load(response)
 if response.status!=200 or document.get('status')!='ok' or document.get('active_session') is not False:
  raise RuntimeError('Backend has an active or unknown session; restart refused')
 print(json.dumps(document))
"""
            try:
                health = json.loads(docker_text("exec", ids["backend"], "/usr/local/bin/python3", "-B", "-c", probe))
                if health.get("status") != "ok" or health.get("active_session") is not False:
                    raise BuildControlError("Backend has an active or unknown session; idle restart refused")
            except Exception:
                operation["daemon_pending"] = True
                docker_capture("start", ids["frontend"], timeout=90)
                operation["daemon_pending"] = False
                raise
            control.write(operation["root"] + "/idle-preflight.json", health)
            control.write(operation["root"] + "/compose.json", document)
            operation["receipt"].update(state="restarting-idle-backend", state_root=str(state),
                backend_volumes=previous["backend_volumes"], frontend_volume=previous["frontend_volume"])
            operation["daemon_pending"] = True
            docker_capture("stop", "--time", "60", ids["backend"], timeout=90)
            docker_capture("start", ids["backend"], timeout=90)
            docker_capture("start", ids["frontend"], timeout=90)
            operation["daemon_pending"] = False
            git_common = Path(next(m["source"] for m in document["services"]["backend"]["volumes"]
                                   if m["target"] == "/opt/fullmag/source-git"))
            _finish(control, operation, document, ids["backend"], ids["frontend"], selected, state,
                certificate_path, certificate, cache, {"image_id": environment["FULLMAG_TOOLCHAIN_IMAGE_ID"]},
                image, git_common, ledger_profile, args.port)
        return
    if recreate_services:
        if actual["backend"]["State"]["Running"]:
            raise BuildControlError("Recreation requires the backend stopped; an active build/runtime is never interrupted")
        if document["services"]["backend"]["environment"].get("FULLMAG_STARTUP_ENABLED") == "1":
            raise BuildControlError("Retained startup activation requires its dedicated recovery; recreation will not repeat Solve")
        state = storage.validate_path(Path(previous["state_root"]), layout["runtime_root"], "retained Windows sessions")
        certificate_path = state / "windows-folder-host.json"
        certificate = json.loads(read_owned_regular(certificate_path))
        owner_path = state / ".fullmag-windows-folder-owner.json"
        if json.loads(read_owned_regular(owner_path)) != certificate or certificate.get("image_id") != image:
            raise BuildControlError("Retained Windows storage owner/certificate differs")
        fresh_state = bool(getattr(args, "fresh_state", False))
        if not fresh_state and not certificate.get("restart_verified"):
            raise BuildControlError("Unadmitted storage cannot rotate as an admitted runtime; use explicit --fresh-state to preserve the old root")
        # Exact recorded helper only; unknown group resources are never deleted.
        helper_ids = []
        for helper_name in ("fullmag-ledger-" + previous["attempt"], "fullmag-ledger-verify-" + previous["attempt"]):
            helper = docker_capture("inspect", helper_name, allow_failure=True)
            if not helper.returncode:
                helper_document = json.loads(helper.stdout)[0]
                labels = helper_document.get("Config", {}).get("Labels", {})
                if (helper_document.get("Image") != image or helper_document.get("State", {}).get("Running")
                        or labels.get("com.docker.compose.project") != control.project
                        or labels.get("com.docker.compose.service") != "host-ledger-maintenance"):
                    raise BuildControlError("Recorded ledger helper identity/outcome differs")
                helper_ids.append(helper_document["Id"])
        with control.operation("recreate-services", {"attempt": args.attempt, "config_sha256": args.config_sha256}) as operation:
            control.write(operation["root"] + "/retained-containers.json", actual)
            operation["receipt"].update(state="stopping-owned-frontend", previous_state_root=str(state),
                                        fresh_state=fresh_state)
            operation["daemon_pending"] = True
            if actual["frontend"]["State"]["Running"]:
                docker_capture("stop", "--time", "60", ids["frontend"], timeout=90)
            for identifier in ids.values():
                if json.loads(docker_text("inspect", identifier))[0]["State"]["Running"]:
                    raise BuildControlError("An owned service is still running; resources retained")
            docker_capture("rm", *ids.values())
            if helper_ids:
                docker_capture("rm", *helper_ids)
            operation["daemon_pending"] = False
            operation["receipt"].update(state="succeeded", removed_containers=list(ids.values()),
                                        retained_volumes=previous["backend_volumes"], retained_frontend_volume=previous["frontend_volume"])
        reuse = None if fresh_state else {"state": state, "host_certificate": certificate_path,
            "owner_marker": owner_path, "receipt": {"image_id": image}}
        return start(args, reuse_state=reuse)
    restart_backend = bool(getattr(args, "restart_backend", False))
    if restart_backend:
        if actual["backend"]["State"]["Running"]:
            raise BuildControlError("Starting the retained backend requires it to be stopped; active runtime is never interrupted")
    elif not actual["backend"]["State"]["Running"] or actual["frontend"]["State"]["Running"]:
        raise BuildControlError("Resume requires the retained backend running and frontend stopped")
    state = storage.validate_path(Path(previous["state_root"]), layout["runtime_root"], "retained Windows sessions")
    certificate_path = state / "windows-folder-host.json"
    certificate = json.loads(read_owned_regular(certificate_path))
    cache = control.read(previous_root + "/backend-cache.json")
    import docker_backend_volume_cache as cache_adapter
    cache_adapter.validate_container(actual["backend"], cache)
    environment = document["services"]["backend"]["environment"]
    ledger_receipt = control.read(previous_root + "/host-ledger.json")
    ledger_profile = {"profile": "host-ledger-v1", "image_id": image, "environment": environment,
        "mount_root": environment["FULLMAG_HOST_LEDGER_MOUNT_ROOT"],
        "project_id": environment["FULLMAG_HOST_LEDGER_PROJECT_ID"],
        "backing_image": environment["FULLMAG_HOST_LEDGER_BACKING_IMAGE"], "host_receipt": ledger_receipt,
        "maintenance_document": control.read(previous_root + "/ledger-maintenance-compose.json")}
    with control.operation("resume", {"attempt": args.attempt, "config_sha256": args.config_sha256}) as operation:
        operation["receipt"].update(state="resuming-observation", state_root=str(state),
            backend_volumes=previous["backend_volumes"], frontend_volume=previous["frontend_volume"])
        if not actual["frontend"]["State"]["Running"]:
            _frontend(control, operation, selected, state, args.port, image)
            compose_capture(document, "start", "frontend", timeout=90)
        if restart_backend:
            operation["daemon_pending"] = True
            compose_capture(document, "start", "backend", timeout=90)
            operation["daemon_pending"] = False
        git_common = Path(environment["FULLMAG_SOURCE_GIT_COMMON"]) if "FULLMAG_SOURCE_GIT_COMMON" in environment else Path(
            next(m["source"] for m in document["services"]["backend"]["volumes"] if m["target"] == "/opt/fullmag/source-git"))
        _finish(control, operation, document, ids["backend"], ids["frontend"], selected, state,
            certificate_path, certificate, cache, {"image_id": environment["FULLMAG_TOOLCHAIN_IMAGE_ID"]},
            image, git_common, ledger_profile, args.port)
