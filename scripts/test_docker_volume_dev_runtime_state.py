"""Regressions for native preparation of a fresh Windows runtime state."""

from __future__ import annotations

import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docker_volume_dev


class DockerVolumeDevRuntimeStateTests(unittest.TestCase):
    def test_precreate_uses_real_write_probe_and_exact_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            state.mkdir()

            with patch.object(docker_volume_dev.sys, "platform", "win32"):
                prepared = docker_volume_dev._precreate_new_windows_runtime_state(state)

            expected = tuple(
                relative.as_posix()
                for relative in docker_volume_dev._NEW_WINDOWS_RUNTIME_STATE_DIRECTORIES
            )
            self.assertEqual(prepared, expected)
            for relative in expected:
                self.assertTrue((state / relative).is_dir())
            self.assertEqual(
                list((state / expected[-1]).iterdir()),
                [],
                "the write probe must not leave technical files in Windows runtime state",
            )

    def test_precreate_rejects_existing_runtime_data_without_adopting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            existing = state / "runs/docker-all/session-store"
            existing.mkdir(parents=True)
            marker = existing / "existing.json"
            marker.write_text("keep", encoding="utf-8")

            with patch.object(docker_volume_dev.sys, "platform", "win32"), self.assertRaises(
                docker_volume_dev.BuildControlError
            ):
                docker_volume_dev._precreate_new_windows_runtime_state(state)

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertTrue(existing.is_dir())

    def test_precreate_rejects_reparse_entry_before_creating_children(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state"
            state.mkdir()
            redirected = root / "outside"
            redirected.mkdir()
            try:
                (state / "runs").symlink_to(redirected, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlink test requires native reparse support: {error}")

            with patch.object(docker_volume_dev.sys, "platform", "win32"), self.assertRaises(
                docker_volume_dev.BuildControlError
            ):
                docker_volume_dev._precreate_new_windows_runtime_state(state)

            self.assertEqual(list(redirected.iterdir()), [])
            self.assertFalse((redirected / "docker-all").exists())

    def test_start_wires_preparation_before_mount_and_compose(self):
        source = inspect.getsource(docker_volume_dev.start)
        self.assertLess(
            source.index("_precreate_new_windows_runtime_state(state)"),
            source.index("local_volume(state)"),
        )
        self.assertLess(
            source.index("_precreate_new_windows_runtime_state(state)"),
            source.index("_start_compose_services(control, operation, document)"),
        )


if __name__ == "__main__":
    unittest.main()
