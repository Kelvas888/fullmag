"""Host-only proof for the narrow post-build failed-owner continuation.

The proof carries the existing configuration digest into ``start``.  It does
not create a runtime capability, reset an owner, release a run, or replace
the native failed-stop metadata.  The original stop journal is kept separate
from the currently observed stopped Docker namespace because their container
identities may differ after a failed retry.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath

from docker_build_control import BuildControlError, canonical


SCHEMA = "fullmag.docker-post-build-failed-owner-continuation.v1"
STATE = "authorized"
PROCESS_SCHEMA = "fullmag.docker-process-tree.v1"
STOP_SCHEMA = "fullmag.stop-failed-admission.v1"
CONTROL_PROCESS = "runtime-control/runtime-service/process-tree.json"
CONTROL_OWNER = "runtime-control/runtime-services/OWNER.json"
CONFIG_RELATIVE = "runtime-control/runtime-service/docker-all.json"
CONTINUATION_METADATA_KEY = "post_build_generation"
START_BINDING_SCHEMA = "fullmag.docker-post-build-failed-owner-start.v1"
START_BINDING_ENV = "FULLMAG_DOCKER_POST_BUILD_CONTINUATION"
START_BINDING_SHA_ENV = "FULLMAG_DOCKER_POST_BUILD_CONTINUATION_SHA256"
START_BINDING_RELATIVE_NAME = "post-build-continuation.json"
RECREATE_SCHEMA = "fullmag.docker-removed-recreation-container.v1"

SHA256 = re.compile(r"^[0-9a-f]{64}$")
TOKEN = re.compile(r"^[0-9a-f]{32}$")
IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTAINER = re.compile(r"^[0-9a-f]{64}$")

PROCESS_KEYS = (
    "schema", "state", "api_pid", "api_exit_code", "accepted_store",
    "bootstrap", "qualification", "error", "shutdown_error",
)
PROCESS_ERROR = (
    "API binding did not become ready: API loopback probe failed for "
    "/v2/platform/openapi.json: [Errno 111] Connection refused"
)
PROCESS_SHUTDOWN_ERROR = "no pinned runtime service owner was available for authenticated drain"


class PostBuildGenerationError(BuildControlError):
    """A continuation proof is malformed or has drifted."""


class PostBuildGenerationUnavailable(PostBuildGenerationError):
    """A required immutable source proof is unavailable."""


def _fail(message: str) -> PostBuildGenerationError:
    return PostBuildGenerationError(message)


def _unavailable(message: str) -> PostBuildGenerationUnavailable:
    return PostBuildGenerationUnavailable(message)


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None or set(value) == {"0"}:
        raise _fail(label + " is not a non-zero lowercase SHA-256")
    return value


def _token(value: object, label: str) -> str:
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise _fail(label + " is not a lowercase operation token")
    return value


def _image(value: object, label: str) -> str:
    if not isinstance(value, str) or IMAGE.fullmatch(value) is None or set(value[7:]) == {"0"}:
        raise _fail(label + " is not an immutable image identity")
    return value


def _container(value: object, label: str) -> str:
    if not isinstance(value, str) or CONTAINER.fullmatch(value) is None or set(value) == {"0"}:
        raise _fail(label + " is not an immutable container identity")
    return value


def _text(value: object, label: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise _fail(label + " is not bounded text")
    return value


def _relative(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise _fail(label + " is not a bounded relative path")
    path = PurePosixPath(value)
    if (path.is_absolute() or str(path) != value or ".." in path.parts
            or "\\" in value or ":" in value or any(part in {"", "."} for part in path.parts)):
        raise _fail(label + " escapes its control root")
    return value


def _positive(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise _fail(label + " is not a positive integer")
    return value


def _read_raw(control, relative: str, *, optional: bool = False) -> bytes | None:
    relative = _relative(relative, "control record")
    read_raw = getattr(control, "read_raw", None)
    if callable(read_raw):
        try:
            raw = read_raw(relative, optional=optional)
        except FileNotFoundError:
            if optional:
                return None
            raise _unavailable("control record is missing: " + relative)
        if raw is None:
            return None
        if not isinstance(raw, bytes):
            raise _fail("control record is not bytes: " + relative)
        return raw
    try:
        from docker_volume_stop_unadmitted import _control_bytes
        return _control_bytes(control, relative, optional=optional)
    except FileNotFoundError:
        if optional:
            return None
        raise _unavailable("control record is missing: " + relative)
    except BuildControlError:
        raise
    except (ImportError, AttributeError, OSError, TypeError) as error:
        raise _unavailable("control adapter cannot read " + relative) from error


def _read_json(control, relative: str, *, optional: bool = False) -> tuple[dict[str, object] | None, bytes | None]:
    raw = _read_raw(control, relative, optional=optional)
    if raw is None:
        return None, None
    def reject_duplicate_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON member")
            value[key] = item
        return value

    def reject_json_constant(constant):
        raise ValueError("non-finite JSON constant: " + constant)

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise _fail("control record is not valid JSON: " + relative) from error
    if not isinstance(value, dict):
        raise _fail("control record is not an object: " + relative)
    return value, raw


def _identity(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise _fail(label + " is not an identity object")
    fields = (
        "owner_token", "process_start_token", "pid", "host", "target_id", "control_address",
        "build_commit", "build_snapshot", "compute_pool_id", "preparation_pool_id",
        "compute_pool_generation", "preparation_pool_generation",
    )
    if not any(field in value for field in fields):
        raise _fail(label + " is empty")
    return {field: value.get(field) for field in fields}


_WINDOWS_CERTIFICATE_IDENTITY_FIELDS = {
    "schema", "storage_profile", "role", "owner_scope", "owner_token", "engine_id",
    "host_root", "host_filesystem", "host_drive_type", "host_volume_serial",
    "host_root_no_reparse",
}
_LINUX_CERTIFICATE_IDENTITY_FIELDS = {
    "schema", "storage_profile", "role", "owner_scope", "owner_token", "engine_id",
    "host_root", "host_filesystem", "host_platform", "host_device",
    "host_root_no_reparse", "host_inode",
}


def _validate_certificate_stable_identity(value: object) -> dict[str, object]:
    """Validate the certificate fields that survive an image rotation.

    ``reuse_certificate`` deliberately changes image, source, binary and
    artifact fields.  The storage/engine/operator identity below is the closed
    part of the old certificate that the runtime may compare with the newly
    admitted certificate.  Raw certificate hashes remain historical evidence;
    they are not a prediction of the post-rotation bytes.
    """
    if not isinstance(value, Mapping):
        raise _fail("certificate stable identity is not an object")
    profile = value.get("storage_profile")
    if profile == "windows-folder-v1":
        required = _WINDOWS_CERTIFICATE_IDENTITY_FIELDS
        schema = "fullmag.windows-folder-host.v1"
        scope = "docker-desktop-linux"
        token_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    elif profile == "linux-native-v1":
        required = _LINUX_CERTIFICATE_IDENTITY_FIELDS
        schema = "fullmag.linux-native-host.v1"
        scope = "docker-linux"
        token_pattern = re.compile(r"^[0-9a-f]{32}$")
    else:
        raise _fail("certificate stable identity has an unsupported storage profile")
    if set(value) != required:
        raise _fail("certificate stable identity field set differs")
    if (value.get("schema") != schema or value.get("role") != "session"
            or value.get("owner_scope") != scope):
        raise _fail("certificate stable identity ownership scope differs")
    token = value.get("owner_token")
    if not isinstance(token, str) or token_pattern.fullmatch(token) is None or set(token.replace("-", "")) == {"0"}:
        raise _fail("certificate stable identity owner token is invalid")
    _text(value.get("engine_id"), "certificate stable identity Docker engine", maximum=256)
    _text(value.get("host_root"), "certificate stable identity host root", maximum=4096)
    _text(value.get("host_filesystem"), "certificate stable identity filesystem", maximum=64)
    if value.get("host_root_no_reparse") is not True:
        raise _fail("certificate stable identity permits reparse roots")
    if profile == "windows-folder-v1":
        if type(value.get("host_drive_type")) is not int or value["host_drive_type"] != 3:
            raise _fail("certificate stable identity Windows drive type differs")
        if type(value.get("host_volume_serial")) is not int or value["host_volume_serial"] < 0:
            raise _fail("certificate stable identity Windows volume serial is invalid")
    else:
        _text(value.get("host_platform"), "certificate stable identity host platform", maximum=64)
        if type(value.get("host_device")) is not int or value["host_device"] <= 0:
            raise _fail("certificate stable identity Linux device is invalid")
        if type(value.get("host_inode")) is not int or value["host_inode"] <= 0:
            raise _fail("certificate stable identity Linux inode is invalid")
    return dict(value)


def certificate_stable_identity(certificate: Mapping[str, object]) -> dict[str, object]:
    """Extract and validate the immutable host identity from a certificate."""
    if not isinstance(certificate, Mapping):
        raise _fail("host certificate is not an object")
    profile = certificate.get("storage_profile")
    fields = (
        _WINDOWS_CERTIFICATE_IDENTITY_FIELDS
        if profile == "windows-folder-v1"
        else _LINUX_CERTIFICATE_IDENTITY_FIELDS
        if profile == "linux-native-v1"
        else set()
    )
    if not fields:
        raise _fail("host certificate has an unsupported storage profile")
    return _validate_certificate_stable_identity({key: certificate.get(key) for key in fields})


def _validate_source(source: Mapping[str, object], project: str) -> dict[str, object]:
    required = {"source_root", "project_id", "worktree_id", "checkout_kind"}
    if set(source) != required:
        raise _fail("source identity field set differs")
    if not isinstance(source["project_id"], str):
        raise _fail("source project identity is invalid")
    return {
        "source_root": _text(source["source_root"], "source root"),
        "project_id": _text(source["project_id"], "source project id", maximum=256),
        "worktree_id": _text(source["worktree_id"], "source worktree id", maximum=256),
        "checkout_kind": _text(source["checkout_kind"], "source checkout kind", maximum=64),
    }


def _validate_actual_namespace(
    actual: Mapping[str, object], *, project: str, project_id: str,
    worktree_id: str, checkout_kind: str, image_id: str,
) -> dict[str, object]:
    if actual.get("Image") != image_id:
        raise _fail("current stopped namespace image differs from retained image")
    identifier = _container(actual.get("Id"), "current stopped namespace container")
    state = actual.get("State")
    if not isinstance(state, Mapping) or state.get("Running") is not False or state.get("Status") != "exited":
        raise _fail("current backend is not an actually stopped namespace")
    started = _text(state.get("StartedAt"), "current stopped namespace StartedAt")
    finished = _text(state.get("FinishedAt"), "current stopped namespace FinishedAt")
    if type(state.get("ExitCode")) is not int:
        raise _fail("current stopped namespace has no integer exit code")
    config = actual.get("Config")
    labels = config.get("Labels") if isinstance(config, Mapping) else None
    if not isinstance(labels, Mapping):
        raise _fail("current stopped namespace has no Docker labels")
    if (labels.get("com.docker.compose.project") != project
            or labels.get("org.fullmag.source.project-id") != project_id
            or labels.get("org.fullmag.source.checkout-kind") != checkout_kind
            or labels.get("com.docker.compose.service") != "backend"
            or labels.get("org.fullmag.source.worktree-id") != worktree_id):
        raise _fail("current stopped namespace ownership differs")
    return {
        "container_id": identifier,
        "image_id": image_id,
        "started_at": started,
        "finished_at": finished,
        "exit_code": state["ExitCode"],
    }


def _validate_process_receipt(process: Mapping[str, object], label: str) -> dict[str, object]:
    if set(process) != set(PROCESS_KEYS):
        raise _fail(label + " is not the exact nine-key API-before-owner receipt")
    if process["schema"] != PROCESS_SCHEMA or process["state"] != "shutdown_unknown":
        raise _fail(label + " is not shutdown_unknown")
    if type(process["api_pid"]) is not int or process["api_pid"] <= 0:
        raise _fail(label + " has an invalid API pid")
    if type(process["api_exit_code"]) is not int or process["api_exit_code"] != 101:
        raise _fail(label + " has an invalid API exit code")
    store = _text(process["accepted_store"], label + " accepted store")
    if (not PurePosixPath(store).is_absolute() or ".." in PurePosixPath(store).parts
            or not isinstance(process["bootstrap"], Mapping)
            or process["qualification"] != "NOT VERIFIED"):
        raise _fail(label + " has invalid store/bootstrap/qualification fields")
    if process["error"] != PROCESS_ERROR or process["shutdown_error"] != PROCESS_SHUTDOWN_ERROR:
        raise _fail(label + " does not contain the canonical API binding failure")
    return dict(process)


def _validate_terminal_process_receipt(
    process: Mapping[str, object], failure_kind: object,
) -> dict[str, object]:
    """Validate the archived shutdown receipt without treating it as current."""
    if (process.get("schema") != PROCESS_SCHEMA
            or process.get("state") != "shutdown_unknown"
            or "terminal_service_owner" in process
            or type(process.get("api_exit_code")) is not int
            or process.get("runtime_pid") is not None):
        raise _fail("original terminal process receipt is not canonical")
    if failure_kind == "native-start-failure" and "service_owner" in process:
        raise _fail("native-start-failure terminal receipt contains a new owner")
    if failure_kind == "native-after-ready-failure":
        if not isinstance(process.get("service_owner"), Mapping):
            raise _fail("after-ready terminal receipt has no retained ready owner")
    return dict(process)


def _validate_failed_owner(owner: Mapping[str, object], expected: Mapping[str, object]) -> dict[str, object]:
    if owner != expected:
        raise _fail("current Failed OWNER.json differs from immutable stop evidence")
    if owner.get("schema_version") != "runtime_service_owner.v1" or owner.get("state") != "failed":
        raise _fail("current owner is not the unchanged Failed owner")
    _identity(owner, "current Failed owner")
    children = owner.get("children")
    if not isinstance(children, list) or len(children) != 2:
        raise _fail("current Failed owner has no exact child identity")
    return dict(owner)


def _accepted_metadata(context: Mapping[str, object]) -> dict[str, object]:
    pins = context.get("accepted_reattach_metadata")
    environment = context.get("accepted_reattach_environment")
    if not isinstance(pins, Mapping) or not isinstance(environment, Mapping):
        raise _unavailable("held accepted-run proof is unavailable")
    if pins.get("schema") != "fullmag.docker-accepted-run-reattach-producer.v1" or pins.get("state") != "prepared":
        raise _fail("held accepted-run proof is not prepared")
    expected_environment = {
        "FULLMAG_ACCEPTED_REATTACH_REQUEST": pins.get("request_relative"),
        "FULLMAG_ACCEPTED_REATTACH_REQUEST_SHA256": pins.get("request_sha256"),
    }
    if dict(environment) != expected_environment:
        raise _fail("held accepted-run environment differs from its pins")
    for key in ("request_sha256", "proof_sha256", "terminal_process_record_sha256",
                "terminal_owner_record_sha256", "stop_reconcile_proof_sha256",
                "stop_verification_sha256"):
        _sha(pins.get(key), "accepted-run " + key)
    for key in (
        "run_id", "project_id", "store_run_relative", "request_relative", "proof_relative",
        "source_root", "source_relative", "compose_project", "control_volume",
        "logical_session_id", "stop_verification_relative", "terminal_process_record_relative",
        "terminal_owner_record_relative", "development_attempt", "activation_attempt",
        "reconciliation_attempt",
    ):
        _text(pins.get(key), "accepted-run " + key)
    _positive(pins.get("session_epoch"), "accepted-run session epoch")
    _relative(pins["source_relative"], "accepted-run source relative path")
    _relative(pins["stop_verification_relative"], "accepted-run stop verification path")
    _relative(pins["terminal_process_record_relative"], "accepted-run terminal process path")
    _relative(pins["terminal_owner_record_relative"], "accepted-run terminal owner path")
    accepted_backend = _container(pins.get("backend_container"), "accepted-run backend container")
    accepted_image = _image(pins.get("image_id"), "accepted-run backend image")
    expected_stop = "verification/stop-failed-" + accepted_backend + ".json"
    if pins["stop_verification_relative"] != expected_stop:
        raise _fail("accepted-run stop verification path is not bound to its backend")
    _positive(pins.get("catalog_revision"), "accepted-run catalog revision")
    _positive(pins.get("task_count"), "accepted-run task count")
    return {
        "schema": pins["schema"],
        "state": pins["state"],
        "run_id": pins["run_id"],
        "project_id": pins["project_id"],
        "store_run_relative": pins["store_run_relative"],
        "request_relative": pins["request_relative"],
        "request_sha256": pins["request_sha256"],
        "proof_relative": pins["proof_relative"],
        "source_root": pins["source_root"],
        "source_relative": pins["source_relative"],
        "compose_project": pins["compose_project"],
        "control_volume": pins["control_volume"],
        "logical_session_id": pins["logical_session_id"],
        "session_epoch": pins["session_epoch"],
        "stop_verification_relative": pins["stop_verification_relative"],
        "terminal_process_record_relative": pins["terminal_process_record_relative"],
        "terminal_owner_record_relative": pins["terminal_owner_record_relative"],
        "development_attempt": pins["development_attempt"],
        "activation_attempt": pins["activation_attempt"],
        "reconciliation_attempt": pins["reconciliation_attempt"],
        "backend_container": accepted_backend,
        "image_id": accepted_image,
        "proof_sha256": pins["proof_sha256"],
        "terminal_process_record_sha256": pins["terminal_process_record_sha256"],
        "terminal_owner_record_sha256": pins["terminal_owner_record_sha256"],
        "stop_reconcile_proof_sha256": pins["stop_reconcile_proof_sha256"],
        "stop_verification_sha256": pins["stop_verification_sha256"],
        "catalog_revision": pins["catalog_revision"],
        "task_count": pins["task_count"],
    }


def _resolve_previous_backend(
    previous: Mapping[str, object],
    *,
    project: object,
    image_id: str,
    label: str,
) -> str:
    """Resolve the retained backend from the terminal or worker-cgroup pin."""
    recorded_backend = previous.get("backend_container")
    if recorded_backend is None:
        cgroup = previous.get("worker_cgroup")
        if (
            not isinstance(cgroup, Mapping)
            or cgroup.get("schema") != "fullmag.worker-cgroup-ready.v1"
            or cgroup.get("state") != "ready"
            or cgroup.get("compose_project") != project
            or cgroup.get("image_id") != image_id
        ):
            raise _unavailable("retained operation has no exact backend container binding")
        recorded_backend = cgroup.get("container_id")
    return _container(recorded_backend, label)


def _read_original_stop(
    control,
    previous: Mapping[str, object],
    image_id: str,
    accepted: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], bytes, str]:
    """Read the old stop archive through an immutable accepted lineage pin.

    A recreate may observe a successor Docker namespace and image.  When the
    accepted producer is present, its stop path/backend/image are the only
    valid archive identity; ``previous`` identifies the current namespace
    separately and is never used to guess an older journal path.
    """
    if accepted:
        original_id = _container(accepted.get("backend_container"), "accepted original backend")
        original_image = _image(accepted.get("image_id"), "accepted original image")
        relative = _relative(accepted.get("stop_verification_relative"), "accepted stop verification path")
        if relative != "verification/stop-failed-" + original_id + ".json":
            raise _fail("accepted stop verification path is not bound to its backend")
        if accepted.get("stop_verification_sha256") is None:
            raise _fail("accepted stop verification digest is missing")
    else:
        original_id = _resolve_previous_backend(
            previous, project=getattr(control, "project", None),
            image_id=image_id, label="original stopped backend"
        )
        original_image = image_id
        relative = "verification/stop-failed-" + original_id + ".json"
    journal, raw = _read_json(control, relative)
    if journal is None or raw is None:
        raise _unavailable("original stop journal is unavailable: " + relative)
    if (journal.get("schema") != STOP_SCHEMA or journal.get("state") != "stopped-confirmed"
            or journal.get("container_id") != original_id or journal.get("image_id") != original_image):
        raise _fail("original stop journal identity/state differs")
    if accepted and hashlib.sha256(raw).hexdigest() != accepted["stop_verification_sha256"]:
        raise _fail("accepted stop verification bytes differ")
    failure = journal.get("failure_receipt")
    probe = journal.get("native_failure_probe")
    if not isinstance(failure, Mapping) or not isinstance(probe, Mapping):
        raise _fail("original stop journal has incomplete native evidence")
    process_sha = _sha(failure.get("sha256"), "original process receipt")
    if probe.get("process_receipt_sha256") != process_sha or probe.get("process_receipt") != failure.get("receipt"):
        raise _fail("original stop journal process evidence differs")
    try:
        from docker_volume_stop_failed import (
            _validate_native_after_ready_failure_probe,
            _validate_native_failure_probe,
        )
        if journal.get("failure_kind") == "native-after-ready-failure":
            _validate_native_after_ready_failure_probe(probe, process_sha)
        elif journal.get("failure_kind") == "native-start-failure":
            _validate_native_failure_probe(
                probe, process_sha, api_start_failure=journal.get("failure_mode") == "api-start-failure"
            )
        else:
            raise _fail("original stop journal failure kind is unsupported")
    except ImportError as error:
        raise _unavailable("native stop proof validator is unavailable") from error
    except BuildControlError as error:
        raise _fail("original native stop proof is invalid: " + str(error)) from error
    owner = journal.get("terminal_failed_owner")
    if not isinstance(owner, Mapping):
        raise _fail("original stop journal has no Failed owner")
    _sha(journal.get("terminal_failed_owner_sha256"), "original Failed owner")
    terminal = journal.get("terminal_process_receipt")
    if not isinstance(terminal, Mapping):
        raise _fail("original stop journal has no terminal process receipt")
    _validate_terminal_process_receipt(terminal, journal.get("failure_kind"))
    return journal, raw, relative


def _validate_recreate_operation(value: object) -> dict[str, object]:
    """Validate the completed recreate boundary carried into a new start.

    This record is deliberately separate from ``operation_id``.  The latter
    identifies the development attempt that produced the failed owner proof;
    this record identifies the later ``recreate-services`` operation whose
    terminal/snapshot/absence evidence permits the old Docker namespace to be
    treated as removed.  It contains no claim that the removed namespace is
    live or inspectable.
    """
    if not isinstance(value, Mapping):
        raise _fail("continuation recreate operation is not an object")
    required = {
        "schema", "operation_id", "terminal_relative", "terminal_sha256",
        "retained_relative", "retained_sha256", "prior_terminal_sha256",
        "prior_compose_sha256", "backend_container", "frontend_container",
        "image_id", "absence",
    }
    if set(value) != required or value.get("schema") != RECREATE_SCHEMA:
        raise _fail("continuation recreate operation field set/schema differs")
    operation_id = _token(value.get("operation_id"), "continuation recreate operation")
    for key in ("terminal_sha256", "retained_sha256", "prior_terminal_sha256", "prior_compose_sha256"):
        _sha(value.get(key), "continuation recreate " + key)
    expected_root = "recreate-services/attempts/" + operation_id
    if value.get("terminal_relative") != expected_root + "/terminal.json":
        raise _fail("continuation recreate terminal path differs")
    if value.get("retained_relative") != expected_root + "/retained-containers.json":
        raise _fail("continuation recreate snapshot path differs")
    backend = _container(value.get("backend_container"), "continuation recreate backend")
    frontend = _container(value.get("frontend_container"), "continuation recreate frontend")
    if backend == frontend:
        raise _fail("continuation recreate services share one container identity")
    _image(value.get("image_id"), "continuation recreate image")
    absence = value.get("absence")
    if not isinstance(absence, Mapping) or set(absence) != {"backend", "frontend"}:
        raise _fail("continuation recreate absence proof is incomplete")
    for service, expected_id in (("backend", backend), ("frontend", frontend)):
        item = absence.get(service)
        if not isinstance(item, Mapping) or set(item) != {
            "container_id", "inspect_returncode", "inspect_output_sha256",
            "ps_returncode", "ps_output_sha256",
        }:
            raise _fail("continuation recreate absence proof is malformed: " + service)
        if _container(item.get("container_id"), "continuation recreate absence container") != expected_id:
            raise _fail("continuation recreate absence container differs: " + service)
        if type(item.get("inspect_returncode")) is not int or item["inspect_returncode"] <= 0:
            raise _fail("continuation recreate inspect did not fail: " + service)
        if item.get("ps_returncode") != 0:
            raise _fail("continuation recreate ps absence command failed: " + service)
        _sha(item.get("inspect_output_sha256"), "continuation recreate inspect output")
        _sha(item.get("ps_output_sha256"), "continuation recreate ps output")
    return dict(value)


def _recreate_operation_from_proof(proof: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(proof, Mapping):
        raise _fail("recreation proof is not an object")
    required = {
        "recreation_operation_id", "recreation_terminal_sha256", "retained_snapshot_sha256",
        "prior_terminal_sha256", "prior_compose_sha256", "container_id", "frontend_container",
        "image_id", "absence",
    }
    if not required.issubset(proof):
        raise _fail("recreation proof has no exact terminal/snapshot/absence evidence")
    operation_id = _token(proof["recreation_operation_id"], "recreation operation")
    record = {
        "schema": RECREATE_SCHEMA,
        "operation_id": operation_id,
        "terminal_relative": "recreate-services/attempts/" + operation_id + "/terminal.json",
        "terminal_sha256": proof["recreation_terminal_sha256"],
        "retained_relative": "recreate-services/attempts/" + operation_id + "/retained-containers.json",
        "retained_sha256": proof["retained_snapshot_sha256"],
        "prior_terminal_sha256": proof["prior_terminal_sha256"],
        "prior_compose_sha256": proof["prior_compose_sha256"],
        "backend_container": proof["container_id"],
        "frontend_container": proof["frontend_container"],
        "image_id": proof["image_id"],
        "absence": proof["absence"],
    }
    return _validate_recreate_operation(record)


def bind_recreate_operation(metadata: Mapping[str, object], proof: Mapping[str, object]) -> dict[str, object]:
    """Attach a completed recreation proof after its lease has closed."""
    base = _validate_metadata_shape(metadata)
    record = _recreate_operation_from_proof(proof)
    existing = base.pop("recreate_operation", None)
    if existing is not None and _validate_recreate_operation(existing) != record:
        raise _fail("continuation recreate operation proof changed")
    base["recreate_operation"] = record
    return _validate_metadata_shape(base, require_recreate=True)


def _validate_metadata_shape(
    metadata: Mapping[str, object], *, require_recreate: bool = False
) -> dict[str, object]:
    if not isinstance(metadata, Mapping):
        raise _fail("post-build continuation metadata is not an object")
    required = {
        "schema", "state", "operation_id", "compose_project", "source_root", "source_identity",
        "original_stop", "current_namespace", "failed_owner", "current_process",
        "runtime_config", "certificate", "accepted_run",
    }
    allowed = required | {"recreate_operation"}
    if set(metadata) not in (required, allowed) or (
        require_recreate and "recreate_operation" not in metadata
    ):
        raise _fail("post-build continuation metadata has an unexpected field set")
    if metadata["schema"] != SCHEMA or metadata["state"] != STATE:
        raise _fail("post-build continuation metadata schema/state is unsupported")
    _token(metadata["operation_id"], "continuation operation")
    _text(metadata["compose_project"], "continuation Compose project")
    _text(metadata["source_root"], "continuation source root")
    source = metadata["source_identity"]
    if not isinstance(source, Mapping) or set(source) != {"project_id", "worktree_id", "checkout_kind"}:
        raise _fail("continuation source identity is incomplete")
    for key in source:
        _text(source[key], "continuation source " + key, maximum=256)
    original = metadata["original_stop"]
    if not isinstance(original, Mapping) or set(original) != {
        "relative", "sha256", "container_id", "image_id", "failure_kind",
        "native_failure_probe_sha256", "terminal_process_sha256", "terminal_owner_sha256",
    }:
        raise _fail("continuation original stop record is incomplete")
    _relative(original["relative"], "continuation original stop path")
    for key in ("sha256", "native_failure_probe_sha256", "terminal_process_sha256", "terminal_owner_sha256"):
        _sha(original[key], "continuation original stop " + key)
    _container(original["container_id"], "continuation original container")
    _image(original["image_id"], "continuation original image")
    _text(original["failure_kind"], "continuation failure kind", maximum=64)
    current = metadata["current_namespace"]
    if not isinstance(current, Mapping) or set(current) != {"container_id", "image_id", "started_at", "finished_at", "exit_code"}:
        raise _fail("continuation current namespace record is incomplete")
    _container(current["container_id"], "continuation current container")
    _image(current["image_id"], "continuation current image")
    _text(current["started_at"], "continuation current StartedAt")
    _text(current["finished_at"], "continuation current FinishedAt")
    if type(current["exit_code"]) is not int:
        raise _fail("continuation current exit code is invalid")
    owner = metadata["failed_owner"]
    if not isinstance(owner, Mapping) or set(owner) != {"relative", "sha256", "identity"}:
        raise _fail("continuation Failed owner record is incomplete")
    _relative(owner["relative"], "continuation owner path")
    _sha(owner["sha256"], "continuation owner")
    _identity(owner["identity"], "continuation owner identity")
    process = metadata["current_process"]
    if not isinstance(process, Mapping) or set(process) != {"relative", "sha256", "immutable_keys", "api_pid", "api_exit_code", "error_sha256", "shutdown_error_sha256"}:
        raise _fail("continuation process record is incomplete")
    _relative(process["relative"], "continuation process path")
    _sha(process["sha256"], "continuation process")
    if process["immutable_keys"] != list(PROCESS_KEYS) or type(process["api_pid"]) is not int or process["api_pid"] <= 0 or type(process["api_exit_code"]) is not int or process["api_exit_code"] != 101:
        raise _fail("continuation process record is not canonical")
    _sha(process["error_sha256"], "continuation process error")
    _sha(process["shutdown_error_sha256"], "continuation process shutdown error")
    config = metadata["runtime_config"]
    if not isinstance(config, Mapping) or set(config) != {"relative", "sha256"}:
        raise _fail("continuation runtime config record is incomplete")
    if config["relative"] != CONFIG_RELATIVE:
        raise _fail("continuation runtime config path differs")
    _sha(config["sha256"], "continuation runtime config")
    certificate = metadata["certificate"]
    certificate_fields = {
        "historical_certificate_sha256", "historical_owner_marker_sha256",
        "stable_identity", "storage_profile", "restart_verified",
    }
    if not isinstance(certificate, Mapping) or set(certificate) != certificate_fields:
        raise _fail("continuation certificate record is incomplete")
    _sha(certificate["historical_certificate_sha256"], "continuation historical certificate")
    _sha(certificate["historical_owner_marker_sha256"], "continuation historical owner marker")
    stable_identity = _validate_certificate_stable_identity(certificate["stable_identity"])
    _text(certificate["storage_profile"], "continuation storage profile", maximum=64)
    if certificate["storage_profile"] != stable_identity["storage_profile"]:
        raise _fail("continuation certificate profile differs from stable identity")
    if certificate["restart_verified"] is not True:
        raise _fail("continuation certificate is not restart_verified")
    if "recreate_operation" in metadata:
        recreate = _validate_recreate_operation(metadata["recreate_operation"])
        current_namespace = metadata["current_namespace"]
        if (
            recreate["backend_container"] != current_namespace["container_id"]
            or recreate["image_id"] != current_namespace["image_id"]
            or recreate["backend_container"] == recreate["frontend_container"]
        ):
            raise _fail("continuation recreate operation is not bound to the current namespace")
    accepted = metadata["accepted_run"]
    if accepted != {}:
        accepted_required = {
            "schema", "state", "run_id", "project_id", "store_run_relative", "request_relative",
            "proof_relative", "source_root", "source_relative", "compose_project", "control_volume",
            "logical_session_id", "session_epoch", "stop_verification_relative",
            "terminal_process_record_relative", "terminal_owner_record_relative", "development_attempt",
            "activation_attempt", "reconciliation_attempt", "backend_container", "image_id",
            "request_sha256", "proof_sha256", "terminal_process_record_sha256",
            "terminal_owner_record_sha256", "stop_reconcile_proof_sha256", "stop_verification_sha256",
            "catalog_revision", "task_count",
        }
        if not isinstance(accepted, Mapping) or set(accepted) != accepted_required:
            raise _fail("continuation accepted-run record is malformed")
        if accepted["schema"] != "fullmag.docker-accepted-run-reattach-producer.v1" or accepted["state"] != "prepared":
            raise _fail("continuation accepted-run state differs")
        for key in (
            "request_sha256", "proof_sha256", "terminal_process_record_sha256",
            "terminal_owner_record_sha256", "stop_reconcile_proof_sha256", "stop_verification_sha256",
        ):
            _sha(accepted.get(key), "continuation accepted-run " + key)
        for key in (
            "run_id", "project_id", "store_run_relative", "request_relative", "proof_relative",
            "source_root", "source_relative", "compose_project", "control_volume", "logical_session_id",
            "stop_verification_relative", "terminal_process_record_relative",
            "terminal_owner_record_relative", "development_attempt", "activation_attempt",
            "reconciliation_attempt",
        ):
            _text(accepted.get(key), "continuation accepted-run " + key)
        for key in (
            "source_relative", "stop_verification_relative", "terminal_process_record_relative",
            "terminal_owner_record_relative",
        ):
            _relative(accepted[key], "continuation accepted-run " + key)
        accepted_backend = _container(accepted["backend_container"], "continuation accepted-run backend")
        _image(accepted["image_id"], "continuation accepted-run image")
        if accepted["stop_verification_relative"] != "verification/stop-failed-" + accepted_backend + ".json":
            raise _fail("continuation accepted-run stop path is not bound to its backend")
        _positive(accepted["session_epoch"], "continuation accepted-run session epoch")
        _positive(accepted["catalog_revision"], "continuation accepted-run catalog revision")
        _positive(accepted["task_count"], "continuation accepted-run task count")
    return dict(metadata)


def validate_continuation_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    """Validate the closed metadata carried in a recreate receipt/start."""
    return _validate_metadata_shape(metadata, require_recreate=True)


def prepare_start_binding(metadata: Mapping[str, object], operation: Mapping[str, object]) -> dict[str, object]:
    """Bind one continuation to the active development operation.

    The binding is written before Compose creates the backend.  It contains
    the closed host proof and the operation token; PID 1 can therefore reject
    an old environment after a failed or abandoned host operation instead of
    treating ``previous_config_sha256`` as a bearer capability.
    """
    metadata = _validate_metadata_shape(metadata, require_recreate=True)
    receipt = operation.get("receipt")
    root = operation.get("root")
    if not isinstance(receipt, Mapping) or not isinstance(root, str):
        raise _fail("continuation start binding has no managed operation")
    token = _token(receipt.get("attempt"), "continuation start attempt")
    expected_root = "development/attempts/" + token
    if root != expected_root or receipt.get("phase") != "development":
        raise _fail("continuation start binding is outside the active development operation")
    metadata_raw = canonical(metadata) + b"\n"
    metadata_sha = hashlib.sha256(metadata_raw).hexdigest()
    relative = expected_root + "/" + START_BINDING_RELATIVE_NAME
    guest_path = "/opt/fullmag/control/" + relative
    binding = {
        "schema": START_BINDING_SCHEMA,
        "state": "pending",
        "attempt": token,
        "receipt_relative": expected_root + "/receipt.json",
        "active_relative": "active",
        "active_token": token,
        "continuation_relative": relative,
        "continuation_sha256": metadata_sha,
        "previous_config_sha256": metadata["runtime_config"]["sha256"],
        "continuation": metadata,
    }
    binding_raw = canonical(binding) + b"\n"
    binding_sha = hashlib.sha256(binding_raw).hexdigest()
    receipt_ref = {
        "schema": START_BINDING_SCHEMA,
        "state": "pending",
        "path": guest_path,
        "sha256": binding_sha,
        "continuation_sha256": metadata_sha,
    }
    return {
        "relative": relative,
        "path": guest_path,
        "sha256": binding_sha,
        "metadata_sha256": metadata_sha,
        "record": binding,
        "receipt": receipt_ref,
        "environment": {
            START_BINDING_ENV: guest_path,
            START_BINDING_SHA_ENV: binding_sha,
        },
    }


def validate_start_binding(binding: Mapping[str, object]) -> dict[str, object]:
    """Validate a binding copied into a development receipt or fixture."""
    if not isinstance(binding, Mapping):
        raise _fail("continuation start binding is not an object")
    required = {
        "schema", "state", "attempt", "receipt_relative", "active_relative",
        "active_token", "continuation_relative", "continuation_sha256",
        "previous_config_sha256", "continuation",
    }
    if set(binding) != required or binding.get("schema") != START_BINDING_SCHEMA:
        raise _fail("continuation start binding field set/schema differs")
    if binding.get("state") not in {"pending", "consumed"}:
        raise _fail("continuation start binding state is unsupported")
    token = _token(binding.get("attempt"), "continuation start attempt")
    if binding.get("active_token") != token or binding.get("active_relative") != "active":
        raise _fail("continuation start binding active marker differs")
    expected_root = "development/attempts/" + token
    if binding.get("receipt_relative") != expected_root + "/receipt.json":
        raise _fail("continuation start binding receipt path differs")
    relative = expected_root + "/" + START_BINDING_RELATIVE_NAME
    if binding.get("continuation_relative") != relative:
        raise _fail("continuation start binding continuation path differs")
    metadata = _validate_metadata_shape(binding.get("continuation"), require_recreate=True)
    metadata_raw = canonical(metadata) + b"\n"
    metadata_sha = hashlib.sha256(metadata_raw).hexdigest()
    if binding.get("continuation_sha256") != metadata_sha:
        raise _fail("continuation start binding proof digest differs")
    if binding.get("previous_config_sha256") != metadata["runtime_config"]["sha256"]:
        raise _fail("continuation start binding config digest differs")
    return dict(binding)


def _metadata_for_records(
    control,
    *,
    operation_id: str,
    previous: Mapping[str, object],
    document: Mapping[str, object],
    actual_backend: Mapping[str, object],
    source_identity: Mapping[str, object],
    certificate_evidence: Mapping[str, object],
    accepted_context: Mapping[str, object] | None,
    runtime_config_sha256: str,
) -> dict[str, object]:
    operation_id = _token(operation_id, "continuation operation")
    previous_attempt = _token(previous.get("attempt"), "retained development attempt")
    if operation_id != previous_attempt:
        raise _fail("continuation operation differs from retained development attempt")
    if document.get("name") != control.project:
        raise _fail("continuation Compose project differs")
    inputs = previous.get("inputs")
    if not isinstance(inputs, Mapping):
        raise _fail("continuation retained record has no inputs")
    source = _validate_source(source_identity, control.project)
    if inputs.get("source_root") != source["source_root"]:
        raise _fail("continuation source differs from retained record")
    image_id = _image(inputs.get("image_id"), "continuation retained image")
    namespace = _validate_actual_namespace(
        actual_backend,
        project=control.project,
        project_id=source["project_id"],
        worktree_id=source["worktree_id"],
        checkout_kind=source["checkout_kind"],
        image_id=image_id,
    )
    accepted = {} if not accepted_context else _accepted_metadata(accepted_context)
    recorded_backend = _resolve_previous_backend(
        previous, project=control.project, image_id=image_id, label="retained backend"
    )
    if recorded_backend != namespace["container_id"]:
        raise _fail("current backend container differs from retained operation")
    journal, journal_raw, journal_relative = _read_original_stop(
        control, previous, image_id, accepted
    )
    terminal = journal["terminal_process_receipt"]
    failed_owner = journal["terminal_failed_owner"]
    _validate_failed_owner(failed_owner, failed_owner)
    current_owner, owner_raw = _read_json(control, CONTROL_OWNER)
    if current_owner is None or owner_raw is None:
        raise _unavailable("current Failed OWNER.json is unavailable")
    _validate_failed_owner(current_owner, failed_owner)
    current_process, process_raw = _read_json(control, CONTROL_PROCESS)
    if current_process is None or process_raw is None:
        raise _unavailable("current API-before-owner process receipt is unavailable")
    current_process = _validate_process_receipt(current_process, "current process receipt")
    if accepted and (
        accepted["source_root"] != source["source_root"]
        or accepted["compose_project"] != control.project
        or accepted["control_volume"] != getattr(control, "volume", None)
    ):
        raise _fail("accepted-run source or control identity differs")
    _sha(runtime_config_sha256, "continuation runtime config")
    config_raw = _read_raw(control, CONFIG_RELATIVE)
    if config_raw is None or hashlib.sha256(config_raw).hexdigest() != runtime_config_sha256:
        raise _fail("native runtime configuration bytes differ from the pinned digest")
    if not isinstance(certificate_evidence, Mapping) or set(certificate_evidence) != {
        "historical_certificate_sha256", "historical_owner_marker_sha256",
        "stable_identity", "storage_profile", "restart_verified",
    }:
        raise _fail("continuation certificate evidence is incomplete")
    certificate = dict(certificate_evidence)
    if certificate["restart_verified"] is not True:
        raise _fail("continuation requires restart_verified=true")
    _sha(certificate["historical_certificate_sha256"], "continuation historical certificate")
    _sha(certificate["historical_owner_marker_sha256"], "continuation historical owner marker")
    stable_identity = _validate_certificate_stable_identity(certificate["stable_identity"])
    _text(certificate["storage_profile"], "continuation storage profile", maximum=64)
    if certificate["storage_profile"] != stable_identity["storage_profile"]:
        raise _fail("continuation certificate profile differs from stable identity")
    failure = journal.get("failure_receipt")
    probe = journal.get("native_failure_probe")
    if not isinstance(failure, Mapping) or not isinstance(probe, Mapping):
        raise _fail("original stop journal has incomplete native evidence")
    canonical_terminal_sha = hashlib.sha256(canonical(terminal) + b"\n").hexdigest()
    recorded_terminal_sha = journal.get("terminal_process_receipt_sha256")
    if recorded_terminal_sha is None:
        original_terminal_sha = (
            accepted["terminal_process_record_sha256"]
            if accepted else canonical_terminal_sha
        )
    else:
        original_terminal_sha = _sha(recorded_terminal_sha, "original terminal process")
        if original_terminal_sha != canonical_terminal_sha:
            raise _fail("original terminal process digest differs from its canonical receipt")
    original_terminal_sha = _sha(original_terminal_sha, "original terminal process")
    original_owner_sha = journal.get("terminal_failed_owner_sha256")
    if original_owner_sha is None and accepted:
        original_owner_sha = accepted["terminal_owner_record_sha256"]
    original_owner_sha = _sha(original_owner_sha, "original Failed owner")
    if accepted:
        if accepted["terminal_process_record_sha256"] != original_terminal_sha:
            raise _fail("accepted-run terminal process pin differs from original stop proof")
        if accepted["terminal_owner_record_sha256"] != original_owner_sha:
            raise _fail("accepted-run terminal owner pin differs from original stop proof")
        terminal_sha = hashlib.sha256(canonical(terminal) + b"\n").hexdigest()
        if accepted["terminal_process_record_sha256"] != terminal_sha:
            raise _fail("accepted-run terminal process pin differs from archived terminal receipt")
        if accepted["image_id"] != journal["image_id"] or accepted["backend_container"] != journal["container_id"]:
            raise _fail("accepted-run stop archive identity differs")
    if hashlib.sha256(owner_raw).hexdigest() != original_owner_sha:
        raise _fail("current Failed owner bytes differ from original stop proof")
    metadata = {
        "schema": SCHEMA,
        "state": STATE,
        "operation_id": operation_id,
        "compose_project": control.project,
        "source_root": source["source_root"],
        "source_identity": {
            "project_id": source["project_id"],
            "worktree_id": source["worktree_id"],
            "checkout_kind": source["checkout_kind"],
        },
        "original_stop": {
            "relative": journal_relative,
            "sha256": hashlib.sha256(journal_raw).hexdigest(),
            "container_id": journal["container_id"],
            "image_id": journal["image_id"],
            "failure_kind": journal["failure_kind"],
            "native_failure_probe_sha256": _sha(probe.get("process_receipt_sha256"), "native failure probe"),
            "terminal_process_sha256": original_terminal_sha,
            "terminal_owner_sha256": original_owner_sha,
        },
        "current_namespace": namespace,
        "failed_owner": {
            "relative": CONTROL_OWNER,
            "sha256": hashlib.sha256(owner_raw).hexdigest(),
            "identity": _identity(current_owner, "current Failed owner"),
        },
        "current_process": {
            "relative": CONTROL_PROCESS,
            "sha256": hashlib.sha256(process_raw).hexdigest(),
            "immutable_keys": list(PROCESS_KEYS),
            "api_pid": current_process["api_pid"],
            "api_exit_code": current_process["api_exit_code"],
            "error_sha256": hashlib.sha256(current_process["error"].encode()).hexdigest(),
            "shutdown_error_sha256": hashlib.sha256(current_process["shutdown_error"].encode()).hexdigest(),
        },
        "runtime_config": {"relative": CONFIG_RELATIVE, "sha256": runtime_config_sha256},
        "certificate": {
            "historical_certificate_sha256": certificate["historical_certificate_sha256"],
            "historical_owner_marker_sha256": certificate["historical_owner_marker_sha256"],
            "stable_identity": stable_identity,
            "storage_profile": certificate["storage_profile"],
            "restart_verified": certificate["restart_verified"],
        },
        "accepted_run": accepted,
    }
    return _validate_metadata_shape(metadata)


def build_failed_owner_continuation(
    control,
    *,
    operation_id: str,
    previous: Mapping[str, object],
    document: Mapping[str, object],
    actual_backend: Mapping[str, object],
    source_identity: Mapping[str, object],
    certificate_evidence: Mapping[str, object],
    accepted_context: Mapping[str, object] | None,
    runtime_config_sha256: str,
) -> dict[str, object]:
    """Build a closed host proof from old stop evidence and current Docker state."""
    metadata = _metadata_for_records(
        control, operation_id=operation_id, previous=previous, document=document,
        actual_backend=actual_backend, source_identity=source_identity,
        certificate_evidence=certificate_evidence, accepted_context=accepted_context,
        runtime_config_sha256=runtime_config_sha256,
    )
    return metadata


def validate_failed_owner_continuation(
    control,
    metadata: Mapping[str, object],
    *,
    operation_id: str,
    expected_project: str,
    expected_source_root: str,
    previous: Mapping[str, object],
    document: Mapping[str, object],
    actual_backend: Mapping[str, object],
    source_identity: Mapping[str, object],
    certificate_evidence: Mapping[str, object],
    accepted_context: Mapping[str, object] | None,
    runtime_config_sha256: str,
) -> dict[str, object]:
    expected = _metadata_for_records(
        control, operation_id=operation_id, previous=previous, document=document,
        actual_backend=actual_backend, source_identity=source_identity,
        certificate_evidence=certificate_evidence, accepted_context=accepted_context,
        runtime_config_sha256=runtime_config_sha256,
    )
    supplied = _validate_metadata_shape(metadata)
    if supplied["compose_project"] != expected_project or supplied["source_root"] != expected_source_root:
        raise _fail("continuation project/source differs")
    supplied_certificate = supplied["certificate"]
    expected_certificate = expected["certificate"]
    # The storage adapter rotates image/source/binary/artifact fields before
    # the new container starts.  Compare only the closed operator/host
    # identity against the admitted certificate; keep the original raw hashes
    # as historical evidence from the pre-rotation observation.
    if (
        supplied_certificate["stable_identity"] != expected_certificate["stable_identity"]
        or supplied_certificate["storage_profile"] != expected_certificate["storage_profile"]
        or supplied_certificate["restart_verified"] is not expected_certificate["restart_verified"]
    ):
        raise _fail("continuation certificate stable identity changed before stop/rm")
    expected["certificate"] = {
        **expected_certificate,
        "historical_certificate_sha256": supplied_certificate["historical_certificate_sha256"],
        "historical_owner_marker_sha256": supplied_certificate["historical_owner_marker_sha256"],
    }
    if supplied != expected:
        raise _fail("continuation proof changed before stop/rm")
    return supplied


def validate_resume_continuation(
    control,
    metadata: Mapping[str, object],
    *,
    operation_id: str,
    expected_project: str,
    expected_source_root: str,
    previous: Mapping[str, object],
    document: Mapping[str, object],
    accepted_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate immutable evidence after the old Docker namespace was removed."""
    expected_attempt = _token(previous.get("attempt"), "retained development attempt")
    operation_id = _token(operation_id, "continuation operation")
    if operation_id != expected_attempt:
        raise _fail("continuation operation differs from retained development attempt")
    supplied = _validate_metadata_shape(metadata, require_recreate=True)
    if supplied["operation_id"] != expected_attempt or supplied["compose_project"] != expected_project or supplied["source_root"] != expected_source_root:
        raise _fail("continuation resume identity differs")
    if document.get("name") != expected_project or previous.get("inputs", {}).get("source_root") != expected_source_root:
        raise _fail("continuation resume retained source differs")
    image_id = _image(previous.get("inputs", {}).get("image_id"), "continuation resume image")
    accepted = {} if not accepted_context else _accepted_metadata(accepted_context)
    original, original_raw, relative = _read_original_stop(control, previous, image_id, accepted)
    original_meta = supplied["original_stop"]
    if (original_meta["relative"] != relative or original_meta["sha256"] != hashlib.sha256(original_raw).hexdigest()
            or original_meta["container_id"] != original["container_id"]):
        raise _fail("continuation resume original stop evidence changed")
    owner, owner_raw = _read_json(control, CONTROL_OWNER)
    process, process_raw = _read_json(control, CONTROL_PROCESS)
    if owner is None or owner_raw is None or process is None or process_raw is None:
        raise _unavailable("continuation resume owner/process evidence is unavailable")
    _validate_failed_owner(owner, original.get("terminal_failed_owner"))
    process = _validate_process_receipt(process, "continuation resume process receipt")
    if hashlib.sha256(owner_raw).hexdigest() != supplied["failed_owner"]["sha256"]:
        raise _fail("continuation resume Failed owner bytes changed")
    if hashlib.sha256(process_raw).hexdigest() != supplied["current_process"]["sha256"]:
        raise _fail("continuation resume process bytes changed")
    if accepted != supplied["accepted_run"]:
        raise _fail("continuation resume accepted-run proof changed")
    return supplied


def validate_post_build_lease_evidence(
    control,
    metadata: Mapping[str, object],
    *,
    certificate_evidence: Mapping[str, object],
    accepted_context: Mapping[str, object] | None,
    runtime_config_sha256: str,
) -> dict[str, object]:
    """Revalidate a bound continuation after the new development lease opens.

    The previous Docker namespace has already been removed at this point.  The
    check therefore reads only durable terminal/snapshot records, the exact
    absence-bound IDs, and mutable owner/process records.  It never calls a
    live namespace validator for the removed container.
    """
    supplied = _validate_metadata_shape(metadata, require_recreate=True)
    recreate = _validate_recreate_operation(supplied["recreate_operation"])

    def read_canonical(relative: str, label: str) -> tuple[dict[str, object], bytes]:
        value, raw = _read_json(control, relative)
        if value is None or raw is None or raw != canonical(value) + b"\n":
            raise _fail(label + " is not a canonical control record")
        return value, raw

    terminal, terminal_raw = read_canonical(
        recreate["terminal_relative"], "completed recreation terminal"
    )
    if (
        hashlib.sha256(terminal_raw).hexdigest() != recreate["terminal_sha256"]
        or terminal.get("schema") != "fullmag.docker-build-operation.v1"
        or terminal.get("phase") != "recreate-services"
        or terminal.get("state") != "succeeded"
        or terminal.get("attempt") != recreate["operation_id"]
        or terminal.get("removed_containers") != [
            recreate["backend_container"], recreate["frontend_container"]
        ]
    ):
        raise _fail("completed recreation terminal changed or is not exact")
    snapshot, snapshot_raw = read_canonical(
        recreate["retained_relative"], "completed recreation retained snapshot"
    )
    if hashlib.sha256(snapshot_raw).hexdigest() != recreate["retained_sha256"]:
        raise _fail("completed recreation retained snapshot changed")
    if set(snapshot) != {"backend", "frontend"}:
        raise _fail("completed recreation retained snapshot service set differs")
    for service, identifier in (
        ("backend", recreate["backend_container"]),
        ("frontend", recreate["frontend_container"]),
    ):
        observed = snapshot[service]
        state = observed.get("State") if isinstance(observed, Mapping) else None
        if (
            not isinstance(observed, Mapping)
            or observed.get("Id") != identifier
            or observed.get("Image") != recreate["image_id"]
            or not isinstance(state, Mapping)
            or state.get("Running") is not False
        ):
            raise _fail("completed recreation retained snapshot differs: " + service)

    prior_root = "development/attempts/" + supplied["operation_id"]
    _prior_terminal, prior_terminal_raw = read_canonical(
        prior_root + "/terminal.json", "prior development terminal"
    )
    _prior_compose, prior_compose_raw = read_canonical(
        prior_root + "/compose.json", "prior development Compose record"
    )
    if (
        hashlib.sha256(prior_terminal_raw).hexdigest() != recreate["prior_terminal_sha256"]
        or hashlib.sha256(prior_compose_raw).hexdigest() != recreate["prior_compose_sha256"]
    ):
        raise _fail("completed recreation prior development pins changed")

    original, original_raw = read_canonical(
        supplied["original_stop"]["relative"], "original stop archive"
    )
    if (
        hashlib.sha256(original_raw).hexdigest() != supplied["original_stop"]["sha256"]
        or original.get("container_id") != supplied["original_stop"]["container_id"]
        or original.get("image_id") != supplied["original_stop"]["image_id"]
    ):
        raise _fail("original stop archive changed during development lease")
    owner, owner_raw = _read_json(control, CONTROL_OWNER)
    process, process_raw = _read_json(control, CONTROL_PROCESS)
    if owner is None or owner_raw is None or process is None or process_raw is None:
        raise _unavailable("post-build continuation owner/process evidence is unavailable")
    _validate_failed_owner(owner, original.get("terminal_failed_owner"))
    process = _validate_process_receipt(process, "post-build continuation process receipt")
    if hashlib.sha256(owner_raw).hexdigest() != supplied["failed_owner"]["sha256"]:
        raise _fail("post-build continuation Failed owner bytes changed")
    if hashlib.sha256(process_raw).hexdigest() != supplied["current_process"]["sha256"]:
        raise _fail("post-build continuation process bytes changed")

    _sha(runtime_config_sha256, "post-build continuation runtime config")
    if runtime_config_sha256 != supplied["runtime_config"]["sha256"]:
        raise _fail("post-build continuation runtime config changed")
    supplied_certificate = supplied["certificate"]
    if not isinstance(certificate_evidence, Mapping) or set(certificate_evidence) != {
        "historical_certificate_sha256", "historical_owner_marker_sha256",
        "stable_identity", "storage_profile", "restart_verified",
    }:
        raise _fail("post-build continuation certificate evidence is incomplete")
    current_identity = _validate_certificate_stable_identity(certificate_evidence["stable_identity"])
    if (
        current_identity != supplied_certificate["stable_identity"]
        or certificate_evidence["storage_profile"] != supplied_certificate["storage_profile"]
        or type(certificate_evidence["restart_verified"]) is not bool
    ):
        raise _fail("post-build continuation certificate stable identity changed")
    accepted = {} if not accepted_context else _accepted_metadata(accepted_context)
    if accepted != supplied["accepted_run"]:
        raise _fail("post-build continuation accepted catalog changed")
    return supplied
