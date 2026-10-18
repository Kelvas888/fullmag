from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


HELPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "docker"
    / "all-in-one"
    / "backend_volume_cache_maintenance.py"
)
SPEC = importlib.util.spec_from_file_location("backend_volume_cache_maintenance", HELPER_PATH)
assert SPEC is not None and SPEC.loader is not None
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class BackendVolumeCacheMaintenanceTests(unittest.TestCase):
    @staticmethod
    def _test_owner() -> tuple[int, int]:
        # The production service is root + CAP_CHOWN. A non-root interpreted
        # test cannot chown to 65532, so it exercises the same contract with
        # the current test user while retaining the production default below.
        if os.geteuid() == 0:
            return helper.DEFAULT_OWNER_UID, helper.DEFAULT_OWNER_GID
        return os.getuid(), os.getgid()

    def _environment(self) -> dict[str, str]:
        return {
            "FULLMAG_BACKEND_CACHE_SCHEMA": helper.SCHEMA,
            "FULLMAG_BACKEND_CACHE_PROFILE": helper.PROFILE,
            "FULLMAG_BACKEND_CACHE_MAINTENANCE_PROFILE": helper.MAINTENANCE_PROFILE,
            "FULLMAG_BACKEND_CACHE_MAINTENANCE_ACTION": "ensure",
            "FULLMAG_BACKEND_CACHE_BUILD_ROOT": helper.BUILD_ROOT,
            "FULLMAG_BACKEND_CACHE_PACKAGE_ROOT": helper.PACKAGE_ROOT,
            "FULLMAG_BACKEND_CACHE_OWNER_UID": str(helper.DEFAULT_OWNER_UID),
            "FULLMAG_BACKEND_CACHE_OWNER_GID": str(helper.DEFAULT_OWNER_GID),
            "FULLMAG_BACKEND_CACHE_PROJECT_ID": "fullmag",
            "FULLMAG_BACKEND_CACHE_KEY": "a" * 64,
            "FULLMAG_BACKEND_CACHE_UNIT_KEY": "b" * 64,
            "FULLMAG_BACKEND_CACHE_OWNER_ID": "b" * 64,
            "FULLMAG_BACKEND_CACHE_WORKTREE_ID": "docker-all-master-integration-20261017",
            "FULLMAG_BACKEND_CACHE_TOOLCHAIN_IMAGE_ID": "sha256:" + "c" * 64,
            "FULLMAG_BACKEND_CARGO_PROFILE": "backend-dev",
            "FULLMAG_BACKEND_RUNTIME_IMAGE_ID": "sha256:" + "d" * 64,
            "FULLMAG_BACKEND_CACHE_BUILD_VOLUME": "fullmag-cache-build",
            "FULLMAG_BACKEND_CACHE_PACKAGE_VOLUME": "fullmag-cache-package",
        }

    def test_fresh_and_reopen_prove_marker_readback_pair_without_host_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            package = root / "package"
            build.mkdir()
            package.mkdir()
            uid, gid = self._test_owner()
            receipt = helper.ensure(
                build,
                package,
                environment=self._environment(),
                owner_uid=uid,
                owner_gid=gid,
            )
            repeated = helper.ensure(
                build,
                package,
                environment=self._environment(),
                owner_uid=uid,
                owner_gid=gid,
            )
            self.assertEqual(receipt, repeated)
            self.assertEqual(receipt["state"], "ready")
            self.assertEqual(receipt["probe"]["state"], "passed")
            self.assertEqual(receipt["probe"]["owner_uid"], uid)
            self.assertEqual(receipt["probe"]["owner_gid"], gid)
            self.assertEqual(set(receipt["markers"]), {"build", "package"})
            self.assertNotIn(str(root), json.dumps(receipt))
            for path in (build, package):
                marker = path / helper.MARKER_NAME
                readback = path / helper.READBACK_NAME
                self.assertTrue(marker.is_file())
                self.assertTrue(readback.is_file())
                self.assertEqual(json.loads(marker.read_text())["uid"], uid)
                self.assertTrue(readback.read_bytes().startswith(b"fullmag-cache-readback:"))

    def test_foreign_marker_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            package = root / "package"
            build.mkdir()
            package.mkdir()
            marker = build / helper.MARKER_NAME
            marker.write_text(json.dumps({"foreign": True}), encoding="utf-8")
            before = marker.read_bytes()
            with self.assertRaisesRegex(helper.MaintenanceError, "foreign"):
                helper.ensure(
                    build,
                    package,
                    environment=self._environment(),
                    owner_uid=self._test_owner()[0],
                    owner_gid=self._test_owner()[1],
                )
            self.assertEqual(marker.read_bytes(), before)

    def test_marker_symlink_is_rejected_without_following(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            package = root / "package"
            build.mkdir()
            package.mkdir()
            target = root / "outside-marker"
            target.write_text("{}", encoding="utf-8")
            (build / helper.MARKER_NAME).symlink_to(target)
            with self.assertRaises(helper.MaintenanceError):
                helper.ensure(
                    build,
                    package,
                    environment=self._environment(),
                    owner_uid=self._test_owner()[0],
                    owner_gid=self._test_owner()[1],
                )
            self.assertEqual(target.read_text(encoding="utf-8"), "{}")

    def test_backend_handoff_keeps_reopenable_directory_and_narrow_records(self):
        """Exercise the DAC-sensitive layout on a real temporary filesystem."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            package = root / "package"
            build.mkdir()
            package.mkdir()
            build.chmod(0o755)
            package.chmod(0o755)
            uid, gid = self._test_owner()
            helper.ensure(
                build,
                package,
                environment=self._environment(),
                owner_uid=uid,
                owner_gid=gid,
            )

            for path in (build, package):
                self.assertEqual((path.stat().st_uid, path.stat().st_gid), (uid, gid))
                directory_mode = path.stat().st_mode & 0o777
                self.assertEqual(directory_mode & 0o700, 0o700)
                # A CAP_CHOWN-only reopen must be able to traverse/read the
                # backend-owned directory before taking record ownership.
                self.assertEqual(directory_mode & 0o005, 0o005)
                marker = path / helper.MARKER_NAME
                readback = path / helper.READBACK_NAME
                self.assertEqual((marker.stat().st_uid, marker.stat().st_gid), (uid, gid))
                self.assertEqual((readback.stat().st_uid, readback.stat().st_gid), (uid, gid))
                self.assertEqual(marker.stat().st_mode & 0o777, 0o640)
                self.assertEqual(readback.stat().st_mode & 0o777, 0o600)

            # A process interrupted while returning a record to the backend
            # owner is recoverable without widening either file's mode.
            if os.geteuid() == 0:
                for path in (build, package):
                    os.chown(path / helper.MARKER_NAME, 0, 0)
                    os.chown(path / helper.READBACK_NAME, 0, 0)
                helper.ensure(
                    build,
                    package,
                    environment=self._environment(),
                    owner_uid=uid,
                    owner_gid=gid,
                )
                for path in (build, package):
                    self.assertEqual(
                        (path / helper.MARKER_NAME).stat().st_uid,
                        uid,
                    )
                    self.assertEqual(
                        (path / helper.READBACK_NAME).stat().st_uid,
                        uid,
                    )

    def test_production_contract_keeps_uid_and_fixed_guest_roots(self):
        self.assertEqual(helper.DEFAULT_OWNER_UID, 65532)
        self.assertEqual(helper.DEFAULT_OWNER_GID, 65532)
        self.assertEqual(helper.BUILD_ROOT, "/build")
        self.assertEqual(helper.PACKAGE_ROOT, "/opt/fullmag/package")


if __name__ == "__main__":
    unittest.main(verbosity=2)
