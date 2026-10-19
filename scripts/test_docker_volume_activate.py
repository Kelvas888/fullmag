"""Source-level regressions for managed activation in a retained DEV group."""
from __future__ import annotations

import json
import hashlib
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import docker_volume_activate as activate
from docker_build_control import BuildControlError


class DockerVolumeActivationTests(unittest.TestCase):
    def test_default_request_fence_is_stable_and_bounded(self) -> None:
        attempt = "a" * 32
        digest = "b" * 64
        helper = SimpleNamespace(StartupScriptError=ValueError)
        first = activate._request_id(helper, attempt, digest, None)
        self.assertEqual(first, activate._request_id(helper, attempt, digest, None))
        self.assertLessEqual(len(first), 128)
        self.assertEqual(first, "docker-volume-" + attempt + "-" + digest[:16])

    def test_selected_helper_loader_uses_selected_prepare_contract(self) -> None:
        """The worktree helper must supply prepare, even if the main helper differs."""
        from docker_volume_dev import _startup_helper

        selected_helper = (
            "from pathlib import Path\n"
            "class StartupScriptError(Exception):\n"
            "    pass\n"
            "MAX_PROVENANCE_BYTES = 1024\n"
            "STARTUP_ACTIVATION_TIMEOUT_SECONDS = 17.0\n"
            "ACTIVATION_RECEIPT_PATH = Path('/state/selected/activation.json')\n"
            "def prepare(*args, **kwargs):\n"
            "    return 'selected-helper'\n"
        ).encode()
        selected_storage = b"SELECTED_STORAGE = True\n"
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory)
            scripts = selected / "scripts"
            scripts.mkdir()
            (scripts / "docker_startup_script.py").write_bytes(selected_helper)
            (scripts / "fullmag_storage.py").write_bytes(selected_storage)
            startup_digest = hashlib.sha256(selected_helper).hexdigest()
            storage_digest = hashlib.sha256(selected_storage).hexdigest()

            class Control:
                image = "helper-image"

                def helper_args(self, command):
                    return ["helper-image", command]

            result = subprocess.CompletedProcess(
                [], 0,
                stdout=(
                    f"{startup_digest}  /opt/fullmag/docker_startup_script.py\n"
                    f"{storage_digest}  /opt/fullmag/fullmag_storage.py\n"
                ).encode(),
                stderr=b"",
            )
            with patch("docker_volume_dev.bounded_capture", return_value=result):
                helper, hashes = _startup_helper(
                    Control(), selected, "sha256:" + "a" * 64
                )

        main_helper = SimpleNamespace(prepare=lambda *args, **kwargs: "main-helper")
        self.assertEqual(main_helper.prepare(), "main-helper")
        self.assertEqual(helper.prepare(), "selected-helper")
        self.assertEqual(hashes["docker_startup_script.py"], startup_digest)

    def test_activation_contract_comes_from_selected_helper(self) -> None:
        helper = SimpleNamespace(
            STARTUP_ACTIVATION_TIMEOUT_SECONDS=17.0,
            ACTIVATION_RECEIPT_PATH=Path("/state/selected/activation.json"),
        )
        self.assertEqual(
            activate._activation_contract(helper),
            (77.0, "/state/selected/activation.json"),
        )

    def test_non_object_receipts_fail_closed(self) -> None:
        control = SimpleNamespace(project="fullmag-worktree-demo")
        with self.assertRaises(BuildControlError):
            activate._validate_running_group(
                control, {}, [], {}, "sha256:" + "a" * 64
            )
        with self.assertRaises(BuildControlError):
            activate._linked_runtime_terminals(
                control, "a" * 32, [], source_root="C:/git/fullmag",
                image="sha256:" + "a" * 64, config_sha256="b" * 64,
            )

    def test_activation_output_accepts_only_terminal_json_state(self) -> None:
        payload = b"diagnostic\n" + json.dumps({"state": "activated"}).encode() + b"\n"
        self.assertEqual(activate._json_result(payload)["state"], "activated")
        self.assertIsNone(activate._json_result(b"wrapper failed\n"))

    def _linked_receipt_fixture(self, phase: str = "resume"):
        original_attempt = "a" * 32
        linked_attempt = "b" * 32
        config_sha256 = "c" * 64
        backend_image = "sha256:" + "d" * 64
        original = {
            "schema": "fullmag.docker-build-operation.v1",
            "phase": "development",
            "state": "failed-confirmed",
            "attempt": original_attempt,
            "compose_project": "fullmag-worktree-demo",
            "config_sha256": config_sha256,
            "inputs": {
                "source_root": "C:/git/fullmag",
                "image_id": backend_image,
            },
            "state_root": "C:/fullmag-storage",
            "backend_volumes": ["fullmag-backend-build"],
            "frontend_volume": "fullmag-frontend-build",
            "source_commit": "e" * 40,
            "source_digest": "f" * 64,
            "source_snapshot_sha256": "1" * 64,
            "backend_build_receipt_sha256": "2" * 64,
        }
        linked = {
            "schema": "fullmag.docker-build-operation.v1",
            "phase": phase,
            "state": "succeeded",
            "attempt": linked_attempt,
            "compose_project": original["compose_project"],
            "config_sha256": config_sha256,
            "inputs": {
                "attempt": original_attempt,
                "config_sha256": config_sha256,
            },
            "backend_container": "3" * 64,
            "frontend_container": "4" * 64,
            "state_root": original["state_root"],
            "backend_volumes": original["backend_volumes"],
            "frontend_volume": original["frontend_volume"],
            "source_commit": original["source_commit"],
            "source_digest": original["source_digest"],
            "source_snapshot_sha256": original["source_snapshot_sha256"],
            "backend_build_receipt_sha256": original["backend_build_receipt_sha256"],
        }
        if phase == "iteration":
            linked["inputs"].update(
                source_root=original["inputs"]["source_root"],
                image_id=backend_image,
            )
        documents = {
            phase + "/verified.json": copy.deepcopy(linked),
            phase + "/attempts/" + linked_attempt + "/terminal.json": copy.deepcopy(linked),
        }

        class Control:
            def read(self, relative, *, optional=False):
                if relative not in documents:
                    if optional:
                        return None
                    raise AssertionError("unexpected control read: " + relative)
                return documents[relative]

        return Control(), original_attempt, original, linked, config_sha256, backend_image, documents

    def _retained_group_fixture(self, frontend_image: str | None = None):
        backend_image = "sha256:" + "a" * 64
        frontend_image = frontend_image or "sha256:" + "b" * 64
        backend_id = "c" * 64
        frontend_id = "d" * 64
        document = {
            "name": "fullmag-worktree-demo",
            "services": {
                "backend": {
                    "image": backend_image,
                    "environment": {"FULLMAG_SOURCE_ROOT": "C:/git/fullmag"},
                    "volumes": [{
                        "type": "bind",
                        "source": "C:/git/fullmag",
                        "target": "/opt/fullmag/source",
                        "read_only": True,
                    }],
                },
                "frontend": {
                    "image": frontend_image,
                    "environment": {},
                    "volumes": [],
                },
            },
        }
        terminal = {
            "backend_container": backend_id,
            "frontend_container": frontend_id,
        }
        control = SimpleNamespace(project=document["name"])
        identity = {"worktree_id": "demo-worktree"}
        actual_images = {"backend": backend_image, "frontend": frontend_image}
        image_configs = {
            backend_image: {"Cmd": ["backend-image"]},
            frontend_image: {"Cmd": ["frontend-image"]},
        }
        ids = {"backend": backend_id, "frontend": frontend_id}

        def compose_capture(_document, *arguments):
            return (ids[arguments[-1]] + "\n").encode()

        def docker_text(*arguments, **_kwargs):
            if arguments[:2] == ("image", "inspect"):
                return json.dumps([{"Config": image_configs[arguments[2]]}])
            if arguments[0] == "inspect":
                service = next(name for name, identifier in ids.items() if identifier == arguments[1])
                return json.dumps([{
                    "Id": arguments[1],
                    "Image": actual_images[service],
                    "Config": {
                        "Labels": {
                            "com.docker.compose.project": document["name"],
                            "com.docker.compose.service": service,
                            "org.fullmag.source.worktree-id": identity["worktree_id"],
                        },
                    },
                    "State": {
                        "Running": True,
                        "Health": {"Status": "healthy"},
                    },
                }])
            raise AssertionError(arguments)

        return control, identity, document, terminal, backend_image, compose_capture, docker_text

    def test_linked_resume_and_iteration_receipts_are_accepted(self) -> None:
        for phase in ("resume", "iteration"):
            with self.subTest(phase=phase):
                control, original_attempt, original, linked, config_sha256, image, _documents = (
                    self._linked_receipt_fixture(phase)
                )
                terminals = activate._linked_runtime_terminals(
                    control,
                    original_attempt,
                    original,
                    source_root=original["inputs"]["source_root"],
                    image=image,
                    config_sha256=config_sha256,
                )
                self.assertEqual(terminals, [linked])

    def test_unrelated_resume_does_not_hide_matching_iteration(self) -> None:
        control, original_attempt, original, linked, config_sha256, image, documents = (
            self._linked_receipt_fixture("iteration")
        )
        unrelated = copy.deepcopy(linked)
        unrelated.update(phase="resume", attempt="7" * 32, config_sha256="8" * 64)
        unrelated["inputs"].update(attempt="9" * 32, config_sha256="8" * 64)
        documents["resume/verified.json"] = unrelated
        self.assertEqual(
            activate._linked_runtime_terminals(
                control, original_attempt, original,
                source_root=original["inputs"]["source_root"], image=image,
                config_sha256=config_sha256,
            ),
            [linked],
        )

    def test_linked_receipt_rejects_wrong_attempt_or_config(self) -> None:
        control, original_attempt, original, _linked, config_sha256, image, documents = (
            self._linked_receipt_fixture()
        )
        documents["resume/verified.json"]["inputs"]["attempt"] = "e" * 32
        documents["resume/attempts/" + "b" * 32 + "/terminal.json"]["inputs"]["attempt"] = "e" * 32
        with self.assertRaises(BuildControlError):
            activate._linked_runtime_terminals(
                control,
                original_attempt,
                original,
                source_root=original["inputs"]["source_root"],
                image=image,
                config_sha256=config_sha256,
            )

        control, original_attempt, original, _linked, config_sha256, image, documents = (
            self._linked_receipt_fixture()
        )
        documents["resume/verified.json"]["config_sha256"] = "9" * 64
        documents["resume/attempts/" + "b" * 32 + "/terminal.json"]["config_sha256"] = "9" * 64
        with self.assertRaises(BuildControlError):
            activate._linked_runtime_terminals(
                control,
                original_attempt,
                original,
                source_root=original["inputs"]["source_root"],
                image=image,
                config_sha256=config_sha256,
            )

    def test_linked_receipt_rejects_terminal_or_container_identity_drift(self) -> None:
        control, original_attempt, original, _linked, config_sha256, image, documents = (
            self._linked_receipt_fixture()
        )
        documents["resume/attempts/" + "b" * 32 + "/terminal.json"]["frontend_container"] = "5" * 64
        with self.assertRaises(BuildControlError):
            activate._linked_runtime_terminals(
                control,
                original_attempt,
                original,
                source_root=original["inputs"]["source_root"],
                image=image,
                config_sha256=config_sha256,
            )

        fixture = self._retained_group_fixture()
        control, identity, document, terminal, backend_image, compose, docker_text = fixture
        terminal["frontend_container"] = "e" * 64
        with patch.object(activate, "compose_capture", side_effect=compose), \
                patch.object(activate, "_docker_text", side_effect=docker_text), \
                patch("docker_volume_dev._validate_retained_service"):
            with self.assertRaises(BuildControlError):
                activate._validate_running_group(
                    control, identity, document, terminal, backend_image
                )

    def test_retained_group_accepts_distinct_backend_and_frontend_images(self) -> None:
        fixture = self._retained_group_fixture()
        control, identity, document, terminal, backend_image, compose, docker_text = fixture
        with patch.object(activate, "compose_capture", side_effect=compose), \
                patch.object(activate, "_docker_text", side_effect=docker_text), \
                patch("docker_volume_dev._validate_retained_service") as validator:
            result = activate._validate_running_group(
                control, identity, document, terminal, backend_image
            )
        self.assertEqual(result, ("c" * 64, "d" * 64))
        self.assertEqual(validator.call_count, 2)
        self.assertEqual(validator.call_args_list[0].args[2], "backend")
        self.assertEqual(validator.call_args_list[0].args[3]["Cmd"], ["backend-image"])
        self.assertEqual(validator.call_args_list[1].args[2], "frontend")
        self.assertEqual(validator.call_args_list[1].args[3]["Cmd"], ["frontend-image"])

    def test_retained_group_rejects_frontend_image_drift(self) -> None:
        wrong_frontend = "sha256:" + "e" * 64
        fixture = self._retained_group_fixture(frontend_image=wrong_frontend)
        control, identity, document, terminal, backend_image, compose, docker_text = fixture
        actual = {"backend": backend_image, "frontend": "sha256:" + "f" * 64}
        original = docker_text

        def drifted_docker_text(*arguments, **kwargs):
            value = json.loads(original(*arguments, **kwargs))
            if arguments[0] == "inspect" and arguments[1] == "d" * 64:
                value[0]["Image"] = actual["frontend"]
            return json.dumps(value)

        with patch.object(activate, "compose_capture", side_effect=compose), \
                patch.object(activate, "_docker_text", side_effect=drifted_docker_text), \
                patch("docker_volume_dev._validate_retained_service"):
            with self.assertRaises(BuildControlError):
                activate._validate_running_group(
                    control, identity, document, terminal, backend_image
                )

    def test_fixed_wrapper_loads_dataclass_helper_from_temp_image_path(self) -> None:
        helper = (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Marker:\n"
            "    value: str\n"
            "def run_from_environment():\n"
            "    return {'state': 'activated', 'marker': Marker('loaded').value}\n"
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            helper_path = Path(directory) / "docker_startup_script.py"
            helper_path.write_bytes(helper)
            script = activate.FIXED_ACTIVATION_SCRIPT.replace(
                "/opt/fullmag/docker_startup_script.py",
                str(helper_path),
            )
            environment = {
                "FULLMAG_STARTUP_HELPER_SHA256": hashlib.sha256(helper).hexdigest(),
            }
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", script],
                env={**os.environ, **environment},
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"state": "activated", "marker": "loaded"},
        )


if __name__ == "__main__":
    unittest.main()
