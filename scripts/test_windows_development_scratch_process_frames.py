"""Small parser contract checks; they do not establish native compute proof."""
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from windows import verify_workspace_browser as proof


class ScratchChildFrameChecks(unittest.TestCase):
    def setUp(self):
        self.expected = {"nonce": "12345678-1234-4234-8234-123456789abc"}
        self.pin = "22345678-1234-4234-8234-123456789abc"
        self.identity = {
            "pid": 321,
            "command_id": "grid-command-7",
            "command_kind": "fdm_grid_refresh",
            "api_instance_id": self.pin,
            "session_id": "session-scientific-7",
            "session_epoch": "session-scientific-7@24",
            "request_scope_epoch": self.pin + ":3",
        }
        self.receipt = {
            "processes": [],
            "workspace_browser_api_logs": [{"api_instance_id": self.pin}],
        }
        self.api_records = {99: {"waited": True, "exit_code": 0}}
        self.scratch_records = {}

    def frame(self, state, **changes):
        started = state == "started"
        return {
            "schema": proof.SCRATCH_CHILD_SCHEMA,
            "nonce": self.expected["nonce"],
            "state": state,
            **self.identity,
            "waited": not started,
            "exit_code": None if started else 0,
            "kill_requested": False,
            **changes,
        }

    def record_start(self, **changes):
        self.assertTrue(proof.record_scratch_child_frame(
            self.frame("started", **changes), self.expected, self.scratch_records, self.receipt))

    def test_valid_grid_child_start_and_wait_are_retained_as_scoped_custody(self):
        start = self.frame("started")
        wait = self.frame("waited", exit_code=0)
        self.assertTrue(proof.record_scratch_child_frame(
            start, self.expected, self.scratch_records, self.receipt))
        self.assertTrue(proof.record_scratch_child_frame(
            wait, self.expected, self.scratch_records, self.receipt))

        record = self.scratch_records[self.identity["command_id"]]["record"]
        self.assertEqual(record["api_instance_id"], self.pin)
        self.assertEqual(record["session_id"], self.identity["session_id"])
        self.assertEqual(record["session_epoch"], self.identity["session_epoch"])
        self.assertEqual(record["request_scope_epoch"], self.identity["request_scope_epoch"])
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(self.receipt["workspace_browser_scratch_child_frames"], [start, wait])
        self.assertTrue(proof.terminal_custody(self.api_records, {}, self.scratch_records, self.receipt))

    def test_killed_cleanup_wait_is_terminal_and_retains_kill_request(self):
        self.record_start(command_kind="run")
        waited = self.frame("waited", command_kind="run", exit_code=137, kill_requested=True)
        proof.record_scratch_child_frame(waited, self.expected, self.scratch_records, self.receipt)

        record = self.scratch_records[self.identity["command_id"]]["record"]
        self.assertTrue(record["waited"])
        self.assertEqual(record["exit_code"], 137)
        self.assertTrue(record["kill_requested"])
        self.assertTrue(proof.terminal_custody(self.api_records, {}, self.scratch_records, self.receipt))

    def test_start_without_wait_does_not_claim_terminal_custody(self):
        self.record_start()
        self.assertFalse(proof.terminal_custody(self.api_records, {}, self.scratch_records, self.receipt))

    def test_wait_without_known_start_is_rejected(self):
        with self.assertRaises(proof.storage.StorageError):
            proof.record_scratch_child_frame(
                self.frame("waited"), self.expected, self.scratch_records, self.receipt)
        self.assertFalse(proof.terminal_custody(self.api_records, {}, self.scratch_records, self.receipt))

    def test_changed_scope_between_start_and_wait_is_rejected(self):
        self.record_start()
        changed = self.frame("waited", request_scope_epoch=self.pin + ":4")
        with self.assertRaises(proof.storage.StorageError):
            proof.record_scratch_child_frame(changed, self.expected, self.scratch_records, self.receipt)
        self.assertFalse(proof.terminal_custody(self.api_records, {}, self.scratch_records, self.receipt))

    def test_wrong_nonce_is_rejected(self):
        with self.assertRaises(proof.storage.StorageError):
            proof.record_scratch_child_frame(
                self.frame("started", nonce="32345678-1234-4234-8234-123456789abc"),
                self.expected, self.scratch_records, self.receipt)
        self.assertEqual(self.receipt["processes"], [])

    def test_duplicate_start_and_wait_frames_are_rejected(self):
        start = self.frame("started")
        proof.record_scratch_child_frame(start, self.expected, self.scratch_records, self.receipt)
        with self.assertRaises(proof.storage.StorageError):
            proof.record_scratch_child_frame(start, self.expected, self.scratch_records, self.receipt)

        wait = self.frame("waited")
        proof.record_scratch_child_frame(wait, self.expected, self.scratch_records, self.receipt)
        with self.assertRaises(proof.storage.StorageError):
            proof.record_scratch_child_frame(wait, self.expected, self.scratch_records, self.receipt)

    def test_boolean_values_are_not_accepted_as_integer_custody(self):
        invalid_frames = [
            self.frame("started", pid=True),
            self.frame("started", waited=0),
            self.frame("waited", exit_code=True),
            self.frame("waited", kill_requested=0),
        ]
        for frame in invalid_frames:
            with self.subTest(frame=frame), self.assertRaises(proof.storage.StorageError):
                proof.record_scratch_child_frame(frame, self.expected, {}, {"processes": []})

    def test_known_browser_api_pin_mismatch_is_rejected(self):
        other_pin = "32345678-1234-4234-8234-123456789abc"
        with self.assertRaises(proof.storage.StorageError):
            proof.record_scratch_child_frame(
                self.frame("started", api_instance_id=other_pin, request_scope_epoch=other_pin + ":3"),
                self.expected, self.scratch_records, self.receipt)

    def test_missing_observed_api_pin_is_not_custody_evidence(self):
        self.receipt["workspace_browser_api_logs"] = []
        with self.assertRaises(proof.storage.StorageError):
            proof.record_scratch_child_frame(
                self.frame("started"), self.expected, self.scratch_records, self.receipt)
        self.assertFalse(proof.terminal_custody(self.api_records, {}, self.scratch_records, self.receipt))

    def test_unrelated_frame_schema_is_ignored(self):
        self.assertFalse(proof.record_scratch_child_frame(
            {"schema": "unrelated.v1"}, self.expected, self.scratch_records, self.receipt))
        self.assertEqual(self.receipt["processes"], [])

    def test_resource_epoch_rekey_does_not_change_stable_execution_owner(self):
        before = {"api_instance_id": "api-a", "session_id": "session-a",
                  "backend_session_epoch": 1, "request_scope_epoch": "api-a:1",
                  "session_resource_epoch": "session-a@100"}
        after = {**before, "session_resource_epoch": "session-a@200:tombstone:300"}
        self.assertTrue(proof.same_execution_scope(before, after))
        for field, changed in (("api_instance_id", "api-b"), ("session_id", "session-b"),
                               ("backend_session_epoch", 2), ("request_scope_epoch", "api-a:2")):
            with self.subTest(field=field):
                self.assertFalse(proof.same_execution_scope(before, {**after, field: changed}))

    def test_completed_command_receipt_requires_exact_kind_and_positive_ordered_time(self):
        frame = {"command_id": "solve-a", "kind": "solve", "status": "completed",
                 "completion_status": "completed", "created_at_unix_ms": 100,
                 "completed_at_unix_ms": 200}
        self.assertEqual(proof.completed_command_detail(frame, "solve-a", "solve")["command_id"], "solve-a")
        for override in ({"kind": "run"}, {"command_id": "solve-b"}, {"status": "failed"},
                         {"completion_status": "failed"}, {"created_at_unix_ms": 0},
                         {"completed_at_unix_ms": 99}, {"completed_at_unix_ms": True}):
            with self.subTest(override=override), self.assertRaises(proof.storage.StorageError):
                proof.completed_command_detail({**frame, **override}, "solve-a", "solve")

    def test_graceful_close_readiness_is_not_terminal_execution_proof(self):
        bridge = proof.ProofBridge({}, 1, None, None)
        bridge._read_execution_evidence = lambda **kwargs: {"scope": "fixture"}
        intermediate = bridge.execution(require_terminal=False)
        self.assertFalse(intermediate["verified"])
        self.assertTrue(intermediate["ready_to_close"])
        terminal = bridge.execution()
        self.assertTrue(terminal["verified"])
        self.assertFalse(terminal["ready_to_close"])


class MaterialPlanCustodyChecks(unittest.TestCase):
    def test_missing_log_still_reaps_owned_planner(self):
        class Child:
            pid = 151
            returncode = None
            killed = False

            def poll(self):
                return self.returncode

            def kill(self):
                self.killed = True
                self.returncode = -1

            def wait(self, timeout=None):
                return self.returncode

        child = Child()
        original_stat = Path.stat

        def missing_log(path, *args, **kwargs):
            if path.name == "example.stdout":
                raise OSError("probe log unavailable")
            return original_stat(path, *args, **kwargs)

        receipt = {"processes": []}
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "fullmag.exe").write_bytes(b"mocked custody fixture")
            with patch.object(proof.subprocess, "Popen", return_value=child), \
                    patch.object(Path, "stat", missing_log):
                with self.assertRaisesRegex(OSError, "probe log unavailable"):
                    proof.check_material_anisotropy_plans(Path(root), Path(root), {}, receipt)
        self.assertTrue(child.killed)
        self.assertTrue(receipt["processes"][0]["waited"])
        self.assertEqual(receipt["processes"][0]["exit_code"], -1)

    def test_unconfirmed_kill_wait_is_unknown_not_terminal(self):
        class Child:
            pid = 152
            returncode = None
            killed = False

            def poll(self):
                return None

            def kill(self):
                self.killed = True

            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired("owned planner", timeout)

        child = Child()
        receipt = {"processes": []}
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "fullmag.exe").write_bytes(b"mocked custody fixture")
            with patch.object(proof.subprocess, "Popen", return_value=child), \
                    patch.object(proof.time, "monotonic", side_effect=[0, 31]):
                with self.assertRaisesRegex(proof.storage.StorageError, "unknown cleanup outcome"):
                    proof.check_material_anisotropy_plans(Path(root), Path(root), {}, receipt)
        record = receipt["processes"][0]
        self.assertTrue(child.killed)
        self.assertFalse(record["waited"])
        self.assertEqual(record["outcome"], "unknown")
        self.assertNotIn("exit_code", record)


if __name__ == "__main__":
    unittest.main()
