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
    def test_closed_admission_needs_a_failed_receipt(self):
        logs = '[fullmag-backend] Startup or runtime failed; admission closed: boom. Process receipt: x\n'
        failed = {'state': 'failed_outcome_retained', 'error': 'scheduler exited'}
        self.assertEqual(docker_volume_dev._readiness_failure(failed, logs),
                         'Runtime admission failed; services retained: scheduler exited')
        self.assertIsNone(docker_volume_dev._readiness_failure({'state': 'running'}, logs))

    def test_startup_diagnostic_fails_fast_with_a_stale_receipt(self):
        logs = ('backend-dev: phase=api state=exec mode=backend\n'
                '[fullmag-backend] Runtime startup failed; starting diagnostic API only: '
                'runtime configuration rotation requires an authenticated drained process receipt. '
                'Diagnostic: /opt/fullmag/runtime-control/runtime-service/api-failure-1.json\n')
        failure = docker_volume_dev._readiness_failure({'state': 'running'}, logs)
        self.assertTrue(failure.startswith('Runtime startup failed; diagnostic API retained: '
                                           'runtime configuration rotation requires'))

    def test_starting_backend_is_not_a_failure(self):
        logs = 'backend-dev: phase=api state=exec mode=backend\n[fullmag-backend] Ready: API and runtime service\n'
        self.assertIsNone(docker_volume_dev._readiness_failure({'state': 'not-published'}, logs))

if __name__ == '__main__':
    unittest.main()
