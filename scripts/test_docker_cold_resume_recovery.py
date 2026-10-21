"""Docker-free checks for explicit cold namespace recovery authorization."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docker_volume_container_recovery as recovery


class ColdRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.attempt = "a" * 32
        self.verified = "iteration/attempts/" + "b" * 32 + "/terminal.json"
        self.image = "sha256:" + "c" * 64
        self.owner = {
            "schema_version": "runtime_service_owner.v1", "state": "ready",
            "owner_token": "dc79acbb-57a9-4fba-abf8-70dc4b6a1f93",
            "process_start_token": "e086e28c-a1ef-4903-9aad-4b324c24d441",
            "target_id": "docker-all", "protocol": "tcp", "pid": 165, "host": "old-backend",
            "build_commit": "d" * 40, "build_snapshot": "e" * 64,
            "children": [{"role": "compute", "pid": 166, "status": "ready"},
                         {"role": "preparation", "pid": 167, "status": "ready"}],
        }
        self.process = {"schema": "fullmag.docker-process-tree.v1", "state": "failed_outcome_retained",
                        "api_pid": 2993, "api_exit_code": -15,
                        "error": "runtime CLI failed: [fullmag] version: new-build\nError: native service target/build mismatch; attach refused"}
        self.compose = {"name": "fullmag-test", "services": {"backend": {"image": self.image}}}
        self.compose_sha = recovery._sha256(recovery._canonical(self.compose))
        self.config = {"target_id": "docker-all", "store_root": "/state/runs/docker-all/session-store"}
        self.launch = {"schema_version": "runtime_service_launch.v1", "state": "ready", "pid": 165}
        self.store = {"store_root_sha256": "1" * 64, "ledger_root_sha256": "2" * 64,
                      "ledger_snapshot_sha256": "3" * 64, "run_records": []}
        def container(service, identity):
            return {"Id": identity * 64, "Image": self.image,
                    "Config": {"Hostname": "old-backend", "Labels": {
                        "com.docker.compose.project": "fullmag-test", "com.docker.compose.service": service}},
                    "HostConfig": {"PidMode": "", "DeviceRequests": []},
                    "State": {"Status": "exited", "Running": False, "Pid": 0, "FinishedAt": "2026-10-20T12:00:00Z"}}
        self.backend, self.frontend = container("backend", "4"), container("frontend", "5")
        self.stop = "verification/stop-failed-" + self.backend["Id"] + ".json"
        self.ready_path = "runtime-control/runtime-services/docker-client-" + self.owner["owner_token"] + ".json"
        self.records = {}
        self.save("development/attempts/" + self.attempt + "/terminal.json", {
            "phase": "development", "attempt": self.attempt, "inputs": {"source_root": "/selected/source"}})
        self.save("development/attempts/" + self.attempt + "/compose.json", self.compose)
        self.save(self.verified, {"schema": "fullmag.docker-build-operation.v1", "state": "succeeded",
            "phase": "iteration", "attempt": "b" * 32, "config_sha256": self.compose_sha, "compose_project": "fullmag-test",
            "backend_container": self.backend["Id"], "frontend_container": self.frontend["Id"],
            "source_commit": self.owner["build_commit"], "source_snapshot_sha256": self.owner["build_snapshot"]})
        self.save("runtime-control/runtime-services/OWNER.json", self.owner)
        self.save(self.ready_path, self.owner)
        self.save("runtime-control/runtime-services/LAUNCH.json", self.launch)
        self.save("runtime-control/runtime-service/docker-all.json", self.config)
        self.save("runtime-control/runtime-service/process-tree.json", self.process)
        self.save(self.stop, {"schema": "fullmag.stop-failed-admission.v1", "state": "stopped-confirmed",
            "container_id": self.backend["Id"], "image_id": self.image, "failure_receipt": {
                "receipt": self.process, "sha256": recovery._sha256(self.records["runtime-control/runtime-service/process-tree.json"]),
                "api_pid_exists": False}})
        @contextmanager
        def operation(phase, inputs):
            yield {"receipt": {}, "root": "cold-recovery-authorization/attempts/" + "f" * 32}
        self.control = SimpleNamespace(project="fullmag-test", volume="control-volume", operation=operation,
                                       write_bytes=lambda path, raw: self.records.__setitem__(path, raw))

    def save(self, path, value):
        self.records[path] = recovery._canonical(value)

    def read(self, control, path, *, optional=False):
        raw = self.records.get(path)
        if raw is None:
            if optional:
                return None, None
            raise recovery.ContainerRecoveryError("missing test proof: " + path)
        return json.loads(raw), raw

    def prepare(self):
        with patch.object(recovery, "_control_json", side_effect=self.read), \
             patch.object(recovery, "_inspect_pair", return_value=(self.backend, self.frontend)), \
             patch.object(recovery, "_ledger_and_store_snapshot", return_value=self.store), \
             patch.object(recovery, "docker_capture") as docker:
            result = recovery.prepare_cold_resume_recovery(self.control, attempt=self.attempt,
                source_root="/selected/source", compose_config_sha256=self.compose_sha,
                verified_receipt_path=self.verified, stop_failed_path=self.stop)
        docker.assert_not_called()
        return result

    def evidence(self, result):
        authorization = recovery.validate_operator_authorization(json.loads(self.records[result["recovery_authorization"]]))
        journal = json.loads(self.records[authorization["stop_journal_path"]])
        return authorization, journal

    def test_prepare_publishes_honest_distinct_journal_and_existing_native_request(self):
        result = self.prepare()
        authorization, journal = self.evidence(result)
        self.assertEqual(journal["schema"], recovery.COLD_JOURNAL_SCHEMA)
        self.assertEqual(journal["state"], recovery.COLD_JOURNAL_STATE)
        self.assertNotIn("drained_process_receipt", journal)
        self.assertNotIn("proof_recheck", journal)
        self.assertEqual(result["recovery_authorization_sha256"], recovery._sha256(self.records[result["recovery_authorization"]]))
        recovery._validate_pre_admission_stop_journal(journal, authorization, self.attempt)
        with patch.object(recovery, "_control_json", side_effect=self.read):
            request = recovery._build_request(authorization, owner=self.owner,
                owner_sha256=authorization["owner_sha256"], launch_sha256=authorization["launch_sha256"],
                config=self.config, control=self.control,
                device_release={"resource_id": "runtime-gpu", "mapping_sha256": "6" * 64, "mapping_detached": True},
                config_sha256=authorization["config_sha256"], **{key: self.store[key] for key in
                    ("store_root_sha256", "ledger_root_sha256", "ledger_snapshot_sha256")},
                docker_engine_id_sha256="7" * 64, manifest_sha256="8" * 64, containers=journal["containers"])
        self.assertEqual(request["expected_owner"], self.owner)
        self.assertEqual(request["prior_ready_owner_proof_sha256"], recovery._sha256(self.records[authorization["stop_journal_path"]]))
        spec = importlib.util.spec_from_file_location("cold_recovery_guest", Path(__file__).parents[1] / "docker/all-in-one/runtime_service.py")
        guest = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = guest
        spec.loader.exec_module(guest)
        _, expected = guest._container_recovery_request_sources(request, "cold recovery test")
        self.assertEqual(expected, self.owner)

    def test_prepare_refuses_missing_ready_pin_or_historical_identity(self):
        original = dict(self.records)
        for path, value in [(self.ready_path, None), (self.verified, {"state": "succeeded"}),
                            (self.stop, {"schema": "fullmag.stop-failed-admission.v1", "state": "stopping-confirmed-failed-supervisor"})]:
            with self.subTest(path=path):
                self.records = dict(original)
                if value is None:
                    self.records.pop(path)
                else:
                    self.save(path, value)
                with self.assertRaises(recovery.ContainerRecoveryError):
                    self.prepare()
                self.assertFalse(any(path.endswith("operator-authorization.json") for path in self.records))

    def test_cold_failure_refuses_native_process_owner_wrong_failure_or_unreaped_api(self):
        for changes in ({"runtime_pid": 165}, {"service_owner": self.owner}, {"api_exit_code": None},
                        {"error": "runtime CLI failed: Error: unknown"}, {"state": "shutdown_unknown"},
                        {"startup_activation": {}}):
            with self.subTest(changes=changes), self.assertRaises(recovery.ContainerRecoveryError):
                recovery._validate_cold_failure({**self.process, **changes})
        recovery._validate_cold_failure(self.process)

    def test_post_stop_terminal_transition_keeps_distinct_pre_and_post_raw_hashes(self):
        pre_sha = recovery._sha256(self.records["runtime-control/runtime-service/process-tree.json"])
        self.process = {**self.process, "state": "shutdown_unknown",
                        "shutdown_error": "no pinned runtime service owner was available for authenticated drain"}
        self.save("runtime-control/runtime-service/process-tree.json", self.process)
        result = self.prepare()
        authorization, journal = self.evidence(result)
        self.assertEqual(journal["pre_stop_process_receipt_sha256"], pre_sha)
        self.assertNotEqual(authorization["process_receipt_sha256"], pre_sha)
        self.assertEqual(authorization["process_receipt_sha256"],
                         recovery._sha256(self.records["runtime-control/runtime-service/process-tree.json"]))
        self.process["api_pid"] += 1
        self.save("runtime-control/runtime-service/process-tree.json", self.process)
        with self.assertRaisesRegex(recovery.ContainerRecoveryError, "managed failed stop"):
            self.prepare()

    def test_cold_evidence_rechecks_raw_cas_and_stopped_namespace(self):
        result = self.prepare()
        authorization, journal = self.evidence(result)
        def validate():
            with patch.object(recovery, "_control_json", side_effect=self.read):
                recovery._validate_cold_evidence(self.control, journal, authorization, self.backend,
                    self.frontend, self.owner, self.launch, self.config, self.process, self.store)
        validate()
        for path in (self.ready_path, self.verified, self.stop):
            with self.subTest(path=path):
                raw = self.records[path]
                self.records[path] = raw + b"\n"
                with self.assertRaisesRegex(recovery.ContainerRecoveryError, "changed"):
                    validate()
                self.records[path] = raw
        self.backend["State"]["FinishedAt"] = "2026-10-20T13:00:00Z"
        with self.assertRaisesRegex(recovery.ContainerRecoveryError, "namespace proof changed"):
            validate()

    def test_prepare_refuses_live_or_host_pid_namespace(self):
        for field, value in (("PidMode", "host"),):
            self.backend["HostConfig"][field] = value
            with self.assertRaises(recovery.ContainerRecoveryError):
                self.prepare()
        self.backend["HostConfig"]["PidMode"] = ""
        self.frontend["State"].update(Running=True, Pid=123, Status="running")
        with self.assertRaises(recovery.ContainerRecoveryError):
            self.prepare()

    def test_prepare_refuses_owner_launch_application_or_reaped_stop_changes(self):
        original = dict(self.records)
        cases = [(self.ready_path, {**self.owner, "build_commit": "f" * 40}),
                 ("runtime-control/runtime-services/LAUNCH.json", {**self.launch, "pid": 999}),
                 ("runtime-control/runtime-service/docker-all.json", {**self.config, "target_id": "other"})]
        for path, value in cases:
            with self.subTest(path=path):
                self.records = dict(original)
                self.save(path, value)
                with self.assertRaises(recovery.ContainerRecoveryError):
                    self.prepare()


if __name__ == "__main__":
    unittest.main()
