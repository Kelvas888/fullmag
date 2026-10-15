#!/usr/bin/env python3
"""Interpreted regression checks; no compiler, Docker or GPU required."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import os
import subprocess
import unittest
from unittest.mock import patch

import setup_docker as setup


class SetupDockerChecks(unittest.TestCase):
    def test_linux_volume_checks_actual_filesystem(self):
        for filesystem in ("ext4", "xfs", "btrfs"):
            with self.subTest(filesystem=filesystem), patch.object(setup.storage, "filesystem_type", return_value=filesystem) as detect:
                setup.validate_linux_volume(Path("/home/operator/fullmag_storage"))
                detect.assert_called_once_with(Path("/home/operator/fullmag_storage"))
        for filesystem in ("9p", "drvfs", "cifs", "nfs", "tmpfs", "overlay", "ntfs", ""):
            with self.subTest(filesystem=filesystem), patch.object(setup.storage, "filesystem_type", return_value=filesystem):
                with self.assertRaises(setup.SetupError):
                    setup.validate_linux_volume(Path("/home/operator/fullmag_storage"))

    def test_linux_rejects_windows_and_ephemeral_paths_even_on_local_filesystem(self):
        with patch.object(setup.storage, "filesystem_type", return_value="ext4"):
            for path in ("/mnt/c/fullmag", "/mnt/d/storage", "/tmp/storage", "/run/storage", "/dev/shm/storage"):
                with self.subTest(path=path), self.assertRaises(setup.SetupError):
                    setup.validate_linux_volume(Path(path))

    def test_linux_validates_both_storage_and_source(self):
        with patch.object(setup.os, "name", "posix"), patch.object(setup.sys, "platform", "linux"), patch.object(setup, "validate_linux_volume") as validate:
            setup.validate_host_paths(Path("/home/operator/storage"), Path("/home/operator/repo"))
        self.assertEqual(validate.call_args_list, [unittest.mock.call(Path("/home/operator/storage")), unittest.mock.call(Path("/home/operator/repo"))])

    def test_wsl_launcher_identity(self):
        with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}), patch.object(setup.os, "name", "posix"), patch.object(setup, "probe", return_value={"state": "available"}):
            checks = setup.host_checks()
        self.assertEqual(checks["platform"], "wsl")
        self.assertEqual(checks["application_launcher"], "linux-native-v1")

    def test_linux_check_is_readonly_and_validates_source(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            main = base / "repo"
            main.mkdir()
            (main / "compose.dev.yaml").write_text("services: {}\n")
            original = setup.merge_dotenv(b"", {"FULLMAG_PROJECT_STORAGE_ROOT": str(base / "storage"), "POSTGRES_PASSWORD": "keep", "MINIO_ROOT_USER": "fullmag", "MINIO_ROOT_PASSWORD": "keep"})
            (main / ".env").write_bytes(original)
            context = {"repo": main, "main": main, "project": base, "checkouts": [main]}
            checks = {"platform": "wsl", "docker_os": {"value": "linux"}, **{name: {"state": "available"} for name in ("git", "just", "docker", "compose", "nvidia")}}
            with patch.object(setup, "checkout_context", return_value=context), patch.object(setup, "host_checks", return_value=checks), patch.object(setup, "show_checks"), patch.object(setup, "validate_host_paths") as validate, patch.object(setup.storage, "resolve_layout"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(setup.main(["--check"]), 0)
                validate.assert_called_once_with(base / "storage", main)
            self.assertEqual((main / ".env").read_bytes(), original)
            self.assertFalse((base / "storage").exists())

    def test_wsl_wizard_prints_shell_safe_commands_with_receipt(self):
        context = {"repo": Path("/repo"), "main": Path("/repo")}
        checks = {"platform": "wsl"}
        source = "/home/operator/my repo's $(touch bad)"
        prepared = {"env_path": "/repo/.env", "storage_root": "/storage", "source_root": source, "port": 3297}
        output = io.StringIO()
        with patch.object(setup, "checkout_context", return_value=context), patch.object(setup, "host_checks", return_value=checks), patch.object(setup, "show_checks"), patch.object(setup.sys.stdin, "isatty", return_value=True), patch.object(setup, "plan", return_value=prepared), patch("builtins.input", side_effect=["/storage", "", "", "t"]), patch.object(setup, "apply_configuration", return_value={"settings_path": "/settings"}) as apply, contextlib.redirect_stdout(output):
            self.assertEqual(setup.main([]), 0)
            apply.assert_called_once_with(prepared)
        commands = [setup.shlex.split(line) for line in output.getvalue().splitlines() if line.startswith("  just ")]
        self.assertEqual(commands, [["just", "docker-all-dev-backend-build", source], ["just", "docker-all-dev", "ASSEMBLY_RECEIPT", "3297", source]])
        self.assertIn("docs/guides/docker-wsl.md", output.getvalue())

    def test_windows_paths_still_use_windows_volume_validation(self):
        root, source = Path("/storage"), Path("/repo")
        with patch.object(setup.os, "name", "nt"), patch.object(setup, "validate_windows_volume") as validate:
            setup.validate_host_paths(root, source)
        self.assertEqual(validate.call_args_list, [unittest.mock.call(root), unittest.mock.call(source)])

    def test_literal_paths_roundtrip_through_storage_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = "C:/Fullmag data/$local/#storage"
            (root / ".env").write_bytes(setup.merge_dotenv(b"# preserve\r\nOTHER=secret\r\n",
                {"FULLMAG_PROJECT_STORAGE_ROOT": value}))
            self.assertEqual(setup.storage.storage_dotenv(root)["FULLMAG_PROJECT_STORAGE_ROOT"], value)
            self.assertIn(b"OTHER=secret\r\n", (root / ".env").read_bytes())

    def test_backslashes_are_literal_and_unsafe_values_rejected(self):
        value = "C:" + chr(92) + "storage"
        self.assertEqual(setup.dotenv_values(setup.merge_dotenv(b"", {"ROOT": value}))["ROOT"], value)
        for value in ("bad\npath", "bad'path", "bad\0path"):
            with self.assertRaises(setup.SetupError):
                setup.merge_dotenv(b"", {"ROOT": value})

    def test_duplicate_managed_keys_rejected(self):
        with self.assertRaises(setup.SetupError):
            setup.dotenv_values(b"FULLMAG_PROJECT_STORAGE_ROOT=/one\nFULLMAG_PROJECT_STORAGE_ROOT=/two\n")

    def test_partial_setup_retains_secrets_and_fills_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            main = base / "repo"
            main.mkdir()
            original = b"# operator\nPOSTGRES_PASSWORD='keep-this'\nMINIO_ROOT_PASSWORD=\nEXTRA=keep\n"
            (main / ".env").write_bytes(original)
            context = {"repo": main, "main": main, "project": base, "checkouts": [main]}
            with patch.object(setup, "checkout_context", return_value=context), patch.object(setup, "validate_host_paths"):
                prepared = setup.plan(main, str(base / "storage"), str(main), 3197)
            values = setup.dotenv_values(prepared["configured"])
            self.assertEqual(values["POSTGRES_PASSWORD"], "keep-this")
            self.assertTrue(values["MINIO_ROOT_PASSWORD"])
            self.assertEqual(values["MINIO_ROOT_USER"], "fullmag")
            self.assertIn(b"EXTRA=keep\n", prepared["configured"])
            self.assertEqual((main / ".env").read_bytes(), original)
            self.assertFalse((base / "storage").exists())

    def test_storage_rejects_checkout_unmarked_and_foreign_data(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            main = base / "repo"
            main.mkdir()
            context = {"project": base, "checkouts": [main]}
            with self.assertRaises(setup.SetupError):
                setup.validate_storage_root(str(main / "storage"), context)
            other = base / "data"
            other.mkdir()
            (other / "important").write_text("preserve")
            with self.assertRaises(setup.SetupError):
                setup.validate_storage_root(str(other), context)
            (other / ".fullmag-storage.json").write_text(json.dumps({"schema": "foreign"}))
            with self.assertRaises(setup.SetupError):
                setup.validate_storage_root(str(other), context)
            self.assertEqual((other / "important").read_text(), "preserve")

    def test_changed_configuration_and_symlink_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            target = base / "env"
            target.write_bytes(b"existing")
            with self.assertRaises(setup.SetupError):
                setup.write_exact(target, b"replacement", b"stale")
            self.assertEqual(target.read_bytes(), b"existing")
            link = base / "link"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("Symlink creation not permitted")
            with self.assertRaises(setup.storage.StorageError):
                setup.write_exact(link, b"replacement", b"existing")

    def test_new_file_publication_never_replaces_concurrent_creator(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "env"
            real_link = setup.os.link
            def race(source, destination):
                target.write_bytes(b"concurrent")
                return real_link(source, destination)
            with patch.object(setup.os, "link", side_effect=race):
                with self.assertRaises(FileExistsError):
                    setup.write_exact(target, b"replacement", None)
            self.assertEqual(target.read_bytes(), b"concurrent")
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_check_is_readonly_and_rejects_invalid_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            main = base / "repo"
            main.mkdir()
            original = setup.merge_dotenv(b"", {"FULLMAG_PROJECT_STORAGE_ROOT": str(main)})
            (main / ".env").write_bytes(original)
            context = {"repo": main, "main": main, "project": base, "checkouts": [main]}
            checks = {"platform": "windows", "docker_os": {"value": "linux"}}
            with patch.object(setup, "checkout_context", return_value=context), patch.object(setup, "host_checks", return_value=checks), patch.object(setup, "show_checks"), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(setup.main(["--check"]), 2)
            self.assertEqual((main / ".env").read_bytes(), original)
            self.assertEqual(sorted(p.name for p in main.iterdir()), [".env"])

    def test_new_clone_configuration_roundtrip_with_real_resolver(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            main = project / "repo"
            main.mkdir()
            subprocess.run(["git", "init", "--quiet", str(main)], check=True)
            (main / ".env.example").write_text("POSTGRES_PASSWORD=change-me\nMINIO_ROOT_USER=fullmag\nMINIO_ROOT_PASSWORD=change-me\nFULLMAG_PROJECT_STORAGE_ROOT=\n")
            isolated = {key: value for key, value in os.environ.items()
                        if key not in setup.storage.MANAGED_VARIABLES and key not in {"GIT_DIR", "GIT_WORK_TREE"}}
            with patch.dict(os.environ, isolated, clear=True), patch.object(setup, "validate_host_paths"):
                prepared = setup.plan(main, str(project / "chosen-storage"), str(main), 3297)
                result = setup.apply_configuration(prepared)
                layout = setup.storage.resolve_layout(main, "docker-all-gpu", environ={})
            self.assertEqual(Path(layout["storage_root"]), project / "chosen-storage")
            saved = json.loads(Path(result["settings_path"]).read_text())
            self.assertEqual(saved["http_port"], 3297)
            self.assertEqual(saved["source_root"], str(main))
            self.assertFalse(saved["application_ready"])
            self.assertNotIn("PASSWORD", json.dumps(saved))
            self.assertNotEqual(setup.dotenv_values((main / ".env").read_bytes())["POSTGRES_PASSWORD"], "change-me")

    def test_resolver_failure_preserves_existing_env(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            main = project / "repo"
            main.mkdir()
            original = b"POSTGRES_PASSWORD=keep\n"
            (main / ".env").write_bytes(original)
            context = {"repo": main, "main": main, "project": project, "checkouts": [main]}
            with patch.object(setup, "checkout_context", return_value=context), patch.object(setup, "validate_host_paths"):
                prepared = setup.plan(main, str(project / "storage"), str(main), 3197)
                with patch.object(setup.storage, "resolve_layout", side_effect=setup.storage.StorageError("invalid override")):
                    with self.assertRaises(setup.storage.StorageError):
                        setup.apply_configuration(prepared)
            self.assertEqual((main / ".env").read_bytes(), original)
            self.assertFalse((project / "storage" / "index").exists())

    def test_cancel_is_readonly(self):
        context = {"repo": Path("/repo"), "main": Path("/repo")}
        checks = {"platform": "windows"}
        with patch.object(setup, "checkout_context", return_value=context), patch.object(setup, "host_checks", return_value=checks), patch.object(setup, "show_checks"), patch.object(setup.sys.stdin, "isatty", return_value=True), patch.object(setup, "plan", return_value={"env_path": "/repo/.env", "storage_root": "/storage", "source_root": "/repo", "port": 3197}), patch("builtins.input", side_effect=["/storage", "", "", "n"]), patch.object(setup, "apply_configuration") as apply, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.main([]), 0)
            apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
