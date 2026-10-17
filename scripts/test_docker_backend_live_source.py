"""Bounded live-source Git and Windows worktree marker regressions."""

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker" / "all-in-one"))
import backend_source


@unittest.skipIf(os.name == "nt", "Linux container Git pipe contract")
class LiveSourceGitTests(unittest.TestCase):
    @staticmethod
    def _worktree_fixture(root: Path, *, marker_id: str, backref: str):
        source = root / "selected-worktree"
        common = root / "common-git"
        candidate = common / "worktrees" / marker_id
        source.mkdir()
        candidate.mkdir(parents=True)
        (source / ".git").write_text(
            f"gitdir: {common / 'worktrees' / marker_id}\n",
            encoding="utf-8",
        )
        (candidate / "gitdir").write_text(backref + "\n", encoding="utf-8")
        return source, common, candidate

    def test_main_checkout_git_directory_remains_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "checkout"
            common = source / ".git"
            common.mkdir(parents=True)
            self.assertEqual(backend_source._live_git_dir(source, common), common)

    def test_windows_worktree_marker_accepts_case_insensitive_host_backref(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, common, candidate = self._worktree_fixture(
                root,
                marker_id="selected",
                backref=r"c:\Users\Dev\FULLMAG\.git",
            )
            with patch.dict(
                os.environ,
                {"FULLMAG_SOURCE_HOST_ROOT": r"C:\users\dev\fullmag"},
                clear=False,
            ):
                self.assertEqual(backend_source._live_git_dir(source, common), candidate)

    def test_worktree_marker_rejects_sibling_admin_backref(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, common, _ = self._worktree_fixture(
                root,
                marker_id="sibling",
                backref=str(root / "sibling-worktree" / ".git"),
            )
            with self.assertRaisesRegex(
                backend_source.BackendSourceError,
                "back-reference differs from the selected source root",
            ):
                backend_source._live_git_dir(source, common)

    def test_git_file_without_worktree_target_does_not_fallback_to_common_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "selected-worktree"
            common = root / "common-git"
            source.mkdir()
            common.mkdir()
            (source / ".git").write_text("gitdir: .git\n", encoding="utf-8")
            with self.assertRaisesRegex(
                backend_source.BackendSourceError,
                "does not identify a mounted worktree",
            ):
                backend_source._live_git_dir(source, common)

    def test_git_query_timeout_kills_stalled_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_git = root / "git"
            fake_git.write_text("#!/bin/sh\n/bin/sleep 1\n", encoding="utf-8")
            fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR)
            with (
                patch.dict(os.environ, {"PATH": str(root)}, clear=False),
                patch.object(backend_source, "LIVE_GIT_TIMEOUT_SECONDS", 0.05),
            ):
                with self.assertRaisesRegex(
                    backend_source.BackendSourceError,
                    "timed out after 0.05 seconds",
                ):
                    backend_source._live_run_git(root, root, "status", maximum=64)

    def test_git_query_output_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_git = root / "git"
            fake_git.write_text("#!/bin/sh\nprintf 123456\n", encoding="utf-8")
            fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {"PATH": str(root)}, clear=False):
                with self.assertRaisesRegex(
                    backend_source.BackendSourceError,
                    "stdout exceeded its size bound",
                ):
                    backend_source._live_run_git(root, root, "status", maximum=4)

    def test_git_batch_reader_handles_framed_body_in_one_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_git = root / "git"
            object_id = "a" * 40
            fake_git.write_text(
                f"#!/bin/sh\nread line\nprintf '{object_id} blob 3\\nabc\\n'\n",
                encoding="utf-8",
            )
            fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {"PATH": str(root)}, clear=False):
                self.assertEqual(
                    backend_source._live_read_blobs(
                        root / "git-dir", {"source.txt": object_id}
                    ),
                    {"source.txt": b"abc"},
                )


if __name__ == "__main__":
    unittest.main()
