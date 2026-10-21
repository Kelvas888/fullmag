"""Interpreted checks for explicit migration authorization and crash fencing."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import docker_host_readiness_migration as launcher
from docker_build_control import canonical

_SOURCE = Path(__file__).resolve().parents[1] / 'docker/all-in-one/runtime_service.py'
_SPEC = importlib.util.spec_from_file_location('migration_runtime_service', _SOURCE)
runtime = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = runtime
_SPEC.loader.exec_module(runtime)


class MigrationRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'runtime-service'
        self.directory.mkdir()
        (self.root / 'worker-cgroup').mkdir()
        package = self.root / 'package'
        package.mkdir()
        raw = b'{"build":"test"}\n'
        (package / 'backend-build-receipt.json').write_bytes(raw)
        self.paths = runtime.RuntimePaths(package=package, state=self.root)
        stat = Path('/proc/self/stat').read_text()
        self.request = {
            'schema': 'fullmag.worker-cpu-quota-migration-request.v1',
            'request_id': 'b6030878-6047-4615-9d49-ae792061583f',
            'expected_generation': 'a' * 64,
            'compose_project': 'fullmag-worktree-test',
            'container_id': 'b' * 64,
            'image_id': 'sha256:' + 'c' * 64,
            'cgroup_nonce': 'd' * 32,
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'pid': os.getpid(),
            'process_start_token': stat[stat.rfind(')') + 2:].split()[19],
            'package_receipt_sha256': hashlib.sha256(raw).hexdigest(),
        }
        ready = {k: self.request[k] for k in
                 ('compose_project', 'container_id', 'image_id', 'boot_id', 'pid', 'process_start_token')}
        ready.update(schema='fullmag.worker-cgroup-ready.v1', state='ready', nonce=self.request['cgroup_nonce'])
        (self.root / 'worker-cgroup/ready.json').write_text(json.dumps(ready))
        self.native = {'schema_version': 'host_worker_cpu_quota_migration.v1',
                       'previous_generation': 'a' * 64, 'runtime_generation_sha256': 'e' * 64}
        self.command = ['native', '--initialize-docker-host']
        self.addCleanup(patch.stopall)
        patch.object(runtime, 'RUNTIME_CONTROL_ROOT', self.root).start()
        patch.dict(os.environ, FULLMAG_COMPOSE_PROJECT=self.request['compose_project']).start()
        self.run = patch.object(runtime.subprocess, 'run', return_value=subprocess.CompletedProcess(
            self.command, 0, json.dumps(self.native).encode(), b'')).start()

    def authorize(self):
        (self.directory / 'worker-cpu-quota-migration.json').write_text(json.dumps(self.request))

    def invoke(self):
        runtime._run_worker_cpu_quota_migration(self.paths, self.command, {})

    def test_launcher_request_is_consumed_without_translation(self):
        gate = {key: self.request[key] for key in
                ('compose_project', 'container_id', 'boot_id', 'pid', 'process_start_token')}
        gate.update(schema='fullmag.worker-cgroup-request.v1', nonce=self.request['cgroup_nonce'])
        written = []

        def write(relative, value):
            # Same runtime-control subpath mapping as the Compose backend mount.
            target = self.root / Path(relative).relative_to('runtime-control')
            raw = canonical(value) + b'\n'
            target.write_bytes(raw)
            written.append((target, raw))

        control = SimpleNamespace(project=self.request['compose_project'],
                                  read=lambda *args, **kwargs: None, write=write)
        operation = {'receipt': {}}
        package = (self.paths.package / 'backend-build-receipt.json').read_bytes()
        with patch.object(launcher, 'docker_capture', return_value=SimpleNamespace(stdout=package)):
            launcher.publish_request(
                control, operation,
                {key: self.request[key] for key in ('request_id', 'expected_generation')},
                gate, self.request['container_id'], self.request['image_id'],
            )
        self.invoke()
        self.run.assert_called_once()
        self.assertEqual(len(written), 1)
        request_path, raw = written[0]
        self.assertEqual(request_path.read_bytes(), raw)
        claim = json.loads((self.directory / 'worker-cpu-quota-migration.claim.json').read_text())
        result = json.loads((self.directory / 'worker-cpu-quota-migration.result.json').read_text())
        self.assertEqual(claim['request_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['request_sha256'], claim['request_sha256'])
        self.assertEqual(result['native_receipt'], self.native)
        self.assertEqual(operation['receipt']['worker_cpu_quota_migration_request'], json.loads(raw))

    def test_ordinary_start_does_not_invoke_migration(self):
        self.invoke()
        self.run.assert_not_called()

    def test_explicit_success_is_claimed_before_native_and_not_repeated(self):
        self.authorize()
        def execute(*args, **kwargs):
            self.assertTrue((self.directory / 'worker-cpu-quota-migration.claim.json').is_file())
            self.assertEqual(args[0][-2:], ['--migrate-worker-cpu-quota-from', 'a' * 64])
            return subprocess.CompletedProcess(args[0], 0, json.dumps(self.native).encode(), b'')
        self.run.side_effect = execute
        self.invoke()
        result = json.loads((self.directory / 'worker-cpu-quota-migration.result.json').read_text())
        self.assertEqual(result['state'], 'succeeded')
        # A later process incarnation must not repeat the native operation.
        with patch.object(runtime.os, 'getpid', return_value=os.getpid() + 1):
            self.invoke()
        self.run.assert_called_once()

    def test_large_valid_package_receipt_matches_host_limit(self):
        raw = b'{"build":"' + b'x' * (300 * 1024) + b'"}'
        (self.paths.package / 'backend-build-receipt.json').write_bytes(raw)
        self.request['package_receipt_sha256'] = hashlib.sha256(raw).hexdigest()
        self.authorize()
        self.invoke()
        self.run.assert_called_once()

    def test_mismatched_authorization_is_rejected_before_claim(self):
        for field, bad in [('cgroup_nonce', 'f' * 32), ('image_id', 'sha256:' + 'f' * 64),
                           ('pid', os.getpid() + 1), ('package_receipt_sha256', 'f' * 64),
                           ('expected_generation', 'latest'),
                           ('request_id', 'b6030878-6047-1615-9d49-ae792061583f'), ('extra', 'unknown')]:
            with self.subTest(field=field):
                original = dict(self.request)
                self.request[field] = bad
                self.authorize()
                with self.assertRaises(runtime.RuntimeServiceError):
                    self.invoke()
                self.assertFalse((self.directory / 'worker-cpu-quota-migration.claim.json').exists())
                self.request = original
        self.run.assert_not_called()

    def test_timeout_is_retained_and_never_retried_implicitly(self):
        self.authorize()
        self.run.side_effect = subprocess.TimeoutExpired(self.command, 60)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.invoke()
        result = json.loads((self.directory / 'worker-cpu-quota-migration.result.json').read_text())
        self.assertEqual(result['state'], 'unknown')
        with self.assertRaisesRegex(runtime.RuntimeServiceError, 'reconciliation'):
            self.invoke()
        self.run.assert_called_once()

    def test_claim_without_result_blocks_native(self):
        self.authorize()
        (self.directory / 'worker-cpu-quota-migration.claim.json').write_text('{}')
        with self.assertRaisesRegex(runtime.RuntimeServiceError, 'unknown'):
            self.invoke()
        self.run.assert_not_called()

    def test_native_failure_is_preserved_without_fallback(self):
        self.authorize()
        self.run.return_value = subprocess.CompletedProcess(self.command, 2, b'', b'active owner')
        with self.assertRaisesRegex(runtime.RuntimeServiceError, 'active owner'):
            self.invoke()
        result = json.loads((self.directory / 'worker-cpu-quota-migration.result.json').read_text())
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['stderr'], 'active owner')
        with self.assertRaisesRegex(runtime.RuntimeServiceError, 'reconciliation'):
            self.invoke()
        self.run.assert_called_once()

    def test_invalid_success_receipt_is_unknown(self):
        self.authorize()
        self.run.return_value = subprocess.CompletedProcess(self.command, 0, b'{}', b'')
        with self.assertRaisesRegex(runtime.RuntimeServiceError, 'invalid receipt'):
            self.invoke()
        self.assertEqual(json.loads((self.directory / 'worker-cpu-quota-migration.result.json')
                                    .read_text())['state'], 'unknown')


if __name__ == '__main__':
    unittest.main()
