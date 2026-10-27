"""Docker-free checks for original-evidence abrupt stop recovery."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import docker_volume_container_recovery as r


class AbruptStopTests(unittest.TestCase):
    def fixture(self):
        project = 'fullmag-master'
        owner = {'schema_version': 'runtime_service_owner.v1', 'state': 'ready',
                 'owner_token': 'old-token', 'process_start_token': 'old-start',
                 'target_id': 'docker-all', 'host': 'old-backend', 'protocol': 'tcp',
                 'pid': 10, 'children': [{'role': 'compute', 'pid': 11}, {'role': 'preparation', 'pid': 12}]}
        originals = {'process_receipt': {'schema': 'fullmag.docker-process-tree.v1', 'state': 'ready', 'service_owner': owner},
                     'owner': owner, 'launch': {'original': 'launch'}, 'config': {'store_root': '/state/runs/docker-all/session-store'}}
        records = {}
        for key, path in {'process_receipt': 'runtime-service/process-tree.json', 'owner': 'runtime-services/OWNER.json',
                          'launch': 'runtime-services/LAUNCH.json', 'config': 'runtime-service/docker-all.json'}.items():
            # Intentionally retain noncanonical formatting.
            raw = (json.dumps(originals[key], indent=3) + '\n').encode()
            records[key] = {'path': 'runtime-control/' + path, 'raw_utf8': raw.decode(), 'sha256': r._sha256(raw)}
        compose = {'name': project}
        pins = {'request_id': '1eccf696-733d-4506-bbd7-9fd79ea602fa', 'source_root': '/selected/source',
                'compose_project': project, 'development_attempt': 'a'*32, 'compose_config_sha256': r._sha256(r._canonical(compose)),
                'backend_container_id': 'b'*64, 'frontend_container_id': 'c'*64, 'old_image_id': 'sha256:'+'d'*64,
                **{key+'_sha256': item['sha256'] for key,item in records.items()}}
        containers = {}
        for service in ('backend', 'frontend'):
            containers[service] = {'Id': pins[service+'_container_id'], 'Image': pins['old_image_id'],
                'Config': {'Hostname': 'old-backend' if service=='backend' else 'old-frontend', 'Labels': {
                    'com.docker.compose.project': project, 'com.docker.compose.service': service}},
                'HostConfig': {'PidMode': '', 'IpcMode': 'private', 'NetworkMode': 'fullmag-private'},
                'NetworkSettings': {'Networks': {'fullmag-private': {'NetworkID': 'e'*64}}},
                'Mounts': [{'Type': 'bind', 'Source': '/state/source', 'Destination': '/state', 'RW': True}],
                'State': {'Status': 'exited', 'Running': False, 'Paused': False, 'Restarting': False,
                          'Pid': 0, 'ExitCode': 255, 'StartedAt': '2026-10-26T00:00:00Z', 'FinishedAt': '2026-10-27T00:00:00Z'}}
        proof = {'schema': r.ABRUPT_PROOF_SCHEMA, 'authorization_pins': pins,
                 'docker_engine_id_sha256': 'f'*64, 'raw_records': records, 'containers': containers,
                 'network': {'name': 'fullmag-private', 'network_id': 'e'*64, 'state': 'absent'},
                 'storage_proof': {'run_records': []}, 'retained_terminal_runs': None}
        auth = r.validate_operator_authorization({**pins, 'schema_version': r.ABRUPT_OPERATOR_SCHEMA,
            'abrupt_stop_proof': 'verification/abrupt-proof.json', 'abrupt_stop_proof_sha256': r._sha256(r._canonical(proof))})
        return proof, auth, compose

    def test_v2_frozen_fields_and_original_ready_bytes(self):
        proof, auth, _ = self.fixture()
        r.validate_abrupt_stop_proof(proof, auth)
        self.assertEqual(proof['raw_records']['process_receipt']['raw_utf8'][-1], '\n')
        with self.assertRaises(r.ContainerRecoveryError):
            r.validate_operator_authorization({**auth, 'prior_stop_journal': 'fake.json'})
        stale = copy.deepcopy(proof)
        stale['raw_records']['owner']['raw_utf8'] += ' '
        with self.assertRaisesRegex(r.ContainerRecoveryError, 'bytes'):
            r.validate_abrupt_stop_proof(stale, auth)

    def test_v1_still_requires_shutdown_unknown_process_receipt(self):
        raw=b'{"schema":"fullmag.docker-process-tree.v1","state":"ready"}'
        with patch.object(r,'_control_json',return_value=(json.loads(raw),raw)):
            with self.assertRaisesRegex(r.ContainerRecoveryError,'shutdown_unknown'):
                r._runtime_process_receipt(SimpleNamespace())
            self.assertEqual(r._runtime_process_receipt(SimpleNamespace(),abrupt=True)[1],raw)

    def test_strict_stopped_rejects_boolean_ints_running_and_shared_namespaces(self):
        proof, _, _ = self.fixture()
        original = proof['containers']['backend']
        for field, value in [('Running', True), ('Running', None), ('Pid', False), ('ExitCode', True),
                             ('Restarting', True), ('Paused', True), ('Status', 'created'), ('FinishedAt', '0001-01-01T00:00:00Z')]:
            with self.subTest(field=field, value=value):
                item = copy.deepcopy(original); item['State'][field] = value
                with self.assertRaises(r.ContainerRecoveryError): r._strict_stopped(item)
        for field,value in [('PidMode','host'), ('IpcMode','shareable'), ('NetworkMode','host')]:
            item=copy.deepcopy(original); item['HostConfig'][field]=value
            with self.assertRaises(r.ContainerRecoveryError): r._strict_stopped(item)

    def test_network_absence_requires_inventory_and_recognized_inspect_failure(self):
        proof, _, _ = self.fixture(); b,f=proof['containers'].values()
        empty=SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
        missing=SimpleNamespace(returncode=1, stdout=b'', stderr=b'Error: No such network: '+b'e'*64)
        with patch.object(r,'docker_capture',side_effect=[empty, missing, empty]) as docker:
            self.assertEqual(r._abrupt_network(b,f,'fullmag-master')['state'],'absent')
            self.assertEqual(docker.call_count,3)
        failed=SimpleNamespace(returncode=1, stdout=b'', stderr=b'Cannot connect to Docker daemon')
        with patch.object(r,'docker_capture',side_effect=[empty,failed]):
            with self.assertRaisesRegex(r.ContainerRecoveryError,'absence'): r._abrupt_network(b,f,'fullmag-master')
        with patch.object(r,'docker_capture',side_effect=r.BuildControlError('daemon unavailable')):
            with self.assertRaises(r.BuildControlError): r._abrupt_network(b,f,'fullmag-master')

    def test_network_name_reuse_and_foreign_consumers_fail_closed(self):
        proof,_,_=self.fixture(); b,f=proof['containers'].values()
        reused=SimpleNamespace(stdout=json.dumps({'Name':'fullmag-private','ID':'a'*64}).encode())
        with patch.object(r,'docker_capture',return_value=reused):
            with self.assertRaisesRegex(r.ContainerRecoveryError,'changed'): r._abrupt_network(b,f,'fullmag-master')
        foreign={'Id':'a'*64,'Mounts':b['Mounts']}
        with patch.object(r,'docker_capture',side_effect=[SimpleNamespace(stdout=('a'*64).encode()), SimpleNamespace(stdout=json.dumps([foreign]).encode())]):
            with self.assertRaisesRegex(r.ContainerRecoveryError,'foreign'): r._assert_no_foreign_storage_consumers(SimpleNamespace(),b,f)

    def test_only_exact_authenticated_operation_helper_is_exempt(self):
        proof,_,_=self.fixture(); b,f=proof['containers'].values()
        helper='1'*64; lookalike='2'*64; operation={}
        authenticated=[]
        control=SimpleNamespace(_active_operation=operation,_pin_operation_helper=lambda current: authenticated.append(current) or helper)
        with patch.object(r,'docker_capture',return_value=SimpleNamespace(stdout=helper.encode())) as docker:
            r._assert_no_foreign_storage_consumers(control,b,f)
        self.assertEqual(authenticated,[operation]); self.assertEqual(docker.call_count,1)
        foreign={'Id':lookalike,'Config':{'Labels':{'com.docker.compose.service':'build-control'}},'Mounts':b['Mounts']}
        with patch.object(r,'docker_capture',side_effect=[SimpleNamespace(stdout=(helper+' '+lookalike).encode()),SimpleNamespace(stdout=json.dumps([foreign]).encode())]):
            with self.assertRaisesRegex(r.ContainerRecoveryError,'foreign'):
                r._assert_no_foreign_storage_consumers(control,b,f)
        control._pin_operation_helper=lambda current: (_ for _ in ()).throw(r.BuildControlError('helper config drift'))
        with patch.object(r,'docker_capture',return_value=SimpleNamespace(stdout=helper.encode())):
            with self.assertRaisesRegex(r.BuildControlError,'config drift'):
                r._assert_no_foreign_storage_consumers(control,b,f)

    def test_foreign_desktop_alias_is_not_assumed_distinct_from_same_store(self):
        proof,_,compose=self.fixture(); b,f=proof['containers'].values()
        prefix='/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/Ubuntu2/'
        b['Mounts'][0]['Source']=prefix+'hashA'
        compose['services']={'backend':{'volumes':[{'type':'bind','source':'/canonical/state','target':'/state'}]}}
        for alias in ('hashA','hashB','unknown'):
            foreign={'Id':'a'*64,'Mounts':[{'Type':'bind','Source':prefix+alias,'Destination':'/state','RW':True}]}
            with self.subTest(alias=alias),patch.object(r,'docker_capture',side_effect=[SimpleNamespace(stdout=('a'*64).encode()),SimpleNamespace(stdout=json.dumps([foreign]).encode())]):
                with self.assertRaisesRegex(r.ContainerRecoveryError,'unresolved storage identity'):
                    r._assert_no_foreign_storage_consumers(SimpleNamespace(),b,f,compose)

    def test_wrapper_publish_runs_real_consumer_gate_with_authenticated_lease(self):
        import contextlib
        import docker_prepare_container_recovery as preparation
        proof,auth,compose=self.fixture(); pins=proof['authorization_pins']
        docs={item['path']:item['raw_utf8'].encode() for item in proof['raw_records'].values()}
        authenticated=[]; active_helper='1'*64
        @contextlib.contextmanager
        def operation(*args):
            op={'receipt':{'attempt':'operation-attempt'},'root':'operations/fake'}
            control._active_operation=op
            try: yield op
            finally: control._active_operation=None
        def pin(op):
            self.assertIs(control._active_operation,op)
            authenticated.append(op)
            return active_helper
        control=SimpleNamespace(project=compose['name'],_active_operation=None,_pin_operation_helper=pin,
            prepare=lambda:None,operation=operation,read_bytes=lambda path,optional=False:docs.get(path),
            write_bytes=lambda path,raw:docs.update({path:raw}))
        calls=[]
        def docker(*args,**kwargs):
            self.assertEqual(args,('ps','-aq','--no-trunc'))
            calls.append(args)
            return SimpleNamespace(stdout=active_helper.encode() if control._active_operation else b'')
        with patch.object(r,'_control_bytes',side_effect=lambda c,p:docs[p]),patch.object(r,'_control_json',side_effect=lambda c,p:(json.loads(docs[p]),docs[p])),patch.object(r,'_inspect_pair',return_value=tuple(proof['containers'].values())),patch.object(r,'_ledger_and_store_snapshot',return_value=proof['storage_proof']),patch.object(r,'_docker_engine_sha',return_value='f'*64),patch.object(r,'_abrupt_network',return_value=proof['network']),patch.object(r,'docker_capture',side_effect=docker):
            result=preparation.prepare(control,pins,compose,publish=True)
        self.assertEqual(result['state'],'prepared-awaiting-explicit-start')
        self.assertEqual(len(calls),3)
        self.assertEqual(len(authenticated),2)
        self.assertIn(result['proof_path'],docs)

    def test_live_cas_rejects_raw_engine_and_container_drift(self):
        proof,auth,compose=self.fixture()
        records={item['path']:item['raw_utf8'].encode() for item in proof['raw_records'].values()}
        with patch.object(r,'_control_bytes',side_effect=lambda c,p: records[p]+b' '):
            with self.assertRaisesRegex(r.ContainerRecoveryError,'stale'): r.validate_abrupt_stop_proof(proof,auth,control=SimpleNamespace(),compose=compose)
        with patch.object(r,'_control_bytes',side_effect=lambda c,p: records[p]), patch.object(r,'_docker_engine_sha',return_value='a'*64):
            with self.assertRaisesRegex(r.ContainerRecoveryError,'engine'): r.validate_abrupt_stop_proof(proof,auth,control=SimpleNamespace(),compose=compose)
        drift=copy.deepcopy(proof['containers']); drift['backend']['State']['ExitCode']=1
        with patch.object(r,'_control_bytes',side_effect=lambda c,p: records[p]), patch.object(r,'_docker_engine_sha',return_value='f'*64), patch.object(r,'_inspect_pair',return_value=tuple(drift.values())):
            with self.assertRaisesRegex(r.ContainerRecoveryError,'observations'): r.validate_abrupt_stop_proof(proof,auth,control=SimpleNamespace(project=compose['name']),compose=compose)

    def test_owner_host_and_identity_cannot_be_fabricated(self):
        proof,auth,_=self.fixture()
        for key in ('host','owner_token'):
            modified=copy.deepcopy(proof)
            owner=json.loads(modified['raw_records']['owner']['raw_utf8']); owner[key]='foreign'
            raw=r._canonical(owner); modified['raw_records']['owner'].update(raw_utf8=raw.decode(),sha256=r._sha256(raw))
            changed_auth={**auth,'owner_sha256':r._sha256(raw)}
            modified['authorization_pins']['owner_sha256']=r._sha256(raw)
            with self.assertRaises(r.ContainerRecoveryError): r.validate_abrupt_stop_proof(modified,changed_auth)

    def test_prepare_archives_originals_without_control_writes(self):
        proof,_,compose=self.fixture(); pins=proof['authorization_pins']; c=SimpleNamespace(project=compose['name'])
        paths={item['path']:item['raw_utf8'].encode() for item in proof['raw_records'].values()}
        with patch.object(r,'_control_json',side_effect=lambda c,p: (json.loads(paths[p]),paths[p])), patch.object(r,'_inspect_pair',return_value=tuple(proof['containers'].values())), patch.object(r,'_assert_no_foreign_storage_consumers'), patch.object(r,'_ledger_and_store_snapshot',return_value=proof['storage_proof']), patch.object(r,'_docker_engine_sha',return_value='f'*64), patch.object(r,'_abrupt_network',return_value=proof['network']):
            observed=r.prepare_abrupt_stop_proof(c,pins,compose)
        self.assertEqual(observed,proof)

    def test_prepared_retry_cas_keeps_archived_observations(self):
        proof,auth,compose=self.fixture(); records={i['path']:i['raw_utf8'].encode() for i in proof['raw_records'].values()}
        transition={**proof['containers'],'present':{}}
        with patch.object(r,'_control_bytes',side_effect=lambda c,p:records[p]), patch.object(r,'_docker_engine_sha',return_value='f'*64), patch.object(r,'_abrupt_network'), patch.object(r,'_assert_no_foreign_storage_consumers'), patch.object(r,'_ledger_and_store_snapshot',return_value=proof['storage_proof']):
            r.validate_abrupt_stop_proof(proof,auth,control=SimpleNamespace(project=compose['name']),compose=compose,transition=transition)
            transition['backend']=copy.deepcopy(transition['backend']); transition['backend']['State']['ExitCode']=1
            with self.assertRaisesRegex(r.ContainerRecoveryError,'prepared retry'): r.validate_abrupt_stop_proof(proof,auth,control=SimpleNamespace(project=compose['name']),compose=compose,transition=transition)

    def test_history_publication_is_immutable(self):
        control=SimpleNamespace(write_bytes=lambda *a: self.fail('must not overwrite'))
        with patch.object(r,'_control_bytes',return_value=b'{"original":true}'):
            r._write_record(control,'proof.json',{'original':True})
            with self.assertRaisesRegex(r.ContainerRecoveryError,'history'): r._write_record(control,'proof.json',{'original':False})

    def test_terminal_pin_shape_outcome_and_v1_v2_isolation(self):
        pin={'run_id':'run-1','run_intent_sha256':'a'*64,'run_catalog_sha256':'b'*64,'artifact_catalog_sha256':None}
        request={'schema_version':r.TERMINAL_REQUEST_SCHEMA,'retained_terminal_runs':[pin]}
        self.assertEqual(r.expected_recovery_outcome(request),'retained_terminal_runs_recovered')
        for changed in [[],[pin,pin],[{**pin,'artifact_catalog_sha256':'bad'}],[{k:v for k,v in pin.items() if k!='artifact_catalog_sha256'}]]:
            with self.assertRaises(r.ContainerRecoveryError): r.expected_recovery_outcome({**request,'retained_terminal_runs':changed})
        for schema in (r.REQUEST_SCHEMA,r.RETAINED_REQUEST_SCHEMA):
            with self.assertRaises(r.ContainerRecoveryError): r.expected_recovery_outcome({**request,'schema_version':schema})
        with self.assertRaises(r.ContainerRecoveryError): r.expected_recovery_outcome({**request,'retained_cancelled_runs':[pin]})

    def test_snapshot_uses_only_pinned_canonical_state_for_stale_wsl_alias(self):
        proof,_,_=self.fixture(); backend=proof['containers']['backend']
        alias='/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/Ubuntu2/old'
        backend['Mounts']=[{'Type':'bind','Source':alias,'Destination':'/state','RW':True},
                           {'Type':'bind','Source':'/ledger/source','Destination':'/host-ledger','RW':True}]
        compose={'services':{'backend':{'volumes':[{'type':'bind','source':'/canonical/state','target':'/state'}],
                                            'x-fullmag-daemon-binds':{'/state':alias}}}}
        output={'store_root_sha256':'1'*64,'ledger_root_sha256':'2'*64,'ledger_snapshot_sha256':'3'*64,'run_records':[]}
        with patch.object(r,'bounded_capture',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(output).encode(),stderr=b'')) as helper:
            r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,compose=compose)
            self.assertIn('type=bind,src=/canonical/state,dst=/state,readonly',helper.call_args.args[0])
            compose['services']['backend']['x-fullmag-daemon-binds']['/state']='foreign-alias'
            with self.assertRaisesRegex(r.ContainerRecoveryError,'retained daemon alias'):
                r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,compose=compose)
            self.assertEqual(helper.call_count,1)

    def test_terminal_helper_checks_real_raw_catalog_artifact_and_active_leases(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); state=root/'state'; ledger=root/'ledger'; ledger.mkdir(); (ledger/'WRITER.lock').touch()
            (ledger/'HOST_RESOURCE_LEDGER.json').write_text(json.dumps({'policy':{},'reservations':[]}))
            run=state/'runs/docker-all/session-store/runs/run-1'; run.mkdir(parents=True)
            (run.parent.parent/'objects/pins').mkdir(parents=True)
            intent=b'{"run_id":"run-1"}'; catalog=b'{"tasks":[{"task_id":"task-1","attempt_id":"current-attempt","ownership_epoch":1,"lifecycle":"succeeded","artifact_ids":["result"]}]}'
            artifact=b'{"entries":[{"id":"result"}]}'
            for name,raw in [('run_intent',intent),('run_catalog',catalog),('artifact_catalog',artifact)]: (run/(name+'.json')).write_bytes(raw)
            pin={'run_id':'run-1','run_intent_sha256':r._sha256(intent),'run_catalog_sha256':r._sha256(catalog),'artifact_catalog_sha256':r._sha256(artifact)}
            backend={'Image':'sha256:'+'d'*64,'Mounts':[{'Type':'bind','Source':str(state),'Destination':'/state','RW':True},{'Type':'bind','Source':str(root),'Destination':'/host-ledger','RW':True}]}
            def execute(argv,**kwargs):
                # Replace the one fixed store path without touching digest constants.
                script=argv[-2].replace("pathlib.Path('/state/runs/docker-all/session-store')",'pathlib.Path('+repr(str(state/'runs/docker-all/session-store'))+')').replace("pathlib.Path('/host-ledger/ledger')",'pathlib.Path('+repr(str(ledger))+')')
                return subprocess.run([sys.executable,'-B','-c',script,argv[-1]],capture_output=True)
            with patch.object(r,'bounded_capture',side_effect=execute):
                result=r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])
                self.assertEqual(result['run_records'],[pin])
                (run/'artifact_catalog.json').write_bytes(artifact+b' ')
                with self.assertRaisesRegex(r.ContainerRecoveryError,'bytes differ'): r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])
                (run/'artifact_catalog.json').write_bytes(artifact)
                cas=run.parent.parent/'objects/sha256'; cas.mkdir()
                payload=b'accepted input'; ref=r._sha256(payload); (cas/ref).write_bytes(payload)
                (run.parent.parent/'objects/pins'/(ref+'.json')).write_text(json.dumps({'schema':'fullmag.cas-pin.v1','object_ref':ref}))
                intent=json.dumps({'run_id':'run-1','definition_object_ref':ref}).encode(); (run/'run_intent.json').write_bytes(intent)
                pin={**pin,'run_intent_sha256':r._sha256(intent)}
                self.assertEqual(r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])['run_records'],[pin])
                (cas/ref).write_bytes(b'tampered accepted input')
                with self.assertRaisesRegex(r.ContainerRecoveryError,'CAS object bytes differ'):
                    r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])
                (cas/ref).write_bytes(payload)
                pending=run.parent.parent/'temp'; pending.mkdir(); pending_file=pending/'pending'; pending_file.write_text('pending')
                with self.assertRaisesRegex(r.ContainerRecoveryError,'pending or unknown'):
                    r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])
                pending_file.unlink()
                leases=run/'resource_leases/cpu'; leases.mkdir(parents=True); (leases/'lease.json').write_text('{"state":"active"}')
                with self.assertRaisesRegex(r.ContainerRecoveryError,'active or unknown'): r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])
                lease={'state':'released','run_id':'run-1','task_id':'task-1','attempt_id':'current-attempt','ownership_epoch':1}
                (leases/'lease.json').write_text(json.dumps(lease))
                admissions=run/'task_admissions/task-1';admissions.mkdir(parents=True)
                admission={'task':{'task_id':'task-1','attempt_id':'current-attempt','ownership_epoch':1},'lease':{**lease,'state':'active'}}
                admission_path=admissions/'current-attempt.json';admission_path.write_text(json.dumps(admission))
                self.assertEqual(r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])['run_records'],[pin])
                for older_lease in ({**lease,'attempt_id':'historical-attempt'},{**lease,'ownership_epoch':2}):
                    (leases/'lease.json').write_text(json.dumps(older_lease))
                    with self.assertRaisesRegex(r.ContainerRecoveryError,'unsupported historical retry'):
                        r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])
                (leases/'lease.json').write_text(json.dumps(lease))
                for component in ('task','lease'):
                    alternate=copy.deepcopy(admission);alternate[component]['attempt_id']='historical-attempt'
                    admission_path.write_text(json.dumps(alternate))
                    with self.assertRaisesRegex(r.ContainerRecoveryError,'unsupported historical retry'):
                        r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])
                admission_path.write_text(json.dumps(admission))
                alternate_path=admissions/'historical-attempt.json';alternate_path.write_text(json.dumps(admission))
                with self.assertRaisesRegex(r.ContainerRecoveryError,'unsupported historical retry'):
                    r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])
                alternate_path.unlink()
                null_pin={**pin,'artifact_catalog_sha256':None}; (run/'artifact_catalog.json').unlink()
                with self.assertRaisesRegex(r.ContainerRecoveryError,'outputs'): r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[null_pin])
                (ledger/'HOST_RESOURCE_LEDGER.json').write_text(json.dumps({'policy':{},'reservations':[{'state':'active'}]}))
                with self.assertRaisesRegex(r.ContainerRecoveryError,'reservations'): r._ledger_and_store_snapshot(SimpleNamespace(project='fullmag-master'),backend,retained_terminal_runs=[pin])

    def test_full_recover_v2_consumes_ready_proof_and_builds_v3_without_solve(self):
        """Exercise orchestration through start() with all external actions mocked."""
        import contextlib
        proof, auth, compose = self.fixture()
        selected = Path(__file__).resolve().parent.parent
        pins = proof['authorization_pins']
        pins['source_root'] = str(selected)
        b,f=proof['containers'].values()
        b['Config']['Env']=['FULLMAG_DOCKER_DEVICE_ACCESS=cpu']
        terminal_pins=[{'run_id':'completed','run_intent_sha256':'1'*64,'run_catalog_sha256':'2'*64,'artifact_catalog_sha256':None}]
        proof['retained_terminal_runs']=terminal_pins
        proof['storage_proof']={'store_root_sha256':'3'*64,'ledger_root_sha256':'4'*64,'ledger_snapshot_sha256':'5'*64,'run_records':terminal_pins}
        proof['docker_engine_id_sha256']=r._sha256(b'engine')
        operator={**pins,'schema_version':r.ABRUPT_OPERATOR_SCHEMA,'abrupt_stop_proof':'verification/abrupt-proof.json','abrupt_stop_proof_sha256':r._sha256(r._canonical(proof))}
        auth=r.validate_operator_authorization(operator)
        terminal={'phase':'development','attempt':pins['development_attempt'],'inputs':{'gpu_access_requested':'disabled'},'state_root':'/canonical/state'}
        documents={'operator.json':r._canonical(operator),auth['stop_journal_path']:r._canonical(proof),
                   f"development/attempts/{pins['development_attempt']}/terminal.json":r._canonical(terminal),
                   f"development/attempts/{pins['development_attempt']}/compose.json":r._canonical(compose)}
        documents.update({item['path']:item['raw_utf8'].encode() for item in proof['raw_records'].values()})
        @contextlib.contextmanager
        def operation(*args):
            yield {'receipt':{},'root':'operations/fake'}
        control=SimpleNamespace(project=compose['name'],prepare=lambda:None,operation=operation,write_bytes=lambda path,raw:documents.update({path:raw}))
        def read(control,path,*,optional=False):
            if path not in documents and not optional: self.fail('missing '+path)
            return documents.get(path)
        def read_json(control,path,*,optional=False):
            raw=read(control,path,optional=optional)
            return (json.loads(raw),raw) if raw else (None,None)
        def docker(*args,**kwargs):
            if args[0]=='rm': return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
            if args[:2]==('network','ls'): return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
            if args[:2]==('network','inspect'): return SimpleNamespace(returncode=1,stdout=b'',stderr=b'No such network')
            if args[0]=='inspect': return SimpleNamespace(returncode=1,stdout=b'',stderr=b'No such object')
            self.fail('unexpected Docker command '+str(args))
        device={'resource_id':'runtime-cpu','mapping_sha256':'6'*64,'mapping_detached':True}
        toolchain={'image_id':pins['old_image_id'],'inputs':{'build_args':{'FULLMAG_CUDA_BASE_IMAGE':'helper'}}}
        images={'backend':{'image_id':pins['old_image_id']}}
        args=SimpleNamespace(repo_root=selected,source_root=str(selected),recovery_authorization='operator.json',attempt=pins['development_attempt'])
        patches=[patch.object(r,'BuildControl',return_value=control),
            patch.object(r,'toolchain_configuration',return_value={'services':{'fem-gpu-toolchain':{'build':{'args':{'FULLMAG_CUDA_BASE_IMAGE':'helper'}}}}}),
            patch.object(r,'_control_bytes',side_effect=read),patch.object(r,'_control_json',side_effect=read_json),
            patch.object(r,'_inspect_pair',return_value=(b,f)),patch.object(r,'_abrupt_network',return_value=proof['network']),
            patch.object(r,'_assert_no_foreign_storage_consumers'),patch.object(r,'_ledger_and_store_snapshot',return_value=proof['storage_proof']),
            patch.object(r,'_docker_engine_sha',return_value=proof['docker_engine_id_sha256']),patch.object(r,'_docker_engine_id',return_value='engine'),
            patch.object(r,'_device_release_from_config',return_value=(device,{'kind':'cpu'})),
            patch.object(r,'_application_pin',return_value={'mode':'external_only','raw_sha256':pins['config_sha256']}),
            patch.object(r,'_validate_reused_session_before_removal',return_value={'state':'/canonical/state','host_certificate':{},'owner_marker':{}}),
            patch.object(r,'docker_capture',side_effect=docker),
            patch('docker_dev._select_source',return_value=(selected,{})),patch('docker_dev._compose_identity',return_value={'project_id':'project','worktree_id':'master','checkout_kind':'main'}),
            patch('docker_dev._resolve_gpu_access',return_value='cpu'),patch('docker_dev._verify_docker_gpu_access',return_value='cpu'),
            patch('docker_build_control.build_volume_toolchain',return_value=toolchain),patch('docker_build_control.build_volume_runtime_images',return_value=images),
            patch('docker_volume_dev._operator_probe_record_from_retained',return_value={})]
        with contextlib.ExitStack() as stack:
            for item in patches: stack.enter_context(item)
            start=stack.enter_context(patch('docker_volume_dev.start'))
            r.recover(args)
        start.assert_called_once()
        request=json.loads(documents[f"{r.RECOVERY_RELATIVE_ROOT}/{auth['request_id']}/request.json"])
        self.assertEqual(request['schema_version'],r.TERMINAL_REQUEST_SCHEMA)
        self.assertEqual(request['retained_terminal_runs'],terminal_pins)
        self.assertEqual(request['expected_owner']['state'],'ready')
        self.assertEqual(documents['runtime-control/runtime-service/process-tree.json'],proof['raw_records']['process_receipt']['raw_utf8'].encode())
        self.assertIsNone(start.call_args.args[0].script)
        self.assertTrue(any(path.endswith('/absence.json') for path in documents))

    def test_inspect_pair_checks_image_service_and_retained_config_before_no_bridge(self):
        proof,auth,compose=self.fixture(); b,f=proof['containers'].values()
        def inspect(*args,**kwargs):
            if args[:2]==('image','inspect'): return SimpleNamespace(stdout=b'[{"Config":{}}]')
            return SimpleNamespace(stdout=json.dumps([b,f]).encode())
        with patch.object(r,'docker_capture',side_effect=inspect),patch('docker_volume_dev._validate_retained_service') as service,patch.object(r,'_abrupt_network',return_value=proof['network']):
            self.assertEqual(r._inspect_pair(auth,compose['name'],compose),(b,f))
            self.assertEqual(service.call_count,2)
            b['Image']='sha256:'+'a'*64
            with self.assertRaisesRegex(r.ContainerRecoveryError,'ownership'):r._inspect_pair(auth,compose['name'],compose)
            b['Image']=auth['old_image_id']
            service.side_effect=ValueError('mount/config drift')
            with self.assertRaisesRegex(r.ContainerRecoveryError,'configuration'):r._inspect_pair(auth,compose['name'],compose)

if __name__=='__main__': unittest.main()
