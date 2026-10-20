"""Behavioral regressions for the retained pre-admission proof validator.

The fixture uses the validator's real selector contract and patches only the
native host adapter.  It does not mock the validator, inspect Docker, write a
control volume, or exercise the recreate caller.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import fullmag_docker_runtime as runtime
import docker_volume_pre_admission_recreate as pre_admission


PROJECT = "fullmag-worktree-pre-admission"
VOLUME = PROJECT + "-control"
PARENT_ATTEMPT = "9a12fbd668f149a6a42ef726c5fbf9bb"
RESUME_ATTEMPT = "26778aad1fb24b249ed28023775d6cef"
IMAGE = "sha256:" + "d" * 64
TOOLCHAIN_IMAGE = "sha256:" + "e" * 64
STARTED_AT = "2026-10-20T15:16:30.069415108Z"
FINISHED_AT = "2026-10-20T15:30:10.872027859Z"
SOURCE_PROJECT = "fullmag-project"
SOURCE_WORKTREE = "pre-admission"
HOST_CERT_NAME = "windows-folder-host.json"
OWNER_NAME = ".fullmag-windows-folder-owner.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _control_raw(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _host_raw(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _set_candidate_config(fixture: _Fixture) -> None:
    candidate = fixture.selector["candidates"][0]
    candidate["terminal"]["inputs"]["config_sha256"] = "f" * 64
    candidate["terminal_raw"] = _control_raw(candidate["terminal"])


def _service(service: str, identifier: str, *, started_at: str = STARTED_AT) -> dict[str, object]:
    state: dict[str, object] = {
        "Running": False,
        "StartedAt": started_at,
    }
    if service == "backend":
        state.update(
            ExitCode=2,
            OOMKilled=False,
            FinishedAt=FINISHED_AT,
        )
    return {
        "Id": identifier,
        "Image": IMAGE,
        "State": state,
        "Config": {
            "Labels": {
                "com.docker.compose.project": PROJECT,
                "com.docker.compose.service": service,
                "org.fullmag.source.worktree-id": SOURCE_WORKTREE,
            },
        },
    }


class _ControlFixture:
    project = PROJECT
    volume = VOLUME

    def __init__(self, selector: dict[str, object]) -> None:
        self.selector = selector
        self.selector_calls: list[dict[str, str]] = []

    def read_pinned_resume_evidence(
        self,
        *,
        parent_attempt: str,
        config_sha256: str,
        backend_started_at: str,
        helper_image: str,
    ) -> dict[str, object]:
        self.selector_calls.append(
            {
                "parent_attempt": parent_attempt,
                "config_sha256": config_sha256,
                "backend_started_at": backend_started_at,
                "helper_image": helper_image,
            }
        )
        return deepcopy(self.selector)


class _Fixture:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="fullmag-pre-admission-validator-")
        root = Path(self.temp.name)
        self.state = root / "state"
        self.source = root / "source"
        self.state.mkdir()
        self.source.mkdir()
        self.identity = {
            "project_name": PROJECT,
            "project_id": SOURCE_PROJECT,
            "worktree_id": SOURCE_WORKTREE,
            "checkout_kind": "worktree",
        }
        self.document = {
            "name": PROJECT,
            "services": {
                "backend": {
                    "image": IMAGE,
                    "environment": {
                        "FULLMAG_SESSION_STORAGE_PROFILE": "windows-folder-v1",
                        "FULLMAG_TOOLCHAIN_IMAGE_ID": TOOLCHAIN_IMAGE,
                        "FULLMAG_STARTUP_ENABLED": "0",
                        "FULLMAG_DOCKER_DEVICE_ACCESS": "gpu",
                    },
                    "labels": {
                        "com.docker.compose.project": PROJECT,
                        "com.docker.compose.service": "backend",
                        "org.fullmag.source.worktree-id": SOURCE_WORKTREE,
                    },
                },
                "frontend": {
                    "image": IMAGE,
                    "labels": {
                        "com.docker.compose.project": PROJECT,
                        "com.docker.compose.service": "frontend",
                        "org.fullmag.source.worktree-id": SOURCE_WORKTREE,
                    },
                },
            },
        }
        self.config_sha256 = hashlib.sha256(_canonical(self.document)).hexdigest()
        self.previous = {
            "schema": "fullmag.docker-build-operation.v1",
            "phase": "development",
            "state": "failed-confirmed",
            "attempt": PARENT_ATTEMPT,
            "compose_project": PROJECT,
            "control_volume": VOLUME,
            "state_root": str(self.state),
            "inputs": {
                "source_root": str(self.source),
                "image_id": IMAGE,
                "toolchain_image_id": TOOLCHAIN_IMAGE,
                "source_project_id": SOURCE_PROJECT,
                "source_worktree_id": SOURCE_WORKTREE,
                "source_checkout_kind": "worktree",
                "gpu_access_requested": "auto",
                "device_access": "gpu",
            },
        }
        self.actual = {
            "backend": _service("backend", "b" * 64),
            "frontend": _service("frontend", "c" * 64),
        }
        provisional, binary_hashes, delegation = runtime._provisional_development_certificate(
            {"image_id": IMAGE, "toolchain_image_id": TOOLCHAIN_IMAGE},
            self.identity,
        )
        self.certificate = {
            "schema": "fullmag.windows-folder-host.v1",
            "storage_profile": "windows-folder-v1",
            "role": "session",
            "owner_scope": "docker-desktop-linux",
            "host_root": str(self.state),
            "host_filesystem": "NTFS",
            "host_drive_type": 3,
            "host_volume_serial": 42,
            "host_root_no_reparse": True,
            "owner_token": "00000000-0000-4000-8000-000000000001",
            "engine_id": "engine-test",
            "image_id": IMAGE,
            "source_commit": provisional["commit"],
            "binary_hashes": binary_hashes,
            "artifact_receipt_sha256": provisional["build_receipt_sha256"],
            "restart_expected_sha256": hashlib.sha256(
                ("00000000-0000-4000-8000-000000000001:" + IMAGE).encode("ascii")
            ).hexdigest(),
            "restart_verified": False,
            "development_build": delegation,
        }
        self.host_records = {
            HOST_CERT_NAME: _host_raw(self.certificate),
            OWNER_NAME: _host_raw(self.certificate),
        }
        self.host_reads: list[tuple[str, int]] = []
        self.adapter = self._host_adapter()
        self.failure = {"log": "make: *** [stat] Error 2\n"}
        self.resume_terminal = {
            "schema": "fullmag.docker-build-operation.v1",
            "phase": "resume",
            "state": "failed-confirmed",
            "attempt": RESUME_ATTEMPT,
            "compose_project": PROJECT,
            "control_volume": VOLUME,
            # This is the real legacy shape: source and image are inherited
            # from the parent development receipt and retained Compose state.
            "inputs": {
                "attempt": PARENT_ATTEMPT,
                "config_sha256": self.config_sha256,
            },
            "backend_started_at": STARTED_AT,
            "error": "Backend exited during build; logs and volumes retained: "
            + self.failure["log"][-4000:],
            "daemon_pending": False,
        }
        self._refresh_selector()
        self.accepted_context = {
            "accepted_reattach_environment": {
                "FULLMAG_ACCEPTED_REATTACH_REQUEST": "accepted-run-reattach/" + "r" * 64 + ".json",
                "FULLMAG_ACCEPTED_REATTACH_REQUEST_SHA256": "1" * 64,
            },
            "accepted_reattach_metadata": {
                "schema": "fullmag.docker-accepted-run-reattach-producer.v1",
                "state": "prepared",
                "request_sha256": "1" * 64,
                "proof_sha256": "2" * 64,
            },
        }
        self.control = _ControlFixture(self.selector)

    def _host_adapter(self) -> types.ModuleType:
        adapter = types.ModuleType("linux_native_host")
        adapter.HOST_SCHEMA = "fullmag.windows-folder-host.v1"
        adapter.HOST_CERT_PATH = "/run/fullmag/windows-folder-host.json"
        adapter.OWNER_NAME = OWNER_NAME

        def read_owned_regular(path: object, maximum: int = 1024 * 1024) -> bytes:
            name = Path(path).name
            self.host_reads.append((name, maximum))
            return self.host_records[name]

        adapter.read_owned_regular = read_owned_regular
        return adapter

    def _refresh_selector(self) -> None:
        terminal_path = f"resume/attempts/{RESUME_ATTEMPT}/terminal.json"
        failure_path = f"resume/attempts/{RESUME_ATTEMPT}/backend-failure-log.json"
        candidate = {
            "phase": "resume",
            "attempt": RESUME_ATTEMPT,
            "terminal_path": terminal_path,
            "failure_log_path": failure_path,
            "terminal": deepcopy(self.resume_terminal),
            "terminal_raw": _control_raw(self.resume_terminal),
            "failure_log": deepcopy(self.failure),
            "failure_log_raw": _control_raw(self.failure),
            "published_paths": {
                name: False for name in pre_admission.PUBLICATION_PATHS
            },
        }
        self.selector = {
            "schema": pre_admission.SELECTOR_SCHEMA,
            "max_entries": 1,
            "scanned_entries": 1,
            "candidate_count": 1,
            "candidates": [candidate],
        }
        if hasattr(self, "control"):
            self.control.selector = self.selector

    def set_failure_log(self, log: str) -> None:
        self.failure = {"log": log}
        self.resume_terminal["error"] = (
            "Backend exited during build; logs and volumes retained: "
            + log[-4000:]
        )
        self._refresh_selector()

    def replace_host_certificate(self, certificate: dict[str, object]) -> None:
        self.certificate = certificate
        self.host_records[HOST_CERT_NAME] = _host_raw(certificate)
        self.host_records[OWNER_NAME] = _host_raw(certificate)

    def close(self) -> None:
        self.temp.cleanup()

    def call(
        self,
        *,
        accepted_context: object | None = None,
        recovery_context: object | None = None,
    ) -> dict[str, object] | None:
        context = (
            deepcopy(self.accepted_context)
            if accepted_context is None
            else accepted_context
        )
        recovery = {} if recovery_context is None else recovery_context
        with patch.dict(sys.modules, {"linux_native_host": self.adapter}):
            return pre_admission.validate_pre_admission_recreate(
                self.control,
                self.previous,
                self.document,
                self.actual,
                self.state,
                self.certificate,
                self.identity,
                self.config_sha256,
                context,
                recovery,
            )


class PreAdmissionRecreateValidatorTests(unittest.TestCase):
    def fixture(self) -> _Fixture:
        fixture = _Fixture()
        self.addCleanup(fixture.close)
        return fixture

    def assert_rejected(self, fixture: _Fixture) -> None:
        with self.assertRaises(pre_admission.PreAdmissionRecreateError):
            fixture.call()

    def test_exact_legacy_bootstrap_receipt_is_accepted_with_accepted_context(self) -> None:
        fixture = self.fixture()
        accepted = deepcopy(fixture.accepted_context)
        proof = fixture.call(accepted_context=accepted)

        self.assertIsInstance(proof, dict)
        assert proof is not None
        self.assertEqual(proof["parent_attempt"], PARENT_ATTEMPT)
        self.assertEqual(proof["failure"]["attempt"], RESUME_ATTEMPT)
        self.assertEqual(proof["failure"]["backend_started_at"], STARTED_AT)
        self.assertEqual(proof["failure"]["backend"]["finished_at"], FINISHED_AT)
        self.assertEqual(proof["accepted_reattach"], accepted)
        self.assertEqual(
            proof["certificate"]["certificate_sha256"],
            hashlib.sha256(fixture.host_records[HOST_CERT_NAME]).hexdigest(),
        )
        self.assertEqual(
            proof["certificate"]["owner_sha256"],
            hashlib.sha256(fixture.host_records[OWNER_NAME]).hexdigest(),
        )
        self.assertEqual(
            fixture.host_reads,
            [
                (HOST_CERT_NAME, pre_admission.MAX_RECORD_BYTES),
                (OWNER_NAME, pre_admission.MAX_RECORD_BYTES),
            ],
        )
        self.assertEqual(
            fixture.control.selector_calls,
            [{
                "parent_attempt": PARENT_ATTEMPT,
                "config_sha256": fixture.config_sha256,
                "backend_started_at": STARTED_AT,
                "helper_image": IMAGE,
            }],
        )

        accepted["accepted_reattach_metadata"]["state"] = "changed-after-proof"
        self.assertEqual(proof["accepted_reattach"]["accepted_reattach_metadata"]["state"], "prepared")

    def test_validator_does_not_promote_already_admitted_certificate(self) -> None:
        fixture = self.fixture()
        fixture.certificate["restart_verified"] = True
        self.assertIsNone(fixture.call())
        self.assertEqual(fixture.control.selector_calls, [])

    def test_handoff_and_publication_probe_evidence_is_rejected(self) -> None:
        cases = {
            "handoff": "phase=start state=handoff\n",
            "api": "phase=api state=exec\n",
            "probe": "storage probe failed after phase=api state=exec\n",
        }
        for name, log in cases.items():
            with self.subTest(name=name):
                fixture = self.fixture()
                if name == "probe":
                    fixture.selector["candidates"][0]["published_paths"][
                        "storage-probe-log.json"
                    ] = True
                else:
                    fixture.set_failure_log(log)
                self.assert_rejected(fixture)

    def test_nonbootstrap_certificate_identity_is_rejected(self) -> None:
        cases = {
            "source": {"source_commit": "1" * 40},
            "artifact": {"artifact_receipt_sha256": "2" * 64},
            "binary": {"binary_hashes": {"fullmag": "3" * 64}},
        }
        for name, changes in cases.items():
            with self.subTest(name=name):
                fixture = self.fixture()
                certificate = deepcopy(fixture.certificate)
                certificate.update(changes)
                fixture.replace_host_certificate(certificate)
                self.assert_rejected(fixture)

    def test_wrong_parent_or_compose_pins_are_rejected(self) -> None:
        cases = {
            "parent_worktree": lambda fixture: fixture.previous["inputs"].update(
                source_worktree_id="foreign-worktree"
            ),
            "candidate_config": _set_candidate_config,
            "actual_image": lambda fixture: fixture.actual["backend"].update(
                Image="sha256:" + "0" * 64
            ),
            "certificate_image": lambda fixture: fixture.replace_host_certificate(
                {**fixture.certificate, "image_id": "sha256:" + "0" * 64}
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                fixture = self.fixture()
                mutate(fixture)
                self.assert_rejected(fixture)

    def test_retained_container_started_at_drift_is_rejected(self) -> None:
        fixture = self.fixture()
        fixture.actual["backend"]["State"]["StartedAt"] = (
            "2026-10-20T15:16:31.000000000Z"
        )
        self.assert_rejected(fixture)

    def test_native_pending_recovery_is_rejected(self) -> None:
        fixture = self.fixture()
        with self.assertRaises(pre_admission.PreAdmissionRecreateError):
            fixture.call(recovery_context={"native_restart_metadata": {"claim_pending": True}})

    def test_certificate_owner_raw_content_drift_is_rejected(self) -> None:
        fixture = self.fixture()
        fixture.host_records[OWNER_NAME] = _host_raw(
            {**fixture.certificate, "owner_token": "foreign-owner"}
        )
        self.assert_rejected(fixture)

    def test_selector_raw_bytes_drift_is_rejected(self) -> None:
        fixture = self.fixture()
        candidate = fixture.selector["candidates"][0]
        candidate["terminal_raw"] = b"{}\n"
        self.assert_rejected(fixture)

    def test_selector_method_is_required_and_frontend_proof_has_identity_only(self) -> None:
        fixture = self.fixture()
        fixture.control.read_pinned_resume_evidence = None
        self.assert_rejected(fixture)

        fixture = self.fixture()
        proof = fixture.call()
        assert proof is not None
        frontend = proof["failure"]["frontend"]
        self.assertEqual(set(frontend), {"container_id", "image_id", "labels", "started_at"})
        self.assertNotIn("health", proof)
        self.assertNotIn("timestamp_now", proof)


if __name__ == "__main__":
    unittest.main()
