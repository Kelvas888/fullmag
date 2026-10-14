"""Source-only checks; no Rust/native test compilation or Docker mutation."""
import importlib.util
import tempfile
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import fullmag_docker_runtime as runtime
import run_managed_browser as managed


class DockerRuntimeContract(unittest.TestCase):
    def test_workspace_uses_one_loopback_port_and_explicit_gpu(self):
        service = runtime.compose_spec("sha256:" + "a" * 64, Path("/state-host"), 3197)["services"]["fullmag"]
        self.assertEqual(service["ports"], ["127.0.0.1:3197:8081"])
        self.assertEqual(service["gpus"], "all")
        self.assertTrue(service["read_only"])
        self.assertEqual([m["target"] for m in service["volumes"]], ["/state"])

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
