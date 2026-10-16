"""Focused source regressions for explicit Docker development-run reuse."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import docker_dev
import docker_development_inputs as development_inputs
import fullmag_docker_runtime as runtime


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DockerDevRecreateContract(unittest.TestCase):
    def _run_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name).resolve()
        storage_root = root / "storage"
        build_root = storage_root / "build"
        runs_root = storage_root / "runs" / "task"
        run_root = runs_root / "docker-all" / ("a" * 32)
        state = run_root / "state"
        source = root / "checkout"
        assembly = build_root / "old-assembly.json"
        for path in (build_root, state / "runs" / "docker-all" / "session-store",
                     state / "development", source):
            path.mkdir(parents=True)
        assembly.write_text('{"schema":"fullmag.docker-all-image.v1"}\n', encoding="utf-8")
        host_certificate = {
            "schema": "fullmag.windows-folder-host.v1",
            "storage_profile": "windows-folder-v1",
            "owner_scope": "docker-desktop-linux",
            "owner_token": "00000000-0000-4000-8000-000000000001",
        }
        (run_root / "windows-folder-host.json").parent.mkdir(parents=True, exist_ok=True)
        (run_root / "windows-folder-host.json").write_text(
            json.dumps(host_certificate), encoding="utf-8"
        )
        (state / ".fullmag-windows-folder-owner.json").write_text(
            json.dumps(host_certificate), encoding="utf-8"
        )
        config = state / ".fullmag" / "runtime-service" / "docker-all.json"
        config.parent.mkdir(parents=True)
        config.write_bytes(b'{"schema_version":"runtime_service_config.v2"}\n')
        frontend_inputs = run_root / "development-inputs-host.json"
        frontend_inputs.write_text('{"schema":"fullmag.docker-development-inputs.v1"}\n', encoding="utf-8")
        guest_inputs = run_root / "development-inputs.json"
        guest_inputs.write_text('{"schema":"fullmag.docker-development-inputs.v1"}\n', encoding="utf-8")
        backend_id = "1" * 64
        frontend_id = "2" * 64
        receipt = {
            "schema": "fullmag.docker-all-run.v1",
            "state": "running",
            "image_id": "sha256:" + "1" * 64,
            "compose_project": "fullmag",
            "compose_file": str(run_root / "compose.json"),
            "state_root": str(state),
            "host_certificate": str(run_root / "windows-folder-host.json"),
            "assembly_receipt": str(assembly),
            "assembly_receipt_sha256": _sha256(assembly),
            "frontend_mode": "dev",
            "frontend_source_root": str(source),
            "frontend_host_inputs": str(frontend_inputs),
            "frontend_host_inputs_sha256": _sha256(frontend_inputs),
            "frontend_inputs": str(guest_inputs),
            "frontend_inputs_sha256": _sha256(guest_inputs),
            "container_id": backend_id,
            "frontend_container_id": frontend_id,
        }
        receipt_path = run_root / "receipt.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        layout = {
            "storage_root": str(storage_root),
            "build_storage_root": str(build_root),
            "runs_root": str(runs_root),
        }
        return temporary, layout, receipt_path, config

    @staticmethod
    def _fake_docker(state, image, running=()):
        backend_id = "1" * 64
        frontend_id = "2" * 64
        documents = {
            backend_id: {
                "Id": backend_id,
                "Image": image,
                "Config": {"Labels": {
                    "com.docker.compose.project": "fullmag",
                    "com.docker.compose.service": "backend",
                }},
                "State": {"Running": False, "Status": "exited"},
                "Mounts": [{"Type": "bind", "Source": str(state),
                            "Destination": "/state", "RW": True}],
            },
            frontend_id: {
                "Id": frontend_id,
                "Image": image,
                "Config": {"Labels": {
                    "com.docker.compose.project": "fullmag",
                    "com.docker.compose.service": "frontend",
                }},
                "State": {"Running": False, "Status": "exited"},
                "Mounts": [{"Type": "bind", "Source": str(state / "development"),
                            "Destination": "/state/development", "RW": True}],
            },
        }
        running_ids = list(running)
        for running_id in running_ids:
            documents[running_id] = {
                "Id": running_id,
                "Image": image,
                "Config": {"Labels": {
                    "com.docker.compose.project": "foreign",
                    "com.docker.compose.service": "worker",
                }},
                "State": {"Running": True, "Status": "running"},
                "Mounts": [{"Type": "bind", "Source": str(state),
                            "Destination": "/state", "RW": True}],
            }

        def fake(*args, **kwargs):
            if args[:2] == ("ps", "--quiet"):
                return "\n".join(running_ids)
            if args and args[0] == "inspect" and len(args) == 2:
                return json.dumps([documents[args[1]]])
            raise AssertionError(f"unexpected Docker read: {args}")

        return fake

    def test_reuse_requires_one_owned_direct_receipt_and_preserves_identity(self):
        temporary, layout, receipt_path, config = self._run_fixture()
        try:
            with patch.object(runtime, "docker", side_effect=self._fake_docker(
                    receipt_path.parent / "state", "sha256:" + "1" * 64)):
                loaded = runtime._load_reuse_run(
                    layout,
                    receipt_path,
                    project_name="fullmag",
                    frontend="dev",
                    previous_config_sha256=_sha256(config),
                )
            self.assertEqual(loaded["root"], receipt_path.parent)
            self.assertEqual(loaded["state"], receipt_path.parent / "state")
            self.assertEqual(loaded["project"], "fullmag")
            with self.assertRaisesRegex(ValueError, "direct docker-all"):
                runtime._load_reuse_run(
                    layout,
                    receipt_path.parent / "nested" / "receipt.json",
                    project_name="fullmag",
                    frontend="dev",
                )
            with patch.object(runtime, "docker", side_effect=self._fake_docker(
                    receipt_path.parent / "state", "sha256:" + "1" * 64)):
                with self.assertRaisesRegex(ValueError, "digest"):
                    runtime._load_reuse_run(
                        layout,
                        receipt_path,
                        project_name="fullmag",
                        frontend="dev",
                        previous_config_sha256="0" * 64,
                    )
        finally:
            temporary.cleanup()

    def test_reuse_rejects_receipt_changed_during_admission(self):
        temporary, layout, receipt_path, config = self._run_fixture()
        try:
            original = receipt_path.read_bytes()
            read_json = runtime._read_reuse_json

            def read_and_change(path, label, maximum=16 * 1024 * 1024):
                value = read_json(path, label, maximum)
                if Path(path).resolve() == receipt_path.resolve():
                    receipt_path.write_bytes(original + b"\n")
                return value

            with patch.object(runtime, "_read_reuse_json", side_effect=read_and_change), \
                    patch.object(runtime, "docker", side_effect=self._fake_docker(
                        receipt_path.parent / "state", "sha256:" + "1" * 64)):
                with self.assertRaisesRegex(ValueError, "changed during admission"):
                    runtime._load_reuse_run(
                        layout,
                        receipt_path,
                        project_name="fullmag",
                        frontend="dev",
                        previous_config_sha256=_sha256(config),
                    )
            self.assertEqual(receipt_path.read_bytes(), original + b"\n")
        finally:
            temporary.cleanup()

    def test_reuse_rejects_running_state_consumer_before_mutation(self):
        temporary, layout, receipt_path, config = self._run_fixture()
        try:
            fake = self._fake_docker(
                receipt_path.parent / "state",
                "sha256:" + "1" * 64,
                running=("3" * 64,),
            )
            with patch.object(runtime, "docker", side_effect=fake):
                with self.assertRaisesRegex(ValueError, "still mounts"):
                    runtime._load_reuse_run(
                        layout,
                        receipt_path,
                        project_name="fullmag",
                        frontend="dev",
                        previous_config_sha256=_sha256(config),
                    )
        finally:
            temporary.cleanup()

    def test_reuse_archives_receipts_before_same_run_metadata_changes(self):
        temporary, layout, receipt_path, config = self._run_fixture()
        try:
            nested_inputs = receipt_path.parent / ".recreate" / "old-token" / "development-inputs-host.json"
            nested_inputs.parent.mkdir(parents=True)
            nested_inputs.write_bytes(b'{"schema":"old"}\n')
            old_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            old_receipt["frontend_host_inputs"] = str(nested_inputs)
            old_receipt["frontend_host_inputs_sha256"] = _sha256(nested_inputs)
            receipt_path.write_text(json.dumps(old_receipt), encoding="utf-8")
            with patch.object(runtime, "docker", side_effect=self._fake_docker(
                    receipt_path.parent / "state", "sha256:" + "1" * 64)):
                reuse = runtime._load_reuse_run(
                    layout, receipt_path, project_name="fullmag", frontend="dev",
                )
            original = receipt_path.read_bytes()
            runtime._preserve_reuse_evidence(reuse)
            history = reuse["history_root"]
            self.assertEqual((history / "receipt.json").read_bytes(), original)
            self.assertEqual(
                (history / ".recreate" / "old-token" / "development-inputs-host.json").read_bytes(),
                b'{"schema":"old"}\n',
            )
            self.assertEqual(
                (history / "state" / ".fullmag" / "runtime-service" / "docker-all.json").read_bytes(),
                config.read_bytes(),
            )
            manifest = json.loads((history / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_receipt_sha256"], hashlib.sha256(original).hexdigest())
            self.assertTrue(reuse["metadata_root"].is_dir())
        finally:
            temporary.cleanup()

    def test_frontend_seed_preflight_keeps_active_receipt_and_records_attempt(self):
        temporary, layout, receipt_path, config = self._run_fixture()
        try:
            source = Path(json.loads(receipt_path.read_text(encoding="utf-8"))["frontend_source_root"])
            with patch.object(runtime, "docker", side_effect=self._fake_docker(
                    receipt_path.parent / "state", "sha256:" + "1" * 64)):
                reuse = runtime._load_reuse_run(
                    layout,
                    receipt_path,
                    project_name="fullmag",
                    frontend="dev",
                    previous_config_sha256=_sha256(config),
                )
            original = receipt_path.read_bytes()
            with patch.object(development_inputs, "select_checkout", return_value=source), \
                    patch.object(
                        development_inputs,
                        "seed",
                        side_effect=ValueError("Persistent frontend seed metadata was changed"),
                    ):
                with self.assertRaisesRegex(ValueError, "Persistent frontend seed metadata"):
                    runtime._preflight_reuse_frontend_inputs(
                        Path("/repo"), reuse, source, 3197,
                    )

            self.assertEqual(receipt_path.read_bytes(), original)
            histories = sorted((receipt_path.parent / "receipt-history").iterdir())
            self.assertEqual(len(histories), 1)
            history = histories[0]
            self.assertEqual((history / "receipt.json").read_bytes(), original)
            attempt = json.loads((history / "failed-attempt.json").read_text(encoding="utf-8"))
            self.assertEqual(attempt["schema"], "fullmag.docker-all-recreate-attempt.v1")
            self.assertEqual(attempt["state"], "failed_preflight")
            self.assertEqual(attempt["failure_phase"], "frontend-seed")
            self.assertEqual(attempt["service_mutation"], "not_started")
            self.assertEqual(attempt["runtime_state_mutation"], "not_started")
            self.assertEqual(attempt["active_receipt_sha256"], _sha256(receipt_path))
            manifest = json.loads((history / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_receipt_sha256"], _sha256(receipt_path))
            self.assertEqual(manifest["failed_attempt_state"], "failed_preflight")
            self.assertEqual(manifest["service_mutation"], "not_started")

            # The failed preflight did not turn the last verified receipt into
            # a failed run, so the normal explicit retry admission still works.
            with patch.object(runtime, "docker", side_effect=self._fake_docker(
                    receipt_path.parent / "state", "sha256:" + "1" * 64)):
                retried = runtime._load_reuse_run(
                    layout,
                    receipt_path,
                    project_name="fullmag",
                    frontend="dev",
                    previous_config_sha256=_sha256(config),
                )
            self.assertEqual(retried["root"], receipt_path.parent)
        finally:
            temporary.cleanup()

    def test_compose_spec_passes_config_cas_to_backend(self):
        document = {"services": {"backend": {"environment": {}}}, "networks": {}}

        def fake_docker(*args, **kwargs):
            return json.dumps(document)

        with patch.object(runtime, "docker", fake_docker):
            configured = runtime.compose_spec(
                "sha256:" + "a" * 64,
                Path("/state"),
                3197,
                Path("/owned/windows-folder-host.json"),
                workspace_state_root=Path("/owned/user-data"),
                repo=Path("/repo"),
                previous_config_sha256="b" * 64,
            )
        self.assertEqual(
            configured["services"]["backend"]["environment"]["FULLMAG_DOCKER_PREVIOUS_CONFIG_SHA256"],
            "b" * 64,
        )

    def test_backend_build_environment_uses_validated_userdata_and_scratch_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            storage_root = root / "storage"
            build_root = storage_root / "build"
            cache_root = storage_root / "cache"
            runtime_root = storage_root / "runtime"
            for path in (storage_root, build_root, cache_root, runtime_root):
                path.mkdir(parents=True)
            selected = root / "checkout"
            selected.mkdir()
            run_root = build_root / "direct-compose" / ("a" * 32)
            run_root.mkdir(parents=True)
            package = run_root / "package"
            source_manifest = run_root / "source.json"
            source_archive = run_root / "source.tar"
            layout = {
                "storage_root": str(storage_root),
                "build_root": str(build_root),
                "build_storage_root": str(build_root),
                "cache_root": str(cache_root),
                "runtime_root": str(runtime_root),
                "repo_root": str(selected),
                "worktree_id": "worktree-test",
                "env": {"FULLMAG_PROJECT_ID": "project-test"},
            }
            identity = {
                "project_name": "fullmag-worktree-worktree-test",
                "network_name": "fullmag-worktree-worktree-test_fullmag",
                "project_id": "project-test",
                "worktree_id": "worktree-test",
                "checkout_kind": "worktree",
            }
            source_bundle = {
                "source_mode": "archive",
                "manifest_path": str(source_manifest),
                "archive_path": str(source_archive),
            }
            with patch.object(docker_dev, "_compose_identity", return_value=identity):
                environment = docker_dev._environment(
                    layout, selected, run_root, source_bundle, package,
                    "fullmag-dev:local", "sha256:" + "a" * 64,
                    "sha256:" + "b" * 64, {"environment": {}},
                    "fullmag/development-base:local", "backend-dev",
                )
            expected_user_data = storage_root / "user-data" / identity["project_name"]
            expected_scratch = run_root / "backend-build-state"
            self.assertEqual(Path(environment["FULLMAG_WORKSPACE_STATE_ROOT"]), expected_user_data)
            self.assertEqual(Path(environment["FULLMAG_BACKEND_BUILD_STATE_ROOT"]), expected_scratch)
            self.assertTrue(expected_user_data.is_dir())
            self.assertTrue(expected_scratch.is_dir())
            for filename in ("compose.backend-build.yaml", "compose.backend-build-live.yaml"):
                overlay = (Path(__file__).resolve().parents[1] / filename).read_text(encoding="utf-8")
                self.assertIn("FULLMAG_WORKSPACE_STATE_ROOT", overlay)
                self.assertIn("target: /user-data", overlay)
                self.assertIn("read_only: true", overlay)
                self.assertIn("FULLMAG_BACKEND_BUILD_STATE_ROOT", overlay)
                self.assertIn("target: /state", overlay)

    def test_empty_owned_network_is_reusable_but_foreign_or_attached_is_rejected(self):
        project = "fullmag-worktree-network-test"
        identity = {
            "project_name": project,
            "network_name": project + "_fullmag",
            "project_id": "project-test",
            "worktree_id": "worktree-test",
            "checkout_kind": "worktree",
        }
        network_id = "a" * 64
        labels = {
            "org.fullmag.source.project-id": identity["project_id"],
            "org.fullmag.source.worktree-id": identity["worktree_id"],
            "org.fullmag.source.checkout-kind": identity["checkout_kind"],
            "org.fullmag.compose.project": project,
            "com.docker.compose.project": project,
            "com.docker.compose.network": "fullmag",
        }
        document = {
            "Name": identity["network_name"],
            "Id": network_id,
            "Driver": "bridge",
            "Scope": "local",
            "Containers": {},
            "Labels": labels,
        }

        def fake_docker(*args, **kwargs):
            if args and args[0] == "ps":
                return ""
            if args[:2] == ("network", "ls"):
                return network_id
            if args[:2] == ("network", "inspect"):
                return json.dumps([document])
            raise AssertionError(f"unexpected Docker read: {args}")

        with patch.object(docker_dev, "_docker_capture", side_effect=fake_docker):
            docker_dev._assert_no_running_fullmag(project, identity)
            document["Containers"] = {"endpoint": {}}
            with self.assertRaisesRegex(docker_dev.DirectDockerError, "attached containers"):
                docker_dev._assert_no_running_fullmag(project, identity)
            document["Containers"] = {}
            document["Labels"] = {**labels, "org.fullmag.source.worktree-id": "foreign"}
            with self.assertRaisesRegex(docker_dev.DirectDockerError, "source labels"):
                docker_dev._assert_no_running_fullmag(project, identity)

    def test_up_passes_resolved_source_identity_to_both_network_fences(self):
        repo = Path(__file__).resolve().parents[1]
        layout = {"repo_root": str(repo)}
        identity = {
            "project_name": "fullmag-worktree-network-test",
            "network_name": "fullmag-worktree-network-test_fullmag",
            "project_id": "project-test",
            "worktree_id": "worktree-test",
            "checkout_kind": "worktree",
        }
        args = types.SimpleNamespace(
            repo_root=repo,
            source_root=None,
            port=3197,
            script=None,
        )
        calls = []
        with patch.object(docker_dev, "_require_native_windows"), \
                patch.object(docker_dev, "_select_source", return_value=(repo, layout)), \
                patch.object(docker_dev, "_compose_identity", return_value=identity), \
                patch.object(docker_dev, "_assert_no_running_fullmag", side_effect=lambda *value: calls.append(value)), \
                patch.object(docker_dev, "_docker_capture", return_value=""), \
                patch.object(docker_dev, "build", return_value=repo / "assembly.json"), \
                patch.object(runtime, "assert_loopback_port_available"), \
                patch.object(runtime, "start"):
            docker_dev.up(args)
        self.assertEqual(calls, [(identity["project_name"], identity),
                                 (identity["project_name"], identity)])

    def test_frontend_workspace_reuse_checks_dependency_bytes_without_reseeding(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "workspace"
            destination.mkdir()
            metadata = destination / "package.json"
            metadata.write_bytes(b'{"name":"fullmag"}\n')
            digest = hashlib.sha256(metadata.read_bytes()).hexdigest()
            source_metadata = destination / "app.tsx"
            source_metadata.write_bytes(b"export const value = 1;\n")
            source_digest = hashlib.sha256(source_metadata.read_bytes()).hexdigest()
            live_directories = [
                {"name": name, "source": f"/checkout/apps/control-room/{name}",
                 "target": f"/state/development/workspace/apps/control-room/{name}"}
                for name in development_inputs.DIRECTORIES
            ]
            for item in live_directories:
                (destination / "apps" / "control-room" / item["name"]).mkdir(parents=True)
            old = {
                "schema": "fullmag.docker-development-inputs.v1",
                "source_root": "/checkout",
                "worktree_id": "checkout-1234567890abcdef",
                "host_port": 3197,
                "dependency_seed_sha256": "a" * 64,
                "toolpins_sha256": "b" * 64,
                "workspace_root": development_inputs.WORKSPACE,
                "frontend_root": development_inputs.FRONTEND,
                "live_directories": live_directories,
                "dependency_seed_files": ["package.json"],
                "files": [
                    {"relative": "app.tsx", "sha256": source_digest},
                    {"relative": "package.json", "sha256": digest},
                ],
            }
            current = {
                **{key: old[key] for key in (
                    "source_root", "worktree_id", "host_port",
                    "dependency_seed_sha256", "toolpins_sha256",
                    "workspace_root", "frontend_root", "live_directories",
                )},
                "dependency_seed_files": ["package.json"],
                "files": old["files"],
            }
            with patch.object(development_inputs, "read_owned_regular",
                              side_effect=lambda path, maximum: Path(path).read_bytes()):
                development_inputs._validate_reused_workspace(destination, current, old)
            metadata.write_bytes(b'{"name":"changed"}\n')
            with patch.object(development_inputs, "read_owned_regular",
                              side_effect=lambda path, maximum: Path(path).read_bytes()):
                with self.assertRaisesRegex(ValueError, "seed metadata was changed"):
                    development_inputs._validate_reused_workspace(destination, current, old)
            metadata.write_bytes(b'{"name":"fullmag"}\n')
            source_metadata.write_bytes(b"export const value = 2;\n")
            with patch.object(development_inputs, "read_owned_regular",
                              side_effect=lambda path, maximum: Path(path).read_bytes()):
                with self.assertRaisesRegex(ValueError, "seed metadata was changed"):
                    development_inputs._validate_reused_workspace(destination, current, old)

    def test_frontend_workspace_reuse_accepts_only_exact_next_generated_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "workspace"
            destination.mkdir()
            repo = Path(__file__).resolve().parents[1]
            relatives = (
                "apps/control-room/next-env.d.ts",
                "apps/control-room/tsconfig.json",
            )
            source_files = {
                relative: (repo / relative).read_bytes() for relative in relatives
            }
            next_env_newline = (
                b"\r\n"
                if b"\r\n" in source_files["apps/control-room/next-env.d.ts"]
                else b"\n"
            )
            generated = {
                "apps/control-room/next-env.d.ts": source_files[
                    "apps/control-room/next-env.d.ts"
                ].replace(
                    b'import "./.next/types/routes.d.ts";',
                    b'import "./.next-control-room-8080/dev/types/routes.d.ts";'
                    + next_env_newline
                    + b'import "./.next-control-room-8080/dev/types/root-params.d.ts";',
                    1,
                ),
                "apps/control-room/tsconfig.json": source_files[
                    "apps/control-room/tsconfig.json"
                ].replace(b"\r\n", b"\n").replace(
                    b'    ".next-control-room-3100/dev/types/**/*.ts"\n  ],',
                    b'    ".next-control-room-3100/dev/types/**/*.ts",\n'
                    b'    ".next-control-room-8080/types/**/*.ts",\n'
                    b'    ".next-control-room-8080/dev/types/**/*.ts"\n  ],',
                    1,
                ),
            }
            for relative in relatives:
                self.assertNotEqual(
                    source_files[relative],
                    generated[relative],
                    f"fixture generated variant is identical to its source: {relative}",
                )
            for relative, data in generated.items():
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            (destination / "package.json").write_bytes(b'{"name":"fullmag"}\n')
            for name in development_inputs.DIRECTORIES:
                (destination / "apps" / "control-room" / name).mkdir(parents=True)
            files = [
                {"relative": "package.json", "sha256": _sha256(destination / "package.json")},
                *[
                    {"relative": relative, "sha256": hashlib.sha256(data).hexdigest()}
                    for relative, data in source_files.items()
                ],
            ]
            live_directories = [
                {"name": name, "source": f"/checkout/apps/control-room/{name}",
                 "target": f"/state/development/workspace/apps/control-room/{name}"}
                for name in development_inputs.DIRECTORIES
            ]
            identity = {
                "schema": "fullmag.docker-development-inputs.v1",
                "source_root": "/checkout",
                "worktree_id": "checkout-1234567890abcdef",
                "host_port": 3197,
                "dependency_seed_sha256": "a" * 64,
                "toolpins_sha256": "b" * 64,
                "workspace_root": development_inputs.WORKSPACE,
                "frontend_root": development_inputs.FRONTEND,
                "live_directories": live_directories,
                "dependency_seed_files": ["package.json"],
                "files": files,
            }
            with patch.object(
                development_inputs,
                "read_owned_regular",
                side_effect=lambda path, maximum: Path(path).read_bytes(),
            ):
                development_inputs._validate_reused_workspace(
                    destination,
                    identity,
                    identity,
                    generated_sources=source_files,
                )
            unknown_tsconfig = destination / "apps/control-room/tsconfig.json"
            unknown_tsconfig_bytes = generated["apps/control-room/tsconfig.json"].replace(
                b".next-control-room-8080/dev/types/**/*.ts",
                b".next-control-room-9999/dev/types/**/*.ts",
                1,
            )
            self.assertNotEqual(
                unknown_tsconfig_bytes,
                generated["apps/control-room/tsconfig.json"],
            )
            unknown_tsconfig.write_bytes(unknown_tsconfig_bytes)
            with patch.object(
                development_inputs,
                "read_owned_regular",
                side_effect=lambda path, maximum: Path(path).read_bytes(),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    r"Persistent frontend seed metadata was changed: apps/control-room/tsconfig\.json",
                ):
                    development_inputs._validate_reused_workspace(
                        destination,
                        identity,
                        identity,
                        generated_sources=source_files,
                    )
            unknown_tsconfig.write_bytes(generated["apps/control-room/tsconfig.json"])
            tampered = destination / "apps/control-room/next-env.d.ts"
            tampered.write_bytes(generated["apps/control-room/next-env.d.ts"].replace(
                b"root-params", b"unexpected", 1
            ))
            with patch.object(
                development_inputs,
                "read_owned_regular",
                side_effect=lambda path, maximum: Path(path).read_bytes(),
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    r"Persistent frontend seed metadata was changed: apps/control-room/next-env\.d\.ts",
                ):
                    development_inputs._validate_reused_workspace(
                        destination,
                        identity,
                        identity,
                        generated_sources=source_files,
                    )
    def test_recreate_does_not_call_build_or_choose_latest(self):
        fake_runtime = types.ModuleType("fullmag_docker_runtime")
        fake_runtime.start = Mock()
        repo = Path(__file__).resolve().parents[1]
        args = types.SimpleNamespace(
            repo_root=repo,
            run_receipt=Path("/owned/receipt.json"),
            assembly_receipt=Path("/owned/new-assembly.json"),
            previous_config_sha256="a" * 64,
            source_root=None,
            port=3197,
            script=None,
            migrate_compose_project=False,
        )
        with patch.object(docker_dev, "_require_native_windows"), \
                patch.object(docker_dev, "_assert_no_running_fullmag") as guard, \
                patch.dict(sys.modules, {"fullmag_docker_runtime": fake_runtime}):
            docker_dev.recreate(args)
        fake_runtime.start.assert_called_once_with(
            repo.resolve(),
            args.assembly_receipt,
            3197,
            frontend="dev",
            source_root=None,
            startup_script=None,
            project_name=None,
            compose_template=repo.resolve() / docker_dev.COMPOSE_RUNTIME_FILE,
            run_receipt=args.run_receipt,
            previous_config_sha256=args.previous_config_sha256,
            migrate_compose_project=False,
        )
        guard.assert_not_called()

    def test_recreate_forwards_explicit_compose_project_migration(self):
        fake_runtime = types.ModuleType("fullmag_docker_runtime")
        fake_runtime.start = Mock()
        repo = Path(__file__).resolve().parents[1]
        args = types.SimpleNamespace(
            repo_root=repo,
            run_receipt=Path("/owned/receipt.json"),
            assembly_receipt=Path("/owned/new-assembly.json"),
            previous_config_sha256="d" * 64,
            source_root=None,
            port=3197,
            script=None,
            migrate_compose_project=True,
        )
        with patch.object(docker_dev, "_require_native_windows"), \
                patch.object(docker_dev, "_assert_no_running_fullmag") as guard, \
                patch.dict(sys.modules, {"fullmag_docker_runtime": fake_runtime}):
            docker_dev.recreate(args)
        fake_runtime.start.assert_called_once_with(
            repo.resolve(),
            args.assembly_receipt,
            3197,
            frontend="dev",
            source_root=None,
            startup_script=None,
            project_name=None,
            compose_template=repo.resolve() / docker_dev.COMPOSE_RUNTIME_FILE,
            run_receipt=args.run_receipt,
            previous_config_sha256=args.previous_config_sha256,
            migrate_compose_project=True,
        )
        guard.assert_not_called()

    def test_reuse_restart_sentinel_rotates_with_new_image_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            probe = state / ".windows-folder-probe"
            probe.mkdir()
            sentinel = probe / "restart-sentinel.bin"
            sentinel.write_bytes(b"old-owner:sha256:old")
            runtime._publish_restart_sentinel(state, b"old-owner:sha256:new")
            self.assertEqual(sentinel.read_bytes(), b"old-owner:sha256:new")


if __name__ == "__main__":
    unittest.main()
