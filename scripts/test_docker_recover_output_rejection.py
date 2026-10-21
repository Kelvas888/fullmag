import copy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from docker_build_control import BuildControl, BuildControlError
import docker_recover_output_rejection as recovery


class OutputRejectionTests(unittest.TestCase):
    def response(self):
        return {"code": recovery.CODE, "capability_reason": recovery.CODE, "message": recovery.MESSAGE,
                "error": recovery.MESSAGE, "diagnostics": None, "revision_context": None}

    def test_only_exact_typed_rejection_is_accepted(self):
        prefix = "fullmag_image_docker_startup_script.StartupScriptError: startup activation returned HTTP 422: "
        error = "Traceback (most recent call last):\n" + prefix + json.dumps(self.response())
        self.assertEqual(recovery.validate_rejection({"error": error}), self.response())
        for changed in (error.replace("422", "409"), error.replace("422", "500"), "timeout", error + "\nunknown",
                        error.replace(recovery.CODE, "unsupported_capability"), error.replace(recovery.MESSAGE, "other")):
            with self.subTest(changed=changed), self.assertRaises((BuildControlError, ValueError)):
                recovery.validate_rejection({"error": changed})

    def test_materialization_rejection_requires_exact_message_and_response(self):
        response = {"code": recovery.MATERIALIZATION_CODE, "capability_reason": recovery.MATERIALIZATION_CODE,
            "message": recovery.MATERIALIZATION_MESSAGE, "error": recovery.MATERIALIZATION_MESSAGE,
            "diagnostics": None, "revision_context": None}
        prefix = "fullmag_image_docker_startup_script.StartupScriptError: startup activation returned HTTP 422: "
        self.assertEqual(recovery.validate_rejection({"error": prefix + json.dumps(response)}), response)
        for key, value in (("message", "another materialization failure"), ("code", recovery.CODE),
                ("diagnostics", {}), ("revision_context", {})):
            changed = {**response, key: value}
            with self.subTest(key=key), self.assertRaises(BuildControlError):
                recovery.validate_rejection({"error": prefix + json.dumps(changed)})
        for status in (409, 500):
            with self.assertRaises(BuildControlError):
                recovery.validate_rejection({"error": prefix.replace("422", str(status)) + json.dumps(response)})

    def test_failed_startup_probe_binds_request_source_and_unchanged_empty_session(self):
        pins = {"request_id": "docker-volume-probe", "source_sha256": "a" * 64, "source_relative": "study.py"}
        session_id = "docker-startup-" + hashlib.sha256((pins["request_id"] + "\0" + pins["source_sha256"]).encode()).hexdigest()
        source_path = "/opt/fullmag/source/study.py"
        for obstacle in (None, "session", "source", "request", "path", "state", "run", "steps", "task", "reservation", "changed"):
            with self.subTest(obstacle=obstacle), tempfile.TemporaryDirectory() as directory:
                store, ledger = Path(directory) / "store", Path(directory) / "ledger"
                for root in (store, ledger):
                    root.mkdir(); (root / "WRITER.lock").touch()
                (ledger / "HOST_RESOURCE_LEDGER.json").write_text(json.dumps({"reservations": [1] if obstacle == "reservation" else []}))
                session = {"session_id": session_id, "status": "startup_failed", "script_path": source_path,
                           "script": {"sha256": pins["source_sha256"], "path": source_path}}
                status = {"session": {"session_id": session_id}, "run": None,
                          "solver": {"state": "startup_failed"}, "metrics": {"total_steps": 0, "uptime_seconds": 1},
                          "domain": {"cell_count": 0}, "resources": {"scene_revision": 1}}
                if obstacle == "session": session["session_id"] = "other"
                if obstacle == "source": session["script"]["sha256"] = "b" * 64
                if obstacle == "path": session["script"]["path"] = "/other.py"
                if obstacle == "state": session["status"] = "awaiting_command"
                if obstacle == "run": status["run"] = {"id": "run"}
                if obstacle == "steps": status["metrics"]["total_steps"] = 1
                responses = {"/v2/platform/health": {"status": "ok", "active_session": True},
                    "/v2/platform/compute/queue": {"schema_version": "compute_queue.v1", "items": [1] if obstacle == "task" else []},
                    "/v2/platform/runtime-service": {"configured": True, "state": "ready", "reason": {"code": "service_ready"}},
                    "/v2/sessions/current": session, "/v2/sessions/current/status": status}
                calls = []
                class Response:
                    status = 200
                    headers = {"x-fullmag-api-instance": "11111111-1111-4111-8111-111111111111"}
                    def __init__(self, value): self.value = value
                    def __enter__(self): return self
                    def __exit__(self, *args): pass
                    def read(self, maximum): return json.dumps(self.value).encode()
                def get(url, **kwargs):
                    path = url.removeprefix("http://127.0.0.1:8081")
                    calls.append(path)
                    value = copy.deepcopy(responses[path])
                    if len(calls) > 5 and path.endswith("/status"):
                        value["metrics"]["uptime_seconds"] = 2
                        if obstacle == "changed": value["resources"]["scene_revision"] += 1
                    return Response(value)
                supplied = {**pins, "request_id": "foreign-request"} if obstacle == "request" else pins
                with patch("urllib.request.urlopen", side_effect=get):
                    if obstacle is None:
                        proof = recovery.probe(str(store), str(ledger), json.dumps(supplied))
                        self.assertEqual(proof["session"]["session_id"], session_id)
                        self.assertEqual(len(calls), 10)
                        # The older output-mapping branch still refuses an active session.
                        with self.assertRaises(RuntimeError):
                            recovery.probe(str(store), str(ledger))
                    else:
                        with self.assertRaises(RuntimeError):
                            recovery.probe(str(store), str(ledger), json.dumps(supplied))

    def test_materialization_stop_journals_before_stop_and_requires_matching_drain(self):
        for obstacle in (None, "prior", "bytes", "exit", "oom", "incarnation", "owner", "drain", "wrong-case"):
            with self.subTest(obstacle=obstacle):
                events = []
                class Control:
                    def write(self, path, value): events.append(("write", path, copy.deepcopy(value)))
                owner = {"owner_token": "owner", "pid": 10, "children": [{"role": "scheduler", "pid": 11}]}
                original = {"Id": "backend", "Image": "image", "State": {"StartedAt": "start", "Running": True}}
                after = {"Id": "backend", "Image": "image", "State": {
                    "StartedAt": "changed" if obstacle == "incarnation" else "start", "Running": False,
                    "ExitCode": 1 if obstacle == "exit" else 0, "OOMKilled": obstacle == "oom"}}
                ready = {"schema": "fullmag.docker-process-tree.v1", "state": "ready", "service_owner": owner}
                drained = {"schema": ready["schema"], "state": "failed" if obstacle == "drain" else "drained",
                    "service_owner": {**owner, "owner_token": "foreign"} if obstacle == "owner" else owner,
                    "terminal_service_owner": owner}
                terminal = {"response": {"code": recovery.CODE if obstacle == "wrong-case" else recovery.MATERIALIZATION_CODE}}
                records = {"active": b"pinned"}
                def read(control, path, **kwargs):
                    if kwargs.get("optional"):
                        return b"prior" if obstacle == "prior" else None
                    return b"changed" if obstacle == "bytes" else records[path]
                def docker(*args, **kwargs):
                    events.append((args[0],))
                    if args[0] == "exec": return SimpleNamespace(stdout=json.dumps(ready).encode())
                    if args[0] == "inspect": return SimpleNamespace(stdout=json.dumps([after]).encode())
                    if args[0] == "stop":
                        self.assertEqual(events[-2][0], "write")
                        self.assertTrue(events[-2][1].endswith("materialization-stop-request.json"))
                        return SimpleNamespace(stdout=b"")
                    self.fail("unexpected Docker command")
                with patch.object(recovery.reconcile, "_control_bytes", side_effect=read), \
                        patch.object(recovery, "docker_capture", side_effect=docker), \
                        patch("docker_volume_stop_unadmitted._read_terminal_process_receipt",
                              return_value=(json.dumps(drained).encode(), drained)):
                    if obstacle is None:
                        result = recovery.stop_rejected_backend(Control(), original, records, "attempt", terminal)
                        self.assertEqual(result["state"], "stopped-confirmed")
                        self.assertTrue(events[-1][1].endswith("materialization-stop-drained.json"))
                        self.assertIn("attempt/materialization-stop-request.json", records)
                        self.assertIn("attempt/materialization-stop-drained.json", records)
                    else:
                        with self.assertRaises(BuildControlError):
                            recovery.stop_rejected_backend(Control(), original, records, "attempt", terminal)
                        self.assertFalse(any(event[0] == "write" and event[1].endswith("-drained.json") for event in events))
                        if obstacle in ("prior", "bytes", "wrong-case"):
                            self.assertFalse(any(event[0] == "stop" for event in events))
                self.assertFalse(any(event[0] == "write" and event[1].endswith("/terminal.json") for event in events))

    def test_refuses_restarted_backend_or_helper(self):
        observed = {"Id": "a", "State": {"Running": True, "StartedAt": "2026-01-01T00:00:00Z"}}
        recovery.validate_incarnation(observed, 1800000000, observed)
        for changed, cutoff in ((observed, 1), ({**observed, "Id": "b"}, 1800000000),
                ({"Id": "a", "State": {"Running": False, "StartedAt": "2026-01-01T00:00:00Z"}}, 1800000000)):
            with self.assertRaises(BuildControlError):
                recovery.validate_incarnation(changed, cutoff, observed)

    def test_docker_nanosecond_timestamp_preserves_exact_incarnation(self):
        started = "2026-10-21T20:19:03.571379583Z"
        observed = {"Id": "a", "State": {"Running": True, "StartedAt": started}}
        recovery.validate_incarnation(observed, 1800000000, observed)
        changed = {"Id": "a", "State": {"Running": True,
            "StartedAt": "2026-10-21T20:19:03.571379584Z"}}
        with self.assertRaisesRegex(BuildControlError, "incarnation changed"):
            recovery.validate_incarnation(changed, 1800000000, observed)
        for malformed in (started[:-1], started.replace("Z", "+01:00"), started.replace("583Z", "5830Z")):
            with self.subTest(malformed=malformed), self.assertRaises(BuildControlError):
                recovery.validate_incarnation({"Id": "a", "State": {"Running": True,
                    "StartedAt": malformed}}, 1800000000)

    def test_publication_preserves_evidence_and_fails_closed_on_changed_bytes(self):
        for changed in (None, "active", "receipt.json", "marker.json", "terminal", "unlocked"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                root = base / "activation/attempts" / ("a" * 32)
                root.mkdir(parents=True)
                records = {"active": b"a" * 32 + b"\n", "activation/attempts/" + "a" * 32 + "/receipt.json": b"original receipt",
                           "marker.json": b"original started marker"}
                for relative, raw in records.items():
                    (base / relative).write_bytes(raw)
                lock = (base / "operation.lock").open("w")
                if changed != "unlocked":
                    fcntl.flock(lock, fcntl.LOCK_EX)
                terminal = "activation/attempts/" + "a" * 32 + "/terminal.json"
                proof = "activation/attempts/" + "a" * 32 + "/output-rejection-proof.json"
                script = recovery.publish_script(BuildControl, records, terminal, proof, "a" * 32)
                script = script.replace("/control", str(base))
                if changed in ("active", "marker.json"):
                    (base / changed).write_bytes(b"changed")
                if changed == "receipt.json":
                    (root / changed).write_bytes(b"changed")
                if changed == "terminal":
                    (base / terminal).write_bytes(b"prior terminal")
                result = subprocess.run(["bash", "-euo", "pipefail", "-c", script], input=b"proof", capture_output=True)
                if changed is None:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((base / terminal).read_bytes(), b"proof")
                    self.assertEqual((base / proof).read_bytes(), b"proof")
                    self.assertEqual((base / proof).stat().st_nlink, 1)
                    self.assertEqual((base / terminal).stat().st_nlink, 1)
                    for path, raw in records.items():
                        self.assertEqual((base / path).read_bytes(), raw)
                    self.assertLess(script.index("sync " + str(base / proof)), script.index('mv -T'))
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((base / proof).exists())
                lock.close()

    def test_probe_refuses_session_work_reservations_or_incarnation_change(self):
        for obstacle in (None, "session", "task", "run", "journal", "reservation", "incarnation", "locked", "transient"):
            with self.subTest(obstacle=obstacle), tempfile.TemporaryDirectory() as directory:
                store, ledger = Path(directory) / "store", Path(directory) / "ledger"
                for root in (store, ledger):
                    root.mkdir(); (root / "WRITER.lock").touch()
                (ledger / "HOST_RESOURCE_LEDGER.json").write_text(json.dumps({"reservations": [1] if obstacle == "reservation" else []}))
                if obstacle in ("run", "journal"):
                    target = store / ("runs" if obstacle == "run" else "live_command_journals")
                    target.mkdir(); (target / "entry").touch()
                responses = {"health": {"status": "ok", "active_session": obstacle == "session"},
                    "compute/queue": {"schema_version": "compute_queue.v1", "items": [1] if obstacle == "task" else []},
                    "runtime-service": {"configured": True, "state": "ready", "reason": {"code": "service_ready"}}}
                calls = []
                class Response:
                    status = 200
                    def __init__(self, value, instance):
                        self.value = value
                        self.headers = {"x-fullmag-api-instance": instance}
                    def __enter__(self): return self
                    def __exit__(self, *args): pass
                    def read(self, maximum): return json.dumps(self.value).encode()
                def get(url, **kwargs):
                    calls.append(url)
                    instance = "11111111-1111-4111-8111-111111111111"
                    if obstacle == "incarnation" and len(calls) > 3:
                        instance = "22222222-2222-4222-8222-222222222222"
                    return Response(copy.deepcopy(responses[url.split("/v2/platform/")[1]]), instance)
                writer = (ledger / "WRITER.lock").open("rb")
                release = None
                if obstacle in ("locked", "transient"):
                    fcntl.flock(writer, fcntl.LOCK_EX)
                if obstacle == "transient":
                    release = threading.Timer(0.15, lambda: fcntl.flock(writer, fcntl.LOCK_UN))
                    release.start()
                with writer, patch("urllib.request.urlopen", side_effect=get):
                    if obstacle in (None, "transient"):
                        self.assertEqual(recovery.probe(str(store), str(ledger))["queue"]["items"], [])
                        self.assertEqual(len(calls), 6)
                    elif obstacle == "locked":
                        with self.assertRaisesRegex(RuntimeError, "Writer lock remains busy: " + str(ledger)):
                            recovery.probe(str(store), str(ledger))
                    else:
                        with self.assertRaises(RuntimeError):
                            recovery.probe(str(store), str(ledger))
                    if release is not None:
                        release.join()


if __name__ == "__main__":
    unittest.main()
