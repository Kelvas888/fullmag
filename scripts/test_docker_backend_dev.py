"""Interpreted package publication regressions; no native compilation."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker" / "all-in-one"))
import backend_dev as backend


@unittest.skipIf(os.name == "nt", "Linux container symlink contract")
class BackendPackageTests(unittest.TestCase):
    @staticmethod
    def _capsule(source_digest, files):
        entries = []
        for relative, content in files.items():
            entries.append(
                {
                    "path": relative,
                    "type": "file",
                    "mode": "100644",
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        return {"source_digest": source_digest, "files": sorted(entries, key=lambda entry: entry["path"])}

    @staticmethod
    def _stage(root, files):
        stage = root / f"stage-{len(tuple(root.glob('stage-*')))}"
        stage.mkdir()
        for relative, content in files.items():
            path = stage.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return stage

    @staticmethod
    def _workspace(root):
        workspace = backend._prepare_workspace(root)
        (workspace / ".fullmag-build" / "cargo-fingerprint").write_bytes(b"cache")
        return workspace

    @staticmethod
    def _package_workspace(root):
        workspace = root / "package-workspace"
        source = workspace / ".fullmag" / "local"
        source.mkdir(parents=True)
        for relative in backend.REQUIRED_PACKAGE_PATHS:
            if relative in backend.RUNTIME_MANIFEST_PATHS:
                continue
            path = source.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            content = "cuda-fem-gpu\n" if relative == "launcher-build-mode" else "package\n"
            path.write_text(content, encoding="utf-8")
            if relative.startswith("bin/"):
                path.chmod(0o755)
        for relative in ("lib/libfullmag_fdm.so.1", "lib/libfullmag_fem.so.1"):
            path = source.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"native-library")
        return workspace

    def _published_package(self, root):
        workspace = self._package_workspace(root)
        output = root / "package"
        records = backend._copy_package(workspace, output)
        return output, records

    def test_local_runtime_manifests_are_attested_and_resolve_workers_inside_package(self):
        with tempfile.TemporaryDirectory() as directory:
            output, records = self._published_package(Path(directory))
            self.assertEqual(backend._hash_package(output), records)
            record_paths = {record["path"] for record in records}
            self.assertTrue(set(backend.RUNTIME_MANIFEST_PATHS).issubset(record_paths))
            self.assertEqual(
                {record["path"] for record in records if record["path"].startswith("runtimes/")},
                set(backend.RUNTIME_MANIFEST_PATHS),
            )

            manifests = {}
            package_root = output.resolve()
            for relative in backend.RUNTIME_MANIFEST_PATHS:
                path = output / relative
                manifest = json.loads(path.read_text(encoding="utf-8"))
                manifests[manifest["family"]] = manifest
                worker = (path.parent / manifest["worker"]).resolve(strict=True)
                self.assertTrue(worker.is_relative_to(package_root))
                self.assertEqual(worker, (output / "bin/fullmag-bin").resolve())
                self.assertEqual(manifest["worker"], "../../bin/fullmag-bin")

            self.assertTrue(manifests["cpu-reference"]["engines"][0]["public"])
            self.assertTrue(manifests["fdm-cuda"]["engines"][0]["public"])
            for family in ("fem-cpu-native", "fem-gpu"):
                engine = manifests[family]["engines"][0]
                self.assertFalse(engine["public"])
                self.assertEqual(engine["stability"], "experimental")

    def test_tampered_runtime_manifest_is_rejected_by_serve_verifier(self):
        with tempfile.TemporaryDirectory() as directory:
            output, records = self._published_package(Path(directory))
            backend._write_json(
                output / "backend-build-receipt.json",
                {
                    "schema": backend.RECEIPT_SCHEMA,
                    "state": "succeeded",
                    "execution_lanes": {lane: {} for lane in backend.LANES},
                    "artifacts": records,
                },
                "test backend build receipt",
            )
            manifest = output / "runtimes/fem-gpu/manifest.json"
            manifest.write_text(manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            original_package_root = backend.PACKAGE_ROOT
            backend.PACKAGE_ROOT = output
            try:
                with self.assertRaisesRegex(
                    backend.BackendBuildError, "runtime package artifacts differ from the build receipt"
                ):
                    backend._serve([])
            finally:
                backend.PACKAGE_ROOT = original_package_root

    def test_development_compose_selects_receipt_validated_backend_start(self):
        repository = Path(__file__).resolve().parents[1]
        development_compose = (repository / "compose.dev.yaml").read_text(encoding="utf-8")
        backend_block = development_compose.split("\n  backend:\n", 1)[1].split(
            "\n  frontend:\n", 1
        )[0]
        self.assertIn(
            'entrypoint: ["/usr/local/bin/python3", "/opt/fullmag/backend_dev.py", "serve"]',
            backend_block,
        )
        static_compose = (repository / "compose.static.yaml").read_text(encoding="utf-8")
        self.assertNotIn("/opt/fullmag/backend_dev.py", static_compose)

        with tempfile.TemporaryDirectory() as directory:
            output, records = self._published_package(Path(directory))
            backend._write_json(
                output / "backend-build-receipt.json",
                {
                    "schema": backend.RECEIPT_SCHEMA,
                    "state": "succeeded",
                    "execution_lanes": {lane: {} for lane in backend.LANES},
                    "artifacts": records,
                },
                "test backend build receipt",
            )
            original_package_root = backend.PACKAGE_ROOT
            backend.PACKAGE_ROOT = output
            try:
                with patch.object(backend.os, "execvpe") as execvpe:
                    self.assertEqual(backend.main(["serve"]), 0)
                    self.assertEqual(backend.main(["serve", "--storage-probe"]), 0)
                self.assertEqual(execvpe.call_count, 2)
                self.assertEqual(
                    execvpe.call_args_list[0].args[1][1:],
                    ["/opt/fullmag/entrypoint.py"],
                )
                self.assertEqual(
                    execvpe.call_args_list[1].args[1][1:],
                    ["/opt/fullmag/entrypoint.py", "--storage-probe"],
                )
                self.assertEqual(
                    execvpe.call_args_list[0].args[2]["FULLMAG_RUNTIME_ROOT"],
                    str(output),
                )
                self.assertEqual(
                    execvpe.call_args_list[0].args[2]["FULLMAG_RUNTIME_PACKAGE_ROOT"],
                    str(output),
                )

                manifest = output / "runtimes/fem-gpu/manifest.json"
                manifest.write_text(
                    manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8"
                )
                with patch.object(backend.os, "execvpe") as tampered_exec:
                    self.assertEqual(backend.main(["serve"]), 2)
                    tampered_exec.assert_not_called()
            finally:
                backend.PACKAGE_ROOT = original_package_root

    def test_native_soname_alias_is_published_as_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "lib").mkdir(parents=True)
            (source / "lib/libfullmag_fdm.so.1").write_bytes(b"native-library")
            (source / "lib/libfullmag_fdm.so").symlink_to("libfullmag_fdm.so.1")
            target = root / "package"
            backend._copy_package_tree(source, target)
            self.assertEqual((target / "lib/libfullmag_fdm.so").read_bytes(), b"native-library")
            self.assertFalse((target / "lib/libfullmag_fdm.so").is_symlink())

    def test_package_alias_cannot_escape_library_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outside").write_bytes(b"retained")
            source = root / "source"
            (source / "lib").mkdir(parents=True)
            (source / "lib/libfullmag_fem.so").symlink_to(root / "outside")
            with self.assertRaises(backend.BackendBuildError):
                backend._copy_package_tree(source, root / "package")
            self.assertEqual((root / "outside").read_bytes(), b"retained")

    def test_empty_first_attempt_workspace_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            for name in backend.PERSISTENT_WORKSPACE_DIRS:
                (workspace / name).mkdir()
            self.assertEqual(backend._prepare_workspace(root), workspace)
            self.assertTrue((workspace / backend.OWNER_MARKER).is_file())
            self.assertEqual(backend._prepare_workspace(root), workspace)

    def test_unowned_nonempty_workspace_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            retained = workspace / "unknown"
            retained.write_bytes(b"keep")
            with self.assertRaises(backend.BackendBuildError):
                backend._prepare_workspace(root)
            self.assertEqual(retained.read_bytes(), b"keep")

    def test_cleanup_unlinks_owned_alias_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "retained"
            outside.write_bytes(b"keep")
            owned = root / "owned"
            owned.mkdir()
            (owned / "alias").symlink_to(outside)
            backend._remove_owned_tree(owned)
            self.assertFalse(owned.exists())
            self.assertEqual(outside.read_bytes(), b"keep")

    def test_reconcile_preserves_mtime_for_identical_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {"crates/example/src/lib.rs": b"pub fn stable() {}\n"}
            capsule = self._capsule("a" * 64, files)
            workspace = self._workspace(root)
            backend._reconcile_source_tree(
                self._stage(root, files), workspace, capsule, "b" * 64
            )
            target = workspace / "crates/example/src/lib.rs"
            stable_time = 1_600_000_000_000_000_000
            os.utime(target, ns=(stable_time, stable_time))
            backend._reconcile_source_tree(
                self._stage(root, files), workspace, capsule, "c" * 64
            )
            self.assertEqual(target.stat().st_mtime_ns, stable_time)
            self.assertEqual(target.read_bytes(), files["crates/example/src/lib.rs"])
            target.write_bytes(b"tampered\n")
            os.utime(target, ns=(stable_time, stable_time))
            backend._reconcile_source_tree(
                self._stage(root, files), workspace, capsule, "d" * 64
            )
            self.assertEqual(target.read_bytes(), files["crates/example/src/lib.rs"])

    def test_reconcile_replaces_changed_and_removes_deleted_without_touching_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = {
                "crates/example/src/lib.rs": b"pub fn old() {}\n",
                "crates/example/src/stable.rs": b"pub fn stable() {}\n",
                "crates/example/src/removed.rs": b"removed\n",
            }
            workspace = self._workspace(root)
            backend._reconcile_source_tree(
                self._stage(root, first), workspace, self._capsule("a" * 64, first), "b" * 64
            )
            marker_path = workspace / backend.OWNER_MARKER
            marker, _ = backend._read_json(marker_path, "test backend workspace owner")
            marker.pop("workspace_inventory_schema")
            marker.pop("workspace_inventory_sha256")
            backend._write_json(marker_path, marker, "test backend workspace owner")
            stable = workspace / "crates/example/src/stable.rs"
            stable_time = 1_600_000_000_000_000_000
            os.utime(stable, ns=(stable_time, stable_time))
            cache = workspace / ".fullmag-build" / "cargo-fingerprint"
            cache_time = 1_600_000_000_000_000_000
            os.utime(cache, ns=(cache_time, cache_time))

            second = {
                "crates/example/src/lib.rs": b"pub fn new() {}\n",
                "crates/example/src/stable.rs": b"pub fn stable() {}\n",
            }
            backend._reconcile_source_tree(
                self._stage(root, second), workspace, self._capsule("c" * 64, second), "d" * 64
            )
            self.assertEqual(
                (workspace / "crates/example/src/lib.rs").read_bytes(),
                second["crates/example/src/lib.rs"],
            )
            self.assertEqual(stable.read_bytes(), second["crates/example/src/stable.rs"])
            self.assertEqual(stable.stat().st_mtime_ns, stable_time)
            self.assertFalse((workspace / "crates/example/src/removed.rs").exists())
            self.assertEqual(cache.read_bytes(), b"cache")
            self.assertEqual(cache.stat().st_mtime_ns, cache_time)
            marker = (workspace / backend.OWNER_MARKER).read_text(encoding="utf-8")
            self.assertIn('"state":"ready"', marker)
            self.assertIn('"source_digest":"' + "c" * 64 + '"', marker)
            self.assertIn('"workspace_inventory_schema":"' + backend.WORKSPACE_INVENTORY_SCHEMA + '"', marker)
            self.assertIn('"workspace_inventory_sha256":"' + "c" * 64 + '"', marker)

    def test_reconcile_removes_owned_generated_output_without_following_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {"crates/example/src/lib.rs": b"safe\n"}
            workspace = self._workspace(root)
            capsule = self._capsule("a" * 64, files)
            backend._reconcile_source_tree(
                self._stage(root, files), workspace, capsule, "b" * 64
            )

            outside = root / "outside.so"
            outside.write_bytes(b"keep")
            alias = workspace / ".fullmag/local/lib/libfullmag_fdm.so"
            alias.parent.mkdir(parents=True)
            alias.symlink_to(outside)

            backend._reconcile_source_tree(
                self._stage(root, files), workspace, capsule, "c" * 64
            )

            self.assertFalse(alias.exists())
            self.assertFalse(alias.is_symlink())
            self.assertEqual(outside.read_bytes(), b"keep")
            self.assertEqual(
                (workspace / "crates/example/src/lib.rs").read_bytes(), files["crates/example/src/lib.rs"]
            )

    def test_reconcile_rejects_workspace_links_and_preserves_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._workspace(root)
            outside = root / "outside"
            outside.write_bytes(b"keep")
            link = workspace / "crates/example/link"
            link.parent.mkdir(parents=True)
            link.symlink_to(outside)
            files = {"crates/example/src/lib.rs": b"safe\n"}
            with self.assertRaises(backend.BackendBuildError):
                backend._reconcile_source_tree(
                    self._stage(root, files), workspace, self._capsule("a" * 64, files), "b" * 64
                )
            self.assertTrue(link.is_symlink())
            self.assertEqual(outside.read_bytes(), b"keep")

    def test_reconcile_rejects_source_replacing_owner_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = self._workspace(root)
            owner = workspace / backend.OWNER_MARKER
            before = owner.read_bytes()
            files = {backend.OWNER_MARKER: b"unexpected source"}
            with self.assertRaises(backend.BackendBuildError):
                backend._reconcile_source_tree(
                    self._stage(root, files), workspace, self._capsule("a" * 64, files), "b" * 64
                )
            self.assertEqual(owner.read_bytes(), before)
            self.assertEqual((workspace / ".fullmag-build/cargo-fingerprint").read_bytes(), b"cache")

    def test_direct_build_keeps_runner_workspace_and_sets_explicit_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            native = {
                "head_commit_full": "a" * 40,
                "source_snapshot_dirty": False,
                "source_snapshot_sha256": "b" * 64,
            }
            environment = backend._build_environment(workspace, root, native, 1)
            self.assertEqual(environment["FULLMAG_DIRECT_COMPOSE"], "1")
            self.assertEqual(environment["FULLMAG_BACKEND_CARGO_PROFILE"], "backend-dev")
            self.assertEqual(environment["FULLMAG_RUNNER_WORKSPACE"], str(workspace))

    def test_release_profile_uses_separate_native_target_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            native = {
                "head_commit_full": "a" * 40,
                "source_snapshot_dirty": False,
                "source_snapshot_sha256": "b" * 64,
            }
            environment = backend._build_environment(workspace, root, native, 1, "release")
            self.assertEqual(environment["FULLMAG_BACKEND_CARGO_PROFILE"], "release")
            self.assertIn("/direct/release/build/", environment["FULLMAG_FEM_NATIVE_BUILD_ROOT"])
            self.assertNotIn("backend-dev", environment["FULLMAG_FEM_NATIVE_BUILD_ROOT"])

    def test_direct_build_native_cache_roots_are_stable_and_cache_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            first_native = {
                "head_commit_full": "a" * 40,
                "source_snapshot_dirty": False,
                "source_snapshot_sha256": "b" * 64,
            }
            second_native = {**first_native, "source_snapshot_sha256": "c" * 64}
            first_environment = backend._build_environment(workspace, root, first_native, 1)
            second_environment = backend._build_environment(workspace, root, second_native, 1)

            other_root = root / "other-cache"
            other_workspace = other_root / "workspace"
            other_environment = backend._build_environment(
                other_workspace, other_root, first_native, 1
            )

            names = ("FULLMAG_FDM_NATIVE_BUILD_ROOT", "FULLMAG_FEM_NATIVE_BUILD_ROOT")
            for name in names:
                first = Path(first_environment[name])
                self.assertEqual(first, Path(second_environment[name]))
                self.assertNotEqual(first, Path(other_environment[name]))
                self.assertTrue(first.is_relative_to(workspace))
                self.assertTrue(first.is_relative_to(root))
                self.assertIn(".fullmag-build", first.parts)
                self.assertIn("backend-dev", first.parts)
                self.assertIn("native-build", first.parts)
            self.assertNotEqual(
                Path(first_environment["FULLMAG_FDM_NATIVE_BUILD_ROOT"]),
                Path(first_environment["FULLMAG_FEM_NATIVE_BUILD_ROOT"]),
            )


if __name__ == "__main__":
    unittest.main()
