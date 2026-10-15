#!/usr/bin/env python3
"""Focused interpreted checks for the Docker Desktop host-ledger adapter."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path, PureWindowsPath

import docker_host_ledger as ledger
import fullmag_storage as storage

IMAGE = "sha256:" + "a" * 64


class FakeDocker:
    def __init__(self, values):
        self.values = values
        self.containers = {}
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if args[:2] == ("info", "--format"):
            return json.dumps({"ID": "desktop-daemon-1", "OSType": "linux"})
        if args[:2] == ("image", "inspect"):
            return json.dumps([{"Id": IMAGE, "Config": {"Volumes": None}, "Created": "now"}])
        if args[0] == "run":
            name = args[args.index("--name") + 1]
            label = args[args.index("--label") + 1].split("=", 1)[1]
            self.containers[name] = self._container(name, label)
            return "fullmag-host-ledger-host-python3-v1\n"
        if args[0] == "compose" and "run" in args:
            name = args[args.index("--name") + 1]
            label = args[args.index("--label") + 1].split("=", 1)[1]
            action = args[-1]
            self.containers[name] = self._container(name, label)
            return json.dumps(self._receipt(action)) + "\n"
        if args[0] == "inspect":
            return json.dumps([self.containers[args[1]]])
        if args[0] == "rm":
            self.containers.pop(args[1], None)
            return args[1]
        if args[0] == "exec":
            return "verified"
        raise AssertionError(f"unexpected fake docker call: {args!r}")

    def _container(self, name, label):
        return {
            "Id": name + "-id", "Name": "/" + name, "Image": IMAGE,
            "Config": {"Labels": {"org.fullmag.host-ledger.owner": label}},
            "State": {"Status": "exited", "ExitCode": 0},
        }

    def _receipt(self, action):
        return {
            "schema": ledger.HOST_RECEIPT_SCHEMA, "profile": ledger.PROFILE,
            "project_id": self.values["project_id"], "backing_image": self.values["backing_image"],
            "mount_root": self.values["mount_root"], "mount_target": "/host-ledger",
            "ledger_root": self.values["mount_root"] + "/ledger", "filesystem": "ext4",
            "filesystem_uuid": "11111111-1111-1111-1111-111111111111", "image_size_bytes": ledger.IMAGE_SIZE_BYTES,
            "loop_device": "/dev/loop7", "mount_active": True, "state": "ready" if action == "ensure" else "validated",
        }


class HostLedgerTests(unittest.TestCase):
    def test_windows_drive_mapping_is_linux_daemon_scoped(self):
        self.assertEqual(
            ledger._daemon_path(r"C:\git\fullmag\storage", "storage"),
            "/run/desktop/mnt/host/c/git/fullmag/storage",
        )
        with self.assertRaises(ledger.HostLedgerError):
            ledger._daemon_path(r"C:\git\fullmag\..\storage", "storage")

    def test_storage_resolver_keeps_linux_mount_paths_under_windows_syntax(self):
        value = storage.linux_host_ledger_infrastructure(
            PureWindowsPath(r"C:\git\fullmag\storage"), "fullmag-test-abc123", ledger.PROFILE
        )
        self.assertEqual(value["host_ledger_mount_root"], "/mnt/fullmag-host-ledger-fullmag-test-abc123")
        self.assertEqual(value["host_ledger_ledger_root"], "/mnt/fullmag-host-ledger-fullmag-test-abc123/ledger")

    def test_prepare_freezes_overlay_and_runs_bounded_maintenance(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage_root = root / "storage"
            values = {
                "project_id": "fullmag-test-abc123",
                "storage_root": str(storage_root),
                "backing_image": str(storage_root / "build-volumes" / ledger.IMAGE_NAME),
                "mount_root": "/mnt/fullmag-host-ledger-fullmag-test-abc123",
            }
            fake = FakeDocker(values)
            layout = {
                "project_id": values["project_id"], "storage_root": values["storage_root"],
                "runs_root": str(root / "runs"),
                "host_ledger_backing_image": values["backing_image"],
                "host_ledger_mount_root": values["mount_root"],
            }
            run_root = root / "runs" / "docker-all" / "run1"
            result = ledger.prepare(layout, repo, IMAGE, run_root, fake)
            self.assertEqual(result["schema"], ledger.SCHEMA)
            self.assertEqual(result["ledger_root"], "/host-ledger/ledger")
            self.assertTrue(Path(result["compose_overlay"]).is_file())
            maintenance = json.loads(Path(result["maintenance_compose"]).read_text())
            self.assertEqual(set(maintenance["services"]), {"host-ledger-maintenance"})
            service = maintenance["services"]["host-ledger-maintenance"]
            self.assertEqual(service["image"], IMAGE)
            self.assertEqual(service["network_mode"], "none")
            self.assertTrue(service["privileged"])
            self.assertEqual(result["environment"]["FULLMAG_HOST_LEDGER_ROOT"], "/host-ledger/ledger")
            self.assertEqual(result["host_receipt"]["filesystem"], "ext4")
            self.assertEqual(result["environment"]["FULLMAG_DOCKER_HOST_ID"], hashlib.sha256(b"desktop-daemon-1").hexdigest())
            self.assertFalse(fake.containers)

    def test_validate_container_requires_rw_parent_and_live_ledger_child(self):
        profile = {
            "profile": ledger.PROFILE, "mount_root": "/mnt/fullmag-host-ledger-test", "image_id": IMAGE,
            "maintenance_compose": "/tmp/compose.host-ledger.maintenance.json", "run_root": "/tmp/run",
            "image_id": IMAGE, "run_id": "a" * 32, "backing_image": "/tmp/storage/build-volumes/" + ledger.IMAGE_NAME,
            "host_receipt": {"filesystem": "ext4", "mount_active": True},
        }
        fake = FakeDocker({"project_id": "test", "backing_image": profile["backing_image"], "mount_root": profile["mount_root"]})
        backend = {
            "Id": "backend-id", "Image": IMAGE, "Config": {"User": "65532:65532", "Env": [
                "FULLMAG_DOCKER_HOST_EXECUTION=1", "FULLMAG_HOST_LEDGER_PROFILE=host-ledger-v1",
                "FULLMAG_HOST_LEDGER_ROOT=/host-ledger/ledger",
            ]},
            "Mounts": [{"Destination": "/host-ledger", "Type": "bind", "RW": True, "Source": profile["mount_root"]}],
            "HostConfig": {"Privileged": False},
        }
        result = ledger.validate_container(backend, profile, fake)
        self.assertEqual(result["host_verification"], "PASS")
        self.assertEqual(result["ledger_root"], "/host-ledger/ledger")
        backend["Mounts"][0]["RW"] = False
        with self.assertRaises(ledger.HostLedgerError):
            ledger.validate_container(backend, profile, fake)


if __name__ == "__main__":
    unittest.main()
