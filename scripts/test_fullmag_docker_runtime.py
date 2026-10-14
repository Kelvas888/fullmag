"""Source-only checks; no Rust/native test compilation or Docker mutation."""
import importlib.util
import json
import tempfile
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import nullcontext

import fullmag_docker_runtime as runtime
import run_managed_browser as managed


class DockerRuntimeContract(unittest.TestCase):
    def test_workspace_uses_one_loopback_port_and_explicit_gpu(self):
        service = runtime.compose_spec("sha256:" + "a" * 64, Path("/state-host"), 3197)["services"]["fullmag"]
        self.assertEqual(service["ports"], ["127.0.0.1:3197:8081"])
        self.assertEqual(service["gpus"], "all")
        self.assertTrue(service["read_only"])
        self.assertEqual([m["target"] for m in service["volumes"]], ["/state"])

    def test_windows_certificate_is_read_only_and_profile_is_explicit(self):
        service = runtime.compose_spec("sha256:" + "a" * 64, Path("C:/owned/state"), 3197,
                                       Path("C:/owned/host.json"))["services"]["fullmag"]
        self.assertEqual(service["environment"]["FULLMAG_SESSION_STORAGE_PROFILE"], "windows-folder-v1")
        self.assertTrue(service["volumes"][1]["read_only"])
        self.assertEqual(service["volumes"][1]["target"], "/run/fullmag/windows-folder-host.json")

    @unittest.skipIf(os.name == "nt", "Guest probes require Linux no-follow and flock")
    def test_guest_probes_require_restart_before_grant_and_reject_junction(self):
        import hashlib
        import uuid
        path = Path(__file__).resolve().parents[1] / "docker/all-in-one/windows_folder_probe.py"
        spec = importlib.util.spec_from_file_location("windows_folder_probe_test", path)
        guest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guest)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / ".windows-folder-probe"
            directory.mkdir()
            target = directory / "junction-target"
            target.mkdir()
            (directory / "host-junction").symlink_to(target, target_is_directory=True)
            image = "sha256:" + "a" * 64
            owner = str(uuid.uuid4())
            host = {"schema": "fullmag.windows-folder-host.v1", "storage_profile": "windows-folder-v1",
                    "role": "session", "owner_scope": "docker-desktop-linux", "host_root_no_reparse": True,
                    "host_drive_type": 3, "host_filesystem": "NTFS", "image_id": image,
                    "owner_token": owner, "restart_verified": False,
                    "restart_expected_sha256": hashlib.sha256((owner + ":" + image).encode()).hexdigest()}
            certificate = root / "host.json"
            marker = root / ".fullmag-windows-folder-owner.json"
            certificate.write_text(json.dumps(host))
            marker.write_text(json.dumps(host))
            with patch.object(guest, "ROOT", root), patch.object(guest, "HOST", certificate), \
                    patch.dict(os.environ, {"FULLMAG_RUNTIME_IMAGE_ID": image}):
                first = guest.run(False)
                self.assertFalse(first["checks"]["restart_readback"])
                with self.assertRaisesRegex(RuntimeError, "Native host has not confirmed"):
                    guest.run(True)
                self.assertFalse((root / ".fullmag-windows-folder-grant.json").exists())
                restart = guest.run(False)
                self.assertTrue(all(restart["checks"].values()))
                host["restart_verified"] = True
                certificate.write_text(json.dumps(host))
                marker.write_text(json.dumps(host))
                grant = guest.run(True)
                self.assertTrue(all(grant["checks"].values()))
                self.assertEqual(grant["host_attestation_sha256"], hashlib.sha256(certificate.read_bytes()).hexdigest())
                self.assertTrue((root / ".fullmag-windows-folder-grant.json").is_file())
                (directory / "host-junction").unlink()
                (directory / "host-junction").mkdir()
                with self.assertRaisesRegex(RuntimeError, "Guest did not expose"):
                    guest.run(True)

    def test_rejects_mutable_image_and_invalid_port(self):
        for image, port in (("fullmag:latest", 3197), ("sha256:" + "a" * 64, 80)):
            with self.assertRaises(ValueError):
                runtime.compose_spec(image, Path("/state-host"), port)

    @unittest.skipIf(os.name == "nt", "Bash shell admission is checked on Linux")
    def test_just_shell_admits_quoted_recipe_and_rejects_composite(self):
        repo = Path(__file__).resolve().parents[1]
        recipe = (f'python3 "{repo}/scripts/fullmag_docker_runtime.py" --repo-root "{repo}" '
                  "build-image --job-id '" + "a" * 32 + "' --commit '" + "b" * 40 + "'")
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "python-probe"
            probe.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nprintf "%s\\n" "$@"\n')
            probe.chmod(0o755)
            env = {**os.environ, "FULLMAG_STORAGE_PYTHON": str(probe)}
            command = ["bash", str(repo / "scripts/just_storage_shell.sh")]
            accepted = subprocess.run([*command, recipe], env=env, text=True, capture_output=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertIn("docker-all-gpu", accepted.stdout)
            rejected = subprocess.run([*command, recipe + "; true"], env=env,
                                      text=True, capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("invalid all-in-Docker recipe", rejected.stderr)

    def test_gpu_release_keeps_receipt_profile(self):
        commit = "b" * 40
        context = {"job_id": "a" * 32, "source_digest": "c" * 64,
                   "profile": "fem-gpu-release", "image_digest": "sha256:" + "d" * 64,
                   "native_source_identity": {"head_commit_full": commit,
                                              "source_snapshot_dirty": False}}
        journal = {**context, "phase": "terminal", "state": "succeeded", "exit_code": 0,
                   "trusted_hashes": {name: "e" * 64 for name in
                                      ("context.json", "build_entrypoint.py", "worker_entrypoint.py")}}
        with patch.object(managed, "read_json", side_effect=[journal, context]), \
                patch.object(managed, "digest", return_value="e" * 64), \
                patch.object(managed, "validate_build_receipt", return_value={}) as validate:
            managed.validate_managed_build(Path(tempfile.gettempdir()).resolve() / context["job_id"], commit,
                                           expected_profile="fem-gpu-release")
            self.assertEqual(validate.call_args.args[1]["profile"], "fem-gpu-release")

    def test_default_cpu_validator_rejects_gpu_release(self):
        with patch.object(managed, "read_json", side_effect=[
            {"phase": "terminal", "state": "succeeded", "exit_code": 0,
             "profile": "fem-gpu-release"}, {}]):
            with self.assertRaisesRegex(ValueError, "terminal and successful"):
                managed.validate_managed_build(Path(tempfile.gettempdir()).resolve() / "job", "b" * 40)

    def test_submission_uses_gpu_queue_and_independent_source_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            layout = {"storage_root": str(root), "runs_root": str(root / "runs" / "test-worktree"),
                      "worktree_id": "test-worktree", "repo_root": str(root / "repo")}
            commit = "b" * 40
            manifest = {"resolved_commit": commit, "source_digest": "c" * 64}
            with patch.object(runtime.storage, "resolve_layout", return_value=layout), \
                    patch.object(runtime, "read_json", return_value={"worktree_id": layout["worktree_id"], "repo_root": layout["repo_root"]}), \
                    patch.object(runtime.storage, "initialize"), \
                    patch.object(runtime.storage, "build_lock", return_value=nullcontext()), \
                    patch("local_runner.build_executor.configured_build"), \
                    patch("local_runner.build_source.native_identity", return_value={}), \
                    patch("local_runner.build_source.bind_identity", return_value={}), \
                    patch("local_runner.source.capture_source", return_value=manifest) as capture, \
                    patch("local_runner.container_client.request", side_effect=[
                        {"accepting_jobs": True, "allowed_profiles": ["fem-gpu-release"]},
                        {"job_id": "d" * 32}]) as request, \
                    patch("builtins.print"):
                runtime.submit_build(root / "repo", commit)
                self.assertIsNone(capture.call_args.kwargs["content_store"])
                self.assertEqual(capture.call_args.kwargs["ref"], commit)
                payload = request.call_args.kwargs["payload"]
                self.assertEqual(payload["profile"], "fem-gpu-release")
                self.assertEqual(payload["operation"], "build")
                self.assertEqual(payload["source_digest"], manifest["source_digest"])
                self.assertEqual(payload["payload"]["source_mode"], "commit")
                self.assertEqual(payload["payload"]["capture_id"], payload["request_key"])
                self.assertEqual(payload["payload"]["capsule_relative"],
                                 "runs/test-worktree/" + payload["request_key"] + "/source")
                self.assertEqual(request.call_args_list[0].kwargs["method"], "GET")
                self.assertEqual(request.call_args_list[1].kwargs["method"], "POST")
                request.reset_mock()
                request.side_effect = [{"accepting_jobs": True, "allowed_profiles": ["fem-gpu-release"]},
                                       TimeoutError("response lost after POST")]
                with self.assertRaises(TimeoutError):
                    runtime.submit_build(root / "repo", commit)
                receipts = [json.loads(path.read_text()) for path in (root / "runs/test-worktree").glob("*/submission.json")]
                pending = [value for value in receipts if value["state"] == "submission_unconfirmed"]
                self.assertEqual(len(pending), 1)
                self.assertEqual(pending[0]["request_key"], pending[0]["submission"]["request_key"])
                self.assertEqual(pending[0]["capture_id"], pending[0]["request_key"])
                self.assertEqual(request.call_count, 2)

    def test_entrypoint_rejects_windows_9p_before_cuda_or_writes(self):
        path = Path(__file__).resolve().parents[1] / "docker/all-in-one/entrypoint.py"
        spec = importlib.util.spec_from_file_location("all_docker_entrypoint", path)
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        with patch.object(entry.subprocess, "check_output", return_value="1021997\n"), \
                patch.object(entry.ctypes, "CDLL") as load, \
                patch.object(entry.Path, "mkdir") as mkdir:
            with self.assertRaisesRegex(RuntimeError, "Unsupported durable session filesystem"):
                entry.preflight()
            load.assert_not_called()
            mkdir.assert_not_called()


if __name__ == "__main__":
    unittest.main()
