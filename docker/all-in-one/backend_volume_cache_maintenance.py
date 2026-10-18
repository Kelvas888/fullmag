"""Initialize and prove the two Docker-VM backend cache volumes.

The process is intentionally a tiny guest-side helper. It never resolves a
Docker volume to a host path and never talks to the Docker socket. The
maintenance Compose service runs it as root with only ``CAP_CHOWN`` so that a
fresh named volume can be handed to the unprivileged backend user (65532).
Existing marker contents are immutable: a foreign or malformed marker fails
closed instead of being replaced.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Iterator, Mapping

SCHEMA = "fullmag.backend-build-cache.v2"
OWNER_SCHEMA = "fullmag.backend-build-cache-owner.v2"
PROBE_SCHEMA = "fullmag.backend-build-cache-probe.v2"
RECEIPT_SCHEMA = "fullmag.backend-build-cache-maintenance.v2"
PROFILE = "backend-build-cache-v2"
MAINTENANCE_PROFILE = "backend-build-cache-v2-maintenance"
BUILD_ROLE = "build"
PACKAGE_ROLE = "package"
BUILD_ROOT = "/build"
PACKAGE_ROOT = "/opt/fullmag/package"
MARKER_NAME = ".fullmag-backend-cache-owner.json"
READBACK_NAME = ".fullmag-backend-cache-readback"
DEFAULT_OWNER_UID = 65532
DEFAULT_OWNER_GID = 65532
MAX_MARKER_BYTES = 16 * 1024
MAX_READBACK_BYTES = 16 * 1024

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


class MaintenanceError(RuntimeError):
    """The guest cache pair could not be proven exact and writable."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _read_bounded(descriptor: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = os.read(descriptor, min(4096, limit + 1 - size))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        size += len(chunk)
        if size > limit:
            raise MaintenanceError("cache maintenance record exceeds its bounded size")


def _chown_record(directory: int, name: str, uid: int, gid: int) -> None:
    """Change one known record without following a reparse/symlink entry."""

    try:
        os.chown(name, uid, gid, dir_fd=directory, follow_symlinks=False)
    except OSError as error:
        raise MaintenanceError(f"cannot set cache maintenance record owner: {name}") from error


@contextmanager
def _open_maintenance_record(
    directory: int, name: str, flags: int
) -> Iterator[tuple[int, os.stat_result]]:
    """Open a record while retaining access with CAP_CHOWN only.

    After the first run the directory and records belong to UID 65532. A
    maintenance process with only CAP_CHOWN cannot read a 0640/0600 record as
    UID 0. It can, however, temporarily change the owner of this exact,
    no-follow regular entry. The original owner is restored before the
    descriptor is released. This keeps the backend file modes narrow and does
    not grant DAC_OVERRIDE or SETUID.
    """

    try:
        original = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise MaintenanceError(f"cannot inspect cache maintenance record: {name}") from error
    if stat.S_ISLNK(original.st_mode) or not stat.S_ISREG(original.st_mode):
        raise MaintenanceError(f"cache maintenance record is not regular: {name}")

    original_owner = (original.st_uid, original.st_gid)
    changed_owner = False
    descriptor: int | None = None
    restoration_error: MaintenanceError | None = None
    try:
        if os.geteuid() == 0 and original_owner != (0, 0):
            _chown_record(directory, name, 0, 0)
            changed_owner = True
        try:
            descriptor = os.open(name, flags | _O_NOFOLLOW, dir_fd=directory)
        except OSError as error:
            raise MaintenanceError(f"cannot open cache maintenance record: {name}") from error
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode)
                or (metadata.st_dev, metadata.st_ino)
                != (original.st_dev, original.st_ino)):
            raise MaintenanceError(f"cache maintenance record changed during open: {name}")
        yield descriptor, original
    finally:
        if changed_owner:
            try:
                _chown_record(directory, name, *original_owner)
            except MaintenanceError as error:
                restoration_error = error
        if descriptor is not None:
            try:
                if changed_owner and restoration_error is None:
                    os.fsync(descriptor)
            except OSError as error:
                restoration_error = MaintenanceError(
                    f"cache maintenance record sync failed: {name}"
                )
                restoration_error.__cause__ = error
            finally:
                os.close(descriptor)
        if restoration_error is not None:
            raise restoration_error


def _read_record(directory: int, name: str, limit: int) -> tuple[Any, os.stat_result]:
    try:
        with _open_maintenance_record(directory, name, os.O_RDONLY) as (descriptor, metadata):
            raw = _read_bounded(descriptor, limit)
    except FileNotFoundError:
        raise
    except MaintenanceError:
        raise
    except OSError as error:
        raise MaintenanceError(f"cannot open cache maintenance record: {name}") from error
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise MaintenanceError(f"cache maintenance record has duplicate key: {name}")
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MaintenanceError(f"cache maintenance record is invalid JSON: {name}") from error
    return value, metadata


def _open_guest_root(path: str | os.PathLike[str], uid: int, gid: int) -> int:
    candidate = Path(path)
    if (not candidate.is_absolute()
            or candidate == Path(candidate.anchor)
            or any(part in {"", ".", ".."} for part in candidate.parts[1:])):
        raise MaintenanceError("cache maintenance root is not a safe absolute guest path")
    try:
        directory = os.open(str(candidate), os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW)
    except OSError as error:
        raise MaintenanceError(f"cache maintenance root is unavailable: {candidate}") from error
    try:
        metadata = os.fstat(directory)
        if not stat.S_ISDIR(metadata.st_mode):
            raise MaintenanceError("cache maintenance root is not a directory")
        owner = (metadata.st_uid, metadata.st_gid)
        if owner not in {(0, 0), (uid, gid)}:
            raise MaintenanceError("cache maintenance root has a foreign owner")
        if os.geteuid() == 0 and owner == (uid, gid):
            # Keep the directory writable while records are opened. The final
            # ownership transfer happens only after all record checks pass.
            try:
                os.fchown(directory, 0, 0)
            except OSError as error:
                raise MaintenanceError("CAP_CHOWN could not prepare cache root") from error
            metadata = os.fstat(directory)
            if (metadata.st_uid, metadata.st_gid) != (0, 0):
                raise MaintenanceError("cache maintenance root ownership did not read back")
    except BaseException:
        os.close(directory)
        raise
    return directory


def _write_new_record(directory: int, name: str, value: Mapping[str, Any], uid: int, gid: int) -> None:
    raw = _canonical(value) + b"\n"
    if len(raw) > MAX_MARKER_BYTES:
        raise MaintenanceError("cache maintenance marker is too large")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, 0o640, dir_fd=directory)
    except FileExistsError as error:
        raise MaintenanceError("cache maintenance marker appeared concurrently") from error
    except OSError as error:
        raise MaintenanceError(f"cannot create cache maintenance marker: {name}") from error
    try:
        if os.geteuid() == 0:
            os.fchown(descriptor, uid, gid)
        elif (os.geteuid(), os.getegid()) != (uid, gid):
            raise MaintenanceError("unprivileged maintenance process has the wrong owner")
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise MaintenanceError("short write while creating cache maintenance marker")
            offset += written
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (metadata.st_uid, metadata.st_gid) != (uid, gid):
            raise MaintenanceError("cache maintenance marker ownership did not read back")
    finally:
        os.close(descriptor)


def _ensure_marker(
    directory: int, marker: Mapping[str, Any], uid: int, gid: int
) -> bytes:
    try:
        existing, metadata = _read_record(directory, MARKER_NAME, MAX_MARKER_BYTES)
    except FileNotFoundError:
        _write_new_record(directory, MARKER_NAME, marker, uid, gid)
        existing, metadata = _read_record(directory, MARKER_NAME, MAX_MARKER_BYTES)
    if existing != dict(marker):
        raise MaintenanceError("cache maintenance marker is foreign or incomplete")
    if (metadata.st_uid, metadata.st_gid) != (uid, gid):
        if (metadata.st_uid, metadata.st_gid) != (0, 0) or os.geteuid() != 0:
            raise MaintenanceError("cache maintenance marker owner is not exact")
        # Recover an interrupted ownership handoff without changing content.
        original_metadata = metadata
        _chown_record(directory, MARKER_NAME, uid, gid)
        recovered = os.stat(MARKER_NAME, dir_fd=directory, follow_symlinks=False)
        if (recovered.st_dev, recovered.st_ino) != (
            original_metadata.st_dev,
            original_metadata.st_ino,
        ):
            raise MaintenanceError("cache maintenance marker changed during owner recovery")
        metadata = recovered
        if (metadata.st_uid, metadata.st_gid) != (uid, gid):
            raise MaintenanceError("cache maintenance marker owner did not recover")
    raw = _canonical(existing)
    if len(raw) > MAX_MARKER_BYTES:
        raise MaintenanceError("cache maintenance marker is too large")
    return raw


def _prepare_readback(directory: int, uid: int, gid: int) -> None:
    try:
        with _open_maintenance_record(directory, READBACK_NAME, os.O_RDONLY) as (
            descriptor,
            metadata,
        ):
            if not stat.S_ISREG(metadata.st_mode):
                raise MaintenanceError("cache maintenance readback is not regular")
    except FileNotFoundError:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW
        try:
            descriptor = os.open(READBACK_NAME, flags, 0o600, dir_fd=directory)
        except OSError as error:
            raise MaintenanceError("cannot create cache maintenance readback") from error
        try:
            if os.geteuid() == 0:
                os.fchown(descriptor, uid, gid)
            elif (os.geteuid(), os.getegid()) != (uid, gid):
                raise MaintenanceError("unprivileged maintenance process has the wrong owner")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return
    except OSError as error:
        raise MaintenanceError("cache maintenance readback is not safely openable") from error
    if (metadata.st_uid, metadata.st_gid) != (uid, gid):
        if (metadata.st_uid, metadata.st_gid) != (0, 0) or os.geteuid() != 0:
            raise MaintenanceError("cache maintenance readback owner is foreign")
        original_metadata = metadata
        _chown_record(directory, READBACK_NAME, uid, gid)
        recovered = os.stat(READBACK_NAME, dir_fd=directory, follow_symlinks=False)
        if (recovered.st_dev, recovered.st_ino) != (
            original_metadata.st_dev,
            original_metadata.st_ino,
        ):
            raise MaintenanceError("cache maintenance readback changed during owner recovery")
        metadata = recovered
        if (metadata.st_uid, metadata.st_gid) != (uid, gid):
            raise MaintenanceError("cache maintenance readback owner did not recover")


def _probe_readback(
    directory: int, marker_raw: bytes, uid: int, gid: int
) -> None:
    """Write/read a bounded probe through the CAP_CHOWN record handoff.

    The maintenance service deliberately has only ``CAP_CHOWN``. It therefore
    cannot safely impersonate UID 65532 (that would require SETUID/SETGID).
    Ownership, owner-mode bits, O_NOFOLLOW, and a bounded readback are the
    proof available in this service; the backend container later runs with the
    exact owner UID and the directory is handed off only after this probe.
    """

    root_metadata = os.fstat(directory)
    root_mode = stat.S_IMODE(root_metadata.st_mode)
    if ((root_metadata.st_uid, root_metadata.st_gid) not in {(0, 0), (uid, gid)}
            or (root_mode & stat.S_IRWXU) != stat.S_IRWXU):
        raise MaintenanceError("cache maintenance root is not writable by backend owner")
    token = b"fullmag-cache-readback:" + hashlib.sha256(marker_raw).hexdigest().encode("ascii")

    def run() -> None:
        flags = os.O_WRONLY | os.O_TRUNC
        with _open_maintenance_record(directory, READBACK_NAME, flags) as (descriptor, _):
            offset = 0
            while offset < len(token):
                written = os.write(descriptor, token[offset:])
                if written <= 0:
                    raise MaintenanceError("short write during cache maintenance readback")
                offset += written
            os.fsync(descriptor)
        with _open_maintenance_record(directory, READBACK_NAME, os.O_RDONLY) as (descriptor, _):
            if _read_bounded(descriptor, MAX_READBACK_BYTES) != token:
                raise MaintenanceError("cache maintenance readback changed during reopen")
        with _open_maintenance_record(directory, MARKER_NAME, os.O_RDONLY) as (descriptor, _):
            if _read_bounded(descriptor, MAX_MARKER_BYTES).rstrip(b"\n") != marker_raw:
                raise MaintenanceError("cache maintenance marker failed user readback")

    run()


def _finalize_guest_root(directory: int, uid: int, gid: int) -> None:
    """Persist records, then hand the directory to the backend user last."""

    metadata = os.fstat(directory)
    mode = stat.S_IMODE(metadata.st_mode)
    if (metadata.st_uid, metadata.st_gid) not in {(0, 0), (uid, gid)}:
        raise MaintenanceError("cache maintenance root has a foreign owner")
    if (mode & stat.S_IRWXU) != stat.S_IRWXU:
        raise MaintenanceError("cache maintenance root is not writable by backend owner")
    if os.geteuid() == 0:
        # Others need only read/execute so the next CAP_CHOWN-only maintenance
        # process can reopen the directory before taking record ownership.
        required_mode = stat.S_IRWXU | stat.S_IROTH | stat.S_IXOTH
        if mode & required_mode != required_mode:
            try:
                os.fchmod(directory, mode | required_mode)
            except OSError as error:
                raise MaintenanceError(
                    "cache maintenance root mode could not be prepared"
                ) from error
        try:
            os.fsync(directory)
            if (metadata.st_uid, metadata.st_gid) != (uid, gid):
                os.fchown(directory, uid, gid)
            metadata = os.fstat(directory)
            if (metadata.st_uid, metadata.st_gid) != (uid, gid):
                raise MaintenanceError("cache maintenance root ownership did not read back")
            os.fsync(directory)
        except OSError as error:
            raise MaintenanceError("cache maintenance root handoff failed") from error
    elif (metadata.st_uid, metadata.st_gid) != (uid, gid):
        raise MaintenanceError("unprivileged maintenance root owner is not exact")
    try:
        os.fsync(directory)
    except OSError as error:
        raise MaintenanceError("cache maintenance directory sync failed") from error


def _record_environment(environment: Mapping[str, str]) -> dict[str, Any]:
    def required(name: str) -> str:
        value = environment.get(name)
        if not isinstance(value, str) or not value:
            raise MaintenanceError(f"cache maintenance environment is missing {name}")
        return value

    if required("FULLMAG_BACKEND_CACHE_SCHEMA") != SCHEMA:
        raise MaintenanceError("cache maintenance schema mismatch")
    if required("FULLMAG_BACKEND_CACHE_PROFILE") != PROFILE:
        raise MaintenanceError("cache maintenance profile mismatch")
    if required("FULLMAG_BACKEND_CACHE_MAINTENANCE_PROFILE") != MAINTENANCE_PROFILE:
        raise MaintenanceError("cache maintenance action profile mismatch")
    if required("FULLMAG_BACKEND_CACHE_MAINTENANCE_ACTION") != "ensure":
        raise MaintenanceError("cache maintenance action mismatch")
    if required("FULLMAG_BACKEND_CACHE_BUILD_ROOT") != BUILD_ROOT:
        raise MaintenanceError("cache maintenance build root mismatch")
    if required("FULLMAG_BACKEND_CACHE_PACKAGE_ROOT") != PACKAGE_ROOT:
        raise MaintenanceError("cache maintenance package root mismatch")

    def positive(name: str) -> int:
        value = required(name)
        try:
            parsed = int(value, 10)
        except ValueError as error:
            raise MaintenanceError(f"cache maintenance owner id is invalid: {name}") from error
        if parsed < 0 or parsed > 65535:
            raise MaintenanceError(f"cache maintenance owner id is invalid: {name}")
        return parsed

    uid = positive("FULLMAG_BACKEND_CACHE_OWNER_UID")
    gid = positive("FULLMAG_BACKEND_CACHE_OWNER_GID")
    if (uid, gid) != (DEFAULT_OWNER_UID, DEFAULT_OWNER_GID):
        raise MaintenanceError("cache maintenance must target backend uid/gid 65532")
    return {
        "project_id": required("FULLMAG_BACKEND_CACHE_PROJECT_ID"),
        "cache_key": required("FULLMAG_BACKEND_CACHE_KEY"),
        "unit_key": required("FULLMAG_BACKEND_CACHE_UNIT_KEY"),
        "owner_id": required("FULLMAG_BACKEND_CACHE_OWNER_ID"),
        "worktree_id": required("FULLMAG_BACKEND_CACHE_WORKTREE_ID"),
        "toolchain_image_id": required("FULLMAG_BACKEND_CACHE_TOOLCHAIN_IMAGE_ID"),
        "cargo_profile": required("FULLMAG_BACKEND_CARGO_PROFILE"),
        "runtime_image_id": required("FULLMAG_BACKEND_RUNTIME_IMAGE_ID"),
        "volume_names": {
            BUILD_ROLE: required("FULLMAG_BACKEND_CACHE_BUILD_VOLUME"),
            PACKAGE_ROLE: required("FULLMAG_BACKEND_CACHE_PACKAGE_VOLUME"),
        },
        "uid": uid,
        "gid": gid,
    }


def ensure(
    build_root: str | os.PathLike[str] = BUILD_ROOT,
    package_root: str | os.PathLike[str] = PACKAGE_ROOT,
    *,
    environment: Mapping[str, str] | None = None,
    owner_uid: int | None = None,
    owner_gid: int | None = None,
) -> dict[str, Any]:
    """Create/reopen exact markers and prove a bounded user read/write pair."""

    identity = _record_environment(os.environ if environment is None else environment)
    uid = identity["uid"] if owner_uid is None else owner_uid
    gid = identity["gid"] if owner_gid is None else owner_gid
    if not isinstance(uid, int) or not isinstance(gid, int) or uid < 0 or gid < 0:
        raise MaintenanceError("cache maintenance owner ids are invalid")
    roots = {BUILD_ROLE: build_root, PACKAGE_ROLE: package_root}
    directories: dict[str, int] = {}
    marker_raw: dict[str, bytes] = {}
    try:
        for role, root in roots.items():
            directory = _open_guest_root(root, uid, gid)
            directories[role] = directory
            marker = {
                "schema": OWNER_SCHEMA,
                "state": "owned",
                "unit_key": identity["unit_key"],
                "owner_id": identity["owner_id"],
                "role": role,
                "volume_name": identity["volume_names"][role],
                "uid": uid,
                "gid": gid,
            }
            marker_raw[role] = _ensure_marker(directory, marker, uid, gid)
            _prepare_readback(directory, uid, gid)
            _probe_readback(directory, marker_raw[role], uid, gid)
            _finalize_guest_root(directory, uid, gid)
    finally:
        for directory in directories.values():
            os.close(directory)

    return {
        "schema": RECEIPT_SCHEMA,
        "profile": PROFILE,
        "state": "ready",
        "project_id": identity["project_id"],
        "cache_key": identity["cache_key"],
        "unit_key": identity["unit_key"],
        "owner_id": identity["owner_id"],
        "cargo_profile": identity["cargo_profile"],
        "runtime_image_id": identity["runtime_image_id"],
        "toolchain_image_id": identity["toolchain_image_id"],
        "volume_names": identity["volume_names"],
        "markers": {
            role: {
                "schema": OWNER_SCHEMA,
                "state": "owned",
                "unit_key": identity["unit_key"],
                "owner_id": identity["owner_id"],
                "role": role,
                "volume_name": identity["volume_names"][role],
                "uid": uid,
                "gid": gid,
            }
            for role in (BUILD_ROLE, PACKAGE_ROLE)
        },
        "probe": {
            "schema": PROBE_SCHEMA,
            "state": "passed",
            "owner_uid": uid,
            "owner_gid": gid,
            "volumes": {
                role: {
                    "regular_marker": True,
                    "writable": True,
                    "readonly_reopen": True,
                    "no_reparse": True,
                }
                for role in (BUILD_ROLE, PACKAGE_ROLE)
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("ensure",))
    args = parser.parse_args(argv)
    try:
        receipt = ensure()
    except MaintenanceError as error:
        print(f"backend volume cache maintenance rejected: {error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
