"""Run bounded interpreted control regressions in the selected DEV backend."""
import argparse
import json
from pathlib import Path
import sys

import fullmag_storage as storage
from docker_build_control import BuildControl, BuildControlError, canonical, docker_capture
from docker_compose_identity import compose_project_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    selected = args.source_root.resolve(strict=True)
    identity = compose_project_identity(storage.resolve_layout(selected, 'docker-all-gpu'))
    from docker_build_control import toolchain_configuration
    configured = toolchain_configuration(selected, identity)
    helper = configured["services"]["fem-gpu-toolchain"]["build"]["args"]["FULLMAG_CUDA_BASE_IMAGE"]
    control = BuildControl(identity, helper)
    control.prepare()
    ids = docker_capture('ps', '--quiet', '--no-trunc', '--filter', 'label=com.docker.compose.project='+control.project,
                         '--filter', 'label=com.docker.compose.service=backend').stdout.decode().split()
    if len(ids) != 1:
        raise BuildControlError('Checks require one running selected backend')
    observed = json.loads(docker_capture('inspect', ids[0]).stdout)[0]
    labels = observed.get('Config', {}).get('Labels', {})
    if labels.get('org.fullmag.source.worktree-id') != identity['worktree_id']:
        raise BuildControlError('Backend worktree ownership differs')
    mounts = [m for m in observed.get('Mounts', []) if m['Destination']=='/build']
    if len(mounts)!=1 or mounts[0]['Type']!='volume':
        raise BuildControlError('Checks require the persistent build volume')
    script = '''import os, pathlib, subprocess, sys
pathlib.Path('/build/verification-tmp').mkdir(exist_ok=True)
environment = {key:value for key,value in os.environ.items() if not key.startswith('FULLMAG_')}
environment.update(TMPDIR='/build/verification-tmp', PYTHONDONTWRITEBYTECODE='1', HOME='/build/verification-tmp/home', USER='fullmag-checks', LOGNAME='fullmag-checks')
pathlib.Path(environment['HOME']).mkdir(exist_ok=True)
command=[sys.executable,'-B','-m','unittest','test_docker_backend_volume_cache','test_bootstrap_docker_toolchain','test_docker_compose_identity','test_docker_volume_receipts','test_docker_frontend_dev','test_docker_backend_dev','test_docker_startup_script','test_backend_volume_cache_maintenance','test_docker_cpu_access','test_docker_dev_storage','test_docker_dev_image_context','test_docker_dev_recreate','test_docker_frontend_cache','test_docker_frontend_cache_named_volume','test_fullmag_docker_runtime','test_docker_orphan_recovery','test_recover_docker_orphan']
sys.exit(subprocess.call(command,cwd='/opt/fullmag/source/scripts',env=environment))
'''
    result = docker_capture('exec', '--workdir', '/opt/fullmag/source/scripts', ids[0],
                           '/usr/local/bin/python3', '-B', '-c', script, allow_failure=True, timeout=180)
    receipt={'schema':'fullmag.volume-dev-interpreted-checks.v1','exit_code':result.returncode,
             'container_id':ids[0], 'image_id':observed['Image'], 'compose_project':control.project,
             'stdout':result.stdout.decode('utf-8','replace'), 'stderr':result.stderr.decode('utf-8','replace')}
    control.write('verification/interpreted-checks.json',receipt)
    print(receipt['stdout']+receipt['stderr'])
    return result.returncode


if __name__=='__main__':
    raise SystemExit(main())
