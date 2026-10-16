#!/usr/bin/env python3
"""Start Fullmag's direct, two-container Docker development workspace.

The launcher has two deliberately separate phases:

``build``
    Selects one registered Windows checkout, freezes it into the verified
    backend source archive, runs the four-lane backend build in a Compose
    build container, and records a development assembly receipt.

``up``
    Performs ``build`` and hands the resulting receipt to the existing runtime
    launcher.  The runtime launcher owns Windows storage attestation, the
    frontend cache, host ledger, startup-script admission, and the final
    Compose start.  No managed Fullmag_build_runner job is submitted here.

The source checkout itself remains the live, read-only bind used by the
runtime containers.  Only the backend compilation consumes the immutable
archive created for that build.  Frontend edits therefore remain HMR-driven;
backend edits require another ``build`` or ``up`` invocation.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid


DEFAULT_COMPOSE_PROJECT = "fullmag-master"
STORAGE_PROFILE = "docker-all-gpu"
DEFAULT_IMAGE = "fullmag/fullmag-dev:local"
DEFAULT_BASE_IMAGE = "fullmag/development-base:local"
COMPOSE_BUILD_FILE = "compose.backend-build.yaml"
COMPOSE_RUNTIME_FILE = "compose.dev.yaml"
TOOLCHAIN_BOOTSTRAP_RECEIPT = "index/docker-toolchain-bootstrap.json"
TOOLCHAIN_MANIFEST_PATH = "/opt/fullmag-deps/share/fullmag/dependency-versions.json"
TOOLCHAIN_MANIFEST_SCHEMA = "fullmag.docker.fem-gpu-dependencies.v1"
DEVELOPMENT_BASE_CONTEXT_SCHEMA = "fullmag.direct-compose.development-base-context.v1"
DEVELOPMENT_IMAGE_SCHEMA = "fullmag.direct-compose.development-image.v1"
RUNTIME_IMAGE_CONTEXT_SCHEMA = "fullmag.direct-compose.runtime-image-context.v1"
BASE_CONTEXT_FILES = (
    ("Dockerfile.dev", "docker/all-in-one/Dockerfile.dev"),
    ("entrypoint.py", "docker/all-in-one/entrypoint.py"),
    ("windows_folder_probe.py", "docker/all-in-one/windows_folder_probe.py"),
    ("runtime_service.py", "docker/all-in-one/runtime_service.py"),
    ("frontend_dev.py", "docker/all-in-one/frontend_dev.py"),
    ("healthcheck.py", "docker/all-in-one/healthcheck.py"),
    ("docker_startup_script.py", "scripts/docker_startup_script.py"),
    ("fullmag_storage.py", "scripts/fullmag_storage.py"),
)
RUNTIME_IMAGE_CONTEXT_FILES = (
    ("Dockerfile.backend", "docker/all-in-one/Dockerfile.backend"),
    ("backend_dev.py", "docker/all-in-one/backend_dev.py"),
    ("backend_source.py", "docker/all-in-one/backend_source.py"),
)
REQUIRED_LANES = ("fdm-cpu", "fdm-gpu", "fem-cpu", "fem-gpu")
BUILD_PROFILE_TO_CARGO_PROFILE = {
    "dev": "backend-dev",
    "release": "release",
}
DEFAULT_BUILD_PROFILE = "dev"
SUPPORTED_CARGO_PROFILES = frozenset(BUILD_PROFILE_TO_CARGO_PROFILE.values())
BACKEND_CARGO_PROFILE = BUILD_PROFILE_TO_CARGO_PROFILE[DEFAULT_BUILD_PROFILE]
REQUIRED_STARTUP_HELPERS = (
    "docker_startup_script.py",
    "fullmag_storage.py",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class DirectDockerError(RuntimeError):
    """A direct Docker build or launch could not be admitted safely."""


class DirectDockerOutcomeUnknown(DirectDockerError):
    """The Docker client timed out while the daemon may still own resources."""


def _fail(message: str) -> DirectDockerError:
    return DirectDockerError(message)


def _cargo_profile_for_build(profile: str) -> str:
    try:
        cargo_profile = BUILD_PROFILE_TO_CARGO_PROFILE[profile]
    except (KeyError, TypeError) as error:
        allowed = ", ".join(sorted(BUILD_PROFILE_TO_CARGO_PROFILE))
        raise _fail(f"build profile must be one of: {allowed}") from error
    return cargo_profile


def _validate_cargo_profile(profile: str) -> str:
    if profile not in SUPPORTED_CARGO_PROFILES:
        allowed = ", ".join(sorted(SUPPORTED_CARGO_PROFILES))
        raise _fail(f"backend Cargo profile must be one of: {allowed}")
    return profile


def _repo_default() -> Path:
    return Path(__file__).resolve().parents[1]


def _require_native_windows() -> None:
    if os.name != "nt":
        raise _fail(
            "direct Docker Compose development must run with native Windows Python; "
            "invoke it from PowerShell, not from WSL"
        )


def _docker_argv(arguments: Sequence[object]) -> list[str]:
    command = ["docker"]
    if os.name == "nt":
        command.extend(("--context", "desktop-linux"))
    return command + [str(value) for value in arguments]


def _docker_capture(*arguments: object, timeout: int = 60,
                    environment: Mapping[str, str] | None = None,
                    combined: bool = False) -> str:
    command = _docker_argv(arguments)
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=None if environment is None else {**os.environ, **dict(environment)},
        )
    except subprocess.TimeoutExpired as error:
        raise DirectDockerOutcomeUnknown(
            f"Docker client timed out after {timeout}s; daemon ownership is unknown: "
            + " ".join(command)
        ) from error
    output = result.stdout + result.stderr if combined else result.stdout
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        raise _fail(message or f"Docker command failed ({result.returncode}): {' '.join(command)}")
    return output.strip()


def _docker_live(log_path: Path, *arguments: object, timeout: int,
                 environment: Mapping[str, str] | None = None) -> None:
    """Run a mutating Docker command while teeing compiler output to host storage."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = _docker_argv(arguments)
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=None if environment is None else {**os.environ, **dict(environment)},
        )
    except OSError as error:
        raise _fail(f"cannot start Docker client: {error}") from error

    deadline = time.monotonic() + timeout
    try:
        with log_path.open("w", encoding="utf-8", newline="") as log:
            assert process.stdout is not None
            for line in process.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log.write(line)
                log.flush()
                if time.monotonic() > deadline:
                    raise subprocess.TimeoutExpired(command, timeout)
        remaining = max(0.0, deadline - time.monotonic())
        try:
            exit_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise DirectDockerOutcomeUnknown(
                f"Docker client timed out after {timeout}s; daemon ownership is unknown: "
                + " ".join(command)
            ) from error
    except subprocess.TimeoutExpired as error:
        # Do not issue a second Docker mutation after an unconfirmed timeout.
        # Releasing only this client leaves the daemon-owned build/container for
        # inspection and keeps the run root as evidence.
        try:
            process.kill()
        except OSError:
            pass
        raise DirectDockerOutcomeUnknown(
            f"Docker client timed out after {timeout}s; daemon ownership is unknown: "
            + " ".join(command)
        ) from error
    if exit_code:
        raise _fail(f"Docker command failed with exit code {exit_code}; see {log_path}")


def _read_json_output(output: str, label: str) -> object:
    candidates = [output.strip()]
    candidates.extend(line.strip() for line in reversed(output.splitlines()))
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise _fail(f"{label} did not return JSON")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _sha256_file(path: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise _fail(f"{label} is not a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> tuple[dict[str, object], bytes]:
    if path.is_symlink() or not path.is_file():
        raise _fail(f"{label} is not a regular file: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _fail(f"{label} is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise _fail(f"{label} must be a JSON object: {path}")
    return value, raw


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _inspect_image(reference: str) -> tuple[str, dict[str, object]]:
    raw = _docker_capture("image", "inspect", reference, timeout=60)
    value = _read_json_output(raw, "docker image inspect")
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise _fail("docker image inspect did not return one image")
    document = value[0]
    image_id = document.get("Id")
    if not isinstance(image_id, str) or not IMAGE_ID_RE.fullmatch(image_id):
        raise _fail("Docker image has no immutable sha256 identity")
    config = document.get("Config")
    if not isinstance(config, dict) or config.get("Volumes") not in (None, {}):
        raise _fail("direct development image must not declare anonymous volumes")
    return image_id, document


def _image_reference_present(reference: str) -> bool:
    try:
        _docker_capture("image", "inspect", reference, timeout=60)
    except DirectDockerOutcomeUnknown:
        raise
    except DirectDockerError:
        return False
    return True


def _image_file(image: str, path: str) -> bytes:
    command = _docker_argv(
        ("run", "--rm", "--pull", "never", "--network", "none", "--read-only",
         "--entrypoint", "/bin/cat", image, path)
    )
    try:
        result = subprocess.run(command, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired as error:
        raise DirectDockerOutcomeUnknown(
            f"Docker helper read timed out; daemon ownership is unknown: {' '.join(command)}"
        ) from error
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise _fail(message or f"cannot read {path} from development image")
    return bytes(result.stdout)


def _image_helper_inventory(image: str, destination: Path) -> dict[str, str]:
    destination.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for name in REQUIRED_STARTUP_HELPERS:
        data = _image_file(image, "/opt/fullmag/" + name)
        if not data or len(data) > 4 * 1024 * 1024:
            raise _fail(f"development image helper is missing or oversized: {name}")
        path = destination / name
        path.write_bytes(data)
        try:
            path.chmod(0o444)
        except OSError:
            pass
        hashes[name] = _sha256_bytes(data)
    return hashes


def _copy_owned_context_file(source: Path, destination: Path) -> str:
    """Copy one regular helper into the frozen Docker build context."""

    if source.is_symlink() or not source.is_file():
        raise _fail(f"development base input is not a regular file: {source}")
    before = source.lstat()
    data = source.read_bytes()
    after = source.lstat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
    ):
        raise _fail(f"development base input changed during capture: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not destination.is_file() or destination.read_bytes() != data:
            raise _fail(f"development base context already contains different input: {destination}")
        return _sha256_bytes(data)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.chmod(0o444)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return _sha256_bytes(data)


def _development_base_context(repo: Path, run_root: Path, toolchain_id: str,
                              toolchain_manifest: Mapping[str, object]) -> dict[str, object]:
    context = run_root / "development-base-context"
    context.mkdir(mode=0o700, parents=True, exist_ok=False)
    files: dict[str, str] = {}
    for destination_name, relative_source in BASE_CONTEXT_FILES:
        files[destination_name] = _copy_owned_context_file(
            repo / relative_source,
            context / destination_name,
        )
    manifest_sha256 = _sha256_bytes(_canonical_json(toolchain_manifest))
    identity = {
        "schema": DEVELOPMENT_BASE_CONTEXT_SCHEMA,
        "toolchain_image_id": toolchain_id,
        "toolchain_manifest_sha256": manifest_sha256,
        "files": files,
    }
    context_sha256 = _sha256_bytes(_canonical_json(identity))
    receipt = {**identity, "context_sha256": context_sha256}
    _write_json(run_root / "development-base-context.json", receipt)
    return {
        "root": str(context),
        "toolchain_image_id": toolchain_id,
        "context_sha256": context_sha256,
        "toolchain_manifest_sha256": manifest_sha256,
        "helper_hashes": files,
        "receipt": str(run_root / "development-base-context.json"),
    }


def _runtime_image_context(repo: Path) -> dict[str, object]:
    """Hash the files copied by Dockerfile.backend before reusing an image."""

    files: dict[str, str] = {}
    for name, relative_source in RUNTIME_IMAGE_CONTEXT_FILES:
        source = repo / relative_source
        if source.is_symlink() or not source.is_file():
            raise _fail(f"runtime image context input is not a regular file: {source}")
        before = source.lstat()
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        after = source.lstat()
        signature = lambda metadata: (
            metadata.st_dev, metadata.st_ino, metadata.st_size,
            metadata.st_mtime_ns, metadata.st_ctime_ns,
        )
        if signature(before) != signature(after):
            raise _fail(f"runtime image context input changed during capture: {source}")
        files[name] = digest.hexdigest()
    identity = {"schema": RUNTIME_IMAGE_CONTEXT_SCHEMA, "files": files}
    return {**identity, "context_sha256": _sha256_bytes(_canonical_json(identity))}


def _image_labels(document: Mapping[str, object]) -> dict[str, str]:
    config = document.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        return {}
    return {str(key): str(value) for key, value in labels.items() if isinstance(key, str)}


def _toolchain_setup_message(detail: str) -> DirectDockerError:
    return _fail(
        f"{detail}; Docker will not pull a FEM/GPU toolchain automatically. "
        "Run `just docker-dev-toolchain` in the native Windows checkout first."
    )


def _bootstrap_toolchain_reference(layout: Mapping[str, object]) -> str | None:
    from fullmag_storage import validate_path

    root = Path(str(layout["storage_root"]))
    path = validate_path(root / TOOLCHAIN_BOOTSTRAP_RECEIPT, root, "toolchain bootstrap receipt")
    if not path.is_file() or path.is_symlink():
        return None
    receipt, _raw = _read_json(path, "toolchain bootstrap receipt")
    if receipt.get("state") != "built":
        raise _toolchain_setup_message(
            f"toolchain bootstrap receipt is not ready: {receipt.get('state')!r}"
        )
    reference = receipt.get("image") or receipt.get("image_id")
    if not isinstance(reference, str) or not reference.strip():
        raise _toolchain_setup_message("toolchain bootstrap receipt has no configured image")
    return reference


def _configured_toolchain_reference(args: argparse.Namespace,
                                    layout: Mapping[str, object]) -> str:
    reference = (
        args.toolchain_image
        or os.environ.get("FULLMAG_TOOLCHAIN_IMAGE")
        or _bootstrap_toolchain_reference(layout)
    )
    if not isinstance(reference, str) or not reference.strip():
        raise _toolchain_setup_message("no local FEM/GPU toolchain image is configured")
    return reference


def _preflight_dependency_image(image_id: str) -> tuple[dict[str, object], str]:
    """Use the shared runtime preflight for one immutable dependency image."""

    try:
        from fullmag_docker_runtime import DockerOutcomeUnknown, _preflight_toolchain_image
        manifest = _preflight_toolchain_image(image_id)
    except DockerOutcomeUnknown as error:
        raise DirectDockerOutcomeUnknown(
            f"toolchain manifest probe timed out; daemon ownership is unknown: {image_id}"
        ) from error
    except Exception as error:
        raise _toolchain_setup_message(
            f"toolchain image {image_id} failed the dependency manifest preflight"
        ) from error
    if not isinstance(manifest, dict) or manifest.get("schema") != TOOLCHAIN_MANIFEST_SCHEMA:
        raise _toolchain_setup_message("toolchain dependency manifest schema is unsupported")
    return manifest, _sha256_bytes(_canonical_json(manifest))


def _direct_image_tag(reference: str, kind: str, context_sha256: str) -> str:
    base = reference.split("@", 1)[0]
    last_slash = base.rfind("/")
    colon = base.rfind(":")
    repository = base[:colon] if colon > last_slash else base
    if not repository or repository == "sha256":
        repository = "fullmag/fullmag-dev" if kind == "runtime" else "fullmag/development-base"
    return f"{repository}:direct-{kind}-{context_sha256[:20]}"


def _image_metadata_path(layout: Mapping[str, object], reference: str) -> Path:
    from fullmag_storage import validate_path

    root = Path(str(layout["storage_root"]))
    index = validate_path(root / "index", root, "Docker development image index")
    index.mkdir(parents=True, exist_ok=True)
    name = "docker-dev-image-" + _sha256_bytes(reference.encode("utf-8")) + ".json"
    return validate_path(index / name, root, "Docker development image receipt")


def _read_image_metadata(layout: Mapping[str, object], reference: str) -> dict[str, object] | None:
    path = _image_metadata_path(layout, reference)
    if not path.exists():
        return None
    value, _raw = _read_json(path, "Docker development image receipt")
    if value.get("schema") != DEVELOPMENT_IMAGE_SCHEMA:
        raise _fail(f"Docker development image receipt schema is unsupported: {path}")
    return value


def _write_image_metadata(layout: Mapping[str, object], reference: str,
                          value: Mapping[str, object]) -> Path:
    path = _image_metadata_path(layout, reference)
    _write_json(path, value)
    return path


def _validate_development_base(reference: str, *, expected_toolchain_id: str | None = None,
                               expected_context_sha256: str | None = None) -> dict[str, object]:
    image_id, document = _inspect_image(reference)
    labels = _image_labels(document)
    if labels.get("org.fullmag.runtime") != "docker-all-gpu-v1":
        raise _fail("development base image is not a Fullmag all-in-Docker runtime")
    if labels.get("org.fullmag.development") != "source-bind-v1":
        raise _fail("development base image is not the source-bind development image")
    toolchain_id = labels.get("org.fullmag.toolchain.image-id")
    if not isinstance(toolchain_id, str) or not IMAGE_ID_RE.fullmatch(toolchain_id):
        raise _fail("development base image has no immutable toolchain label")
    if expected_toolchain_id is not None and toolchain_id != expected_toolchain_id:
        raise _fail("development base image toolchain label differs from the requested image")
    manifest, manifest_sha256 = _preflight_dependency_image(image_id)
    context_sha256 = labels.get("org.fullmag.direct-development.context-sha256")
    if expected_context_sha256 is not None and context_sha256 != expected_context_sha256:
        raise _fail(
            "development base image context label differs; the existing image will not be replaced"
        )
    return {
        "reference": reference,
        "image_id": image_id,
        "labels": labels,
        "toolchain_image_id": toolchain_id,
        "toolchain_manifest": manifest,
        "toolchain_manifest_sha256": manifest_sha256,
        "context_sha256": context_sha256,
        "built": False,
    }


def _development_base_metadata_matches(metadata: Mapping[str, object] | None,
                                       base: Mapping[str, object],
                                       toolchain_id: str,
                                       context: Mapping[str, object]) -> bool:
    """Require a receipt that describes this exact frozen base context."""

    if not isinstance(metadata, Mapping):
        return False
    context_sha256 = context.get("context_sha256")
    manifest_sha256 = context.get("toolchain_manifest_sha256")
    helper_hashes = context.get("helper_hashes")
    recorded_context = metadata.get("context")
    return (
        metadata.get("schema") == DEVELOPMENT_IMAGE_SCHEMA
        and metadata.get("kind") == "development-base"
        and metadata.get("image_id") == base.get("image_id")
        and metadata.get("base_image_id") == toolchain_id
        and metadata.get("toolchain_image_id") == toolchain_id
        and metadata.get("toolchain_manifest_sha256") == manifest_sha256
        and metadata.get("context_sha256") == context_sha256
        and isinstance(recorded_context, Mapping)
        and recorded_context.get("context_sha256") == context_sha256
        and recorded_context.get("toolchain_manifest_sha256") == manifest_sha256
        and recorded_context.get("helper_hashes") == helper_hashes
    )


def _verify_development_base_context(context: Mapping[str, object]) -> None:
    """Verify the frozen Docker context before publishing an image receipt."""

    root_value = context.get("root")
    helper_hashes = context.get("helper_hashes")
    context_sha256 = context.get("context_sha256")
    manifest_sha256 = context.get("toolchain_manifest_sha256")
    if (not isinstance(root_value, str) or not isinstance(helper_hashes, Mapping)
            or not isinstance(context_sha256, str) or not isinstance(manifest_sha256, str)):
        raise _fail("development base context receipt is incomplete")
    root = Path(root_value)
    observed: dict[str, str] = {}
    for name, expected in helper_hashes.items():
        if not isinstance(name, str) or not isinstance(expected, str):
            raise _fail("development base context helper inventory is malformed")
        observed[name] = _sha256_file(root / name, "development base context helper")
    if observed != dict(helper_hashes):
        raise _fail("development base context changed before image receipt publication")
    identity = {
        "schema": DEVELOPMENT_BASE_CONTEXT_SCHEMA,
        "toolchain_image_id": context.get("toolchain_image_id"),
        "toolchain_manifest_sha256": manifest_sha256,
        "files": observed,
    }
    if _sha256_bytes(_canonical_json(identity)) != context_sha256:
        raise _fail("development base context digest no longer matches its frozen inputs")


def _ensure_development_base(args: argparse.Namespace, repo: Path,
                             layout: Mapping[str, object], run_root: Path) -> dict[str, object]:
    """Admit an exact base context or derive one from the selected toolchain."""

    requested = os.environ.get("FULLMAG_DEVELOPMENT_BASE_IMAGE", DEFAULT_BASE_IMAGE)
    toolchain_reference = _configured_toolchain_reference(args, layout)
    try:
        toolchain_id, _ = _inspect_image(toolchain_reference)
    except DirectDockerOutcomeUnknown:
        raise
    except DirectDockerError as error:
        raise _toolchain_setup_message(
            f"configured toolchain image is unavailable locally: {toolchain_reference}"
        ) from error
    toolchain_manifest, toolchain_manifest_sha256 = _preflight_dependency_image(toolchain_id)
    context_info = _development_base_context(repo, run_root, toolchain_id, toolchain_manifest)
    context_sha256 = str(context_info["context_sha256"])

    # A shared tag may point at an older development base.  It is reusable only
    # when its image label and durable receipt both describe this exact helper
    # context.  Otherwise it remains an immutable parent candidate at most;
    # the requested tag is never retagged or replaced.
    if _image_reference_present(requested):
        try:
            existing = _validate_development_base(
                requested,
                expected_toolchain_id=toolchain_id,
                expected_context_sha256=context_sha256,
            )
            metadata = _read_image_metadata(layout, requested)
        except DirectDockerOutcomeUnknown:
            raise
        except DirectDockerError:
            existing = None
            metadata = None
        if (existing is not None
                and _development_base_metadata_matches(
                    metadata, existing, toolchain_id, context_info
                )):
            existing["context"] = context_info
            existing["built"] = False
            existing["toolchain_manifest"] = toolchain_manifest
            existing["toolchain_manifest_sha256"] = toolchain_manifest_sha256
            return existing

    # Always build FROM the immutable image selected by the operator or the
    # bootstrap receipt.  This also covers the case where that image happens
    # to be an older source-bind development base: the current Dockerfile and
    # helper context must still be copied into a newly derived image.
    toolchain_base = f"fullmag/direct-toolchain:{run_root.name}"
    _docker_capture("tag", toolchain_id, toolchain_base, timeout=60)
    aliased_id, _aliased_document = _inspect_image(toolchain_base)
    if aliased_id != toolchain_id:
        raise _fail("run-scoped toolchain alias changed the immutable image identity")

    base_reference = _direct_image_tag(requested, "base", context_sha256)
    if _image_reference_present(base_reference):
        existing = _validate_development_base(
            base_reference,
            expected_toolchain_id=toolchain_id,
            expected_context_sha256=context_sha256,
        )
        metadata = _read_image_metadata(layout, base_reference)
        if not _development_base_metadata_matches(
                metadata, existing, toolchain_id, context_info):
            raise _fail("existing derived development base receipt does not match the image")
        existing["context"] = context_info
        existing["toolchain_build_reference"] = toolchain_base
        existing["built"] = False
        return existing

    iid_path = run_root / "development-base-image-id.txt"
    _docker_live(
        run_root / "development-base-build.log",
        "build", "--pull=false", "--network", "none", "--file",
        str(Path(str(context_info["root"])) / "Dockerfile.dev"),
        "--build-arg", "RUNTIME_BASE=" + toolchain_base,
        "--build-arg", "FULLMAG_TOOLCHAIN_IMAGE_ID=" + toolchain_id,
        "--label", "org.fullmag.direct-development.context-schema=" + DEVELOPMENT_BASE_CONTEXT_SCHEMA,
        "--label", "org.fullmag.direct-development.context-sha256=" + context_sha256,
        "--iidfile", str(iid_path), "--tag", base_reference,
        str(context_info["root"]),
        timeout=4 * 60 * 60,
    )
    try:
        built_id = iid_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise _fail("development base build did not publish an image ID") from error
    if not IMAGE_ID_RE.fullmatch(built_id):
        raise _fail("development base build published an invalid image ID")
    _verify_development_base_context(context_info)
    base = _validate_development_base(
        base_reference,
        expected_toolchain_id=toolchain_id,
        expected_context_sha256=context_sha256,
    )
    if base["image_id"] != built_id:
        raise _fail("development base image ID changed after build")
    if base.get("toolchain_manifest_sha256") != toolchain_manifest_sha256:
        raise _fail("development base dependency manifest differs from the selected toolchain")
    base["context"] = context_info
    base["toolchain_build_reference"] = toolchain_base
    base["built"] = True
    base["toolchain_manifest_sha256"] = toolchain_manifest_sha256
    _write_json(run_root / "development-base-receipt.json", base)
    _write_image_metadata(layout, base_reference, {
        "schema": DEVELOPMENT_IMAGE_SCHEMA,
        "kind": "development-base",
        "image_reference": base_reference,
        "image_id": base["image_id"],
        "base_image_id": toolchain_id,
        "toolchain_image_id": toolchain_id,
        "toolchain_manifest_sha256": toolchain_manifest_sha256,
        "toolchain_build_reference": toolchain_base,
        "context_sha256": context_sha256,
        "context": context_info,
    })
    return base


def _select_source(repo: Path, source_root: Path | None) -> tuple[Path, dict[str, object]]:
    from docker_development_inputs import select_checkout
    from fullmag_storage import initialize, resolve_layout

    selected = select_checkout(repo, source_root).resolve(strict=True)
    if not selected.is_dir() or selected.is_symlink():
        raise _fail(f"selected source is not a real checkout: {selected}")
    layout = resolve_layout(selected, STORAGE_PROFILE)
    initialize(layout)
    return selected, layout


def _compose_identity(layout: Mapping[str, object]) -> dict[str, str]:
    from docker_compose_identity import compose_project_identity

    return compose_project_identity(layout)


def _compose_identity_environment(layout: Mapping[str, object]) -> dict[str, str]:
    identity = _compose_identity(layout)
    return {
        "FULLMAG_COMPOSE_PROJECT": identity["project_name"],
        "FULLMAG_COMPOSE_NETWORK": identity["network_name"],
        "FULLMAG_SOURCE_PROJECT_ID": identity["project_id"],
        "FULLMAG_SOURCE_WORKTREE_ID": identity["worktree_id"],
        "FULLMAG_SOURCE_CHECKOUT_KIND": identity["checkout_kind"],
    }


def _new_run_root(layout: Mapping[str, object]) -> tuple[str, Path]:
    from fullmag_storage import validate_path

    build_root = Path(str(layout["build_root"]))
    build_storage = Path(str(layout["build_storage_root"]))
    run_id = uuid.uuid4().hex
    parent = validate_path(build_root / "direct-compose", build_storage, "direct Compose build root")
    parent.mkdir(parents=True, exist_ok=True)
    root = validate_path(parent / run_id, build_storage, "direct Compose run root")
    root.mkdir(mode=0o700)
    return run_id, root


def _direct_compose_files(repo: Path, cache: Mapping[str, object] | None = None) -> list[Path]:
    backend = repo / COMPOSE_BUILD_FILE
    runtime = repo / COMPOSE_RUNTIME_FILE
    if backend.is_file() and runtime.is_file():
        # The versioned backend-build overlay is the direct topology.  It is
        # layered over the normal two-service development contract so the
        # builder and runtime share exactly one image/service definition.
        files = [runtime, backend]
    else:
        missing = [str(path) for path in (backend, runtime) if not path.is_file()]
        raise _fail("direct Compose definition is missing: " + ", ".join(missing))
    if cache is not None:
        overlay = cache.get("compose_overlay")
        if not isinstance(overlay, str) or not Path(overlay).is_file():
            raise _fail("backend build cache did not return its Compose overlay")
        files.append(Path(overlay))
    return files


def _compose_prefix(repo: Path, files: Sequence[Path], project: str = DEFAULT_COMPOSE_PROJECT) -> list[str]:
    arguments: list[str] = [
        "compose", "--project-name", project, "--project-directory", str(repo),
    ]
    for path in files:
        arguments.extend(("-f", str(path)))
    return arguments


def _compose_config(repo: Path, files: Sequence[Path], environment: Mapping[str, str], *,
                    project: str = DEFAULT_COMPOSE_PROJECT) -> dict[str, object]:
    raw = _docker_capture(
        *_compose_prefix(repo, files, project), "config", "--format", "json",
        timeout=120, environment=environment,
    )
    value = _read_json_output(raw, "direct Compose config")
    if not isinstance(value, dict) or not isinstance(value.get("services"), dict):
        raise _fail("direct Compose config has no service map")
    services = value["services"]
    if "backend" not in services or not isinstance(services["backend"], dict):
        raise _fail("direct Compose config has no backend service")
    return value


def _service_tokens(service: Mapping[str, object]) -> list[str]:
    tokens: list[str] = []
    for key in ("entrypoint", "command"):
        value = service.get(key)
        if isinstance(value, str):
            tokens.append(value)
        elif isinstance(value, list):
            tokens.extend(str(item) for item in value)
    return tokens


def _mount_targets(service: Mapping[str, object]) -> set[str]:
    result: set[str] = set()
    volumes = service.get("volumes")
    if not isinstance(volumes, list):
        return result
    for volume in volumes:
        if isinstance(volume, dict) and isinstance(volume.get("target"), str):
            result.add(volume["target"])
        elif isinstance(volume, str):
            target = volume.rsplit(":", 1)[-1].split(":", 1)[0]
            if target.startswith("/"):
                result.add(target)
    return result


def _prepare_override(service: Mapping[str, object]) -> list[str]:
    tokens = _service_tokens(service)
    expected = {"/input/backend-source.tar", "/input/manifest.json"}
    output_targets = {"/output", "/opt/fullmag/package"}
    if "prepare" in tokens and expected.issubset(set(tokens)) and output_targets.intersection(tokens):
        # The versioned compose file owns the worker's positional contract.
        return []
    # docker/all-in-one/backend_dev.py is the current worker implementation.
    # Its flags are intentionally fixed here; callers cannot supply a shell
    # command or alter the CUDA/FEM feature set.
    return [
        "prepare",
        "--source-tar", "/input/backend-source.tar",
        "--manifest", "/input/manifest.json",
        "--output", "/opt/fullmag/package",
        "--build-root", "/build",
    ]


def _validate_runtime_image(reference: str, expected_toolchain_id: str,
                            layout: Mapping[str, object], expected_context_sha256: str | None,
                            expected_base_id: str,
                            expected_label_ids: Sequence[str] = (),
                            expected_backend_context_sha256: str | None = None,
                            expected_runtime_context_sha256: str | None = None,
                            require_receipt: bool = True) -> tuple[str, dict[str, object]]:
    image_id, document = _inspect_image(reference)
    labels = _image_labels(document)
    if labels.get("org.fullmag.runtime") != "docker-all-gpu-v1":
        raise _fail("development image is not a Fullmag all-in-Docker runtime")
    if labels.get("org.fullmag.development") != "source-bind-v1":
        raise _fail("development image is not the source-bind image")
    accepted_label_ids = {expected_toolchain_id}
    accepted_label_ids.update(
        value for value in expected_label_ids
        if isinstance(value, str) and IMAGE_ID_RE.fullmatch(value)
    )
    if labels.get("org.fullmag.toolchain.image-id") not in accepted_label_ids:
        raise _fail("development image toolchain label differs from the admitted base")
    _image_file(reference, "/opt/fullmag/backend_dev.py")
    metadata = _read_image_metadata(layout, reference)
    if metadata is None:
        if require_receipt:
            raise _fail("development image has no pinned direct-build receipt")
    elif (
            metadata.get("image_id") != image_id
            or metadata.get("toolchain_image_id") != expected_toolchain_id
            or metadata.get("base_image_id") != expected_base_id
            or metadata.get("context_sha256") != expected_context_sha256
            or (expected_backend_context_sha256 is not None
                and metadata.get("backend_context_sha256") != expected_backend_context_sha256)
            or (expected_runtime_context_sha256 is not None
                and metadata.get("runtime_context_sha256") != expected_runtime_context_sha256)):
        raise _fail("development image receipt does not match the admitted base")
    return image_id, document


def _runtime_image_reference(args: argparse.Namespace, repo: Path,
                            environment: dict[str, str], run_root: Path,
                            layout: Mapping[str, object],
                            base_info: Mapping[str, object],
                            project: str = DEFAULT_COMPOSE_PROJECT) -> tuple[str, str, dict[str, object], bool]:
    requested = (
        args.image
        or os.environ.get("FULLMAG_DEV_IMAGE")
        or DEFAULT_IMAGE
    )
    toolchain_id = str(base_info["toolchain_image_id"])
    base_id = str(base_info["image_id"])
    base_labels = base_info.get("labels")
    inherited_label = (
        base_labels.get("org.fullmag.toolchain.image-id")
        if isinstance(base_labels, Mapping) else None
    )
    expected_label_ids = (inherited_label,) if isinstance(inherited_label, str) else ()
    context_sha256 = base_info.get("context_sha256")
    context_sha256 = context_sha256 if isinstance(context_sha256, str) else None
    backend_context = _runtime_image_context(repo)
    backend_context_sha256 = str(backend_context["context_sha256"])
    runtime_context_identity = {
        "schema": RUNTIME_IMAGE_CONTEXT_SCHEMA,
        "base_context_sha256": context_sha256,
        "base_image_id": base_id,
        "backend_context_sha256": backend_context_sha256,
        "toolchain_image_id": toolchain_id,
    }
    runtime_context_sha256 = _sha256_bytes(_canonical_json(runtime_context_identity))
    existing = _image_reference_present(requested)
    if existing:
        try:
            image_id, document = _validate_runtime_image(
                requested, toolchain_id, layout, context_sha256, base_id,
                expected_label_ids,
                backend_context_sha256, runtime_context_sha256,
            )
        except DirectDockerOutcomeUnknown:
            raise
        except DirectDockerError:
            image_id = None
            document = None
        else:
            return requested, image_id, document, False
        tag_seed = runtime_context_sha256
        image_reference = _direct_image_tag(requested, "runtime", tag_seed)
    else:
        image_reference = requested

    if _image_reference_present(image_reference):
        try:
            image_id, document = _validate_runtime_image(
                image_reference, toolchain_id, layout, context_sha256, base_id,
                expected_label_ids,
                backend_context_sha256, runtime_context_sha256,
            )
        except DirectDockerOutcomeUnknown:
            raise
        except DirectDockerError as error:
            raise _fail(
                f"existing derived development image will not be replaced: {image_reference}"
            ) from error
        return image_reference, image_id, document, False

    build_environment = dict(environment)
    build_environment.update(
        FULLMAG_DEV_IMAGE=image_reference,
        FULLMAG_RELEASE_IMAGE=image_reference,
        FULLMAG_TOOLCHAIN_IMAGE=toolchain_id,
        FULLMAG_TOOLCHAIN_IMAGE_ID=toolchain_id,
        FULLMAG_DEVELOPMENT_BASE_IMAGE=str(base_info["reference"]),
    )
    _docker_live(
        run_root / "image-build.log",
        *_compose_prefix(repo, [repo / COMPOSE_RUNTIME_FILE], project),
        "build", "--pull=false", "--progress=plain", "backend",
        timeout=4 * 60 * 60,
        environment=build_environment,
    )
    if _runtime_image_context(repo) != backend_context:
        raise _fail("backend image helpers changed while Docker was building; image retained without receipt")
    image_id, document = _validate_runtime_image(
        image_reference, toolchain_id, layout, context_sha256, base_id,
        expected_label_ids,
        backend_context_sha256, runtime_context_sha256,
        require_receipt=False,
    )
    _preflight_dependency_image(image_id)
    metadata = {
        "schema": DEVELOPMENT_IMAGE_SCHEMA,
        "kind": "development-runtime",
        "image_reference": image_reference,
        "image_id": image_id,
        "base_image_id": base_id,
        "toolchain_image_id": toolchain_id,
        "toolchain_manifest_sha256": base_info.get("toolchain_manifest_sha256"),
        "context_sha256": context_sha256,
        "context": base_info.get("context"),
        "backend_context_schema": RUNTIME_IMAGE_CONTEXT_SCHEMA,
        "backend_context_sha256": backend_context_sha256,
        "backend_context": backend_context,
        "runtime_context_sha256": runtime_context_sha256,
        "runtime_context_identity": runtime_context_identity,
    }
    metadata_path = _write_image_metadata(layout, image_reference, metadata)
    _write_json(run_root / "development-image-receipt.json", {
        **metadata,
        "receipt_path": str(metadata_path),
    })
    return image_reference, image_id, document, True


def _prepare_backend_cache(layout: Mapping[str, object], repo: Path, image_id: str,
                           run_root: Path, selected: Path, toolchain_id: str) -> dict[str, object]:
    """Use the versioned project backend-cache helper."""

    from docker_backend_cache import prepare
    profile = prepare(
        layout,
        repo,
        image_id,
        run_root,
        _docker_capture,
        source_root=selected,
        toolchain_image=toolchain_id,
    )
    if not isinstance(profile, Mapping) or profile.get("state") != "ready":
        raise _fail("backend build cache did not reach ready state")
    return dict(profile)


def _environment(layout: Mapping[str, object], selected: Path, run_root: Path,
                 source_bundle: Mapping[str, object], package: Path, image_ref: str,
                 image_id: str, toolchain_id: str, cache: Mapping[str, object],
                 base_reference: str, cargo_profile: str) -> dict[str, str]:
    cargo_profile = _validate_cargo_profile(cargo_profile)
    archive = Path(str(source_bundle["archive_path"]))
    manifest = Path(str(source_bundle["manifest_path"]))
    state = run_root / "state"
    state.mkdir(exist_ok=True)
    (run_root / "host-certificate.json").touch(exist_ok=True)
    (run_root / "provenance.json").touch(exist_ok=True)
    (run_root / "development-inputs.json").touch(exist_ok=True)
    package.mkdir(exist_ok=True)
    environment = {
        **_compose_identity_environment(layout),
        "FULLMAG_DEV_IMAGE": image_ref,
        "FULLMAG_RELEASE_IMAGE": image_ref,
        "FULLMAG_RUNTIME_IMAGE_ID": image_id,
        "FULLMAG_TOOLCHAIN_IMAGE": toolchain_id,
        "FULLMAG_TOOLCHAIN_IMAGE_ID": toolchain_id,
        "FULLMAG_BACKEND_CARGO_PROFILE": cargo_profile,
        "FULLMAG_SOURCE_ROOT": str(selected),
        "FULLMAG_BACKEND_SOURCE_TAR": str(archive),
        "FULLMAG_BACKEND_SOURCE_MANIFEST": str(manifest),
        "FULLMAG_BACKEND_PACKAGE": str(package),
        "FULLMAG_DEVELOPMENT_BASE_IMAGE": base_reference,
        "FULLMAG_STATE_ROOT": str(state),
        "FULLMAG_HOST_CERTIFICATE": str(run_root / "host-certificate.json"),
        "FULLMAG_PACKAGE_PROVENANCE": str(run_root / "provenance.json"),
        "FULLMAG_DEVELOPMENT_INPUTS": str(run_root / "development-inputs.json"),
        "FULLMAG_BACKEND_HOSTNAME": "fullmag-direct-backend-" + run_root.name[:12],
        "FULLMAG_PROJECT_STORAGE_ROOT": str(layout["storage_root"]),
        "FULLMAG_BUILD_ROOT": str(layout["build_root"]),
        "FULLMAG_CACHE_ROOT": str(layout["cache_root"]),
        "FULLMAG_RUNTIME_ROOT": str(layout["runtime_root"]),
        "FULLMAG_CARGO_TARGET_DIR": "/build/workspace/.fullmag-build/cargo-targets/direct",
        "FULLMAG_CARGO_TARGET_ROOT": "/build/workspace/.fullmag-build/cargo-targets",
        "CARGO_TARGET_DIR": "/build/workspace/.fullmag-build/cargo-targets/direct",
    }
    cache_environment = cache.get("environment")
    if isinstance(cache_environment, Mapping):
        environment.update({str(key): str(value) for key, value in cache_environment.items()})
    # Keep the source/package identities after the helper environment so the
    # backend-build overlay cannot accidentally inherit a stale host setting.
    environment.update({
        "FULLMAG_BACKEND_SOURCE_TAR": str(archive),
        "FULLMAG_BACKEND_SOURCE_MANIFEST": str(manifest),
        "FULLMAG_BACKEND_PACKAGE": str(package),
        "FULLMAG_SOURCE_ROOT": str(selected),
        "FULLMAG_RUNTIME_IMAGE_ID": image_id,
        "FULLMAG_TOOLCHAIN_IMAGE_ID": toolchain_id,
        "FULLMAG_BACKEND_CARGO_PROFILE": cargo_profile,
    })
    return environment


def _validate_prepare_receipt(package: Path, source_bundle: Mapping[str, object],
                              toolchain_id: str,
                              expected_cargo_profile: str) -> tuple[dict[str, object], bytes]:
    receipt_path = package / "backend-build-receipt.json"
    receipt, raw = _read_json(receipt_path, "backend build receipt")
    if receipt.get("schema") != "fullmag.direct-compose.backend-build-receipt.v1":
        raise _fail("backend worker returned an unsupported build receipt schema")
    if receipt.get("state") != "succeeded" or receipt.get("operation") != "direct-compose-build":
        raise _fail("backend worker did not publish a successful direct build receipt")
    expected_cargo_profile = _validate_cargo_profile(expected_cargo_profile)
    build = receipt.get("build")
    if (not isinstance(build, dict)
            or build.get("cargo_profile") != expected_cargo_profile
            or build.get("cargo_target_profile_dir") != expected_cargo_profile):
        raise _fail(
            f"backend build receipt is not a {expected_cargo_profile} cargo profile build"
        )
    source = receipt.get("source")
    if not isinstance(source, dict):
        raise _fail("backend build receipt has no source identity")
    for key, expected in (
        ("source_digest", source_bundle.get("source_digest")),
        ("resolved_commit", source_bundle.get("resolved_commit")),
        ("source_tar_sha256", source_bundle.get("archive_sha256")),
    ):
        if source.get(key) != expected:
            raise _fail(f"backend build receipt source identity differs: {key}")
    native = receipt.get("native_source_identity")
    if native != source_bundle.get("native_source_identity"):
        raise _fail("backend build receipt native source identity differs from the archive")
    toolchain = receipt.get("toolchain")
    if not isinstance(toolchain, dict) or toolchain.get("image_id") != toolchain_id:
        raise _fail("backend build receipt toolchain image identity differs")
    lanes = receipt.get("execution_lanes")
    if not isinstance(lanes, dict) or set(lanes) != set(REQUIRED_LANES):
        raise _fail("backend build receipt does not attest all four execution lanes")
    if any(not isinstance(lanes[lane], dict) or lanes[lane].get("status") != "compiled"
           for lane in REQUIRED_LANES):
        raise _fail("backend build receipt has an incomplete execution lane")
    return receipt, raw


def _assembly(layout: Mapping[str, object], run_id: str, run_root: Path,
              selected: Path, source_bundle: Mapping[str, object], package: Path,
              image_id: str, toolchain_id: str, prepare_receipt: Mapping[str, object],
              prepare_receipt_bytes: bytes, base_info: Mapping[str, object],
              build_profile: str, expected_cargo_profile: str) -> Path:
    expected_cargo_profile = _validate_cargo_profile(expected_cargo_profile)
    if _cargo_profile_for_build(build_profile) != expected_cargo_profile:
        raise _fail("assembly build profile does not match its Cargo profile")
    from fullmag_docker_runtime import REQUIRED_BINARIES
    from fullmag_storage import atomic_json, validate_path

    context = run_root / "context"
    helper_hashes = _image_helper_inventory(image_id, context)
    observed_image_id, runtime_document = _inspect_image(image_id)
    if observed_image_id != image_id:
        raise _fail("runtime image changed while assembling provenance")
    runtime_labels = _image_labels(runtime_document)
    binary_hashes: dict[str, str] = {}
    for name in REQUIRED_BINARIES:
        binary_hashes[name] = _sha256_file(package / "bin" / name, f"backend binary {name}")
    if not (package / "_fullmag_core.so").is_file():
        raise _fail("backend package has no _fullmag_core.so")
    source_commit = str(source_bundle.get("resolved_commit", ""))
    if not COMMIT_RE.fullmatch(source_commit):
        raise _fail("direct source archive has no canonical commit")
    build_receipt = package / "backend-build-receipt.json"
    if _sha256_bytes(prepare_receipt_bytes) != _sha256_file(build_receipt, "backend build receipt"):
        raise _fail("backend build receipt changed while assembling provenance")
    build = prepare_receipt.get("build")
    if (not isinstance(build, dict)
            or build.get("cargo_profile") != expected_cargo_profile
            or build.get("cargo_target_profile_dir") != expected_cargo_profile):
        raise _fail("backend build receipt profile changed while assembling provenance")
    assembly = {
        "schema": "fullmag.docker-all-image.v1",
        "state": "succeeded",
        "exit_code": 0,
        "qualification": "NOT VERIFIED",
        "build_kind": "direct-compose",
        "direct_source_provenance": "fullmag.docker-backend-source.v1",
        "direct_build_id": run_id,
        "commit": source_commit,
        "source_mode": str(source_bundle.get("source_mode", "snapshot")),
        "source_root": str(selected),
        "source_digest": str(source_bundle["source_digest"]),
        "source_snapshot_sha256": str(source_bundle["source_snapshot_sha256"]),
        "native_source_identity": source_bundle["native_source_identity"],
        "source_archive": {
            "path": str(source_bundle["archive_path"]),
            "manifest_path": str(source_bundle["manifest_path"]),
            "sha256": str(source_bundle["archive_sha256"]),
            "bytes": source_bundle["archive_bytes"],
        },
        # Keep the final runtime image separate from the immutable toolchain
        # base.  The runtime launcher consumes image_id; base_image is the
        # provenance identity passed as the toolchain image to Compose.
        "image_id": image_id,
        "base_image": toolchain_id,
        "toolchain_image_id": toolchain_id,
        "development_base_image": base_info.get("reference"),
        "development_base_image_id": base_info.get("image_id"),
        "development_base_build_reference": base_info.get("toolchain_build_reference"),
        "toolchain_manifest_sha256": base_info.get("toolchain_manifest_sha256"),
        "development_base_context_sha256": base_info.get("context_sha256"),
        "development_base_context": base_info.get("context"),
        "development_base_labels": base_info.get("labels", {}),
        "runtime_image_labels": runtime_labels,
        "runtime_mode": "development_source_bind",
        "build_profile": build_profile,
        "cargo_profile": build["cargo_profile"],
        "cargo_target_profile_dir": build["cargo_target_profile_dir"],
        "package_root": str(validate_path(package, Path(str(layout["build_storage_root"])), "backend package")),
        "binary_hashes": binary_hashes,
        "startup_helper_hashes": helper_hashes,
        "build_receipt_sha256": _sha256_bytes(prepare_receipt_bytes),
        "backend_build_receipt": str(build_receipt),
        "backend_build_receipt_schema": prepare_receipt.get("schema"),
        "output": str(run_root),
        "context": str(context),
    }
    receipt_path = validate_path(run_root / "assembly.json", Path(str(layout["build_storage_root"])), "direct assembly receipt")
    atomic_json(receipt_path, assembly)
    # The runtime binds this exact receipt as /opt/fullmag/provenance.json.
    _write_json(run_root / "provenance.json", assembly)
    return receipt_path


def _compose_stop_hint(container_ids: Sequence[str]) -> str:
    """Return a stop command for the exact Compose file that owns the run."""

    try:
        documents = _read_json_output(
            _docker_capture("inspect", *container_ids, timeout=60),
            "running Fullmag container inspection",
        )
    except DirectDockerError:
        documents = None
    if isinstance(documents, list) and documents:
        configs: tuple[str, ...] | None = None
        working_dir: str | None = None
        compose_project: str | None = None
        valid = True
        for document in documents:
            if not isinstance(document, dict):
                valid = False
                break
            config = document.get("Config")
            labels = config.get("Labels") if isinstance(config, dict) else None
            if not isinstance(labels, dict):
                valid = False
                break
            raw_files = labels.get("com.docker.compose.project.config_files")
            raw_working = labels.get("com.docker.compose.project.working_dir")
            raw_project = labels.get("com.docker.compose.project")
            if (not isinstance(raw_files, str) or not raw_files.strip()
                    or not isinstance(raw_working, str)
                    or not isinstance(raw_project, str)
                    or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", raw_project)):
                valid = False
                break
            # Compose records multiple files as a platform-separated or
            # comma-separated label.  The runtime launcher records its fully
            # resolved compose.json here, so this command needs no shell env.
            files = tuple(item for item in re.split(r"[;,]", raw_files) if item)
            if not files:
                valid = False
                break
            if configs is None:
                configs = files
                working_dir = raw_working
                compose_project = raw_project
            elif configs != files or working_dir != raw_working or compose_project != raw_project:
                valid = False
                break
        if (valid and configs and working_dir and compose_project
                and all(Path(compose_file).suffix.lower() == ".json" for compose_file in configs)):
            parts = [
                "docker", "compose", "--project-name", compose_project,
                "--project-directory", working_dir,
            ]
            for compose_file in configs:
                parts.extend(("-f", compose_file))
            parts.append("down")
            return " ".join(f'"{part}"' if any(character.isspace() for character in part) else part
                            for part in parts)
    # If a foreign/manual container has no trustworthy Compose provenance,
    # stopping only the inspected IDs remains an exact, bounded operation.
    return "docker stop " + " ".join(container_ids)


def _assert_no_running_fullmag(project: str) -> None:
    """Reject all stale containers/networks for the selected Compose group.

    The historical helper name is retained for callers, but the admission
    fence covers stopped containers and orphaned project networks as well as
    running services.  Compose must never silently replace an old identity.
    """

    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project):
        raise _fail("Invalid Compose project name")
    from docker_compose_identity import compose_network_name

    network_name = compose_network_name(project)
    container_ids: set[str] = set()
    for label in ("com.docker.compose.project", "org.fullmag.compose.project"):
        raw = _docker_capture(
            "ps", "--all", "--quiet", "--filter", "label=" + label + "=" + project,
            timeout=60,
        )
        container_ids.update(line.strip() for line in raw.splitlines() if line.strip())
    if container_ids:
        ordered = sorted(container_ids)
        raise _fail(
            "Fullmag Docker containers already exist for project " + project
            + " (running or stopped): " + ", ".join(ordered)
            + "; remove them explicitly with the recorded command: `"
            + _compose_stop_hint(ordered)
            + "` before `up`"
        )

    network_ids: set[str] = set()
    network_filters = (
        "label=com.docker.compose.project=" + project,
        "label=org.fullmag.compose.project=" + project,
        # Catch a stale/manual network with the deterministic Compose name even
        # if someone stripped its labels; Compose must not replace it silently.
        "name=^" + network_name + "$",
    )
    for network_filter in network_filters:
        raw = _docker_capture(
            "network", "ls", "--quiet", "--filter", network_filter,
            timeout=60,
        )
        network_ids.update(line.strip() for line in raw.splitlines() if line.strip())
    if not network_ids:
        return
    ordered_networks = sorted(network_ids)
    try:
        documents = _read_json_output(
            _docker_capture("network", "inspect", *ordered_networks, timeout=60),
            "Fullmag Compose network inspection",
        )
    except DirectDockerError:
        raise
    if not isinstance(documents, list) or len(documents) != len(ordered_networks):
        raise _fail("Docker network identity inspection returned an incomplete document")
    names = []
    for document in documents:
        if not isinstance(document, dict):
            raise _fail("Docker network identity inspection returned an invalid document")
        labels = document.get("Labels")
        if not isinstance(labels, dict) or not any(
            labels.get(label) == project
            for label in ("com.docker.compose.project", "org.fullmag.compose.project")
        ):
            raise _fail("Docker network identity labels could not be verified")
        names.append(str(document.get("Name") or document.get("Id") or "<unknown>"))
    raise _fail(
        "Fullmag Docker project network identity already exists for " + project
        + " (" + ", ".join(names)
        + "); remove the stale network explicitly before `up`"
    )


def _frozen_source_bundle(manifest_path: Path, layout: Mapping[str, object], selected: Path) -> dict[str, object]:
    """Explicitly resume immutable inputs; later checkout edits are not included."""
    from fullmag_storage import validate_path
    from windows_folder_host import read_owned_regular
    from docker_backend_inputs import (
        ARCHIVE_FILENAME, ARCHIVE_MANIFEST_SCHEMA, CAPTURE_ID_RE, MAX_ARCHIVE_BYTES,
        BackendInputError, _validate_source_manifest,
        _validate_native_identity, _canonical_bytes,
    )
    manifest = validate_path(Path(manifest_path), Path(str(layout["build_storage_root"])),
                             "frozen backend source manifest")
    try:
        def unique_object(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError(f"duplicate frozen manifest key: {key}")
                value[key] = item
            return value
        value = json.loads(read_owned_regular(manifest, maximum=64 * 1024 * 1024),
                           object_pairs_hook=unique_object)
        required = {
            "schema", "capture_id", "source_mode", "source_root", "resolved_commit", "source_digest",
            "backend_source_sha256", "source_snapshot_sha256", "native_source_identity", "source_manifest",
            "source_manifest_sha256", "archive_filename", "archive_sha256", "archive_bytes", "created_at",
        }
        if (not isinstance(value, dict) or set(value) != required
                or value.get("schema") != ARCHIVE_MANIFEST_SCHEMA):
            raise ValueError("unsupported frozen source manifest")
        if (not isinstance(value["capture_id"], str)
                or not CAPTURE_ID_RE.fullmatch(value["capture_id"])
                or not isinstance(value["created_at"], str) or not value["created_at"]
                or not isinstance(value["source_root"], str) or not value["source_root"]
                or isinstance(value["archive_bytes"], bool)
                or not isinstance(value["archive_bytes"], int)
                or not 0 < value["archive_bytes"] <= MAX_ARCHIVE_BYTES
                or not isinstance(value["archive_sha256"], str)
                or not SHA256_RE.fullmatch(value["archive_sha256"])):
            raise ValueError("invalid frozen source manifest metadata")
        if Path(value["source_root"]).resolve(strict=True) != selected:
            raise ValueError("frozen source checkout differs from selected live checkout")
        source, _ = _validate_source_manifest(value["source_manifest"])
        _validate_native_identity(value["native_source_identity"], source["resolved_commit"])
        if (value.get("source_digest") != source["source_digest"]
                or value.get("backend_source_sha256") != source["source_digest"]
                or value.get("source_mode") != source["source_mode"]
                or value.get("source_snapshot_sha256") != value["native_source_identity"]["source_snapshot_sha256"]
                or value.get("resolved_commit") != source["resolved_commit"]
                or value.get("source_manifest_sha256") != _sha256_bytes(_canonical_bytes(source))
                or value.get("archive_filename") != ARCHIVE_FILENAME):
            raise ValueError("frozen source manifest identity differs")
        archive = validate_path(manifest.parent / ARCHIVE_FILENAME,
                                Path(str(layout["build_storage_root"])), "frozen backend source archive")
        if (archive.stat().st_size != value.get("archive_bytes")
                or _sha256_file(archive, "frozen source archive") != value.get("archive_sha256")):
            raise ValueError("frozen source archive differs from its manifest")
        return {**value, "archive_path": str(archive), "manifest_path": str(manifest)}
    except (OSError, ValueError, KeyError, TypeError, BackendInputError) as error:
        raise _fail(f"Cannot resume frozen backend inputs: {error}") from error


def build(args: argparse.Namespace) -> Path:
    _require_native_windows()
    build_profile = getattr(args, "profile", DEFAULT_BUILD_PROFILE)
    cargo_profile = _cargo_profile_for_build(build_profile)
    repo = Path(args.repo_root).resolve(strict=True)
    selected, layout = _select_source(repo, args.source_root)
    compose_project = _compose_identity(layout)["project_name"]
    run_id, run_root = _new_run_root(layout)
    terminal = {
        "schema": "fullmag.direct-compose-build.v1",
        "state": "building",
        "run_id": run_id,
        "source_root": str(selected),
        "run_root": str(run_root),
        "backend_log": str(run_root / "backend-build.log"),
        "image_log": str(run_root / "image-build.log"),
        "development_base_log": str(run_root / "development-base-build.log"),
        "queue": "not-used",
        "build_profile": build_profile,
        "cargo_profile": cargo_profile,
        "compose_project": compose_project,
    }
    _write_json(run_root / "receipt.json", terminal)

    from fullmag_storage import file_lock, validate_path

    # Direct Docker builds share the canonical heavy slot with every other
    # Fullmag compiler. This route intentionally does not submit a queue job,
    # but it must still serialize image/cache/backend mutations and retain the
    # same durable lock path used by the managed build executor.
    lock_context = None
    try:
        storage_root = Path(str(layout["storage_root"]))
        heavy_lock = validate_path(
            storage_root / "locks" / "fullmag-heavy.lock",
            storage_root,
            "direct Docker heavy build lock",
        )
        lock_context = file_lock(
            heavy_lock,
            "direct Docker Fullmag build",
            wait_timeout_seconds=120,
        )
        lock_context.__enter__()
    except Exception as error:
        terminal.update(
            state=("outcome_unknown_resources_retained"
                   if isinstance(error, DirectDockerOutcomeUnknown)
                   else "failed_resources_retained"),
            exit_code=2,
            error=str(error),
        )
        try:
            _write_json(run_root / "receipt.json", terminal)
        except Exception:
            pass
        raise

    try:
        frozen_bundle = None
        if getattr(args, "source_manifest", None) is not None:
            if args.include_untracked:
                raise _fail("Frozen inputs cannot include additional untracked files")
            frozen_bundle = _frozen_source_bundle(args.source_manifest, layout, selected)
        # Resolve the existing versioned development image before creating any
        # backend cache.  A missing image is built by compose.dev's dedicated
        # Dockerfile.backend; it is never fetched implicitly from a registry.
        placeholder_environment = {
            **_compose_identity_environment(layout),
            "FULLMAG_DEV_IMAGE": args.image or os.environ.get("FULLMAG_DEV_IMAGE", DEFAULT_IMAGE),
            "FULLMAG_RELEASE_IMAGE": args.image or os.environ.get("FULLMAG_DEV_IMAGE", DEFAULT_IMAGE),
            "FULLMAG_TOOLCHAIN_IMAGE": args.toolchain_image or os.environ.get("FULLMAG_TOOLCHAIN_IMAGE", DEFAULT_BASE_IMAGE),
            "FULLMAG_TOOLCHAIN_IMAGE_ID": args.toolchain_image or os.environ.get("FULLMAG_TOOLCHAIN_IMAGE_ID", "pending"),
            "FULLMAG_BACKEND_CARGO_PROFILE": cargo_profile,
            "FULLMAG_DEVELOPMENT_BASE_IMAGE": os.environ.get(
                "FULLMAG_DEVELOPMENT_BASE_IMAGE", DEFAULT_BASE_IMAGE
            ),
            "FULLMAG_SOURCE_ROOT": str(selected),
            "FULLMAG_BACKEND_PACKAGE": str(run_root / "package"),
            "FULLMAG_BACKEND_SOURCE_TAR": str(run_root / "placeholder-source.tar"),
            "FULLMAG_BACKEND_SOURCE_MANIFEST": str(run_root / "placeholder-source-manifest.json"),
            "FULLMAG_STATE_ROOT": str(run_root / "state"),
            "FULLMAG_HOST_CERTIFICATE": str(run_root / "host-certificate.json"),
            "FULLMAG_PACKAGE_PROVENANCE": str(run_root / "provenance.json"),
            "FULLMAG_DEVELOPMENT_INPUTS": str(run_root / "development-inputs.json"),
            "FULLMAG_BACKEND_HOSTNAME": "fullmag-direct-backend-" + run_id[:12],
        }
        (run_root / "package").mkdir(exist_ok=True)
        (run_root / "state" / "development").mkdir(parents=True, exist_ok=True)
        for placeholder in ("host-certificate.json", "provenance.json", "development-inputs.json"):
            (run_root / placeholder).touch(exist_ok=True)
        base_info = _ensure_development_base(args, repo, layout, run_root)
        terminal.update(
            development_base_image=base_info["reference"],
            development_base_image_id=base_info["image_id"],
            toolchain_image_id=base_info["toolchain_image_id"],
            toolchain_manifest_sha256=base_info["toolchain_manifest_sha256"],
            development_base_context_sha256=base_info.get("context_sha256"),
        )
        _write_json(run_root / "receipt.json", terminal)
        placeholder_environment["FULLMAG_DEVELOPMENT_BASE_IMAGE"] = str(base_info["reference"])
        placeholder_environment["FULLMAG_TOOLCHAIN_IMAGE"] = str(base_info["toolchain_image_id"])
        placeholder_environment["FULLMAG_TOOLCHAIN_IMAGE_ID"] = str(base_info["toolchain_image_id"])
        image_ref, image_id, _image_document, image_built = _runtime_image_reference(
            args, repo, placeholder_environment, run_root, layout, base_info,
            compose_project,
        )
        toolchain_id = str(base_info["toolchain_image_id"])
        terminal.update(
            image_reference=image_ref,
            image_id=image_id,
            runtime_image_built=image_built,
        )
        _write_json(run_root / "receipt.json", terminal)

        from docker_backend_inputs import capture_backend_source

        if frozen_bundle is not None:
            source_bundle = frozen_bundle
            terminal["source_input_policy"] = "explicit_frozen_inputs; later checkout edits not included"
        else:
            source_bundle = capture_backend_source(
                repo,
                source_root=selected,
                mode="snapshot",
                include_untracked=tuple(args.include_untracked),
                output_dir=run_root / "source",
                capture_id=run_id,
                profile=STORAGE_PROFILE,
                require_windows=True,
            )
        terminal.update(
            source_digest=source_bundle["source_digest"],
            source_archive_sha256=source_bundle["archive_sha256"],
            source_manifest=str(source_bundle["manifest_path"]),
        )
        _write_json(run_root / "receipt.json", terminal)
        package = run_root / "package"
        cache = _prepare_backend_cache(layout, repo, image_id, run_root, selected, toolchain_id)
        files = _direct_compose_files(repo, cache)
        environment = _environment(
            layout, selected, run_root, source_bundle, package, image_ref, image_id, toolchain_id, cache,
            str(base_info["reference"]),
            cargo_profile,
        )
        config = _compose_config(repo, files, environment, project=compose_project)
        backend = config["services"]["backend"]
        if not isinstance(backend, dict):
            raise _fail("direct Compose backend service is malformed")
        mount_targets = _mount_targets(backend)
        required_mounts = {"/input/backend-source.tar", "/input/manifest.json", "/build"}
        missing_mounts = required_mounts - mount_targets
        if "/opt/fullmag/package" not in mount_targets:
            missing_mounts.add("/opt/fullmag/package")
        if missing_mounts:
            raise _fail("direct backend Compose service misses mounts: " + ", ".join(sorted(missing_mounts)))
        override = _prepare_override(backend)
        command = [
            *_compose_prefix(repo, files, compose_project),
            "run", "--rm", "--no-deps", "--name", "fullmag-backend-build-" + run_id[:16],
            "backend", *override,
        ]
        _docker_live(
            run_root / "backend-build.log",
            *command,
            timeout=4 * 60 * 60,
            environment=environment,
        )
        prepare_receipt, prepare_receipt_bytes = _validate_prepare_receipt(
            package, source_bundle, toolchain_id, cargo_profile
        )
        assembly_receipt = _assembly(
            layout, run_id, run_root, selected, source_bundle, package, image_id, toolchain_id,
            prepare_receipt, prepare_receipt_bytes, base_info, build_profile, cargo_profile,
        )
        terminal.update(state="succeeded", exit_code=0, assembly_receipt=str(assembly_receipt))
        _write_json(run_root / "receipt.json", terminal)
        print(json.dumps({
            "state": "succeeded",
            "assembly_receipt": str(assembly_receipt),
            "package_root": str(package),
            "source_root": str(selected),
            "image_id": image_id,
            "toolchain_image_id": toolchain_id,
            "build_profile": build_profile,
            "cargo_profile": cargo_profile,
            "run_root": str(run_root),
        }, indent=2))
        return assembly_receipt
    except Exception as error:
        terminal.update(
            state=("outcome_unknown_resources_retained"
                   if isinstance(error, DirectDockerOutcomeUnknown)
                   else "failed_resources_retained"),
            exit_code=2,
            error=str(error),
        )
        try:
            _write_json(run_root / "receipt.json", terminal)
        except Exception:
            pass
        raise
    finally:
        if lock_context is not None:
            lock_context.__exit__(None, None, None)


def up(args: argparse.Namespace) -> None:
    _require_native_windows()
    repo = Path(args.repo_root).resolve(strict=True)
    selected, layout = _select_source(repo, args.source_root)
    compose_project = _compose_identity(layout)["project_name"]
    _assert_no_running_fullmag(compose_project)
    from fullmag_docker_runtime import assert_loopback_port_available, start
    assert_loopback_port_available(args.port, compose_project)
    assembly_receipt = build(args)
    _assert_no_running_fullmag(compose_project)
    # Keep startup_script opaque to this launcher.  The existing startup helper
    # performs the path admission, source containment, hash, and wait_for_solve
    # policy checks against the same selected live checkout.
    start(
        repo,
        assembly_receipt,
        args.port,
        frontend="dev",
        source_root=selected,
        startup_script=args.script,
        project_name=compose_project,
        compose_template=repo / COMPOSE_RUNTIME_FILE,
    )


def recreate(args: argparse.Namespace) -> None:
    """Recreate one named run, optionally promoting its Compose project."""
    _require_native_windows()
    repo = Path(args.repo_root).resolve(strict=True)
    from fullmag_docker_runtime import start

    # No build or latest-run lookup is allowed here.  The runtime validates the
    # receipt, owner marker, source checkout, config CAS and package receipt
    # before it mutates the explicitly named run namespace.
    start_kwargs = {
        "frontend": "dev",
        "source_root": args.source_root,
        "startup_script": args.script,
        "project_name": None,
        "compose_template": repo / COMPOSE_RUNTIME_FILE,
        "run_receipt": args.run_receipt,
        "previous_config_sha256": args.previous_config_sha256,
        "migrate_compose_project": getattr(args, "migrate_compose_project", False),
    }
    recovery_authorization = getattr(args, "recover_idle_failure", None)
    if recovery_authorization is not None:
        start_kwargs["recovery_authorization"] = recovery_authorization
    start(repo, args.assembly_receipt, args.port, **start_kwargs)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=_repo_default(),
                        help="main Fullmag checkout used for storage and Compose definitions")
    subparsers = parser.add_subparsers(dest="action", required=True)
    for name in ("build", "up"):
        command = subparsers.add_parser(name, help=(
            "build the backend package without starting services"
            if name == "build" else "build and start backend plus frontend"
        ))
        command.add_argument("--source-root", type=Path,
                             help="registered checkout/worktree mounted live by both services")
        command.add_argument(
            "--profile", choices=sorted(BUILD_PROFILE_TO_CARGO_PROFILE),
            default=DEFAULT_BUILD_PROFILE,
            help="backend build profile: dev (Cargo backend-dev) or release",
        )
        command.add_argument("--image", help="existing/buildable development image/tag; default: FULLMAG_DEV_IMAGE or fullmag/fullmag-dev:local")
        command.add_argument("--toolchain-image", help="immutable toolchain image ID/tag; default: image label or configured value")
        command.add_argument("--source-manifest", type=Path,
                             help="absolute manifest path to resume verified frozen backend inputs; later checkout edits are not included")
        command.add_argument("--include-untracked", action="append", default=[],
                             help="relative untracked source path to include in the frozen backend archive (repeatable)")
        command.add_argument("--port", type=int, default=3197,
                             help="loopback frontend port (up only)")
        command.add_argument("--script", "--startup-script", dest="script", type=Path,
                             help="optional simulation script, relative to the selected checkout or absolute inside it (up only)")
        if name == "build":
            command.set_defaults(port=3197, script=None)
    recreate_parser = subparsers.add_parser(
        "recreate",
        help="recreate the named development run while retaining its state and session store",
    )
    recreate_parser.add_argument(
        "--run-receipt", type=Path, required=True,
        help="receipt.json of the one existing run to reuse; latest lookup is forbidden",
    )
    recreate_parser.add_argument(
        "--assembly-receipt", type=Path, required=True,
        help="new successful development assembly receipt to mount",
    )
    recreate_parser.add_argument(
        "--previous-config-sha256", required=True,
        help="exact raw SHA-256 of the prior runtime service config",
    )
    recreate_parser.add_argument(
        "--migrate-compose-project", action="store_true",
        help=(
            "explicitly promote a validated legacy fullmag run to the "
            "canonical project for the same registered checkout"
        ),
    )
    recreate_parser.add_argument(
        "--recover-idle-failure", type=Path,
        help=(
            "explicit host authorization for one stopped failed native owner; "
            "without this flag recovery/takeover is never attempted"
        ),
    )
    recreate_parser.add_argument(
        "--source-root", type=Path,
        help="registered live checkout; omitted means the checkout recorded by the run receipt",
    )
    recreate_parser.add_argument("--port", type=int, default=3197)
    recreate_parser.add_argument(
        "--script", "--startup-script", dest="script", type=Path,
        help="optional simulation script relative to the selected checkout",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "build":
            build(args)
        elif args.action == "up":
            up(args)
        elif args.action == "recreate":
            recreate(args)
        else:
            raise _fail(f"unsupported action: {args.action}")
        return 0
    except DirectDockerError as error:
        print(f"docker-dev: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
