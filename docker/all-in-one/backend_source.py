"""Verify and atomically extract a direct-Compose backend source archive.

The archive and external manifest are both untrusted inputs at this boundary.
Only regular files named by the verified source manifest are written.  The
destination is created in a temporary sibling and renamed only after the
archive digest, manifest, member set, and every file digest have passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import tarfile
import tempfile
from typing import Any, BinaryIO, Mapping


ARCHIVE_MANIFEST_SCHEMA = "fullmag.docker-backend-source.v1"
SOURCE_MANIFEST_SCHEMA = "fullmag.source-capsule.v1"
EMBEDDED_MANIFEST_FILENAME = "backend-source-manifest.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 300_000
CAPTURE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


class BackendSourceError(RuntimeError):
    """The direct backend source archive is not safe or internally coherent."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file_stream(stream: BinaryIO, expected_size: int) -> str:
    digest = hashlib.sha256()
    total = 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        total += len(chunk)
        if total > MAX_ARCHIVE_BYTES:
            raise BackendSourceError("backend source archive exceeds the size limit")
        digest.update(chunk)
    if total != expected_size:
        raise BackendSourceError("backend source archive changed while being read")
    return digest.hexdigest()


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackendSourceError("JSON manifest contains duplicate keys")
        result[key] = value
    return result


def _read_regular_json(path: Path) -> dict[str, Any]:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        metadata = os.fstat(descriptor)
        path_metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(path_metadata.st_mode)
            or getattr(path_metadata, "st_file_attributes", 0) & 0x400
            or metadata.st_nlink != 1
            or metadata.st_size <= 0
            or metadata.st_size > MAX_MANIFEST_BYTES
        ):
            raise BackendSourceError("manifest is not one bounded regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
        after = os.fstat(descriptor)
    except (OSError, UnicodeError) as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise BackendSourceError(f"cannot read manifest: {path}") from error
    finally:
        try:
            os.close(descriptor)
        except (UnboundLocalError, OSError):
            pass
    if len(raw) != metadata.st_size or (metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns) != (
        after.st_size, after.st_mtime_ns, after.st_ctime_ns
    ):
        raise BackendSourceError("manifest changed while being read")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeError, ValueError) as error:
        raise BackendSourceError("manifest is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise BackendSourceError("manifest root must be an object")
    return value


def _safe_member_name(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise BackendSourceError("archive member name is invalid")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.anchor
        or value != posix.as_posix()
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        raise BackendSourceError(f"archive member escapes its root: {value!r}")
    return value


def _sha256(value: object, label: str, *, length: int = 64) -> str:
    regex = SHA256_RE if length == 64 else SHA40_RE
    if not isinstance(value, str) or not regex.fullmatch(value):
        raise BackendSourceError(f"{label} is not a lowercase digest")
    return value


def _source_manifest_digest(source_manifest: Mapping[str, Any]) -> str:
    try:
        material = {
            "schema_version": source_manifest["schema_version"],
            "source_mode": source_manifest["source_mode"],
            "resolved_commit": source_manifest["resolved_commit"],
            "files": source_manifest["files"],
            "deleted": source_manifest["deleted"],
            "included_untracked": source_manifest["included_untracked"],
            "excluded": source_manifest["excluded"],
        }
    except KeyError as error:
        raise BackendSourceError(f"source manifest is missing {error.args[0]}") from error
    return _sha256_bytes(_canonical_bytes(material))


def _validate_source_manifest(value: object) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not isinstance(value, dict):
        raise BackendSourceError("source_manifest must be an object")
    if value.get("schema") != SOURCE_MANIFEST_SCHEMA or value.get("schema_version") != SOURCE_MANIFEST_SCHEMA:
        raise BackendSourceError("source_manifest schema mismatch")
    if value.get("source_mode") not in {"commit", "snapshot"}:
        raise BackendSourceError("source_manifest source_mode is invalid")
    resolved = _sha256(value.get("resolved_commit"), "source_manifest.resolved_commit", length=40)
    files = value.get("files")
    if not isinstance(files, list):
        raise BackendSourceError("source_manifest.files must be a list")
    checked: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for index, raw in enumerate(files):
        if not isinstance(raw, dict):
            raise BackendSourceError(f"source_manifest.files[{index}] is not an object")
        path = _safe_member_name(raw.get("path"))
        if path in checked:
            raise BackendSourceError(f"duplicate source manifest path: {path}")
        if raw.get("type") != "file" or raw.get("mode") not in {"100644", "100755"}:
            raise BackendSourceError(f"source manifest entry is not regular: {path}")
        size = raw.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0 or size > MAX_FILE_BYTES:
            raise BackendSourceError(f"source manifest file size is invalid: {path}")
        checked[path] = {
            "path": path,
            "type": "file",
            "mode": raw["mode"],
            "size": size,
            "sha256": _sha256(raw.get("sha256"), f"source manifest file {path}"),
        }
        order.append(path)
    if order != sorted(order):
        raise BackendSourceError("source manifest files are not canonically sorted")
    for field in ("deleted", "included_untracked", "excluded"):
        if not isinstance(value.get(field), list):
            raise BackendSourceError(f"source_manifest.{field} must be a list")
    for field in ("deleted", "included_untracked"):
        seen: set[str] = set()
        for item in value[field]:
            path = _safe_member_name(item)
            if path in seen:
                raise BackendSourceError(f"duplicate source manifest {field} path: {path}")
            seen.add(path)
    file_paths = set(checked)
    deleted_paths = set(value["deleted"])
    untracked_paths = set(value["included_untracked"])
    if (
        file_paths & deleted_paths
        or not untracked_paths <= file_paths
        or deleted_paths & untracked_paths
    ):
        raise BackendSourceError("source manifest path classes overlap")
    expected = _source_manifest_digest(value)
    if value.get("source_digest") != expected or value.get("source_digest_sha256") != expected:
        raise BackendSourceError("source_manifest digest does not match its content")
    if value.get("resolved_commit") != resolved:
        raise BackendSourceError("source_manifest commit is not canonical lowercase hex")
    return dict(value), checked


def _validate_native_identity(value: object, resolved_commit: str) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != "fullmag.source-snapshot.v2":
        raise BackendSourceError("native_source_identity schema mismatch")
    if value.get("head_commit_full") != resolved_commit:
        raise BackendSourceError("native identity commit differs from source manifest")
    for field in ("head_tree_sha256", "dirty_content_sha256", "source_snapshot_sha256"):
        _sha256(value.get(field), f"native_source_identity.{field}")
    if type(value.get("source_snapshot_dirty")) is not bool or type(value.get("ignored_non_runtime_dirty")) is not bool:
        raise BackendSourceError("native source dirty flags are invalid")
    if not isinstance(value.get("git_status_porcelain_v1"), list) or not isinstance(value.get("dirty_path_content"), list):
        raise BackendSourceError("native source status fields are invalid")
    return dict(value)


def _open_archive(path: Path) -> tuple[int, os.stat_result]:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        metadata = os.fstat(descriptor)
        path_metadata = path.lstat()
    except OSError as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise BackendSourceError(f"cannot open backend source archive: {path}") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(path_metadata.st_mode)
        or getattr(path_metadata, "st_file_attributes", 0) & 0x400
        or metadata.st_nlink != 1
        or metadata.st_size <= 0
        or metadata.st_size > MAX_ARCHIVE_BYTES
    ):
        os.close(descriptor)
        raise BackendSourceError("backend source archive is not one bounded regular file")
    return descriptor, metadata


def _validate_manifest(value: Mapping[str, Any], archive: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    required = {
        "schema", "capture_id", "source_mode", "source_root", "resolved_commit", "source_digest",
        "backend_source_sha256", "source_snapshot_sha256", "native_source_identity", "source_manifest",
        "source_manifest_sha256", "archive_filename", "archive_sha256", "archive_bytes", "created_at",
    }
    if set(value) != required or value.get("schema") != ARCHIVE_MANIFEST_SCHEMA:
        raise BackendSourceError("direct backend source manifest fields/schema mismatch")
    if not isinstance(value.get("capture_id"), str) or not CAPTURE_ID_RE.fullmatch(value["capture_id"]):
        raise BackendSourceError("capture_id is missing")
    if not isinstance(value.get("source_root"), str) or not value["source_root"]:
        raise BackendSourceError("source_root is missing")
    if not isinstance(value.get("created_at"), str) or not value["created_at"]:
        raise BackendSourceError("created_at is missing")
    mode = value.get("source_mode")
    if mode not in {"commit", "snapshot"}:
        raise BackendSourceError("source_mode is invalid")
    resolved = _sha256(value.get("resolved_commit"), "resolved_commit", length=40)
    source_manifest, files = _validate_source_manifest(value.get("source_manifest"))
    if source_manifest["source_mode"] != mode or source_manifest["resolved_commit"] != resolved:
        raise BackendSourceError("top-level source identity differs from source manifest")
    source_digest = _sha256(value.get("source_digest"), "source_digest")
    if source_digest != source_manifest["source_digest"] or value.get("backend_source_sha256") != source_digest:
        raise BackendSourceError("backend source digest does not match source manifest")
    native = _validate_native_identity(value.get("native_source_identity"), resolved)
    if value.get("source_snapshot_sha256") != native["source_snapshot_sha256"]:
        raise BackendSourceError("source snapshot digest does not match native identity")
    if value.get("source_manifest_sha256") != _sha256_bytes(_canonical_bytes(source_manifest)):
        raise BackendSourceError("source manifest digest is invalid")
    if not isinstance(value.get("archive_filename"), str) or value["archive_filename"] != archive.name:
        raise BackendSourceError("archive filename does not match the supplied archive")
    archive_bytes = value.get("archive_bytes")
    if isinstance(archive_bytes, bool) or not isinstance(archive_bytes, int) or archive_bytes <= 0 or archive_bytes > MAX_ARCHIVE_BYTES:
        raise BackendSourceError("archive byte count is invalid")
    _sha256(value.get("archive_sha256"), "archive_sha256")
    return dict(value), files, native


def _member_bytes(tar: tarfile.TarFile, member: tarfile.TarInfo, maximum: int) -> bytes:
    stream = tar.extractfile(member)
    if stream is None:
        raise BackendSourceError(f"archive member cannot be read: {member.name}")
    data = stream.read(maximum + 1)
    if len(data) != member.size or len(data) > maximum:
        raise BackendSourceError(f"archive member size is invalid: {member.name}")
    return data


def _verify_tar_contents(
    stream: BinaryIO,
    checked_manifest: Mapping[str, Any],
    files: Mapping[str, Mapping[str, Any]],
) -> None:
    """Validate the complete tar member set and every declared file digest."""

    stream.seek(0)
    with tarfile.open(fileobj=stream, mode="r:") as tar:
        members = tar.getmembers()
        if len(members) > MAX_MEMBERS:
            raise BackendSourceError("backend source archive has too many members")
        by_name: dict[str, tarfile.TarInfo] = {}
        for member in members:
            name = _safe_member_name(member.name)
            if name in by_name:
                raise BackendSourceError(f"duplicate archive member: {name}")
            if (
                member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE}
                or not member.isreg()
                or member.linkname
                or member.size < 0
                or member.size > MAX_FILE_BYTES
                or member.mode & 0o7000
            ):
                raise BackendSourceError(f"archive member is not a plain regular file: {name}")
            by_name[name] = member
        expected_names = set(files) | {EMBEDDED_MANIFEST_FILENAME}
        if set(by_name) != expected_names:
            missing = sorted(expected_names - set(by_name))
            extra = sorted(set(by_name) - expected_names)
            raise BackendSourceError(f"archive member set differs (missing={missing[:1]}, extra={extra[:1]})")
        embedded = _member_bytes(tar, by_name[EMBEDDED_MANIFEST_FILENAME], MAX_MANIFEST_BYTES)
        if embedded != _canonical_bytes(checked_manifest["source_manifest"]):
            raise BackendSourceError("embedded source manifest differs from external manifest")
        for name, entry in files.items():
            member = by_name[name]
            if member.size != entry["size"]:
                raise BackendSourceError(f"archive size differs from source manifest: {name}")
            stream_in = tar.extractfile(member)
            if stream_in is None:
                raise BackendSourceError(f"archive member cannot be read: {name}")
            digest = hashlib.sha256()
            total = 0
            for chunk in iter(lambda: stream_in.read(1024 * 1024), b""):
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    raise BackendSourceError(f"archive member exceeds the file limit: {name}")
                digest.update(chunk)
            if total != entry["size"] or digest.hexdigest() != entry["sha256"]:
                raise BackendSourceError(f"archive content digest differs from source manifest: {name}")


def _checked_destination(value: Path) -> tuple[Path, Path]:
    destination = Path(value)
    if not destination.is_absolute() or destination.exists() or destination.is_symlink():
        raise BackendSourceError("frozen source destination must be an absent absolute path")
    parent = destination.parent
    if not parent.is_dir():
        raise BackendSourceError("frozen source destination parent must already exist")
    for ancestor in (parent, *parent.parents):
        try:
            metadata = ancestor.lstat()
        except OSError as error:
            raise BackendSourceError("cannot inspect frozen source destination parent") from error
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise BackendSourceError("frozen source destination traverses a link/reparse point")
    return destination, parent


def _make_readonly(root: Path) -> None:
    for current, directories, filenames in os.walk(root, topdown=False, followlinks=False):
        current_path = Path(current)
        for name in filenames:
            path = current_path / name
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise BackendSourceError(f"extracted source contains an unsafe file: {path}")
            path.chmod(0o444 if not (metadata.st_mode & stat.S_IXUSR) else 0o555)
        for name in directories:
            path = current_path / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
                raise BackendSourceError(f"extracted source contains an unsafe directory: {path}")
            path.chmod(0o555)
    root.chmod(0o555)


def extract_frozen_source(archive_path: Path, manifest_path: Path, destination: Path) -> dict[str, Any]:
    """Verify and atomically extract one direct-Compose backend source archive."""

    archive = Path(archive_path)
    manifest_file = Path(manifest_path)
    manifest = _read_regular_json(manifest_file)
    destination, parent = _checked_destination(Path(destination))
    checked_manifest, files, native = _validate_manifest(manifest, archive)
    descriptor, archive_metadata = _open_archive(archive)
    temporary: Path | None = None
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            digest = _sha256_file_stream(stream, archive_metadata.st_size)
            if digest != checked_manifest["archive_sha256"] or archive_metadata.st_size != checked_manifest["archive_bytes"]:
                raise BackendSourceError("backend source archive digest/size mismatch")
            stream.seek(0)
            try:
                with tarfile.open(fileobj=stream, mode="r:") as tar:
                    members = tar.getmembers()
                    if len(members) > MAX_MEMBERS:
                        raise BackendSourceError("backend source archive has too many members")
                    by_name: dict[str, tarfile.TarInfo] = {}
                    for member in members:
                        name = _safe_member_name(member.name)
                        if name in by_name:
                            raise BackendSourceError(f"duplicate archive member: {name}")
                        if (
                            member.type not in {tarfile.REGTYPE, tarfile.AREGTYPE}
                            or not member.isreg()
                            or member.linkname
                            or member.size < 0
                            or member.size > MAX_FILE_BYTES
                            or member.mode & 0o7000
                        ):
                            raise BackendSourceError(f"archive member is not a plain regular file: {name}")
                        by_name[name] = member
                    expected_names = set(files) | {EMBEDDED_MANIFEST_FILENAME}
                    if set(by_name) != expected_names:
                        missing = sorted(expected_names - set(by_name))
                        extra = sorted(set(by_name) - expected_names)
                        raise BackendSourceError(f"archive member set differs (missing={missing[:1]}, extra={extra[:1]})")
                    embedded = _member_bytes(tar, by_name[EMBEDDED_MANIFEST_FILENAME], MAX_MANIFEST_BYTES)
                    if embedded != _canonical_bytes(checked_manifest["source_manifest"]):
                        raise BackendSourceError("embedded source manifest differs from external manifest")
                    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.extract-", dir=parent))
                    for name, entry in files.items():
                        member = by_name[name]
                        if member.size != entry["size"]:
                            raise BackendSourceError(f"archive size differs from source manifest: {name}")
                        stream_in = tar.extractfile(member)
                        if stream_in is None:
                            raise BackendSourceError(f"archive member cannot be extracted: {name}")
                        target = temporary / Path(*PurePosixPath(name).parts)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if target.exists() or target.is_symlink():
                            raise BackendSourceError(f"duplicate extracted path: {name}")
                        digest_file = hashlib.sha256()
                        total = 0
                        with target.open("xb") as output:
                            for chunk in iter(lambda: stream_in.read(1024 * 1024), b""):
                                total += len(chunk)
                                if total > MAX_FILE_BYTES:
                                    raise BackendSourceError(f"archive member exceeds the file limit: {name}")
                                digest_file.update(chunk)
                                output.write(chunk)
                            output.flush()
                            os.fsync(output.fileno())
                        if total != entry["size"] or digest_file.hexdigest() != entry["sha256"]:
                            raise BackendSourceError(f"archive content digest differs from source manifest: {name}")
                        target.chmod(0o755 if entry["mode"] == "100755" else 0o644)
            finally:
                # The descriptor remains owned by this function; tarfile does
                # not close the externally supplied file object on all Python
                # versions, so close it explicitly below as well.
                pass
        after = os.fstat(descriptor)
        if (archive_metadata.st_dev, archive_metadata.st_ino, archive_metadata.st_size, archive_metadata.st_mtime_ns, archive_metadata.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
        ):
            raise BackendSourceError("backend source archive changed during extraction")
        if temporary is None:
            raise BackendSourceError("backend source extraction produced no temporary directory")
        _make_readonly(temporary)
        os.replace(temporary, destination)
        temporary = None
        return {
            "schema": ARCHIVE_MANIFEST_SCHEMA,
            "state": "extracted",
            "destination": str(destination),
            "archive_sha256": checked_manifest["archive_sha256"],
            "archive_bytes": checked_manifest["archive_bytes"],
            "source_digest": checked_manifest["source_digest"],
            "backend_source_sha256": checked_manifest["backend_source_sha256"],
            "source_snapshot_sha256": native["source_snapshot_sha256"],
            "resolved_commit": checked_manifest["resolved_commit"],
            "file_count": len(files),
        }
    except BackendSourceError:
        raise
    except (OSError, tarfile.TarError, ValueError) as error:
        raise BackendSourceError("backend source archive extraction failed") from error
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


def verify_frozen_source_archive(archive_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Verify archive/manifest identity without creating a source directory."""

    archive = Path(archive_path)
    manifest = _read_regular_json(Path(manifest_path))
    checked, files, native = _validate_manifest(manifest, archive)
    descriptor, metadata = _open_archive(archive)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            digest = _sha256_file_stream(stream, metadata.st_size)
        if digest != checked["archive_sha256"] or metadata.st_size != checked["archive_bytes"]:
            raise BackendSourceError("backend source archive digest/size mismatch")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            _verify_tar_contents(stream, checked, files)
        after = os.fstat(descriptor)
        if (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise BackendSourceError("backend source archive changed while being verified")
        return {
            "schema": ARCHIVE_MANIFEST_SCHEMA,
            "state": "verified",
            "archive_sha256": digest,
            "archive_bytes": metadata.st_size,
            "source_digest": checked["source_digest"],
            "source_snapshot_sha256": native["source_snapshot_sha256"],
            "resolved_commit": checked["resolved_commit"],
            "file_count": len(files),
        }
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", required=True, type=Path)
    verify.add_argument("--manifest", required=True, type=Path)
    extract = subparsers.add_parser("extract")
    extract.add_argument("--archive", required=True, type=Path)
    extract.add_argument("--manifest", required=True, type=Path)
    extract.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "verify":
        result = verify_frozen_source_archive(args.archive, args.manifest)
    else:
        result = extract_frozen_source(args.archive, args.manifest, args.destination)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BackendSourceError as error:
        print(f"backend source boundary failed: {error}", file=os.sys.stderr)
        raise SystemExit(2)
