"""Interpreted regressions for Docker-managed receipt boundaries; no native build."""
from pathlib import Path
import tempfile
import unittest
import sys
from unittest import mock

import docker_backend_volume_cache as cache
from test_docker_backend_volume_cache import _profile, _maintenance_receipt, DockerVolumeFixture
from docker_build_control import BuildControl, BuildControlError, ControlOutcomeUnknown, bounded_capture


class VolumeReceiptTests(unittest.TestCase):
    def test_control_output_and_input_are_bounded_without_host_files(self):
        result = bounded_capture([sys.executable, '-B', '-c', 'import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())'], data=b'expected', maximum=128)
        self.assertEqual(result.stdout, b'expected')
        with self.assertRaises(ControlOutcomeUnknown):
            bounded_capture([sys.executable, '-B', '-c', 'print("x"*1024)'], maximum=128)
        with self.assertRaises(ControlOutcomeUnknown):
            bounded_capture([sys.executable, '-B', '-c', 'import time;time.sleep(10)'], timeout=0.05)

    def test_admitted_volume_receipt_never_uses_a_host_writer(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile, layout, source, repo, runroot = _profile(temporary)
            location = 'docker-volume://fullmag-control-test/development/attempts/test/cache.json'
            profile = cache.prepare(layout, repo, profile['runtime_image_id'], runroot,
                source_root=source, toolchain_image=profile['toolchain_image_id'], volume_receipt=location)
            volumes = DockerVolumeFixture(profile, roles=(cache.BUILD_VOLUME_ROLE, cache.PACKAGE_VOLUME_ROLE))
            published = []
            with mock.patch.object(cache, '_write_json', side_effect=AssertionError('host receipt write')):
                ready = cache.validate(profile, volumes.documents, _maintenance_receipt(profile),
                                       receipt_writer=published.append)
            self.assertEqual(ready['state'], 'ready')
            self.assertEqual(ready['receipt_path'], location)
            self.assertEqual(len(published), 1)
            self.assertFalse((Path(runroot)/cache.RECEIPT_NAME).exists())
            with self.assertRaisesRegex(cache.BackendVolumeCacheError, 'storage contract'):
                cache.validate(profile, volumes.documents, _maintenance_receipt(profile))

    def test_volume_receipt_cannot_escape_or_redirect_its_declared_location(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile, layout, source, repo, runroot = _profile(temporary)
            for location in ('docker-volume://owned/../../other/cache.json', 'C:/host/receipt.json'):
                with self.assertRaises(cache.BackendVolumeCacheError):
                    cache.prepare(layout, repo, profile['runtime_image_id'], runroot,
                        source_root=source, toolchain_image=profile['toolchain_image_id'], volume_receipt=location)

    def test_control_paths_cannot_address_host_or_parent_files(self):
        for path in ('../active', '/control/active', 'a/../../active', 'C:/host/data', "a'; touch /bad"):
            with self.assertRaises(BuildControlError):
                BuildControl.path(path)


if __name__ == '__main__':
    unittest.main()
