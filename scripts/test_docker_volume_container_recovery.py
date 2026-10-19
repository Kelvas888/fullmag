"""Interpreted regressions for controlled stopped-container recovery.

These checks are intentionally Docker-free.  They cover the authorization,
outcome-unknown journal and helper command boundaries without compiling Rust,
starting Compose, or touching a runtime volume.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docker_volume_container_recovery as recovery  # noqa: E402


class ContainerRecoveryTests(unittest.TestCase):
    @staticmethod
    def operator(**overrides):
        value = {
            "schema_version": recovery.OPERATOR_AUTHORIZATION_SCHEMA,
            "request_id": "1eccf696-733d-4506-bbd7-9fd79ea602fa",
            "source_root": "C:/git/fullmag/fullmag",
            "compose_project": "fullmag-worktree-docker-volume-only-implementatio-670653a9f4702651",
            "development_attempt": "a" * 32,
            "compose_config_sha256": "1" * 64,
            "backend_container_id": "2" * 64,
            "frontend_container_id": "3" * 64,
            "old_image_id": "sha256:" + "4" * 64,
            "prior_stop_journal": "verification/stop-unadmitted-" + "a" * 32 + ".json",
            "prior_stop_journal_sha256": "5" * 64,
            "process_receipt_sha256": "6" * 64,
            "config_sha256": "7" * 64,
            "owner_sha256": "8" * 64,
            "launch_sha256": "9" * 64,
        }
        value.update(overrides)
        return value

    def test_operator_authorization_binds_prior_journal_not_shutdown_receipt(self):
        value = recovery.validate_operator_authorization(self.operator())
        self.assertEqual(value["prior_ready_owner_proof_sha256"], "5" * 64)
        with self.assertRaisesRegex(recovery.ContainerRecoveryError, "fields"):
            recovery.validate_operator_authorization({**self.operator(), "unexpected": True})

    def test_outcome_unknown_journal_requires_empty_reprobe(self):
        authorization = recovery.validate_operator_authorization(self.operator())
        journal = {
            "schema": "fullmag.docker-unadmitted-stop.v1",
            "state": "outcome-unknown",
            "attempt": authorization["attempt"],
            "backend_container_id": authorization["backend_container_id"],
            "frontend_container_id": authorization["frontend_container_id"],
            "image_id": authorization["old_image_id"],
            "process_receipt_sha256": "a" * 64,
            "request_id": "docker-startup-" + "b" * 32,
            "session_id": "docker-startup-" + "c" * 32,
            "source_sha256": "d" * 64,
            "failure_marker_sha256": "e" * 64,
            "proof_recheck": {
                "schema": "fullmag.docker-unadmitted-stop-probe.v1",
                "request_id": "docker-startup-" + "b" * 32,
                "session_id": "docker-startup-" + "c" * 32,
                "source_sha256": "d" * 64,
                "activation_marker_sha256": "e" * 64,
                "process_receipt_sha256": "a" * 64,
                "current_session": {"status": "startup_failed"},
                "compute_queue": {"items": []},
                "current_run_status": 404,
                "accepted_store": {"run_records": []},
                "host_ledger": {"reservation_states": ["released"]},
                "runtime_service": {"configured": True, "state": "ready"},
            },
        }
        recovery._validate_pre_admission_stop_journal(
            journal, authorization, authorization["attempt"]
        )
        journal["proof_recheck"]["accepted_store"]["run_records"] = ["run_intent.json"]
        with self.assertRaisesRegex(recovery.ContainerRecoveryError, "run records"):
            recovery._validate_pre_admission_stop_journal(
                journal, authorization, authorization["attempt"]
            )

    def test_storage_probe_uses_old_backend_python_and_readonly_binds(self):
        class Control:
            project = "fullmag-test"

        backend = {
            "Image": "sha256:" + "f" * 64,
            "Mounts": [
                {"Destination": "/state", "Type": "bind", "Source": "/windows/state", "RW": True},
                {"Destination": "/host-ledger", "Type": "bind", "Source": "/windows/ledger", "RW": True},
            ],
        }
        output = json.dumps({
            "store_root_sha256": "1" * 64,
            "ledger_root_sha256": "2" * 64,
            "ledger_snapshot_sha256": "3" * 64,
            "run_records": [],
        }).encode()
        result = type("Result", (), {"returncode": 0, "stdout": output, "stderr": b""})()
        with patch.object(recovery, "bounded_capture", return_value=result) as capture:
            proof = recovery._ledger_and_store_snapshot(Control(), backend)
        self.assertEqual(proof["ledger_snapshot_sha256"], "3" * 64)
        argv = capture.call_args.args[0]
        self.assertIn("/usr/local/bin/python3", argv)
        self.assertIn("-B", argv)
        self.assertIn("-c", argv)
        self.assertIn("type=bind,src=/windows/state,dst=/state,readonly", argv)
        self.assertIn("type=bind,src=/windows/ledger,dst=/host-ledger,readonly", argv)
        self.assertIn("deadline=time.monotonic()+5", " ".join(argv))
        self.assertNotIn("bind-nonrecursive", " ".join(argv))

    def test_container_pin_normalizes_docker_null_device_requests(self):
        container = {
            "Id": "a" * 64,
            "Image": "sha256:" + "b" * 64,
            "Config": {
                "Labels": {
                    "com.docker.compose.project": "fullmag-test",
                    "com.docker.compose.service": "backend",
                },
            },
            "HostConfig": {"PidMode": None, "DeviceRequests": None},
        }
        pin = recovery._container_pin(container, "backend", "fullmag-test")
        self.assertEqual(pin["device_requests_sha256"], hashlib.sha256(b"[]").hexdigest())

    def test_request_uses_raw_config_sha_for_external_application(self):
        config_sha = "f" * 64
        owner = {
            "schema_version": "runtime_service_owner.v1",
            "state": "unknown",
            "owner_token": "owner-token",
            "process_start_token": "process-token",
            "target_id": "docker-all",
            "host": "backend-host",
            "protocol": "tcp",
            "pid": 100,
            "children": [{"role": "compute"}, {"role": "preparation"}],
        }
        device = {
            "resource_id": "runtime-cpu",
            "mapping_sha256": "1" * 64,
            "mapping_detached": True,
        }
        authorization = recovery.validate_operator_authorization(self.operator())
        class Control:
            @staticmethod
            def path(relative):
                return "/control/" + relative

        with patch.object(recovery, "_control_json", return_value=(None, None)):
            request = recovery._build_request(
                authorization,
                owner=owner,
                owner_sha256="2" * 64,
                launch_sha256="3" * 64,
                config={},
                control=Control(),
                device_release=device,
                config_sha256=config_sha,
                store_root_sha256="4" * 64,
                ledger_root_sha256="5" * 64,
                ledger_snapshot_sha256="6" * 64,
                docker_engine_id_sha256="7" * 64,
                manifest_sha256="8" * 64,
                containers=[
                    {
                        "container_id": "9" * 64,
                        "image_id": "sha256:" + "a" * 64,
                        "config_sha256": "b" * 64,
                        "service": "backend",
                        "compose_project": "fullmag-test",
                        "private_pid_namespace": True,
                        "host_pid": False,
                        "device_requests_sha256": "c" * 64,
                    },
                    {
                        "container_id": "d" * 64,
                        "image_id": "sha256:" + "a" * 64,
                        "config_sha256": "e" * 64,
                        "service": "frontend",
                        "compose_project": "fullmag-test",
                        "private_pid_namespace": True,
                        "host_pid": False,
                        "device_requests_sha256": "f" * 64,
                    },
                ],
            )
        self.assertEqual(request["application"], {"mode": "external_only", "raw_sha256": config_sha})

    def test_prepared_transition_is_resumable_before_absence_sidecar(self):
        """A crash between rm and absence publication remains recoverable."""
        authorization = recovery.validate_operator_authorization(self.operator())
        project = authorization["compose_project"]
        image = authorization["old_image_id"]
        backend_id = authorization["backend_container_id"]
        frontend_id = authorization["frontend_container_id"]

        def inspect(service, identifier):
            config = {
                "Labels": {
                    "com.docker.compose.project": project,
                    "com.docker.compose.service": service,
                },
            }
            return {
                "Id": identifier,
                "Image": image,
                "Config": config,
                "HostConfig": {"PidMode": None, "DeviceRequests": None},
                "State": {"Running": False, "Pid": 0, "FinishedAt": "2026-10-19T00:00:00Z"},
                "NetworkSettings": {"Networks": {"fullmag-private": {}}},
            }

        backend = inspect("backend", backend_id)
        frontend = inspect("frontend", frontend_id)
        backend_pin = recovery._container_pin(backend, "backend", project)
        frontend_pin = recovery._container_pin(frontend, "frontend", project)
        owner = {
            "schema_version": "runtime_service_owner.v1",
            "state": "unknown",
            "owner_token": "owner-token",
            "process_start_token": "process-token",
            "target_id": "docker-all",
            "host": "backend-host",
            "protocol": "tcp",
            "pid": 100,
            "children": [
                {"role": "compute", "pid": 101},
                {"role": "preparation", "pid": 102},
            ],
        }
        request = recovery.validate_request({
            "schema_version": recovery.REQUEST_SCHEMA,
            "request_id": authorization["request_id"],
            "config_sha256": "7" * 64,
            "owner_sha256": "8" * 64,
            "launch_sha256": "9" * 64,
            "expected_owner": owner,
            "store_root_sha256": "a" * 64,
            "application": {"mode": "external_only", "raw_sha256": "7" * 64},
            "ledger_root_sha256": "b" * 64,
            "ledger_snapshot_sha256": "c" * 64,
            "docker_engine_id_sha256": "d" * 64,
            "docker_manifest_sha256": "e" * 64,
            "prior_ready_owner_proof_sha256": authorization["prior_stop_journal_sha256"],
            "device_release_resource_id": "runtime-cpu",
            "device_release_mapping_sha256": "f" * 64,
            "containers": [backend_pin, frontend_pin],
        })
        request_raw = recovery._canonical(request)
        manifest = recovery._manifest(
            authorization,
            "1" * 64,
            backend,
            frontend,
            [backend_pin, frontend_pin],
            {"resource_id": "runtime-cpu", "mapping_sha256": "f" * 64, "mapping_detached": True},
            {"kind": "cpu"},
        )
        manifest_raw = recovery._canonical(manifest)
        request["docker_manifest_sha256"] = recovery._sha256(manifest_raw)
        request = recovery.validate_request(request)
        request_raw = recovery._canonical(request)
        prepared = {
            "schema": "fullmag.docker-container-recovery-transition.v1",
            "state": "prepared-before-removal",
            "request_id": authorization["request_id"],
            "old_container_ids": [backend_id, frontend_id],
            "old_image_id": image,
            "request_sha256": recovery._sha256(request_raw),
            "manifest_sha256": recovery._sha256(manifest_raw),
            "stop_journal_sha256": authorization["stop_journal_sha256"],
        }
        prepared_raw = recovery._canonical(prepared)
        records = {
            "prepared.json": (prepared, prepared_raw),
            "absence.json": (None, None),
            "request.json": (request, request_raw),
            "manifest.json": (manifest, manifest_raw),
        }

        class Control:
            pass

        Control.project = project

        def control_json(_control, relative, *, optional=False):
            item = records[relative.rsplit("/", 1)[-1]]
            return item

        def docker_inspect(*args, **kwargs):
            identifier = args[1]
            if identifier in {backend_id, frontend_id}:
                return SimpleNamespace(
                    returncode=1, stdout=b"", stderr=b"Error: no such object: " + identifier.encode()
                )
            raise AssertionError(f"unexpected Docker call: {args}")

        with patch.object(recovery, "_control_json", side_effect=control_json), patch.object(
            recovery, "docker_capture", side_effect=docker_inspect
        ) as capture:
            transition = recovery._load_recovery_transition(Control(), authorization, project)

        self.assertIsNotNone(transition)
        self.assertIsNone(transition["absence"])
        self.assertEqual(transition["present"], {})
        self.assertEqual(transition["network_name"], "fullmag-private")
        self.assertEqual(transition["prepared_sha"], recovery._sha256(prepared_raw))
        inspected = [call.args[0:3] for call in capture.call_args_list]
        self.assertEqual(len(inspected), 2)

    def test_teardown_after_requires_an_actual_exited_namespace(self):
        pin = {"device_requests_sha256": "a" * 64}
        container = {"HostConfig": {"PidMode": ""}, "State": {
            "Status": "exited", "Running": False, "Pid": 0,
            "FinishedAt": "2026-10-19T09:50:20Z"}}
        observed = recovery._container_observation(container, pin, after=True)
        self.assertEqual(observed["finished_at"], container["State"]["FinishedAt"])
        for status, pid in (("created", 0), ("exited", None), ("running", 42)):
            with self.subTest(status=status, pid=pid):
                container["State"].update(Status=status, Pid=pid)
                with self.assertRaises(recovery.ContainerRecoveryError):
                    recovery._container_observation(container, pin, after=True)


if __name__ == "__main__":
    unittest.main()
