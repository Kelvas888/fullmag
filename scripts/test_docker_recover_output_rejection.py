import copy
import fcntl
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

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
        for obstacle in (None, "session", "task", "run", "journal", "reservation", "incarnation"):
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
                with patch("urllib.request.urlopen", side_effect=get):
                    if obstacle is None:
                        self.assertEqual(recovery.probe(str(store), str(ledger))["queue"]["items"], [])
                        self.assertEqual(len(calls), 6)
                    else:
                        with self.assertRaises(RuntimeError):
                            recovery.probe(str(store), str(ledger))


if __name__ == "__main__":
    unittest.main()
