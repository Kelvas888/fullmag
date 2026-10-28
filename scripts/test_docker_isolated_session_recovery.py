import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import docker_isolated_session_recovery as recovery
from docker_build_control import BuildControlError, canonical


class SuccessorAdmissionTests(unittest.TestCase):
    def fixture(self):
        control=mock.Mock(namespace='namespaces/'+'a'*32,
                          namespace_registry_sha256='b'*64)
        pins={'development_attempt':'c'*32,'compose_config_sha256':'d'*64,
              'backend_container_id':'e'*64,'frontend_container_id':'f'*64}
        terminal=canonical({'schema':'fullmag.docker-build-operation.v1',
            'phase':'development','state':'succeeded','attempt':pins['development_attempt'],
            'config_sha256':pins['compose_config_sha256'],
            'backend_container':pins['backend_container_id'],
            'frontend_container':pins['frontend_container_id'],
            'control_namespace':control.namespace,
            'namespace_registry_sha256':control.namespace_registry_sha256})
        documents={'development/current.json':terminal,'development/verified.json':terminal,
                   'isolated-snapshot/native-validation.json':b'validated-native-proof'}
        control.read_bytes.side_effect=lambda path: documents[path]
        return control,pins,terminal,documents

    def test_admitted_predecessor_pins_all_admission_evidence(self):
        control,pins,terminal,documents=self.fixture()
        with mock.patch('docker_control_namespace.assert_namespace_activation') as validate:
            result=recovery._successor_admission_pins(control,pins,terminal)
        validate.assert_called_once_with(control)
        self.assertEqual(result,{control.namespace+'/'+path:raw for path,raw in documents.items()})

    def test_unadmitted_or_changed_current_receipt_is_refused(self):
        for path in ('development/current.json','development/verified.json'):
            with self.subTest(path=path):
                control,pins,terminal,documents=self.fixture()
                documents[path]=canonical({'state':'starting'})
                with mock.patch('docker_control_namespace.assert_namespace_activation'):
                    with self.assertRaises(BuildControlError):
                        recovery._successor_admission_pins(control,pins,terminal)
        control,pins,terminal,_=self.fixture()
        with mock.patch('docker_control_namespace.assert_namespace_activation',
                        side_effect=BuildControlError('native admission absent')):
            with self.assertRaises(BuildControlError):
                recovery._successor_admission_pins(control,pins,terminal)

    def test_wrong_attempt_config_containers_or_namespace_are_refused(self):
        for key in ('attempt','config_sha256','backend_container','frontend_container',
                    'control_namespace','namespace_registry_sha256','state','phase'):
            with self.subTest(key=key):
                control,pins,terminal,documents=self.fixture()
                value=json.loads(terminal);value[key]='wrong'
                terminal=canonical(value)
                documents['development/current.json']=documents['development/verified.json']=terminal
                with mock.patch('docker_control_namespace.assert_namespace_activation'):
                    with self.assertRaises(BuildControlError):
                        recovery._successor_admission_pins(control,pins,terminal)

    def test_native_receipt_cannot_change_during_validation(self):
        control,pins,terminal,documents=self.fixture()
        def changed(_control):
            documents['isolated-snapshot/native-validation.json']=b'changed'
        with mock.patch('docker_control_namespace.assert_namespace_activation',side_effect=changed):
            with self.assertRaises(BuildControlError):
                recovery._successor_admission_pins(control,pins,terminal)

    def test_successor_is_explicit_and_existing_retry_keeps_original_start(self):
        control=mock.Mock(project='fullmag-master',namespace='namespaces/'+'a'*32,
            namespace_registry={'retirement':{'schema':recovery.SNAPSHOT_SCHEMA,'recovery_id':'a'*32}})
        original_start={'restore_run_id':'original-held-run'}
        control.read.return_value=original_start.copy()
        args=SimpleNamespace(recovery_id='b'*32,successor_snapshot=False,apply=False,
            operator_pins=Path('pins.json'),restore_run_id='new-held-run')
        with mock.patch.object(recovery.retained,'_read_operator_file',return_value=({},b'{}',Path('pins.json'))), \
             mock.patch.object(recovery.retained,'_request_context',return_value={'control':control}):
            with self.assertRaises(BuildControlError):
                recovery.recover(args)
            args.recovery_id='a'*32;args.restore_run_id='original-held-run'
            self.assertEqual(recovery.recover(args)['state'],'snapshot-awaiting-gated-start')
            args.restore_run_id='new-held-run'
            with self.assertRaises(BuildControlError):
                recovery.recover(args)
        self.assertEqual(control.read.return_value,original_start)
        control.write.assert_not_called()
        control.write_bytes.assert_not_called()


class IsolatedCommitTests(unittest.TestCase):
    def fixture(self, root):
        (root/'namespaces/new').mkdir(parents=True)
        (root/'namespaces/current.json').write_bytes(b'old-registry')
        (root/'operation.lock').write_bytes(b'')
        (root/'original-owner.json').write_bytes(b'original-owner')
        return {'previous_registry_sha256':recovery.digest(b'old-registry'),
                'pins':{'original-owner.json':recovery.digest(b'original-owner')},
                'namespace':'namespaces/new','recovery_id':'a'*32,'registry':{'new':'registry'}}

    def run_commit(self, root, payload):
        script=recovery.COMMIT.replace("pathlib.Path('/control')",'pathlib.Path('+repr(str(root))+')')
        return subprocess.run([sys.executable,'-I','-B','-c',script],input=canonical(payload),capture_output=True)

    def test_commit_preserves_owner_and_links_same_operation_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);payload=self.fixture(root)
            result=self.run_commit(root,payload)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((root/'original-owner.json').read_bytes(),b'original-owner')
            self.assertEqual(json.loads((root/'namespaces/current.json').read_bytes()),payload['registry'])
            self.assertEqual((root/'operation.lock').stat().st_ino,(root/'namespaces/new/operation.lock').stat().st_ino)

    def test_registry_cas_or_source_pin_drift_never_publishes(self):
        for field in ('registry','owner'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                root=Path(folder);payload=self.fixture(root)
                if field=='registry':(root/'namespaces/current.json').write_bytes(b'new-external-value')
                else:(root/'original-owner.json').write_bytes(b'changed')
                before=(root/'namespaces/current.json').read_bytes()
                self.assertNotEqual(self.run_commit(root,payload).returncode,0)
                self.assertEqual((root/'namespaces/current.json').read_bytes(),before)

    def test_owner_control_pins_validated_config_image_without_mutating_control(self):
        control=mock.Mock(image='nvidia/cuda:base@sha256:'+'a'*64,
                          namespace='namespaces/'+'b'*32)
        backend={'Image':'sha256:'+'c'*64}
        owner=recovery._owner_control(control,backend)
        self.assertIsNot(owner,control)
        self.assertEqual(owner.image,backend['Image'])
        self.assertEqual(owner.namespace,control.namespace)
        self.assertEqual(control.image,'nvidia/cuda:base@sha256:'+'a'*64)
        for invalid in ({}, {'Image':'nvidia/cuda:latest'}):
            with self.assertRaises(BuildControlError):
                recovery._owner_control(control,invalid)

    def test_removal_refuses_live_container_without_stop(self):
        record={'old_container_ids':{'backend':'a'*64},'old_image_id':'sha256:'+'b'*64,'compose_project':'fullmag-master'}
        row={'Id':'a'*64,'Image':record['old_image_id'],'State':{'Status':'running','Running':True}}
        responses=[mock.Mock(stdout=('a'*64+'\n').encode()),mock.Mock(stdout=json.dumps([row]).encode())]
        with mock.patch.object(recovery,'docker_capture',side_effect=responses) as capture:
            with self.assertRaises(ValueError):recovery._remove_stopped(record)
        self.assertFalse(any(c.args[0] in ('stop','rm','restart') for c in capture.call_args_list))

class SnapshotActivationTests(unittest.TestCase):
    def fixture(self):
        import hashlib
        import docker_control_namespace as namespace
        request={'retained_terminal_runs':[{'run_id':'terminal'}],
                 'retained_held_manual_runs':[{'run_id':'held'}]}
        manifest=canonical({'retired_request_ids':['old-preview','old-other']})
        request_raw=canonical(request)
        record={'schema':recovery.SNAPSHOT_SCHEMA,'old_request_id':'old-preview',
                'request_sha256':recovery.digest(request_raw),'original_config_sha256':'c'*64,
                'source_manifest_sha256':recovery.digest(manifest),
                'terminal_run_count':1,'held_manual_run_count':1}
        validation={'schema_version':'runtime_service_retained_snapshot_validation.v1',
                    'state':'validated-read-only','request_sha256':record['request_sha256'],
                    'config_sha256':'c'*64,'source_manifest_sha256':record['source_manifest_sha256'],
                    'run_ids':['held','terminal'],'terminal_count':1,'held_count':1,
                    'owner_changed':False,'compute_started':False}
        control=mock.Mock(namespace='namespaces/'+'a'*32,
                          namespace_registry={'retirement':record})
        control.read.return_value=validation
        control.read_bytes.side_effect=lambda path: manifest if 'manifest' in path else request_raw
        return namespace,control,validation

    def test_activation_requires_native_admission_and_typed_receipt(self):
        for replacement in (None,{'owner_changed':0},{'unknown':False}):
            with self.subTest(replacement=replacement):
                namespace,control,validation=self.fixture()
                control.read.return_value=None if replacement is None else {**validation,**replacement}
                with self.assertRaises(BuildControlError):
                    namespace.assert_namespace_activation(control,'new-request')

    def test_activation_rejects_all_retired_requests_even_after_admission(self):
        for request in ('old-preview','old-other'):
            namespace,control,_=self.fixture()
            with self.assertRaises(BuildControlError):
                namespace.assert_namespace_activation(control,request)

    def test_activation_allows_new_request_only_after_exact_native_evidence(self):
        namespace,control,_=self.fixture()
        namespace.assert_namespace_activation(control,'new-request')

    def test_activation_rejects_manifest_drift(self):
        namespace,control,_=self.fixture()
        control.read_bytes.side_effect=None
        control.read_bytes.return_value=b'{}'
        with self.assertRaises(BuildControlError):
            namespace.assert_namespace_activation(control,'new-request')

class SnapshotPlaceholderTests(unittest.TestCase):
    def fixture(self, root):
        import docker_volume_dev as dev
        path=root/'linux-native-host.json';path.write_bytes(b'')
        snapshot={'source_root':'/source/master','destination_state_root':str(root)}
        previous={'state':'failed-confirmed','control_namespace':'namespaces/test',
                  'namespace_registry_sha256':'a'*64,'inputs':{'source_root':'/source/master'},
                  'error':'runtime-control control namespace is nonempty without its owner marker'}
        control=mock.Mock(namespace='namespaces/test',namespace_registry_sha256='a'*64)
        control.read.return_value=previous;control.read_bytes.return_value=None
        return dev,path,snapshot,previous,control

    def test_known_cache_failure_retains_empty_placeholder_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);dev,path,snapshot,previous,control=self.fixture(root)
            before=path.stat()
            dev._snapshot_certificate_placeholder(control,root,path,snapshot)
            after=path.stat()
            self.assertEqual((before.st_ino,before.st_mtime_ns,before.st_ctime_ns),
                             (after.st_ino,after.st_mtime_ns,after.st_ctime_ns))
            self.assertEqual(path.read_bytes(),b'')

    def test_foreign_or_already_admitted_placeholder_is_never_adopted(self):
        for mutation in ('nonempty','owner','native','unknown','different_namespace'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);dev,path,snapshot,previous,control=self.fixture(root)
                if mutation=='nonempty':path.write_bytes(b'{}')
                elif mutation=='owner':(root/recovery.host.OWNER_NAME).write_bytes(b'owner')
                elif mutation=='native':control.read_bytes.return_value=b'{}'
                elif mutation=='unknown':previous['state']='unknown'
                else:previous['control_namespace']='foreign'
                before=path.read_bytes()
                with self.assertRaises((RuntimeError,OSError,ValueError)):
                    dev._snapshot_certificate_placeholder(control,root,path,snapshot)
                self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()
