"""Focused regressions for the host-only failed-owner continuation proof."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docker_volume_post_build_generation as continuation


def _raw(value: object) -> bytes:
    return continuation.canonical(value) + b"\n"


class _Control:
    project = "fullmag-worktree-continuation"
    volume = project + "-control"

    def __init__(self, records: dict[str, bytes]) -> None:
        self.records = records

    def read_raw(self, relative: str, *, optional: bool = False) -> bytes | None:
        try:
            return self.records[relative]
        except KeyError:
            if optional:
                return None
            raise FileNotFoundError(relative)


class PostBuildContinuationTests(unittest.TestCase):
    old_backend = "a" * 64
    current_backend = "b" * 64
    image = "sha256:" + "c" * 64
    old_image = "sha256:" + "d" * 64
    source_root = "/workspace/fullmag"
    attempt = "d" * 32

    def setUp(self) -> None:
        self.config_raw = _raw({"schema_version": "runtime_service_config.v2",
                                "host_execution": {"runtime_generation_sha256": "b" * 64}})
        self.config_sha = hashlib.sha256(self.config_raw).hexdigest()
        self.owner = {
            "schema_version": "runtime_service_owner.v1",
            "protocol": "stdin-v1",
            "state": "failed",
            "owner_token": "owner-token",
            "process_start_token": "process-token",
            "pid": 3217,
            "host": "fullmag-test-host",
            "target_id": "docker-all",
            "control_address": "127.0.0.1:43123",
            "build_commit": "1" * 40,
            "build_snapshot": "2" * 64,
            "compute_pool_id": "compute-pool",
            "preparation_pool_id": "preparation-pool",
            "compute_pool_generation": 7,
            "preparation_pool_generation": 8,
            "acquired_at": "2026-10-20T15:00:00Z",
            "heartbeat_at": "2026-10-20T15:00:01Z",
            "children": [
                {"role": "compute", "pid": 3220, "status": "exited_success"},
                {"role": "preparation", "pid": 3221, "status": "exited_success"},
            ],
        }
        owner_raw = _raw(self.owner)
        old_process = {
            "schema": continuation.PROCESS_SCHEMA,
            "state": "failed_outcome_retained",
            "api_pid": 3209,
            "api_exit_code": -15,
            "error": "API binding did not become ready: old process",
            "runtime_pid": None,
        }
        old_process_raw = _raw(old_process)
        process_sha = hashlib.sha256(old_process_raw).hexdigest()
        terminal_process = {
            "schema": continuation.PROCESS_SCHEMA,
            "state": "shutdown_unknown",
            "api_pid": 3209,
            "api_exit_code": -15,
            "runtime_pid": None,
        }
        terminal_process_raw = _raw(terminal_process)
        terminal_process_sha = hashlib.sha256(terminal_process_raw).hexdigest()
        probe = {
            "schema": "fullmag.docker-native-start-failure-stop-probe.v1",
            "failure_mode": "api-start-failure",
            "process_receipt_sha256": process_sha,
            "process_receipt": old_process,
            "failed_owner_sha256": hashlib.sha256(owner_raw).hexdigest(),
            "failed_owner": self.owner,
            "api_pid_exists": False,
            "owner_pid_exists": False,
            "child_pids_exist": False,
            "native_processes_live": False,
            "startup_enabled": None,
            "legacy_activation_marker_exists": False,
            "active_lease_count": 0,
            "reservation_states": ["released"],
            "lease_states": ["released"],
        }
        self.stop = {
            "schema": continuation.STOP_SCHEMA,
            "state": "stopped-confirmed",
            "container_id": self.old_backend,
            "image_id": self.old_image,
            "failure_kind": "native-start-failure",
            "failure_mode": "api-start-failure",
            "failure_receipt": {"sha256": process_sha, "receipt": old_process},
            "native_failure_probe": probe,
            "terminal_process_receipt": terminal_process,
            "terminal_failed_owner": self.owner,
            "terminal_failed_owner_sha256": hashlib.sha256(owner_raw).hexdigest(),
        }
        current_process = {
            "schema": continuation.PROCESS_SCHEMA,
            "state": "shutdown_unknown",
            "api_pid": 3206,
            "api_exit_code": 101,
            "accepted_store": "/state/runs/docker-all/session-store",
            "bootstrap": {"state": "succeeded"},
            "qualification": "NOT VERIFIED",
            "error": continuation.PROCESS_ERROR,
            "shutdown_error": continuation.PROCESS_SHUTDOWN_ERROR,
        }
        accepted_pins = {
            "schema": "fullmag.docker-accepted-run-reattach-producer.v1",
            "state": "prepared",
            "run_id": "run-held",
            "project_id": "project-held",
            "request_relative": "accepted-run-reattach/" + "1" * 64 + "/request.json",
            "request_sha256": "3" * 64,
            "proof_relative": "accepted-run-reattach/" + "1" * 64 + "/proof.json",
            "proof_sha256": "4" * 64,
            "terminal_process_record_sha256": terminal_process_sha,
            "terminal_owner_record_sha256": hashlib.sha256(owner_raw).hexdigest(),
            "stop_reconcile_proof_sha256": "7" * 64,
            "stop_verification_sha256": hashlib.sha256(_raw(self.stop)).hexdigest(),
            "stop_verification_relative": "verification/stop-failed-" + self.old_backend + ".json",
            "terminal_process_record_relative": "accepted-run-reattach/" + "1" * 64 + "/terminal-process.json",
            "terminal_owner_record_relative": "accepted-run-reattach/" + "1" * 64 + "/terminal-owner.json",
            "source_root": self.source_root,
            "source_relative": "examples/accepted.py",
            "compose_project": _Control.project,
            "control_volume": _Control.volume,
            "logical_session_id": "session-held",
            "session_epoch": 3,
            "development_attempt": self.attempt,
            "activation_attempt": "e" * 32,
            "reconciliation_attempt": "f" * 32,
            "backend_container": self.old_backend,
            "image_id": self.old_image,
            "store_run_relative": "runs/run-held",
            "catalog_revision": 4,
            "task_count": 1,
        }
        accepted_context = {
            "accepted_reattach_metadata": accepted_pins,
            "accepted_reattach_environment": {
                "FULLMAG_ACCEPTED_REATTACH_REQUEST": accepted_pins["request_relative"],
                "FULLMAG_ACCEPTED_REATTACH_REQUEST_SHA256": accepted_pins["request_sha256"],
            },
        }
        self.accepted_context = accepted_context
        self.previous = {
            "attempt": self.attempt,
            "backend_container": self.current_backend,
            "inputs": {"source_root": self.source_root, "image_id": self.image},
        }
        self.document = {"name": _Control.project, "services": {"backend": {}}}
        self.actual = {
            "Id": self.current_backend,
            "Image": self.image,
            "State": {
                "Running": False,
                "Status": "exited",
                "StartedAt": "2026-10-20T15:16:30.069415108Z",
                "FinishedAt": "2026-10-20T15:17:01.069415108Z",
                "ExitCode": 2,
            },
            "Config": {"Labels": {
                "com.docker.compose.project": _Control.project,
                "org.fullmag.source.project-id": "fullmag-project",
                "com.docker.compose.service": "backend",
                "org.fullmag.source.worktree-id": "continuation",
                "org.fullmag.source.checkout-kind": "worktree",
            }},
        }
        self.source = {
            "source_root": self.source_root,
            "project_id": "fullmag-project",
            "worktree_id": "continuation",
            "checkout_kind": "worktree",
        }
        self.certificate = {
            "historical_certificate_sha256": "9" * 64,
            "historical_owner_marker_sha256": "a" * 64,
            "stable_identity": {
                "schema": "fullmag.linux-native-host.v1",
                "storage_profile": "linux-native-v1",
                "role": "session",
                "owner_scope": "docker-linux",
                "owner_token": "1" * 32,
                "engine_id": "sha256:" + "e" * 64,
                "host_root": "/var/lib/fullmag-runtime",
                "host_filesystem": "ext4",
                "host_platform": "linux",
                "host_device": 2049,
                "host_root_no_reparse": True,
                "host_inode": 314159,
            },
            "storage_profile": "linux-native-v1",
            "restart_verified": True,
        }
        self.records = {
            "verification/stop-failed-" + self.old_backend + ".json": _raw(self.stop),
            continuation.CONTROL_OWNER: owner_raw,
            continuation.CONTROL_PROCESS: _raw(current_process),
            continuation.CONFIG_RELATIVE: self.config_raw,
        }
        self.control = _Control(self.records)

    def _build(self) -> dict[str, object]:
        return continuation.build_failed_owner_continuation(
            self.control,
            operation_id=self.attempt,
            previous=self.previous,
            document=self.document,
            actual_backend=self.actual,
            source_identity=self.source,
            certificate_evidence=self.certificate,
            accepted_context=self.accepted_context,
            runtime_config_sha256=self.config_sha,
        )

    def _recreation_proof(self) -> dict[str, object]:
        operation_id = "e" * 32
        frontend = "c" * 64
        absence = {}
        for service, identifier in (("backend", self.current_backend), ("frontend", frontend)):
            inspect_output = ("Error: No such object: " + identifier + "\n").encode()
            absence[service] = {
                "container_id": identifier,
                "inspect_returncode": 1,
                "inspect_output_sha256": hashlib.sha256(inspect_output).hexdigest(),
                "ps_returncode": 0,
                "ps_output_sha256": hashlib.sha256(b"").hexdigest(),
            }
        terminal = {
            "schema": "fullmag.docker-build-operation.v1",
            "phase": "recreate-services",
            "state": "succeeded",
            "attempt": operation_id,
            "removed_containers": [self.current_backend, frontend],
        }
        retained = {
            "backend": self.actual,
            "frontend": {
                "Id": frontend,
                "Image": self.image,
                "State": {"Running": False},
            },
        }
        prior_terminal = {"schema": "fullmag.docker-build-operation.v1", "state": "failed-confirmed"}
        prior_compose = self.document
        self.recreation_records = {
            "recreate-services/attempts/" + operation_id + "/terminal.json": _raw(terminal),
            "recreate-services/attempts/" + operation_id + "/retained-containers.json": _raw(retained),
            "development/attempts/" + self.attempt + "/terminal.json": _raw(prior_terminal),
            "development/attempts/" + self.attempt + "/compose.json": _raw(prior_compose),
        }
        return {
            "recreation_operation_id": operation_id,
            "recreation_terminal_sha256": hashlib.sha256(_raw(terminal)).hexdigest(),
            "retained_snapshot_sha256": hashlib.sha256(_raw(retained)).hexdigest(),
            "prior_terminal_sha256": hashlib.sha256(_raw(prior_terminal)).hexdigest(),
            "prior_compose_sha256": hashlib.sha256(_raw(prior_compose)).hexdigest(),
            "container_id": self.current_backend,
            "frontend_container": frontend,
            "image_id": self.image,
            "absence": absence,
        }

    def _bound(self) -> dict[str, object]:
        return continuation.bind_recreate_operation(self._build(), self._recreation_proof())

    def test_true_published_case_binds_old_stop_to_new_stopped_namespace(self):
        metadata = self._build()
        self.assertEqual(metadata["schema"], continuation.SCHEMA)
        self.assertEqual(metadata["original_stop"]["container_id"], self.old_backend)
        self.assertEqual(metadata["current_namespace"]["container_id"], self.current_backend)
        self.assertEqual(metadata["runtime_config"]["sha256"], self.config_sha)
        self.assertEqual(metadata["current_process"]["api_exit_code"], 101)

    def test_true_published_after_ready_archive_keeps_ready_identity_separate(self):
        control, context = self._after_ready_case()
        metadata = continuation.build_failed_owner_continuation(
            control,
            operation_id=self.attempt,
            previous=self.previous,
            document=self.document,
            actual_backend=self.actual,
            source_identity=self.source,
            certificate_evidence=self.certificate,
            accepted_context=context,
            runtime_config_sha256=self.config_sha,
        )
        self.assertEqual(metadata["original_stop"]["container_id"], self.old_backend)
        self.assertEqual(metadata["current_namespace"]["container_id"], self.current_backend)
        self.assertEqual(metadata["failed_owner"]["identity"]["pid"], self.owner["pid"])

    def test_direct_stop_without_accepted_run_uses_cgroup_and_canonical_terminal_pin(self):
        direct_stop = deepcopy(self.stop)
        direct_stop["container_id"] = self.current_backend
        direct_stop["image_id"] = self.image
        records = dict(self.records)
        records.pop("verification/stop-failed-" + self.old_backend + ".json")
        direct_relative = "verification/stop-failed-" + self.current_backend + ".json"
        records[direct_relative] = _raw(direct_stop)
        previous = deepcopy(self.previous)
        previous.pop("backend_container")
        previous["worker_cgroup"] = {
            "schema": "fullmag.worker-cgroup-ready.v1",
            "state": "ready",
            "compose_project": _Control.project,
            "image_id": self.image,
            "container_id": self.current_backend,
        }
        metadata = continuation.build_failed_owner_continuation(
            _Control(records),
            operation_id=self.attempt,
            previous=previous,
            document=self.document,
            actual_backend=self.actual,
            source_identity=self.source,
            certificate_evidence=self.certificate,
            accepted_context=None,
            runtime_config_sha256=self.config_sha,
        )
        self.assertEqual(metadata["accepted_run"], {})
        self.assertEqual(metadata["original_stop"]["relative"], direct_relative)
        self.assertEqual(
            metadata["original_stop"]["terminal_process_sha256"],
            hashlib.sha256(_raw(direct_stop["terminal_process_receipt"])).hexdigest(),
        )

    def test_direct_stop_rejects_unpinned_worker_cgroup_fallback(self):
        previous = deepcopy(self.previous)
        previous.pop("backend_container")
        previous["worker_cgroup"] = {
            "schema": "fullmag.worker-cgroup-ready.v1",
            "state": "ready",
            "compose_project": _Control.project,
            "image_id": self.old_image,
            "container_id": self.current_backend,
        }
        with self.assertRaises(continuation.PostBuildGenerationUnavailable):
            continuation.build_failed_owner_continuation(
                self.control,
                operation_id=self.attempt,
                previous=previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=None,
                runtime_config_sha256=self.config_sha,
            )

    def test_start_binding_is_bound_to_active_development_attempt(self):
        metadata = self._bound()
        operation = {
            "root": "development/attempts/" + self.attempt,
            "receipt": {"phase": "development", "attempt": self.attempt},
        }
        binding = continuation.prepare_start_binding(metadata, operation)
        checked = continuation.validate_start_binding(binding["record"])
        self.assertEqual(checked["state"], "pending")
        self.assertEqual(binding["environment"][continuation.START_BINDING_ENV], binding["path"])
        self.assertEqual(
            binding["environment"][continuation.START_BINDING_SHA_ENV], binding["sha256"]
        )

    def test_start_binding_rejects_another_attempt(self):
        metadata = self._bound()
        operation = {
            "root": "development/attempts/" + self.attempt,
            "receipt": {"phase": "development", "attempt": self.attempt},
        }
        binding = continuation.prepare_start_binding(metadata, operation)["record"]
        changed = deepcopy(binding)
        changed["active_token"] = "e" * 32
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.validate_start_binding(changed)

    def test_current_namespace_identity_drift_rejects_before_stop_rm(self):
        changed = deepcopy(self.actual)
        changed["Id"] = "e" * 64
        with self.assertRaises(continuation.PostBuildGenerationError):
            self._build_with(changed)

    def test_continuation_operation_binds_to_previous_attempt(self):
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.build_failed_owner_continuation(
                self.control,
                operation_id="e" * 32,
                previous=self.previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=self.accepted_context,
                runtime_config_sha256=self.config_sha,
            )

    def test_resume_rejects_metadata_operation_from_another_attempt(self):
        metadata = self._bound()
        metadata["operation_id"] = "e" * 32
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.validate_resume_continuation(
                self.control,
                metadata,
                operation_id="e" * 32,
                expected_project=_Control.project,
                expected_source_root=self.source_root,
                previous=self.previous,
                document=self.document,
                accepted_context=self.accepted_context,
            )

    def test_recreate_operation_binds_current_namespace_and_distinct_services(self):
        metadata = self._bound()
        changed = deepcopy(metadata)
        changed["recreate_operation"]["image_id"] = self.old_image
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.validate_continuation_metadata(changed)
        changed = deepcopy(metadata)
        changed["recreate_operation"]["frontend_container"] = self.current_backend
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.validate_continuation_metadata(changed)

    def test_current_api_receipt_type_or_error_drift_rejects(self):
        changed = deepcopy(self.records)
        receipt = json.loads(changed[continuation.CONTROL_PROCESS])
        receipt["api_exit_code"] = 101.0
        changed[continuation.CONTROL_PROCESS] = _raw(receipt)
        control = _Control(changed)
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.build_failed_owner_continuation(
                control,
                operation_id=self.attempt,
                previous=self.previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=self.accepted_context,
                runtime_config_sha256=self.config_sha,
            )

    def test_missing_owner_or_process_is_unavailable(self):
        for missing in (continuation.CONTROL_OWNER, continuation.CONTROL_PROCESS):
            control = _Control({key: value for key, value in self.records.items() if key != missing})
            with self.subTest(missing=missing), self.assertRaises(
                continuation.PostBuildGenerationUnavailable
            ):
                continuation.build_failed_owner_continuation(
                    control,
                    operation_id=self.attempt,
                    previous=self.previous,
                    document=self.document,
                    actual_backend=self.actual,
                    source_identity=self.source,
                    certificate_evidence=self.certificate,
                    accepted_context=self.accepted_context,
                    runtime_config_sha256=self.config_sha,
                )

    def test_original_stop_archive_tamper_rejects(self):
        changed = deepcopy(self.records)
        archive = json.loads(changed["verification/stop-failed-" + self.old_backend + ".json"])
        archive["exit_code"] = 99
        changed["verification/stop-failed-" + self.old_backend + ".json"] = _raw(archive)
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.build_failed_owner_continuation(
                _Control(changed),
                operation_id=self.attempt,
                previous=self.previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=self.accepted_context,
                runtime_config_sha256=self.config_sha,
            )

    def test_native_probe_drift_rejects_before_stop_rm(self):
        changed = deepcopy(self.stop)
        changed["native_failure_probe"]["active_lease_count"] = 1
        records = dict(self.records)
        records["verification/stop-failed-" + self.old_backend + ".json"] = _raw(changed)
        context = deepcopy(self.accepted_context)
        context["accepted_reattach_metadata"]["stop_verification_sha256"] = hashlib.sha256(
            records["verification/stop-failed-" + self.old_backend + ".json"]
        ).hexdigest()
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.build_failed_owner_continuation(
                _Control(records),
                operation_id=self.attempt,
                previous=self.previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=context,
                runtime_config_sha256=self.config_sha,
            )

    def test_native_start_failure_terminal_owner_transition_rejects(self):
        changed = deepcopy(self.stop)
        changed["terminal_process_receipt"]["service_owner"] = self.owner
        records = dict(self.records)
        records["verification/stop-failed-" + self.old_backend + ".json"] = _raw(changed)
        context = deepcopy(self.accepted_context)
        context["accepted_reattach_metadata"]["stop_verification_sha256"] = hashlib.sha256(
            records["verification/stop-failed-" + self.old_backend + ".json"]
        ).hexdigest()
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.build_failed_owner_continuation(
                _Control(records),
                operation_id=self.attempt,
                previous=self.previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=context,
                runtime_config_sha256=self.config_sha,
            )

    def test_accepted_stop_pin_drift_rejects(self):
        context = deepcopy(self.accepted_context)
        context["accepted_reattach_metadata"]["stop_verification_sha256"] = "e" * 64
        with self.assertRaises(continuation.PostBuildGenerationError):
            self._build_with_context(context)

    def test_duplicate_json_member_rejects(self):
        changed = dict(self.records)
        changed[continuation.CONTROL_PROCESS] = b'{"schema":"x","schema":"y"}'
        with self.assertRaises(continuation.PostBuildGenerationError):
            self._build_with_control(_Control(changed))

    def test_image_or_runtime_config_pin_drift_rejects(self):
        changed = deepcopy(self.previous)
        changed["inputs"]["image_id"] = "sha256:" + "d" * 64
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.build_failed_owner_continuation(
                self.control,
                operation_id=self.attempt,
                previous=changed,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=self.accepted_context,
                runtime_config_sha256=self.config_sha,
            )
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.build_failed_owner_continuation(
                self.control,
                operation_id=self.attempt,
                previous=self.previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=self.accepted_context,
                runtime_config_sha256="e" * 64,
            )

    def test_certificate_must_remain_restart_verified(self):
        changed = deepcopy(self.certificate)
        changed["restart_verified"] = False
        with self.assertRaises(continuation.PostBuildGenerationError):
            self._build_with_certificate(changed)

    def test_rotated_certificate_keeps_historical_hashes_and_stable_identity(self):
        metadata = self._build()
        rotated = deepcopy(self.certificate)
        rotated["historical_certificate_sha256"] = "b" * 64
        rotated["historical_owner_marker_sha256"] = "c" * 64
        checked = continuation.validate_failed_owner_continuation(
            self.control,
            metadata,
            operation_id=self.attempt,
            expected_project=_Control.project,
            expected_source_root=self.source_root,
            previous=self.previous,
            document=self.document,
            actual_backend=self.actual,
            source_identity=self.source,
            certificate_evidence=rotated,
            accepted_context=self.accepted_context,
            runtime_config_sha256=self.config_sha,
        )
        self.assertEqual(checked, metadata)

    def test_certificate_stable_identity_drift_rejects_after_rotation(self):
        metadata = self._build()
        rotated = deepcopy(self.certificate)
        rotated["stable_identity"]["engine_id"] = "sha256:" + "f" * 64
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.validate_failed_owner_continuation(
                self.control,
                metadata,
                operation_id=self.attempt,
                expected_project=_Control.project,
                expected_source_root=self.source_root,
                previous=self.previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=rotated,
                accepted_context=self.accepted_context,
                runtime_config_sha256=self.config_sha,
            )

    def test_new_lease_revalidates_completed_recreation_without_live_namespace(self):
        metadata = self._bound()
        control = _Control({**self.records, **self.recreation_records})
        checked = continuation.validate_post_build_lease_evidence(
            control,
            metadata,
            certificate_evidence=self.certificate,
            accepted_context=self.accepted_context,
            runtime_config_sha256=self.config_sha,
        )
        self.assertEqual(checked, metadata)

    def test_new_lease_rejects_completed_recreation_terminal_drift(self):
        metadata = self._bound()
        records = {**self.records, **self.recreation_records}
        terminal_path = metadata["recreate_operation"]["terminal_relative"]
        terminal = json.loads(records[terminal_path])
        terminal["removed_containers"] = [self.current_backend, "d" * 64]
        records[terminal_path] = _raw(terminal)
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.validate_post_build_lease_evidence(
                _Control(records),
                metadata,
                certificate_evidence=self.certificate,
                accepted_context=self.accepted_context,
                runtime_config_sha256=self.config_sha,
            )

    def test_current_process_error_bytes_drift_rejects(self):
        changed = deepcopy(self.records)
        receipt = json.loads(changed[continuation.CONTROL_PROCESS])
        receipt["error"] = continuation.PROCESS_ERROR + " changed"
        changed[continuation.CONTROL_PROCESS] = _raw(receipt)
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.build_failed_owner_continuation(
                _Control(changed),
                operation_id=self.attempt,
                previous=self.previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=self.accepted_context,
                runtime_config_sha256=self.config_sha,
            )

    def test_missing_original_stop_proof_is_unavailable(self):
        control = _Control({key: value for key, value in self.records.items() if "stop-failed" not in key})
        with self.assertRaises(continuation.PostBuildGenerationUnavailable):
            continuation.build_failed_owner_continuation(
                control,
                operation_id=self.attempt,
                previous=self.previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=self.accepted_context,
                runtime_config_sha256=self.config_sha,
            )

    def test_resume_rejects_failed_owner_byte_drift(self):
        metadata = self._bound()
        changed_owner = deepcopy(self.owner)
        changed_owner["pid"] += 1
        control = _Control({
            **self.records,
            continuation.CONTROL_OWNER: _raw(changed_owner),
        })
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.validate_resume_continuation(
                control,
                metadata,
                operation_id=self.attempt,
                expected_project=_Control.project,
                expected_source_root=self.source_root,
                previous=self.previous,
                document=self.document,
                accepted_context=self.accepted_context,
            )

    def test_same_owner_value_with_different_raw_bytes_rejects(self):
        changed = dict(self.records)
        changed[continuation.CONTROL_OWNER] = (
            json.dumps(self.owner, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        )
        with self.assertRaises(continuation.PostBuildGenerationError):
            self._build_with_control(_Control(changed))

    def test_current_process_raw_drift_rejects_under_recreate_lease(self):
        metadata = self._build()
        changed = dict(self.records)
        process = json.loads(changed[continuation.CONTROL_PROCESS])
        changed[continuation.CONTROL_PROCESS] = (
            json.dumps(process, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        )
        with self.assertRaises(continuation.PostBuildGenerationError):
            continuation.validate_failed_owner_continuation(
                _Control(changed),
                metadata,
                operation_id=self.attempt,
                expected_project=_Control.project,
                expected_source_root=self.source_root,
                previous=self.previous,
                document=self.document,
                actual_backend=self.actual,
                source_identity=self.source,
                certificate_evidence=self.certificate,
                accepted_context=self.accepted_context,
                runtime_config_sha256=self.config_sha,
            )

    def test_consumed_binding_remains_shape_valid_but_is_not_pending(self):
        metadata = self._bound()
        operation = {
            "root": "development/attempts/" + self.attempt,
            "receipt": {"phase": "development", "attempt": self.attempt},
        }
        binding = continuation.prepare_start_binding(metadata, operation)["record"]
        binding["state"] = "consumed"
        self.assertEqual(continuation.validate_start_binding(binding)["state"], "consumed")

    def _build_with(self, actual_backend: dict[str, object]) -> dict[str, object]:
        return continuation.build_failed_owner_continuation(
            self.control,
            operation_id=self.attempt,
            previous=self.previous,
            document=self.document,
            actual_backend=actual_backend,
            source_identity=self.source,
            certificate_evidence=self.certificate,
            accepted_context=self.accepted_context,
            runtime_config_sha256=self.config_sha,
        )

    def _build_with_certificate(self, certificate: dict[str, object]) -> dict[str, object]:
        return continuation.build_failed_owner_continuation(
            self.control,
            operation_id=self.attempt,
            previous=self.previous,
            document=self.document,
            actual_backend=self.actual,
            source_identity=self.source,
            certificate_evidence=certificate,
            accepted_context=self.accepted_context,
            runtime_config_sha256=self.config_sha,
        )

    def _build_with_control(self, control: _Control) -> dict[str, object]:
        return continuation.build_failed_owner_continuation(
            control,
            operation_id=self.attempt,
            previous=self.previous,
            document=self.document,
            actual_backend=self.actual,
            source_identity=self.source,
            certificate_evidence=self.certificate,
            accepted_context=self.accepted_context,
            runtime_config_sha256=self.config_sha,
        )

    def _build_with_context(self, context: dict[str, object]) -> dict[str, object]:
        return continuation.build_failed_owner_continuation(
            self.control,
            operation_id=self.attempt,
            previous=self.previous,
            document=self.document,
            actual_backend=self.actual,
            source_identity=self.source,
            certificate_evidence=self.certificate,
            accepted_context=context,
            runtime_config_sha256=self.config_sha,
        )

    def _after_ready_case(self) -> tuple[_Control, dict[str, object]]:
        """Model the real successor namespace after a retained READY owner failed."""
        ready_owner = deepcopy(self.owner)
        ready_owner["state"] = "ready"
        for child in ready_owner["children"]:
            child["status"] = "running"
        stop = deepcopy(self.stop)
        stop["failure_kind"] = "native-after-ready-failure"
        stop.pop("failure_mode", None)
        failure_receipt = stop["failure_receipt"]["receipt"]
        failure_receipt["service_owner"] = ready_owner
        failure_raw = _raw(failure_receipt)
        failure_sha = hashlib.sha256(failure_raw).hexdigest()
        stop["failure_receipt"]["sha256"] = failure_sha
        probe = stop["native_failure_probe"]
        probe["schema"] = "fullmag.docker-native-after-ready-failure-stop-probe.v1"
        probe.pop("failure_mode", None)
        probe["process_receipt_sha256"] = failure_sha
        probe["process_receipt"] = failure_receipt
        terminal = stop["terminal_process_receipt"]
        terminal["service_owner"] = ready_owner
        stop["retained_ready_owner"] = ready_owner
        stop["terminal_retained_ready_owner"] = ready_owner
        stop["retained_ready_owner_sha256"] = hashlib.sha256(
            continuation.canonical(ready_owner)
        ).hexdigest()
        terminal_sha = hashlib.sha256(_raw(terminal)).hexdigest()
        stop_sha = hashlib.sha256(_raw(stop)).hexdigest()
        context = deepcopy(self.accepted_context)
        pins = context["accepted_reattach_metadata"]
        pins["terminal_process_record_sha256"] = terminal_sha
        pins["stop_verification_sha256"] = stop_sha
        return _Control({
            "verification/stop-failed-" + self.old_backend + ".json": _raw(stop),
            continuation.CONTROL_OWNER: self.records[continuation.CONTROL_OWNER],
            continuation.CONTROL_PROCESS: self.records[continuation.CONTROL_PROCESS],
            continuation.CONFIG_RELATIVE: self.config_raw,
        }), context


if __name__ == "__main__":
    unittest.main()
