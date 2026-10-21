from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import docker_dev_defaults as defaults
import docker_volume_resources as resources
from docker_build_control import BuildControlError

GIB = 1024 ** 3
VM = {"NCPU": 40, "MemTotal": 196 * GIB}


def _document():
    return {"services": {
        "backend": {"cpus": 4, "mem_limit": str(8 * GIB), "environment": {"CARGO_BUILD_JOBS": "4"}},
        "frontend": {"cpus": 4, "mem_limit": str(16 * GIB), "environment": {}},
    }}


class GroupBudgetTests(unittest.TestCase):
    def test_defaults_let_three_groups_fit_the_vm(self):
        document = _document()
        resources.apply_group_budget(document, {}, VM)
        backend, frontend = document["services"]["backend"], document["services"]["frontend"]
        self.assertEqual((backend["cpus"], backend["mem_limit"]), (8, 32 * GIB))
        self.assertEqual((frontend["cpus"], frontend["mem_limit"]), (4, 12 * GIB))
        self.assertLessEqual(3 * (backend["mem_limit"] + frontend["mem_limit"]), VM["MemTotal"])
        self.assertLessEqual(3 * (backend["cpus"] + frontend["cpus"]), VM["NCPU"])
        # Container quota, native profile and Cargo share one value.
        self.assertEqual(backend["environment"]["CARGO_BUILD_JOBS"], "8")
        self.assertEqual(backend["environment"]["FULLMAG_DOCKER_CPU_MILLIS"], "8000")
        self.assertEqual(backend["environment"]["FULLMAG_DOCKER_MEMORY_BYTES"], str(32 * GIB))

    def test_small_vm_keeps_native_minimums(self):
        document = _document()
        resources.apply_group_budget(document, {}, {"NCPU": 4, "MemTotal": 16 * GIB})
        self.assertEqual(document["services"]["backend"]["cpus"], 2)
        self.assertEqual(document["services"]["backend"]["mem_limit"], 8 * GIB)

    def test_configured_values_override_defaults_and_are_bounded(self):
        document = _document()
        resources.apply_group_budget(document, {"FULLMAG_DEV_BACKEND_CPUS": 12}, VM)
        self.assertEqual(document["services"]["backend"]["cpus"], 12)
        self.assertEqual(document["services"]["backend"]["environment"]["CARGO_BUILD_JOBS"], "12")
        with self.assertRaisesRegex(BuildControlError, "at least 2"):
            resources.apply_group_budget(_document(), {"FULLMAG_DEV_BACKEND_CPUS": 1}, VM)
        with self.assertRaisesRegex(BuildControlError, "exceeds Docker capacity"):
            resources.apply_group_budget(_document(), {"FULLMAG_DEV_BACKEND_CPUS": 41}, VM)
        with self.assertRaisesRegex(BuildControlError, "8 GiB for frontend"):
            resources.apply_group_budget(_document(), {"FULLMAG_DEV_FRONTEND_MEMORY_GIB": 4}, VM)

    def test_process_environment_overrides_main_dotenv(self):
        dotenv = {"FULLMAG_DEV_BACKEND_CPUS": "6", "FULLMAG_DEV_FRONTEND_CPUS": "3"}
        with mock.patch.object(defaults, "_known_checkouts", return_value=(Path.cwd(),)), \
                mock.patch.object(defaults, "_read_dotenv", return_value=dotenv):
            budget = defaults.configured_group_budget(
                Path.cwd(), {"FULLMAG_DEV_BACKEND_CPUS": "10"})
            self.assertEqual(budget, {"FULLMAG_DEV_BACKEND_CPUS": 10, "FULLMAG_DEV_FRONTEND_CPUS": 3})
            with self.assertRaisesRegex(defaults.DiscoveryError, "positive whole number"):
                defaults.configured_group_budget(Path.cwd(), {"FULLMAG_DEV_BACKEND_CPUS": "2.5"})


if __name__ == "__main__":
    unittest.main()
