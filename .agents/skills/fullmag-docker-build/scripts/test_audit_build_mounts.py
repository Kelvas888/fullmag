"""Portable regression checks for the partial, read-only Compose auditor."""
import copy
import unittest
from audit_build_mounts import audit


def configuration():
    source = {"type": "bind", "source": "C:/repo/worktree", "target": "/opt/fullmag/source", "read_only": True}
    return {"name": "fullmag-master", "volumes": {name: {} for name in ("build", "package", "frontend")}, "services": {
        "backend": {"read_only": True,
            "environment": {"FULLMAG_PACKAGE_PROVENANCE": "/build/control/provenance.json"},
            "volumes": [copy.deepcopy(source),
            {"type": "volume", "source": "build", "target": "/build"},
            {"type": "volume", "source": "package", "target": "/opt/fullmag/package"},
            {"type": "bind", "source": "C:/results", "target": "/state"},
            {"type": "bind", "source": "C:/settings", "target": "/user-data"}]},
        "frontend": {"read_only": True, "volumes": [copy.deepcopy(source),
            {"type": "volume", "source": "frontend", "target": "/state/development"},
            {"type": "bind", "source": "C:/repo/worktree/apps/control-room/app",
             "target": "/state/development/workspace/apps/control-room/app", "read_only": True}]},
    }}


class BuildMountTests(unittest.TestCase):
    def test_named_build_volumes_with_windows_runtime_and_live_readonly_source(self):
        result = audit(configuration(), "fullmag-master")
        self.assertEqual(result["status"], "PASS", result)

    def test_file_bind_overrides_parent_control_volume(self):
        config = configuration()
        config["services"]["backend"]["volumes"].append({
            "type": "bind", "source": "C:/storage/provenance.json",
            "target": "/build/control/provenance.json"})
        result = audit(config, "fullmag-master")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("provenance.json" in problem for problem in result["problems"]))

    def test_frontend_windows_working_tree_is_rejected(self):
        config = configuration()
        config["services"]["frontend"]["volumes"][1] = {
            "type": "bind", "source": "C:/storage/development", "target": "/state/development"}
        self.assertEqual(audit(config, "fullmag-master")["status"], "FAIL")

    def test_descendant_tmpfs_cannot_hide_inside_persistent_build_root(self):
        config = configuration()
        config["services"]["backend"]["volumes"].append({
            "type": "tmpfs", "target": "/build/workspace/.fullmag-build"})
        self.assertEqual(audit(config, "fullmag-master")["status"], "FAIL")

    def test_different_source_or_project_is_rejected(self):
        config = configuration()
        config["services"]["frontend"]["volumes"][0]["source"] = "C:/other/repo"
        self.assertEqual(audit(config, "fullmag-master")["status"], "FAIL")
        self.assertEqual(audit(configuration(), "fullmag-worktree-other")["status"], "FAIL")

    def test_named_volume_with_host_bind_driver_options_is_rejected(self):
        config = configuration()
        config["volumes"]["build"] = {"driver": "local", "driver_opts": {
            "type": "none", "o": "bind", "device": "/host/storage/build"}}
        self.assertEqual(audit(config, "fullmag-master")["status"], "FAIL")

    def test_parent_traversal_and_unrendered_mounts_are_not_admitted(self):
        for mount in ["build:/build", {"type": "volume", "source": "build", "target": "/build/../state"}]:
            config = configuration()
            config["services"]["backend"]["volumes"].append(mount)
            with self.assertRaises(ValueError):
                audit(config, "fullmag-master")


if __name__ == "__main__":
    unittest.main()
