"""Interpreted pending-continuation regressions; no native compilation."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import unittest


SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))


import docker_volume_pending_continuation as pending  # noqa: E402
import docker_volume_post_build_generation as continuation  # noqa: E402
import docker_volume_pre_admission_recreate as pre_admission  # noqa: E402
import test_docker_volume_post_build_generation as generation_fixtures  # noqa: E402


def _raw(value: object) -> bytes:
    return continuation.canonical(value) + b"\n"


class PendingCaptureContinuationTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = generation_fixtures.PostBuildContinuationTests(
            "test_new_lease_revalidates_completed_recreation_without_live_namespace"
        )
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.fixture = fixture
        self.old_metadata_attempt = fixture.attempt
        self.capture_attempt = "b" * 32
        self.metadata = fixture._bound()
        self.old_recreation_attempt = self.metadata["recreate_operation"]["operation_id"]
        self.producer = fixture.accepted_context["accepted_reattach_metadata"]

        # The old recreation terminal is retained exactly under the old
        # operation/attempt.  The new failed capture attempt has its own root;
        # it must never overwrite the old terminal used by the metadata proof.
        self.fixture.control.records.update(self.fixture.recreation_records)
        self.previous = deepcopy(fixture.previous)
        self.previous.update(
            {
                "schema": "fullmag.docker-build-operation.v1",
                "phase": "development",
                "state": "failed-confirmed",
                "attempt": self.capture_attempt,
                "compose_project": fixture.control.project,
                "control_volume": fixture.control.volume,
                "state_root": "/state/docker-volume-dev",
                "backend_started_at": fixture.actual["State"]["StartedAt"],
                "finished_at": fixture.actual["State"]["FinishedAt"],
                "post_build_generation": deepcopy(self.metadata),
                "accepted_reattach": deepcopy(self.producer),
            }
        )
        self.previous.pop("backend_container", None)
        self.previous["inputs"].update(
            {
                "source_root": fixture.source_root,
                "source_project_id": fixture.source["project_id"],
                "source_worktree_id": fixture.source["worktree_id"],
                "source_checkout_kind": fixture.source["checkout_kind"],
                "image_id": fixture.image,
                "previous_config_sha256": fixture.config_sha,
                "post_build_generation": deepcopy(self.metadata),
                "accepted_reattach": deepcopy(self.producer),
            }
        )

        binding = continuation.prepare_start_binding(
            self.metadata,
            {
                "root": "development/attempts/" + self.capture_attempt,
                "receipt": {"phase": "development", "attempt": self.capture_attempt},
            },
        )
        self.previous["post_build_start"] = deepcopy(binding["receipt"])
        self.document = deepcopy(fixture.document)
        self.document["services"]["backend"]["environment"] = {
            **binding["environment"],
            "FULLMAG_DOCKER_PREVIOUS_CONFIG_SHA256": fixture.config_sha,
        }
        compose_sha = hashlib.sha256(continuation.canonical(self.document)).hexdigest()

        failure_log = (
            "phase=capture state=failed\n"
            "current live source capture failed\n"
            "capture timed out while collecting the mounted source\n"
        )
        self.failure_log = {"started_at": fixture.actual["State"]["StartedAt"], "log": failure_log}
        capture_root = "development/attempts/" + self.capture_attempt
        failure_path = capture_root + "/backend-failure-log.json"
        terminal_path = capture_root + "/terminal.json"
        self.previous["error"] = (
            "Backend exited during build; logs and volumes retained: " + failure_log[-4000:]
        )

        # Publish only fixture records in memory.  The old development terminal
        # in fixture.recreation_records remains untouched.
        fixture.control.records[binding["relative"]] = _raw(binding["record"])
        fixture.control.records[failure_path] = _raw(self.failure_log)
        fixture.control.records[terminal_path] = _raw(self.previous)
        fixture.control.records["development/current.json"] = _raw(self.previous)
        self.binding = binding
        self.compose_sha = compose_sha
        self.pre_admission_proof = self._make_pre_admission_proof(
            terminal_path=terminal_path,
            failure_path=failure_path,
        )

    def _make_pre_admission_proof(
        self, *, terminal_path: str, failure_path: str
    ) -> dict[str, object]:
        terminal_raw = _raw(self.previous)
        failure_raw = _raw(self.failure_log)
        return {
            "schema": pre_admission.PROOF_SCHEMA,
            "state": "validated",
            "parent_attempt": self.capture_attempt,
            "compose_project": self.fixture.control.project,
            "config_sha256": self.compose_sha,
            "source_identity": {
                "project_name": self.fixture.control.project,
                "project_id": self.fixture.source["project_id"],
                "worktree_id": self.fixture.source["worktree_id"],
                "checkout_kind": self.fixture.source["checkout_kind"],
            },
            "state_root": "/state/docker-volume-dev",
            # This is the existing pre-admission proof certificate shape.  The
            # provisional ``restart_verified=False`` value belongs to the
            # retained resume certificate supplied by the caller; it is not a
            # new field in this proof payload.
            "certificate": {
                "certificate_sha256": "1" * 64,
                "owner_sha256": "2" * 64,
                "storage_profile": "linux-native-v1",
                "toolchain_image_id": "sha256:" + "f" * 64,
            },
            "recovery_context": {},
            "accepted_reattach": deepcopy(self.fixture.accepted_context),
            "failure": {
                "phase": "development",
                "attempt": self.capture_attempt,
                "terminal_path": terminal_path,
                "terminal_sha256": hashlib.sha256(terminal_raw).hexdigest(),
                "failure_log_path": failure_path,
                "failure_log_sha256": hashlib.sha256(failure_raw).hexdigest(),
                "backend_started_at": self.fixture.actual["State"]["StartedAt"],
                "terminal_error_sha256": hashlib.sha256(
                    self.previous["error"].encode("utf-8")
                ).hexdigest(),
                "published_paths_absent": list(pre_admission.PUBLICATION_PATHS),
                "backend": {
                    "container_id": self.fixture.current_backend,
                    "image_id": self.fixture.image,
                    "labels": {
                        "com.docker.compose.project": self.fixture.control.project,
                        "com.docker.compose.service": "backend",
                        "org.fullmag.source.worktree-id": self.fixture.source["worktree_id"],
                    },
                    "started_at": self.fixture.actual["State"]["StartedAt"],
                    "running": False,
                    "exit_code": 2,
                    "oom_killed": False,
                    "finished_at": self.fixture.actual["State"]["FinishedAt"],
                },
                "frontend": {
                    "container_id": "c" * 64,
                    "image_id": self.fixture.image,
                    "labels": {
                        "com.docker.compose.project": self.fixture.control.project,
                        "com.docker.compose.service": "frontend",
                        "org.fullmag.source.worktree-id": self.fixture.source["worktree_id"],
                    },
                    "started_at": self.fixture.actual["State"]["StartedAt"],
                },
            },
        }

    def _validate(self):
        return pending.validate_pending_capture_continuation(
            self.fixture.control,
            previous=self.previous,
            document=self.document,
            expected_attempt=self.capture_attempt,
            expected_project=self.fixture.control.project,
            expected_source_root=self.fixture.source_root,
            expected_config_sha256=self.compose_sha,
            certificate_evidence=self.fixture.certificate,
            accepted_context=self.fixture.accepted_context,
            runtime_config_sha256=self.fixture.config_sha,
            pre_admission_recreate_proof=self.pre_admission_proof,
        )

    def _repin_terminal(self, terminal: dict[str, object]) -> None:
        """Keep raw-byte and saved-proof pins aligned for a targeted check."""
        self.previous = terminal
        raw = _raw(terminal)
        relative = "development/attempts/" + self.capture_attempt + "/terminal.json"
        self.fixture.control.records["development/current.json"] = raw
        self.fixture.control.records[relative] = raw
        self.pre_admission_proof["failure"]["terminal_sha256"] = hashlib.sha256(
            raw
        ).hexdigest()
        self.pre_admission_proof["failure"]["terminal_error_sha256"] = hashlib.sha256(
            terminal["error"].encode("utf-8")
        ).hexdigest()

    def _repin_compose_digest(self) -> None:
        self.compose_sha = hashlib.sha256(
            continuation.canonical(self.document)
        ).hexdigest()
        self.pre_admission_proof["config_sha256"] = self.compose_sha
        self._repin_terminal(self.previous)

    def test_exact_capture_pending_state_passes_and_keeps_old_recreate_id(self):
        self.assertNotIn("attempt", self.previous["inputs"])
        self.assertNotIn("config_sha256", self.previous["inputs"])
        self.assertNotIn("config_sha256", self.previous)
        self.assertNotIn("backend_container", self.previous)
        result = self._validate()
        self.assertEqual(result["metadata"], self.metadata)
        self.assertEqual(
            result["metadata"]["recreate_operation"]["operation_id"],
            self.old_recreation_attempt,
        )
        self.assertEqual(result["binding"]["state"], "pending")
        self.assertEqual(result["attempt"], self.capture_attempt)
        self.assertEqual(result["previous_config_sha256"], self.fixture.config_sha)

    def test_new_capture_root_is_distinct_and_old_terminal_bytes_remain_unchanged(self):
        old_relative = "development/attempts/" + self.old_metadata_attempt + "/terminal.json"
        new_relative = "development/attempts/" + self.capture_attempt + "/terminal.json"
        self.assertNotEqual(old_relative, new_relative)
        self.assertNotEqual(
            self.fixture.control.records[old_relative],
            self.fixture.control.records[new_relative],
        )
        self.assertEqual(
            self.fixture.control.records["development/current.json"],
            self.fixture.control.records[new_relative],
        )
        self._validate()

    def test_current_pointer_and_new_attempt_terminal_must_have_identical_raw_bytes(self):
        changed = deepcopy(self.previous)
        changed["error"] += " drift"
        relative = "development/attempts/" + self.capture_attempt + "/terminal.json"
        self.fixture.control.records[relative] = _raw(changed)
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_current_terminal_metadata_drift_is_rejected(self):
        changed = deepcopy(self.previous)
        changed["inputs"]["post_build_generation"]["runtime_config"]["sha256"] = "f" * 64
        self._repin_terminal(changed)
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_source_identity_must_match_previous_inputs(self):
        changed = deepcopy(self.previous)
        changed["inputs"]["source_worktree_id"] = "other-worktree"
        self._repin_terminal(changed)
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_previous_config_input_is_pinned(self):
        changed = deepcopy(self.previous)
        changed["inputs"]["previous_config_sha256"] = "f" * 64
        self._repin_terminal(changed)
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_previous_input_attempt_is_pinned_to_current_capture_attempt(self):
        changed = deepcopy(self.previous)
        changed["inputs"]["attempt"] = self.old_metadata_attempt
        self._repin_terminal(changed)
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_compose_previous_config_environment_is_pinned(self):
        self.document["services"]["backend"]["environment"][
            "FULLMAG_DOCKER_PREVIOUS_CONFIG_SHA256"
        ] = "f" * 64
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_pre_admission_failure_log_path_and_sha_are_revalidated(self):
        changed = deepcopy(self.failure_log)
        changed["log"] += " changed"
        self.fixture.control.records[
            "development/attempts/" + self.capture_attempt + "/backend-failure-log.json"
        ] = _raw(changed)
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_pre_admission_parent_and_compose_config_pins_are_required(self):
        self.pre_admission_proof["parent_attempt"] = self.old_metadata_attempt
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

        self.pre_admission_proof["parent_attempt"] = self.capture_attempt
        self.pre_admission_proof["config_sha256"] = "f" * 64
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

        del self.pre_admission_proof["config_sha256"]
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_make_package_api_or_missing_capture_marker_is_rejected(self):
        changed = deepcopy(self.failure_log)
        changed["log"] = "phase=package state=published\n"
        failure_raw = _raw(changed)
        failure_path = (
            "development/attempts/" + self.capture_attempt + "/backend-failure-log.json"
        )
        changed_terminal = deepcopy(self.previous)
        changed_terminal["error"] = (
            "Backend exited during build; logs and volumes retained: " + changed["log"]
        )
        self.previous = changed_terminal
        terminal_raw = _raw(changed_terminal)
        terminal_path = "development/attempts/" + self.capture_attempt + "/terminal.json"
        self.fixture.control.records[failure_path] = failure_raw
        self.fixture.control.records[terminal_path] = terminal_raw
        self.fixture.control.records["development/current.json"] = terminal_raw
        self.pre_admission_proof["failure"]["failure_log_sha256"] = hashlib.sha256(
            failure_raw
        ).hexdigest()
        self.pre_admission_proof["failure"]["terminal_sha256"] = hashlib.sha256(
            terminal_raw
        ).hexdigest()
        self.pre_admission_proof["failure"]["terminal_error_sha256"] = hashlib.sha256(
            changed_terminal["error"].encode("utf-8")
        ).hexdigest()
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_compose_binding_drift_is_rejected(self):
        self.document["services"]["backend"]["environment"][
            continuation.START_BINDING_SHA_ENV
        ] = "f" * 64
        self._repin_compose_digest()
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_consumed_marker_is_rejected(self):
        consumed = (
            "runtime-control/runtime-services/post-build-continuation/"
            + self.capture_attempt
            + "/consumed.json"
        )
        self.fixture.control.records[consumed] = _raw({"state": "consumed"})
        with self.assertRaises(pending.PendingCaptureContinuationError):
            self._validate()

    def test_carry_receipt_check_does_not_rebind_old_operation(self):
        receipt = {
            "inputs": {"attempt": self.capture_attempt, "config_sha256": self.compose_sha},
            "removed_containers": [
                self.pre_admission_proof["failure"][service]["container_id"]
                for service in ("backend", "frontend")
            ],
            "post_build_generation": deepcopy(self.metadata),
            "pre_admission_recreate": deepcopy(self.pre_admission_proof),
            "accepted_reattach": deepcopy(self.producer),
        }
        pending.validate_carry_recreate_receipt(
            receipt,
            metadata=self.metadata,
            pre_admission_proof=self.pre_admission_proof,
            recreation_attempt="f" * 32,
            accepted_producer=self.producer,
        )
        with self.assertRaises(pending.PendingCaptureContinuationError):
            pending.validate_carry_recreate_receipt(
                receipt,
                metadata=self.metadata,
                pre_admission_proof=self.pre_admission_proof,
                recreation_attempt=self.old_recreation_attempt,
                accepted_producer=self.producer,
            )


    def test_carry_recreate_receipt_rejects_another_current_namespace(self):
        receipt = {
            "inputs": {"attempt": self.capture_attempt, "config_sha256": self.compose_sha},
            "removed_containers": [
                self.pre_admission_proof["failure"][service]["container_id"]
                for service in ("backend", "frontend")
            ],
            "post_build_generation": deepcopy(self.metadata),
            "pre_admission_recreate": deepcopy(self.pre_admission_proof),
            "accepted_reattach": deepcopy(self.producer),
        }
        for changed_field in ("backend", "parent", "malformed-inputs"):
            changed = deepcopy(receipt)
            if changed_field == "backend":
                changed["removed_containers"][0] = "a" * 64
            elif changed_field == "parent":
                changed["inputs"]["attempt"] = "a" * 32
            else:
                changed["inputs"] = []
            with self.subTest(changed_field=changed_field):
                with self.assertRaises(pending.PendingCaptureContinuationError):
                    pending.validate_carry_recreate_receipt(
                        changed,
                        metadata=self.metadata,
                        pre_admission_proof=self.pre_admission_proof,
                        recreation_attempt="f" * 32,
                        accepted_producer=self.producer,
                    )


if __name__ == "__main__":
    unittest.main()
