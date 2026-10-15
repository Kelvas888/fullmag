#!/usr/bin/env python3
"""Interpreted regressions for the persistent frontend-cache-v1 adapter."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import docker_frontend_cache as cache
import fullmag_docker_runtime as runtime


IMAGE = "sha256:" + "a" * 64
UUID = "11111111-1111-1111-1111-111111111111"


class FakeDocker:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if args[0] == "ps":
            return ""
        if args[:2] == ("image", "inspect"):
            return json.dumps([{"Id": IMAGE, "Config": {"Volumes": None},
                                "Os": "linux", "Architecture": "amd64"}])
        if args[0] == "compose" and "config" in args:
            env = kwargs["environment"]
            volumes = [
                {"type": "bind", "source": env[cache.ENV_CACHE_SOURCE],
                 "target": cache.CHILD_TARGETS["cache"], "read_only": False},
                {"type": "bind", "source": env[cache.ENV_PNPM_SOURCE],
                 "target": cache.CHILD_TARGETS["pnpm_store"], "read_only": False},
                {"type": "bind", "source": env[cache.ENV_WORKSPACE_NODE_MODULES_SOURCE],
                 "target": cache.CHILD_TARGETS["workspace_node_modules"], "read_only": False},
                {"type": "bind", "source": env[cache.ENV_CONTROL_ROOM_NODE_MODULES_SOURCE],
                 "target": cache.CHILD_TARGETS["control_room_node_modules"], "read_only": False},
            ]
            return json.dumps({
                "name": "frontend-cache-test",
                "services": {
                    "frontend": {
                        "image": IMAGE,
                        "labels": {
                            cache.CONSUMER_PROFILE_LABEL: env[cache.ENV_PROFILE],
                            cache.CONSUMER_KEY_LABEL: env[cache.ENV_KEY],
                        },
                        "volumes": volumes,
                    },
                    cache.MAINTENANCE_SERVICE: {
                        "image": IMAGE, "privileged": True,
                        "network_mode": "none", "volumes": [],
                    },
                },
            })
        if args[0] == "compose" and "run" in args:
            env = kwargs["environment"]
            return json.dumps({
                "schema": cache.SCHEMA, "profile": cache.PROFILE,
                "state": "ready", "project_id": env[cache.ENV_PROJECT_ID],
                "cache_key": env[cache.ENV_KEY],
                "backing_image": env[cache.ENV_BACKING_IMAGE],
                "mount_root": env[cache.ENV_MOUNT_ROOT],
                "mount_target": env[cache.ENV_MOUNT_TARGET],
                "filesystem": "ext4", "filesystem_uuid": UUID,
                "filesystem_label": cache.IMAGE_LABEL,
                "loop_device": "/dev/loop7", "mount_active": True,
                "size_bytes": cache.CACHE_SIZE_BYTES,
                "runtime_image_id": IMAGE,
            })
        raise AssertionError(f"unexpected Docker call: {args!r}")


class FrontendCacheTests(unittest.TestCase):
    def test_python_shell_contract_uses_short_label_and_identical_paths(self):
        helper = Path(cache.__file__).parents[1] / "scripts" / "lib" / "docker_frontend_cache.sh"
        source = helper.read_text(encoding="utf-8")
        self.assertLessEqual(len(cache.IMAGE_LABEL.encode("ascii")), 16)
        self.assertIn(f'IMAGE_LABEL="{cache.IMAGE_LABEL}"', source)
        self.assertIn('+"\\n"', source)
        self.assertNotIn('+"\\\\n"', source)
        with tempfile.TemporaryDirectory() as temporary:
            paths = cache._cache_paths({"project_id": "fullmag-test", "storage_root": temporary}, "a" * 64)
            self.assertEqual(str(paths["lock_path"]), str(paths["backing_image"]) + ".lock")
        self.assertIn("inspect_unmounted", source)
        self.assertIn('elif [[ "$MOUNT_ACTIVE" == 1 ]]', source)

    def test_existing_image_reuse_only_verifies_and_mountpoint_must_be_empty(self):
        helper = Path(cache.__file__).parents[1] / "scripts" / "lib" / "docker_frontend_cache.sh"
        source = helper.read_text(encoding="utf-8")
        self.assertIn("local fresh_image=0", source)
        self.assertIn("fresh_image=1", source)
        reuse = 'if [[ "$fresh_image" == 0 ]]; then\n    verify_current\n    lock_runtime\n    return\n  fi'
        self.assertIn(reuse, source)
        self.assertLess(source.index(reuse), source.index('host chown 0:0 "$MOUNT_ROOT"'))
        self.assertIn("CREATED_IMAGE=\"$fresh_image\"", source)
        self.assertIn('emit ready "$CREATED_IMAGE"', source)
        self.assertIn('find "$MOUNT_ROOT" -mindepth 1 -maxdepth 1 -print -quit', source)
        self.assertNotIn('lost+found', source)

    def test_owner_marker_read_is_bounded_and_no_follow(self):
        helper = Path(cache.__file__).parents[1] / "scripts" / "lib" / "docker_frontend_cache.sh"
        source = helper.read_text(encoding="utf-8")
        self.assertIn("os.O_NOFOLLOW|os.O_CLOEXEC", source)
        self.assertIn("s=os.fstat(fd)", source)
        self.assertIn("s.st_size>16384", source)
        self.assertIn("raw=os.read(fd,16385)", source)

    def test_overlay_is_standalone_and_pins_attested_frontend_image(self):
        overlay = Path(cache.__file__).parents[1] / "compose.frontend-cache.yaml"
        source = overlay.read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r"(?ms)^  frontend:\n(?:.*\n){0,4}    image: \"\$\{FULLMAG_FRONTEND_CACHE_RUNTIME_IMAGE_ID",
        )
        self.assertIn("pull_policy: never", source)

    def test_image_identity_is_full_linux_digest(self):
        fake = FakeDocker()
        with self.assertRaises(cache.FrontendCacheError):
            cache._image_attestation(fake, "sha256:" + "a" * 63)

    def test_docker_json_parser_accepts_pretty_output_and_helper_tail(self):
        pretty = json.dumps({"services": {"frontend": {"image": IMAGE}}}, indent=2)
        self.assertEqual(cache._read_json_output(pretty)["services"]["frontend"]["image"], IMAGE)
        tailed = "helper progress 1/1\n" + json.dumps({"state": "ready"}) + "\n"
        self.assertEqual(cache._read_json_output(tailed), {"state": "ready"})

    def test_active_exact_key_consumer_is_rejected_by_inspect_guard(self):
        key = "a" * 64
        children = {
            "cache": "/mnt/cache/cache",
            "pnpm_store": "/mnt/cache/pnpm-store",
            "workspace_node_modules": "/mnt/cache/workspace-node_modules",
            "control_room_node_modules": "/mnt/cache/control-room_node_modules",
        }
        mounts = [
            {"Type": "bind", "Source": source, "Destination": target}
            for target, source in {
                cache.CHILD_TARGETS[name]: path for name, path in children.items()
            }.items()
        ]

        def docker(*args, **kwargs):
            if args[0] == "ps":
                return "a" * 12 + "\n"
            if args[0] == "inspect":
                return json.dumps([{
                    "Config": {"Labels": {
                        cache.CONSUMER_PROFILE_LABEL: cache.PROFILE,
                        cache.CONSUMER_KEY_LABEL: key,
                    }},
                    "Mounts": mounts,
                }])
            raise AssertionError(args)

        with self.assertRaisesRegex(cache.FrontendCacheError, "already held"):
            cache._assert_no_active_consumers(docker, key, children)

    def test_key_ignores_commit_and_authored_source_but_tracks_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "checkout"
            source.mkdir()
            first = cache.cache_key(source, "worktree-abc", 32871, "a" * 64)
            second = cache.cache_key(source, "worktree-abc", 32871, "a" * 64)
            self.assertEqual(first["key"], second["key"])
            (source / "page.tsx").write_text("changed", encoding="utf-8")
            self.assertEqual(
                first["key"],
                cache.cache_key(source, "worktree-abc", 32871, "a" * 64)["key"],
            )
            self.assertNotEqual(
                first["key"],
                cache.cache_key(source, "worktree-abc", 32871, "b" * 64)["key"],
            )

    def test_prepare_freezes_overlay_and_attests_ext4_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repo = root / "repo"
            (repo / "scripts" / "lib").mkdir(parents=True)
            (repo / "scripts" / "lib" / "docker_frontend_cache.sh").write_text(
                "#!/bin/sh\n", encoding="utf-8"
            )
            (repo / "compose.frontend-cache.yaml").write_text("services: {}\n", encoding="utf-8")
            source = root / "checkout"
            source.mkdir()
            fake = FakeDocker()
            layout = {"project_id": "fullmag-test", "storage_root": str(root / "storage")}
            result = cache.prepare(
                layout, repo, IMAGE, root / "run", fake,
                source_root=source, worktree_id="worktree-abc", host_port=32871,
                dependency_seed_sha256="a" * 64,
            )
            self.assertEqual(result["schema"], cache.SCHEMA)
            self.assertEqual(result["filesystem_uuid"], UUID)
            self.assertRegex(result["helper_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(result["compose_overlay_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(set(result["guest_targets"].values()), set(cache.CHILD_TARGETS.values()))
            self.assertTrue(Path(result["receipt_path"]).is_file())
            maintenance = json.loads(Path(result["maintenance_compose"]).read_text())
            self.assertEqual(set(maintenance["services"]), {cache.MAINTENANCE_SERVICE})
            self.assertNotIn("volumes", maintenance)
            self.assertTrue(any(args[0] == "compose" and "run" in args for args, _ in fake.calls))

    def test_container_attestation_rejects_missing_child_or_named_volume(self):
        profile = {
            "schema": cache.SCHEMA, "state": "ready", "cache_key": "a" * 64,
            "filesystem_uuid": UUID,
            "guest_targets": dict(cache.CHILD_TARGETS),
            "children": {name: "/mnt/cache/" + name for name in cache.CHILD_TARGETS},
            "environment": {
                cache.ENV_SCHEMA: cache.SCHEMA,
                cache.ENV_PROFILE: cache.PROFILE,
                cache.ENV_PROJECT_ID: "fullmag-test",
                cache.ENV_KEY: "a" * 64,
                cache.ENV_FILESYSTEM_UUID: UUID,
                cache.ENV_RUNTIME_IMAGE_ID: IMAGE,
            },
        }
        container = {
            "Config": {
                "Env": [f"{key}={value}" for key, value in profile["environment"].items()],
                "Labels": {
                    cache.CONSUMER_PROFILE_LABEL: cache.PROFILE,
                    cache.CONSUMER_KEY_LABEL: "a" * 64,
                },
            },
            "Mounts": [
                {"Type": "bind", "Source": profile["children"][name],
                 "Destination": profile["guest_targets"][name], "RW": True}
                for name in cache.CHILD_TARGETS
            ] + [{"Type": "tmpfs", "Destination": "/tmp", "RW": True}],
        }
        self.assertEqual(cache.validate_container(container, profile)["state"], "attested")
        container["Mounts"].pop(0)
        with self.assertRaises(cache.FrontendCacheError):
            cache.validate_container(container, profile)
        container["Mounts"] = [{"Type": "volume", "Source": "hidden", "Destination": "/state/development/cache"}]
        with self.assertRaises(cache.FrontendCacheError):
            cache.validate_container(container, profile)

    def test_runtime_compose_spec_requires_and_wires_cache_overlay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repo = root / "repo"
            (repo / "scripts" / "lib").mkdir(parents=True)
            (repo / "scripts" / "lib" / "docker_frontend_cache.sh").write_text(
                "#!/bin/sh\n", encoding="utf-8"
            )
            overlay = repo / "compose.frontend-cache.yaml"
            overlay.write_text("services: {}\n", encoding="utf-8")
            source = root / "checkout"
            source.mkdir()
            profile = cache.prepare(
                {"project_id": "fullmag-test", "storage_root": str(root / "storage")},
                repo, IMAGE, root / "run", FakeDocker(), source_root=source,
                worktree_id="worktree-abc", host_port=32871,
                dependency_seed_sha256="a" * 64,
            )

            calls = []

            def compose(*args, **kwargs):
                calls.append((args, kwargs))
                return json.dumps({"services": {"backend": {}, "frontend": {}}})

            with mock.patch.object(runtime, "docker", side_effect=compose):
                configured = runtime.compose_spec(
                    IMAGE, root / "state", 32871, root / "certificate.json",
                    repo=repo, inputs={"source_root": str(source)},
                    inputs_path=root / "inputs.json", package=root / "package",
                    provenance=root / "assembly.json", frontend_cache=profile,
                )
            self.assertEqual(set(configured["services"]), {"backend", "frontend"})
            args, kwargs = calls[0]
            self.assertIn(profile["compose_overlay"], args)
            self.assertEqual(
                kwargs["environment"][cache.ENV_KEY], profile["environment"][cache.ENV_KEY]
            )
    def test_helper_is_independent_and_shell_parses(self):
        helper = Path(cache.__file__).parents[1] / "scripts" / "lib" / "docker_frontend_cache.sh"
        source = helper.read_text(encoding="utf-8")
        self.assertNotIn("docker_host_ledger", source)
        self.assertEqual(subprocess.run(["bash", "-n", str(helper)], check=False).returncode, 0)
        overlay = helper.parents[2] / "compose.frontend-cache.yaml"
        self.assertNotIn("\nvolumes:\n", overlay.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
