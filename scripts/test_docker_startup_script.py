"""Interpreted regressions for the Docker startup-script admission boundary."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import docker_startup_script as startup
import fullmag_docker_runtime as docker_runtime


class DockerStartupScriptTests(unittest.TestCase):
    def write_script(self, root: Path, relative: str = "models/scene.py") -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("import fullmag as fm\nfm.interactive(True)\n", encoding="utf-8")
        return path

    def test_prepare_pins_relative_path_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            script = self.write_script(root)
            authorization = startup.prepare(
                root,
                Path("models") / "scene.py",
                request_id="startup-test-1",
                source_commit="a" * 40,
            )
            self.assertEqual(authorization.source_relative, "models/scene.py")
            self.assertEqual(authorization.container_script_path, "/opt/fullmag/source/models/scene.py")
            self.assertEqual(
                authorization.source_sha256,
                hashlib.sha256(script.read_bytes()).hexdigest(),
            )
            request = startup.build_activation_request(authorization.as_dict())
            self.assertEqual(request["schema"], startup.REQUEST_SCHEMA)
            self.assertEqual(request["source"]["sha256"], authorization.source_sha256)
            self.assertTrue(request["execution"]["auto_study"])
            self.assertEqual(request["execution"]["wait_for_solve"], "script_metadata")
            self.assertFalse(request["execution"]["legacy_cli"])
            self.assertTrue(startup.STARTUP_ENDPOINT.startswith("/v1/internal/live/current/"))
            self.assertEqual(startup.MAX_SCRIPT_BYTES, 1024 * 1024)

    def test_prepare_rejects_symlink_and_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.write_script(root)
            outside = root.parent / (root.name + "-outside.py")
            outside.write_text("print('outside')\n", encoding="utf-8")
            link = root / "link.py"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlinks unavailable: {error}")
            with self.assertRaises(startup.StartupScriptError):
                startup.prepare(root, link, request_id="startup-test-2")
            with self.assertRaises(startup.StartupScriptError):
                startup.prepare(root, "../" + outside.name, request_id="startup-test-3")

    def test_provenance_is_exclusive_and_digest_is_attested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            script = self.write_script(root)
            authorization = startup.prepare(root, script, request_id="startup-test-provenance")
            target = root / "startup-provenance.json"
            observed = startup.write_provenance(target, authorization)
            self.assertEqual(observed, hashlib.sha256(target.read_bytes()).hexdigest())
            with self.assertRaisesRegex(startup.StartupScriptError, "already exists"):
                startup.write_provenance(target, authorization)

    def test_activation_response_requires_pinned_request_and_hash(self) -> None:
        authorization = {
            "schema": startup.AUTHORIZATION_SCHEMA,
            "authorization": startup.AUTHORIZATION_KIND,
            "request_id": "startup-test-4",
            "source_sha256": "b" * 64,
            "source_size_bytes": 2,
        }
        response = {
            "schema": startup.RESPONSE_SCHEMA,
            "authorization": startup.AUTHORIZATION_KIND,
            "request_id": "startup-test-4",
            "source_sha256": "b" * 64,
            "status": "waiting_for_solve",
            "execution": {
                "mode": "canonical_live_v2",
                "auto_study": True,
                "interactive": "script_metadata",
                "wait_for_solve": "script_metadata",
                "legacy_cli": False,
            },
        }
        self.assertEqual(startup.validate_activation_response(response, authorization), response)
        for field, value in (("request_id", "other"), ("source_sha256", "c" * 64)):
            tampered = dict(response)
            tampered[field] = value
            with self.assertRaises(startup.StartupScriptError):
                startup.validate_activation_response(tampered, authorization)

    def test_activation_uses_bounded_mesh_compatible_default_timeout(self) -> None:
        authorization = {
            "schema": startup.AUTHORIZATION_SCHEMA,
            "authorization": startup.AUTHORIZATION_KIND,
            "request_id": "startup-test-timeout",
            "source_sha256": "b" * 64,
            "source_relative": "models/scene.py",
            "container_script_path": "/opt/fullmag/source/models/scene.py",
            "container_source_root": "/opt/fullmag/source",
        }
        response = {
            "schema": startup.RESPONSE_SCHEMA,
            "authorization": startup.AUTHORIZATION_KIND,
            "request_id": authorization["request_id"],
            "source_sha256": authorization["source_sha256"],
            "status": "waiting_for_solve",
            "execution": {
                "mode": "canonical_live_v2",
                "auto_study": True,
                "interactive": "script_metadata",
                "wait_for_solve": "script_metadata",
                "legacy_cli": False,
            },
        }

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _maximum):
                return json.dumps(response).encode("utf-8")

        observed = {}

        class Opener:
            def open(self, _request, *, timeout):
                observed["timeout"] = timeout
                return Response()

        with mock.patch.object(startup.urllib.request, "build_opener", return_value=Opener()):
            result = startup.activate(authorization)
        self.assertEqual(result, response)
        self.assertEqual(observed["timeout"], startup.STARTUP_ACTIVATION_TIMEOUT_SECONDS)
        self.assertEqual(startup.STARTUP_ACTIVATION_TIMEOUT_SECONDS, 1800.0)

    def test_activation_rejects_unbounded_timeout(self) -> None:
        authorization = {
            "schema": startup.AUTHORIZATION_SCHEMA,
            "authorization": startup.AUTHORIZATION_KIND,
            "request_id": "startup-test-timeout-bound",
            "source_sha256": "b" * 64,
            "source_relative": "models/scene.py",
            "container_script_path": "/opt/fullmag/source/models/scene.py",
            "container_source_root": "/opt/fullmag/source",
        }
        with self.assertRaisesRegex(startup.StartupScriptError, "between 0 and 1800"):
            startup.activate(authorization, timeout=1801)

    def test_activation_response_rejects_legacy_cli_claim(self) -> None:
        authorization = {
            "schema": startup.AUTHORIZATION_SCHEMA,
            "authorization": startup.AUTHORIZATION_KIND,
            "request_id": "startup-test-5",
            "source_sha256": "d" * 64,
        }
        response = {
            "schema": startup.RESPONSE_SCHEMA,
            "authorization": startup.AUTHORIZATION_KIND,
            "request_id": "startup-test-5",
            "source_sha256": "d" * 64,
            "status": "accepted",
            "execution": {
                "mode": "canonical_live_v2",
                "auto_study": True,
                "interactive": "script_metadata",
                "wait_for_solve": "script_metadata",
                "legacy_cli": True,
            },
        }
        with self.assertRaises(startup.StartupScriptError):
            startup.validate_activation_response(response, authorization)

    def test_activation_response_requires_the_complete_live_execution_contract(self) -> None:
        authorization = {
            "schema": startup.AUTHORIZATION_SCHEMA,
            "authorization": startup.AUTHORIZATION_KIND,
            "request_id": "startup-test-6",
            "source_sha256": "e" * 64,
        }
        response = {
            "schema": startup.RESPONSE_SCHEMA,
            "authorization": startup.AUTHORIZATION_KIND,
            "request_id": "startup-test-6",
            "source_sha256": "e" * 64,
            "status": "ready",
            "execution": {
                "mode": "canonical_live_v2",
                "auto_study": True,
                "interactive": "script_metadata",
                "wait_for_solve": "script_metadata",
                "legacy_cli": False,
            },
        }
        for field in ("mode", "auto_study", "interactive", "wait_for_solve", "legacy_cli"):
            tampered = json.loads(json.dumps(response))
            tampered["execution"].pop(field)
            with self.subTest(field=field), self.assertRaises(startup.StartupScriptError):
                startup.validate_activation_response(tampered, authorization)

    def test_overlay_is_readonly_and_mounts_selected_checkout_only_when_enabled(self) -> None:
        authorization = {
            "source_root": "/host/checkout",
            "container_script_path": "/opt/fullmag/source/examples/start.py",
        }
        with tempfile.TemporaryDirectory() as temporary:
            overlay = Path(temporary) / "compose.startup.json"
            docker_runtime._write_startup_overlay(
                overlay, authorization, include_source=True,
                provenance_sha256="a" * 64, helper_sha256="b" * 64,
            )
            document = json.loads(overlay.read_text(encoding="utf-8"))
            service = document["services"]["backend"]
            self.assertEqual(service["environment"]["FULLMAG_STARTUP_ENABLED"], "1")
            self.assertEqual(
                service["environment"]["FULLMAG_STARTUP_SCRIPT"],
                authorization["container_script_path"],
            )
            self.assertEqual(service["environment"]["FULLMAG_STARTUP_PROVENANCE_SHA256"], "a" * 64)
            self.assertEqual(service["environment"]["FULLMAG_STARTUP_HELPER_SHA256"], "b" * 64)
            self.assertEqual(
                {mount["target"] for mount in service["volumes"]},
                {"/opt/fullmag/source", "/run/fullmag/startup-provenance.json"},
            )
            self.assertTrue(all(mount["read_only"] for mount in service["volumes"]))
            docker_runtime._write_startup_overlay(overlay, authorization, include_source=False)
            document = json.loads(overlay.read_text(encoding="utf-8"))
            self.assertEqual(
                [mount["target"] for mount in document["services"]["backend"]["volumes"]],
                ["/run/fullmag/startup-provenance.json"],
            )

    def test_entrypoint_does_not_reintroduce_scratch_cli(self) -> None:
        entrypoint = Path(__file__).parents[1] / "docker/all-in-one/entrypoint.py"
        text = entrypoint.read_text(encoding="utf-8")
        self.assertIn("docker_startup_script.run_from_environment()", text)
        self.assertIn("/opt/fullmag/docker_startup_script.py", text)
        self.assertNotIn("/opt/fullmag/source/scripts", text)
        self.assertLess(text.index("startup_result = activate_startup_script()"),
                        text.index('receipt.update(state="ready"'))
        self.assertNotIn("fullmag-bin", text)

    def test_entrypoint_rejects_partial_startup_environment(self) -> None:
        entrypoint = Path(__file__).parents[1] / "docker/all-in-one/entrypoint.py"
        spec = importlib.util.spec_from_file_location("fullmag_all_in_one_entrypoint", entrypoint)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with mock.patch.dict(
            os.environ,
            {"FULLMAG_STARTUP_API": "http://127.0.0.1:8081"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "environment is incomplete"):
                module.activate_startup_script()


if __name__ == "__main__":
    unittest.main()
