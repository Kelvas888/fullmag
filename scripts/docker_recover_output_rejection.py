#!/usr/bin/env python3
"""Finalize only the reviewed output-mapping rejection; never replay a request.

The original receipt and started marker remain immutable. This trusts the
managed private network boundary, not concurrent privileged Docker operators.
"""
import argparse
from contextlib import contextmanager
import hashlib
import inspect
import json
from pathlib import Path
import shlex
import subprocess
import time

from docker_build_control import BuildControlError, bounded_capture, canonical, docker_capture
import docker_volume_activation_reconcile as reconcile

# This recovery is deliberately limited to the reviewed, clean runtime build.
REVIEWED_COMMIT = "7a3ced8d7c3c643e27ffe7cff451c212558228f8"
REVIEWED_SNAPSHOT = "86ce3beb19c2bcca3ee88e3838edb6b061c0c667fc621f7c1f853aa3369ab4d3"
CODE = "docker_startup_output_mapping_required"
MESSAGE = "FULLMAG_SCRIPT_OUTPUT_ROOT is required for default or relative script output paths"


def validate_rejection(receipt):
    error = receipt.get("error", "")
    prefix = "fullmag_image_docker_startup_script.StartupScriptError: startup activation returned HTTP 422: "
    lines = error.rstrip().splitlines()
    if not lines or not lines[-1].startswith(prefix):
        raise BuildControlError("Not the exact retained output-mapping HTTP 422")
    response = json.loads(lines[-1][len(prefix):])
    expected = {"code": CODE, "capability_reason": CODE, "message": MESSAGE, "error": MESSAGE,
                "diagnostics": None, "revision_context": None}
    if response != expected:
        raise BuildControlError("Output-mapping rejection response differs")
    return response



def validate_incarnation(observed, not_after, expected=None):
    from datetime import datetime
    from decimal import Decimal
    import re

    state = observed.get("State", {})
    started = state.get("StartedAt", "")
    try:
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z", started)
        if match is None:
            raise ValueError("Expected a Docker UTC RFC3339 timestamp")
        seconds = datetime.fromisoformat(match[1] + "+00:00").timestamp()
        timestamp = Decimal(int(seconds)) + Decimal("0." + (match[2] or "0"))
    except (TypeError, ValueError) as error:
        raise BuildControlError("Invalid container start timestamp") from error
    if state.get("Running") is not True or timestamp > Decimal(str(not_after)):
        raise BuildControlError("Container restarted after the retained activation")
    if expected is not None and (observed.get("Id") != expected.get("Id")
            or started != expected.get("State", {}).get("StartedAt")):
        raise BuildControlError("Container incarnation changed")

def probe(store_root, ledger_root):
    import fcntl
    import json
    import os
    from pathlib import Path
    import stat
    import urllib.request
    import uuid

    def read_api():
        result = {}
        for key, path in (("health", "health"), ("queue", "compute/queue"), ("runtime", "runtime-service")):
            with urllib.request.urlopen("http://127.0.0.1:8081/v2/platform/" + path, timeout=5) as response:
                raw = response.read(1024 * 1024 + 1)
                instance = response.headers.get("x-fullmag-api-instance")
                if response.status != 200 or len(raw) > 1024 * 1024 or str(uuid.UUID(instance)) != instance:
                    raise RuntimeError("Invalid API proof")
                if result.get("instance", instance) != instance:
                    raise RuntimeError("API incarnation changed")
                result["instance"] = instance
                result[key] = json.loads(raw)
        if result["health"].get("status") != "ok" or result["health"].get("active_session") is not False:
            raise RuntimeError("Current workspace is not empty")
        if result["queue"].get("schema_version") != "compute_queue.v1" or result["queue"].get("items") != []:
            raise RuntimeError("Compute queue is not empty")
        runtime = result["runtime"]
        if runtime.get("configured") is not True or runtime.get("state") != "ready" or runtime.get("reason", {}).get("code") != "service_ready":
            raise RuntimeError("Native runtime is not ready")
        return result

    before = read_api()
    descriptors = []
    try:
        for root in (Path(ledger_root), Path(store_root)):
            if not root.is_absolute() or ".." in root.parts or any(p.is_symlink() for p in (root, *root.parents)):
                raise RuntimeError("Unsafe store path")
            fd = os.open(root / "WRITER.lock", os.O_RDWR | os.O_NOFOLLOW)
            descriptors.append(fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise RuntimeError("Invalid writer lock")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in ("runs", "live_command_journals", "development"):
            path = Path(store_root) / name
            if path.is_symlink() or (path.exists() and (not path.is_dir() or any(path.iterdir()))):
                raise RuntimeError("Accepted store is not empty: " + name)
        fd = os.open(Path(ledger_root) / "HOST_RESOURCE_LEDGER.json", os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise RuntimeError("Invalid ledger")
            raw = stream.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024 or json.loads(raw).get("reservations") != []:
            raise RuntimeError("Host ledger has reservations")
        after = read_api()
        if before["instance"] != after["instance"]:
            raise RuntimeError("API incarnation changed")
        return after
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


@contextmanager
def recovery_lock(control):
    # The original helper keeps operation.lock. Serialize explicit recovery
    # separately, including frontend quiesce and restoration.
    script = "umask 027; test ! -L /control/output-rejection.lock; exec 8>/control/output-rejection.lock; flock -n 8; printf 'READY\\n'; cat >/dev/null"
    process = subprocess.Popen(control.helper_args(script), stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        if control._line(process) != "READY":
            raise BuildControlError("Another output-rejection recovery holds the lock")
        yield
    finally:
        process.stdin.close()
        process.wait(timeout=30)


def publish_script(control, records, terminal_path, proof_path, attempt):
    q = shlex.quote
    lines = ["umask 027", "regular() { test -f \"$1\"; test ! -L \"$1\"; test \"$(stat -c %h \"$1\")\" = 1; test \"$(readlink -f \"$1\")\" = \"$1\"; }"]
    for relative, raw in records.items():
        path = control.path(relative)
        lines += ["regular " + q(path), "test \"$(sha256sum " + q(path) + " | cut -d' ' -f1)\" = " + q(hashlib.sha256(raw).hexdigest())]
    terminal, proof = control.path(terminal_path), control.path(proof_path)
    parent = str(Path(terminal).parent)
    checks = list(lines[2:])
    lines += ["test ! -e " + q(terminal), "test ! -L " + q(terminal),
              "test ! -e /control/activation/unresolved.json; test ! -L /control/activation/unresolved.json",
              "exec 9</control/operation.lock; if flock -n 9; then exit 1; fi",
              "test \"$(cat /control/active)\" = " + q(attempt),
              "t=$(mktemp " + q(parent + "/.rejection.XXXXXXXX") + ")",
              "trap 'rm -f -- \"$t\"' EXIT", "cat >\"$t\"; sync \"$t\"",
              "test ! -e " + q(proof), "test ! -L " + q(proof),
              "cp -- \"$t\" " + q(proof), "sync " + q(proof), "sync " + q(parent)]
    lines += checks + ["mv -T \"$t\" " + q(terminal), "sync " + q(parent)]
    return "\n".join(lines)


def recover(args):
    from docker_dev_up import _selected_context
    from docker_dev_host import require_host
    from docker_volume_activate import _linked_runtime_terminals, _validate_running_group
    from docker_volume_dev import _assert_private_restart_network, _startup_helper
    from docker_dev_codegen import _backend_documents, _validate_backend

    require_host()
    reconcile._attempt(args.activation_attempt, "activation attempt")
    reconcile._hash(args.receipt_sha256, "receipt SHA-256")
    _, selected, _, identity, control = _selected_context(args)
    control.prepare()
    if control.namespace:
        raise BuildControlError("Output rejection recovery requires the original control namespace")
    root = "activation/attempts/" + args.activation_attempt
    raw = reconcile._control_bytes(control, root + "/receipt.json")
    if hashlib.sha256(raw).hexdigest() != args.receipt_sha256:
        raise BuildControlError("Activation receipt changed")
    inputs = json.loads(raw)["inputs"]
    development = reconcile._attempt(inputs.get("development_attempt"), "development attempt")
    previous = control.read("development/attempts/" + development + "/terminal.json")
    document = control.read("development/attempts/" + development + "/compose.json")
    config_sha = hashlib.sha256(canonical(document)).hexdigest()
    image = previous["inputs"]["image_id"]
    if previous["inputs"].get("source_root") != str(selected):
        raise BuildControlError("Development source differs")
    terminals = _linked_runtime_terminals(control, development, previous, source_root=str(selected), image=image, config_sha256=config_sha)
    last_error = None
    for terminal in terminals:
        try:
            backend, frontend = _validate_running_group(control, identity, document, terminal, image, source_root=str(selected))
            break
        except BuildControlError as error:
            last_error = error
    else:
        raise BuildControlError("No running retained group matches") from last_error
    receipt, receipt_raw, pins = reconcile._validate_activation_receipt(control,
        activation_attempt=args.activation_attempt, development_attempt=development, config_sha256=config_sha,
        source_root=str(selected), image_id=image, backend_id=backend)
    if receipt_raw != raw:
        raise BuildControlError("Activation receipt changed during discovery")
    response = validate_rejection(receipt)
    ids = {"backend": backend, "frontend": frontend}

    def inspect_services():
        return {key: json.loads(docker_capture("inspect", value).stdout)[0] for key, value in ids.items()}

    with recovery_lock(control):
        records = {root + "/receipt.json": raw, "active": reconcile._control_bytes(control, "active")}
        if records["active"].strip() != args.activation_attempt.encode():
            raise BuildControlError("Another operation owns the lease")
        marker_path = pins["activation_receipt_path"].removeprefix("/opt/fullmag/control/")
        for path in (marker_path, root + "/startup-provenance.json"):
            records[path] = reconcile._control_bytes(control, path)
        marker = json.loads(records[marker_path])
        provenance = json.loads(records[root + "/startup-provenance.json"])
        if (hashlib.sha256(records[root + "/startup-provenance.json"]).hexdigest() != pins["provenance_sha256"]
                or marker.get("state") != "started" or marker.get("result") is not None or marker.get("rejection") is not None):
            raise BuildControlError("Original marker/provenance differs")
        if (marker.get("schema") != "fullmag.docker-startup-activation-receipt.v1"
                or marker.get("authorization") != provenance
                or marker.get("request_id") != pins["request_id"]
                or marker.get("source_sha256") != pins["source_sha256"]
                or marker.get("provenance_sha256") != pins["provenance_sha256"]):
            raise BuildControlError("Started marker authorization differs")
        for value in (provenance,):
            if any(value.get(key) != pins[key] for key in ("request_id", "source_sha256", "source_relative")) or value.get("source_commit") != REVIEWED_COMMIT:
                raise BuildControlError("Original activation source identity differs")
        script = selected / pins["source_relative"]
        if not script.resolve().is_relative_to(selected) or hashlib.sha256(script.read_bytes()).hexdigest() != pins["source_sha256"]:
            raise BuildControlError("Original script changed")
        helper_name = "fullmag-control-" + args.activation_attempt
        helper_document, helper_id = reconcile._validate_helper(control, helper_name, args.activation_attempt)
        validate_incarnation(helper_document, receipt["finished_at"])
        helper_log = reconcile._validate_helper_logged(helper_id)
        _, helper_hashes = _startup_helper(control, selected, image)
        if helper_hashes["docker_startup_script.py"] != receipt["helper_sha256"]:
            raise BuildControlError("Image-owned activation helper differs")
        package, runtime, package_sha, hashes = _backend_documents(backend)
        source, runtime_sha, binary_sha = _validate_backend(package, runtime, package_sha, hashes)
        if source["commit"] != REVIEWED_COMMIT or source["snapshot"] != REVIEWED_SNAPSHOT or source["worktree_state"] != "clean":
            raise BuildControlError("Runtime does not match the reviewed pre-admission implementation")
        original = inspect_services()
        validate_incarnation(original["backend"], receipt["started_at"])
        _assert_private_restart_network(original, ids, control.project)
        environment = document["services"]["backend"]["environment"]
        probe_script = inspect.getsource(probe) + "\nimport json,sys\nprint(json.dumps(probe(*sys.argv[1:])))"
        docker_capture("stop", "--time", "60", frontend, timeout=90)
        try:
            fresh = inspect_services()
            for key in ids:
                if fresh[key]["Id"] != original[key]["Id"] or fresh[key]["State"]["StartedAt"] != original[key]["State"]["StartedAt"]:
                    raise BuildControlError("Service incarnation changed")
            if fresh["frontend"]["State"]["Running"] is not False or fresh["backend"]["State"]["Running"] is not True:
                raise BuildControlError("Frontend was not quiesced")
            _assert_private_restart_network(fresh, ids, control.project)
            proof = json.loads(docker_capture("exec", backend, "/usr/local/bin/python3", "-B", "-c", probe_script,
                environment.get("FULLMAG_RUNS_ROOT", "/state/runs/docker-all") + "/session-store",
                environment.get("FULLMAG_HOST_LEDGER_ROOT", "/host-ledger/ledger"), timeout=60).stdout)
            fresh_helper, observed_helper = reconcile._validate_helper(control, helper_name, args.activation_attempt)
            validate_incarnation(fresh_helper, receipt["finished_at"], helper_document)
            validate_incarnation(inspect_services()["backend"], receipt["started_at"], original["backend"])
            if hashlib.sha256(script.read_bytes()).hexdigest() != pins["source_sha256"]:
                raise BuildControlError("Original script changed before publication")
            if observed_helper != helper_id:
                raise BuildControlError("Original helper changed")
            terminal = {**receipt, "state": "failed-confirmed", "activation_state": "rejected",
                "reason": "confirmed-output-mapping-pre-admission-rejection", "finished_at": time.time(),
                "original_receipt_sha256": args.receipt_sha256, "response": response,
                "rejection_proof": {"api": proof, "backend_started_at": original["backend"]["State"]["StartedAt"],
                    "source": source, "package_receipt_sha256": package_sha, "runtime_provenance_sha256": runtime_sha,
                    "api_binary_sha256": binary_sha, "helper_id": helper_id, "helper_log": helper_log,
                    "records_sha256": {path: hashlib.sha256(data).hexdigest() for path, data in records.items()}}}
            command = publish_script(control, records, root + "/terminal.json", root + "/output-rejection-proof.json", args.activation_attempt)
            result = bounded_capture(control.helper_args(command), data=canonical(terminal) + b"\n", timeout=90)
            if result.returncode:
                raise BuildControlError("Recovery publication refused; evidence retained: " + result.stderr.decode("utf-8", "replace")[-1024:])
            reconcile._wait_for_helper_exit(helper_id)
        finally:
            docker_capture("start", frontend, timeout=90)
    print(json.dumps({"state": "failed-confirmed", "activation_attempt": args.activation_attempt,
                      "terminal": root + "/terminal.json", "retry": "new request ID required"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--activation-attempt", required=True)
    parser.add_argument("--receipt-sha256", required=True)
    args = parser.parse_args()
    try:
        recover(args)
    except (BuildControlError, OSError, ValueError, KeyError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
