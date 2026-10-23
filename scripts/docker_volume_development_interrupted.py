"""Confirm an interrupted pre-publication development; never start services."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from docker_build_control import BuildControl, BuildControlError, canonical, docker_capture, toolchain_configuration
from docker_volume_reconcile import SHA, TOKEN, digest, fingerprint, read_raw, require, write_immutable
from docker_volume_activation_reconcile import _probe_helper_absence
from docker_volume_toolchain_reconcile import host_clients

SCHEMA = "fullmag.docker-development-interrupted.v1"
CONTROLLERS = ("docker_build_control.py", "docker_volume_dev.py", "docker_volume_reconcile.py",
               "docker_volume_activation_reconcile.py", "docker_volume_toolchain_reconcile.py",
               "docker_volume_prestart_recovery.py")


def validate_request(r):
    require(isinstance(r, dict) and set(r) == {"schema", "attempt", "source_root", "source_revision",
        "compose_project", "engine_id", "observed_at", "receipt_sha256", "compose_sha256", "active_sha256",
        "current_sha256", "verified_sha256", "helper_absence_sha256", "backend_log_sha256", "containers",
        "controller_inputs", "controller_sha256", "attempt_documents", "storage_certificate_sha256"}, "Exact interrupted-development request required")
    require(r["schema"] == SCHEMA and isinstance(r["attempt"], str) and TOKEN.fullmatch(r["attempt"]),
            "Invalid schema or attempt")
    for k in ("receipt_sha256", "compose_sha256", "active_sha256", "helper_absence_sha256",
              "backend_log_sha256", "controller_sha256"):
        require(isinstance(r[k], str) and SHA.fullmatch(r[k]), "Invalid digest: " + k)
    for k in ("current_sha256", "verified_sha256"):
        require(r[k] is None or isinstance(r[k], str) and SHA.fullmatch(r[k]), "Invalid pointer: " + k)
    require(isinstance(r["observed_at"], (int, float)) and not isinstance(r["observed_at"], bool)
            and 0 < r["observed_at"] < 10**11, "Pinned observation time required")
    require(isinstance(r["containers"], dict) and set(r["containers"]) == {"backend", "frontend"},
            "Both service pins required")
    for pin in r["containers"].values():
        require(isinstance(pin, dict) and set(pin) == {"id", "image", "fingerprint", "state_sha256"},
                "Exact service pin required")
        require(all(isinstance(pin[k], str) and SHA.fullmatch(pin[k]) for k in ("id", "fingerprint", "state_sha256"))
                and isinstance(pin["image"], str) and pin["image"].startswith("sha256:")
                and SHA.fullmatch(pin["image"][7:]), "Invalid service pin")
    require(r["containers"]["backend"]["id"] != r["containers"]["frontend"]["id"], "Distinct services required")
    require(isinstance(r["source_revision"], str) and len(r["source_revision"]) == 40
        and all(x in "0123456789abcdef" for x in r["source_revision"])
        and isinstance(r["engine_id"], str) and bool(r["engine_id"]), "Source/engine pins required")
    require(isinstance(r["storage_certificate_sha256"], str) and SHA.fullmatch(r["storage_certificate_sha256"]), "Storage certificate pin required")
    require(isinstance(r["attempt_documents"], dict) and set(r["attempt_documents"]) == {
        "backend-cache.json", "group-ledger.json", "frontend-seed.json", "cache-maintenance-compose.json"}
        and all(isinstance(x, str) and SHA.fullmatch(x) for x in r["attempt_documents"].values()), "Attempt documents required")
    require(isinstance(r["controller_inputs"], dict) and set(r["controller_inputs"]) == set(CONTROLLERS)
        and all(isinstance(x, str) and SHA.fullmatch(x) for x in r["controller_inputs"].values()), "Controller pin set differs")


def validate_original(original, document, r, control, source):
    require(original.get("schema") == "fullmag.docker-build-operation.v1"
        and original.get("phase") == "development" and original.get("state") == "starting"
        and original.get("attempt") == r["attempt"] and original.get("compose_project") == control.project
        and original.get("control_volume") == control.volume
        and original.get("helper_container") == "fullmag-control-" + r["attempt"], "Original operation differs")
    require(original.get("inputs", {}).get("source_root") == str(source)
        and r["source_root"] == str(source) and r["compose_project"] == control.project,
        "Source or project differs")
    require(original.get("config_sha256") is None and "backend_started_at" not in original,
        "Publication was already observed")
    require(document.get("name") == control.project and set(document.get("services", {})) == {"backend", "frontend"},
        "Retained Compose differs")
    require(document["services"]["backend"].get("environment", {}).get("FULLMAG_STARTUP_ENABLED") != "1",
        "Startup activation is outside this recovery")
    require(original["inputs"]["image_id"] == r["containers"]["backend"]["image"], "Backend image differs")
    for service, pin in r["containers"].items():
        require(document["services"][service]["image"] == pin["image"], "Service image differs")


def validate_container(actual, pin, service, project):
    state = actual.get("State", {})
    require(actual.get("Id") == pin["id"] and actual.get("Image") == pin["image"]
        and fingerprint(actual) == pin["fingerprint"] and digest(canonical(state)) == pin["state_sha256"],
        "Service incarnation changed: " + service)
    require(actual.get("Config", {}).get("Labels", {}).get("com.docker.compose.project") == project
        and actual["Config"]["Labels"].get("com.docker.compose.service") == service,
        "Service ownership differs")
    require(state.get("Status") == "exited" and state.get("Pid") == 0 and state.get("ExitCode") == 255
        and all(state.get(k) is False for k in ("Running", "Paused", "Restarting", "Dead", "OOMKilled"))
        and not state.get("Error"), "Only stopped interrupted services are supported")


def failure_result(raw, document, r, request_sha):
    result = copy.deepcopy(json.loads(raw))
    result.pop("exit_code", None)
    result.update(state="failed-confirmed", finished_at=r["observed_at"],
        config_sha256=digest(canonical(document)), build_data_qualification="NOT VERIFIED",
        backend_container=r["containers"]["backend"]["id"], frontend_container=r["containers"]["frontend"]["id"],
        error="Development interrupted before package handoff; producer exit status unavailable",
        reconciliation={"schema": SCHEMA, "request_sha256": request_sha,
            "original_receipt_sha256": r["receipt_sha256"],
            "compose_binding": "retained-configuration-not-package-qualification",
            "service_exit_codes": {"backend": 255, "frontend": 255},
            "producer_exit_code": None, "observation_time_not_build_completion": True,
            "containers": r["containers"]})
    return canonical(result) + b"\n"


def observe(control, source, r, result=None, helper_name=None):
    require(not control.namespace, "Namespaced control volumes need their dedicated recovery")
    require(docker_capture("info", "--format", "{{.ID}}").stdout.decode().strip() == r["engine_id"], "Engine changed")
    revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True, capture_output=True).stdout.decode().strip()
    require(revision == r["source_revision"], "Source revision changed")
    for name, sha in r["controller_inputs"].items():
        require(digest((source / "scripts" / name).read_bytes()) == sha, "Controller changed: " + name)
    root = "development/attempts/" + r["attempt"]
    raw = read_raw(control, root + "/unknown-receipt.json", optional=True)
    if raw is None:
        raw = read_raw(control, root + "/receipt.json")
    require(digest(raw) == r["receipt_sha256"], "Original receipt changed")
    document_raw = read_raw(control, root + "/compose.json")
    require(digest(document_raw) == r["compose_sha256"], "Compose changed")
    original, document = json.loads(raw), json.loads(document_raw)
    validate_original(original, document, r, control, source)
    for name, sha in r["attempt_documents"].items():
        require(digest(read_raw(control, root + "/" + name)) == sha, "Attempt document changed: " + name)
    import docker_volume_dev as dev
    state = Path(original["state_root"])
    dev._retained_certificate(state, document)
    require(digest(dev._certificate_path(state).read_bytes()) == r["storage_certificate_sha256"], "Storage certificate changed")
    result_sha = digest(result) if result is not None else None
    for path, expected in ((root + "/receipt.json", r["receipt_sha256"]),
                           ("development/current.json", r["current_sha256"]),
                           ("development/verified.json", r["verified_sha256"])):
        current = read_raw(control, path, optional=True)
        allowed = {expected} | ({result_sha} if result_sha and not path.endswith("verified.json") else set())
        require((digest(current) if current is not None else None) in allowed, "Durable pointer changed: " + path)
    terminal = read_raw(control, root + "/terminal.json", optional=True)
    require(terminal is None or result is not None and terminal == result, "A different terminal exists")
    active = read_raw(control, "active")
    require(active == (r["attempt"] + "\n").encode() and digest(active) == r["active_sha256"], "Active owner changed")
    require(_probe_helper_absence(original["helper_container"]) == r["helper_absence_sha256"], "Original helper is present")
    group_ids = docker_capture("ps", "--all", "--no-trunc", "--filter", "label=com.docker.compose.project=" + control.project,
                              "--format", "{{.ID}}").stdout.decode().split()
    actuals = json.loads(docker_capture("inspect", *group_ids).stdout) if group_ids else []
    app_ids = set()
    for actual in actuals:
        if helper_name and actual.get("Name") == "/" + helper_name:
            continue
        service = actual.get("Config", {}).get("Labels", {}).get("com.docker.compose.service")
        require(service in r["containers"], "Unexpected group resource retained")
        validate_container(actual, r["containers"][service], service, control.project)
        app_ids.add(actual["Id"])
    require(app_ids == {pin["id"] for pin in r["containers"].values()}, "Service inventory differs")
    for filename in ("backend-build-receipt.json", "provenance.json", "handoff-log.json"):
        require(read_raw(control, root + "/" + filename, optional=True) is None, "Package handoff was observed")
    logs = docker_capture("logs", r["containers"]["backend"]["id"])
    require(len(logs.stdout) + len(logs.stderr) <= 33554432
        and digest(logs.stdout + logs.stderr) == r["backend_log_sha256"]
        and b"phase=start state=handoff" not in logs.stdout + logs.stderr, "Backend log changed or handoff exists")
    running = docker_capture("ps", "--no-trunc", "--format", "{{.ID}}").stdout.decode().split()
    volumes = set(original["backend_volumes"].values()) | {original["frontend_volume"]}
    for actual in (json.loads(docker_capture("inspect", *running).stdout) if running else []):
        if helper_name and actual.get("Name") == "/" + helper_name:
            continue
        require(not any(m.get("Name") in volumes and m.get("RW") is True for m in actual.get("Mounts", [])),
            "A live container consumes retained volumes")
    # This scanner identifies our held Docker helper as a mutating client.
    # Scan before acquiring it; canonical admissions thereafter share its flock.
    if helper_name is None:
        host_clients(source)
    return raw, document


def transaction_script(control, r, request_path, request_sha, result_path, result_sha):
    root = "development/attempts/" + r["attempt"]
    q = shlex.quote
    checks = []
    for path, allowed in (("active", [r["active_sha256"]]), (request_path, [request_sha]),
        (result_path, [result_sha]), (root + "/compose.json", [r["compose_sha256"]]),
        (root + "/receipt.json", [r["receipt_sha256"], result_sha]),
        ("development/current.json", [r["current_sha256"], result_sha]),
        ("development/verified.json", [r["verified_sha256"]]),
        (root + "/terminal.json", [None, result_sha]), (root + "/unknown-receipt.json", [None, r["receipt_sha256"]])):
        path = control.path(path)
        alternatives = ["test \"$observed\" = " + q(x) for x in allowed if x is not None]
        if None in allowed:
            alternatives.append("test \"$observed\" = absent")
        checks.append("observe " + q(path) + "; { " + " || ".join(alternatives) + "; }")
    for name, sha in r["attempt_documents"].items():
        checks.append("observe " + q(control.path(root + "/" + name)) + "; test \"$observed\" = " + q(sha))
    verification = "\n".join(checks)
    return """umask 027
regular() { test -f "$1"; test ! -L "$1"; test "$(readlink -f "$1")" = "$1"; test "$(stat -c %h "$1")" = 1; }
observe() { if test -e "$1"; then regular "$1"; observed=$(sha256sum "$1" | cut -d' ' -f1); else test ! -L "$1"; observed=absent; fi; }
regular /control/operation.lock
exec 9<>/control/operation.lock
flock -n 9
""" + verification + "\nprintf 'READY\\n'\nIFS= read -r decision\ntest \"$decision\" = APPLY\n" + verification + "\nregular " + q(control.path(root + "/unknown-receipt.json")) + "; test \"$(sha256sum " + q(control.path(root + "/unknown-receipt.json")) + " | cut -d\' \' -f1)\" = " + q(r["receipt_sha256"]) + "\n" + """publish() { local path="$1" payload="$2" parent temp; parent="${path%/*}"; test "$(readlink -f "$parent")" = "$parent"; temp=$(mktemp "$parent/.interrupt.XXXXXXXX"); cat "$payload" > "$temp"; sync "$temp"; mv -T "$temp" "$path"; sync "$parent"; }
""" + "\n".join("publish " + q(control.path(path)) + " " + q(control.path(result_path)) for path in
        (root + "/receipt.json", "development/current.json", root + "/terminal.json")) + "\n" + \
        "rm -- /control/active\nsync /control\nprintf 'COMMITTED\\n'\n"


def reconcile(args):
    from docker_dev import _select_source, _compose_identity
    source, layout = _select_source(Path(args.source_root).resolve(strict=True), args.source_root)
    identity = _compose_identity(layout)
    cfg = toolchain_configuration(source, identity)
    control = BuildControl(identity, cfg["services"]["fem-gpu-toolchain"]["build"]["args"]["FULLMAG_CUDA_BASE_IMAGE"])
    request_raw = read_raw(control, args.request)
    require(digest(request_raw) == args.request_sha256, "Request CAS differs")
    r = json.loads(request_raw); validate_request(r)
    require(digest(Path(__file__).read_bytes()) == r["controller_sha256"], "Recovery controller differs")
    base = "development/attempts/" + r["attempt"]
    original_raw = read_raw(control, base + "/unknown-receipt.json", optional=True)
    if original_raw is None:
        original_raw = read_raw(control, base + "/receipt.json")
    require(digest(original_raw) == r["receipt_sha256"], "Original receipt CAS differs")
    document = json.loads(read_raw(control, base + "/compose.json"))
    result = failure_result(original_raw, document, r, args.request_sha256)
    if read_raw(control, "active", optional=True) is None:
        require(read_raw(control, base + "/terminal.json", optional=True) == result
            and read_raw(control, base + "/receipt.json") == result, "No matching completed recovery")
        print(json.dumps({"state": "failed-confirmed", "replay": True, "services_started": False, "archived_receipt_confirmation_only": True}))
        return
    observe(control, source, r, result)
    result_path = "verification/development-interrupted/" + args.request_sha256 + "/result.json"
    write_immutable(control, result_path, result)
    script = transaction_script(control, r, args.request, args.request_sha256, result_path, digest(result))
    helper_name = "fullmag-development-reconcile-" + r["attempt"]
    helper = subprocess.Popen(control.helper_args(script, name=helper_name), stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        require(control._line(helper) == "READY", "Recovery lease was not acknowledged")
        observe(control, source, r, result, helper_name)
        if args.preview:
            helper.stdin.close()
            require(helper.wait(timeout=30) != 0, "Preview unexpectedly committed")
            print(json.dumps({"state": "validated-only", "result_sha256": digest(result), "native_state_changed": False}))
            return
        write_immutable(control, base + "/unknown-receipt.json", original_raw)
        helper.stdin.write(b"APPLY\n"); helper.stdin.flush(); helper.stdin.close()
        require(control._line(helper) == "COMMITTED", "Recovery outcome unknown; replay exact request")
        require(helper.wait(timeout=30) == 0, "Recovery helper failed")
    finally:
        if helper.stdin and not helper.stdin.closed:
            helper.stdin.close()
    require(read_raw(control, base + "/terminal.json") == result and read_raw(control, "active", optional=True) is None,
            "Recovery completion not confirmed")
    print(json.dumps({"state": "failed-confirmed", "result_sha256": digest(result), "services_started": False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(); args.preview = not args.apply
    reconcile(args)

if __name__ == "__main__":
    main()
