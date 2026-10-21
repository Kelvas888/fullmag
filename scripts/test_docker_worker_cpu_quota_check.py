"""Scoped native-check orchestration tests; Cargo and Docker are mocked."""
from contextlib import ExitStack, contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import docker_dev
import docker_worker_cpu_quota_check as host
from docker_build_control import BuildControlError, canonical
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker" / "all-in-one"))
import backend_dev as backend
import worker_cgroup_gate


class WorkerCpuQuotaCheckTests(unittest.TestCase):
    def setUp(self):
        self.request = {"schema": "fullmag.worker-cpu-quota-check-request.v1",
            "request_id": "11111111-1111-4111-8111-111111111111", "compose_project": "fullmag-master",
            "container_id": "a" * 64, "image_id": "sha256:" + "b" * 64}

    def test_backend_runs_fixed_test_once_and_keeps_evidence(self):
        for code, summary in ((0, b"test result: ok. 1 passed; 0 failed;"),
                              (0, b"test result: ok. 0 passed; 0 failed;"), (1, b"test failed")):
            with self.subTest(code=code, summary=summary), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                control = root / "control"
                check = control / host.ROOT
                attempt = check / self.request["request_id"]
                attempt.mkdir(parents=True)
                raw = canonical(self.request) + b"\n"
                (check / "request.json").write_bytes(raw)
                (attempt / "request.json").write_bytes(raw)
                args = SimpleNamespace(manifest=root / "manifest", source_root=root / "source", git_common_root=root / "git")
                def execute(command, **kwargs):
                    self.assertEqual(command, ["cargo", "test", "--locked", "--profile", "backend-dev",
                        "-p", "fullmag-session", "--lib",
                        "host_resource_ledger::tests::worker_cpu_quota_readiness_migration_is_narrow_and_fenced",
                        "--", "--exact"])
                    self.assertEqual(kwargs["env"]["TMPDIR"], str(root / "build" / "worker-cpu-quota-check" / self.request["request_id"]))
                    kwargs["stdout"].write(summary)
                    return SimpleNamespace(returncode=code)
                with patch.object(backend, "CONTROL_ROOT", control), \
                        patch.object(worker_cgroup_gate, "_container_id_from_mountinfo", return_value=self.request["container_id"]), \
                        patch.dict(os.environ, FULLMAG_RUNTIME_IMAGE_ID=self.request["image_id"], FULLMAG_COMPOSE_PROJECT="fullmag-master"), \
                        patch.object(backend, "_materialize_source", return_value=(root, {}, {"source_snapshot_sha256": "c" * 64}, "d" * 64, None, "live")), \
                        patch.object(backend, "_build_environment", return_value={}), \
                        patch.object(backend.subprocess, "run", side_effect=execute) as run:
                    result = backend._verify_worker_cpu_quota_requested(args, root / "build", 2)
                    self.assertEqual(result, 0 if b"1 passed" in summary else code or 2)
                    self.assertIsNone(backend._verify_worker_cpu_quota_requested(args, root / "build", 2))
                    run.assert_called_once()
                receipt = json.loads((attempt / "result.json").read_bytes())
                self.assertEqual(receipt["request_sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(receipt["log_sha256"], hashlib.sha256(summary).hexdigest())
                self.assertTrue((attempt / "claim.json").is_file())

    def test_backend_rejects_unknown_claim_and_wrong_container(self):
        for claimed in (False, True):
            with self.subTest(claimed=claimed), tempfile.TemporaryDirectory() as directory:
                control = Path(directory)
                check = control / host.ROOT
                attempt = check / self.request["request_id"]
                attempt.mkdir(parents=True)
                raw = canonical(self.request) + b"\n"
                (check / "request.json").write_bytes(raw)
                (attempt / "request.json").write_bytes(raw)
                if claimed:
                    (attempt / "claim.json").write_text("{}")
                with patch.object(backend, "CONTROL_ROOT", control), \
                        patch.object(worker_cgroup_gate, "_container_id_from_mountinfo", return_value="other"), \
                        patch.object(backend, "_materialize_source") as materialize:
                    with self.assertRaisesRegex(backend.BackendBuildError, "unknown" if claimed else "another backend"):
                        backend._verify_worker_cpu_quota_requested(SimpleNamespace(), control / "build", 2)
                    materialize.assert_not_called()

    def test_host_refuses_running_backend_without_docker(self):
        args = SimpleNamespace(request_id=self.request["request_id"])
        with patch.object(host, "docker_capture") as capture:
            with self.assertRaisesRegex(BuildControlError, "stopped"):
                host.run(Mock(), args, {"State": {"Running": True}}, self.request["image_id"])
            capture.assert_not_called()

    def test_host_does_not_retry_unknown_result(self):
        control = Mock(project="fullmag-master")
        control.operation.return_value = nullcontext({"receipt": {}})
        control.read.side_effect = [self.request, {"state": "unknown"}]
        args = SimpleNamespace(request_id="33333333-3333-4333-8333-333333333333", attempt="a" * 32,
                               config_sha256="c" * 64)
        with patch.object(host, "docker_capture") as capture:
            with self.assertRaisesRegex(BuildControlError, "unknown"):
                host.run(control, args, {"Id": "a" * 64, "State": {"Running": False}}, self.request["image_id"])
        capture.assert_not_called()
        control.write.assert_not_called()

    def test_host_starts_only_backend_and_validates_terminal_receipt(self):
        control = Mock(project="fullmag-master")
        operation = {"receipt": {}}
        control.operation.return_value = nullcontext(operation)
        result = {"schema": "fullmag.worker-cpu-quota-check-result.v1",
            "request_sha256": hashlib.sha256(canonical(self.request) + b"\n").hexdigest(),
            "container_id": self.request["container_id"], "image_id": self.request["image_id"],
            "state": "succeeded", "exit_code": 0}
        control.read.side_effect = [None, None, result]
        stopped = {"Id": self.request["container_id"], "Image": self.request["image_id"],
                   "State": {"Running": False, "StartedAt": "old", "ExitCode": 0, "OOMKilled": False}}
        args = SimpleNamespace(request_id=self.request["request_id"], attempt="a" * 32, config_sha256="c" * 64)
        finished = {**stopped, "State": {**stopped["State"], "StartedAt": "new"}}
        with patch.object(host, "docker_capture", side_effect=[SimpleNamespace(stdout=json.dumps([stopped]).encode()),
                SimpleNamespace(), SimpleNamespace(stdout=json.dumps([finished]).encode())]) as capture:
            host.run(control, args, stopped, self.request["image_id"])
        self.assertEqual([call.args[0] for call in capture.call_args_list], ["inspect", "start", "inspect"])
        self.assertEqual(capture.call_args_list[1].args, ("start", self.request["container_id"]))
        self.assertEqual(operation["receipt"]["state"], "succeeded")

    def test_start_verification_holds_build_lock_and_never_enters_api(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            events = []
            @contextmanager
            def locked(_root):
                events.append("locked")
                yield
                events.append("unlocked")
            def verify(args, build_root, jobs):
                self.assertEqual(events, ["locked", "captured"])
                self.assertEqual(args.manifest, root / "manifest")
                return 0
            for name, value in (("_validate_start_output", None), ("_ensure_package_development_root", root),
                                ("_package_children", []), ("_reject_partial_package_candidates", None),
                                ("_recover_pending_package_rotation", None), ("_backend_cache_receipt", None),
                                ("_prune_failed_make_logs", None), ("_toolchain_identity", ("image", {}))):
                stack.enter_context(patch.object(backend, name, return_value=value))
            stack.enter_context(patch.object(backend, "_runtime_build_lock", side_effect=locked))
            stack.enter_context(patch.object(backend, "_capture_start_manifest",
                side_effect=lambda *args: (events.append("captured"), root / "manifest")[1]))
            stack.enter_context(patch.object(backend, "_verify_worker_cpu_quota_requested", side_effect=verify))
            serve = stack.enter_context(patch.object(backend, "_serve"))
            prepare = stack.enter_context(patch.object(backend, "_prepare_locked"))
            args = SimpleNamespace(build_root=root, output=root / "package", jobs=2)
            self.assertEqual(backend._start(args), 0)
            self.assertEqual(events, ["locked", "captured", "unlocked"])
            serve.assert_not_called()
            prepare.assert_not_called()

    def test_parser_dispatches_fixed_verification(self):
        with patch("docker_volume_dev.verify_worker_cpu_quota") as verify:
            self.assertEqual(docker_dev.main(["verify-worker-cpu-quota-volume", "--attempt", "a" * 32,
                "--config-sha256", "b" * 64, "--source-root", "/owned/source", "--port", "3198",
                "--request-id", self.request["request_id"]]), 0)
        self.assertEqual(verify.call_args.args[0].request_id, self.request["request_id"])


if __name__ == "__main__":
    unittest.main()
