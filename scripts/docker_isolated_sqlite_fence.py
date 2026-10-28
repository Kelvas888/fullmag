"""Hold a read-only host proof and managed SQLite lock for a stopped DEV source.

The helper is attached only to the workspace database file. It acquires the
SQLite lock-page fence without connecting to SQLite or writing source bytes.
The caller must already have validated and pinned the stopped Compose group.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import errno
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import struct
import subprocess
import sys
import uuid

from docker_build_control import (
    BuildControlError,
    ControlOutcomeUnknown,
    docker_capture,
)
import docker_linux_host_readmission as retained
from docker_compose_identity import source_labels
from docker_dev_host import validate_host_path


_CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
_UINT32_MAX = (1 << 32) - 1
_UNCERTAIN_HELPERS: list[subprocess.Popen[bytes]] = []


def _require_posix_bind_source(source: str) -> str:
    """Reject values that cannot be passed unambiguously as Docker mount CSV."""
    if (not isinstance(source, str) or not source
            or any(ord(character) < 0x20 or ord(character) == 0x7f for character in source)
            or "\x00" in source
            or "," in source or "\\" in source):
        raise BuildControlError("SQLite helper bind source is not a safe POSIX path")
    path = PurePosixPath(source)
    if (not path.is_absolute() or source == "/" or ".." in path.parts or str(path) != source
            or source.startswith("//")):
        raise BuildControlError("SQLite helper bind source is not canonical")
    return source


def _mount_arguments(args: list[str], target: str) -> list[int]:
    found = []
    for index in range(len(args) - 1):
        if args[index] == "--mount":
            options = args[index + 1].split(",")
            if "dst=" + target in options:
                found.append(index)
    return found


def _managed_helper_args(control, script: str, *, name: str,
                         database_source: str, user: str,
                         group_add: tuple[int, ...],
                         database_read_only: bool) -> list[str]:
    """Build a helper invocation only from the selected BuildControl object."""
    database_source = _require_posix_bind_source(database_source)
    if (not isinstance(name, str)
            or re.fullmatch(r"fullmag-sqlite-fence-[0-9a-f]{32}", name) is None):
        raise BuildControlError("SQLite helper name is not a generated fence identity")
    if not isinstance(user, str) or re.fullmatch(r"[0-9]{1,10}:[0-9]{1,10}", user) is None:
        raise BuildControlError("SQLite helper user must be a numeric UID:GID pair")
    uid, gid = (int(part) for part in user.split(":"))
    if uid > _UINT32_MAX or gid > _UINT32_MAX:
        raise BuildControlError("SQLite helper UID or GID is out of range")
    if (not isinstance(group_add, tuple)
            or any(type(group) is not int or group < 0 or group > _UINT32_MAX
                   for group in group_add)
            or len(set(group_add)) != len(group_add)):
        raise BuildControlError("SQLite helper supplementary groups are invalid")
    if type(database_read_only) is not bool:
        raise BuildControlError("SQLite helper database mount mode is invalid")

    try:
        args = list(control.helper_args(script, name=name))
    except Exception as error:
        raise BuildControlError("Could not construct the managed SQLite helper") from error
    if "--cap-add" in args or "--group-add" in args:
        raise BuildControlError("Managed SQLite helper has an unexpected privilege option")
    control_mounts = _mount_arguments(args, "/control")
    if len(control_mounts) != 1:
        raise BuildControlError("Managed SQLite helper has no unique control mount")
    control_index = control_mounts[0]
    control_options = args[control_index + 1].split(",")
    if (control_options[0] != "type=volume" or "readonly" in control_options
            or "rw" in control_options):
        raise BuildControlError("Managed SQLite helper control mount differs")
    control_options.insert(3, "readonly")
    args[control_index + 1] = ",".join(control_options)

    if _mount_arguments(args, "/sqlite-source/workspace.db"):
        raise BuildControlError("Managed SQLite helper already has a database mount")
    try:
        entrypoint_index = args.index("--entrypoint")
        user_index = args.index("--user")
    except ValueError as error:
        raise BuildControlError("Managed SQLite helper arguments are incomplete") from error
    args[user_index + 1] = user
    if "--user" in args[user_index + 2:]:
        raise BuildControlError("Managed SQLite helper has duplicate user options")
    for group in group_add:
        args[user_index:user_index] = ["--group-add", str(group)]
        entrypoint_index += 2
    database_mode = ",readonly" if database_read_only else ""
    args[entrypoint_index:entrypoint_index] = [
        "--mount",
        "type=bind,src=" + database_source
        + ",dst=/sqlite-source/workspace.db" + database_mode,
    ]
    return args


def _expected_labels(control) -> dict[str, str]:
    return {
        "com.docker.compose.project": control.project,
        "com.docker.compose.service": "build-control",
        **control.labels,
        **source_labels(control.identity),
    }


def _strict_inspect_mapping(document, key: str) -> dict:
    value = document.get(key) if isinstance(document, dict) else None
    if not isinstance(value, dict):
        raise BuildControlError("SQLite helper inspect is missing " + key)
    return value


def _volume_mount_matches(mount: dict, *, control, target: str,
                          readonly: bool, subpath: str | None) -> bool:
    options = mount.get("VolumeOptions")
    return (
        mount.get("Type") == "volume"
        and mount.get("Source") == control.volume
        and mount.get("Target") == target
        and type(mount.get("ReadOnly")) is bool
        and mount.get("ReadOnly") is readonly
        and isinstance(options, dict)
        and options.get("NoCopy") is True
        and options.get("Subpath") == subpath
    )


def _validate_helper_inspection(*, control, document, name: str,
                                arguments: list[str], host_mount_source: str,
                                expected_daemon_source: str | None,
                                user: str, group_add: tuple[int, ...],
                                database_read_only: bool) -> str:
    """Authenticate the exact short-lived helper and all of its mount rights."""
    host_mount_source = _require_posix_bind_source(host_mount_source)
    if expected_daemon_source is not None:
        expected_daemon_source = _require_posix_bind_source(expected_daemon_source)
    config = _strict_inspect_mapping(document, "Config")
    state = _strict_inspect_mapping(document, "State")
    host_config = _strict_inspect_mapping(document, "HostConfig")
    identifier = document.get("Id") if isinstance(document, dict) else None
    labels = config.get("Labels")
    required_labels = _expected_labels(control)
    labels_match = (
        isinstance(labels, dict)
        and all(labels.get(key) == value for key, value in required_labels.items())
    )
    environment = config.get("Env")
    mounts = document.get("Mounts") if isinstance(document, dict) else None
    host_mounts = host_config.get("Mounts")
    if (not isinstance(identifier, str) or _CONTAINER_ID.fullmatch(identifier) is None
            or document.get("Name") != "/" + name
            or document.get("Image") != control.image
            or config.get("Image") != control.image
            or config.get("Cmd") != arguments[-4:]
            or config.get("Entrypoint") != ["/bin/bash"]
            or config.get("User") != user
            or not isinstance(environment, list)
            or environment.count("NVIDIA_VISIBLE_DEVICES=void") != 1
            or config.get("OpenStdin") is not True or config.get("Tty") is not False
            or not labels_match
            or state.get("Running") is not True
            or type(state.get("Pid")) is not int or state["Pid"] <= 0
            or host_config.get("NetworkMode") != "none"
            or host_config.get("Runtime") != "runc"
            or host_config.get("ReadonlyRootfs") is not True
            or type(host_config.get("PidsLimit")) is not int
            or host_config.get("PidsLimit") != 32
            or type(host_config.get("Memory")) is not int
            or host_config.get("Memory") != 64 * 1024 * 1024
            or type(host_config.get("NanoCpus")) is not int
            or host_config.get("NanoCpus") != 250_000_000
            or host_config.get("CapDrop") != ["ALL"]
            or host_config.get("CapAdd") not in (None, [])
            or host_config.get("SecurityOpt") != ["no-new-privileges:true"]
            or host_config.get("Privileged") is not False
            or host_config.get("AutoRemove") is not True
            or host_config.get("PidMode") not in (None, "", "private")
            or host_config.get("IpcMode") not in (None, "", "private")
            or host_config.get("UTSMode") not in (None, "", "private")
            or host_config.get("CgroupnsMode") not in (None, "", "private")
            or host_config.get("UsernsMode") not in (None, "", "private")
            or host_config.get("Binds") not in (None, [])
            or host_config.get("Tmpfs") not in (None, {})
            or host_config.get("VolumesFrom") not in (None, [])
            or host_config.get("Links") not in (None, [])
            or host_config.get("Devices") not in (None, [])
            or host_config.get("DeviceRequests") not in (None, [])
            or host_config.get("PortBindings") not in (None, {})
            or host_config.get("PublishAllPorts") is True
            or not isinstance(mounts, list) or not isinstance(host_mounts, list)):
        raise BuildControlError("SQLite helper does not match its exact managed identity")
    expected_groups = [str(group) for group in group_add]
    actual_groups = host_config.get("GroupAdd")
    if actual_groups is None:
        actual_groups = []
    if actual_groups != expected_groups:
        raise BuildControlError("SQLite helper supplementary groups differ")

    expected_targets = {"/control"}
    if control.namespace:
        expected_targets.add("/registry")
    expected_targets.add("/sqlite-source/workspace.db")
    if (len(mounts) != len(expected_targets)
            or len(host_mounts) != len(expected_targets)):
        raise BuildControlError("SQLite helper has an unexpected mount count")
    actual_by_target = {}
    for mount in mounts:
        if not isinstance(mount, dict):
            raise BuildControlError("SQLite helper mount record is malformed")
        target = mount.get("Destination")
        if not isinstance(target, str):
            raise BuildControlError("SQLite helper mount target is malformed")
        if target in actual_by_target:
            raise BuildControlError("SQLite helper mount target is duplicated")
        actual_by_target[target] = mount
    host_by_target = {}
    for mount in host_mounts:
        if not isinstance(mount, dict):
            raise BuildControlError("SQLite helper host mount record is malformed")
        target = mount.get("Target")
        if not isinstance(target, str):
            raise BuildControlError("SQLite helper host mount target is malformed")
        if target in host_by_target:
            raise BuildControlError("SQLite helper host mount target is duplicated")
        host_by_target[target] = mount
    if set(actual_by_target) != expected_targets or set(host_by_target) != expected_targets:
        raise BuildControlError("SQLite helper mount target set differs")

    control_subpath = control.namespace or None
    if (not _volume_mount_matches(host_by_target["/control"], control=control,
                                  target="/control", readonly=True,
                                  subpath=control_subpath)
            or actual_by_target["/control"].get("Type") != "volume"
            or actual_by_target["/control"].get("Name") != control.volume
            or actual_by_target["/control"].get("Destination") != "/control"
            or actual_by_target["/control"].get("RW") is not False):
        raise BuildControlError("SQLite helper control mount is not the exact read-only namespace")
    if control.namespace:
        if (not _volume_mount_matches(host_by_target["/registry"], control=control,
                                      target="/registry", readonly=True, subpath=None)
                or actual_by_target["/registry"].get("Type") != "volume"
                or actual_by_target["/registry"].get("Name") != control.volume
                or actual_by_target["/registry"].get("Destination") != "/registry"
                or actual_by_target["/registry"].get("RW") is not False):
            raise BuildControlError("SQLite helper registry mount is not read-only")

    host_db = host_by_target["/sqlite-source/workspace.db"]
    actual_db = actual_by_target["/sqlite-source/workspace.db"]
    expected_read_only = database_read_only
    host_db_read_only = host_db.get("ReadOnly", False)
    host_database_source = host_db.get("Source")
    try:
        _require_posix_bind_source(host_database_source)
    except BuildControlError as error:
        raise BuildControlError("SQLite helper host database source is unsafe") from error
    if (host_db.get("Type") != "bind"
            or host_db.get("Target") != "/sqlite-source/workspace.db"
            or type(host_db_read_only) is not bool
            or host_db_read_only is not expected_read_only
            or host_db.get("VolumeOptions") not in (None, {})):
        raise BuildControlError("SQLite helper host database mount differs")
    actual_source = actual_db.get("Source")
    try:
        _require_posix_bind_source(actual_source)
    except BuildControlError as error:
        raise BuildControlError("SQLite helper daemon database source is unsafe") from error
    if expected_daemon_source is None:
        translated_probe_source = (
            database_read_only
            and host_database_source == actual_source
            and actual_source.startswith(retained._WSL_ALIAS_PREFIXES)
        )
        unchanged_probe_source = (
            database_read_only
            and host_database_source == host_mount_source
            and actual_source == host_mount_source
        )
        source_matches = translated_probe_source or unchanged_probe_source
    else:
        source_matches = (
            host_database_source == host_mount_source
            and actual_source == expected_daemon_source
        )
    if (actual_db.get("Type") != "bind"
            or actual_db.get("Destination") != "/sqlite-source/workspace.db"
            or actual_db.get("RW") is not (not expected_read_only)
            or not source_matches):
        raise BuildControlError("SQLite helper daemon database mount differs")
    return identifier


def _database_daemon_source(document: dict) -> str:
    mounts = document.get("Mounts") if isinstance(document, dict) else None
    selected = [item for item in mounts if isinstance(item, dict)
                and item.get("Destination") == "/sqlite-source/workspace.db"] \
        if isinstance(mounts, list) else []
    if len(selected) != 1 or selected[0].get("Type") != "bind":
        raise BuildControlError("SQLite helper has no unique database bind source")
    return _require_posix_bind_source(selected[0].get("Source"))


def _json_ack(line: str, expected_state: str) -> dict:
    try:
        value = json.loads(line)
    except (json.JSONDecodeError, TypeError) as error:
        raise BuildControlError("SQLite helper acknowledgement is malformed") from error
    if not isinstance(value, dict) or value.get("state") != expected_state:
        raise BuildControlError("SQLite helper acknowledgement has the wrong state")
    return value


def _bounded_uint(value, label: str) -> int:
    if type(value) is not int or value < 0 or value > _UINT32_MAX:
        raise BuildControlError("SQLite helper reported an invalid " + label)
    return value


def _metadata_ack(value: dict, *, owner: bool) -> dict[str, int]:
    result = {
        "device": value.get("device"),
        "inode": value.get("inode"),
        "size": value.get("size"),
    }
    if any(type(item) is not int or item < 0 for item in result.values()):
        raise BuildControlError("SQLite helper metadata acknowledgement is incomplete")
    if owner:
        result["uid"] = _bounded_uint(value.get("uid"), "database UID")
        result["gid"] = _bounded_uint(value.get("gid"), "database GID")
        mode = value.get("mode")
        if type(mode) is not int or mode < 0 or mode > 0o7777:
            raise BuildControlError("SQLite helper reported an invalid database mode")
        result["mode"] = mode
        if type(value.get("links")) is not int or value["links"] != 1:
            raise BuildControlError("SQLite helper database is linked or not regular")
        if value.get("regular") is not True:
            raise BuildControlError("SQLite helper database is not a regular file")
        if mode & 0o600 != 0o600:
            raise BuildControlError("SQLite owner lacks read/write permission for the database")
    return result


def _probe_script() -> str:
    code = r'''import json, os, stat, sys
path = "/sqlite-source/workspace.db"
info = os.lstat(path)
if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
    raise RuntimeError("workspace database is linked or not regular")
record = {"state":"READY", "device":info.st_dev, "inode":info.st_ino,
          "size":info.st_size, "uid":info.st_uid, "gid":info.st_gid,
          "mode":stat.S_IMODE(info.st_mode), "links":info.st_nlink,
          "regular":True}
print(json.dumps(record, sort_keys=True, separators=(",", ":")), flush=True)
sys.stdin.buffer.read()
after = os.lstat(path)
if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
        info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns):
    raise RuntimeError("workspace database changed during the metadata probe")
print(json.dumps({"state":"RELEASED"}, separators=(",", ":")), flush=True)
'''
    return "python3 -B -c " + shlex.quote(code)


def _sqlite_module_source() -> str:
    """Read the reviewed Linux fence implementation for embedding in a helper."""
    path = Path(__file__).with_name("docker_isolated_sqlite_snapshot.py")
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_size > 128 * 1024):
            raise BuildControlError("SQLite lock module is not a bounded regular file")
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino, opened.st_size) != (
                    info.st_dev, info.st_ino, info.st_size):
                raise BuildControlError("SQLite lock module changed while opening")
            raw = os.read(fd, 128 * 1024 + 1)
        finally:
            os.close(fd)
    except OSError as error:
        raise BuildControlError("Could not read the SQLite lock module") from error
    if len(raw) != info.st_size or len(raw) > 128 * 1024:
        raise BuildControlError("SQLite lock module exceeded its read bound")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BuildControlError("SQLite lock module is not UTF-8") from error


def _owner_script() -> str:
    code = _sqlite_module_source() + r'''
import json, os, sys
with hold_workspace_database(Path("/sqlite-source")):
    info = os.stat("/sqlite-source/workspace.db", follow_symlinks=False)
    print(json.dumps({"state":"READY", "device":info.st_dev,
                      "inode":info.st_ino, "size":info.st_size},
                     sort_keys=True, separators=(",", ":")), flush=True)
    sys.stdin.buffer.read()
print(json.dumps({"state":"RELEASED"}, separators=(",", ":")), flush=True)
'''
    return "python3 -B -c " + shlex.quote(code)


def _retain_uncertain(process: subprocess.Popen[bytes]) -> None:
    if all(existing is not process for existing in _UNCERTAIN_HELPERS):
        _UNCERTAIN_HELPERS.append(process)


def _helper_label(process) -> str:
    name = getattr(process, "_fullmag_helper_name", "unknown-name")
    identifier = getattr(process, "_fullmag_helper_id", None)
    return name + (" (container ID " + identifier + ")" if identifier else "")


def _inspect_helper(control, process, name: str, args: list[str], *,
                    requested_source: str, expected_daemon_source: str | None,
                    user: str, group_add: tuple[int, ...],
                    database_read_only: bool) -> tuple[str, dict]:
    if process.poll() is not None:
        raise BuildControlError("SQLite helper exited before inspection")
    try:
        raw = docker_capture("inspect", name, timeout=30).stdout
        documents = json.loads(raw)
    except Exception as error:
        raise ControlOutcomeUnknown(
            "SQLite helper inspection failed for " + _helper_label(process)
            + "; helper resources are retained") from error
    if not isinstance(documents, list) or len(documents) != 1:
        raise ControlOutcomeUnknown(
            "SQLite helper identity is ambiguous for " + _helper_label(process)
            + "; helper resources are retained")
    document = documents[0]
    candidate_id = document.get("Id") if isinstance(document, dict) else None
    if isinstance(candidate_id, str) and _CONTAINER_ID.fullmatch(candidate_id):
        process._fullmag_helper_id = candidate_id
    try:
        identifier = _validate_helper_inspection(
            control=control, document=document, name=name, arguments=args,
            host_mount_source=requested_source,
            expected_daemon_source=expected_daemon_source, user=user,
            group_add=group_add, database_read_only=database_read_only,
        )
    except Exception as error:
        raise ControlOutcomeUnknown(
            "SQLite helper identity or mount policy differs for " + _helper_label(process)
            + "; helper resources are retained") from error
    process._fullmag_helper_id = identifier
    return identifier, document


def _start_helper(control, script: str, *, database_source: str, user: str,
                  group_add: tuple[int, ...], database_read_only: bool):
    name = "fullmag-sqlite-fence-" + uuid.uuid4().hex
    args = _managed_helper_args(
        control, script, name=name, database_source=database_source,
        user=user, group_add=group_add,
        database_read_only=database_read_only,
    )
    try:
        process = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0,
        )
    except OSError as error:
        raise BuildControlError("Could not start the managed SQLite helper") from error
    process._fullmag_helper_name = name
    try:
        line = retained._readline(process, timeout=90)
        ready = _json_ack(line, "READY")
        _, document = _inspect_helper(
            control, process, name, args, requested_source=database_source,
            expected_daemon_source=None, user=user, group_add=group_add,
            database_read_only=database_read_only,
        )
    except Exception as error:
        if process.poll() is None:
            _retain_uncertain(process)
            if isinstance(error, ControlOutcomeUnknown):
                raise
            raise ControlOutcomeUnknown(
                "SQLite helper did not produce an authenticated READY state for "
                + _helper_label(process) + "; resources are retained") from error
        raise
    return process, name, args, ready, document


def _release_helper(process, *, expected_state: str = "RELEASED") -> None:
    try:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        line = retained._readline(process, timeout=30)
        _json_ack(line, expected_state)
        code = process.wait(timeout=30)
        if code != 0:
            raise ControlOutcomeUnknown(
                "SQLite helper exited unsuccessfully after release for "
                + _helper_label(process) + "; resources need inspection")
    except Exception as error:
        _retain_uncertain(process)
        if isinstance(error, ControlOutcomeUnknown):
            raise
        raise ControlOutcomeUnknown(
            "SQLite helper release was not confirmed for " + _helper_label(process)
            + "; resources are retained") from error


def _lstat_optional(path: Path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _validate_host_database(root: Path):
    database = root / "workspace.db"
    database_info = _lstat_optional(database)
    journal_info = _lstat_optional(root / "workspace.db-journal")
    wal_info = _lstat_optional(root / "workspace.db-wal")
    shm_info = _lstat_optional(root / "workspace.db-shm")
    if journal_info is not None:
        raise BuildControlError("Workspace rollback journal requires separate recovery")
    if wal_info is not None and shm_info is None:
        raise BuildControlError("Workspace WAL without its lock file is unsupported")
    for label, info in (("WAL", wal_info), ("SHM", shm_info)):
        if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
            raise BuildControlError("Workspace " + label + " sidecar is linked or not regular")
    if database_info is not None and (
            not stat.S_ISREG(database_info.st_mode) or database_info.st_nlink != 1):
        raise BuildControlError("Workspace database is linked or not regular")
    if database_info is None and (wal_info is not None or shm_info is not None):
        raise BuildControlError("Workspace SQLite sidecars exist without the database")
    return database, database_info


def _host_fingerprint(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
        info.st_ctime_ns, stat.S_IMODE(info.st_mode), info.st_nlink,
    )


def _validate_probe_host_identity(metadata: dict[str, int], host_info: os.stat_result) -> None:
    if (metadata["device"], metadata["inode"], metadata["size"]) != (
            host_info.st_dev, host_info.st_ino, host_info.st_size):
        raise BuildControlError("Read-only probe and host identify different database files")


def _assert_host_identity(database: Path, fd: int,
                          expected: tuple[int, int, int, int, int, int, int]) -> None:
    descriptor_info = os.fstat(fd)
    path_info = database.lstat()
    if (not stat.S_ISREG(path_info.st_mode) or path_info.st_nlink != 1
            or _host_fingerprint(descriptor_info) != expected
            or _host_fingerprint(path_info) != expected):
        raise BuildControlError("Workspace database identity or metadata changed while fenced")


def _prove_host_read_lock_conflict(fd: int) -> None:
    if not hasattr(fcntl, "F_OFD_SETLK"):
        raise BuildControlError("SQLite source fence requires Linux OFD locks")
    lock = struct.pack("@hhqqi4x", fcntl.F_RDLCK, os.SEEK_SET, 0x40000000, 512, 0)
    try:
        fcntl.fcntl(fd, fcntl.F_OFD_SETLK, lock)
    except OSError as error:
        if error.errno not in (errno.EAGAIN, errno.EACCES):
            raise BuildControlError("Host could not verify the SQLite lock conflict") from error
        return
    unlock = struct.pack("@hhqqi4x", fcntl.F_UNLCK, os.SEEK_SET, 0x40000000, 512, 0)
    fcntl.fcntl(fd, fcntl.F_OFD_SETLK, unlock)
    raise BuildControlError("Managed SQLite exclusive fence is not visible to the host")


def _validate_backend_source(control, backend) -> str:
    if not isinstance(backend, dict):
        raise BuildControlError("Pinned backend inspection is malformed")
    identifier = backend.get("Id")
    config = backend.get("Config")
    state = backend.get("State")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if (not isinstance(identifier, str) or _CONTAINER_ID.fullmatch(identifier) is None
            or not isinstance(state, dict) or state.get("Running") is not False
            or not isinstance(labels, dict)
            or labels.get("com.docker.compose.project") != control.project
            or labels.get("com.docker.compose.service") != "backend"
            or any(labels.get(key) != value
                   for key, value in source_labels(control.identity).items())):
        raise BuildControlError("Pinned backend is not the stopped selected project backend")
    mounts = backend.get("Mounts")
    selected = [item for item in mounts if isinstance(item, dict)
                and item.get("Destination") == "/user-data"] if isinstance(mounts, list) else []
    if (len(selected) != 1 or selected[0].get("Type") != "bind"
            or selected[0].get("RW") is not True):
        raise BuildControlError("Pinned backend has no unique writable user-data bind")
    return _require_posix_bind_source(selected[0].get("Source"))


def _python_helper_control(control, backend):
    """Reuse the stopped backend's immutable Python-capable image, without building."""
    image = backend.get("Image") if isinstance(backend, dict) else None
    if not isinstance(image, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None:
        raise BuildControlError("Pinned backend does not identify an immutable image")
    helper_control = copy.copy(control)
    helper_control.image = image
    return helper_control


def _canonical_user_data(user_data: Path) -> Path:
    path = Path(user_data)
    try:
        validated = validate_host_path(path, "retained workspace source")
        canonical = validated.resolve(strict=True)
    except (OSError, ValueError) as error:
        raise BuildControlError("Retained workspace source is not valid local storage") from error
    if canonical != validated or not canonical.is_dir():
        raise BuildControlError("Retained workspace source is not a canonical directory")
    return canonical


@contextmanager
def hold_managed_workspace_database(control, backend, user_data: Path):
    """Fence one stopped backend's workspace.db without changing source data.

    The caller must validate the stopped Compose pair and canonical declared
    storage root first. The yielded record is evidence only; the managed helper
    and host descriptor stay open until the context exits.
    """
    if not sys.platform.startswith("linux"):
        raise BuildControlError("Managed SQLite source fencing is Linux-only")
    _validate_backend_source(control, backend)
    helper_control = _python_helper_control(control, backend)
    root = _canonical_user_data(user_data)
    database, info = _validate_host_database(root)
    if info is None:
        yield {"database_present": False}
        return

    if not hasattr(fcntl, "F_OFD_SETLK"):
        raise BuildControlError("Managed SQLite source fencing requires Linux OFD locks")
    database_source = _require_posix_bind_source(str(database))
    # The fresh probe observes the daemon's actual alias for the canonical host
    # path. The owner fence reuses that exact inspect source after the probe exits.
    probe_process, probe_name, probe_args, probe_line, probe_document = _start_helper(
        helper_control, _probe_script(), database_source=database_source,
        user="65532:65532", group_add=(), database_read_only=True,
    )
    try:
        probe_metadata = _metadata_ack(probe_line, owner=True)
        daemon_source = _database_daemon_source(probe_document)
        _validate_helper_inspection(
            control=helper_control, document=probe_document, name=probe_name,
            arguments=probe_args, host_mount_source=daemon_source,
            expected_daemon_source=daemon_source, user="65532:65532",
            group_add=(), database_read_only=True,
        )
        _validate_probe_host_identity(probe_metadata, info)
        _validate_host_database(root)
    except Exception as error:
        _release_helper(probe_process)
        raise BuildControlError(
            "Metadata probe did not match the original host database for "
            + _helper_label(probe_process)) from error
    _release_helper(probe_process)

    uid = probe_metadata["uid"]
    gid = probe_metadata["gid"]
    owner_user = str(uid) + ":" + str(gid)
    owner_groups = () if gid == 65532 else (65532,)
    owner_process, owner_name, owner_args, owner_line, owner_document = _start_helper(
        helper_control, _owner_script(), database_source=daemon_source,
        user=owner_user, group_add=owner_groups, database_read_only=False,
    )
    try:
        owner_metadata = _metadata_ack(owner_line, owner=False)
    except Exception as error:
        _retain_uncertain(owner_process)
        raise ControlOutcomeUnknown(
            "Owner fence acknowledgement is invalid for " + _helper_label(owner_process)
            + "; helper resources are retained") from error
    host_fd = None
    try:
        _validate_helper_inspection(
            control=helper_control, document=owner_document, name=owner_name,
            arguments=owner_args, host_mount_source=daemon_source,
            expected_daemon_source=daemon_source, user=owner_user,
            group_add=owner_groups, database_read_only=False,
        )
        if (owner_metadata["device"], owner_metadata["inode"], owner_metadata["size"]) != (
                probe_metadata["device"], probe_metadata["inode"], probe_metadata["size"]):
            raise BuildControlError("Metadata probe and owner fence identify different database bytes")
        _validate_host_database(root)
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        host_fd = os.open(database, flags)
        host_info = os.fstat(host_fd)
        if (host_info.st_dev, host_info.st_ino, host_info.st_size) != (
                owner_metadata["device"], owner_metadata["inode"], owner_metadata["size"]):
            raise BuildControlError("Host and managed fence do not identify the same database file")
        expected_fingerprint = _host_fingerprint(host_info)
        _prove_host_read_lock_conflict(host_fd)
        _assert_host_identity(database, host_fd, expected_fingerprint)
        _validate_host_database(root)
        yield {
            "database_present": True,
            "device": host_info.st_dev,
            "inode": host_info.st_ino,
            "size": host_info.st_size,
            "owner_uid": uid,
            "owner_gid": gid,
            "fence": "managed-ofd-exclusive",
        }
        _assert_host_identity(database, host_fd, expected_fingerprint)
        _validate_host_database(root)
    except BaseException:
        # The authenticated helper has a simple EOF release protocol. If that
        # protocol cannot be confirmed, retain the process and do not kill it.
        _release_helper(owner_process)
        raise
    else:
        _release_helper(owner_process)
        _assert_host_identity(database, host_fd, expected_fingerprint)
        _validate_host_database(root)
    finally:
        if host_fd is not None:
            os.close(host_fd)
