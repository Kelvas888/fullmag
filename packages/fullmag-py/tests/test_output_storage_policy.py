"""Output-storage collision policy checks; no native solver or build is executed."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import fullmag as fm
from fullmag.model.output_storage import OutputStorage
from fullmag.runtime.cli import build_parser, _reserve_stage_sequence_root


class ExistingOutputPolicyTests(unittest.TestCase):
    def test_model_accepts_every_supported_policy(self):
        for policy in ("timestamp", "error", "overwrite"):
            with self.subTest(policy=policy):
                storage = OutputStorage(existing_output=policy)
                self.assertEqual(storage.to_ir()["existing_output"], policy)
                self.assertEqual(OutputStorage.from_ir(storage.to_ir()), storage)

    def test_model_rejects_unknown_policies(self):
        for policy in ("Overwrite", "replace", "", "overwrite ", None, 1):
            with self.subTest(policy=policy), self.assertRaises(ValueError) as raised:
                OutputStorage(existing_output=policy)  # type: ignore[arg-type]
            self.assertIn("'overwrite'", str(raised.exception))

    def test_study_storage_records_overwrite(self):
        fm.reset()
        self.addCleanup(fm.reset)
        study = fm.study("overwrite_policy")
        study.storage(output_dir="results.zarr", existing_output="overwrite")
        from fullmag.world import _state

        self.assertEqual(
            _state._extra_runtime_metadata["output_storage"]["existing_output"],
            "overwrite",
        )

    def test_python_launcher_accepts_overwrite(self):
        args = build_parser().parse_args(["model.py", "--existing-output", "overwrite"])
        self.assertEqual(args.existing_output, "overwrite")


class SequenceRootOverwriteTests(unittest.TestCase):
    def test_overwrite_replaces_an_inactive_fullmag_result(self):
        with TemporaryDirectory() as directory:
            base = Path(directory) / "results.zarr"
            base.mkdir()
            (base / ".zattrs").write_text(
                json.dumps({"schema_version": "fullmag.project_results.v1"}),
                encoding="utf-8",
            )
            (base / "stale.bin").write_bytes(b"old")

            root = _reserve_stage_sequence_root(base, existing_output="overwrite")

            self.assertEqual(root, base.absolute())
            self.assertTrue(root.is_dir())
            self.assertEqual(list(root.iterdir()), [])

    def test_overwrite_refuses_a_foreign_directory(self):
        with TemporaryDirectory() as directory:
            base = Path(directory) / "results.zarr"
            base.mkdir()
            (base / "notes.txt").write_text("user data", encoding="utf-8")

            with self.assertRaises(FileExistsError) as raised:
                _reserve_stage_sequence_root(base, existing_output="overwrite")

            self.assertIn("refusing to overwrite", str(raised.exception))
            self.assertIn(str(base), str(raised.exception))
            self.assertEqual((base / "notes.txt").read_text(encoding="utf-8"), "user data")

    def test_overwrite_refuses_an_active_result(self):
        with TemporaryDirectory() as directory:
            base = Path(directory) / "results.zarr"
            stage = base / "stage_01_run.zarr"
            stage.mkdir(parents=True)
            (base / ".zattrs").write_text(
                json.dumps({"schema_version": "fullmag.project_results.v1"}),
                encoding="utf-8",
            )
            (stage / ".fullmag-active.lock").write_text("token", encoding="utf-8")

            with self.assertRaises(FileExistsError) as raised:
                _reserve_stage_sequence_root(base, existing_output="overwrite")

            self.assertIn("active run reservation", str(raised.exception))
            self.assertTrue((stage / ".fullmag-active.lock").exists())


if __name__ == "__main__":
    unittest.main()
