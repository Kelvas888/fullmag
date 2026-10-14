"""Operational probes for one Docker-owned Windows session namespace."""
import errno
import fcntl
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path('/state')
HOST = Path('/run/fullmag/windows-folder-host.json')
CHECKS = ('file_sync', 'directory_sync', 'atomic_replace', 'atomic_directory_publish',
          'process_lock', 'no_follow_symlink', 'no_follow_junction',
          'sqlite_transactions', 'restart_readback')


def read_regular(path, limit=65536):
    import stat
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise RuntimeError('Attestation must be a regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError('Attestation is oversized')
        return data
    finally:
        os.close(fd)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(path, data):
    temporary = path.parent / ('.publish-' + uuid.uuid4().hex)
    with temporary.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    sync_dir(path.parent)


def nofollow(path):
    if not path.is_symlink():
        raise RuntimeError('Guest did not expose the probe link as a symlink')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            return
        raise
    os.close(fd)
    raise RuntimeError('No-follow opened the link target')


def run(require_restart):
    raw = read_regular(HOST)
    host = json.loads(raw)
    image = os.environ.get('FULLMAG_RUNTIME_IMAGE_ID')
    if (host['schema'] != 'fullmag.windows-folder-host.v1'
            or host['storage_profile'] != 'windows-folder-v1'
            or host['role'] != 'session' or host['owner_scope'] != 'docker-desktop-linux'
            or not host['host_root_no_reparse'] or host['host_drive_type'] != 3
            or host['host_filesystem'] not in ('NTFS', 'ReFS') or host['image_id'] != image
            or json.loads(read_regular(ROOT / '.fullmag-windows-folder-owner.json')) != host):
        raise RuntimeError('Invalid Windows host admission')
    if require_restart and host['restart_verified'] is not True:
        raise RuntimeError('Native host has not confirmed the restart readback')
    directory = ROOT / '.windows-folder-probe'
    payload = (host['owner_token'] + ':' + image).encode('ascii')
    sentinel = directory / 'restart-sentinel.bin'
    existed = sentinel.exists()
    if existed:
        if hashlib.sha256(read_regular(sentinel)).hexdigest() != host['restart_expected_sha256']:
            raise RuntimeError('Restart sentinel changed')
    elif require_restart:
        raise RuntimeError('Restart sentinel is missing')
    else:
        publish(sentinel, payload)
    checks = {key: False for key in CHECKS}
    publication = directory / 'publication.bin'
    publish(publication, payload)
    if read_regular(publication) != payload:
        raise RuntimeError('Atomic publication readback mismatch')
    checks.update(file_sync=True, directory_sync=True, atomic_replace=True)
    stage = directory / ('stage-' + uuid.uuid4().hex)
    stage.mkdir()
    publish(stage / 'payload', payload)
    final = directory / ('published-' + uuid.uuid4().hex)
    os.rename(stage, final)
    sync_dir(directory)
    if read_regular(final / 'payload') != payload:
        raise RuntimeError('Directory publication readback mismatch')
    checks['atomic_directory_publish'] = True
    with (directory / 'writer.lock').open('a+b') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code = ('import fcntl,sys; f=open(sys.argv[1],"a+b");\n'
                'try: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\n'
                'except BlockingIOError: sys.exit(0)\nelse: sys.exit(1)')
        result = subprocess.run([sys.executable, '-c', code, str(directory / 'writer.lock')], timeout=5)
        if result.returncode != 0:
            raise RuntimeError('Independent process acquired the held writer lock')
    checks['process_lock'] = True
    link = directory / 'posix-link'
    if not link.is_symlink():
        link.symlink_to('publication.bin')
    nofollow(link)
    nofollow(directory / 'host-junction')
    checks.update(no_follow_symlink=True, no_follow_junction=True)
    database = directory / 'transactions.sqlite'
    with sqlite3.connect(database) as connection:
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('CREATE TABLE IF NOT EXISTS probe (id TEXT PRIMARY KEY)')
        connection.execute('INSERT OR REPLACE INTO probe VALUES (?)', (host['owner_token'],))
        connection.commit()
        connection.execute('INSERT INTO probe VALUES (?)', ('rollback-' + uuid.uuid4().hex,))
        connection.rollback()
    with sqlite3.connect(database) as connection:
        if connection.execute('SELECT id FROM probe').fetchall() != [(host['owner_token'],)]:
            raise RuntimeError('SQLite committed/rolled-back state mismatch')
    checks.update(sqlite_transactions=True, restart_readback=existed)
    root_stat = ROOT.stat()
    grant = {'schema': 'fullmag.windows-folder-session.v1', 'storage_profile': 'windows-folder-v1',
             'role': 'session', 'state': 'operational', 'container_root': '/state',
             'host_attestation_sha256': hashlib.sha256(raw).hexdigest(), 'owner_token': host['owner_token'],
             'root_device': root_stat.st_dev, 'root_inode': root_stat.st_ino,
             'mount_namespace_inode': os.stat('/proc/self/ns/mnt').st_ino,
             'power_loss': 'NOT VERIFIED', 'checks': checks}
    publish(directory / ('probe-restart.json' if existed else 'probe-first.json'),
            json.dumps(grant, indent=2).encode())
    if require_restart:
        if not all(checks.values()):
            raise RuntimeError('Windows storage operational probes did not pass')
        publish(ROOT / '.fullmag-windows-folder-grant.json', json.dumps(grant, indent=2).encode())
    return grant
