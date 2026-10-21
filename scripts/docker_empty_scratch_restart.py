"""Read-only proof for restarting an explicitly selected empty scratch session."""
import inspect
import json
import re

from docker_build_control import BuildControlError, docker_capture


def validate_export(value, expected_session):
    import hashlib
    import json
    import uuid

    def require(condition, message):
        if not condition:
            raise RuntimeError("Empty scratch restart refused: " + message)

    session, status, scene = value["session"], value["status"], value["scene"]
    identity = status["session"]
    instance = value["api_instance"]
    require(str(uuid.UUID(instance)) == instance, "invalid API incarnation")
    require(session.get("session_id") == expected_session == identity.get("session_id") == scene["scene"].get("id"), "session changed")
    require(session.get("status") == "awaiting_command" and session.get("script") is None
            and session.get("script_path") == "", "session is not untouched scratch")
    created = identity.get("created_at")
    require(isinstance(created, str) and created.isdigit()
            and identity.get("session_epoch") == expected_session + "@" + created
            and isinstance(identity.get("request_scope_epoch"), str)
            and identity["request_scope_epoch"].startswith(instance + ":"), "session incarnation changed")
    require(status.get("run") is None and status["solver"].get("state") == "awaiting_command"
            and status["metrics"].get("total_steps") == 0 and status["domain"].get("cell_count") == 0,
            "runtime or run exists")
    require(bool(status.get("resources")) and all(type(v) is int and v == 0 or k == "domain_generation_id" and v == "0"
            for k, v in status["resources"].items()), "workspace was modified")
    require(scene.get("version") == "scene.v2" and type(scene.get("revision")) is int
            and scene["revision"] == 0 and scene["scene"].get("source_of_truth") == "ui", "scene was modified")
    for key, item in scene.items():
        if key not in {"version", "revision", "scene", "study", "editor"}:
            require(item in ({}, []), "scene contains authored data: " + key)
    require(scene["study"].get("exchange_enabled") is False and scene["study"].get("demag_enabled") is False,
            "scene contains active physics")
    commands = value["commands"]
    require(commands.get("commands") == [] and commands.get("revision") == 0
            and all(commands.get(key) == 0 for key in ("pending_count", "accepted_count", "dispatched_count",
                "running_count", "completed_count", "rejected_count", "failed_count")), "command history is not empty")
    require(value["compute_queue"].get("schema_version") == "compute_queue.v1"
            and value["compute_queue"].get("items") == [], "compute queue is not empty")
    require(value["health"].get("status") == "ok" and value["health"].get("active_session") is True,
            "session health changed")
    runtime = value["runtime_service"]
    require(runtime.get("configured") is True and runtime.get("state") == "ready"
            and runtime.get("reason", {}).get("code") == "service_ready", "native runtime is not ready")
    stable_status = {**status, "metrics": {
        key: item for key, item in status["metrics"].items() if key != "uptime_seconds"
    }}
    stable = {"api_instance": instance, "session": session, "status": stable_status,
              "scene": scene, "commands": commands, "compute_queue": value["compute_queue"]}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def probe(expected_session, store_root, ledger_root):
    import fcntl
    import json
    import os
    from pathlib import Path
    import stat
    import time
    import urllib.request

    def read_export():
        result = {}
        for name, path in (("session", "/v2/sessions/current"), ("status", "/v2/sessions/current/status"),
                ("scene", "/v2/sessions/current/model/scene"), ("commands", "/v2/sessions/current/simulation/commands"),
                ("compute_queue", "/v2/platform/compute/queue"), ("runtime_service", "/v2/platform/runtime-service"),
                ("health", "/v2/platform/health")):
            with urllib.request.urlopen("http://127.0.0.1:8081" + path, timeout=5) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024 or response.status != 200:
                    raise RuntimeError("Unbounded or failed scratch API response")
                instance = response.headers.get("x-fullmag-api-instance")
                if "api_instance" in result and instance != result["api_instance"]:
                    raise RuntimeError("API incarnation changed during export")
                result["api_instance"] = instance
                result[name] = json.loads(raw)
        return result

    before = read_export()
    fingerprint = validate_export(before, expected_session)
    roots = [Path(ledger_root), Path(store_root)]
    descriptors = []
    try:
        for root in roots:
            if not root.is_absolute() or ".." in root.parts or any(p.is_symlink() for p in (root, *root.parents)):
                raise RuntimeError("Unsafe accepted store or ledger root")
            fd = os.open(root / "WRITER.lock", os.O_RDWR | os.O_NOFOLLOW)
            descriptors.append(fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise RuntimeError("Writer lock is not regular")
            deadline = time.monotonic() + 5
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Writer remains busy")
                    time.sleep(0.05)
        for name in ("runs", "live_command_journals", "development"):
            path = roots[1] / name
            if path.is_symlink() or (path.exists() and (not path.is_dir() or any(path.iterdir()))):
                raise RuntimeError("Scratch store has durable admissions or history: " + name)
        fd = os.open(roots[0] / "HOST_RESOURCE_LEDGER.json", os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise RuntimeError("Host ledger is not regular")
            raw = stream.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024 or json.loads(raw).get("reservations") != []:
            raise RuntimeError("Host ledger has reservations or invalid data")
    finally:
        for fd in reversed(descriptors):
            os.close(fd)
    after = read_export()
    if validate_export(after, expected_session) != fingerprint:
        raise RuntimeError("Scratch workspace changed during preflight")
    return {"schema": "fullmag.empty-scratch-restart-proof.v1", "fingerprint": fingerprint,
            "session_id": expected_session, "export": after}


def capture(backend_id, session_id, environment):
    if not isinstance(session_id, str) or re.fullmatch(r"session-[a-zA-Z0-9_-]+", session_id) is None:
        raise BuildControlError("Empty scratch restart requires an exact session ID")
    script = inspect.getsource(validate_export) + "\n" + inspect.getsource(probe) + "\nimport json,sys\nprint(json.dumps(probe(*sys.argv[1:])))\n"
    output = docker_capture("exec", backend_id, "/usr/local/bin/python3", "-B", "-c", script, session_id,
        environment.get("FULLMAG_RUNS_ROOT", "/state/runs/docker-all") + "/session-store",
        environment.get("FULLMAG_HOST_LEDGER_ROOT", "/host-ledger/ledger"), timeout=90).stdout
    if len(output) > 8 * 1024 * 1024:
        raise BuildControlError("Empty scratch proof exceeds its size bound")
    proof = json.loads(output)
    if (proof.get("schema") != "fullmag.empty-scratch-restart-proof.v1" or proof.get("session_id") != session_id
            or validate_export(proof["export"], session_id) != proof.get("fingerprint")):
        raise BuildControlError("Empty scratch proof differs from its session export")
    return proof
