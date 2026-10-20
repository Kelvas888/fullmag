"""Bounded proof for recreating a stopped, never-admitted DEV build.

This helper never calls Docker, writes control records,
changes a certificate, releases a lease, or removes a service.  The caller
must invoke it after the existing retained-service checks and invoke it again
with a fresh stable inspection while holding the existing recreate operation
lease.  The two returned proofs must compare equal before any stop/rm.

The selector is supplied by the selected Compose group's image-owned control
helper through ``control.read_pinned_resume_evidence``.  Keeping enumeration
there avoids a host-side Docker-volume walk or an uncontrolled Docker command.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any


PROOF_SCHEMA = "fullmag.docker-pre-admission-recreate.v1"
SELECTOR_SCHEMA = "fullmag.docker-pre-admission-resume-selector.v1"
MAX_SELECTOR_ENTRIES = 256
MAX_RECORD_BYTES = 8 * 1024 * 1024
MAX_PROOF_BYTES = 256 * 1024
MAX_TEXT_BYTES = 64 * 1024
MAX_ERROR_BYTES = 8192
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ATTEMPT_RE = re.compile(r"^[0-9a-f]{32}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
PHASE_RE = re.compile(r"^(?:resume|development)$")
SAFE_RELATIVE_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*[a-z0-9]$")
PROVISIONAL_COMMIT = "0" * 40
PROVISIONAL_DIGEST = "0" * 64

# These are the first publication records written by _finish().  Their
# authenticated absence is the legacy substitute for an explicit stage field.
PUBLICATION_PATHS = (
    "handoff-log.json",
    "backend-build-receipt.json",
    "provenance.json",
    "storage-probe-log.json",
)


class PreAdmissionRecreateError(RuntimeError):
    """The legacy pre-publication proof is absent, ambiguous, or changed."""


def _fail(message: str) -> None:
    raise PreAdmissionRecreateError(message)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise PreAdmissionRecreateError("proof value is not canonical JSON") from error


def _bounded_copy(value: object, label: str, maximum: int = MAX_PROOF_BYTES) -> dict[str, object]:
    if not isinstance(value, Mapping):
        _fail(label + " is not an object")
    raw = _canonical(value)
    if len(raw) > maximum:
        _fail(label + " exceeds its size bound")
    try:
        copy = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreAdmissionRecreateError(label + " is not valid JSON") from error
    if not isinstance(copy, dict):
        _fail(label + " is not an object")
    return copy


def _text(value: object, label: str, maximum: int = MAX_TEXT_BYTES) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        _fail(label + " is missing or exceeds its size bound")
    if "\x00" in value:
        _fail(label + " contains NUL")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail(label + " is not a SHA-256 digest")
    return value


def _image(value: object, label: str) -> str:
    if not isinstance(value, str) or IMAGE_RE.fullmatch(value) is None:
        _fail(label + " is not an immutable image ID")
    return value


def _attempt(value: object, label: str) -> str:
    if not isinstance(value, str) or ATTEMPT_RE.fullmatch(value) is None:
        _fail(label + " is not an attempt token")
    return value


def _safe_relative(value: object, label: str) -> str:
    if not isinstance(value, str) or SAFE_RELATIVE_RE.fullmatch(value) is None:
        _fail(label + " is not a safe control-volume path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or any(part in {"", "."} for part in path.parts):
        _fail(label + " escapes the control volume")
    return path.as_posix()


def _bytes(value: object, label: str, maximum: int = MAX_RECORD_BYTES) -> bytes:
    if not isinstance(value, bytes) or not value or len(value) > maximum:
        _fail(label + " is missing or exceeds its size bound")
    return value


def _json_bytes(raw: bytes, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreAdmissionRecreateError(label + " is not valid JSON") from error
    if not isinstance(value, dict):
        _fail(label + " is not an object")
    return value


def _raw_document(
    raw: object,
    value: object,
    label: str,
    *,
    canonical_required: bool = True,
) -> tuple[bytes, dict[str, object]]:
    data = _bytes(raw, label + " raw bytes")
    parsed = _json_bytes(data, label)
    if not isinstance(value, Mapping) or _canonical(value) != _canonical(parsed):
        _fail(label + " parsed value differs from its raw bytes")
    # BuildControl.write publishes canonical JSON followed by one newline.
    # Native host evidence is intentionally written with its adapter's
    # pretty-JSON serializer, so only control-volume records use this check.
    if canonical_required and data != _canonical(parsed) + b"\n":
        _fail(label + " is not the canonical control record")
    return data, parsed


def _project(control: Any, identity: Mapping[str, object]) -> str:
    project = getattr(control, "project", None)
    expected = identity.get("project_name")
    if not isinstance(project, str) or not project or project != expected:
        _fail("control and selected Compose identity differ")
    return project


def _identity(identity: object) -> dict[str, str]:
    if not isinstance(identity, Mapping):
        _fail("selected Compose identity is missing")
    result: dict[str, str] = {}
    for key in ("project_name", "project_id", "worktree_id", "checkout_kind"):
        value = identity.get(key)
        if not isinstance(value, str) or not value or len(value) > 256 or "\x00" in value:
            _fail("selected Compose identity has no valid " + key)
        result[key] = value
    return result


def _host_certificate(
    state: object,
    certificate: object,
    document: Mapping[str, object],
    *,
    expected_image: str,
    expected_project: str,
) -> dict[str, str]:
    """Read certificate and owner with the selected native host adapter.

    The adapter owns no-follow/regular-file checks and profile-specific storage
    identity validation.  This helper only binds both raw files to the parsed
    certificate already validated by the retained launcher.
    """

    if not isinstance(state, (str, os.PathLike)):
        _fail("retained state root is not a path")
    state_path = Path(state)
    if not state_path.is_absolute():
        _fail("retained state root is not absolute")
    if os.name == "nt":
        import windows_folder_host as host
    else:
        import linux_native_host as host
    if not isinstance(certificate, Mapping):
        _fail("host certificate is not an object")
    certificate_copy = _bounded_copy(certificate, "host certificate")
    services = document.get("services")
    backend_service = services.get("backend") if isinstance(services, Mapping) else None
    environment = backend_service.get("environment", {}) if isinstance(backend_service, Mapping) else {}
    if not isinstance(environment, Mapping):
        _fail("retained Compose backend environment is missing")
    if certificate_copy.get("schema") != getattr(host, "HOST_SCHEMA", None):
        _fail("host certificate schema differs from the selected native adapter")
    if certificate_copy.get("storage_profile") != environment.get("FULLMAG_SESSION_STORAGE_PROFILE"):
        _fail("host certificate profile differs from retained Compose")
    if certificate_copy.get("restart_verified") is not False:
        _fail("host certificate is not the unadmitted bootstrap certificate")
    cert_path = state_path / Path(host.HOST_CERT_PATH).name
    owner_path = state_path / host.OWNER_NAME
    try:
        cert_raw = host.read_owned_regular(cert_path, maximum=MAX_RECORD_BYTES)
        owner_raw = host.read_owned_regular(owner_path, maximum=MAX_RECORD_BYTES)
    except (OSError, ValueError, TypeError) as error:
        raise PreAdmissionRecreateError("host certificate/owner cannot be read safely") from error
    cert_bytes, cert_value = _raw_document(
        cert_raw, certificate_copy, "host certificate", canonical_required=False
    )
    owner_bytes, owner_value = _raw_document(
        owner_raw, certificate_copy, "host owner marker", canonical_required=False
    )
    if cert_value != owner_value:
        _fail("host certificate and owner marker differ")
    # The current producer's bootstrap values are deliberately unusable for a
    # runtime admission.  All binary and source identity values must remain
    # provisional; a false restart flag alone is not sufficient.
    if cert_value.get("source_commit") != PROVISIONAL_COMMIT:
        _fail("host certificate already contains a published source commit")
    if cert_value.get("artifact_receipt_sha256") != PROVISIONAL_DIGEST:
        _fail("host certificate already contains a published package receipt")
    if cert_value.get("image_id") != expected_image:
        _fail("host certificate image differs from retained service image")
    binary_hashes = cert_value.get("binary_hashes")
    if (not isinstance(binary_hashes, Mapping) or not binary_hashes
            or any(value != PROVISIONAL_DIGEST for value in binary_hashes.values())):
        _fail("host certificate binary identity is not provisional")
    development = cert_value.get("development_build")
    if not isinstance(development, Mapping):
        _fail("host certificate has no development bootstrap delegation")
    required = {
        "schema", "cargo_profile", "toolchain_image_id", "package_root",
        "provenance_path", "group_identity", "source_identity",
    }
    if set(development) != required:
        _fail("host certificate development delegation fields differ")
    if (development.get("schema") != "fullmag.windows-folder-development-build.v1"
            or development.get("cargo_profile") != "backend-dev"
            or development.get("package_root") != "/opt/fullmag/package"
            or development.get("provenance_path") != "/opt/fullmag/control/backend/runtime-provenance.json"
            or development.get("group_identity") != expected_project):
        _fail("host certificate development delegation is not the bootstrap contract")
    source_identity = development.get("source_identity")
    if (not isinstance(source_identity, Mapping)
            or set(source_identity) != {"commit", "source_digest", "source_snapshot_sha256", "native_source_identity_sha256"}
            or source_identity.get("commit") != PROVISIONAL_COMMIT
            or any(source_identity.get(key) != PROVISIONAL_DIGEST for key in (
                "source_digest", "source_snapshot_sha256", "native_source_identity_sha256"))):
        _fail("host certificate source delegation is not provisional")
    toolchain_image = development.get("toolchain_image_id")
    _image(toolchain_image, "host certificate toolchain image")
    return {
        "certificate_sha256": hashlib.sha256(cert_bytes).hexdigest(),
        "owner_sha256": hashlib.sha256(owner_bytes).hexdigest(),
        "storage_profile": str(cert_value["storage_profile"]),
        "toolchain_image_id": str(toolchain_image),
    }


def _compose_document(document: object, project: str, config_sha256: str) -> dict[str, object]:
    if not isinstance(document, Mapping) or document.get("name") != project:
        _fail("retained Compose document belongs to another group")
    if hashlib.sha256(_canonical(document)).hexdigest() != config_sha256:
        _fail("retained Compose document/config digest differs")
    services = document.get("services")
    if not isinstance(services, Mapping) or not isinstance(services.get("backend"), Mapping):
        _fail("retained Compose document has no backend service")
    return _bounded_copy(document, "retained Compose document", MAX_RECORD_BYTES)


def _parent_inputs(previous: object, config_sha256: str) -> tuple[str, dict[str, object]]:
    if not isinstance(previous, Mapping):
        _fail("parent development terminal is not an object")
    if previous.get("phase") != "development" or previous.get("state") != "failed-confirmed":
        _fail("parent development terminal is not the retained failed attempt")
    attempt = _attempt(previous.get("attempt"), "parent development attempt")
    inputs = previous.get("inputs")
    if not isinstance(inputs, Mapping):
        _fail("parent development terminal inputs are missing")
    if inputs.get("attempt", attempt) != attempt:
        _fail("parent development terminal attempt input differs")
    if ("config_sha256" in inputs and inputs.get("config_sha256") != config_sha256):
        _fail("parent development terminal config input differs")
    return attempt, _bounded_copy(inputs, "parent development inputs", MAX_RECORD_BYTES)


def _service_snapshot(
    actual: object,
    service: str,
    expected_image: str,
    project: str,
    worktree_id: str,
    *,
    backend: bool = False,
) -> dict[str, object]:
    if not isinstance(actual, Mapping) or not isinstance(actual.get(service), Mapping):
        _fail("retained " + service + " inspection is missing")
    observed = actual[service]
    identifier = observed.get("Id")
    image = observed.get("Image")
    config = observed.get("Config")
    labels = config.get("Labels", {}) if isinstance(config, Mapping) else None
    state = observed.get("State")
    if (not isinstance(identifier, str) or re.fullmatch(r"[0-9a-f]{64}", identifier) is None
            or image != expected_image or not isinstance(labels, Mapping)
            or labels.get("com.docker.compose.project") != project
            or labels.get("com.docker.compose.service") != service
            or labels.get("org.fullmag.source.worktree-id") != worktree_id
            or not isinstance(state, Mapping)):
        _fail("retained " + service + " identity differs from the selected group")
    started_at = _text(state.get("StartedAt"), service + " Docker StartedAt", 256)
    result: dict[str, object] = {
        "container_id": identifier,
        "image_id": image,
        "labels": {
            "com.docker.compose.project": labels.get("com.docker.compose.project"),
            "com.docker.compose.service": labels.get("com.docker.compose.service"),
            "org.fullmag.source.worktree-id": labels.get("org.fullmag.source.worktree-id"),
        },
        "started_at": started_at,
    }
    if backend:
        if (state.get("Running") is not False or state.get("ExitCode") != 2
                or state.get("OOMKilled") is not False):
            _fail("retained backend is not the exact non-OOM exit-2 failure")
        result.update({
            "running": False,
            "exit_code": 2,
            "oom_killed": False,
            "finished_at": _text(state.get("FinishedAt"), "backend Docker FinishedAt", 256),
        })
    return result


def _read_selector(control: Any, parent_attempt: str, config_sha256: str, started_at: str, image_id: str) -> dict[str, object]:
    reader = getattr(control, "read_pinned_resume_evidence", None)
    if not callable(reader):
        _fail("selected control group has no bounded pre-admission selector")
    try:
        selected = reader(
            parent_attempt=parent_attempt,
            config_sha256=config_sha256,
            backend_started_at=started_at,
            helper_image=image_id,
        )
    except PreAdmissionRecreateError:
        raise
    except Exception as error:
        raise PreAdmissionRecreateError("bounded pre-admission selector failed") from error
    if not isinstance(selected, Mapping):
        _fail("pre-admission selector result is not an object")
    # Candidate records carry raw bytes, so they cannot be passed through the
    # JSON copier.  Bound and canonicalize the selector metadata separately;
    # each candidate's bytes are checked by _raw_document below.
    metadata = {key: value for key, value in selected.items() if key != "candidates"}
    result = _bounded_copy(metadata, "pre-admission selector metadata")
    candidates = selected.get("candidates")
    result["candidates"] = candidates
    if result.get("schema") != SELECTOR_SCHEMA:
        _fail("pre-admission selector schema differs")
    maximum = result.get("max_entries")
    scanned = result.get("scanned_entries")
    if (isinstance(maximum, bool) or not isinstance(maximum, int)
            or maximum <= 0 or maximum > MAX_SELECTOR_ENTRIES
            or isinstance(scanned, bool) or not isinstance(scanned, int)
            or scanned < 0 or scanned > maximum or not isinstance(candidates, list)):
        _fail("pre-admission selector bounds are invalid")
    if (len(candidates) != 1 or result.get("candidate_count") != 1
            or scanned < len(candidates)):
        _fail("pre-admission selector did not identify one unique candidate")
    return result


def _validate_candidate(
    candidate: object,
    parent_attempt: str,
    config_sha256: str,
    parent_inputs: Mapping[str, object],
    started_at: str,
    actual: object,
    expected_image: str,
    project: str,
    worktree_id: str,
    previous_terminal: object | None = None,
) -> dict[str, object]:
    if not isinstance(candidate, Mapping):
        _fail("pre-admission selector candidate is not an object")
    phase = candidate.get("phase")
    if not isinstance(phase, str) or PHASE_RE.fullmatch(phase) is None:
        _fail("pre-admission selector candidate phase is unsupported")
    token = _attempt(candidate.get("attempt"), "pre-admission selector candidate attempt")
    direct = phase == "development" and token == parent_attempt
    if token == parent_attempt and not direct:
        _fail("pre-admission selector selected the parent attempt itself")
    root = f"{phase}/attempts/{token}"
    terminal_path = candidate.get("terminal_path")
    failure_path = candidate.get("failure_log_path")
    if _safe_relative(terminal_path, "pre-admission terminal path") != root + "/terminal.json":
        _fail("pre-admission terminal path is not the selected attempt")
    if _safe_relative(failure_path, "pre-admission failure-log path") != root + "/backend-failure-log.json":
        _fail("pre-admission failure-log path is not the selected attempt")
    terminal_raw, terminal = _raw_document(
        candidate.get("terminal_raw"), candidate.get("terminal"), "pre-admission terminal"
    )
    failure_raw, failure = _raw_document(
        candidate.get("failure_log_raw"), candidate.get("failure_log"), "pre-admission failure log"
    )
    if terminal.get("phase") != phase or terminal.get("state") != "failed-confirmed":
        _fail("pre-admission terminal is not a failed confirmation")
    if ("config_sha256" in terminal
            and terminal.get("config_sha256") != config_sha256):
        _fail("pre-admission terminal config pin differs")
    inputs = terminal.get("inputs")
    if not isinstance(inputs, Mapping):
        _fail("pre-admission terminal inputs are missing")
    if direct:
        if not isinstance(previous_terminal, Mapping):
            _fail("direct development terminal has no retained parent terminal")
        if _canonical(terminal) != _canonical(previous_terminal):
            _fail("direct development terminal differs from retained parent terminal")
        if (inputs.get("attempt", parent_attempt) != parent_attempt
                or ("config_sha256" in inputs
                    and inputs.get("config_sha256") != config_sha256)):
            _fail("direct development terminal pins differ")
    else:
        if inputs.get("attempt") != parent_attempt:
            _fail("pre-admission terminal is not linked to the parent attempt")
        if inputs.get("config_sha256") != config_sha256:
            _fail("pre-admission terminal config differs")
    for key in (
        "source_root", "source_project_id", "source_worktree_id",
        "source_checkout_kind", "image_id", "toolchain_image_id",
        "gpu_access_requested", "device_access",
    ):
        if key in inputs and key in parent_inputs and inputs.get(key) != parent_inputs.get(key):
            _fail("pre-admission terminal input differs: " + key)
    if terminal.get("compose_project") != project:
        _fail("pre-admission terminal Compose project differs")
    if terminal.get("backend_started_at") != started_at:
        _fail("pre-admission terminal Docker StartedAt differs")
    if terminal.get("daemon_pending") is True:
        _fail("pre-admission terminal still has a daemon-pending operation")
    log = failure.get("log")
    if not isinstance(log, str) or len(log.encode("utf-8")) > MAX_RECORD_BYTES:
        _fail("pre-admission failure log is invalid or oversized")
    terminal_error = _text(terminal.get("error"), "pre-admission terminal error", MAX_ERROR_BYTES)
    if terminal_error != "Backend exited during build; logs and volumes retained: " + log[-4000:]:
        _fail("pre-admission terminal error is not the exact failed-build error")
    if "phase=start state=handoff" in log or "phase=api state=exec" in log:
        _fail("pre-admission failure log contains a publication/API handoff")
    published = candidate.get("published_paths")
    if (not isinstance(published, Mapping)
            or set(published) != set(PUBLICATION_PATHS)
            or any(value is not False for value in published.values())):
        _fail("pre-admission publication paths are not all authenticated absent")
    backend = _service_snapshot(actual, "backend", expected_image, project, worktree_id, backend=True)
    frontend = _service_snapshot(actual, "frontend", expected_image, project, worktree_id)
    return {
        "phase": phase,
        "attempt": token,
        "terminal_path": terminal_path,
        "terminal_sha256": hashlib.sha256(terminal_raw).hexdigest(),
        "failure_log_path": failure_path,
        "failure_log_sha256": hashlib.sha256(failure_raw).hexdigest(),
        "backend_started_at": started_at,
        "terminal_error_sha256": hashlib.sha256(terminal_error.encode("utf-8")).hexdigest(),
        "published_paths_absent": list(PUBLICATION_PATHS),
        "backend": backend,
        "frontend": frontend,
    }


def _accepted_context(value: object) -> dict[str, object]:
    if value is None:
        return {}
    result = _bounded_copy(value, "accepted reattach context")
    if not result:
        return {}
    if set(result) != {"accepted_reattach_environment", "accepted_reattach_metadata"}:
        _fail("accepted reattach context has unexpected fields")
    return result


def validate_pre_admission_recreate(
    control: Any,
    previous: object,
    document: object,
    actual: object,
    state: object,
    certificate: object,
    identity: object,
    config_sha256: str,
    accepted_context: object,
    recovery_context: object,
) -> dict[str, object] | None:
    """Return a deterministic typed proof or ``None`` for admitted storage.

    This validator is intentionally narrow.  It only retro-qualifies a legacy
    stopped development build whose backend exited with the exact build error
    before package publication.  All source/image/GPU pins remain those already
    checked by the existing retained-operation caller.
    """

    if not isinstance(config_sha256, str) or SHA256_RE.fullmatch(config_sha256) is None:
        _fail("recreate config digest is invalid")
    if not isinstance(certificate, Mapping):
        _fail("host certificate is not an object")
    if certificate.get("restart_verified") is True:
        return None
    selected_identity = _identity(identity)
    project = _project(control, selected_identity)
    compose = _compose_document(document, project, config_sha256)
    previous_terminal = _bounded_copy(previous, "parent development terminal", MAX_RECORD_BYTES)
    parent_attempt, inputs = _parent_inputs(previous_terminal, config_sha256)
    image_id = _image(inputs.get("image_id"), "parent development image")
    if inputs.get("source_project_id") != selected_identity["project_id"]:
        _fail("parent development project identity differs")
    if inputs.get("source_worktree_id") != selected_identity["worktree_id"]:
        _fail("parent development worktree identity differs")
    environment = compose["services"]["backend"].get("environment", {})
    if isinstance(environment, Mapping) and environment.get("FULLMAG_STARTUP_ENABLED") == "1":
        _fail("startup activation requires its dedicated recovery path")
    certificate_info = _host_certificate(
        state, certificate, compose, expected_image=image_id, expected_project=project
    )
    expected_toolchain = inputs.get("toolchain_image_id")
    if expected_toolchain is None and isinstance(environment, Mapping):
        expected_toolchain = environment.get("FULLMAG_TOOLCHAIN_IMAGE_ID")
    if certificate_info["toolchain_image_id"] != expected_toolchain:
        _fail("bootstrap certificate toolchain differs from retained Compose/parent inputs")
    if not isinstance(recovery_context, Mapping) or recovery_context:
        _fail("pre-admission recreation cannot replace native recovery authority")
    accepted = _accepted_context(accepted_context)
    backend = _service_snapshot(
        actual, "backend", image_id, project, selected_identity["worktree_id"], backend=True
    )
    started_at = str(backend["started_at"])
    selector = _read_selector(control, parent_attempt, config_sha256, started_at, image_id)
    candidate = _validate_candidate(
        selector["candidates"][0], parent_attempt, config_sha256, inputs, started_at,
        actual, image_id, project, selected_identity["worktree_id"], previous_terminal,
    )
    if candidate["backend"] != backend:
        _fail("pre-admission backend identity changed during validation")
    proof: dict[str, object] = {
        "schema": PROOF_SCHEMA,
        "state": "validated",
        "parent_attempt": parent_attempt,
        "compose_project": project,
        "config_sha256": config_sha256,
        "source_identity": selected_identity,
        "state_root": str(Path(state)),
        "certificate": certificate_info,
        "recovery_context": {},
        "accepted_reattach": accepted,
        "failure": candidate,
    }
    if len(_canonical(proof)) > MAX_PROOF_BYTES:
        _fail("pre-admission proof exceeds its size bound")
    # Re-encode through canonical JSON so a caller cannot accidentally carry a
    # mutable Mapping subclass or an object with non-deterministic iteration.
    return json.loads(_canonical(proof))


def proof_sha256(proof: Mapping[str, object]) -> str:
    """Return the digest suitable for the recreate operation receipt."""

    if not isinstance(proof, Mapping) or proof.get("schema") != PROOF_SCHEMA:
        _fail("pre-admission proof schema is invalid")
    raw = _canonical(proof)
    if len(raw) > MAX_PROOF_BYTES:
        _fail("pre-admission proof exceeds its size bound")
    return hashlib.sha256(raw).hexdigest()
