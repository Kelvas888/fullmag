#!/usr/bin/env python3
"""Direct Compose builder and server for the all-in-one backend image.

The host submits an immutable source capsule and an attested manifest.  This
entrypoint materializes the capsule in the image-owned build volume, invokes
the repository Make target with the complete CUDA/FEM feature set, and
publishes one package receipt.  The server only consumes a receipt-validated
package and then hands process ownership to the existing all-in-one
entrypoint.

This command deliberately has no public build-command option.  The source
archive is data, never a shell script supplied by the caller, and the only
native build command is the canonical ``make install-cli-dev`` target.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, NoReturn

try:
    import fcntl
except ImportError:  # pragma: no cover - direct backend images are Linux
    fcntl = None  # type: ignore[assignment]

from backend_source import (
    BackendSourceError,
    extract_frozen_source,
)


RECEIPT_SCHEMA = "fullmag.direct-compose.backend-build-receipt.v1"

MAX_MANIFEST_BYTES = 32 * 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

BUILD_ROOT = Path("/build")
OUTPUT_ROOT = Path("/output")
PACKAGE_ROOT = Path("/opt/fullmag/package")
OWNER_MARKER = ".fullmag-direct-backend-owner.json"
RUNTIME_LOCK_NAME = ".fullmag-backend-runtime.lock"
PERSISTENT_WORKSPACE_DIRS = frozenset(
    {".fullmag-build", ".fullmag-cargo", ".fullmag-rustup"}
)

# ``install-cli-dev`` emits one CUDA-capable binary.  Runtime execution
# profiles select the requested lane from that binary; these four entries are
# part of the receipt so host admission can reject a package missing a lane.
LANES = ("fdm-cpu", "fdm-gpu", "fem-cpu", "fem-gpu")
REQUIRED_PACKAGE_PATHS = (
    "bin/fullmag-bin",
    "bin/fullmag-api",
    "bin/fullmag-api-accepted-worker",
    "bin/fullmag-api-accepted-supervisor",
    "bin/fullmag-api-accepted-scheduler",
    "bin/fullmag-runtime-service",
    "bin/fullmag-api-resource-pool",
    "bin/fullmag-api-accepted-fem-preparer",
    "bin/fullmag-api-accepted-fem-preparation-supervisor",
    "bin/fullmag-api-accepted-fem-preparation-scheduler",
    "bin/fullmag-api-preparation-resource-pool",
    "bin/fullmag-api-preparation-retry",
    "_fullmag_core.so",
    "launcher-build-mode",
)


class BackendBuildError(RuntimeError):
    """A fail-closed direct backend build or package error."""


def _fail(message: str) -> NoReturn:
    raise BackendBuildError(message)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path, name: str, maximum: int | None = None) -> tuple[str, os.stat_result]:
    path = _absolute(path, name)
    descriptor = _open_regular(path, name, maximum)
    try:
        before = os.fstat(descriptor)
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            total += len(block)
            digest.update(block)
            if maximum is not None and total > maximum:
                _fail(f"{name} exceeds its size bound")
        after = os.fstat(descriptor)
        if _file_signature(before) != _file_signature(after):
            _fail(f"{name} changed while hashing")
        return digest.hexdigest(), before
    finally:
        os.close(descriptor)


def _file_signature(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _absolute(path: Path, name: str) -> Path:
    if not path.is_absolute() or any(part == ".." for part in path.parts):
        _fail(f"{name} must be absolute and cannot contain parent traversal")
    return path


def _assert_no_links(path: Path, name: str) -> None:
    path = _absolute(path, name)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            _fail(f"cannot inspect {name}: {error}")
        if stat.S_ISLNK(metadata.st_mode) or bool(
            getattr(metadata, "st_file_attributes", 0) & 0x400
        ):
            _fail(f"{name} traverses a link or reparse point: {current}")


def _open_regular(path: Path, name: str, maximum: int | None) -> int:
    path = _absolute(path, name)
    _assert_no_links(path.parent, f"{name} parent")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        _fail(f"cannot open {name}: {error}")
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            _fail(f"{name} is not a regular file")
        if maximum is not None and metadata.st_size > maximum:
            _fail(f"{name} exceeds its size bound")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _read_regular(path: Path, name: str, maximum: int) -> tuple[bytes, os.stat_result]:
    descriptor = _open_regular(path, name, maximum)
    try:
        before = os.fstat(descriptor)
        data = bytearray()
        while len(data) <= maximum:
            block = os.read(descriptor, min(1024 * 1024, maximum + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > maximum:
            _fail(f"{name} exceeds its size bound")
        after = os.fstat(descriptor)
        if _file_signature(before) != _file_signature(after):
            _fail(f"{name} changed while reading")
        return bytes(data), before
    finally:
        os.close(descriptor)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"JSON object contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_json(path: Path, name: str, maximum: int = MAX_MANIFEST_BYTES) -> tuple[dict[str, Any], bytes]:
    raw, _ = _read_regular(path, name, maximum)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{name} is not valid JSON: {error}")
    if not isinstance(value, dict):
        _fail(f"{name} must contain a JSON object")
    return value, raw


def _ensure_directory(path: Path, name: str) -> Path:
    path = _absolute(path, name)
    _assert_no_links(path, name)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir()
            except FileExistsError:
                pass
            metadata = current.lstat()
        except OSError as error:
            _fail(f"cannot inspect {name}: {error}")
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            _fail(f"{name} component is not a directory: {current}")
    return path


def _remove_owned_tree(path: Path) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        # Remove only this owned directory entry; never traverse its target.
        path.unlink()
        return
    if bool(getattr(metadata, "st_file_attributes", 0) & 0x400):
        _fail(f"owned workspace contains a reparse point: {path}")
    if stat.S_ISDIR(metadata.st_mode):
        for child in path.iterdir():
            _remove_owned_tree(child)
        path.rmdir()
    elif stat.S_ISREG(metadata.st_mode):
        path.unlink()
    else:
        _fail(f"owned workspace contains a special file: {path}")


def _prepare_workspace(build_root: Path) -> Path:
    workspace = build_root / "workspace"
    _ensure_directory(build_root, "build root")
    _ensure_directory(workspace, "backend workspace")
    marker = workspace / OWNER_MARKER
    if marker.exists() or marker.is_symlink():
        document, _ = _read_json(marker, "backend workspace owner", 16 * 1024)
        if document.get("schema") != "fullmag.direct-compose.backend-workspace.v1":
            _fail("backend workspace owner marker has an unsupported schema")
        for child in tuple(workspace.iterdir()):
            if child.name in PERSISTENT_WORKSPACE_DIRS or child.name == OWNER_MARKER:
                continue
            _remove_owned_tree(child)
    elif any(workspace.iterdir()):
        _fail("backend workspace is nonempty without an owned marker")
    for name in PERSISTENT_WORKSPACE_DIRS:
        _ensure_directory(workspace / name, f"persistent workspace directory {name}")
    return workspace


def _copy_tree(source: Path, destination: Path) -> None:
    for current, dirnames, filenames in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        relative = current_path.relative_to(source)
        target_dir = destination.joinpath(*relative.parts) if relative.parts else destination
        _ensure_directory(target_dir, f"materialized source directory {relative}")
        for name in dirnames:
            child = current_path / name
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                _fail(f"source tree contains an unsafe directory entry: {child}")
        for name in filenames:
            child = current_path / name
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                _fail(f"source tree contains an unsafe file entry: {child}")
            target = target_dir / name
            _copy_regular_file(child, target, metadata.st_mode, "materialized source")


def _copy_regular_file(source: Path, target: Path, source_mode: int, label: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags, 0o644)
    except OSError as error:
        _fail(f"cannot create {label} entry {target}: {error}")
    try:
        with source.open("rb") as source_stream:
            while True:
                block = source_stream.read(1024 * 1024)
                if not block:
                    break
                view = memoryview(block)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        _fail(f"short write while copying {label} entry {target}")
                    view = view[written:]
    finally:
        os.close(descriptor)
    os.chmod(target, 0o755 if source_mode & 0o111 else 0o644)


PACKAGE_LIBRARY_PREFIXES = ("libfullmag_fdm.so", "libfullmag_fem.so")


def _resolve_package_library_alias(source_lib: Path, child: Path) -> Path:
    if child.parent != source_lib or not any(
        child.name.startswith(prefix) for prefix in PACKAGE_LIBRARY_PREFIXES
    ):
        _fail(f"package contains an unsupported symlink: {child}")
    try:
        target = child.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        _fail(f"package library symlink cannot be resolved: {child}: {error}")
    if target == source_lib or source_lib not in target.parents:
        _fail(f"package library symlink escapes its lib directory: {child}")
    metadata = target.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail(f"package library symlink target is not a regular file: {child}")
    return target


def _copy_package_tree(source: Path, destination: Path) -> None:
    """Copy runtime output, dereferencing only confined SONAME library aliases."""

    source_lib = source / "lib"
    if source_lib.exists() or source_lib.is_symlink():
        metadata = source_lib.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("package lib directory is not a regular directory")
    for current, dirnames, filenames in os.walk(source, topdown=True, followlinks=False):
        current_path = Path(current)
        relative = current_path.relative_to(source)
        target_dir = destination.joinpath(*relative.parts) if relative.parts else destination
        _ensure_directory(target_dir, f"package directory {relative}")
        for name in dirnames:
            child = current_path / name
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                _fail(f"package contains an unsafe directory entry: {child}")
        for name in filenames:
            child = current_path / name
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                if current_path != source_lib:
                    _fail(f"package contains an out-of-scope symlink: {child}")
                source_file = _resolve_package_library_alias(source_lib, child)
                source_mode = source_file.stat().st_mode
            elif stat.S_ISREG(metadata.st_mode):
                source_file = child
                source_mode = metadata.st_mode
            else:
                _fail(f"package contains an unsafe file entry: {child}")
            target = target_dir / name
            _copy_regular_file(source_file, target, source_mode, "package")


def _remove_extracted_source(path: Path) -> None:
    """Make the helper's read-only extraction removable by its owner."""

    if not path.exists() and not path.is_symlink():
        return
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail(f"extracted source root is unsafe: {path}")
    for current, dirnames, filenames in os.walk(path, topdown=False, followlinks=False):
        current_path = Path(current)
        for name in filenames:
            child = current_path / name
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                _fail(f"extracted source contains an unsafe cleanup entry: {child}")
            child.chmod(0o600)
        for name in dirnames:
            child = current_path / name
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                _fail(f"extracted source contains an unsafe cleanup directory: {child}")
            child.chmod(0o700)
    path.chmod(0o700)
    _remove_owned_tree(path)


def _materialize_source(source_tar: Path, manifest_path: Path, build_root: Path) -> tuple[Path, dict[str, Any], dict[str, Any], str, str]:
    source_tar = _absolute(source_tar, "source archive")
    manifest_path = _absolute(manifest_path, "source manifest")
    document, manifest_bytes = _read_json(manifest_path, "source manifest", 64 * 1024 * 1024)
    capsule_value = document.get("source_manifest")
    native_value = document.get("native_source_identity")
    if not isinstance(capsule_value, dict) or not isinstance(native_value, dict):
        _fail("source manifest lacks canonical source_manifest/native_source_identity")
    capsule = dict(capsule_value)
    native = dict(native_value)
    manifest_hash = _sha256_bytes(manifest_bytes)
    workspace = _prepare_workspace(build_root)
    stage_parent = Path(tempfile.mkdtemp(prefix=".backend-capsule-", dir=build_root))
    stage = stage_parent / "source"
    try:
        try:
            extracted = extract_frozen_source(source_tar, manifest_path, stage)
        except BackendSourceError as error:
            _fail(f"source archive failed canonical extraction: {error}")
        if extracted.get("source_digest") != capsule.get("source_digest"):
            _fail("source archive source digest differs from the supplied manifest")
        if extracted.get("resolved_commit") != capsule.get("resolved_commit"):
            _fail("source archive commit differs from the supplied manifest")
        archive_hash = extracted.get("archive_sha256")
        if not isinstance(archive_hash, str) or not SHA256_RE.fullmatch(archive_hash):
            _fail("source archive extractor returned an invalid digest")
        if extracted.get("source_snapshot_sha256") != native.get("source_snapshot_sha256"):
            _fail("source archive native identity differs from the supplied manifest")
        after_document, after_manifest_bytes = _read_json(
            manifest_path, "source manifest", 64 * 1024 * 1024
        )
        if after_manifest_bytes != manifest_bytes or after_document != document:
            _fail("source manifest changed during extraction")
        _copy_tree(stage, workspace)
        owner = {
            "schema": "fullmag.direct-compose.backend-workspace.v1",
            "source_digest": capsule["source_digest"],
            "source_tar_sha256": archive_hash,
        }
        _write_json(workspace / OWNER_MARKER, owner, "backend workspace owner")
        return workspace, capsule, native, manifest_hash, archive_hash
    finally:
        _remove_extracted_source(stage)
        try:
            stage_parent.rmdir()
        except OSError:
            pass


def _write_json(path: Path, value: Mapping[str, Any], name: str) -> None:
    parent = _ensure_directory(path.parent, f"{name} parent")
    data = _canonical(value)
    temporary = parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o660)
        try:
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    _fail(f"short write while publishing {name}")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
    except OSError as error:
        try:
            temporary.unlink()
        except OSError:
            pass
        _fail(f"cannot publish {name}: {error}")


@contextmanager
def _runtime_build_lock(build_root: Path):
    """Serialize source replacement and Make against the shared build cache."""

    if fcntl is None:
        _fail("direct backend requires POSIX flock support")
    _ensure_directory(build_root, "build root")
    lock_path = build_root / RUNTIME_LOCK_NAME
    _assert_no_links(lock_path.parent, "backend runtime lock parent")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o660)
    except OSError as error:
        _fail(f"cannot open backend runtime lock: {error}")
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            _fail("backend runtime lock is not one regular file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as error:
            _fail(f"backend runtime cache is already in use: {error}")
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _toolchain_identity() -> tuple[str, dict[str, Any]]:
    image_id = os.environ.get("FULLMAG_TOOLCHAIN_IMAGE_ID", "")
    if not IMAGE_RE.fullmatch(image_id):
        _fail("FULLMAG_TOOLCHAIN_IMAGE_ID must be an immutable sha256 image ID")
    path = Path("/opt/fullmag-deps/share/fullmag/dependency-versions.json")
    dependency, raw = _read_json(path, "FEM dependency manifest", 4 * 1024 * 1024)
    if dependency.get("schema") != "fullmag.docker.fem-gpu-dependencies.v1":
        _fail("FEM dependency manifest schema is unsupported")
    for key in ("declared", "actual", "latest"):
        if not isinstance(dependency.get(key), dict):
            _fail(f"FEM dependency manifest field {key} is invalid")
    commits = dependency["actual"].get("source_commits")
    if not isinstance(commits, dict) or any(not isinstance(commits.get(key), str) or not commits[key] for key in ("mfem", "libceed", "hypre", "petsc", "slepc")):
        _fail("FEM dependency manifest lacks pinned source commits")
    return image_id, {
        "image_id": image_id,
        "dependency_manifest_sha256": _sha256_bytes(raw),
        "dependency_schema": dependency["schema"],
        "actual_source_commits": dict(commits),
    }


def _build_environment(workspace: Path, build_root: Path, native: Mapping[str, Any], jobs: int) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "FULLMAG_WINDOWS_CONTAINER_MANAGED": "1",
            "FULLMAG_RUNNER_WORKSPACE": str(workspace),
            "FULLMAG_CARGO_TARGET_DIR": "/workspace/.fullmag-build/cargo-targets/direct",
            "CARGO_TARGET_DIR": "/workspace/.fullmag-build/cargo-targets/direct",
            "FULLMAG_CARGO_TARGET_ROOT": "/workspace/.fullmag-build/cargo-targets",
            "CARGO_TARGET_ROOT": "/workspace/.fullmag-build/cargo-targets",
            "CARGO_HOME": str(build_root / "cargo"),
            "RUSTUP_HOME": "/root/.rustup",
            "RUSTUP_TOOLCHAIN": "nightly",
            "RUSTUP_AUTO_INSTALL": "0",
            "FULLMAG_BUILD_CPU_ONLY": "0",
            "FULLMAG_FORCE_LOCAL_FEM_CPU": "0",
            "FULLMAG_FORCE_LOCAL_FEM_GPU": "1",
            "FULLMAG_SKIP_MANAGED_FEM_GPU_EXPORT": "1",
            "FULLMAG_DISABLE_MANAGED_FEM_GPU_RUNTIME": "1",
            "FULLMAG_USE_MFEM_STACK": "ON",
            "FULLMAG_FEM_ENABLE_CUDA": "ON",
            "FULLMAG_FEM_REQUIRE_GPU": "1",
            "FULLMAG_FEM_REQUIRE_CEED": "1",
            "FULLMAG_FEM_WITH_SLEPC": "ON",
            "FULLMAG_FEM_MFEM_DEVICE": "ceed-cuda:/gpu/cuda/shared",
            "FULLMAG_SOURCE_GIT_COMMIT": str(native["head_commit_full"]),
            "FULLMAG_SOURCE_WORKTREE_STATE": (
                "dirty" if native["source_snapshot_dirty"] else "clean"
            ),
            "FULLMAG_SOURCE_SNAPSHOT_SHA256": str(native["source_snapshot_sha256"]),
            "CARGO_BUILD_JOBS": str(jobs),
            "CMAKE_BUILD_PARALLEL_LEVEL": str(jobs),
            "CARGO_INCREMENTAL": "1",
            "HOME": str(build_root / "home"),
            "TMPDIR": str(build_root / "tmp"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    for path in (build_root / "cargo", build_root / "home", build_root / "tmp"):
        _ensure_directory(path, f"build directory {path}")
    return environment


def _hash_package(root: Path) -> list[dict[str, Any]]:
    if root.is_symlink() or not root.is_dir():
        _fail("built package root is not a regular directory")
    for relative in REQUIRED_PACKAGE_PATHS:
        path = root.joinpath(*PurePosixPath(relative).parts)
        if path.is_symlink() or not path.is_file():
            _fail(f"built package is missing required output: {relative}")
        if relative.startswith("bin/") and not os.access(path, os.X_OK):
            _fail(f"built package binary is not executable: {relative}")
    marker = (root / "launcher-build-mode").read_text(encoding="utf-8").strip()
    if marker != "cuda-fem-gpu":
        _fail(f"canonical build did not produce strict CUDA/FEM GPU mode: {marker!r}")
    libraries = []
    for pattern in ("lib/libfullmag_fdm.so*", "lib/libfullmag_fem.so*"):
        matches = sorted(root.glob(pattern))
        if not matches or any(path.is_symlink() or not path.is_file() for path in matches):
            _fail(f"built package is missing native library family: {pattern}")
        libraries.extend(matches)
    selected: set[Path] = set()
    for relative in REQUIRED_PACKAGE_PATHS:
        selected.add(root.joinpath(*PurePosixPath(relative).parts))
    selected.update(libraries)
    records: list[dict[str, Any]] = []
    for path in sorted(selected):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail(f"built package contains an unsafe output: {path}")
        digest, _ = _sha256_file(path, f"built package {path}", MAX_SOURCE_BYTES)
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": metadata.st_size,
                "sha256": digest,
                "mode": "100755" if metadata.st_mode & 0o111 else "100644",
            }
        )
    return records


def _copy_package(workspace: Path, output: Path) -> list[dict[str, Any]]:
    source = workspace / ".fullmag" / "local"
    if source.is_symlink() or not source.is_dir():
        _fail("canonical Make target did not publish .fullmag/local")
    _ensure_directory(output, "backend output")
    if any(output.iterdir()):
        _fail("backend output must be empty before direct package publication")
    stage = Path(tempfile.mkdtemp(prefix=".backend-package-", dir=output.parent))
    try:
        _copy_package_tree(source, stage)
        records = _hash_package(stage)
        for child in stage.iterdir():
            destination = output / child.name
            if destination.exists() or destination.is_symlink():
                _fail(f"backend output changed during publication: {destination}")
            os.replace(child, destination)
        return records
    finally:
        if stage.exists():
            _remove_owned_tree(stage)


def _write_console_chunk(chunk: bytes) -> None:
    """Mirror Make output to the container log without making it a build input."""

    stream = getattr(sys.stdout, "buffer", sys.stdout)
    try:
        stream.write(chunk)
    except TypeError:
        stream.write(chunk.decode("utf-8", errors="replace"))
    except (BrokenPipeError, OSError):
        return
    try:
        stream.flush()
    except (BrokenPipeError, OSError):
        pass


def _run_canonical_make(command: list[str], workspace: Path, environment: Mapping[str, str], log_path: Path) -> int:
    try:
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
            )
            assert process.stdout is not None
            with process.stdout:
                while True:
                    chunk = process.stdout.read(1024 * 1024)
                    if not chunk:
                        break
                    log.write(chunk)
                    log.flush()
                    _write_console_chunk(chunk)
            return process.wait()
    except OSError as error:
        _fail(f"cannot execute canonical Make target: {error}")


def _prepare_locked(
    args: argparse.Namespace,
    build_root: Path,
    output: Path,
    jobs: int,
    toolchain: Mapping[str, Any],
) -> int:
    workspace, capsule, native, manifest_hash, archive_hash = _materialize_source(
        Path(args.source_tar), Path(args.manifest), build_root
    )
    environment = _build_environment(workspace, build_root, native, jobs)
    build_log = workspace / ".fullmag" / "local" / "direct-backend-build.log"
    _ensure_directory(build_log.parent, "backend build log parent")
    command = [shutil.which("make") or "/usr/bin/make", "install-cli-dev"]
    return_code = _run_canonical_make(command, workspace, environment, build_log)
    if return_code != 0:
        _fail(f"canonical Make target failed with exit code {return_code}")
    records = _copy_package(workspace, output)
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "state": "succeeded",
        "qualification": "NOT VERIFIED",
        "operation": "direct-compose-build",
        "command": command,
        "source": {
            "manifest_sha256": manifest_hash,
            "source_snapshot_sha256": native["source_snapshot_sha256"],
            "source_digest": capsule["source_digest"],
            "resolved_commit": capsule["resolved_commit"],
            "source_tar_sha256": archive_hash,
        },
        "native_source_identity": native,
        "native_source_identity_sha256": _sha256_bytes(_canonical(native)),
        "toolchain": toolchain,
        "execution_lanes": {
            lane: {
                "status": "compiled",
                "binary": "bin/fullmag-api",
                "selection": "published_execution_profile",
                "fallback": "forbidden",
            }
            for lane in LANES
        },
        "build": {
            "mode": "cuda-fem-gpu",
            "features": ["cuda", "fem-gpu"],
            "fullmag_build_cpu_only": False,
            "fem_gpu_required": True,
            "libceed_required": True,
            "make_log": "direct-backend-build.log",
        },
        "artifacts": records,
    }
    _write_json(output / "backend-build-receipt.json", receipt, "backend build receipt")
    return 0


def _prepare(args: argparse.Namespace) -> int:
    build_root = _absolute(Path(args.build_root), "build root")
    output = _absolute(Path(args.output), "backend output")
    jobs = int(args.jobs)
    if jobs < 1 or jobs > 64:
        _fail("jobs must be between 1 and 64")
    _, toolchain = _toolchain_identity()
    with _runtime_build_lock(build_root):
        return _prepare_locked(args, build_root, output, jobs, toolchain)


def _serve(extra: list[str]) -> int:
    if os.environ.get("FULLMAG_DOCKER_ROLE") == "frontend":
        environment = dict(os.environ)
        command = [sys.executable, "/opt/fullmag/entrypoint.py", *extra]
        os.execvpe(sys.executable, command, environment)
        return 0
    receipt_path = PACKAGE_ROOT / "backend-build-receipt.json"
    receipt, _ = _read_json(receipt_path, "backend build receipt", 8 * 1024 * 1024)
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("state") != "succeeded":
        _fail("runtime package receipt is not a successful direct-compose receipt")
    lanes = receipt.get("execution_lanes")
    if not isinstance(lanes, dict) or set(lanes) != set(LANES):
        _fail("runtime package receipt does not attest all four execution lanes")
    actual_artifacts = _hash_package(PACKAGE_ROOT)
    if receipt.get("artifacts") != actual_artifacts:
        _fail("runtime package artifacts differ from the build receipt")
    environment = dict(os.environ)
    environment.update(
        {
            "FULLMAG_DOCKER_ROLE": "backend",
            "FULLMAG_RUNTIME_ROOT": str(PACKAGE_ROOT),
            "FULLMAG_WEB_STATIC_DIR": str(PACKAGE_ROOT / "web"),
            "PATH": f"{PACKAGE_ROOT / 'bin'}:/opt/fullmag-deps/bin:/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin",
        }
    )
    command = [sys.executable, "/opt/fullmag/entrypoint.py", *extra]
    os.execvpe(sys.executable, command, environment)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for name in ("prepare", "build"):
        subparser = subparsers.add_parser(name, help="build the direct four-lane package")
        subparser.add_argument("--source-tar", required=True, type=Path)
        subparser.add_argument("--manifest", required=True, type=Path)
        subparser.add_argument("--output", default=OUTPUT_ROOT, type=Path)
        subparser.add_argument("--build-root", default=BUILD_ROOT, type=Path)
        subparser.add_argument("--jobs", default=int(os.environ.get("CARGO_BUILD_JOBS", "2")), type=int)
    subparsers.add_parser("serve", help="serve the receipt-validated package")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args, extra = parser.parse_known_args(argv)
    try:
        if args.operation in {"prepare", "build"}:
            if extra:
                parser.error(f"unexpected arguments for {args.operation}: {' '.join(extra)}")
            return _prepare(args)
        return _serve(extra)
    except BackendBuildError as error:
        print(f"backend-dev: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"backend-dev: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
