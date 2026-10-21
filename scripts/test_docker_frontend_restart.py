"""Exercise stopped-incarnation frontend recovery without Docker mutations."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import docker_frontend_restart as recovery
from docker_build_control import BuildControlError


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux runtime flock contract")
class FrontendRestartTests(unittest.TestCase):
    def setUp(self):
        self.contract = ("/state/development/frontend-dev-receipt.json", "")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "cache").mkdir()
        self.lock = self.root / "cache/.fullmag-frontend-runtime.lock"
        self.lock.touch()
        self.path = self.root / "frontend-dev-receipt.json"
        self.receipt = {"schema": "fullmag.docker-frontend-development-receipt.v1", "state": "unknown",
                        "source_root": "/home/user/fullmag", "host_port": 3197, "owner_token": "old-owner",
                        "workspace_root": "/state/development/workspace", "frontend_root": "/state/development/cache"}
        self.path.write_text(json.dumps(self.receipt))
        self.proof = {"schema": "fullmag.stopped-frontend-incarnation.v1", "container_id": "a" * 64,
                      "image_id": "sha256:" + "b" * 64, "running": False, "pid": 0, "pid_mode": "",
                      "started_at": "2026-10-19T13:00:00Z", "finished_at": "2026-10-20T06:00:00Z"}
        self.request = {"mode": "read", "proof": self.proof, "source_root": self.receipt["source_root"], "port": 3197}

    def recover(self, **changes):
        original = recovery.guest(self.request, self.root, self.contract)
        request = {**self.request, "mode": "recover", "expected_sha256": original["sha256"], **changes}
        return recovery.guest(request, self.root, self.contract)

    def test_real_guest_cas_keeps_original_and_cache_and_marks_only_receipt_stopped(self):
        original = self.path.read_bytes()
        cache = self.root / "cache/node_modules-proof"
        cache.write_bytes(b"preserved cache")
        result = self.recover()
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(result["original_sha256"], hashlib.sha256(original).hexdigest())
        changed = json.loads(self.path.read_bytes())
        self.assertEqual(changed["owner_token"], "old-owner")
        self.assertEqual(changed["docker_restart_recovery"]["incarnation"], self.proof)
        self.assertEqual(cache.read_bytes(), b"preserved cache")

    def test_ephemeral_image_contract_preserves_diagnostic_receipt_without_lock(self):
        original = self.path.read_bytes()
        self.lock.unlink()
        contract = ("/run/fullmag/frontend-owner/receipt.json", "/state/development/frontend-dev-receipt.json")
        self.assertEqual(recovery.guest(self.request, self.root, contract), {"state": "no-recovery-required"})
        self.assertEqual(self.path.read_bytes(), original)
        with self.assertRaisesRegex(RuntimeError, "contract is unsupported"):
            recovery.guest(self.request, self.root, ("/unexpected/receipt", ""))
        self.assertEqual(self.path.read_bytes(), original)

    def test_guest_reads_receipt_contract_from_fixed_image_module(self):
        image_module = self.root / "image_frontend.py"
        image_module.write_text("from pathlib import Path\nRECEIPT_PATH=Path('/run/fullmag/frontend-owner/receipt.json')\nDIAGNOSTIC_RECEIPT_PATH=Path('/state/development/frontend-dev-receipt.json')\n")
        real_spec = importlib.util.spec_from_file_location
        with patch.object(importlib.util, "spec_from_file_location", side_effect=lambda name, path: real_spec(name, image_module)) as load:
            result = recovery.guest(self.request, self.root)
        self.assertEqual(load.call_args.args[1], "/opt/fullmag/frontend_dev.py")
        self.assertEqual(result, {"state": "no-recovery-required"})

    def test_absent_receipt_is_not_started_but_missing_lock_is_rejected(self):
        self.path.unlink()
        self.assertEqual(recovery.guest(self.request, self.root, self.contract), {"state": "not-started"})
        self.assertFalse(self.path.exists())
        self.lock.unlink()
        with self.assertRaises(FileNotFoundError):
            recovery.guest(self.request, self.root, self.contract)

    def test_active_flock_rejects_without_changes(self):
        import fcntl
        before = self.path.read_bytes()
        with self.lock.open("r+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.recover()
        self.assertEqual(self.path.read_bytes(), before)

    def test_cas_and_running_or_foreign_namespace_proofs_fail_closed(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "CAS"):
            self.recover(expected_sha256="0" * 64)
        for changes in ({"running": True}, {"pid": 7}, {"pid_mode": "host"}, {"finished_at": ""}):
            with self.subTest(changes=changes), self.assertRaisesRegex(RuntimeError, "stopped private"):
                self.recover(proof={**self.proof, **changes})
        self.assertEqual(self.path.read_bytes(), before)

    def test_foreign_source_port_and_image_receipts_are_preserved(self):
        for field, value in (("source_root", "/other/source"), ("host_port", 3000), ("image_id", "sha256:" + "c" * 64)):
            self.path.write_text(json.dumps({**self.receipt, field: value}))
            before = self.path.read_bytes()
            with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, "scope differs"):
                self.recover()
            self.assertEqual(self.path.read_bytes(), before)

    def test_symlink_receipt_is_rejected(self):
        target = self.root / "original"
        self.path.rename(target)
        self.path.symlink_to(target)
        with self.assertRaises(OSError):
            self.recover()
        self.assertEqual(json.loads(target.read_text()), self.receipt)

    def test_managed_host_archives_before_mutation_and_refuses_active_consumers(self):
        actual = {"Id": "a" * 64, "Image": self.proof["image_id"],
                  "State": {"Status": "exited", "Running": False, "Restarting": False, "Pid": 0,
                            "StartedAt": self.proof["started_at"], "FinishedAt": self.proof["finished_at"]},
                  "HostConfig": {"PidMode": ""}, "Config": {"Labels": {
                      "com.docker.compose.project": "fullmag-master", "com.docker.compose.service": "frontend",
                      "org.fullmag.source.worktree-id": "main"}},
                  "Mounts": [{"Destination": "/state/development", "Type": "volume", "RW": True, "Name": "state"}]}
        document = {"services": {"frontend": {"image": self.proof["image_id"], "volumes": [
            {"target": "/state/development", "type": "volume", "source": "state"}]}}, "volumes": {"state": {"name": "state"}}}
        archives = {}
        control = SimpleNamespace(project="fullmag-master", identity={"worktree_id": "main"}, image="bootstrap",
            helper_args=lambda command: ["docker", "run", "--mount", "control-mount", "--entrypoint", "/bin/bash", "bootstrap", command],
            write_bytes=lambda key, value: archives.setdefault(key, value),
            write=lambda key, value: archives.setdefault(key, value))
        operation = {"root": "resume/attempts/" + "a" * 32}
        original = self.path.read_bytes()
        def capture(*args):
            return SimpleNamespace(stdout=json.dumps([actual]).encode() if args[0] == "inspect" else b"")
        def helper(arguments, *, data, timeout):
            request = json.loads(data)
            self.assertNotIn("control-mount", arguments)
            self.assertIn(self.proof["image_id"], arguments)
            if request["mode"] == "recover":
                self.assertEqual(archives[operation["root"] + "/frontend-restart/original-receipt.json"], original)
            return SimpleNamespace(returncode=0, stdout=json.dumps(recovery.guest(request, self.root, self.contract)).encode())
        with patch.object(recovery, "docker_capture", side_effect=capture), patch.object(recovery, "bounded_capture", side_effect=helper):
            result = recovery.recover_stopped_frontend(control, operation, actual, document, self.receipt["source_root"], 3197)
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(archives[operation["root"] + "/frontend-restart/stopped-incarnation.json"]["original_sha256"], hashlib.sha256(original).hexdigest())
        self.path.write_bytes(original)
        archives.clear()
        with (patch.object(recovery, "docker_capture", side_effect=lambda *args: SimpleNamespace(
                stdout=json.dumps([actual]).encode() if args[0] == "inspect" else b"foreign-consumer\n")),
              patch.object(recovery, "bounded_capture") as invocation):
            with self.assertRaisesRegex(BuildControlError, "active consumer"):
                recovery.recover_stopped_frontend(control, operation, actual, document, self.receipt["source_root"], 3197)
            invocation.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(archives, {})
        self.path.unlink()
        with patch.object(recovery, "docker_capture", side_effect=capture), patch.object(recovery, "bounded_capture", side_effect=helper):
            self.assertEqual(recovery.recover_stopped_frontend(control, operation, actual, document,
                             self.receipt["source_root"], 3197), {"state": "not-started"})
        self.assertEqual(archives, {})
        self.assertFalse(self.path.exists())

    def test_host_proof_rejects_started_again_or_namespace_drift(self):
        actual = {"Id": "a" * 64, "Image": self.proof["image_id"],
                  "State": {"Status": "exited", "Running": False, "Restarting": False, "Pid": 0,
                            "StartedAt": self.proof["started_at"], "FinishedAt": self.proof["finished_at"]},
                  "HostConfig": {"PidMode": ""}, "Config": {"Labels": {
                      "com.docker.compose.project": "fullmag-master", "com.docker.compose.service": "frontend",
                      "org.fullmag.source.worktree-id": "main"}},
                  "Mounts": [{"Destination": "/state/development", "Type": "volume", "RW": True, "Name": "state"}]}
        control = SimpleNamespace(project="fullmag-master", identity={"worktree_id": "main"})
        document = {"services": {"frontend": {"image": self.proof["image_id"], "volumes": [
            {"target": "/state/development", "type": "volume", "source": "state"}]}}, "volumes": {"state": {"name": "state"}}}
        self.assertEqual(recovery._proof(actual, control, document)["volume"], "state")
        for field, value in (("Running", True), ("Restarting", True), ("Pid", 9), ("FinishedAt", "0001-01-01T00:00:00Z")):
            with self.subTest(field=field), self.assertRaises(BuildControlError):
                recovery._proof({**actual, "State": {**actual["State"], field: value}}, control, document)
        with self.assertRaises(BuildControlError):
            recovery._proof({**actual, "HostConfig": {"PidMode": "host"}}, control, document)


if __name__ == "__main__":
    unittest.main()
