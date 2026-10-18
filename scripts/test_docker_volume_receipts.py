"""Interpreted regressions for Docker-managed receipt boundaries; no native build."""
from pathlib import Path
import tempfile
import unittest
import sys
import importlib.util
import subprocess
from unittest import mock

import docker_backend_volume_cache as cache
from test_docker_backend_volume_cache import _profile, _maintenance_receipt, DockerVolumeFixture
from docker_build_control import BuildControl, BuildControlError, ControlOutcomeUnknown, bounded_capture


class VolumeReceiptTests(unittest.TestCase):
    def test_runtime_supervisor_accepts_only_fixed_provenance_locations(self):
        path = Path(__file__).resolve().parents[1] / 'docker/all-in-one/runtime_service.py'
        spec = importlib.util.spec_from_file_location('volume_runtime_paths_test', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertEqual(module.canonical_paths({}).provenance, Path('/opt/fullmag/provenance.json'))
        self.assertEqual(module.canonical_paths({'FULLMAG_PACKAGE_PROVENANCE':'/build/provenance.json'}).provenance,
                         Path('/build/provenance.json'))
        control_provenance = '/opt/fullmag/control/backend/runtime-provenance.json'
        self.assertEqual(module.canonical_paths({'FULLMAG_PACKAGE_PROVENANCE': control_provenance}).provenance,
                         Path(control_provenance))
        with self.assertRaises(module.RuntimeServiceError):
            module.canonical_paths({'FULLMAG_PACKAGE_PROVENANCE':'/state/user-data.json'})

    def test_previous_package_is_ignored_until_current_start_handoff(self):
        import json
        import subprocess
        import docker_volume_dev as dev
        operation = {'receipt': {}, 'root': 'test'}
        control = mock.Mock()
        started = json.dumps([{'State': {'Running': True, 'StartedAt': 'current'}}])
        observations = iter([started, 'building', started, 'phase=start state=cache-hit phase=start state=handoff'])
        documents = {'receipt': {'value': {'state': 'succeeded'}, 'sha256': 'digest'},
                     'provenance': {'value': {'state': 'succeeded', 'build_receipt_sha256': 'digest'}}}
        with mock.patch.object(dev, 'docker_text', side_effect=lambda *a, **k: next(observations)), \
             mock.patch.object(dev, 'docker_capture', return_value=subprocess.CompletedProcess([], 0, json.dumps(documents).encode(), b'')) as capture, \
             mock.patch.object(dev.time, 'sleep', side_effect=lambda *_: self.assertEqual(capture.call_count, 0)):
            receipt, provenance = dev._wait_for_publication(control, operation, 'backend')
        self.assertEqual(capture.call_count, 1)
        self.assertTrue(operation['receipt']['backend_package_cache_hit'])
        self.assertEqual(provenance['build_receipt_sha256'], 'digest')

    def test_publication_refuses_a_changed_backend_incarnation(self):
        import json
        import docker_volume_dev as dev
        observations = iter([json.dumps([{'State': {'Running': True, 'StartedAt': 'first'}}]), 'building',
                             json.dumps([{'State': {'Running': True, 'StartedAt': 'second'}}])])
        with mock.patch.object(dev, 'docker_text', side_effect=lambda *a, **k: next(observations)), \
             mock.patch.object(dev, 'docker_capture') as capture, mock.patch.object(dev.time, 'sleep'):
            with self.assertRaisesRegex(BuildControlError, 'incarnation changed'):
                dev._wait_for_publication(mock.Mock(), {'receipt': {}, 'root': 'test'}, 'backend')
        capture.assert_not_called()

    def test_retained_service_rejects_volume_or_command_drift_before_mutation(self):
        import copy
        import docker_volume_dev as dev
        expected = {'environment': {'SOURCE': 'selected'}, 'labels': {'owner': 'task'},
                    'volumes': [{'type': 'volume', 'source': 'build', 'target': '/build'}]}
        document = {'services': {'backend': expected}, 'volumes': {'build': {'name': 'owned-build'}}}
        image = {'Entrypoint': ['trusted-helper'], 'Cmd': ['serve']}
        actual = {'Config': {'Env': ['SOURCE=selected'], 'Labels': {'owner': 'task'}, **image},
                  'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False, 'Tmpfs': {}},
                  'Mounts': [{'Destination': '/build', 'Type': 'volume', 'RW': True, 'Name': 'owned-build'}]}
        actual['State'] = {'StartedAt': 'first-start'}
        dev._validate_retained_service(document, actual, 'backend', image, expected_started_at='first-start')
        changed = copy.deepcopy(actual)
        changed['State']['StartedAt'] = 'replacement-start'
        with self.assertRaisesRegex(BuildControlError, 'incarnation changed'):
            dev._validate_retained_service(document, changed, 'backend', image, expected_started_at='first-start')
        changed = copy.deepcopy(actual)
        changed['Mounts'][0]['Name'] = 'foreign-build'
        with self.assertRaisesRegex(BuildControlError, 'named-volume identity'):
            dev._validate_retained_service(document, changed, 'backend', image)
        changed = copy.deepcopy(actual)
        changed['Config']['Entrypoint'] = ['foreign-command']
        with self.assertRaisesRegex(BuildControlError, 'image command'):
            dev._validate_retained_service(document, changed, 'backend', image)

    def test_restart_refuses_public_backend_or_foreign_bridge_consumers(self):
        import json
        import docker_volume_dev as dev
        ids = {'backend': 'backend-id', 'frontend': 'frontend-id'}
        actual = {'backend': {'HostConfig': {'PortBindings': {}},
                             'NetworkSettings': {'Networks': {'private': {}}}}}
        network = [{'Driver': 'bridge', 'Labels': {'com.docker.compose.project': 'owned'},
                    'Containers': {'backend-id': {}, 'frontend-id': {}}}]
        with mock.patch.object(dev, 'docker_text', return_value=json.dumps(network)):
            dev._assert_private_restart_network(actual, ids, 'owned')
        network[0]['Containers']['foreign-id'] = {}
        with mock.patch.object(dev, 'docker_text', return_value=json.dumps(network)):
            with self.assertRaisesRegex(BuildControlError, 'unknown consumers'):
                dev._assert_private_restart_network(actual, ids, 'owned')
        actual['backend']['HostConfig']['PortBindings'] = {'8081/tcp': [{}]}
        with mock.patch.object(dev, 'docker_text') as inspect:
            with self.assertRaisesRegex(BuildControlError, 'unpublished private backend'):
                dev._assert_private_restart_network(actual, ids, 'owned')
        inspect.assert_not_called()

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
            profile = cache.prepare(layout, repo, profile['runtime_image_id'], runroot,
                source_root=source, toolchain_image=profile['toolchain_image_id'],
                control_volume_name=profile['volume_names'][cache.CONTROL_VOLUME_ROLE])
            volumes = DockerVolumeFixture(profile, roles=cache.VOLUME_ROLES)
            before = sorted(Path(temporary).rglob('*'))
            with mock.patch.object(Path, 'write_text', side_effect=AssertionError('host receipt write')), \
                 mock.patch.object(Path, 'write_bytes', side_effect=AssertionError('host receipt write')):
                ready = cache.validate(profile, volumes.documents, _maintenance_receipt(profile))
            self.assertEqual(ready['state'], 'ready')
            self.assertEqual(ready['receipt_path'], cache.RECEIPT_TARGET)
            self.assertEqual(ready['receipt']['receipt_path'], cache.RECEIPT_TARGET)
            self.assertEqual(ready['receipt']['receipt_storage'], 'docker-named-volume')
            self.assertIsNone(ready['receipt']['host_receipt_path'])
            self.assertEqual(sorted(Path(temporary).rglob('*')), before)
            self.assertFalse((Path(runroot)/cache.RECEIPT_NAME).exists())

    def test_volume_receipt_cannot_escape_or_redirect_its_declared_location(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile, *_ = _profile(temporary)
            volumes = DockerVolumeFixture(profile, roles=cache.VOLUME_ROLES)
            for location in ('docker-volume://owned/../../other/cache.json', 'C:/host/receipt.json',
                             '/opt/fullmag/control/backend/../other.json',
                             '/opt/fullmag/control/other.json'):
                with self.subTest(location=location):
                    with self.assertRaises(cache.BackendVolumeCacheError):
                        cache.validate(profile, volumes.documents, _maintenance_receipt(profile),
                                       receipt_path=location)

    def test_just_guard_admits_device_policy_without_shell_tail(self):
        wrapper = (Path(__file__).resolve().parents[1] / 'scripts/just_storage_shell.sh').read_text(encoding='utf-8')
        assignment = next(line.strip() for line in wrapper.splitlines() if line.strip().startswith('docker_dev_pattern='))
        base = 'python "D:/repo/scripts/docker_dev.py" --repo-root "D:/repo" '
        for action in ('build', "up --port '3202'"):
            for policy in ('auto', 'required', 'disabled'):
                recipe = base + action + " --gpu-access '" + policy + "' --source-root 'D:/owned/worktree' "
                for suffix, expected in (('', 0), ('; echo injected', 1)):
                    with self.subTest(action=action, policy=policy, suffix=suffix):
                        result = subprocess.run(['bash', '-c', assignment + '\n[[ "$1" =~ ${docker_dev_pattern} ]]',
                                                 'recipe-guard', recipe + suffix], capture_output=True)
                        self.assertEqual(result.returncode, expected, result.stderr)

    def test_control_paths_cannot_address_host_or_parent_files(self):
        for path in ('../active', '/control/active', '/opt/fullmag/control/active', 'a/../../active', 'C:/host/data', "a'; touch /bad"):
            with self.assertRaises(BuildControlError):
                BuildControl.path(path)


if __name__ == '__main__':
    unittest.main()
