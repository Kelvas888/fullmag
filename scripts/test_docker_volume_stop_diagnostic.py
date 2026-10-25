"""Diagnostic stop preserves Unknown and authenticates the original Ready identity."""
import ast
import base64
import copy
import json
import unittest
from unittest.mock import patch

import docker_volume_stop_diagnostic as stop
from docker_build_control import BuildControlError
from test_docker_volume_stop_failed import ready_owner


class DiagnosticUnknownStopTests(unittest.TestCase):
    def fixture(self):
        ready=ready_owner()
        owner={**ready,'state':'unknown','heartbeat_at':'2026-10-25T14:00:00Z',
               'children':[{**c,'status':'exited_failure' if c['role']=='preparation' else 'running'} for c in ready['children']]}
        fence_path=stop.FENCE_PARENT+'/api-failure-'+'1'*32+'.json'
        process={'schema':'fullmag.docker-process-tree.v1','state':'failed_outcome_retained',
                 'api_pid':500,'api_diagnostic_only':True,'api_failure_fence':fence_path,'runtime_pid':None,
                 'service_owner':ready,'error':'runtime service owner observation failed during supervision: runtime service owner is not ready'}
        return owner,process

    def evidence(self,owner,process):
        config={'schema_version':'runtime_service_config.v2','target_id':'docker-all',
                'store_root':'/state/runs/docker-all/session-store'}
        fence={'schema':'fullmag.api-runtime-failure-fence.v1','stage':'runtime_supervision',
               'api_pid':process['api_pid'],'api_instance_id':'instance'}
        values={'runtime_config':config,'owner':owner,'process_receipt':process,'failure_fence':fence}
        raw={k:json.dumps(v,sort_keys=True).encode() for k,v in values.items()}
        paths={'runtime-control/runtime-service/docker-all.json':raw['runtime_config'],
               'runtime-control/runtime-services/OWNER.json':raw['owner'],
               'runtime-control/runtime-service/process-tree.json':raw['process_receipt'],
               stop._runtime_relative(process['api_failure_fence']):raw['failure_fence']}
        probe={k:base64.b64encode(v).decode() for k,v in raw.items()}
        probe.update(api_failure_fence=process['api_failure_fence'],api_instance_id='instance')
        with patch.object(stop,'_read_raw',side_effect=lambda control,path,**kw:paths[path]), \
             patch('docker_volume_unclaimed_cancellation._control_raw',return_value=None):
            return stop._probe_evidence(object(),'development/attempts/'+'a'*32,probe)

    def test_host_check_keeps_unknown_and_original_ready_bytes(self):
        owner,process=self.fixture();before=copy.deepcopy((owner,process))
        result=self.evidence(owner,process)
        self.assertEqual(result['failed_owner'],owner)
        self.assertEqual(result['failed_owner']['state'],'unknown')
        self.assertEqual(result['ready_owner'],process['service_owner'])
        self.assertEqual((owner,process),before)

    def test_drift_or_unfenced_api_is_refused(self):
        for field,value in [('owner_token','other'),('pid',999),('state','ready')]:
            owner,process=self.fixture();owner[field]=value
            with self.subTest(field=field),self.assertRaises(BuildControlError):self.evidence(owner,process)
        for field,value in [('api_diagnostic_only',False),('runtime_pid',123),('api_exit_code',0),('error','different')]:
            owner,process=self.fixture();process[field]=value
            with self.subTest(field=field),self.assertRaises(BuildControlError):self.evidence(owner,process)

    def test_serialized_guest_uses_the_same_identity_check(self):
        tree=ast.parse(stop._probe_script())
        branch=next(n for n in tree.body if isinstance(n,ast.If) and "owner.get('state') == 'unknown'" in ast.unparse(n.test))
        functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'require','validate_diagnostic_build'}]
        module=ast.fix_missing_locations(ast.Module(body=[*functions,branch],type_ignores=[]))
        owner,process=self.fixture();scope={'owner':owner,'process':process}
        exec(compile(module,'guest-owner-check','exec'),scope)
        self.assertEqual(owner['state'],'unknown')
        scope['owner']={**owner,'owner_token':'other'}
        with self.assertRaises(ValueError):exec(compile(module,'guest-owner-check','exec'),scope)


if __name__=='__main__':unittest.main()
