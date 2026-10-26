"""Exercise the guest receipt probe against the configured technical root."""
from pathlib import Path
import contextlib
import io
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import docker_volume_dev

class ReadinessReceiptProbeTests(unittest.TestCase):
    def probe(self, raw=None):
        expected = Path('/technical-volume/runtime-service/process-tree.json')
        observed = []
        def read(path, label):
            observed.append(path)
            if raw is None:
                raise FileNotFoundError(path)
            return raw
        paths = object()
        runtime = SimpleNamespace(canonical_paths=lambda: paths,
            process_receipt_path=lambda value: expected if value is paths else None,
            _bounded_regular=read)
        output = io.StringIO()
        with patch.dict(sys.modules, runtime_service=runtime), contextlib.redirect_stdout(output), patch.object(sys, 'path', list(sys.path)):
            exec(docker_volume_dev._PROCESS_RECEIPT_PROBE, {})
        self.assertEqual(observed, [expected])
        return json.loads(output.getvalue())

    def test_failure_is_read_from_configured_root(self):
        receipt = {'schema': 'fullmag.docker-process-tree.v1',
                   'state': 'failed_outcome_retained', 'error': 'native startup failed'}
        self.assertEqual(self.probe(json.dumps(receipt).encode()), receipt)

    def test_missing_receipt_is_not_published(self):
        self.assertEqual(self.probe(), {'state': 'not-published'})

class ReadinessFailureTests(unittest.TestCase):
    def test_startup_diagnostic_failure_overrides_historical_receipt(self):
        logs = "[fullmag-backend] Runtime startup failed; starting diagnostic API only: container recovery archived evidence differs from live store: runtime-services/LAUNCH.json\n"
        for state in ("shutdown_unknown", "not-published", "ready"):
            with self.subTest(state=state):
                error = docker_volume_dev._readiness_failure({"state": state}, logs)
                self.assertIn("diagnostic API only", error)
                self.assertIn("runtime-services/LAUNCH.json", error)

    def test_supervision_failure_still_reports_native_cause(self):
        error = docker_volume_dev._readiness_failure(
            {"state": "failed_outcome_retained", "error": "scheduler compute exited"},
            "[fullmag-backend] Startup or runtime failed; admission closed: scheduler compute exited")
        self.assertIn("scheduler compute exited", error)

    def test_normal_startup_or_quoted_user_text_is_not_a_failure(self):
        for logs in ("backend-dev: phase=make state=start", "[fullmag-backend] Ready: API and runtime service",
                     "user output: [fullmag-backend] Runtime startup failed; starting diagnostic API only: text"):
            with self.subTest(logs=logs):
                self.assertIsNone(docker_volume_dev._readiness_failure({"state": "not-published"}, logs))

    def test_unconfirmed_old_failed_receipt_is_not_a_new_failure(self):
        self.assertIsNone(docker_volume_dev._readiness_failure(
            {"state": "failed_outcome_retained", "error": "previous boot"}, "backend-dev: phase=start state=handoff"))

    def test_error_text_is_bounded(self):
        error = docker_volume_dev._readiness_failure({},
            "[fullmag-backend] Runtime startup failed; starting diagnostic API only: " + "x" * 10000)
        self.assertLess(len(error), 4200)

if __name__ == '__main__':
    unittest.main()
