"""Interpreted checks for native Linux Docker storage admission."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

GUEST = Path(__file__).resolve().parents[1] / 'docker/all-in-one'
sys.path.insert(0, str(GUEST))


def load(name):
    spec = importlib.util.spec_from_file_location(name, GUEST / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(os.name == 'nt', 'Linux guest contract')
class LinuxGuestTest(unittest.TestCase):
    def setUp(self):
        self.entry = load('entrypoint')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.host_path = self.root / 'host.json'
        self.image = 'sha256:' + 'a' * 64
        self.payload = ('b' * 32 + ':' + self.image).encode()
        self.host = dict(schema='fullmag.linux-native-host.v1', storage_profile='linux-native-v1',
                         image_id=self.image, owner_token='b' * 32, restart_verified=False,
                         restart_expected_sha256=hashlib.sha256(self.payload).hexdigest())
        self.write_host()
        (self.state / '.linux-native-sentinel').write_bytes(self.payload)
        self.environment = patch.dict(os.environ, FULLMAG_RUNTIME_IMAGE_ID=self.image,
                                      FULLMAG_SESSION_STORAGE_PROFILE='linux-native-v1')
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def write_host(self):
        self.host_path.write_text(json.dumps(self.host))

    def probe(self, require_restart=False):
        return self.entry.linux_storage_probe(require_restart, self.state, self.host_path)

    def test_real_storage_operations_and_restart_readback(self):
        first = self.probe()
        self.assertFalse(first['checks']['restart_readback'])
        self.assertTrue(all(value for key, value in first['checks'].items() if key != 'restart_readback'))
        self.assertTrue(all(self.probe()['checks'].values()))
        with self.assertRaisesRegex(RuntimeError, 'restart'):
            self.probe(True)
        self.host['restart_verified'] = True
        self.write_host()
        self.assertTrue(all(self.probe(True)['checks'].values()))
        self.assertEqual(json.loads((self.state / '.linux-native-probe.json').read_text())['checks'],
                         self.probe(True)['checks'])

    def test_host_readback_files_are_readable_under_restrictive_umask(self):
        previous = os.umask(0o077)
        try:
            self.probe()
        finally:
            os.umask(previous)
        for name in ('.linux-native-restart', '.linux-native-probe.json'):
            self.assertEqual((self.state / name).stat().st_mode & 0o777, 0o644)

    def test_missing_or_corrupt_restart_is_rejected(self):
        self.host['restart_verified'] = True
        self.write_host()
        with self.assertRaisesRegex(RuntimeError, 'missing'):
            self.probe(True)
        self.probe()
        (self.state / '.linux-native-restart').write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, 'Restart'):
            self.probe(True)

    def test_mismatched_certificate_and_sentinel_fail_before_publication(self):
        for field, value in [('image_id', 'sha256:' + 'c' * 64),
                             ('owner_token', '../owner'), ('restart_expected_sha256', '0' * 64),
                             ('storage_profile', 'windows-folder-v1')]:
            with self.subTest(field=field):
                previous = self.host[field]
                self.host[field] = value
                self.write_host()
                with self.assertRaises(RuntimeError):
                    self.probe()
                self.assertFalse((self.state / '.linux-native-restart').exists())
                self.host[field] = previous
        self.write_host()
        (self.state / '.linux-native-sentinel').write_bytes(b'corrupt')
        with self.assertRaises(RuntimeError):
            self.probe()

    def test_nofollow_and_bounded_certificate(self):
        real = self.root / 'real.json'
        self.host_path.rename(real)
        self.host_path.symlink_to(real)
        with self.assertRaises(OSError):
            self.probe()
        self.host_path.unlink()
        self.host_path.write_bytes(b' ' * 65537)
        with self.assertRaisesRegex(RuntimeError, 'oversized'):
            self.probe()
        self.write_host()
        sentinel = self.state / '.linux-native-sentinel'
        sentinel.unlink()
        sentinel.symlink_to(real)
        with self.assertRaises(OSError):
            self.probe()

    def test_linux_rejects_non_native_fs_before_cuda_or_writes(self):
        for filesystem in ('1021997', '794c7630', '1021994', 'deadbeef'):
            with self.subTest(filesystem=filesystem), patch.object(self.entry.subprocess, 'check_output', return_value=filesystem), patch.object(self.entry.ctypes, 'CDLL') as cuda:
                with self.assertRaisesRegex(RuntimeError, 'native Linux'):
                    self.entry.preflight()
                cuda.assert_not_called()

    def test_restart_and_parent_symlinks_are_rejected(self):
        self.probe()
        restart = self.state / '.linux-native-restart'
        real = self.root / 'restart-real'
        restart.rename(real)
        restart.symlink_to(real)
        with self.assertRaises(OSError):
            self.probe()
        restart.unlink()
        real.rename(restart)
        held = self.root / 'held-state'
        self.state.rename(held)
        self.state.symlink_to(held, target_is_directory=True)
        with self.assertRaises(OSError):
            self.probe()

    def test_failed_capability_never_publishes_success(self):
        import windows_folder_probe
        with patch.object(windows_folder_probe, '_sqlite_probe', side_effect=RuntimeError('transaction failed')):
            with self.assertRaisesRegex(RuntimeError, 'transaction failed'):
                self.probe()
        self.assertFalse((self.state / '.linux-native-probe.json').exists())

    def test_native_fs_runs_admission_before_cuda(self):
        for filesystem in ('ef53', '58465342', '9123683e'):
            with self.subTest(filesystem=filesystem), patch.object(self.entry.subprocess, 'check_output', return_value=filesystem), patch.object(self.entry, 'linux_storage_probe') as admission, patch.object(self.entry.ctypes, 'CDLL', side_effect=RuntimeError('CUDA observed')):
                with self.assertRaisesRegex(RuntimeError, 'CUDA observed'):
                    self.entry.preflight()
                admission.assert_called_once_with(require_restart=True)

    def test_runtime_preserves_selected_profile(self):
        runtime = load('runtime_service')
        paths = runtime.canonical_paths()
        self.assertEqual(runtime.api_environment(paths)['FULLMAG_SESSION_STORAGE_PROFILE'], 'linux-native-v1')
        self.assertEqual(str(paths.host_certificate), '/run/fullmag/linux-native-host.json')
        with patch.dict(os.environ, FULLMAG_SESSION_STORAGE_PROFILE='windows-folder-v1'):
            self.assertEqual(runtime.api_environment(runtime.canonical_paths())['FULLMAG_SESSION_STORAGE_PROFILE'], 'windows-folder-v1')
        with patch.dict(os.environ, FULLMAG_SESSION_STORAGE_PROFILE='unknown'):
            with self.assertRaises(runtime.RuntimeServiceError):
                runtime.api_environment(paths)


if __name__ == '__main__':
    unittest.main()
