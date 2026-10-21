"""Validate an unconsumed post-build continuation after capture-only failure.

The caller authenticates the current stopped container with the existing
pre-admission proof and checks historical namespace absence before and under
the recreate lease. These checks preserve the original continuation proof;
they never promote the storage certificate or replay a simulation.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re

from docker_build_control import BuildControlError, canonical
from docker_volume_post_build_generation import (
    CONTINUATION_METADATA_KEY,
    START_BINDING_SCHEMA,
    START_BINDING_ENV,
    START_BINDING_RELATIVE_NAME,
    START_BINDING_SHA_ENV,
    _read_json,
    validate_continuation_metadata,
    validate_post_build_lease_evidence,
    validate_start_binding,
)
from docker_volume_pre_admission_recreate import PROOF_SCHEMA, PUBLICATION_PATHS


ATTEMPT_RE = re.compile(r"^[0-9a-f]{32}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CONSUMED_ROOT = "runtime-control/runtime-services/post-build-continuation"


class PendingCaptureContinuationError(BuildControlError):
    """The retained capture-only continuation is absent, stale, or changed."""


def _fail(message: str) -> PendingCaptureContinuationError:
    return PendingCaptureContinuationError(message)


def _attempt(value: object, label: str) -> str:
    if not isinstance(value, str) or ATTEMPT_RE.fullmatch(value) is None:
        raise _fail(label + " is not a development attempt token")
    return value


def _canonical_control(value: object, raw: bytes, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or raw != canonical(value) + b"\n":
        raise _fail(label + " is not the canonical control record")
    return dict(value)


def _metadata_from_terminal(previous: Mapping[str, object]) -> dict[str, object]:
    """Require the existing metadata to be duplicated identically in inputs."""
    metadata = previous.get(CONTINUATION_METADATA_KEY)
    inputs = previous.get("inputs")
    if not isinstance(inputs, Mapping):
        raise _fail("capture continuation terminal has no operation inputs")
    if metadata is None and CONTINUATION_METADATA_KEY not in inputs:
        raise _fail("capture continuation has no pending post-build metadata")
    if metadata is None or inputs.get(CONTINUATION_METADATA_KEY) != metadata:
        raise _fail("capture continuation metadata differs between terminal and inputs")
    try:
        checked = validate_continuation_metadata(metadata)
    except BuildControlError as error:
        raise _fail("capture continuation metadata is invalid: " + str(error)) from error
    if checked != metadata:
        raise _fail("capture continuation metadata was normalized or changed")
    return checked


def _validate_source_and_config(
    previous: Mapping[str, object],
    document: Mapping[str, object],
    metadata: Mapping[str, object],
    *,
    expected_project: str,
    expected_source_root: str,
    expected_config_sha256: str,
    runtime_config_sha256: str,
) -> None:
    """Bind the carried proof to the failed attempt's recorded inputs.

    ``source_identity`` and ``source_root`` are separate fields in the
    existing continuation schema.  Both must agree with the failed attempt;
    accepting only the metadata copy would allow a caller to supply a valid
    old proof beside a different capture attempt.
    """
    inputs = previous.get("inputs")
    source = metadata.get("source_identity")
    if not isinstance(inputs, Mapping) or not isinstance(source, Mapping):
        raise _fail("capture continuation source inputs are incomplete")
    if (
        metadata.get("compose_project") != expected_project
        or metadata.get("source_root") != expected_source_root
        or inputs.get("source_root") != expected_source_root
        or inputs.get("config_sha256", expected_config_sha256) != expected_config_sha256
    ):
        raise _fail("capture continuation source root or Compose identity differs")
    for input_key, source_key in (
        ("source_project_id", "project_id"),
        ("source_worktree_id", "worktree_id"),
        ("source_checkout_kind", "checkout_kind"),
    ):
        if (
            inputs.get(input_key) is None
            or source.get(source_key) != inputs.get(input_key)
        ):
            raise _fail("capture continuation source identity differs: " + input_key)
    old_config_sha256 = metadata.get("runtime_config", {}).get("sha256")
    if old_config_sha256 != runtime_config_sha256:
        raise _fail("capture continuation runtime configuration differs")
    if inputs.get("previous_config_sha256") != old_config_sha256:
        raise _fail("capture continuation previous config input is not pinned")
    services = document.get("services")
    backend = services.get("backend") if isinstance(services, Mapping) else None
    environment = backend.get("environment") if isinstance(backend, Mapping) else None
    if (
        not isinstance(environment, Mapping)
        or environment.get("FULLMAG_DOCKER_PREVIOUS_CONFIG_SHA256") != old_config_sha256
    ):
        raise _fail("capture continuation Compose previous config binding differs")


def _validate_accepted_lineage(
    previous: Mapping[str, object],
    metadata: Mapping[str, object],
    accepted_context: Mapping[str, object] | None,
) -> None:
    """Keep the full accepted producer and its continuation projection paired."""
    inputs = previous.get("inputs")
    if not isinstance(inputs, Mapping):
        raise _fail("capture continuation has no operation inputs")
    projection = metadata.get("accepted_run")
    producer = accepted_context.get("accepted_reattach_metadata") if accepted_context else None
    retained_producer = previous.get("accepted_reattach")
    input_producer = inputs.get("accepted_reattach")
    if projection:
        if not isinstance(producer, Mapping) or not producer:
            raise _fail("accepted continuation projection has no producer")
        if retained_producer != producer or input_producer != producer:
            raise _fail("accepted producer changed between terminal, inputs, and context")
    else:
        if accepted_context or retained_producer is not None or input_producer is not None:
            raise _fail("capture continuation has an unexpected accepted producer")


def _validate_current_terminal(
    control,
    previous: Mapping[str, object],
    *,
    expected_attempt: str,
    expected_project: str,
) -> dict[str, object]:
    current, current_raw = _read_json(control, "development/current.json")
    attempt_relative = "development/attempts/" + expected_attempt + "/terminal.json"
    attempt_terminal, attempt_raw = _read_json(control, attempt_relative)
    if (
        current is None
        or current_raw is None
        or attempt_terminal is None
        or attempt_raw is None
    ):
        raise _fail("capture continuation has no current development terminal")
    expected_raw = canonical(previous) + b"\n"
    if current_raw != attempt_raw or current_raw != expected_raw:
        raise _fail("current and attempt terminal bytes are not the retained capture terminal")
    current = _canonical_control(current, current_raw, "current development terminal")
    attempt_terminal = _canonical_control(
        attempt_terminal, attempt_raw, "capture attempt development terminal"
    )
    if current != attempt_terminal or current != dict(previous):
        raise _fail("current development terminal is not the retained capture attempt")
    if (
        current.get("schema") != "fullmag.docker-build-operation.v1"
        or current.get("phase") != "development"
        or current.get("state") != "failed-confirmed"
        or current.get("attempt") != expected_attempt
        or current.get("compose_project") != expected_project
        or current.get("control_volume") != getattr(control, "volume", None)
    ):
        raise _fail("current development terminal is not the exact failed capture attempt")
    inputs = current.get("inputs")
    if not isinstance(inputs, Mapping) or inputs.get("attempt", expected_attempt) != expected_attempt:
        raise _fail("current development terminal input attempt differs")
    _metadata_from_terminal(current)
    return current


def _validate_pending_binding(
    control,
    previous: Mapping[str, object],
    document: Mapping[str, object],
    metadata: Mapping[str, object],
    *,
    expected_attempt: str,
) -> dict[str, object]:
    reference = previous.get("post_build_start")
    required_reference = {"schema", "state", "path", "sha256", "continuation_sha256"}
    if not isinstance(reference, Mapping) or set(reference) != required_reference:
        raise _fail("capture continuation has no exact pending start reference")
    expected_root = "development/attempts/" + expected_attempt
    expected_path = "/opt/fullmag/control/" + expected_root + "/" + START_BINDING_RELATIVE_NAME
    metadata_sha = hashlib.sha256(canonical(metadata) + b"\n").hexdigest()
    if (
        reference.get("schema") != START_BINDING_SCHEMA
        or reference.get("state") != "pending"
        or reference.get("path") != expected_path
        or reference.get("continuation_sha256") != metadata_sha
        or not isinstance(reference.get("sha256"), str)
        or SHA256_RE.fullmatch(reference["sha256"]) is None
        or set(reference["sha256"]) == {"0"}
    ):
        raise _fail("capture continuation pending start reference differs")

    binding_relative = expected_root + "/" + START_BINDING_RELATIVE_NAME
    binding, binding_raw = _read_json(control, binding_relative)
    if binding is None or binding_raw is None:
        raise _fail("capture continuation pending start binding is missing")
    binding = _canonical_control(binding, binding_raw, "pending start binding")
    try:
        checked = validate_start_binding(binding)
    except BuildControlError as error:
        raise _fail("capture continuation pending start binding is invalid: " + str(error)) from error
    if (
        checked.get("state") != "pending"
        or checked.get("attempt") != expected_attempt
        or checked.get("continuation") != metadata
        or checked.get("continuation_sha256") != metadata_sha
        or hashlib.sha256(binding_raw).hexdigest() != reference.get("sha256")
    ):
        raise _fail("capture continuation pending start binding changed")

    services = document.get("services")
    backend = services.get("backend") if isinstance(services, Mapping) else None
    environment = backend.get("environment") if isinstance(backend, Mapping) else None
    if not isinstance(environment, Mapping):
        raise _fail("capture continuation Compose backend environment is missing")
    if (
        environment.get(START_BINDING_ENV) != expected_path
        or environment.get(START_BINDING_SHA_ENV) != reference.get("sha256")
    ):
        raise _fail("capture continuation Compose binding does not match its pending record")

    consumed_relative = CONSUMED_ROOT + "/" + expected_attempt + "/consumed.json"
    consumed, _consumed_raw = _read_json(control, consumed_relative, optional=True)
    if consumed is not None:
        raise _fail("capture continuation has already been consumed")
    return checked


def _validate_pre_admission_proof(
    control,
    previous: Mapping[str, object],
    document: Mapping[str, object],
    proof: Mapping[str, object],
    *,
    expected_attempt: str,
    expected_project: str,
    expected_source_root: str,
    expected_config_sha256: str,
    accepted_context: Mapping[str, object] | None,
) -> dict[str, object]:
    """Recheck the saved pre-admission proof and its canonical failure log.

    The existing pre-admission validator authenticates the live backend and
    selector before this helper is called.  This second check keeps the saved
    proof tied to that exact failed capture while the recreate lease is held;
    it does not manufacture a native receipt or turn a provisional
    certificate into a verified one.
    """
    if not isinstance(proof, Mapping):
        raise _fail("capture continuation has no pre-admission recreation proof")
    if (
        proof.get("schema") != PROOF_SCHEMA
        or proof.get("state") != "validated"
        or proof.get("parent_attempt") != expected_attempt
        or proof.get("compose_project") != expected_project
        or proof.get("config_sha256") != expected_config_sha256
        or proof.get("recovery_context") != {}
    ):
        raise _fail("pre-admission recreation proof pins differ")
    proof_certificate = proof.get("certificate")
    if isinstance(proof_certificate, Mapping) and proof_certificate.get("restart_verified") is True:
        raise _fail("pre-admission proof cannot promote a provisional certificate")
    if hashlib.sha256(canonical(document)).hexdigest() != expected_config_sha256:
        raise _fail("pre-admission recreation proof Compose digest differs")

    inputs = previous.get("inputs")
    source = proof.get("source_identity")
    if not isinstance(inputs, Mapping) or not isinstance(source, Mapping):
        raise _fail("pre-admission recreation proof source identity is incomplete")
    if inputs.get("source_root") != expected_source_root:
        raise _fail("pre-admission recreation proof source root differs")
    expected_source = {
        "project_name": expected_project,
        "project_id": inputs.get("source_project_id"),
        "worktree_id": inputs.get("source_worktree_id"),
        "checkout_kind": inputs.get("source_checkout_kind"),
    }
    if (
        expected_source["project_id"] is None
        or expected_source["worktree_id"] is None
        or expected_source["checkout_kind"] is None
        or dict(source) != expected_source
    ):
        raise _fail("pre-admission recreation proof source identity differs")
    expected_accepted = {} if not accepted_context else dict(accepted_context)
    if proof.get("accepted_reattach") != expected_accepted:
        raise _fail("pre-admission recreation proof accepted context differs")

    failure = proof.get("failure")
    if not isinstance(failure, Mapping):
        raise _fail("pre-admission recreation proof has no failure record")
    expected_fields = {
        "phase", "attempt", "terminal_path", "terminal_sha256",
        "failure_log_path", "failure_log_sha256", "backend_started_at",
        "terminal_error_sha256", "published_paths_absent", "backend", "frontend",
    }
    if set(failure) != expected_fields:
        raise _fail("pre-admission recreation failure record fields differ")
    capture_root = "development/attempts/" + expected_attempt
    terminal_path = capture_root + "/terminal.json"
    failure_log_path = capture_root + "/backend-failure-log.json"
    if (
        failure.get("phase") != "development"
        or failure.get("attempt") != expected_attempt
        or failure.get("terminal_path") != terminal_path
        or failure.get("failure_log_path") != failure_log_path
        or failure.get("published_paths_absent") != list(PUBLICATION_PATHS)
    ):
        raise _fail("pre-admission recreation proof is not the current capture attempt")
    backend = failure.get("backend")
    if (
        not isinstance(backend, Mapping)
        or not isinstance(backend.get("container_id"), str)
        or SHA256_RE.fullmatch(backend["container_id"]) is None
        or set(backend["container_id"]) == {"0"}
        or backend.get("container_id") != previous.get(
            "backend_container", backend.get("container_id")
        )
        or backend.get("image_id") != inputs.get("image_id")
        or backend.get("running") is not False
        or backend.get("exit_code") != 2
        or backend.get("oom_killed") is not False
    ):
        raise _fail("pre-admission recreation proof backend is not the current failed capture")

    terminal, terminal_raw = _read_json(control, terminal_path)
    failure_log, failure_log_raw = _read_json(control, failure_log_path)
    if terminal is None or terminal_raw is None or failure_log is None or failure_log_raw is None:
        raise _fail("pre-admission recreation proof records are missing")
    terminal = _canonical_control(terminal, terminal_raw, "pre-admission capture terminal")
    failure_log = _canonical_control(failure_log, failure_log_raw, "pre-admission capture failure log")
    if (
        terminal != dict(previous)
        or hashlib.sha256(terminal_raw).hexdigest() != failure.get("terminal_sha256")
        or hashlib.sha256(failure_log_raw).hexdigest() != failure.get("failure_log_sha256")
    ):
        raise _fail("pre-admission recreation proof record bytes changed")
    log = failure_log.get("log")
    if not isinstance(log, str):
        raise _fail("pre-admission capture failure log has no bounded log text")
    if failure_log.get("started_at") != failure.get("backend_started_at"):
        raise _fail("pre-admission capture failure start pin differs")
    if terminal.get("backend_started_at") != failure.get("backend_started_at"):
        raise _fail("pre-admission capture terminal start pin differs")
    expected_error = "Backend exited during build; logs and volumes retained: " + log[-4000:]
    if (
        terminal.get("error") != expected_error
        or hashlib.sha256(expected_error.encode("utf-8")).hexdigest()
        != failure.get("terminal_error_sha256")
    ):
        raise _fail("pre-admission capture terminal error is not exact")
    required_markers = ("phase=capture state=failed", "current live source capture failed")
    if any(marker not in log for marker in required_markers):
        raise _fail("pre-admission failure log is not an explicit capture-only failure")
    forbidden_markers = (
        "phase=make", "phase=package", "phase=api", "phase=start state=handoff",
        "phase=handoff", "phase=publication", "state=published",
    )
    if any(marker in log for marker in forbidden_markers):
        raise _fail("pre-admission failure log contains Make/package/API/handoff evidence")
    return dict(proof)


def validate_pending_capture_continuation(
    control,
    *,
    previous: Mapping[str, object],
    document: Mapping[str, object],
    expected_attempt: str,
    expected_project: str,
    expected_source_root: str,
    expected_config_sha256: str,
    certificate_evidence: Mapping[str, object],
    accepted_context: Mapping[str, object] | None,
    runtime_config_sha256: str,
    pre_admission_recreate_proof: Mapping[str, object],
) -> dict[str, object]:
    """Validate existing pending evidence before, and again under, a lease.

    The returned object is an in-memory handoff only.  The caller persists the
    already existing ``post_build_generation`` and ``pre_admission_recreate``
    receipt keys, then lets ``start`` call ``prepare_start_binding`` for the
    new development attempt.  This function never calls ``bind_recreate_operation``.
    """
    expected_attempt = _attempt(expected_attempt, "capture continuation attempt")
    if not isinstance(expected_project, str) or not expected_project:
        raise _fail("capture continuation Compose project is invalid")
    if not isinstance(expected_source_root, str) or not expected_source_root:
        raise _fail("capture continuation source root is invalid")
    if not isinstance(expected_config_sha256, str) or SHA256_RE.fullmatch(expected_config_sha256) is None:
        raise _fail("capture continuation Compose digest is invalid")
    _validate_current_terminal(
        control,
        previous,
        expected_attempt=expected_attempt,
        expected_project=expected_project,
    )
    metadata = _metadata_from_terminal(previous)
    _validate_source_and_config(
        previous,
        document,
        metadata,
        expected_project=expected_project,
        expected_source_root=expected_source_root,
        expected_config_sha256=expected_config_sha256,
        runtime_config_sha256=runtime_config_sha256,
    )
    pre_admission = _validate_pre_admission_proof(
        control,
        previous,
        document,
        pre_admission_recreate_proof,
        expected_attempt=expected_attempt,
        expected_project=expected_project,
        expected_source_root=expected_source_root,
        expected_config_sha256=expected_config_sha256,
        accepted_context=accepted_context,
    )
    _validate_accepted_lineage(previous, metadata, accepted_context)
    binding = _validate_pending_binding(
        control,
        previous,
        document,
        metadata,
        expected_attempt=expected_attempt,
    )
    try:
        checked = validate_post_build_lease_evidence(
            control,
            metadata,
            certificate_evidence=certificate_evidence,
            accepted_context=accepted_context,
            runtime_config_sha256=runtime_config_sha256,
        )
    except BuildControlError as error:
        raise _fail("original post-build proof changed: " + str(error)) from error
    if checked != metadata:
        raise _fail("original post-build metadata changed during validation")
    return {
        "metadata": metadata,
        "binding": binding,
        "attempt": expected_attempt,
        "previous_config_sha256": metadata["runtime_config"]["sha256"],
        "pre_admission_recreate_proof": pre_admission,
    }


def validate_carry_recreate_receipt(
    operation_terminal: Mapping[str, object],
    *,
    metadata: Mapping[str, object],
    pre_admission_proof: Mapping[str, object],
    recreation_attempt: str,
    accepted_producer: Mapping[str, object] | None,
) -> None:
    """Cross-check receipt fields after independent proof validation.

    This is deliberately not a proof verifier: every supplied value must have
    already passed ``validate_pending_capture_continuation`` and the existing
    post-build validator.  The function only prevents the new recreation
    receipt from silently replacing those values or rebinding the old
    operation ID.
    """
    recreation_attempt = _attempt(recreation_attempt, "new recreation attempt")
    if operation_terminal.get(CONTINUATION_METADATA_KEY) != dict(metadata):
        raise _fail("recreate receipt changed the carried continuation metadata")
    if operation_terminal.get("pre_admission_recreate") != dict(pre_admission_proof):
        raise _fail("recreate receipt changed the pre-admission proof")
    failure = pre_admission_proof.get("failure", {})
    if not isinstance(failure, Mapping):
        raise _fail("recreate capture failure is not an object")
    old_backend = failure.get("backend", {})
    old_frontend = failure.get("frontend", {})
    if not isinstance(old_backend, Mapping) or not isinstance(old_frontend, Mapping):
        raise _fail("recreate capture container identity is not an object")
    expected_removed = [old_backend.get("container_id"), old_frontend.get("container_id")]
    if operation_terminal.get("removed_containers") != expected_removed:
        raise _fail("recreate receipt removed IDs differ from the capture proof")
    operation_inputs = operation_terminal.get("inputs", {})
    if not isinstance(operation_inputs, Mapping):
        raise _fail("recreate operation inputs are not an object")
    if (
        operation_inputs.get("attempt") != pre_admission_proof.get("parent_attempt")
        or operation_inputs.get("config_sha256") != pre_admission_proof.get("config_sha256")
    ):
        raise _fail("recreate receipt parent/config pins differ from the capture proof")
    old_recreate = metadata.get("recreate_operation")
    if not isinstance(old_recreate, Mapping) or old_recreate.get("operation_id") == recreation_attempt:
        raise _fail("recreate receipt attempted to bind the old continuation proof")
    if accepted_producer is None:
        if "accepted_reattach" in operation_terminal:
            raise _fail("recreate receipt has an unexpected accepted producer")
    elif operation_terminal.get("accepted_reattach") != dict(accepted_producer):
        raise _fail("recreate receipt accepted producer changed")


def _classify_recreate_resume(
    operation_terminal: Mapping[str, object],
    certificate: Mapping[str, object],
    native_recovery_context: Mapping[str, object],
) -> str:
    """Select native versus carry resume without authenticating either proof.

    A native resume may contain only ``post_build_generation``.  Carry resume
    is selected only when the same receipt also contains the existing
    ``pre_admission_recreate`` proof.  The caller still performs the full
    helper validation before starting services.
    """
    if not isinstance(operation_terminal, Mapping):
        raise _fail("recreation resume terminal is not an object")
    if not isinstance(certificate, Mapping):
        raise _fail("recreation resume certificate is not an object")
    metadata = operation_terminal.get(CONTINUATION_METADATA_KEY)
    proof = operation_terminal.get("pre_admission_recreate")
    has_metadata = metadata is not None
    has_proof = proof is not None
    restart_verified = certificate.get("restart_verified")
    if has_proof and not has_metadata:
        raise _fail("capture-only recreation resume has no carried metadata")
    if has_metadata and not has_proof:
        if restart_verified is True:
            return "native"
        raise _fail("capture-only recreation resume has no pre-admission proof")
    if not has_metadata and not has_proof:
        return "native"
    if not isinstance(metadata, Mapping) or not isinstance(proof, Mapping):
        raise _fail("capture-only recreation resume has a malformed continuation receipt")
    if restart_verified is not False:
        raise _fail("capture-only recreation resume requires restart_verified=false")
    if native_recovery_context != {}:
        raise _fail("capture-only recreation resume has unexpected native recovery authority")
    return "carry"
