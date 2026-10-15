"""Interpreted contract checks for the Docker Control Room dev supervisor.

This deliberately avoids pnpm, Node, Docker, Rust, and compiled test targets.
It exercises the bounded manifest/freeze boundary, managed links, dependency
cache reconciliation, and owned-child shutdown receipt semantics.
"""
from __future__ import annotations

import hashlib
import io
import importlib.util
import json
import os
import runpy
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from types import ModuleType
from unittest import TestCase, main, skipIf
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "docker" / "all-in-one" / "frontend_dev.py"
HEALTHCHECK_PATH = MODULE_PATH.with_name("healthcheck.py")


def load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fullmag_frontend_dev_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frontend_dev.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _DeadProcess:
    pid = 49152

    def __init__(self, returncode: int):
        self.returncode = returncode
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def wait(self, timeout):
        return self.returncode


class _RunningProcess:
    pid = 49153

    def __init__(self):
        self.returncode = None
        self.terminated = False

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.returncode = -signal.SIGTERM
        return self.returncode

    def terminate(self):
        self.terminated = True
        raise AssertionError("stop must signal the owned process group")


@contextmanager
def isolated(module):
    with tempfile.TemporaryDirectory(prefix="fullmag-frontend-dev-") as raw:
        root = Path(raw)
        workspace = root / "workspace"
        app = workspace / "apps" / "control-room"
        for name in module.LIVE_DIRECTORY_NAMES:
            (app / name).mkdir(parents=True)
        seed = {
            "package.json": b'{"name":"fullmag"}\n',
            "pnpm-lock.yaml": b"lockfileVersion: 9.0\n",
            "pnpm-workspace.yaml": b"packages:\n  - apps/*\n",
            "apps/control-room/package.json": b'{"name":"@fullmag/control-room"}\n',
            "apps/control-room/next.config.ts": b"export default {};\n",
            "apps/control-room/tsconfig.json": b'{"compilerOptions":{}}\n',
            "apps/control-room/next-env.d.ts": b"/// <reference types=\"next\" />\n",
        }
        for relative, data in seed.items():
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        manifest = {
            "schema": module.INPUTS_SCHEMA,
            "source_root": r"C:\git\fullmag\fullmag",
            "source_commit": "0" * 40,
            "host_port": 3197,
            "workspace_root": str(workspace),
            "frontend_root": str(root / "cache"),
            "files": [
                {"relative": relative, "sha256": hashlib.sha256(data).hexdigest()}
                for relative, data in seed.items()
            ],
            "live_directories": list(module.LIVE_DIRECTORY_NAMES),
        }
        inputs_path = root / "development-inputs.json"
        inputs_path.write_text(json.dumps(manifest), encoding="utf-8")
        names = {
            "INPUTS_PATH": inputs_path,
            "DEVELOPMENT_ROOT": root,
            "WORKSPACE_ROOT": workspace,
            "FRONTEND_ROOT": root / "cache",
            "PNPM_STORE_ROOT": root / "pnpm-store",
            "PNPM_HOME": root / "pnpm-home",
            "COREPACK_HOME": root / "corepack",
            "HOME_ROOT": root / "home",
            "TEMP_ROOT": root / "tmp",
            "FREEZE_ROOT": root / "frozen-inputs",
            "FREEZE_PATH": root / "inputs-freeze.json",
            "RECEIPT_PATH": root / "frontend-dev-receipt.json",
            "LOG_PATH": root / "next.log",
            "RUNTIME_LOCK_PATH": root / "cache" / ".fullmag-frontend-runtime.lock",
        }
        (root / "cache").mkdir(parents=True, exist_ok=True)
        runtime_lock = root / "cache" / ".fullmag-frontend-runtime.lock"
        runtime_lock.write_bytes(b"")
        runtime_lock.chmod(0o660)
        old = {name: getattr(module, name) for name in names}
        for name, value in names.items():
            setattr(module, name, value)
        try:
            yield root, workspace, module.read_inputs(inputs_path)
        finally:
            for name, value in old.items():
                setattr(module, name, value)


class FrontendDevContractTests(TestCase):
    def setUp(self):
        self.module = load_module()

    def test_enabled_requires_exact_dev_mode(self):
        self.assertTrue(self.module.enabled({"FULLMAG_DOCKER_FRONTEND": "dev"}))
        self.assertFalse(self.module.enabled({"FULLMAG_DOCKER_FRONTEND": "DEV"}))
        self.assertFalse(self.module.enabled({}))
        self.assertEqual(self.module.EXPECTED_PNPM_VERSION, "10.8.1")

    def test_frontend_healthcheck_requires_workspace_2xx_without_redirect(self):
        import urllib.error
        import urllib.request

        class Response:
            def __init__(self, status):
                self.status = status

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Opener:
            def __init__(self, status):
                self.status = status
                self.requests = []

            def open(self, request, timeout):
                self.requests.append((request, timeout))
                if self.status != 200:
                    raise urllib.error.HTTPError(
                        request.full_url,
                        self.status,
                        "mock healthcheck response",
                        {},
                        None,
                    )
                return Response(self.status)

        for status in (200, 307, 500):
            with self.subTest(status=status):
                opener = Opener(status)
                with patch.dict(
                    os.environ,
                    {"FULLMAG_DOCKER_ROLE": "frontend", "FULLMAG_DOCKER_FRONTEND": "dev"},
                    clear=False,
                ):
                    with patch.object(urllib.request, "build_opener", return_value=opener):
                        if status == 200:
                            runpy.run_path(str(HEALTHCHECK_PATH), run_name="__main__")
                        else:
                            with self.assertRaises(urllib.error.HTTPError) as raised:
                                runpy.run_path(str(HEALTHCHECK_PATH), run_name="__main__")
                            self.assertEqual(raised.exception.code, status)
                self.assertEqual(len(opener.requests), 1)
                request, timeout = opener.requests[0]
                self.assertEqual(request.full_url, "http://127.0.0.1:8080/workspace")
                self.assertEqual(request.method, "HEAD")
                self.assertEqual(timeout, 2)

    def test_tool_version_logs_bounded_success_with_elapsed_time(self):
        log_stream = io.BytesIO()
        stdout = io.StringIO()
        result = subprocess.CompletedProcess(
            args=[sys.executable, "--version"],
            returncode=0,
            stdout="v24.18.0\n",
        )
        with patch.object(self.module.subprocess, "run", return_value=result) as run:
            with redirect_stdout(stdout):
                version = self.module._tool_version(
                    Path(sys.executable),
                    "v24.18.0",
                    "Node",
                    log_stream=log_stream,
                )
        self.assertEqual(version, "v24.18.0")
        self.assertEqual(run.call_args.kwargs["timeout"], 120)
        log = log_stream.getvalue().decode("utf-8")
        self.assertIn("frontend tool probe start name=Node", log)
        self.assertRegex(log, r"status=ok elapsed_seconds=[0-9.]+ budget_seconds=120")
        self.assertIn("lifecycle event=tool_probe_start", stdout.getvalue())
        self.assertIn("lifecycle event=tool_probe_result", stdout.getvalue())

    def test_tool_version_rejects_timeout_and_wrong_version_with_result_logs(self):
        timeout_log = io.BytesIO()
        timeout_stdout = io.StringIO()
        with patch.object(
            self.module.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(
                [sys.executable, "--version"], self.module.TOOL_TIMEOUT_SECONDS
            ),
        ):
            with redirect_stdout(timeout_stdout):
                with self.assertRaisesRegex(
                    self.module.FrontendDevError,
                    r"pinned Node version probe timed out.*budget 120s",
                ):
                    self.module._tool_version(
                        Path(sys.executable),
                        "v24.18.0",
                        "Node",
                        log_stream=timeout_log,
                    )
        timeout_text = timeout_log.getvalue().decode("utf-8")
        self.assertRegex(
            timeout_text,
            r"status=timeout elapsed_seconds=[0-9.]+ budget_seconds=120",
        )
        self.assertIn("status=timeout", timeout_stdout.getvalue())

        mismatch_log = io.BytesIO()
        mismatch = subprocess.CompletedProcess(
            args=[sys.executable, "--version"],
            returncode=0,
            stdout="v24.18.1\n",
        )
        with patch.object(self.module.subprocess, "run", return_value=mismatch):
            with self.assertRaisesRegex(
                self.module.FrontendDevError,
                r"pinned Node version is 'v24\.18\.1'; expected 'v24\.18\.0'",
            ):
                self.module._tool_version(
                    Path(sys.executable),
                    "v24.18.0",
                    "Node",
                    log_stream=mismatch_log,
                )
        self.assertIn("status=mismatch", mismatch_log.getvalue().decode("utf-8"))

    @skipIf(os.name == "nt", "the bounded tailer regression uses POSIX no-follow file semantics")
    def test_log_tailer_streams_only_bytes_appended_after_start(self):
        with isolated(self.module) as (_root, _workspace, _inputs):
            self.module._prepare_state_directories()
            log_stream = self.module._log_stream()
            tailer = None
            try:
                log_stream.write(
                    b"frontend tool probe result name=pnpm status=ok\n"
                    b"old install progress 1/758\n"
                )
                log_stream.flush()
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    tailer = self.module._start_log_tailer()
                    self.assertIsNotNone(tailer)
                    log_stream.write(b"pnpm install progress 572/758\n")
                    log_stream.flush()
                    deadline = time.monotonic() + 2.0
                    while "pnpm install progress 572/758" not in stdout.getvalue():
                        if time.monotonic() >= deadline:
                            self.fail("the appended frontend log bytes were not streamed")
                        time.sleep(0.01)
                    tailer.stop()
                    tailer = None
                streamed = stdout.getvalue()
                self.assertIn("pnpm install progress 572/758", streamed)
                self.assertNotIn("frontend tool probe result", streamed)
                self.assertNotIn("old install progress 1/758", streamed)
            finally:
                if tailer is not None:
                    tailer.stop()
                log_stream.close()

    @skipIf(os.name == "nt", "FIFO no-follow regression uses the Linux container filesystem")
    def test_log_tailer_rejects_fifo_without_blocking(self):
        with tempfile.TemporaryDirectory(prefix="fullmag-frontend-log-fifo-") as raw:
            fifo = Path(raw) / "next.log"
            os.mkfifo(fifo)
            script = """
import importlib.util
import pathlib
import sys

module_path = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("fullmag_fifo_frontend_dev", module_path)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load frontend_dev.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.LOG_PATH = pathlib.Path(sys.argv[2])
try:
    module._LogTailer.start()
except module.FrontendDevError as error:
    if "regular file" not in str(error):
        raise
else:
    raise SystemExit("FIFO was accepted as the frontend log")
"""
            result = subprocess.run(
                [sys.executable, "-c", script, str(MODULE_PATH), str(fifo)],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_browser_origin_and_internal_api_target_are_separate(self):
        with isolated(self.module) as (root, workspace, inputs):
            environment = self.module._safe_environment(inputs)
            self.assertEqual(environment["FULLMAG_API_PROXY_TARGET"], "http://backend:8081")
            self.assertEqual(environment["FULLMAG_API_URL"], "http://backend:8081")
            self.assertEqual(environment["NEXT_PUBLIC_API_URL"], "http://localhost:3197")
            self.assertEqual(environment["COREPACK_ENABLE_PROJECT_SPEC"], "1")
            self.assertEqual(environment["COREPACK_DEFAULT_TO_LATEST"], "0")

    @skipIf(os.name == "nt", "directory fsync is a Linux container filesystem contract")
    def test_start_publishes_starting_receipt_before_tool_probe_failure(self):
        with isolated(self.module) as (root, workspace, inputs):
            with patch.dict(os.environ, {"FULLMAG_DOCKER_FRONTEND": "dev"}, clear=False):
                with patch.object(
                    self.module,
                    "_tool_version",
                    side_effect=[
                        "v24.18.0",
                        self.module.FrontendDevError("pinned pnpm version probe timed out"),
                    ],
                ):
                    with self.assertRaises(self.module.FrontendDevError):
                        self.module.start(type("Stopping", (), {"is_set": lambda self: False})())
            receipt = json.loads(self.module.RECEIPT_PATH.read_text(encoding="utf-8"))
            self.assertEqual(receipt["state"], "failed")
            self.assertEqual(receipt["failure_evidence"]["kind"], "tool-version-probe")
            self.assertIn("pinned pnpm version probe timed out", receipt["error"])
            self.assertEqual(receipt["tool_versions"], {"node": "v24.18.0"})

    @skipIf(os.name == "nt", "directory fsync is a Linux container filesystem contract")
    def test_start_checks_shutdown_between_bounded_tool_probes(self):
        with isolated(self.module) as (root, workspace, inputs):
            class Stopping:
                probes = 0

                def is_set(self):
                    return self.probes > 0

            stopping = Stopping()

            def probe(*args, **kwargs):
                stopping.probes += 1
                return "v24.18.0"

            with patch.dict(os.environ, {"FULLMAG_DOCKER_FRONTEND": "dev"}, clear=False):
                with patch.object(self.module, "_tool_version", side_effect=probe) as tool_probe:
                    with self.assertRaises(self.module.FrontendDevUnknown):
                        self.module.start(stopping)
            self.assertEqual(tool_probe.call_count, 1)
            receipt = json.loads(self.module.RECEIPT_PATH.read_text(encoding="utf-8"))
            self.assertEqual(receipt["state"], "unknown")

    def test_host_mount_descriptors_are_bound_to_the_fixed_workspace_targets(self):
        with isolated(self.module) as (root, workspace, inputs):
            manifest = json.loads(self.module.INPUTS_PATH.read_text(encoding="utf-8"))
            manifest["live_directories"] = [
                {
                    "name": name,
                    "source": rf"C:\git\fullmag\fullmag\apps\control-room\{name}",
                    "target": str(workspace / "apps" / "control-room" / name),
                }
                for name in self.module.LIVE_DIRECTORY_NAMES
            ]
            self.module.INPUTS_PATH.write_text(json.dumps(manifest), encoding="utf-8")
            parsed = self.module.read_inputs(self.module.INPUTS_PATH)
            self.assertEqual(parsed.live_directories, self.module.LIVE_DIRECTORY_NAMES)

    @skipIf(os.name == "nt", "directory fsync is a Linux container filesystem contract")
    def test_freeze_rejects_dependency_change_but_allows_generated_restart_files(self):
        with isolated(self.module) as (root, workspace, inputs):
            self.module._validate_live_directories(inputs)
            self.module._freeze_inputs(inputs, allow_generated=False)
            (workspace / "apps/control-room/package.json").write_bytes(b"changed\n")
            with self.assertRaises(self.module.FrontendDevError):
                self.module._freeze_inputs(inputs, allow_generated=False)

        with isolated(self.module) as (root, workspace, inputs):
            self.module._freeze_inputs(inputs, allow_generated=False)
            (workspace / "apps/control-room/tsconfig.json").write_bytes(b"generated\n")
            self.module._freeze_inputs(inputs, allow_generated=True)

        with isolated(self.module) as (root, workspace, inputs):
            self.module._freeze_inputs(inputs, allow_generated=False)
            generated = workspace / "apps/control-room/tsconfig.json"
            generated.unlink()
            generated.symlink_to(workspace / "missing-generated-tsconfig.json")
            with self.assertRaises(self.module.FrontendDevError):
                self.module._freeze_inputs(inputs, allow_generated=True)

    def test_managed_frontend_links_stay_in_state(self):
        with isolated(self.module) as (root, workspace, inputs):
            self.module._prepare_state_directories()
            target = self.module._prepare_managed_frontend(inputs)
            app = workspace / "apps" / "control-room"
            self.assertEqual(target, workspace / "node_modules")
            self.assertEqual((app / ".fullmag-frontend").resolve(), self.module.FRONTEND_ROOT.resolve())
            self.assertEqual(
                (app / ".next-control-room-8080").resolve(),
                (self.module.FRONTEND_ROOT / "next" / "dev-8080").resolve(),
            )
            self.assertEqual((workspace / "node_modules").resolve(), target.resolve())
            self.assertTrue((workspace / "node_modules").is_dir())
            self.assertFalse((workspace / "node_modules").is_symlink())
            self.assertTrue((app / "node_modules").is_dir())
            self.assertFalse((app / "node_modules").is_symlink())
            self.assertEqual(
                (root / "cache" / "node_modules").resolve(),
                (app / "node_modules").resolve(),
            )
            self.assertTrue((root / "cache" / "node_modules").is_symlink())
            self.assertFalse((root / "node_modules").exists())

    @skipIf(os.name == "nt", "dependency readiness regression uses Linux symlink semantics")
    def test_dependency_ready_does_not_trust_an_old_receipt_over_empty_cache(self):
        with isolated(self.module) as (_root, workspace, inputs):
            self.module._prepare_state_directories()
            self.module._prepare_managed_frontend(inputs)
            self.assertFalse(self.module._dependency_tree_ready(inputs))

            virtual_next = (
                workspace
                / "node_modules"
                / ".pnpm"
                / "next@16.3.8"
                / "node_modules"
                / "next"
            )
            binary = virtual_next / "dist" / "bin" / "next"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/usr/bin/env node\n", encoding="utf-8")
            app_next = workspace / "apps" / "control-room" / "node_modules" / "next"
            app_next.symlink_to(virtual_next, target_is_directory=True)
            self.assertTrue(self.module._dependency_tree_ready(inputs))

    @skipIf(os.name == "nt", "dependency reconciliation regression uses Linux symlink semantics")
    def test_start_reconciles_ready_receipt_when_cache_is_empty(self):
        with isolated(self.module) as (_root, workspace, inputs):
            self.module._prepare_state_directories()
            self.module._prepare_managed_frontend(inputs)
            self.module._atomic_json(
                self.module.RECEIPT_PATH,
                {
                    "schema": self.module.RECEIPT_SCHEMA,
                    "state": "failed",
                    "dependency_install": "ready",
                },
                "frontend development receipt",
            )

            def fake_install(_inputs, _stopping_event, _log_stream, _receipt, _runtime_lock):
                virtual_next = (
                    workspace
                    / "node_modules"
                    / ".pnpm"
                    / "next@16.3.8"
                    / "node_modules"
                    / "next"
                )
                binary = virtual_next / "dist" / "bin" / "next"
                binary.parent.mkdir(parents=True)
                binary.write_text("#!/usr/bin/env node\n", encoding="utf-8")
                (workspace / "apps" / "control-room" / "node_modules" / "next").symlink_to(
                    virtual_next, target_is_directory=True
                )

            stopping = type("Stopping", (), {"is_set": lambda self: False})()
            log_stream = io.BytesIO()
            with patch.dict(os.environ, {"FULLMAG_DOCKER_FRONTEND": "dev"}, clear=False):
                with patch.object(
                    self.module,
                    "_tool_version",
                    side_effect=[self.module.EXPECTED_NODE_VERSION, self.module.EXPECTED_PNPM_VERSION],
                ):
                    with patch.object(self.module, "_log_stream", return_value=log_stream):
                        with patch.object(self.module, "_run_pnpm_install", side_effect=fake_install) as install:
                            with patch.object(self.module, "_start_log_tailer", return_value=None):
                                with patch.object(self.module, "_start_next", return_value=object()):
                                    self.module.start(stopping)
            install.assert_called_once()
            log_stream.close()

    @skipIf(os.name == "nt", "runtime flock regression uses POSIX file locking")
    def test_runtime_lock_rejects_a_second_active_consumer(self):
        with isolated(self.module):
            first = self.module._acquire_runtime_lock()
            try:
                with self.assertRaisesRegex(
                    self.module.FrontendDevError,
                    "already held by an active consumer",
                ):
                    self.module._acquire_runtime_lock()
            finally:
                self.module._release_runtime_lock(first)

    @skipIf(os.name == "nt", "Node module resolution regression uses Linux symlink semantics")
    def test_generated_cache_path_requires_from_managed_dependency_alias(self):
        node = self.module.NODE_BINARY
        if not node.is_file() or not os.access(node, os.X_OK):
            self.skipTest(f"pinned Node executable is unavailable: {node}")
        with isolated(self.module) as (root, workspace, inputs):
            self.module._prepare_state_directories()
            self.module._prepare_managed_frontend(inputs)
            package = workspace / "apps" / "control-room" / "node_modules" / "frontend-resolution-fixture"
            package.mkdir()
            (package / "index.js").write_text("module.exports = 'state-owned';\n", encoding="utf-8")
            generated = root / "cache" / "next" / "dev-8080" / "dev" / "server" / "app"
            generated.mkdir(parents=True)
            page = generated / "page.js"
            page.write_text(
                "const value = require('frontend-resolution-fixture');\n"
                "if (value !== 'state-owned') process.exit(2);\n"
                "process.stdout.write(value);\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [str(node), str(page)],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertEqual(result.stdout, "state-owned")

    @skipIf(os.name == "nt", "symlink support is a Linux container filesystem contract")
    def test_old_external_node_modules_alias_is_rejected(self):
        with isolated(self.module) as (root, workspace, inputs):
            self.module._prepare_state_directories()
            legacy_target = root / "legacy-node-modules"
            legacy_target.mkdir()
            (workspace / "node_modules").symlink_to(legacy_target, target_is_directory=True)
            with self.assertRaises(self.module.FrontendDevError):
                self.module._prepare_managed_frontend(inputs)

        with isolated(self.module) as (root, workspace, inputs):
            self.module._prepare_state_directories()
            legacy_target = root / "legacy-cache-node-modules"
            legacy_target.mkdir()
            cache_alias = root / "cache" / "node_modules"
            cache_alias.symlink_to(legacy_target, target_is_directory=True)
            with self.assertRaises(self.module.FrontendDevError):
                self.module._prepare_managed_frontend(inputs)
            self.assertEqual(cache_alias.resolve(), legacy_target.resolve())

    @skipIf(os.name == "nt", "symlink support is a Linux container filesystem contract")
    def test_next_binary_may_resolve_through_workspace_virtual_store(self):
        with isolated(self.module) as (root, workspace, inputs):
            self.module._prepare_state_directories()
            self.module._prepare_managed_frontend(inputs)
            virtual_next = (
                workspace
                / "node_modules"
                / ".pnpm"
                / "next@16.3.8"
                / "node_modules"
                / "next"
            )
            binary = virtual_next / "dist" / "bin" / "next"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/usr/bin/env node\n", encoding="utf-8")
            app_next = workspace / "apps" / "control-room" / "node_modules" / "next"
            app_next.symlink_to(virtual_next, target_is_directory=True)
            self.assertEqual(
                self.module._next_binary(inputs),
                app_next / "dist" / "bin" / "next",
            )

    @skipIf(os.name == "nt", "symlink support is a Linux container filesystem contract")
    def test_check_rejects_managed_target_tamper_without_repair(self):
        with isolated(self.module) as (root, workspace, inputs):
            self.module._prepare_state_directories()
            self.module._prepare_managed_frontend(inputs)
            self.module._freeze_inputs(inputs, allow_generated=False)
            process = _RunningProcess()
            identity = {
                "pid": process.pid,
                "pid_namespace": "pid:[4026531836]",
                "process_start_time_ticks": 18,
                "session_id": process.pid,
                "process_group_id": process.pid,
            }
            handle = self.module.FrontendHandle(
                process=process,
                inputs=inputs,
                stopping_event=object(),
                kind="next",
                pid=process.pid,
                owner_token="owner-token",
                log_path=self.module.LOG_PATH,
                process_group_id=process.pid,
                process_identity=identity,
            )
            self.module._atomic_json(
                self.module.RECEIPT_PATH,
                {
                    "schema": self.module.RECEIPT_SCHEMA,
                    "state": "running",
                    "pid": process.pid,
                    "owner_token": handle.owner_token,
                    **{field: identity[field] for field in self.module.PROCESS_IDENTITY_FIELDS},
                },
                "receipt",
            )
            tampered_target = root / "tampered-cache"
            tampered_target.mkdir()
            alias = workspace / "apps" / "control-room" / self.module.NEXT_DIST_DIR
            alias.unlink()
            alias.symlink_to(tampered_target, target_is_directory=True)
            with self.assertRaises(self.module.FrontendDevError):
                self.module.check(handle)
            self.assertEqual(alias.resolve(), tampered_target.resolve())
            saved = json.loads(self.module.RECEIPT_PATH.read_text(encoding="utf-8"))
            self.assertEqual(saved["state"], "failed")
            self.assertEqual(saved["failure_evidence"]["kind"], "frontend-input-change")

    @skipIf(os.name == "nt", "directory fsync is a Linux container filesystem contract")
    def test_stop_preserves_failure_and_does_not_force_kill(self):
        with isolated(self.module) as (root, workspace, inputs):
            process = _DeadProcess(1)
            identity = {
                "pid": process.pid,
                "pid_namespace": "pid:[4026531836]",
                "process_start_time_ticks": 17,
                "session_id": process.pid,
                "process_group_id": process.pid,
            }
            handle = self.module.FrontendHandle(
                process=process,
                inputs=inputs,
                stopping_event=object(),
                kind="next",
                pid=process.pid,
                owner_token="owner-token",
                log_path=self.module.LOG_PATH,
                process_group_id=process.pid,
                process_identity=identity,
            )
            self.module._atomic_json(
                self.module.RECEIPT_PATH,
                {
                    "schema": self.module.RECEIPT_SCHEMA,
                    "state": "failed",
                    "pid": process.pid,
                    "owner_token": handle.owner_token,
                    **{field: identity[field] for field in self.module.PROCESS_IDENTITY_FIELDS},
                    "failure_evidence": {"kind": "child-exit"},
                },
                "receipt",
            )
            receipt = self.module.stop(handle)
            self.assertFalse(process.terminated)
            self.assertEqual(receipt["state"], "stopped-after-failure")
            self.assertEqual(receipt["failure_evidence"], {"kind": "child-exit"})

    @skipIf(os.name == "nt", "process-group supervision is a Linux container contract")
    def test_stop_signals_owned_process_group_and_waits_for_empty_group(self):
        with isolated(self.module) as (root, workspace, inputs):
            process = _RunningProcess()
            identity = {
                "pid": process.pid,
                "pid_namespace": "pid:[4026531836]",
                "process_start_time_ticks": 18,
                "session_id": process.pid,
                "process_group_id": process.pid,
            }
            handle = self.module.FrontendHandle(
                process=process,
                inputs=inputs,
                stopping_event=object(),
                kind="next",
                pid=process.pid,
                owner_token="owner-token",
                log_path=self.module.LOG_PATH,
                process_group_id=process.pid,
                process_identity=identity,
            )
            self.module._atomic_json(
                self.module.RECEIPT_PATH,
                {
                    "schema": self.module.RECEIPT_SCHEMA,
                    "state": "running",
                    "pid": process.pid,
                    "owner_token": handle.owner_token,
                    **{field: identity[field] for field in self.module.PROCESS_IDENTITY_FIELDS},
                },
                "receipt",
            )
            with patch.object(self.module, "_confirmed_live_identity", return_value=identity):
                with patch.object(self.module, "_wait_for_group_empty", return_value=True):
                    with patch.object(self.module.os, "killpg") as killpg:
                        receipt = self.module.stop(handle)
            killpg.assert_called_once_with(process.pid, signal.SIGTERM)
            self.assertFalse(process.terminated)
            self.assertEqual(receipt["state"], "stopped")

    def test_live_failure_receipt_blocks_takeover(self):
        with self.assertRaises(self.module.FrontendDevError):
            self.module._reject_existing_owner(
                {"state": "stop-timeout", "pid": os.getpid()}
            )

    @skipIf(os.name == "nt", "Linux process identity probing is a container contract")
    def test_terminal_failed_receipt_without_identity_requires_recovery(self):
        with self.assertRaises(self.module.FrontendDevUnknown):
            self.module._reject_existing_owner({"state": "failed", "pid": 4194303})

    @skipIf(os.name == "nt", "directory fsync is a Linux container filesystem contract")
    def test_pid_reuse_marks_active_owner_unknown_without_takeover(self):
        with isolated(self.module) as (root, workspace, inputs):
            observed = self.module._read_process_identity(os.getpid())
            self.assertIsNotNone(observed)
            stale = dict(observed)
            stale["process_start_time_ticks"] += 1
            receipt = {
                "schema": self.module.RECEIPT_SCHEMA,
                "state": "running",
                **{field: stale[field] for field in ("pid", *self.module.PROCESS_IDENTITY_FIELDS)},
            }
            with self.assertRaises(self.module.FrontendDevUnknown):
                self.module._reject_existing_owner(receipt)
            saved = json.loads(self.module.RECEIPT_PATH.read_text(encoding="utf-8"))
            self.assertEqual(saved["state"], "unknown")
            self.assertEqual(saved["failure_evidence"]["kind"], "owner-identity-unconfirmed")


if __name__ == "__main__":
    main()
