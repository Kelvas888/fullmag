"""Prepare and attest the native Docker Desktop host-ledger adapter.

The resolver owns Windows paths.  This adapter only translates those paths for a
verified Linux Docker daemon, freezes the versioned maintenance overlay, and
keeps every Docker mutation bounded by an owned container name and receipt.
"""
from __future__ import annotations

import copy
import hashlib
import json
import ntpath
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

import fullmag_storage as storage

SCHEMA = "fullmag.docker-host-ledger-layout.v1"
RECEIPT_SCHEMA = "fullmag.docker-host-ledger-adapter-receipt.v1"
HOST_RECEIPT_SCHEMA = "fullmag.host-ledger-receipt.v1"
PROFILE = storage.HOST_LEDGER_PROFILE
IMAGE_NAME = storage.HOST_LEDGER_IMAGE_NAME
IMAGE_SIZE_BYTES = storage.HOST_LEDGER_SIZE_BYTES
MOUNT_TARGET = "/host-ledger"
LEDGER_ROOT = "/host-ledger/ledger"
DAEMON_HOST_PREFIX = "/run/desktop/mnt/host"
COMPOSE_SOURCE_NAME = "compose.host-ledger.source.yaml"
COMPOSE_MAINTENANCE_NAME = "compose.host-ledger.maintenance.json"
HELPER_COPY_NAME = "docker_host_ledger.sh"
MAX_HELPER_BYTES = 256 * 1024
MAX_COMPOSE_BYTES = 256 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/].*")
_TEMPLATE_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::([?!-])(.*?))?\}")


class HostLedgerError(RuntimeError):
    """A fail-closed host-ledger adapter error."""


def _text(value: Any, field: str) -> str:
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str) or not value or "\x00" in value:
        raise HostLedgerError(f"{field} must be a non-empty string without NUL")
    return value


def _safe_project_id(value: Any) -> str:
    value = _text(value, "host-ledger project id")
    if not _PROJECT_RE.fullmatch(value):
        raise HostLedgerError(f"invalid host-ledger project id: {value!r}")
    return value


def _safe_image_id(value: Any) -> str:
    value = _text(value, "image id")
    if not _IMAGE_RE.fullmatch(value):
        raise HostLedgerError("a full immutable image ID is required")
    return value


def _raw_path(value: Any, field: str) -> str:
    raw = _text(value, field)
    if "\r" in raw or "\n" in raw:
        raise HostLedgerError(f"{field} contains a newline")
    return raw


def _reject_dot_components(raw: str, field: str) -> None:
    if raw.startswith("\\\\") or raw.startswith("//"):
        raise HostLedgerError(f"{field} must not use a UNC or double-leading path")
    pieces = raw.replace("\\", "/").split("/")
    if any(part in {".", ".."} for part in pieces):
        raise HostLedgerError(f"{field} contains a dot path component")


def _local_normalized(raw: str) -> str:
    if _WINDOWS_ABS_RE.fullmatch(raw):
        return ntpath.normcase(ntpath.normpath(raw.replace("/", "\\")))
    return os.path.normcase(os.path.abspath(raw))


def _daemon_path(value: Any, field: str) -> str:
    """Translate a local Windows path to the Docker Desktop Linux namespace.

    Existing daemon paths are accepted verbatim after lexical validation.  A
    Windows drive is translated only after the caller has proven the daemon is
    Linux; callers must not use this function before `_daemon_info` succeeds.
    """
    raw = _raw_path(value, field)
    _reject_dot_components(raw, field)
    if _WINDOWS_ABS_RE.fullmatch(raw):
        drive = raw[0].lower()
        tail = raw[2:].replace("\\", "/")
        tail = tail.lstrip("/")
        if not tail:
            raise HostLedgerError(f"{field} cannot be a drive root")
        return f"{DAEMON_HOST_PREFIX}/{drive}/{tail}"
    if raw.startswith(DAEMON_HOST_PREFIX + "/"):
        return str(PurePosixPath(raw))
    if raw.startswith("/"):
        # Linux callers already operate in the daemon namespace.  Native
        # Windows paths never take this branch.
        return str(PurePosixPath(raw))
    raise HostLedgerError(f"{field} must be absolute: {raw}")


def _same_daemon_path(left: Any, right: Any) -> bool:
    try:
        return _daemon_path(left, "left") == _daemon_path(right, "right")
    except HostLedgerError:
        return False


def _regular_file(path: Path, field: str, maximum: int) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise HostLedgerError(f"{field} must be a regular non-symlink file: {path}")
    size = path.stat().st_size
    if size <= 0 or size > maximum:
        raise HostLedgerError(f"{field} exceeds its bounded size: {path}")
    return path


def _digest(path: Path, maximum: int | None = None) -> str:
    path = _regular_file(path, "managed file", maximum or 64 * 1024 * 1024)
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def _atomic_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise HostLedgerError(f"refusing to replace symlink: {path}")
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        raise HostLedgerError(f"temporary receipt path already exists: {temporary}")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_bytes(Path(path), (json.dumps(value, sort_keys=True, indent=2) + "\n").encode(), 0o600)


def _copy_immutable(source: Path, destination: Path, maximum: int, mode: int) -> str:
    source = _regular_file(Path(source), "source helper/overlay", maximum)
    source_hash = _digest(source, maximum)
    destination = Path(destination)
    if destination.is_symlink():
        raise HostLedgerError(f"refusing symlink destination: {destination}")
    if destination.exists():
        if not destination.is_file() or _digest(destination, maximum) != source_hash:
            raise HostLedgerError(f"owned frozen file differs from source: {destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as source_stream, destination.open("xb") as target_stream:
            shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
            target_stream.flush()
            os.fsync(target_stream.fileno())
    destination.chmod(mode)
    return source_hash


def _within(path: Any, parent: Any) -> bool:
    raw_path = _raw_path(path, "path")
    raw_parent = _raw_path(parent, "parent")
    if _WINDOWS_ABS_RE.fullmatch(raw_path) != _WINDOWS_ABS_RE.fullmatch(raw_parent):
        return False
    try:
        candidate = _local_normalized(raw_path)
        root = _local_normalized(raw_parent)
        return os.path.commonpath([candidate, root]) == root
    except (OSError, ValueError):
        return False


def _layout_value(layout: Mapping[str, Any], name: str, env_name: str | None = None) -> Any:
    if name in layout and layout[name] not in (None, ""):
        return layout[name]
    values = layout.get("env")
    if isinstance(values, Mapping) and env_name and values.get(env_name) not in (None, ""):
        return values[env_name]
    return None


def _resolve_values(layout: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(layout, Mapping):
        raise HostLedgerError("resolved storage layout must be a mapping")
    project_id = _layout_value(layout, "host_ledger_project_id", "FULLMAG_HOST_LEDGER_PROJECT_ID")
    if project_id is None:
        project_id = _layout_value(layout, "project_id", "FULLMAG_PROJECT_ID")
    if project_id is None:
        project_root = _layout_value(layout, "project_root")
        if project_root is None:
            raise HostLedgerError("resolved layout has no project identity")
        project_id = storage.identifier(project_root)
    project_id = _safe_project_id(project_id)

    storage_root = _layout_value(layout, "storage_root", "FULLMAG_PROJECT_STORAGE_ROOT")
    if storage_root is None:
        raise HostLedgerError("resolved layout has no canonical storage root")
    storage_root = _raw_path(storage_root, "storage root")
    if storage_root in {"/", "\\", "C:\\", "c:\\"}:
        raise HostLedgerError("host-ledger storage root cannot be a filesystem root")
    backing = _layout_value(layout, "host_ledger_backing_image", "FULLMAG_HOST_LEDGER_BACKING_IMAGE")
    expected_backing = ntpath.join(storage_root, "build-volumes", IMAGE_NAME) if _WINDOWS_ABS_RE.fullmatch(storage_root) else os.path.join(storage_root, "build-volumes", IMAGE_NAME)
    backing = _raw_path(backing or expected_backing, "host-ledger backing image")
    if _local_normalized(backing) != _local_normalized(expected_backing):
        raise HostLedgerError("host-ledger backing image is not under canonical storage/build-volumes")

    mount = _layout_value(layout, "host_ledger_mount_root", "FULLMAG_HOST_LEDGER_MOUNT_ROOT")
    expected_mount = f"/mnt/fullmag-host-ledger-{project_id}"
    mount = _raw_path(mount or expected_mount, "host-ledger mount root")
    if mount != expected_mount:
        raise HostLedgerError("host-ledger mount root is not project-scoped")
    lock = _layout_value(layout, "host_ledger_lock_path", "FULLMAG_HOST_LEDGER_LOCK_PATH")
    expected_lock = backing + ".lock"
    lock = _raw_path(lock or expected_lock, "host-ledger lock path")
    if _local_normalized(lock) != _local_normalized(expected_lock):
        raise HostLedgerError("host-ledger lock path is not next to the canonical image")
    marker = _layout_value(layout, "host_ledger_owner_marker", "FULLMAG_HOST_LEDGER_OWNER_MARKER")
    expected_marker = mount + "/.fullmag-host-ledger-owner.json"
    marker = _raw_path(marker or expected_marker, "host-ledger owner marker")
    if marker != expected_marker:
        raise HostLedgerError("host-ledger owner marker is not under the project mount")
    return {
        "project_id": project_id,
        "storage_root": storage_root,
        "backing_image": backing,
        "mount_root": mount,
        "lock_path": lock,
        "owner_marker": marker,
        "ledger_root": LEDGER_ROOT,
        "ledger_root_daemon": mount + "/ledger",
    }


def _capture(value: Any) -> tuple[str, str, str]:
    """Normalize the injected Docker callable result without leaking secrets."""
    if isinstance(value, subprocess.CompletedProcess):
        stdout = value.stdout or ""
        stderr = value.stderr or ""
        return str(stdout), str(stderr), str(stdout) + str(stderr)
    if isinstance(value, Mapping):
        stdout = str(value.get("stdout") or "")
        stderr = str(value.get("stderr") or "")
        combined = str(value.get("combined") or (stdout + stderr))
        return stdout, stderr, combined
    if isinstance(value, tuple) and len(value) == 2:
        stdout, stderr = (str(value[0] or ""), str(value[1] or ""))
        return stdout, stderr, stdout + stderr
    text = "" if value is None else str(value)
    return text, "", text


def _invoke(docker_callable: Callable[..., Any], *args: str, timeout: int = 60,
            environment: Mapping[str, str] | None = None) -> tuple[str, str, str]:
    kwargs: dict[str, Any] = {"combined": True, "timeout": timeout}
    if environment is not None:
        kwargs["environment"] = dict(environment)
    try:
        value = docker_callable(*args, **kwargs)
    except TypeError as error:
        # Small test doubles may expose only positional arguments; the real
        # launcher wrapper accepts all kwargs above.  Do not hide Docker errors.
        if "unexpected keyword" not in str(error) and "positional argument" not in str(error):
            raise
        value = docker_callable(*args)
    return _capture(value)


def _unknown(error: BaseException) -> bool:
    return isinstance(error, (TimeoutError, subprocess.TimeoutExpired)) or (
        hasattr(error, "operation") and hasattr(error, "timeout_seconds")
    )


def _daemon_info(docker_callable: Callable[..., Any]) -> dict[str, str]:
    stdout, stderr, combined = _invoke(docker_callable, "info", "--format", "{{json .}}", timeout=30)
    text = stdout.strip() or combined.strip()
    try:
        document = json.loads(text)
    except (ValueError, TypeError):
        fields = text.split("|", 1)
        document = {"ID": fields[0].strip(), "OSType": fields[1].strip() if len(fields) == 2 else ""}
    if not isinstance(document, Mapping):
        raise HostLedgerError("Docker info did not return an object")
    daemon_id = str(document.get("ID") or "").strip()
    os_type = str(document.get("OSType") or "").strip().lower()
    if not daemon_id or "\n" in daemon_id or os_type != "linux":
        raise HostLedgerError("host-ledger requires a verified Linux Docker daemon with a non-empty ID")
    return {"id_sha256": hashlib.sha256(daemon_id.encode("utf-8")).hexdigest(), "os_type": os_type}


def _image_attestation(image_id: str, docker_callable: Callable[..., Any]) -> dict[str, Any]:
    stdout, _, combined = _invoke(docker_callable, "image", "inspect", image_id, timeout=60)
    try:
        document = json.loads(stdout or combined)
        observed = document[0] if isinstance(document, list) and len(document) == 1 else document
    except (ValueError, TypeError, IndexError) as error:
        raise HostLedgerError("Docker image inspect did not return one image") from error
    if not isinstance(observed, Mapping) or observed.get("Id") != image_id:
        raise HostLedgerError("maintenance image identity differs from the immutable requested image")
    if (observed.get("Config") or {}).get("Volumes"):
        raise HostLedgerError("maintenance image declares anonymous volumes")
    return {"id": image_id, "created": observed.get("Created"), "repo_tags": observed.get("RepoTags", [])}


def _parse_json_lines(text: str, schema: str) -> dict[str, Any] | None:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{") or not line.endswith("}"):
            continue
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("schema") == schema:
            return value
    return None


def _inspect_container(name: str, docker_callable: Callable[..., Any]) -> dict[str, Any]:
    stdout, _, combined = _invoke(docker_callable, "inspect", name, timeout=60)
    try:
        value = json.loads(stdout or combined)
    except ValueError as error:
        raise HostLedgerError(f"Docker inspect for owned container {name!r} was not JSON") from error
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise HostLedgerError(f"Docker inspect for owned container {name!r} was ambiguous")
    return value[0]


def _owned_terminal(document: Mapping[str, Any], *, name: str, image_id: str,
                    label_key: str, label_value: str) -> bool:
    if document.get("Name") != "/" + name:
        return False
    if document.get("Image") != image_id:
        return False
    labels = document.get("Config", {}).get("Labels") or {}
    if labels.get(label_key) != label_value:
        return False
    state = document.get("State") or {}
    return state.get("Status") == "exited" and int(state.get("ExitCode", -1)) >= 0


def _remove_owned(document: Mapping[str, Any], *, name: str, image_id: str,
                  label_key: str, label_value: str,
                  docker_callable: Callable[..., Any]) -> None:
    if not _owned_terminal(document, name=name, image_id=image_id, label_key=label_key, label_value=label_value):
        raise HostLedgerError(f"refusing to remove unverified container {name!r}")
    _invoke(docker_callable, "rm", name, timeout=60)


def _write_output(run_root: Path, prefix: str, stdout: str, stderr: str, combined: str) -> None:
    for suffix, value in (("stdout.log", stdout), ("stderr.log", stderr), ("output.log", combined)):
        if len(value.encode("utf-8", "replace")) > MAX_OUTPUT_BYTES:
            value = value.encode("utf-8", "replace")[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        _atomic_bytes(run_root / f"{prefix}.{suffix}", value.encode("utf-8"), 0o600)


def _validate_host_receipt(value: Mapping[str, Any], values: Mapping[str, str]) -> None:
    if value.get("schema") != HOST_RECEIPT_SCHEMA or value.get("profile") != PROFILE:
        raise HostLedgerError("host-ledger maintenance receipt schema/profile mismatch")
    if value.get("state") not in {"ready", "validated"} or value.get("filesystem") != "ext4":
        raise HostLedgerError("host-ledger maintenance did not report a validated ext4 filesystem")
    if value.get("mount_active") is not True or value.get("mount_root") != values["mount_root"]:
        raise HostLedgerError("host-ledger maintenance did not leave the expected mount active")
    if value.get("backing_image") != values["backing_image"] or not value.get("filesystem_uuid"):
        raise HostLedgerError("host-ledger receipt identity does not match the resolved backing image")
    if value.get("ledger_root") != values["mount_root"] + "/ledger":
        raise HostLedgerError("host-ledger receipt ledger child differs from the resolved mount")
    if value.get("mount_target") != MOUNT_TARGET or value.get("image_size_bytes") != IMAGE_SIZE_BYTES:
        raise HostLedgerError("host-ledger receipt resource contract mismatch")


def _render_maintenance(source: Path, destination: Path, *, environment: Mapping[str, str], image_id: str) -> None:
    try:
        import yaml
    except ImportError as error:
        raise HostLedgerError("PyYAML is required to freeze the maintenance overlay") from error
    source = _regular_file(source, "host-ledger Compose overlay", MAX_COMPOSE_BYTES)
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise HostLedgerError("host-ledger Compose overlay is not valid YAML") from error
    if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
        raise HostLedgerError("host-ledger Compose overlay has no services mapping")
    services = document["services"]
    if set(services) != {"backend", "host-ledger-maintenance"}:
        raise HostLedgerError("host-ledger overlay service topology changed")
    values = dict(environment)
    values["FULLMAG_HOST_LEDGER_HELPER_IMAGE"] = image_id
    maintenance = copy.deepcopy(services["host-ledger-maintenance"])

    def substitute(value: Any) -> Any:
        if isinstance(value, str):
            def replace(match: re.Match[str]) -> str:
                name, operator, fallback = match.groups()
                present = values.get(name)
                if present not in (None, ""):
                    return str(present)
                if operator in {"-"}:
                    return fallback or ""
                if operator in {"?", "!"}:
                    raise HostLedgerError(f"missing Compose variable {name}")
                return ""
            return _TEMPLATE_RE.sub(replace, value)
        if isinstance(value, list):
            return [substitute(item) for item in value]
        if isinstance(value, dict):
            return {key: substitute(item) for key, item in value.items()}
        return value

    maintenance = substitute(maintenance)
    if maintenance.get("image") != image_id:
        raise HostLedgerError("maintenance image did not resolve to the immutable image ID")
    if maintenance.get("privileged") is not True or maintenance.get("pid") != "host" or maintenance.get("network_mode") != "none":
        raise HostLedgerError("maintenance service lost its privileged host-namespace contract")
    if maintenance.get("ports") or maintenance.get("gpus") or maintenance.get("devices"):
        raise HostLedgerError("maintenance service must not publish ports or request GPUs/devices")
    _atomic_json(destination, {"services": {"host-ledger-maintenance": maintenance}})


def _container_name(prefix: str, run_root: Path) -> str:
    token = re.sub(r"[^a-z0-9_.-]", "-", run_root.name.lower()).strip(".-")
    if not token:
        raise HostLedgerError("run root has no safe identity")
    value = f"fullmag-host-ledger-{prefix}-{token}"
    if len(value) > 63:
        value = value[:63].rstrip(".-")
    return value


def _run_owned_container(*, args: list[str], name: str, image_id: str, label_value: str,
                         run_root: Path, prefix: str, docker_callable: Callable[..., Any],
                         timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    label_key = "org.fullmag.host-ledger.owner"
    try:
        stdout, stderr, combined = _invoke(docker_callable, *args, timeout=timeout)
        _write_output(run_root, prefix, stdout, stderr, combined)
    except BaseException as error:
        _write_output(run_root, prefix, "", str(error), str(error))
        if _unknown(error):
            raise
        # A normal non-zero run may still have created a terminal container;
        # inspect it before deciding whether removal is safe.
        try:
            document = _inspect_container(name, docker_callable)
            if _owned_terminal(document, name=name, image_id=image_id, label_key=label_key, label_value=label_value):
                _remove_owned(document, name=name, image_id=image_id, label_key=label_key, label_value=label_value, docker_callable=docker_callable)
        except BaseException:
            pass
        raise
    document = _inspect_container(name, docker_callable)
    if not _owned_terminal(document, name=name, image_id=image_id, label_key=label_key, label_value=label_value):
        raise HostLedgerError(f"owned maintenance container {name!r} did not terminate in a verifiable state")
    state = document["State"]
    if int(state.get("ExitCode", -1)) != 0:
        raise HostLedgerError(f"owned maintenance container {name!r} exited with {state.get('ExitCode')}")
    _remove_owned(document, name=name, image_id=image_id, label_key=label_key, label_value=label_value, docker_callable=docker_callable)
    output = _parse_json_lines(_capture((stdout, stderr))[2], HOST_RECEIPT_SCHEMA)
    if output is None:
        try:
            _, _, logs = _invoke(docker_callable, "logs", name, timeout=60)
            output = _parse_json_lines(logs, HOST_RECEIPT_SCHEMA)
        except BaseException:
            output = None
    return document, output or {}


def _probe_host_python(run_root: Path, image_id: str, docker_callable: Callable[..., Any], receipt: dict[str, Any]) -> None:
    name = _container_name("python", run_root)
    script = "set -eu; command -v nsenter >/dev/null; nsenter -t 1 -m -- python3 -c 'print(\"fullmag-host-ledger-host-python3-v1\")'"
    label_key = "org.fullmag.host-ledger.owner"
    args = ["run", "--name", name, "--user", "0:0", "--privileged", "--pid", "host", "--network", "none",
            "--read-only", "--entrypoint", "/bin/sh", "--label", f"{label_key}={receipt['run_id']}", image_id, "-c", script]
    receipt["host_python_probe_container"] = name
    try:
        document, _ = _run_owned_container(args=args, name=name, image_id=image_id, label_value=receipt["run_id"],
                                            run_root=run_root, prefix="host-python", docker_callable=docker_callable,
                                            timeout=120)
        receipt["host_python_probe_state"] = document.get("State", {}).get("Status")
        stdout = (run_root / "host-python.stdout.log").read_text(encoding="utf-8") if (run_root / "host-python.stdout.log").is_file() else ""
        if "fullmag-host-ledger-host-python3-v1" not in stdout:
            raise HostLedgerError("host namespace python3 probe did not return its marker")
        receipt["host_python_probe"] = "PASS"
    except BaseException:
        receipt["host_python_probe"] = "UNKNOWN" if _unknown(sys.exc_info()[1]) else "FAIL"
        raise


def _run_maintenance(run_root: Path, compose_file: Path, image_id: str, project: str,
                     action: str, docker_callable: Callable[..., Any], receipt: dict[str, Any],
                     timeout: int) -> dict[str, Any]:
    name = _container_name(action, run_root)
    label_value = receipt["run_id"]
    label_key = "org.fullmag.host-ledger.owner"
    args = ["compose", "--project-name", project, "--profile", "host-ledger-maintenance", "-f", str(compose_file),
            "run", "--name", name, "--label", f"{label_key}={label_value}", "host-ledger-maintenance", action]
    receipt[f"{action}_container"] = name
    document, host_receipt = _run_owned_container(args=args, name=name, image_id=image_id, label_value=label_value,
                                                   run_root=run_root, prefix=f"maintenance-{action}",
                                                   docker_callable=docker_callable, timeout=timeout)
    values = {"mount_root": receipt["mount_root"], "backing_image": receipt["backing_image"]}
    _validate_host_receipt(host_receipt, values)
    receipt[f"{action}_container_state"] = document.get("State", {}).get("Status")
    receipt[f"{action}_receipt"] = host_receipt
    return host_receipt


def prepare(layout: Mapping[str, Any], repo: Any, image_id: str, run_root: Any,
            docker_callable: Callable[..., Any]) -> dict[str, Any]:
    """Prepare one persistent host-ledger mount and return launcher bindings."""
    image_id = _safe_image_id(image_id)
    values = _resolve_values(layout)
    repo = Path(repo)
    run_root = Path(run_root)
    if not repo.is_absolute() or not run_root.is_absolute():
        raise HostLedgerError("repo and run_root must be absolute paths")
    runs_root = _layout_value(layout, "runs_root")
    if runs_root is not None and not _within(run_root, runs_root):
        raise HostLedgerError("host-ledger run root is outside the resolved runs root")
    if run_root.is_symlink():
        raise HostLedgerError("host-ledger run root must not be a symlink")
    run_root.mkdir(parents=True, exist_ok=True)
    helper_source = repo / "scripts" / "lib" / HELPER_COPY_NAME
    overlay_source = repo / "compose.host-ledger.yaml"
    helper_copy = run_root / HELPER_COPY_NAME
    overlay_copy = run_root / COMPOSE_SOURCE_NAME
    helper_hash = _copy_immutable(helper_source, helper_copy, MAX_HELPER_BYTES, 0o444)
    overlay_hash = _copy_immutable(overlay_source, overlay_copy, MAX_COMPOSE_BYTES, 0o444)
    daemon_info = _daemon_info(docker_callable)
    image_attestation = _image_attestation(image_id, docker_callable)

    environment = {
        "FULLMAG_HOST_LEDGER_PROFILE": PROFILE,
        "FULLMAG_HOST_LEDGER_PROJECT_ID": values["project_id"],
        "FULLMAG_HOST_LEDGER_STORAGE_ROOT": _daemon_path(values["storage_root"], "storage root"),
        "FULLMAG_HOST_LEDGER_BACKING_IMAGE": _daemon_path(values["backing_image"], "backing image"),
        "FULLMAG_HOST_LEDGER_MOUNT_ROOT": values["mount_root"],
        "FULLMAG_HOST_LEDGER_LOCK_PATH": _daemon_path(values["lock_path"], "lock path"),
        "FULLMAG_HOST_LEDGER_OWNER_MARKER": values["owner_marker"],
        "FULLMAG_HOST_LEDGER_SIZE_BYTES": str(IMAGE_SIZE_BYTES),
        "FULLMAG_HOST_LEDGER_MOUNT_TARGET": MOUNT_TARGET,
        "FULLMAG_HOST_LEDGER_ROOT": LEDGER_ROOT,
        "FULLMAG_HOST_LEDGER_LEDGER_ROOT": values["ledger_root_daemon"],
        "FULLMAG_HOST_LEDGER_HELPER_PATH": _daemon_path(helper_copy, "helper copy"),
        "FULLMAG_HOST_LEDGER_HELPER_IMAGE": image_id,
        "FULLMAG_HOST_LEDGER_HOST_PID": "1",
        "FULLMAG_HOST_LEDGER_RUNTIME_UID": "65532",
        "FULLMAG_HOST_LEDGER_RUNTIME_GID": "65532",
        "FULLMAG_HOST_LEDGER_LOCK_WAIT_SECONDS": "120",
        "FULLMAG_DOCKER_HOST_ID": daemon_info["id_sha256"],
    }
    run_id = hashlib.sha256(str(run_root).encode("utf-8")).hexdigest()[:32]
    receipt_path = run_root / "host-ledger-adapter-receipt.json"
    if receipt_path.is_symlink() or receipt_path.exists():
        raise HostLedgerError("an existing host-ledger receipt requires explicit reconciliation; refusing retry")
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "state": "starting",
        "run_id": run_id,
        "profile": PROFILE,
        "project_id": values["project_id"],
        "image_id": image_id,
        "image": image_attestation,
        "docker_daemon_id_sha256": daemon_info["id_sha256"],
        "docker_ostype": daemon_info["os_type"],
        "storage_root": environment["FULLMAG_HOST_LEDGER_STORAGE_ROOT"],
        "backing_image": environment["FULLMAG_HOST_LEDGER_BACKING_IMAGE"],
        "mount_root": values["mount_root"],
        "ledger_root": LEDGER_ROOT,
        "ledger_root_daemon": values["ledger_root_daemon"],
        "helper_source": str(helper_source),
        "helper_copy": str(helper_copy),
        "helper_sha256": helper_hash,
        "compose_source": str(overlay_copy),
        "compose_source_sha256": overlay_hash,
        "receipt_path": str(receipt_path),
    }
    _atomic_json(receipt_path, receipt)
    try:
        maintenance_doc = run_root / COMPOSE_MAINTENANCE_NAME
        _render_maintenance(overlay_copy, maintenance_doc, environment=environment, image_id=image_id)
        receipt["maintenance_compose"] = str(maintenance_doc)
        receipt["maintenance_compose_sha256"] = _digest(maintenance_doc, MAX_COMPOSE_BYTES)
        _atomic_json(receipt_path, receipt)
        _probe_host_python(run_root, image_id, docker_callable, receipt)
        _atomic_json(receipt_path, receipt)
        project = f"fullmag-host-ledger-{run_root.name}"
        host_receipt = _run_maintenance(run_root, maintenance_doc, image_id, project, "ensure", docker_callable, receipt, 300)
        _validate_host_receipt(host_receipt, {"mount_root": values["mount_root"],
                                            "backing_image": environment["FULLMAG_HOST_LEDGER_BACKING_IMAGE"]})
        receipt["state"] = "ready"
        receipt["host_receipt"] = host_receipt
        receipt["environment"] = environment
        _atomic_json(receipt_path, receipt)
    except BaseException as error:
        receipt["state"] = "outcome_unknown" if _unknown(error) else "failed_resources_retained"
        receipt["error"] = str(error)
        receipt["resources_retained"] = True
        _atomic_json(receipt_path, receipt)
        raise
    return {
        "schema": SCHEMA,
        "profile": PROFILE,
        "state": "ready",
        "run_id": run_id,
        "project_id": values["project_id"],
        "image_id": image_id,
        "environment": environment,
        "mount_root": values["mount_root"],
        "ledger_root": LEDGER_ROOT,
        "ledger_root_daemon": values["ledger_root_daemon"],
        "backing_image": environment["FULLMAG_HOST_LEDGER_BACKING_IMAGE"],
        "backing_image_local": values["backing_image"],
        "compose_overlay": str(overlay_copy),
        "maintenance_compose": str(run_root / COMPOSE_MAINTENANCE_NAME),
        "run_root": str(run_root),
        "helper_copy": str(helper_copy),
        "helper_sha256": helper_hash,
        "compose_source_sha256": overlay_hash,
        "receipt": str(receipt_path),
        "receipt_sha256": _digest(receipt_path),
        "host_receipt": host_receipt,
        "docker_daemon_id_sha256": daemon_info["id_sha256"],
    }


def backend_verify_command(container: str) -> list[str]:
    """Return the bounded guest-side write/root check used after API startup."""
    container = _text(container, "backend container")
    return ["exec", container, "/bin/sh", "-ceu",
            "test -d /host-ledger/ledger; test ! -L /host-ledger/ledger; test -w /host-ledger/ledger"]


def _env_map(config: Mapping[str, Any]) -> dict[str, str]:
    values = {}
    for item in config.get("Env", []) or []:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
    return values


def validate_container(document: Mapping[str, Any] | list[Mapping[str, Any]], profile: Mapping[str, Any] | str,
                       docker_callable: Callable[..., Any]) -> dict[str, Any]:
    """Attest backend binds and perform a live guest + host filesystem check."""
    if isinstance(document, list):
        if len(document) != 1:
            raise HostLedgerError("backend inspect result is ambiguous")
        document = document[0]
    if not isinstance(document, Mapping):
        raise HostLedgerError("backend inspect document must be an object")
    if isinstance(profile, str):
        expected_profile = profile
        profile_values: Mapping[str, Any] = {"profile": profile}
    else:
        profile_values = profile
        expected_profile = profile.get("profile", PROFILE)
    if expected_profile != PROFILE:
        raise HostLedgerError("unexpected host-ledger profile")
    actual = document
    container_id = str(actual.get("Id") or actual.get("ID") or "")
    if not container_id:
        raise HostLedgerError("backend inspect has no container ID")
    config = actual.get("Config") or {}
    expected_image = profile_values.get("image_id")
    if expected_image and actual.get("Image") != expected_image:
        raise HostLedgerError("backend image differs from the immutable host-ledger image")
    env = _env_map(config)
    if env.get("FULLMAG_HOST_LEDGER_PROFILE") != PROFILE or env.get("FULLMAG_HOST_LEDGER_ROOT") != LEDGER_ROOT:
        raise HostLedgerError("backend did not receive the fixed host-ledger profile/root")
    if env.get("FULLMAG_DOCKER_HOST_EXECUTION") != "1":
        raise HostLedgerError("backend host execution flag is missing")
    expected_env = profile_values.get("environment") or {}
    for key in ("FULLMAG_HOST_LEDGER_MOUNT_ROOT", "FULLMAG_HOST_LEDGER_PROJECT_ID", "FULLMAG_DOCKER_HOST_ID"):
        if key in expected_env and env.get(key) != expected_env[key]:
            raise HostLedgerError(f"backend host-ledger environment differs for {key}")
    expected_mount = profile_values.get("mount_root")
    mounts = [m for m in actual.get("Mounts", []) or [] if isinstance(m, Mapping) and m.get("Destination") == MOUNT_TARGET]
    if len(mounts) != 1 or mounts[0].get("Type") != "bind" or not mounts[0].get("RW"):
        raise HostLedgerError("backend must have exactly one writable /host-ledger bind")
    if expected_mount is not None and not _same_daemon_path(mounts[0].get("Source"), expected_mount):
        raise HostLedgerError("backend /host-ledger source differs from the managed mount root")
    host_config = actual.get("HostConfig") or {}
    if host_config.get("Privileged") or config.get("User") != "65532:65532":
        raise HostLedgerError("backend host-ledger service isolation mismatch")
    _invoke(docker_callable, *backend_verify_command(container_id), timeout=60)

    maintenance = profile_values.get("maintenance_compose")
    image_id = profile_values.get("image_id")
    run_root = Path(profile_values.get("run_root") or Path(maintenance).parent if maintenance else ".")
    host_receipt = profile_values.get("host_receipt")
    if maintenance and image_id:
        # The maintenance file is already frozen and has no backend service.
        run_id = profile_values.get("run_id") or hashlib.sha256(str(run_root).encode()).hexdigest()[:32]
        verify_receipt: dict[str, Any] = {
            "run_id": run_id,
            "mount_root": profile_values.get("mount_root"),
            "backing_image": profile_values.get("backing_image", ""),
        }
        host_receipt = _run_maintenance(run_root, Path(maintenance), image_id,
                                        f"fullmag-host-ledger-{run_root.name}", "verify",
                                        docker_callable, verify_receipt, 180)
    elif not isinstance(host_receipt, Mapping):
        raise HostLedgerError("live host-ledger verification evidence is missing")
    if host_receipt.get("filesystem") != "ext4" or host_receipt.get("mount_active") is not True:
        raise HostLedgerError("live host-ledger verification did not prove an active ext4 mount")
    return {
        "schema": "fullmag.docker-host-ledger-attestation.v1",
        "profile": PROFILE,
        "backend_container_id": container_id,
        "mount_source": mounts[0].get("Source"),
        "mount_target": MOUNT_TARGET,
        "ledger_root": LEDGER_ROOT,
        "filesystem": "ext4",
        "filesystem_uuid": host_receipt.get("filesystem_uuid"),
        "loop_device": host_receipt.get("loop_device"),
        "backing_image": host_receipt.get("backing_image"),
        "backend_verification": "PASS",
        "host_verification": "PASS",
        "host_receipt": host_receipt,
    }
