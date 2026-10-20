"""Bounded live-source Git and Windows worktree marker regressions."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker" / "all-in-one"))
import backend_source


@unittest.skipIf(os.name == "nt", "Linux container Git pipe contract")
class LiveSourceGitTests(unittest.TestCase):
    @staticmethod
    def _git(repository: Path, *arguments: str) -> None:
        subprocess.run(
            ("git", "-C", str(repository), *arguments),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

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

    def test_runtime_status_pathspec_matches_canonical_helper(self):
        canonical_path = Path(__file__).resolve().parent / "capture_source_snapshot_identity.py"
        spec = importlib.util.spec_from_file_location("canonical_source_identity", canonical_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        canonical = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(canonical)
        tree = b"\0".join(
            b"100644 blob " + (b"a" * 40) + b"\t" + path
            for path in (
                (
                    b".agents/metadata.txt",
                    b"apps/control-room/main.ts",
                    b"docs/guide.md",
                    b"external_solvers/3/README",
                    b"README.md",
                    b"runtime.py",
                    b"scripts/test_fixture.py",
                    b"src/main.py",
                )
            )
        ) + b"\0"
        top_level = b"\n".join(
            (
                b".agents",
                b"apps",
                b"docs",
                b"external_solvers",
                b"README.md",
                b"runtime.py",
                b"scripts",
                b"src",
            )
        ) + b"\n"
        with patch.object(canonical, "_git", return_value=top_level):
            expected = canonical._runtime_status_pathspecs(Path("/unused"))
        self.assertEqual(backend_source._live_runtime_status_pathspecs(tree), expected)

    def test_gitlink_worktree_is_ignored_but_pinned_index_changes_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            self._git(repository, "init", "--quiet")
            self._git(repository, "config", "user.email", "backend-source@example.invalid")
            self._git(repository, "config", "user.name", "Backend source test")
            (repository / "runtime.py").write_text("runtime\n", encoding="utf-8")
            self._git(repository, "add", "runtime.py")
            self._git(repository, "commit", "-qm", "initial")

            solver_seed = root / "solver-seed"
            solver_seed.mkdir()
            self._git(solver_seed, "init", "--quiet")
            self._git(solver_seed, "config", "user.email", "solver@example.invalid")
            self._git(solver_seed, "config", "user.name", "Solver test")
            (solver_seed / "tracked.txt").write_text("solver\n", encoding="utf-8")
            self._git(solver_seed, "add", "tracked.txt")
            self._git(solver_seed, "commit", "-qm", "initial solver")
            self._git(
                repository,
                "-c",
                "protocol.file.allow=always",
                "submodule",
                "add",
                str(solver_seed),
                "external_solvers/3",
            )
            self._git(repository, "commit", "-qm", "add external solver")

            build_root = root / "build"
            build_root.mkdir()

            def capture() -> dict[str, object]:
                manifest_path = backend_source.capture_live_source_manifest(
                    repository, repository / ".git", build_root
                )
                return json.loads(manifest_path.read_text(encoding="utf-8"))

            with patch.object(
                backend_source, "_live_run_git", wraps=backend_source._live_run_git
            ) as run_git:
                first = capture()
            status_calls = [
                call.args[2:]
                for call in run_git.call_args_list
                if len(call.args) >= 3 and call.args[2] == "status"
            ]
            self.assertTrue(status_calls)
            self.assertTrue(
                all("--ignore-submodules=all" in arguments for arguments in status_calls)
            )

            first_gitlinks = [
                item
                for item in first["source_manifest"]["excluded"]
                if isinstance(item, dict)
                and item.get("path") == "external_solvers/3"
                and item.get("type") == "gitlink"
            ]
            self.assertEqual(len(first_gitlinks), 1)
            first_pin = first_gitlinks[0]["pinned_commit"]

            solver_checkout = repository / "external_solvers" / "3"
            (solver_checkout / "tracked.txt").write_text(
                "dirty solver worktree\n", encoding="utf-8"
            )
            dirty = capture()
            self.assertEqual(dirty["source_digest"], first["source_digest"])
            self.assertFalse(
                dirty["native_source_identity"]["source_snapshot_dirty"]
            )

            canonical_path = Path(__file__).resolve().parent / "capture_source_snapshot_identity.py"
            spec = importlib.util.spec_from_file_location("gitlink_canonical_identity", canonical_path)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            canonical = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(canonical)
            for ignore_non_runtime_dirty in (False, True):
                with patch.object(canonical, "_git", wraps=canonical._git) as canonical_git:
                    identity = canonical.capture(
                        repository, ignore_non_runtime_dirty=ignore_non_runtime_dirty
                    )
                self.assertFalse(identity["source_snapshot_dirty"])
                self.assertEqual(identity["dirty_path_content"], [])
                canonical_status = [
                    call.args[1:] for call in canonical_git.call_args_list
                    if len(call.args) >= 2 and call.args[1] == "status"
                ]
                self.assertTrue(canonical_status)
                self.assertTrue(all(
                    "--ignore-submodules=all" in arguments
                    for arguments in canonical_status
                ))

            (solver_checkout / "tracked.txt").write_text(
                "next solver commit\n", encoding="utf-8"
            )
            self._git(solver_checkout, "config", "user.email", "solver@example.invalid")
            self._git(solver_checkout, "config", "user.name", "Solver test")
            self._git(solver_checkout, "add", "tracked.txt")
            self._git(solver_checkout, "commit", "-qm", "next solver")
            self._git(repository, "add", "external_solvers/3")
            changed_pin = capture()
            changed_gitlinks = [
                item
                for item in changed_pin["source_manifest"]["excluded"]
                if isinstance(item, dict)
                and item.get("path") == "external_solvers/3"
                and item.get("type") == "gitlink"
            ]
            self.assertNotEqual(changed_pin["source_digest"], first["source_digest"])
            self.assertTrue(
                any(item.get("pinned_commit") != first_pin for item in changed_gitlinks)
            )

    def test_full_untracked_scan_reconstructs_porcelain_records(self):
        paths, records = backend_source._live_untracked_records(
            b"src/new.py\0docs/new.md\0"
        )
        self.assertEqual(paths, ["src/new.py", "docs/new.md"])
        self.assertEqual(
            records,
            [
                {"status": "??", "paths": ["src/new.py"]},
                {"status": "??", "paths": ["docs/new.md"]},
            ],
        )

    def test_stream_hash_is_bounded_deterministic_and_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contents = {
                "z-last.bin": b"z" * (backend_source.LIVE_HASH_CHUNK_BYTES + 17),
                "a-first.txt": b"first\n",
                "m-middle.txt": b"middle\n",
            }
            for relative, content in contents.items():
                (root / relative).write_bytes(content)
            relatives = sorted(contents)
            expected = {
                relative: (
                    "100644",
                    len(contents[relative]),
                    hashlib.sha256(contents[relative]).hexdigest(),
                )
                for relative in relatives
            }
            self.assertEqual(backend_source._live_hash_regular_files(root, relatives), expected)
            self.assertEqual(backend_source._live_hash_regular_files(root, relatives), expected)

    def test_stream_hash_rejects_unsafe_parent_and_changed_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir()
            (target / "file.txt").write_text("safe", encoding="utf-8")
            (root / "link").symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(
                backend_source.BackendSourceError,
                "unsafe parent",
            ):
                backend_source._live_hash_regular(root, "link/file.txt")

            regular = root / "stable.txt"
            regular.write_text("stable", encoding="utf-8")
            original_signature = backend_source._live_metadata_signature
            calls = 0

            def changed_signature(metadata):
                nonlocal calls
                calls += 1
                signature = original_signature(metadata)
                if calls == 2:
                    return (*signature[:-1], signature[-1] + 1)
                return signature

            with patch.object(
                backend_source,
                "_live_metadata_signature",
                side_effect=changed_signature,
            ):
                with self.assertRaisesRegex(
                    backend_source.BackendSourceError,
                    "changed while being read",
                ):
                    backend_source._live_hash_regular(root, "stable.txt")

    def test_stream_hash_rejects_lowercase_lfs_pointer_with_padding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pointer = (
                b"version https://git-lfs.github.com/spec/v1\n"
                b"oid sha256:" + b"a" * 64 + b"\n"
                b"size 4\n"
            )
            (root / "pointer.dat").write_bytes(pointer + b"x" * (backend_source.LIVE_GIT_MARKER_BYTES + 1))
            with self.assertRaisesRegex(
                backend_source.BackendSourceError,
                "Git-LFS pointer",
            ):
                backend_source._live_hash_regular(root, "pointer.dat")


if __name__ == "__main__":
    unittest.main()
