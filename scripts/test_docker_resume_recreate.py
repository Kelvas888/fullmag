"""Resume only a pinned completed removal; preserve its original state."""
import hashlib
import json
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import docker_dev
import docker_volume_dev as dev
import docker_volume_stop_unadmitted as stop


class ResumeRecreateTests(unittest.TestCase):
    def setUp(self):
        self.args = SimpleNamespace(attempt="a" * 32, recreate_attempt="b" * 32,
                                    recreate_receipt_sha256="", config_sha256="")
        self.control = Mock(project="fullmag-master", volume="control", identity={})
        self.selected = Path("/source")
        self.layout = {"runtime_root": "/runtime"}
        self.document = {"name": "fullmag-master", "services": {}}
        self.args.config_sha256 = hashlib.sha256(dev.canonical(self.document)).hexdigest()
        self.operator = dev._operator_probe_record(docker_dev.OPERATOR_PROBE_ENVIRONMENT_DEFAULTS)
        self.previous = {
            "attempt": self.args.attempt, "state": "succeeded", "compose_project": "fullmag-master",
            "inputs": {"source_root": "/source", "image_id": "sha256:" + "f" * 64},
            "state_root": "/runtime/sessions", "backend_volumes": ["cache"],
            "frontend_volume": "frontend", "backend_container": "c" * 64,
            "frontend_container": "d" * 64,
        }
        self.receipt = {
            "attempt": self.args.recreate_attempt, "phase": "recreate-services", "state": "succeeded",
            "compose_project": "fullmag-master", "control_volume": "control", "fresh_state": False,
            "inputs": {"attempt": self.args.attempt, "config_sha256": self.args.config_sha256},
            "previous_state_root": "/runtime/sessions", "retained_volumes": ["cache"],
            "retained_frontend_volume": "frontend", "removed_containers": ["c" * 64, "d" * 64],
            **self.operator,
        }
        self.retained = {service: {"Id": self.previous[service + "_container"],
                                  "Image": self.previous["inputs"]["image_id"]}
                         for service in ("backend", "frontend")}
        self.control.read.side_effect = lambda path: (
            self.document if path.endswith("compose.json") else
            self.retained if path.endswith("retained-containers.json") else self.previous
        )
        self.context = {"previous_config_sha256": "e" * 64,
                        "native_restart_metadata": {"pinned": True}}
        self.inventory = ""
        self.inspect = CompletedProcess([], 1, b"", b"error: no such object: " + b"c" * 64 + b"\n")
        patches = [
            patch.object(stop, "_control_bytes", side_effect=lambda *a, **kw: self.raw),
            patch.object(dev, "docker_text", side_effect=lambda *a: (
                json.dumps([{"Config": {}}]) if a[0] == "image" else self.inventory)),
            patch.object(dev, "docker_capture", side_effect=lambda *a, **kw: self.inspect),
            patch("docker_compose_identity.validate_source_labels"),
            patch.object(dev, "_validate_retained_service"),
            patch.object(dev.storage, "validate_path", side_effect=lambda path, *a: path),
            patch.object(dev, "_retained_certificate", return_value={
                "image_id": self.previous["inputs"]["image_id"], "restart_verified": True}),
            patch.object(dev, "_operator_probe_record_from_retained", return_value=self.operator),
            patch.object(dev, "_native_failed_stop_recovery_context", return_value=self.context),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.pin_receipt()

    def pin_receipt(self):
        self.raw = dev.canonical(self.receipt) + b"\n"
        self.args.recreate_receipt_sha256 = hashlib.sha256(self.raw).hexdigest()

    def resume_context(self):
        return dev._resume_recreate_context(self.control, self.args, self.selected, self.layout)

    def test_preserves_original_storage_and_native_restart_context(self):
        reuse, context = self.resume_context()
        self.assertEqual(reuse["state"], Path("/runtime/sessions"))
        self.assertEqual(reuse["operator_probe_environment_record"], self.operator)
        self.assertEqual(context, self.context)
        dev._native_failed_stop_recovery_context.assert_called_once_with(
            self.control, self.previous, backend_id="c" * 64, fresh_state=False,
            removed_backend=self.retained["backend"])

    def test_refuses_changed_receipt_inventory_or_unknown_inspect(self):
        self.raw += b" "
        with self.assertRaisesRegex(dev.BuildControlError, "receipt changed"):
            self.resume_context()
        self.pin_receipt()
        self.inventory = "foreign-container"
        with self.assertRaisesRegex(dev.BuildControlError, "services absent"):
            self.resume_context()
        self.inventory = ""
        self.inspect = CompletedProcess([], 1, b"", b"Cannot connect to Docker")
        with self.assertRaisesRegex(dev.BuildControlError, "absence is unconfirmed"):
            self.resume_context()

    def test_refuses_fresh_state_wrong_removed_id_or_storage_drift(self):
        for key, value in [("fresh_state", True), ("removed_containers", ["e" * 64]),
                           ("previous_state_root", "/runtime/other"),
                           ("retained_volumes", ["other-cache"])]:
            with self.subTest(key=key):
                old = self.receipt[key]
                self.receipt[key] = value
                self.pin_receipt()
                with self.assertRaises(dev.BuildControlError):
                    self.resume_context()
                self.receipt[key] = old

    def test_cli_dispatches_explicit_pins(self):
        argv = ["resume-recreate-volume", "--attempt", "a" * 32,
                "--config-sha256", "c" * 64, "--recreate-attempt", "b" * 32,
                "--recreate-receipt-sha256", "d" * 64,
                "--source-root", "/source", "--port", "3197"]
        with patch.object(dev, "resume_recreate") as resume:
            self.assertEqual(docker_dev.main(argv), 0)
        self.assertEqual(resume.call_args.args[0].recreate_attempt, "b" * 32)
        self.assertIsNone(resume.call_args.args[0].script)


if __name__ == "__main__":
    unittest.main()
