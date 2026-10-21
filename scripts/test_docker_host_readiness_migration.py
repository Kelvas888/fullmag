"""Interpreted checks for explicit, incarnation-bound host readiness migration."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import docker_dev
import docker_host_readiness_migration as migration
import docker_volume_dev as volume
import docker_worker_cgroup as cgroup
from docker_build_control import BuildControlError


class HostReadinessMigrationTests(unittest.TestCase):
    def setUp(self):
        self.backend = "a" * 64
        self.image = "sha256:" + "b" * 64
        self.project = "fullmag-master"
        self.intent = {"request_id": "11111111-1111-4111-8111-111111111111", "expected_generation": "c" * 64}
        self.request = {"schema": "fullmag.worker-cgroup-request.v1", "nonce": "d" * 32,
                        "compose_project": self.project, "container_id": self.backend,
                        "boot_id": "22222222-2222-4222-8222-222222222222", "pid": 17,
                        "process_start_token": "12345"}
        self.control = Mock(project=self.project)
        self.control.read.return_value = None
        self.operation = {"root": "attempts/test", "receipt": {"attempt": "e" * 32}}
        self.raw = b'{ "state": "succeeded" }\n'

    def test_cli_dispatches_explicit_migration_and_preserves_pins(self):
        with patch.object(volume, "migrate_worker_cpu_quota") as run:
            result = docker_dev.main(["migrate-worker-cpu-quota-volume", "--attempt", "a" * 32,
                "--config-sha256", "b" * 64, "--source-root", "/owned/checkout", "--port", "3198",
                "--from-readiness-sha256", self.intent["expected_generation"],
                "--request-id", self.intent["request_id"]])
        self.assertEqual(result, 0)
        args = run.call_args.args[0]
        self.assertEqual(args.from_readiness_sha256, self.intent["expected_generation"])
        self.assertEqual(args.request_id, self.intent["request_id"])
        self.assertEqual(args.attempt, "a" * 32)
        self.assertEqual(args.config_sha256, "b" * 64)
        self.assertEqual(args.source_root, Path("/owned/checkout"))
        self.assertEqual(args.port, 3198)

    def test_action_validates_before_retained_restart(self):
        args = SimpleNamespace(from_readiness_sha256=self.intent["expected_generation"],
                               request_id=self.intent["request_id"])
        with patch.object(volume, "_retained_operation") as retained:
            volume.migrate_worker_cpu_quota(args)
        retained.assert_called_once_with(args, recreate_services=False)
        self.assertTrue(args.restart_backend)
        self.assertEqual(args.worker_cpu_quota_migration, self.intent)
        for key, value in (("from_readiness_sha256", "wrong"), ("request_id", "wrong")):
            bad = SimpleNamespace(from_readiness_sha256=self.intent["expected_generation"],
                                  request_id=self.intent["request_id"])
            setattr(bad, key, value)
            with self.subTest(key=key), patch.object(volume, "_retained_operation") as retained:
                with self.assertRaises(BuildControlError):
                    volume.migrate_worker_cpu_quota(bad)
                retained.assert_not_called()

    def publish(self):
        return migration.publish_request(self.control, self.operation, self.intent, self.request,
                                         self.backend, self.image)

    def test_publication_hashes_raw_package_and_records_fixed_location(self):
        with patch.object(migration, "docker_capture", return_value=SimpleNamespace(stdout=self.raw)):
            self.publish()
        relative, request = self.control.write.call_args.args
        self.assertEqual(relative, migration.REQUEST_RELATIVE)
        self.assertEqual(request["package_receipt_sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(request["cgroup_nonce"], self.request["nonce"])
        self.assertEqual(request["schema"], "fullmag.worker-cpu-quota-migration-request.v1")
        self.assertEqual(self.operation["receipt"]["worker_cpu_quota_migration_request"], request)
        self.assertEqual(self.operation["receipt"]["worker_cpu_quota_migration_request_path"], relative)

    def test_different_existing_request_is_never_overwritten(self):
        self.control.read.return_value = {"request_id": "other"}
        with patch.object(migration, "docker_capture", return_value=SimpleNamespace(stdout=self.raw)):
            with self.assertRaisesRegex(BuildControlError, "existing"):
                self.publish()
        self.control.write.assert_not_called()

    def test_identical_existing_request_is_retained_without_rewrite(self):
        with patch.object(migration, "docker_capture", return_value=SimpleNamespace(stdout=self.raw)):
            self.publish()
            request = self.control.write.call_args.args[1]
            self.control.write.reset_mock()
            self.control.read.return_value = request
            self.publish()
        self.control.write.assert_not_called()

    def test_migration_requires_configured_delegation_profile(self):
        document = {"services": {"backend": {"environment": {}}}}
        callback = Mock()
        with patch.object(cgroup, "docker_text") as capture:
            with self.assertRaisesRegex(BuildControlError, "requires a worker cgroup"):
                cgroup.ensure_delegation(self.control, self.operation, document, self.backend,
                                        self.image, Path("."), before_ready=callback)
        capture.assert_not_called()
        callback.assert_not_called()

    def test_malformed_live_identity_is_rejected_before_io(self):
        for key, value in (("nonce", "wrong"), ("boot_id", "wrong"), ("pid", True),
                           ("process_start_token", "wrong"), ("container_id", None)):
            with self.subTest(key=key), patch.object(migration, "docker_capture") as capture:
                original = dict(self.request)
                self.request[key] = value
                with self.assertRaises(BuildControlError):
                    self.publish()
                self.request = original
                capture.assert_not_called()
        self.control.write.assert_not_called()

    def test_callback_precedes_helper_and_rejects_ready_gate(self):
        observed = {"Id": self.backend, "Image": self.image,
            "Config": {"Labels": {"com.docker.compose.project": self.project,
                                  "com.docker.compose.service": "backend"}, "User": "65532:65532"},
            "HostConfig": {"Privileged": False}, "State": {"Running": True, "Pid": 99}}
        document = {"services": {"backend": {"environment": {"FULLMAG_WORKER_CGROUP_PROFILE": cgroup.PROFILE}}}}
        ready = {**self.request, "schema": "fullmag.worker-cgroup-ready.v1", "image_id": self.image,
                 "state": "ready", "root": cgroup.ROOT}
        for reused in (False, "container", "operation"):
            operation = {"root": "attempts/test", "receipt": {"attempt": "e" * 32}}
            if reused == "operation":
                operation["receipt"]["worker_cgroup"] = ready
            events = []
            def before(request):
                self.assertEqual(request, self.request)
                events.append("request")
            def helper(*args, **kwargs):
                events.append("helper")
                raise RuntimeError("helper boundary")
            answers = [json.dumps([observed]), json.dumps(self.request),
                       json.dumps(ready if reused == "container" else {})]
            with self.subTest(reused=reused), patch.object(cgroup, "docker_text", side_effect=answers), \
                    patch.object(cgroup, "compose_capture", side_effect=helper):
                with self.assertRaisesRegex(BuildControlError if reused else RuntimeError,
                                            "already" if reused else "helper boundary"):
                    cgroup.ensure_delegation(self.control, operation, document, self.backend, self.image,
                                            Path(__file__).resolve().parents[1], before_ready=before)
            self.assertEqual(events, [] if reused else ["request", "helper"])


if __name__ == "__main__":
    unittest.main()
