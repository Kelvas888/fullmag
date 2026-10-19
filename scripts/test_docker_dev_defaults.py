"""Interpreted regressions for automatic running-group script defaults."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import docker_dev_defaults as defaults
from docker_build_control import BuildControlError


class DockerDevDefaultsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.main = root / "fullmag"
        self.worktree = root / "worktrees" / "demo"
        self.main.mkdir(parents=True)
        self.worktree.mkdir(parents=True)
        self.known = (self.main, self.worktree)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _defaults(self, repo, *, source=None, port=None, environment=None, cwd=None,
                  dotenv=None, settings=None):
        with patch.object(defaults, "_known_checkouts", return_value=self.known), \
                patch.object(defaults, "_read_dotenv", return_value=dotenv or {}), \
                patch.object(defaults, "_read_host_settings", return_value=settings or {}):
            return defaults.resolve_defaults(
                repo, source_root=source, port=port,
                environ=environment or {}, cwd=cwd or self.main,
            )

    def test_source_priority_is_explicit_then_current_then_configured(self) -> None:
        explicit = self._defaults(
            self.main, source=self.worktree, environment={"FULLMAG_SOURCE_ROOT": str(self.main)},
            settings={"source_root": str(self.main)},
        )
        self.assertEqual(explicit.source_root, self.worktree)
        process = self._defaults(
            self.main, environment={"FULLMAG_SOURCE_ROOT": str(self.worktree)},
            settings={"source_root": str(self.main)},
        )
        self.assertEqual(process.source_root, self.worktree)
        current = self._defaults(
            self.worktree, environment={}, settings={"source_root": str(self.main)},
        )
        self.assertEqual(current.source_root, self.worktree)
        configured = self._defaults(
            self.main, environment={}, settings={"source_root": str(self.worktree)},
        )
        self.assertEqual(configured.source_root, self.worktree)
        dotenv_overrides_saved = self._defaults(
            self.main,
            dotenv={"FULLMAG_SOURCE_ROOT": str(self.main)},
            settings={"source_root": str(self.worktree)},
        )
        self.assertEqual(dotenv_overrides_saved.source_root, self.main)
        fallback = self._defaults(self.main, environment={})
        self.assertEqual(fallback.source_root, self.main)

    def test_port_priority_and_conflicts_fail_closed(self) -> None:
        self.assertEqual(self._defaults(self.main, port=3210).port, 3210)
        self.assertEqual(
            self._defaults(self.main, environment={"FULLMAG_HTTP_PORT": "3211"},
                           settings={"http_port": 3212}).port,
            3211,
        )
        self.assertEqual(
            self._defaults(self.main, environment={}, dotenv={"FULLMAG_HTTP_PORT": "3213"},
                           settings={"http_port": 3212}).port,
            3213,
        )
        self.assertEqual(self._defaults(self.main, settings={"http_port": 3214}).port, 3214)
        self.assertEqual(self._defaults(self.main, environment={}).port, defaults.DEFAULT_PORT)
        with self.assertRaisesRegex(defaults.DiscoveryError, "ambiguous process port"):
            self._defaults(
                self.main,
                environment={"FULLMAG_HTTP_PORT": "3210", "FULLMAG_FRONTEND_HOST_PORT": "3211"},
            )

    def test_bounded_host_defaults_reader_rejects_links_and_large_files(self) -> None:
        path = Path(self.temp.name) / "settings.json"
        path.write_bytes(b"1234")
        self.assertEqual(defaults._bounded_regular(path, 4, "settings"), b"1234")
        path.write_bytes(b"12345")
        with self.assertRaisesRegex(defaults.DiscoveryError, "exceeds"):
            defaults._bounded_regular(path, 4, "settings")
        hardlink = Path(self.temp.name) / "settings-hardlink.json"
        try:
            os.link(path, hardlink)
        except OSError:
            pass
        else:
            with self.assertRaisesRegex(defaults.DiscoveryError, "private regular"):
                defaults._bounded_regular(hardlink, 64, "settings")
        symlink = Path(self.temp.name) / "settings-symlink.json"
        try:
            symlink.symlink_to(path)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaises(defaults.DiscoveryError):
                defaults._bounded_regular(symlink, 64, "settings")

    def test_current_attempt_is_a_freshness_fence_for_verified_receipts(self) -> None:
        current_attempt = "a" * 32
        old_attempt = "b" * 32
        documents = {
            "development/current.json": {"state": "failed-confirmed", "attempt": current_attempt},
            "development/verified.json": {"state": "succeeded", "attempt": old_attempt},
            "resume/verified.json": {
                "state": "succeeded", "inputs": {"attempt": old_attempt},
            },
            "iteration/verified.json": None,
        }

        class Control:
            def read(self, relative, *, optional=False):
                value = documents.get(relative)
                if value is None and optional:
                    return None
                return value

        self.assertEqual(
            defaults._verified_original_attempts(Control(), documents["development/current.json"]),
            [],
        )
        with self.assertRaisesRegex(defaults.DiscoveryError, "current development attempt"):
            defaults._verified_original_attempts(Control(), {"state": "outcome_unknown", "attempt": current_attempt})

        documents["development/verified.json"] = {
            "state": "succeeded", "attempt": current_attempt,
        }
        self.assertEqual(
            defaults._verified_original_attempts(Control(), documents["development/current.json"]),
            [current_attempt],
        )

    def test_running_frontend_port_and_backend_network_are_strict(self) -> None:
        backend_id, frontend_id = "b" * 64, "f" * 64
        inspect = {
            backend_id: {
                "State": {"Running": True, "Health": {"Status": "healthy"}},
                "HostConfig": {"PortBindings": {}, "NetworkMode": "fullmag-net"},
                "NetworkSettings": {"Networks": {"fullmag-net": {}}},
            },
            frontend_id: {
                "State": {"Running": True, "Health": {"Status": "healthy"}},
                "HostConfig": {
                    "PortBindings": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3197"}]},
                },
                "NetworkSettings": {"Networks": {"fullmag-net": {}}},
            },
        }

        def docker_text(*args, **_kwargs):
            if args[0] == "inspect":
                return json.dumps([inspect[args[1]]])
            if args[:2] == ("network", "inspect"):
                return json.dumps([{
                    "Driver": "bridge",
                    "Labels": {"com.docker.compose.project": "fullmag-master"},
                    "Containers": {backend_id: {}, frontend_id: {}},
                }])
            raise AssertionError(args)

        with patch("docker_volume_activate._docker_text", side_effect=docker_text):
            defaults._validate_live_network(backend_id, frontend_id, "fullmag-master", 3197)
        for status in ("starting", "unhealthy"):
            with self.subTest(frontend_health=status):
                inspect[frontend_id]["State"]["Health"]["Status"] = status
                with patch("docker_volume_activate._docker_text", side_effect=docker_text), \
                        self.assertRaisesRegex(defaults.DiscoveryError, "frontend health is not healthy"):
                    defaults._validate_live_network(backend_id, frontend_id, "fullmag-master", 3197)
        inspect[frontend_id]["State"].pop("Health")
        with patch("docker_volume_activate._docker_text", side_effect=docker_text), \
                self.assertRaisesRegex(defaults.DiscoveryError, "frontend health is not healthy"):
            defaults._validate_live_network(backend_id, frontend_id, "fullmag-master", 3197)
        inspect[frontend_id]["State"]["Health"] = {"Status": "healthy"}
        inspect[frontend_id]["HostConfig"]["PortBindings"]["8080/tcp"][0]["HostIp"] = "0.0.0.0"
        with patch("docker_volume_activate._docker_text", side_effect=docker_text), \
                self.assertRaisesRegex(defaults.DiscoveryError, "loopback"):
            defaults._validate_live_network(backend_id, frontend_id, "fullmag-master", 3197)

    def test_discovered_activation_preserves_request_fence(self) -> None:
        pins = defaults.ScriptPins("a" * 32, "b" * 64, self.worktree, 3197)
        args = argparse.Namespace(
            repo_root=self.main, source_root=None, port=None,
            script=Path("examples/model.py"), request_id="stable-request",
        )
        with patch.object(defaults, "resolve_defaults", return_value=defaults.ScriptDefaults(self.worktree, 3197)), \
                patch.object(defaults, "_discover_pins", return_value=pins), \
                patch("docker_dev._require_native_windows", side_effect=AssertionError("legacy Windows gate")), \
                patch("docker_volume_activate.activate") as activate:
            defaults.activate_discovered(args)
        forwarded = activate.call_args.args[0]
        self.assertEqual(forwarded.attempt, "a" * 32)
        self.assertEqual(forwarded.config_sha256, "b" * 64)
        self.assertEqual(forwarded.request_id, "stable-request")
        self.assertEqual(forwarded.script, Path("examples/model.py"))

    def _up_args(self, *, script=None):
        return argparse.Namespace(
            repo_root=self.main,
            source_root=self.worktree,
            port=3197,
            gpu_access="auto",
            profile="dev",
            image=None,
            toolchain_image=None,
            source_manifest=None,
            include_untracked=[],
            script=script,
        )

    def test_reuse_existing_is_a_noop_for_one_healthy_pair(self):
        pins = defaults.ScriptPins("a" * 32, "b" * 64, self.worktree, 3197)
        with patch.object(defaults, "require_host"), \
                patch.object(defaults, "_discover_pins", return_value=pins), \
                patch("builtins.print") as output:
            self.assertTrue(defaults.reuse_existing(self._up_args()))
        output.assert_called_once_with(
            "docker-dev: reused healthy running group " + "a" * 32 + " on port 3197"
        )

    def test_reuse_existing_uses_existing_activation_lifecycle_for_script(self):
        pins = defaults.ScriptPins("a" * 32, "b" * 64, self.worktree, 3197)
        args = self._up_args(script=Path("examples/model.py"))
        with patch.object(defaults, "require_host"), \
                patch.object(defaults, "_discover_pins", return_value=pins) as discover, \
                patch.object(defaults, "activate_discovered") as activate:
            self.assertTrue(defaults.reuse_existing(args))
        discover.assert_called_once_with(
            self.main,
            defaults.ScriptDefaults(self.worktree, 3197),
            requested_port=3197,
            requested_gpu_access="auto",
            allow_missing_control=True,
        )
        activate.assert_called_once_with(args, pins=pins)

    def test_reuse_existing_does_not_bypass_explicit_nondefault_inputs(self):
        for name, value in (
            ("profile", "release"),
            ("image", "sha256:" + "a" * 64),
            ("toolchain_image", "sha256:" + "b" * 64),
            ("source_manifest", Path("manifest.json")),
            ("include_untracked", ["new.py"]),
        ):
            with self.subTest(name=name):
                args = self._up_args()
                setattr(args, name, value)
                with patch.object(defaults, "require_host"), \
                        patch.object(defaults, "_discover_pins") as discover:
                    self.assertFalse(defaults.reuse_existing(args))
                discover.assert_not_called()

    def test_reuse_existing_allows_only_the_initial_no_namespace_case(self):
        with patch.object(defaults, "require_host"), \
                patch.object(defaults, "_discover_pins", return_value=None):
            self.assertFalse(defaults.reuse_existing(self._up_args()))

    def test_reuse_existing_fails_closed_with_recovery_for_stale_or_ambiguous_state(self):
        for detail in (
            "stopped backend",
            "unhealthy backend",
            "multiple validated healthy running DEV groups",
            "foreign control volume",
            "config mismatch",
        ):
            with self.subTest(detail=detail), \
                    patch.object(defaults, "require_host"), \
                    patch.object(defaults, "_discover_pins",
                                  side_effect=defaults.DiscoveryError(detail)):
                with self.assertRaisesRegex(
                    defaults.DiscoveryError,
                    r"docker-dev-resume|docker-dev-recreate-volume",
                ) as raised:
                    defaults.reuse_existing(self._up_args())
                self.assertIn(detail, str(raised.exception))

    def test_just_keeps_discovery_and_pinned_activation_as_distinct_routes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        justfile = (root / "justfile").read_text(encoding="utf-8")
        shell = (root / "scripts" / "just_storage_shell.sh").read_text(encoding="utf-8")
        self.assertIn("docker-dev-script script source_root=\"\" port=\"\"", justfile)
        self.assertIn("docker-dev-script-pinned attempt config_sha256 source_root script", justfile)
        self.assertIn("script --script", shell)
        self.assertIn("activate-script --attempt", shell)


    def test_up_and_toolchain_choose_the_same_configured_checkout(self):
        import docker_dev
        import bootstrap_docker_toolchain as bootstrap
        selected = defaults.ScriptDefaults(self.worktree, 32900)
        with patch.object(defaults, "resolve_defaults", return_value=selected), \
                patch.object(docker_dev, "_require_native_windows"), \
                patch.object(docker_dev, "up") as up:
            self.assertEqual(docker_dev.main(["--repo-root", str(self.main), "up"]), 0)
        args = up.call_args.args[0]
        self.assertEqual((args.source_root, args.port), (self.worktree, 32900))
        with patch.object(defaults, "resolve_defaults", return_value=selected), \
                patch.object(docker_dev, "_require_native_windows"), \
                patch.object(bootstrap, "build", return_value={}) as build:
            self.assertEqual(bootstrap.main(["--repo-root", str(self.main), "--direct-development"]), 0)
        self.assertEqual(build.call_args.args[0], self.worktree)

    @unittest.skipUnless(os.name == "posix", "POSIX executable shell fixture")
    def test_shell_forwards_default_and_explicit_arguments_without_storage_writer(self):
        root = Path(__file__).resolve().parents[1]
        probe = Path(self.temp.name) / "python-probe"
        probe.write_text(f"#!{sys.executable}\nimport json, sys\n"
                         "if sys.argv[1:2] != ['-c']: print(json.dumps(sys.argv[1:]))\n")
        probe.chmod(0o700)
        prefix = f'python3 "{root}/scripts/docker_dev.py" --repo-root "{root}" '
        for body, expected in (
            ("up  --gpu-access 'auto'", ["up", "--gpu-access", "auto"]),
            ("up --port '32900' --gpu-access 'required' --source-root '/selected source' --script 'examples/a.py'",
             ["up", "--port", "32900", "--gpu-access", "required", "--source-root", "/selected source", "--script", "examples/a.py"]),
            ("script --script 'examples/a.py'", ["script", "--script", "examples/a.py"]),
        ):
            result = subprocess.run(["bash", str(root / "scripts/just_storage_shell.sh"), prefix + body],
                                    env={**os.environ, "FULLMAG_STORAGE_PYTHON": str(probe)},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = json.loads(result.stdout)
            self.assertEqual(actual[3:], expected)
            self.assertNotIn("fullmag_storage.py", actual[0])

    def _discovery_control(self, current):
        project = "fullmag-worktree-demo"
        image = "sha256:" + "c" * 64
        control = SimpleNamespace(
            project=project,
            volume="owned-control",
            shared_labels={"owner": "selected"},
            read=Mock(return_value=current),
        )
        config = {"services": {"fem-gpu-toolchain": {"build": {"args": {
            "FULLMAG_CUDA_BASE_IMAGE": image
        }}}}}
        return control, config

    def test_discovery_missing_control_volume_requires_exact_error_and_bounded_listing(self):
        control, config = self._discovery_control(None)
        calls = []

        def docker_text(*args, **kwargs):
            calls.append((args, kwargs))
            if args[:2] == ("volume", "inspect"):
                raise BuildControlError(
                    "Error response from daemon: get " + control.volume + ": no such volume"
                )
            if args[:2] == ("volume", "ls"):
                self.assertEqual(kwargs.get("timeout"), 60)
                return "x" * (defaults._MAX_VOLUME_LIST_BYTES + 1)
            raise AssertionError(args)

        with patch.object(defaults, "require_host"), \
                patch("docker_development_inputs.select_checkout", return_value=self.worktree), \
                patch("fullmag_storage.resolve_layout", return_value={}), \
                patch("docker_dev._compose_identity", return_value={"worktree_id": "demo"}), \
                patch.object(defaults, "toolchain_configuration", return_value=config), \
                patch.object(defaults, "BuildControl", return_value=control), \
                patch("docker_volume_activate._docker_text", side_effect=docker_text):
            with self.assertRaisesRegex(defaults.DiscoveryError, "bounded size"):
                defaults._discover_pins(
                    self.main, defaults.ScriptDefaults(self.worktree, 3197),
                    allow_missing_control=True,
                )
        self.assertEqual([item[0][:2] for item in calls], [("volume", "inspect"), ("volume", "ls")])

    def test_discovery_missing_control_volume_returns_none_only_after_listing_confirms_absence(self):
        control, config = self._discovery_control(None)
        calls = []

        def docker_text(*args, **kwargs):
            calls.append(args)
            if args[:2] == ("volume", "inspect"):
                raise BuildControlError(
                    "Error response from daemon: get " + control.volume + ": no such volume"
                )
            if args[:2] == ("volume", "ls"):
                self.assertEqual(kwargs.get("timeout"), 60)
                return "other-volume\n"
            raise AssertionError(args)

        with patch.object(defaults, "require_host"), \
                patch("docker_development_inputs.select_checkout", return_value=self.worktree), \
                patch("fullmag_storage.resolve_layout", return_value={}), \
                patch("docker_dev._compose_identity", return_value={"worktree_id": "demo"}), \
                patch.object(defaults, "toolchain_configuration", return_value=config), \
                patch.object(defaults, "BuildControl", return_value=control), \
                patch("docker_volume_activate._docker_text", side_effect=docker_text):
            result = defaults._discover_pins(
                self.main, defaults.ScriptDefaults(self.worktree, 3197),
                allow_missing_control=True,
            )
        self.assertIsNone(result)
        self.assertEqual(calls, [
            ("volume", "inspect", control.volume),
            ("volume", "ls", "--format", "{{.Name}}"),
        ])

    def test_discovery_missing_current_is_initial_start_but_malformed_current_is_not(self):
        control, config = self._discovery_control(None)
        valid_volume = json.dumps([{
            "Name": control.volume, "Driver": "local", "Options": None,
            "Labels": {"owner": "selected"},
        }])
        with patch.object(defaults, "require_host"), \
                patch("docker_development_inputs.select_checkout", return_value=self.worktree), \
                patch("fullmag_storage.resolve_layout", return_value={}), \
                patch("docker_dev._compose_identity", return_value={"worktree_id": "demo"}), \
                patch.object(defaults, "toolchain_configuration", return_value=config), \
                patch.object(defaults, "BuildControl", return_value=control), \
                patch("docker_volume_activate._docker_text", return_value=valid_volume):
            self.assertIsNone(defaults._discover_pins(
                self.main, defaults.ScriptDefaults(self.worktree, 3197),
                allow_missing_control=True,
            ))
            control.read.return_value = {"state": "succeeded"}
            with self.assertRaisesRegex(defaults.DiscoveryError, "valid attempt fence"):
                defaults._discover_pins(
                    self.main, defaults.ScriptDefaults(self.worktree, 3197),
                    allow_missing_control=True,
                )

    def test_discovery_deduplicates_one_live_pair_and_uses_its_overridden_port(self):
        attempt = "a" * 32
        project = "fullmag-worktree-demo"
        image = "sha256:" + "c" * 64
        document = {"name": project, "services": {"frontend": {"ports": [{"published": "32900"}]}}}
        terminal = {"compose_project": project, "inputs": {
            "source_root": str(self.worktree), "image_id": image,
            "gpu_access_requested": "auto"}}
        docs = {"development/current.json": {"attempt": attempt},
                "development/attempts/" + attempt + "/terminal.json": terminal,
                "development/attempts/" + attempt + "/compose.json": document}
        control = SimpleNamespace(project=project, volume="owned-control", shared_labels={"owner": "selected"}, read=Mock(side_effect=lambda path, **kw: docs[path]))
        config = {"services": {"fem-gpu-toolchain": {"build": {"args": {"FULLMAG_CUDA_BASE_IMAGE": image}}}}}
        with patch("docker_dev._require_native_windows", side_effect=AssertionError("legacy Windows gate")), \
                patch("docker_development_inputs.select_checkout", return_value=self.worktree), \
                patch("fullmag_storage.resolve_layout", return_value={}), \
                patch("docker_dev._compose_identity", return_value={"worktree_id": "demo"}), \
                patch.object(defaults, "toolchain_configuration", return_value=config), \
                patch.object(defaults, "BuildControl", return_value=control), \
                patch("docker_volume_activate._docker_text", return_value=json.dumps([{"Name": "owned-control", "Driver": "local", "Options": None, "Labels": {"owner": "selected"}}])), \
                patch.object(defaults, "_verified_original_attempts", return_value=[attempt]), \
                patch("docker_volume_activate._linked_runtime_terminals", return_value=[{}, {}]), \
                patch("docker_volume_activate._validate_running_group", return_value=("b" * 64, "f" * 64)), \
                patch.object(defaults, "_validate_live_network") as network:
            result = defaults._discover_pins(self.main, defaults.ScriptDefaults(self.worktree, 3197))
            self.assertEqual(result.port, 32900)
            self.assertEqual(result.attempt, attempt)
            self.assertEqual(network.call_args.args[-1], 32900)
            result = defaults._discover_pins(
                self.main, defaults.ScriptDefaults(self.worktree, 32900),
                requested_gpu_access="auto",
            )
            self.assertEqual(result.attempt, attempt)
            with self.assertRaisesRegex(defaults.DiscoveryError, "no exactly validated"):
                defaults._discover_pins(
                    self.main, defaults.ScriptDefaults(self.worktree, 32900),
                    requested_gpu_access="disabled",
                )
            with self.assertRaises(defaults.DiscoveryError):
                defaults._discover_pins(self.main, defaults.ScriptDefaults(self.worktree, 3197), requested_port=3197)
            control.read.reset_mock()
            with patch("docker_volume_activate._docker_text", side_effect=defaults.DiscoveryError("missing volume")):
                with self.assertRaisesRegex(defaults.DiscoveryError, "missing volume"):
                    defaults._discover_pins(self.main, defaults.ScriptDefaults(self.worktree, 3197))
            control.read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
