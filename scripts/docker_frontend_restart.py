"""Recover one frontend receipt after Docker proves its private container stopped."""
import base64
import hashlib
import inspect
import json
from pathlib import Path
import re
import shlex

from docker_build_control import BuildControlError, bounded_capture, docker_capture


def guest(request, root="/state/development", contract=None):
    import base64
    import fcntl
    import hashlib
    import json
    import os
    from pathlib import Path
    import stat
    import uuid

    if contract is None:
        import importlib.util
        import sys
        spec = importlib.util.spec_from_file_location("fullmag_image_frontend_restart_contract", "/opt/fullmag/frontend_dev.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Image frontend receipt contract is unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        contract = (str(module.RECEIPT_PATH), str(getattr(module, "DIAGNOSTIC_RECEIPT_PATH", "")))
    if contract == ("/run/fullmag/frontend-owner/receipt.json", "/state/development/frontend-dev-receipt.json"):
        return {"state": "no-recovery-required"}
    if contract not in (("/state/development/frontend-dev-receipt.json", ""),
                         ("/state/development/frontend-dev-receipt.json", "/state/development/frontend-dev-receipt.json")):
        raise RuntimeError("Image frontend receipt contract is unsupported")
    root = Path(root)
    def open_path(path, flags):
        path = Path(path)
        if not path.is_absolute() or ".." in path.parts:
            raise RuntimeError("Recovery path must be absolute without traversal")
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in path.parts[1:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                os.close(parent)
                parent = child
            return os.open(path.name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        finally:
            os.close(parent)

    lock = open_path(root / "cache/.fullmag-frontend-runtime.lock", os.O_RDWR)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            raise RuntimeError("Frontend runtime lock must be regular")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            descriptor = open_path(root / "frontend-dev-receipt.json", os.O_RDONLY)
        except FileNotFoundError:
            if request["mode"] == "read":
                return {"state": "not-started"}
            raise RuntimeError("Frontend receipt disappeared before recovery")
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1024 * 1024:
                raise RuntimeError("Frontend receipt must be one bounded regular file")
            raw = stream.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise RuntimeError("Frontend receipt exceeded its bound")
        value = json.loads(raw)
        if (value.get("schema") != "fullmag.docker-frontend-development-receipt.v1"
                or value.get("source_root") != request["source_root"]
                or value.get("host_port") != request["port"]
                or value.get("workspace_root") != "/state/development/workspace"
                or value.get("frontend_root") != "/state/development/cache"
                or value.get("image_id", request["proof"]["image_id"]) != request["proof"]["image_id"]):
            raise RuntimeError("Frontend receipt scope differs from stopped incarnation")
        digest = hashlib.sha256(raw).hexdigest()
        if request["mode"] == "read":
            return {"sha256": digest, "original": base64.b64encode(raw).decode()}
        if request["mode"] != "recover" or digest != request["expected_sha256"]:
            raise RuntimeError("Frontend recovery receipt CAS differs")
        proof = request["proof"]
        if (proof.get("schema") != "fullmag.stopped-frontend-incarnation.v1"
                or proof.get("running") is not False or proof.get("pid") != 0
                or proof.get("pid_mode") not in ("", "private")
                or not proof.get("started_at") or not proof.get("finished_at")):
            raise RuntimeError("Frontend recovery requires stopped private Docker incarnation")
        if value.get("state") == "stopped":
            return {"state": "already-stopped", "original_sha256": digest}
        if value.get("state") not in {"running", "starting", "installing", "stopping", "unknown", "stop-unknown", "stop-timeout", "failed", "stopped-after-failure"}:
            raise RuntimeError("Frontend receipt has an unsupported recovery state")
        value.update(state="stopped", docker_restart_recovery={"original_sha256": digest, "incarnation": proof})
        directory = open_path(root, os.O_RDONLY | os.O_DIRECTORY)
        temporary = ".frontend-recovery-" + uuid.uuid4().hex
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o660, dir_fd=directory)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write((json.dumps(value, sort_keys=True) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            # The runtime flock fences all managed frontend writers.
            current = open_path(root / "frontend-dev-receipt.json", os.O_RDONLY)
            with os.fdopen(current, "rb") as stream:
                if hashlib.sha256(stream.read(1024 * 1024 + 1)).hexdigest() != digest:
                    raise RuntimeError("Frontend receipt changed before publication")
            os.replace(temporary, "frontend-dev-receipt.json", src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)
        return {"state": "stopped", "original_sha256": digest}
    finally:
        os.close(lock)


def _proof(actual, control, document):
    identifier, image = actual.get("Id", ""), actual.get("Image", "")
    state, host = actual.get("State", {}), actual.get("HostConfig", {})
    labels = actual.get("Config", {}).get("Labels", {})
    if (not re.fullmatch(r"[0-9a-f]{64}", identifier)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", image)
            or image != document["services"]["frontend"]["image"]
            or labels.get("com.docker.compose.project") != control.project
            or labels.get("com.docker.compose.service") != "frontend"
            or labels.get("org.fullmag.source.worktree-id") != control.identity["worktree_id"]
            or state.get("Status") != "exited" or state.get("Running") is not False
            or state.get("Restarting") is not False or state.get("Pid") != 0
            or host.get("PidMode", "") not in ("", "private")
            or any(not isinstance(state.get(key), str) or state[key].startswith("0001-") or not state[key]
                   for key in ("StartedAt", "FinishedAt"))):
        raise BuildControlError("Frontend recovery requires its exact stopped private Docker incarnation")
    mounts = [mount for mount in actual.get("Mounts", []) if mount.get("Destination") == "/state/development"]
    expected = [mount for mount in document["services"]["frontend"]["volumes"]
                if mount.get("target") == "/state/development"]
    if (len(mounts) != 1 or len(expected) != 1 or mounts[0].get("Type") != "volume"
            or expected[0].get("type") != "volume" or not mounts[0].get("RW")
            or mounts[0].get("Name") != document["volumes"][expected[0]["source"]]["name"]):
        raise BuildControlError("Frontend recovery state-volume identity differs")
    return {"schema": "fullmag.stopped-frontend-incarnation.v1", "container_id": identifier,
            "image_id": image, "started_at": state["StartedAt"], "finished_at": state["FinishedAt"],
            "running": False, "pid": 0, "pid_mode": host.get("PidMode", ""),
            "volume": mounts[0]["Name"], "compose_project": control.project}


def recover_stopped_frontend(control, operation, frontend_actual, document, source, port):
    proof = _proof(frontend_actual, control, document)

    def recheck():
        observed = json.loads(docker_capture("inspect", proof["container_id"]).stdout)
        if len(observed) != 1 or _proof(observed[0], control, document) != proof:
            raise BuildControlError("Frontend stopped incarnation changed during recovery")
        active = docker_capture("ps", "--quiet", "--no-trunc", "--filter", "volume=" + proof["volume"]).stdout.split()
        if active:
            raise BuildControlError("Frontend state volume has an active consumer; receipt preserved")

    def invoke(request):
        code = inspect.getsource(guest) + "\nimport json,sys\nprint(json.dumps(guest(json.load(sys.stdin))))\n"
        arguments = control.helper_args("exec /usr/local/bin/python3 -I -B -c " + shlex.quote(code))
        # This helper needs only the exact state volume, not writable control storage.
        index = arguments.index("--mount")
        del arguments[index:index + 2]
        arguments[arguments.index("--entrypoint"):arguments.index("--entrypoint")] = [
            "--mount", "type=volume,src=" + proof["volume"] + ",dst=/state/development,volume-nocopy"]
        arguments[arguments.index(control.image)] = proof["image_id"]
        result = bounded_capture(arguments, data=json.dumps(request).encode(), timeout=60)
        if result.returncode:
            raise BuildControlError("Frontend receipt recovery failed: " + result.stderr.decode("utf-8", "replace")[-2048:])
        return json.loads(result.stdout)

    request = {"mode": "read", "proof": proof, "source_root": str(source), "port": port}
    recheck()
    original = invoke(request)
    if original.get("state") in {"not-started", "no-recovery-required"}:
        recheck()
        return original
    raw = base64.b64decode(original["original"], validate=True)
    if hashlib.sha256(raw).hexdigest() != original["sha256"]:
        raise BuildControlError("Frontend receipt archive hash differs")
    archive = operation["root"] + "/frontend-restart"
    control.write_bytes(archive + "/original-receipt.json", raw)
    control.write(archive + "/stopped-incarnation.json", {**proof, "original_sha256": original["sha256"]})
    recheck()
    result = invoke({**request, "mode": "recover", "expected_sha256": original["sha256"]})
    recheck()
    control.write(archive + "/receipt.json", result)
    return result
