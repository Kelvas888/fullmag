"""Run the real readmission lock protocol on private, disposable evidence."""
import base64
import copy
import fcntl
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest

import docker_linux_native_readmission as recovery


class ReadmissionRequestTests(unittest.TestCase):
    def request(self):
        return {"schema": recovery.SCHEMA, "source_revision": "a" * 40,
            "controller_inputs": {n: "b" * 64 for n in recovery.CONTROLLERS},
            "boot_id": "12345678-1234-1234-1234-123456789abc", "engine_id": "retained-engine",
            "compose_path": "development/attempts/" + "c" * 32 + "/compose.json",
            "compose_sha256": "d" * 64,
            "failed_resume_path": "resume/attempts/" + "e" * 32 + "/terminal.json",
            "failed_resume_sha256": "f" * 64,
            "containers": {s: {"id": n * 64, "fingerprint": "a" * 64,
                "state": {"Status": "exited", "Running": False, "Pid": 0, "OOMKilled": False}}
                for s, n in (("backend", "1"), ("frontend", "2"))},
            "native_pins": {n: "a" * 64 for n in recovery.NATIVE_PINS},
            "storage_pins": {"engine_id": "retained-engine"}}

    def test_closed_request_accepts_only_exact_stopped_services(self):
        r = self.request(); recovery.validate_request(r)
        for key, value in (("Running", True), ("Pid", 42), ("Status", "running"), ("OOMKilled", True)):
            with self.subTest(key=key):
                bad = copy.deepcopy(r); bad["containers"]["backend"]["state"][key] = value
                with self.assertRaises(recovery.BuildControlError): recovery.validate_request(bad)
        for field in ("controller_inputs", "native_pins"):
            bad = copy.deepcopy(r); bad[field].pop(next(iter(bad[field])))
            with self.assertRaises(recovery.BuildControlError): recovery.validate_request(bad)
        bad = copy.deepcopy(r); bad["permit_running"] = True
        with self.assertRaises(recovery.BuildControlError): recovery.validate_request(bad)

    def test_archive_roundtrips_raw_bytes_and_rejects_invalid_encoding(self):
        p = {"original": {"first": b'\x00\xff\n\r'}, "candidate_raw": b'{"x":1}\n',
             "pins": {"unchanged": True}, "candidate_sha256": "a" * 64}
        encoded = recovery.archive_preparation(p)
        self.assertEqual(recovery.restore_preparation(json.loads(json.dumps(encoded))), p)
        encoded["candidate_raw"] = "!not-base64"
        with self.assertRaises(ValueError): recovery.restore_preparation(encoded)


@unittest.skipUnless(os.name == "posix", "Guard requires shared POSIX flock inodes")
class ReadmissionGuardTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.control = self.root / "control"
        self.ledger = self.root / "host-ledger/ledger"
        self.store = self.root / "retained"
        for d in (self.control / "runtime-control/runtime-services", self.ledger, self.store):
            d.mkdir(parents=True)
        self.locks = [self.control / "operation.lock", *[
            self.control / "runtime-control/runtime-services" / name
            for name in ("STARTUP-GATE.lock", "LAUNCH.lock", "OWNER.lock")],
            self.ledger / "WRITER.lock", self.store / "WRITER.lock"]
        for p in self.locks: p.write_bytes(b"")
        self.ledger_path = self.ledger / "HOST_RESOURCE_LEDGER.json"
        self.ledger_path.write_text(json.dumps({"reservations": [{"state": "released"}]}))
        self.evidence = self.control / "runtime-control/runtime-services/OWNER.json"
        self.evidence.write_text('{"state":"ready","preserve":true}')
        self.payload = {"control_pins": {self.evidence.relative_to(self.control).as_posix():
                                        recovery.digest(self.evidence.read_bytes())}}
        (self.store / "result.bin").write_bytes(b"scientific result")
        self.code = recovery.GUARD.replace("/control", str(self.control)).replace(
            "/host-ledger", str(self.root / "host-ledger")).replace("/retained", str(self.store))

    def launch(self):
        p = subprocess.Popen([sys.executable, "-I", "-B", "-c", self.code],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.close, p)
        p.stdin.write(json.dumps(self.payload).encode() + b"\n"); p.stdin.flush()
        return p

    @staticmethod
    def close(p):
        if p.stdin and not p.stdin.closed: p.stdin.close()
        p.wait(timeout=5)
        p.stdout.close(); p.stderr.close()

    def line(self, p):
        self.assertTrue(select.select([p.stdout], [], [], 5)[0], "guard handshake timed out")
        raw = p.stdout.readline()
        if not raw: self.fail(p.stderr.read().decode())
        return json.loads(raw)

    def test_protocol_holds_all_locks_and_preserves_all_science(self):
        before = (self.store / "result.bin").read_bytes()
        p = self.launch(); locked = self.line(p)
        self.assertEqual(locked["state"], "locked")
        for path in self.locks:
            with path.open("rb") as f:
                with self.assertRaises(BlockingIOError): fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        p.stdin.write(b"CHECK\n"); p.stdin.flush()
        self.assertEqual(self.line(p), {"state": "preserved", "snapshot": locked["snapshot"]})
        p.stdin.write(b"RELEASE\n"); p.stdin.flush(); p.stdin.close()
        self.assertEqual(p.wait(timeout=5), 0)
        self.assertEqual((self.store / "result.bin").read_bytes(), before)
        self.assertEqual(self.evidence.read_text(), '{"state":"ready","preserve":true}')

    def test_eof_before_publication_releases_locks_without_writes(self):
        p = self.launch(); self.line(p); p.stdin.close()
        self.assertNotEqual(p.wait(timeout=5), 0)
        for path in self.locks:
            with path.open("rb") as f: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertEqual((self.store / "result.bin").read_bytes(), b"scientific result")

    def test_busy_lock_active_operation_and_unreleased_ledger_refuse(self):
        for path in self.locks:
            with self.subTest(lock=path.name), path.open("rb") as f:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                p = self.launch(); p.stdin.close(); self.assertNotEqual(p.wait(timeout=5), 0)
        (self.control / "active").write_text("other-operation")
        p = self.launch(); p.stdin.close(); self.assertNotEqual(p.wait(timeout=5), 0)
        (self.control / "active").unlink()
        self.ledger_path.write_text('{"reservations":[{"state":"active"}]}')
        p = self.launch(); p.stdin.close(); self.assertNotEqual(p.wait(timeout=5), 0)

    def test_science_or_native_pin_drift_fails_recheck(self):
        for path in (self.store / "result.bin", self.evidence, self.ledger_path):
            with self.subTest(path=path.name):
                original = path.read_bytes(); p = self.launch(); self.line(p)
                path.write_bytes(original + b"drift")
                p.stdin.write(b"CHECK\n"); p.stdin.flush(); p.stdin.close()
                self.assertNotEqual(p.wait(timeout=5), 0)
                path.write_bytes(original)

    @unittest.skipIf(os.geteuid() == 0, "Permission regression requires the normal non-root helper")
    def test_unreadable_store_directory_refuses_incomplete_snapshot(self):
        hidden = self.store / "unreadable"
        hidden.mkdir(); (hidden / "retained.bin").write_bytes(b"must not be omitted")
        hidden.chmod(0)
        try:
            p = self.launch(); p.stdin.close()
            self.assertNotEqual(p.wait(timeout=5), 0)
            self.assertIn(b"PermissionError", p.stderr.read())
        finally:
            hidden.chmod(0o700)

    def test_more_than_64_files_supported_and_linked_science_refused(self):
        for i in range(70): (self.store / (str(i) + ".bin")).write_bytes(b"history")
        p = self.launch(); self.assertGreater(self.line(p)["snapshot"]["file_count"], 64)
        p.stdin.close(); p.wait(timeout=5)
        (self.store / "linked").symlink_to(self.evidence)
        p = self.launch(); p.stdin.close(); self.assertNotEqual(p.wait(timeout=5), 0)


if __name__ == "__main__": unittest.main()
