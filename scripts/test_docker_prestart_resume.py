"""Regressions for resuming a closed pre-start recreation successor."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import docker_volume_dev as volume_dev
import docker_volume_post_build_generation as continuation
import docker_volume_stop_unadmitted as stop_unadmitted
import test_docker_volume_post_build_generation as generation_fixture


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


class PreStartResumeTests(unittest.TestCase):
    successor_attempt = "f" * 32
    successor_image = "sha256:" + "f" * 64
    state_root = "/retained/fullmag-state"
    frontend_container = "c" * 64
    config_raw = b"{\"runtime\":\"prestart-resume\"}\n"

    @staticmethod
    def _probe_digest(values: dict[str, str]) -> str:
        encoded = (
            json.dumps(
                {
                    "schema": "fullmag.operator-probe-environment.v1",
                    "values": values,
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _service_snapshot(
        service: str,
        identifier: str,
        image: str,
        labels: dict[str, str],
        environment: dict[str, str],
        *,
        exit_code: int | None = None,
    ) -> dict[str, object]:
        state: dict[str, object] = {
            "Running": False,
            "StartedAt": "2026-10-20T15:16:30.069415108Z",
        }
        if service == "backend":
            state.update(
                Status="exited",
                FinishedAt="2026-10-20T15:17:01.069415108Z",
                ExitCode=2 if exit_code is None else exit_code,
            )
        return {
            "Id": identifier,
            "Image": image,
            "State": state,
            "Config": {
                "Env": [name + "=" + value for name, value in environment.items()],
                "Labels": labels,
                "Entrypoint": None,
                "Cmd": None,
            },
            "HostConfig": {"ReadonlyRootfs": True, "Privileged": False, "Tmpfs": {}},
            "Mounts": [],
        }

    @classmethod
    def _recreation_resume_projection(cls, proof: dict[str, object]) -> dict[str, object]:
        projection = {
            key: proof[key]
            for key in (
                "recreation_operation_id",
                "recreation_terminal_sha256",
                "retained_snapshot_sha256",
                "prior_terminal_sha256",
                "prior_compose_sha256",
            )
        }
        projection["proof_sha256"] = hashlib.sha256(continuation.canonical(proof)).hexdigest()
        return projection

    def _fixture(self):
        source = generation_fixture.PostBuildContinuationTests()
        source.setUp()
        source.previous["state_root"] = self.state_root
        operator_probe = {
            "operator_probe_environment_schema": "fullmag.operator-probe-environment.v1",
            "operator_probe_environment": {
                "FULLMAG_MIXED_P1_DEVICE": "gpu",
                "FULLMAG_ARTIFACT_FIELD_STORAGE": "json",
            },
            "operator_probe_environment_sha256": self._probe_digest(
                {
                    "FULLMAG_MIXED_P1_DEVICE": "gpu",
                    "FULLMAG_ARTIFACT_FIELD_STORAGE": "json",
                }
            ),
        }
        source.records[continuation.CONFIG_RELATIVE] = self.config_raw
        current_process = json.loads(source.records[continuation.CONTROL_PROCESS])
        current_process["accepted_store"] = "/var/lib/fullmag/accepted-store"
        current_process["qualification"] = "NOT VERIFIED"
        source.records[continuation.CONTROL_PROCESS] = _raw(current_process)
        accepted_producer = source.accepted_context["accepted_reattach_metadata"]
        accepted_producer.update(
            source_request_id="source-request",
            source_sha256="1" * 64,
            startup_provenance_sha256="2" * 64,
            config_sha256="3" * 64,
            activation_record_relative="activation/attempts/" + "e" * 32 + "/receipt.json",
            startup_provenance_relative="activation/attempts/" + "e" * 32 + "/startup-provenance.json",
            authorization_relative="activation/attempts/" + "e" * 32 + "/authorization.json",
            reconciliation_record_relative=(
                "activation-reconciliation/attempts/" + "f" * 32 + "/terminal.json"
            ),
            terminal_process_receipt_relative="runtime-control/runtime-service/process-tree.json",
            terminal_process_receipt_sha256=hashlib.sha256(
                _raw(source.stop["terminal_process_receipt"])
            ).hexdigest(),
            terminal_failed_owner_relative="runtime-control/runtime-services/OWNER.json",
            terminal_failed_owner_sha256=hashlib.sha256(
                _raw(source.stop["terminal_failed_owner"])
            ).hexdigest(),
            activation_receipt_sha256="5" * 64,
            control_request_relative="accepted-run-reattach-control/request.json",
            control_proof_relative="accepted-run-reattach-control/proof.json",
            namespace_attestation_relative=(
                "verification/stopped-namespace-attestation-"
                + source.old_backend
                + ".json"
            ),
            namespace_attestation_sha256="6" * 64,
        )
        source.previous.update(
            schema="fullmag.docker-build-operation.v1",
            phase="development",
            state="failed-confirmed",
            compose_project=_Control.project,
            control_volume=_Control.volume,
            frontend_container=self.frontend_container,
            backend_volumes=["fullmag-backend-cache"],
            frontend_volume="fullmag-frontend-build",
            **operator_probe,
        )
        source.previous["inputs"].update(
            source_project_id="fullmag-project",
            source_worktree_id="continuation",
            source_checkout_kind="worktree",
            gpu_access_requested="auto",
            device_access="gpu",
            gpu_preflight="PASS",
            **operator_probe,
        )

        backend_labels = {
            "com.docker.compose.project": _Control.project,
            "com.docker.compose.service": "backend",
            "org.fullmag.source.project-id": "fullmag-project",
            "org.fullmag.source.worktree-id": "continuation",
            "org.fullmag.source.checkout-kind": "worktree",
        }
        frontend_labels = {
            "com.docker.compose.project": _Control.project,
            "com.docker.compose.service": "frontend",
            "org.fullmag.source.project-id": "fullmag-project",
            "org.fullmag.source.worktree-id": "continuation",
            "org.fullmag.source.checkout-kind": "worktree",
        }
        backend_environment = {
            **operator_probe["operator_probe_environment"],
            "FULLMAG_OPERATOR_PROBE_ENVIRONMENT_SHA256": operator_probe[
                "operator_probe_environment_sha256"
            ],
            "FULLMAG_DEVELOPMENT_INPUTS_PATH": (
                "/opt/fullmag/control/frontend/development-inputs.json"
            ),
            "FULLMAG_CONTROL_NAMESPACE": "",
            "FULLMAG_DEV_INCLUDE_UNTRACKED": "[]",
        }
        source.document = {
            "name": _Control.project,
            "services": {
                "backend": {
                    "image": source.image,
                    "environment": backend_environment,
                    "labels": backend_labels,
                    "volumes": [],
                },
                "frontend": {
                    "image": source.image,
                    "environment": {
                        "FULLMAG_DEVELOPMENT_INPUTS_PATH": (
                            "/opt/fullmag/control/development-inputs.json"
                        ),
                    },
                    "labels": frontend_labels,
                    "volumes": [{
                        "type": "volume",
                        "source": "build-control",
                        "target": "/opt/fullmag/control",
                        "read_only": True,
                        "volume": {"subpath": "frontend"},
                    }],
                    "ports": [{
                        "host_ip": "127.0.0.1",
                        "mode": "ingress",
                        "protocol": "tcp",
                        "target": 8080,
                        "published": "3197",
                    }],
                },
            },
            "volumes": {"build-control": {"name": _Control.volume}},
        }
        source.actual = self._service_snapshot(
            "backend",
            source.current_backend,
            source.image,
            backend_labels,
            backend_environment,
        )
        frontend_snapshot = self._service_snapshot(
            "frontend",
            self.frontend_container,
            source.image,
            frontend_labels,
            source.document["services"]["frontend"]["environment"],
        )
        frontend_snapshot["Mounts"] = [{
            "Type": "volume",
            "Name": _Control.volume,
            "Destination": "/opt/fullmag/control",
            "RW": False,
        }]
        source.frontend_snapshot = frontend_snapshot
        runtime_config_sha256 = hashlib.sha256(self.config_raw).hexdigest()
        base = continuation.build_failed_owner_continuation(
            source.control,
            operation_id=source.attempt,
            previous=source.previous,
            document=source.document,
            actual_backend=source.actual,
            source_identity=source.source,
            certificate_evidence=source.certificate,
            accepted_context=source.accepted_context,
            runtime_config_sha256=runtime_config_sha256,
        )
        proof = source._recreation_proof()
        proof["native_recovery_context"] = {}
        stopped = source.actual["State"]
        proof.update(
            schema="fullmag.docker-removed-recreation-container.v1",
            container_state={
                "id": source.current_backend,
                "image": source.image,
                "started_at": stopped["StartedAt"],
                "finished_at": stopped["FinishedAt"],
                "exit_code": stopped["ExitCode"],
            },
        )

        prior_relative = "development/attempts/" + source.attempt + "/terminal.json"
        prior_raw = _raw(source.previous)
        source.recreation_records[prior_relative] = prior_raw
        proof["prior_terminal_sha256"] = hashlib.sha256(prior_raw).hexdigest()

        operation_relative = (
            "recreate-services/attempts/"
            + proof["recreation_operation_id"]
            + "/terminal.json"
        )
        operation_terminal = json.loads(source.recreation_records[operation_relative])
        operation_terminal["post_build_generation"] = base
        operation_terminal.update(
            inputs={
                "attempt": source.attempt,
                "config_sha256": hashlib.sha256(
                    continuation.canonical(source.document)
                ).hexdigest(),
                **operator_probe,
            },
            accepted_reattach=accepted_producer,
            compose_project=_Control.project,
            control_volume=_Control.volume,
            previous_state_root=source.previous["state_root"],
            retained_volumes=source.previous["backend_volumes"],
            retained_frontend_volume=source.previous["frontend_volume"],
            fresh_state=False,
        )
        source.recreation_records[
            "recreate-services/attempts/"
            + proof["recreation_operation_id"]
            + "/retained-containers.json"
        ] = _raw({
            "backend": source.actual,
            "frontend": source.frontend_snapshot,
        })
        operation_raw = _raw(operation_terminal)
        source.recreation_records[operation_relative] = operation_raw
        proof["recreation_terminal_sha256"] = hashlib.sha256(operation_raw).hexdigest()
        proof["retained_snapshot_sha256"] = hashlib.sha256(
            source.recreation_records[
                "recreate-services/attempts/"
                + proof["recreation_operation_id"]
                + "/retained-containers.json"
            ]
        ).hexdigest()
        proof["prior_compose_sha256"] = hashlib.sha256(
            _raw(source.document)
        ).hexdigest()

        metadata = continuation.bind_recreate_operation(base, proof)
        operation = {
            "root": "development/attempts/" + self.successor_attempt,
            "receipt": {"phase": "development", "attempt": self.successor_attempt},
        }
        binding = continuation.prepare_start_binding(metadata, operation)
        retained_relative = (
            "recreate-services/attempts/"
            + proof["recreation_operation_id"]
            + "/retained-containers.json"
        )
        retained_raw = source.recreation_records[retained_relative]
        successor = {
            "schema": "fullmag.docker-build-operation.v1",
            "phase": "development",
            "state": "failed-confirmed",
            "error": (
                "Post-build continuation changed under the new development lease: "
                "fixture pre-start failure"
            ),
            "attempt": self.successor_attempt,
            "compose_project": _Control.project,
            "control_volume": _Control.volume,
            "state_root": self.state_root,
            "inputs": {
                "source_root": source.source_root,
                "source_project_id": "fullmag-project",
                "source_worktree_id": "continuation",
                "source_checkout_kind": "worktree",
                "gpu_access_requested": "auto",
                "device_access": "gpu",
                "gpu_preflight": "PASS",
                "image_id": self.successor_image,
                "previous_config_sha256": runtime_config_sha256,
                **operator_probe,
                "accepted_reattach": accepted_producer,
                "post_build_generation": metadata,
            },
            "post_build_generation": metadata,
            "post_build_start": binding["receipt"],
            **operator_probe,
            "accepted_reattach": accepted_producer,
        }
        records = dict(source.recreation_records)
        successor_root = "development/attempts/" + self.successor_attempt
        records[successor_root + "/post-build-continuation.json"] = _raw(binding["record"])
        successor_raw = _raw(successor)
        records[successor_root + "/terminal.json"] = successor_raw
        records["development/current.json"] = successor_raw
        return {
            "args": types.SimpleNamespace(
                attempt=source.attempt,
                resume_recreation=proof["recreation_operation_id"],
                config_sha256=hashlib.sha256(
                    continuation.canonical(source.document)
                ).hexdigest(),
                port=3197,
                gpu_access="auto",
                include_untracked=[],
            ),
            "control": _Control(records),
            "selected": Path(source.source_root),
            "identity": {
                "project_id": "fullmag-project",
                "worktree_id": "continuation",
                "checkout_kind": "worktree",
            },
            "current": successor,
            "current_raw": successor_raw,
            "previous": source.previous,
            "previous_raw": prior_raw,
            "document": source.document,
            "document_raw": _raw(source.document),
            "operation_raw": operation_raw,
            "operation_terminal": operation_terminal,
            "retained_raw": retained_raw,
            "operator_probe": operator_probe,
            "proof": proof,
            "native_recovery_context": {},
            "accepted_producer": accepted_producer,
        }

    def _validate(self, fixture) -> None:
        with patch.object(
            stop_unadmitted,
            "_control_bytes",
            side_effect=lambda control, relative, optional=False: control.read_raw(
                relative, optional=optional
            ),
        ):
            volume_dev._validate_failed_prestart_successor(
                fixture["args"],
                fixture["control"],
                fixture["selected"],
                fixture["identity"],
                current_raw=fixture["current_raw"],
                current=fixture["current"],
                previous_raw=fixture["previous_raw"],
                previous=fixture["previous"],
                document_raw=fixture["document_raw"],
                operation_raw=fixture["operation_raw"],
                operation_terminal=fixture["operation_terminal"],
                retained_raw=fixture["retained_raw"],
                operator_probe_record=fixture["operator_probe"],
                native_recovery_context=fixture["native_recovery_context"],
                removed_container_proof=fixture["proof"],
            )

    def _rewrite_current(self, fixture) -> None:
        fixture["current_raw"] = _raw(fixture["current"])
        fixture["control"].records["development/current.json"] = fixture["current_raw"]
        fixture["control"].records[
            "development/attempts/" + self.successor_attempt + "/terminal.json"
        ] = fixture["current_raw"]

    def _validate_full_resume(self, fixture):
        """Exercise the recreation caller with Docker/control reads only mocked."""
        def docker_text(*args):
            self.assertEqual(args[:2], ("image", "inspect"))
            self.assertEqual(args[2], fixture["previous"]["inputs"]["image_id"])
            return json.dumps([{"Config": {}}])

        def docker_capture(*args, **kwargs):
            self.assertIn(args[0], {"inspect", "ps"})
            identifier = args[1] if args[0] == "inspect" else args[-1].split("=", 1)[1]
            if args[0] == "inspect":
                return types.SimpleNamespace(
                    returncode=1,
                    stdout=b"",
                    stderr=(b"Error: No such object: " + identifier.encode() + b"\n"),
                )
            return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        with patch.object(
            stop_unadmitted,
            "_control_bytes",
            side_effect=lambda control, relative, optional=False: control.read_raw(
                relative, optional=optional
            ),
        ), patch.object(volume_dev, "docker_text", side_effect=docker_text), patch.object(
            volume_dev, "docker_capture", side_effect=docker_capture
        ), patch.object(volume_dev, "_retained_recovery_context", return_value={}):
            return volume_dev._validate_recreation_resume_records(
                fixture["args"],
                fixture["control"],
                fixture["selected"],
                fixture["identity"],
            )

    def test_closed_failed_prestart_successor_keeps_original_previous(self):
        fixture = self._fixture()
        self._validate(fixture)
        self.assertEqual(fixture["previous"]["attempt"], "d" * 32)
        self.assertNotEqual(fixture["current"]["attempt"], fixture["previous"]["attempt"])
        self.assertNotIn("toolchain_image_id", fixture["current"]["inputs"])
        self.assertNotIn("recreation_resume", fixture["current"]["inputs"])
        self.assertEqual(len(fixture["current"]["accepted_reattach"]), 46)
        self.assertEqual(
            fixture["current"]["accepted_reattach"],
            fixture["current"]["inputs"]["accepted_reattach"],
        )
        self.assertEqual(
            fixture["current"]["accepted_reattach"],
            fixture["operation_terminal"]["accepted_reattach"],
        )
        self.assertNotEqual(
            fixture["current"]["accepted_reattach"],
            fixture["current"]["post_build_generation"]["accepted_run"],
        )

    def test_full_resume_validator_keeps_original_previous_and_exact_proof(self):
        fixture = self._fixture()
        records = self._validate_full_resume(fixture)
        self.assertEqual(records["previous"]["attempt"], "d" * 32)
        self.assertEqual(records["proof"], fixture["proof"])

    def test_exact_nested_recreation_resume_projection_is_admitted(self):
        fixture = self._fixture()
        fixture["current"]["inputs"]["recreation_resume"] = self._recreation_resume_projection(
            fixture["proof"]
        )
        self._rewrite_current(fixture)
        self._validate(fixture)

    def test_nested_recreation_resume_foreign_projection_is_rejected(self):
        fixture = self._fixture()
        foreign = self._recreation_resume_projection(fixture["proof"])
        foreign["recreation_operation_id"] = "1" * 32
        fixture["current"]["inputs"]["recreation_resume"] = foreign
        self._rewrite_current(fixture)
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_pending_binding_bytes_and_hash_are_exact(self):
        fixture = self._fixture()
        relative = "development/attempts/" + self.successor_attempt + "/post-build-continuation.json"
        binding_raw = fixture["control"].records[relative]
        self.assertEqual(binding_raw, _raw(json.loads(binding_raw)))
        self.assertEqual(
            hashlib.sha256(binding_raw).hexdigest(),
            fixture["current"]["post_build_start"]["sha256"],
        )
        self._validate(fixture)

    def test_pending_binding_bytes_cannot_be_mutated_under_same_reference(self):
        fixture = self._fixture()
        relative = "development/attempts/" + self.successor_attempt + "/post-build-continuation.json"
        binding_raw = fixture["control"].records[relative]
        fixture["control"].records[relative] = binding_raw.replace(
            b'"state":"pending"', b'"state":"pending" '
        )
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_pending_binding_digest_and_path_are_exact(self):
        for field, value in (("sha256", "0" * 64), ("path", "/foreign/post-build-continuation.json")):
            with self.subTest(field=field):
                fixture = self._fixture()
                fixture["current"]["post_build_start"][field] = value
                self._rewrite_current(fixture)
                with self.assertRaises(volume_dev.BuildControlError):
                    self._validate(fixture)

    def test_previous_config_digest_is_bound_to_runtime_metadata(self):
        fixture = self._fixture()
        fixture["current"]["inputs"]["previous_config_sha256"] = "0" * 64
        self._rewrite_current(fixture)
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_device_access_and_gpu_preflight_remain_bound_to_previous_inputs(self):
        for field, value in (("device_access", "cpu"), ("gpu_preflight", "FAIL")):
            with self.subTest(field=field):
                fixture = self._fixture()
                fixture["current"]["inputs"][field] = value
                self._rewrite_current(fixture)
                with self.assertRaises(volume_dev.BuildControlError):
                    self._validate(fixture)

    def test_native_restart_evidence_requires_native_recovery_context(self):
        fixture = self._fixture()
        fixture["current"]["inputs"]["native_failed_restart"] = {
            "schema": "fullmag.native-restart.v1",
        }
        self._rewrite_current(fixture)
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_successor_inputs_have_a_closed_allowlist(self):
        fixture = self._fixture()
        fixture["current"]["inputs"]["unexpected"] = "published"
        self._rewrite_current(fixture)
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_current_pointer_must_be_the_successor_terminal_bytes(self):
        fixture = self._fixture()
        fixture["control"].records[
            "development/attempts/" + self.successor_attempt + "/terminal.json"
        ] = _raw({**fixture["current"], "error": "different terminal"})
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_active_lease_is_not_admitted(self):
        fixture = self._fixture()
        fixture["control"].records["active"] = _raw({"attempt": self.successor_attempt})
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_consumed_continuation_is_not_admitted(self):
        fixture = self._fixture()
        consumed = (
            "runtime-control/runtime-services/post-build-continuation/"
            + self.successor_attempt
            + "/consumed.json"
        )
        fixture["control"].records[consumed] = _raw({"state": "consumed"})
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_published_compose_or_cache_artifact_is_not_admitted(self):
        for filename in ("compose.json", "backend-cache.json", "frontend-seed.json"):
            with self.subTest(filename=filename):
                fixture = self._fixture()
                fixture["control"].records[
                    "development/attempts/" + self.successor_attempt + "/" + filename
                ] = b"{}\n"
                with self.assertRaises(volume_dev.BuildControlError):
                    self._validate(fixture)

    def test_current_must_be_a_mapping(self):
        fixture = self._fixture()
        fixture["current"] = ["not", "a", "receipt"]
        fixture["current_raw"] = _raw(fixture["current"])
        fixture["control"].records["development/current.json"] = fixture["current_raw"]
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_published_successor_is_not_admitted_as_prestart_failure(self):
        fixture = self._fixture()
        fixture["current"]["backend_container"] = "1" * 64
        self._rewrite_current(fixture)
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_unknown_successor_state_is_not_treated_as_prestart_failure(self):
        fixture = self._fixture()
        fixture["current"]["state"] = "succeeded"
        self._rewrite_current(fixture)
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_arbitrary_later_failure_is_not_treated_as_prestart_failure(self):
        fixture = self._fixture()
        fixture["current"]["error"] = "backend failed after the admission gate"
        self._rewrite_current(fixture)
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)

    def test_foreign_recreation_binding_is_not_admitted(self):
        fixture = self._fixture()
        foreign = deepcopy(fixture["current"]["post_build_generation"])
        foreign["recreate_operation"]["operation_id"] = "1" * 32
        fixture["current"]["post_build_generation"] = foreign
        fixture["current"]["inputs"]["post_build_generation"] = foreign
        self._rewrite_current(fixture)
        with self.assertRaises(volume_dev.BuildControlError):
            self._validate(fixture)


if __name__ == "__main__":
    unittest.main()
