"""Focused checks for the bounded selector and its image-owned helper.

The helper tests execute only the self-contained selector source in a temporary
fixture. They rewrite its fixed /control mount to that fixture and never invoke
Docker, application code, or a real control volume.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


import docker_volume_pre_admission_selector as selector
from docker_build_control import BuildControlError


PARENT = "9a12fbd668f149a6a42ef726c5fbf9bb"
ATTEMPT = "26778aad1fb24b249ed28023775d6cef"
OTHER_ATTEMPT = "deadbeefdeadbeefdeadbeefdeadbeef"
CONFIG = "d5a5ec453c89a6e184f1f64a5e2168d48ce9783f5d5760df737e9dea3bbd655b"
STARTED = "2026-10-20T15:16:30.069415108Z"


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        .encode("utf-8")
        + b"\n"
    )


def terminal_document(
    *,
    attempt: str = ATTEMPT,
    parent: str = PARENT,
    config: str = CONFIG,
    started: str = STARTED,
) -> dict[str, object]:
    return {
        "attempt": attempt,
        "backend_started_at": started,
        "inputs": {"attempt": parent, "config_sha256": config},
        "phase": "resume",
        "state": "failed-confirmed",
    }


def response_for(terminal_raw: bytes, failure_raw: bytes, *, published=None) -> bytes:
    candidate = {
        "phase": "resume",
        "attempt": ATTEMPT,
        "terminal_path": f"resume/attempts/{ATTEMPT}/terminal.json",
        "terminal_raw_b64": base64.b64encode(terminal_raw).decode("ascii"),
        "failure_log_path": f"resume/attempts/{ATTEMPT}/backend-failure-log.json",
        "failure_log_raw_b64": base64.b64encode(failure_raw).decode("ascii"),
        "published_paths": published or {name: False for name in selector.PUBLICATION_PATHS},
    }
    return canonical({
        "schema": selector.SELECTOR_SCHEMA,
        "max_entries": selector.MAX_SELECTOR_ENTRIES,
        "scanned_entries": 1,
        "candidate_count": 1,
        "candidates": [candidate],
    })


def write_attempt(
    control_root: Path,
    attempt: str,
    *,
    terminal: dict[str, object] | None = None,
    failure: dict[str, object] | None = None,
) -> Path:
    path = control_root / "resume" / "attempts" / attempt
    path.mkdir(parents=True)
    if terminal is not None:
        (path / "terminal.json").write_bytes(canonical(terminal))
    if failure is not None:
        (path / "backend-failure-log.json").write_bytes(canonical(failure))
    return path


def run_helper(
    control_root: Path,
    *,
    parent: str = PARENT,
    config: str = CONFIG,
    started: str = STARTED,
) -> subprocess.CompletedProcess[bytes]:
    source = selector._HELPER_SOURCE.replace("'/control'", repr(str(control_root)))
    request = canonical({
        "backend_started_at": started,
        "config_sha256": config,
        "parent_attempt": parent,
    })
    return subprocess.run(
        [sys.executable, "-B", "-c", source],
        input=request,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class Control:
    project = "fullmag-worktree-draft"
    volume = "fullmag-control-draft"
    namespace = ""
    image = "sha256:" + "a" * 64
    entrypoint = "/bin/bash"
    command_image = None

    def helper_args(self, script):
        self.script = script
        command = [
            "docker", "run", "--rm", "-i", "--pull", "never",
            "--network", "none", "--runtime", "runc", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--pids-limit", "32", "--memory", "64m", "--cpus", "0.25",
            "--env", "NVIDIA_VISIBLE_DEVICES=void",
            "--mount", f"type=volume,src={self.volume},dst=/control,volume-nocopy",
            "--label", "com.docker.compose.project=" + self.project,
        ]
        if self.namespace:
            command[command.index("--mount") + 1] += ",volume-subpath=" + self.namespace
            command.extend([
                "--mount",
                f"type=volume,src={self.volume},dst=/registry,readonly,volume-nocopy",
            ])
        command.extend([
            "--user", "65532:65532", "--entrypoint", self.entrypoint,
            self.command_image or self.image, "-euo", "pipefail", "-c", script,
        ])
        return command


class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.terminal = terminal_document()
        self.failure = {"log": "backend failed before publication"}
        self.terminal_raw = canonical(self.terminal)
        self.failure_raw = canonical(self.failure)
        self.control = Control()

    def call(self, output=None, *, helper_image="sha256:" + "b" * 64):
        output = output or response_for(self.terminal_raw, self.failure_raw)
        calls = []

        def capture(command, *, data, timeout, maximum):
            calls.append((command, data, timeout, maximum))
            return type("Result", (), {
                "returncode": 0, "stdout": output, "stderr": b"",
            })()

        with patch.object(selector, "bounded_capture", side_effect=capture):
            result = selector.read_pinned_resume_evidence(
                self.control,
                parent_attempt=PARENT,
                config_sha256=CONFIG,
                backend_started_at=STARTED,
                helper_image=helper_image,
            )
        return result, calls

    def test_returns_exact_raw_documents_and_authenticated_absence(self):
        result, calls = self.call()
        candidate = result["candidates"][0]
        self.assertEqual(candidate["terminal_raw"], self.terminal_raw)
        self.assertEqual(candidate["terminal"], self.terminal)
        self.assertEqual(candidate["failure_log_raw"], self.failure_raw)
        self.assertEqual(candidate["failure_log"], self.failure)
        self.assertEqual(set(candidate["published_paths"].values()), {False})
        mount = calls[0][0][calls[0][0].index("--mount") + 1]
        self.assertTrue(mount.endswith(",volume-nocopy,readonly"))
        self.assertNotIn("/opt/fullmag/source", " ".join(calls[0][0]))
        self.assertNotIn("/var/run/docker.sock", " ".join(calls[0][0]))
        self.assertEqual(json.loads(calls[0][1]), {
            "backend_started_at": STARTED,
            "config_sha256": CONFIG,
            "parent_attempt": PARENT,
        })
        self.assertEqual(calls[0][2:], (90, selector.MAX_SELECTOR_OUTPUT_BYTES))

    def test_rejects_noncanonical_terminal_bytes(self):
        noncanonical = b'{"state":"failed-confirmed","phase":"resume"}\n'
        with self.assertRaises(BuildControlError):
            self.call(response_for(noncanonical, self.failure_raw))

    def test_rejects_authenticated_publication_presence(self):
        published = {name: False for name in selector.PUBLICATION_PATHS}
        published["provenance.json"] = True
        with self.assertRaises(BuildControlError):
            self.call(response_for(self.terminal_raw, self.failure_raw, published=published))

    def test_rejects_unpinned_selected_image_before_capture(self):
        with self.assertRaisesRegex(BuildControlError, "immutable retained backend image"):
            self.call(helper_image="fullmag/backend:dev")

    def test_rejects_wrong_entrypoint_before_capture(self):
        self.control.entrypoint = "/bin/sh"
        with self.assertRaisesRegex(BuildControlError, "entrypoint/image differs"):
            self.call()

    def test_rejects_command_that_does_not_use_current_image(self):
        self.control.command_image = "sha256:" + "c" * 64
        with self.assertRaisesRegex(BuildControlError, "entrypoint/image differs"):
            self.call()

    def test_preserves_namespace_registry_mounts_and_security(self):
        self.control.namespace = "namespace-a"
        result, calls = self.call()
        self.assertEqual(result["candidate_count"], 1)
        command = calls[0][0]
        mounts = [command[index + 1] for index, value in enumerate(command) if value == "--mount"]
        self.assertEqual(mounts, [
            f"type=volume,src={self.control.volume},dst=/control,volume-nocopy,"
            "volume-subpath=namespace-a,readonly",
            f"type=volume,src={self.control.volume},dst=/registry,readonly,volume-nocopy",
        ])
        for value in (
            "--pull", "never", "--network", "none", "--runtime", "runc",
            "--read-only", "--cap-drop", "ALL", "--security-opt",
            "no-new-privileges:true", "--pids-limit", "32", "--memory", "64m",
            "--cpus", "0.25", "--env", "NVIDIA_VISIBLE_DEVICES=void",
            "--user", "65532:65532",
        ):
            self.assertIn(value, command)
        self.assertIn("com.docker.compose.project=" + self.control.project, command)

    def test_selected_image_replaces_current_image_in_final_command(self):
        selected = "sha256:" + "b" * 64
        _, calls = self.call(helper_image=selected)
        command = calls[0][0]
        anchor = command.index("--entrypoint")
        self.assertEqual(command[anchor:anchor + 3], ["--entrypoint", "/bin/bash", selected])
        self.assertNotEqual(selected, self.control.image)

    def test_helper_accepts_one_pinned_terminal_and_preserves_raw_bytes(self):
        with tempfile.TemporaryDirectory() as value:
            control_root = Path(value) / "control"
            write_attempt(
                control_root,
                ATTEMPT,
                terminal=self.terminal,
                failure=self.failure,
            )
            result = run_helper(control_root)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            response = json.loads(result.stdout)
            candidate = response["candidates"][0]
            self.assertEqual(base64.b64decode(candidate["terminal_raw_b64"]), self.terminal_raw)
            self.assertEqual(base64.b64decode(candidate["failure_log_raw_b64"]), self.failure_raw)
            self.assertEqual(candidate["published_paths"], {
                name: False for name in selector.PUBLICATION_PATHS
            })

    def test_helper_rejects_symlinked_ancestor(self):
        with tempfile.TemporaryDirectory() as value:
            control_root = Path(value) / "control"
            control_root.mkdir()
            outside = Path(value) / "outside"
            outside.mkdir()
            os.symlink(outside, control_root / "resume")
            result = run_helper(control_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("canonical directory", result.stderr.decode())

    def test_helper_rejects_ambiguous_pinned_terminals(self):
        with tempfile.TemporaryDirectory() as value:
            control_root = Path(value) / "control"
            write_attempt(
                control_root,
                ATTEMPT,
                terminal=self.terminal,
            )
            write_attempt(
                control_root,
                OTHER_ATTEMPT,
                terminal=terminal_document(attempt=OTHER_ATTEMPT),
            )
            result = run_helper(control_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("more than one pinned terminal", result.stderr.decode())

    def test_helper_rejects_changed_pins(self):
        with tempfile.TemporaryDirectory() as value:
            control_root = Path(value) / "control"
            write_attempt(
                control_root,
                ATTEMPT,
                terminal=terminal_document(started="2026-10-20T15:16:30.069415109Z"),
            )
            result = run_helper(control_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one pinned terminal", result.stderr.decode())

    def test_helper_rejects_publication_file(self):
        with tempfile.TemporaryDirectory() as value:
            control_root = Path(value) / "control"
            path = write_attempt(
                control_root,
                ATTEMPT,
                terminal=self.terminal,
                failure=self.failure,
            )
            (path / "provenance.json").write_bytes(canonical({"published": True}))
            result = run_helper(control_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("publication path provenance.json is present", result.stderr.decode())

    def test_helper_enforces_entry_bound(self):
        with tempfile.TemporaryDirectory() as value:
            control_root = Path(value) / "control"
            attempts = control_root / "resume" / "attempts"
            attempts.mkdir(parents=True)
            for index in range(257):
                (attempts / f"{index:032x}").mkdir()
            result = run_helper(control_root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("directory-entry bound exceeded", result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
