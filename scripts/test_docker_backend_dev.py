"""Interpreted package publication regressions; no native compilation."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker" / "all-in-one"))
import backend_dev as backend


@unittest.skipIf(os.name == "nt", "Linux container symlink contract")
class BackendPackageTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
