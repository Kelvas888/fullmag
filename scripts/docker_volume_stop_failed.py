"""Stop one pinned DEV supervisor only after failed admission reaped its API."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import fullmag_storage as storage
from docker_build_control import BuildControl, BuildControlError, docker_capture
from docker_compose_identity import compose_project_identity, validate_source_labels


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--container-id',required=True)
    parser.add_argument('--image-id',required=True)
    parser.add_argument('--process-receipt-sha256',required=True)
    args=parser.parse_args()
    if not re.fullmatch('[0-9a-f]{64}',args.container_id) or not re.fullmatch('sha256:[0-9a-f]{64}',args.image_id) or not re.fullmatch('[0-9a-f]{64}',args.process_receipt_sha256):
        raise BuildControlError('Stop requires complete immutable container/image/receipt identities')
    selected=args.source_root.resolve(strict=True)
    identity=compose_project_identity(storage.resolve_layout(selected,'docker-all-gpu'))
    actual=json.loads(docker_capture('inspect',args.container_id).stdout)
    if len(actual)!=1 or actual[0].get('Id')!=args.container_id or actual[0].get('Image')!=args.image_id:
        raise BuildControlError('Pinned backend identity differs')
    actual=actual[0]
    validate_source_labels(actual,identity)
    labels=actual.get('Config',{}).get('Labels',{})
    if labels.get('com.docker.compose.project')!=identity['project_name'] or labels.get('com.docker.compose.service')!='backend' or not actual.get('State',{}).get('Running'):
        raise BuildControlError('Stop requires this exact running DEV backend')
    logs = docker_capture('logs','--since',actual['State']['StartedAt'],'--tail','100',args.container_id).stdout.decode('utf-8','replace')
    if 'Startup or runtime failed; admission closed:' not in logs:
        raise BuildControlError('This backend incarnation has no confirmed failed-admission event')
    script='''import hashlib,json,pathlib,sys,os
sys.path.insert(0,'/opt/fullmag')
import runtime_service
raw=runtime_service._bounded_regular(pathlib.Path('/state/.fullmag/runtime-service/process-tree.json'),'failed process receipt')
document=json.loads(raw)
pid=document.get('api_pid')
print(json.dumps({'sha256':hashlib.sha256(raw).hexdigest(),'receipt':document,'api_pid_exists':bool(pid and os.path.exists('/proc/'+str(pid)))}))
'''
    observed=json.loads(docker_capture('exec',args.container_id,'/usr/local/bin/python3','-B','-c',script).stdout)
    receipt=observed['receipt']
    if (observed['sha256']!=args.process_receipt_sha256 or observed['api_pid_exists']
            or receipt.get('schema')!='fullmag.docker-process-tree.v1'
            or receipt.get('state')!='failed_outcome_retained'
            or not isinstance(receipt.get('api_exit_code'),int) or receipt.get('runtime_pid') is not None
            or not receipt.get('error','').startswith('API binding did not become ready:')):
        raise BuildControlError('Failed admission is not proven; no process will be stopped')
    from docker_build_control import toolchain_configuration
    config=toolchain_configuration(selected,identity)
    control=BuildControl(identity,config['services']['fem-gpu-toolchain']['build']['args']['FULLMAG_CUDA_BASE_IMAGE'])
    journal={'schema':'fullmag.stop-failed-admission.v1','state':'stopping-confirmed-failed-supervisor',
             'container_id':args.container_id,'image_id':args.image_id,'failure_receipt':observed}
    path='verification/stop-failed-'+args.container_id+'.json'
    control.write(path,journal)
    docker_capture('stop','--time','60',args.container_id,timeout=90)
    after=json.loads(docker_capture('inspect',args.container_id).stdout)[0]
    if after.get('State',{}).get('Running'):
        raise BuildControlError('Failed supervisor is still running; no retry was attempted')
    journal.update(state='stopped-confirmed',exit_code=after['State']['ExitCode'])
    control.write(path,journal)
    print(json.dumps({'state':journal['state'],'container_id':args.container_id}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
