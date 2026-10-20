"""Contract and pure-validator regressions for the managed Docker DEV browser proof."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def _load_qa_module():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("docker_dev_browser_qa_draft", ROOT / "scripts" / "docker_dev_browser_qa.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load browser QA wrapper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _recovery_fixture(qa):
    selected = ROOT.resolve()
    identity = {
        "project_id": "fullmag",
        "worktree_id": "fixture",
        "checkout_kind": "worktree",
    }
    project = "fullmag-worktree-fixture"
    attempt = "a" * 32
    runtime_attempt = "b" * 32
    image = "sha256:" + "c" * 64
    document = {"name": project, "services": {"backend": {}, "frontend": {}}}
    config_sha256 = hashlib.sha256(qa.canonical(document)).hexdigest()
    original_inputs = {
        "schema": "fullmag.docker-development-inputs.v1",
        "source_root": str(selected),
        "source_project_id": identity["project_id"],
        "source_worktree_id": identity["worktree_id"],
        "source_checkout_kind": identity["checkout_kind"],
        "image_id": image,
        "source_commit": "1" * 40,
    }
    original = {
        "state": "failed-confirmed",
        "phase": "development",
        "attempt": attempt,
        "compose_project": project,
        "config_sha256": config_sha256,
        "inputs": original_inputs,
        "source_commit": original_inputs["source_commit"],
        "frontend_volume": "fullmag-frontend-state",
    }
    recovered = {
        "state": "succeeded",
        "phase": "resume",
        "attempt": runtime_attempt,
        "compose_project": project,
        "config_sha256": config_sha256,
        "inputs": {
            "attempt": attempt,
            "config_sha256": config_sha256,
            "source_root": str(selected),
            "image_id": image,
        },
        "backend_container": "d" * 64,
        "frontend_container": "e" * 64,
        "finished_at": 42,
    }

    class FakeControl:
        def __init__(self):
            self.project = project
            self.documents = {
                "development/current.json": deepcopy(original),
                f"development/attempts/{attempt}/terminal.json": deepcopy(original),
                f"development/attempts/{attempt}/compose.json": deepcopy(document),
                "frontend/development-inputs.json": {
                    "source_root": str(selected),
                    "worktree_id": identity["worktree_id"],
                    "host_port": "3199",
                },
            }
            self.reads = []

        def read(self, path, optional=False):
            self.reads.append((path, optional))
            if path not in self.documents:
                if optional:
                    return None
                raise AssertionError(f"unexpected control-volume read: {path}")
            return deepcopy(self.documents[path])

    return {
        "selected": selected,
        "identity": identity,
        "project": project,
        "attempt": attempt,
        "runtime_attempt": runtime_attempt,
        "image": image,
        "document": document,
        "config_sha256": config_sha256,
        "original_inputs": original_inputs,
        "original": original,
        "recovered": recovered,
        "control": FakeControl(),
    }


class DockerDevBrowserQaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qa = _load_qa_module()

    def test_failed_development_resolves_only_verified_linked_runtime_and_keeps_original_provenance(self):
        qa = self.qa
        case = _recovery_fixture(qa)
        activation = importlib.import_module("docker_volume_activate")
        original_before = deepcopy(case["original"])
        resolved_ids = ("backend-runtime", "frontend-runtime")
        stale_candidate = {**deepcopy(case["recovered"]), "attempt": "f" * 32, "finished_at": 99}
        with patch.object(
            activation, "_linked_runtime_terminals", return_value=[stale_candidate, case["recovered"]],
        ) as linked, \
             patch.object(
                 activation,
                 "_validate_running_group",
                 side_effect=[qa.BuildControlError("stale candidate is no longer running"), resolved_ids],
             ) as validate:
            result = qa._read_live_development(
                case["control"], case["selected"], case["identity"], 3199,
            )

        current, backend_id, frontend_id, frontend_volume, frontend_inputs = result
        self.assertEqual(current["state"], "succeeded")
        self.assertEqual(current["development_terminal_state"], "failed-confirmed")
        self.assertEqual(current["attempt"], case["attempt"])
        self.assertEqual(current["phase"], "development")
        self.assertEqual(current["inputs"], case["original_inputs"])
        self.assertEqual(current["runtime_attempt"], case["runtime_attempt"])
        self.assertEqual(current["runtime_phase"], "resume")
        self.assertEqual(
            current["development_fence_sha256"],
            hashlib.sha256(qa.canonical(original_before)).hexdigest(),
        )
        self.assertEqual(
            current["runtime_terminal_sha256"],
            hashlib.sha256(qa.canonical(case["recovered"])).hexdigest(),
        )
        self.assertEqual(backend_id, case["recovered"]["backend_container"])
        self.assertEqual(frontend_id, case["recovered"]["frontend_container"])
        self.assertEqual(frontend_volume, "fullmag-frontend-state")
        self.assertEqual(frontend_inputs["worktree_id"], case["identity"]["worktree_id"])
        self.assertEqual(case["original"], original_before)
        linked.assert_called_once_with(
            case["control"], case["attempt"], case["original"],
            source_root=str(case["selected"]), image=case["image"],
            config_sha256=case["config_sha256"],
        )
        self.assertEqual(validate.call_count, 2)
        self.assertEqual(validate.call_args_list[0].args[3], stale_candidate)
        self.assertEqual(validate.call_args_list[1].args[3], case["recovered"])

    def test_failed_development_rejects_stale_terminal_config_source_missing_link_and_ambiguous_live_ids(self):
        qa = self.qa
        activation = importlib.import_module("docker_volume_activate")

        with self.subTest(reason="current differs from its terminal"), \
             patch.object(activation, "_linked_runtime_terminals") as linked, \
             patch.object(activation, "_validate_running_group"):
            case = _recovery_fixture(qa)
            case["control"].documents[
                f"development/attempts/{case['attempt']}/terminal.json"
            ]["state"] = "failed"
            with self.assertRaisesRegex(qa.BuildControlError, "differs from its terminal"):
                qa._read_recovered_development(
                    case["control"], case["original"], case["selected"], case["identity"],
                )
            linked.assert_not_called()

        with self.subTest(reason="configuration pin differs"), \
             patch.object(activation, "_linked_runtime_terminals") as linked, \
             patch.object(activation, "_validate_running_group"):
            case = _recovery_fixture(qa)
            case["original"]["config_sha256"] = "f" * 64
            case["control"].documents[
                f"development/attempts/{case['attempt']}/terminal.json"
            ] = deepcopy(case["original"])
            with self.assertRaisesRegex(qa.BuildControlError, "original/config pin differs"):
                qa._read_recovered_development(
                    case["control"], case["original"], case["selected"], case["identity"],
                )
            linked.assert_not_called()

        with self.subTest(reason="source differs from selected checkout"), \
             patch.object(activation, "_linked_runtime_terminals") as linked, \
             patch.object(activation, "_validate_running_group"):
            case = _recovery_fixture(qa)
            case["original"]["inputs"]["source_root"] = str(case["selected"].parent)
            case["control"].documents[
                f"development/attempts/{case['attempt']}/terminal.json"
            ] = deepcopy(case["original"])
            with self.assertRaisesRegex(qa.BuildControlError, "recovery source differs"):
                qa._read_recovered_development(
                    case["control"], case["original"], case["selected"], case["identity"],
                )
            linked.assert_not_called()

        with self.subTest(reason="no succeeded linked runtime"), \
             patch.object(activation, "_linked_runtime_terminals", return_value=[]) as linked, \
             patch.object(activation, "_validate_running_group") as validate:
            case = _recovery_fixture(qa)
            with self.assertRaisesRegex(qa.BuildControlError, "exactly one live group"):
                qa._read_recovered_development(
                    case["control"], case["original"], case["selected"], case["identity"],
                )
            linked.assert_called_once()
            validate.assert_not_called()

        with self.subTest(reason="linked receipts resolve to distinct live groups"), \
             patch.object(
                 activation,
                 "_linked_runtime_terminals",
                 side_effect=lambda _control, _attempt, _original, **_kwargs: [
                     {**_recovery_fixture(qa)["recovered"], "attempt": "b" * 32},
                     {**_recovery_fixture(qa)["recovered"], "attempt": "c" * 32, "phase": "iteration"},
                 ],
             ) as linked, \
             patch.object(
                 activation,
                 "_validate_running_group",
                 side_effect=[("backend-one", "frontend-one"), ("backend-two", "frontend-two")],
             ) as validate:
            case = _recovery_fixture(qa)
            with self.assertRaisesRegex(qa.BuildControlError, "exactly one live group"):
                qa._read_recovered_development(
                    case["control"], case["original"], case["selected"], case["identity"],
                )
            linked.assert_called_once()
            self.assertEqual(validate.call_count, 2)

    def test_succeeded_development_receipt_keeps_direct_read_path(self):
        qa = self.qa
        selected = ROOT.resolve()
        identity = {
            "project_id": "fullmag",
            "worktree_id": "fixture",
            "checkout_kind": "worktree",
        }
        current = {
            "state": "succeeded",
            "compose_project": "fullmag-worktree-fixture",
            "inputs": {
                "source_root": str(selected),
                "source_project_id": identity["project_id"],
                "source_worktree_id": identity["worktree_id"],
                "source_checkout_kind": identity["checkout_kind"],
            },
            "backend_container": "backend-current",
            "frontend_container": "frontend-current",
            "frontend_volume": "fullmag-frontend-state",
        }
        frontend_inputs = {
            "source_root": str(selected),
            "worktree_id": identity["worktree_id"],
            "host_port": "3199",
        }

        class FakeControl:
            project = "fullmag-worktree-fixture"

            def read(self, path):
                if path == "development/current.json":
                    return current
                if path == "frontend/development-inputs.json":
                    return frontend_inputs
                raise AssertionError(f"unexpected control-volume read: {path}")

        with patch.object(qa, "_read_recovered_development") as recover:
            result = qa._read_live_development(FakeControl(), selected, identity, 3199)

        self.assertEqual(result[0]["state"], current["state"])
        self.assertEqual(result[0]["inputs"], current["inputs"])
        self.assertEqual(
            result[0]["development_fence_sha256"],
            hashlib.sha256(qa.canonical(current)).hexdigest(),
        )
        self.assertEqual(result[1:], (
            "backend-current", "frontend-current", "fullmag-frontend-state", frontend_inputs,
        ))
        recover.assert_not_called()

    def test_just_recipe_stays_on_managed_python_route(self):
        text = (ROOT / "justfile").read_text(encoding="utf-8")
        match = re.search(r"(?ms)^docker-dev-browser-qa .*?(?=^\S|\Z)", text)
        self.assertIsNotNone(match)
        recipe = match.group(0)
        self.assertIn("docker_dev_browser_qa.py", recipe)
        self.assertIn('source_root="" port=""', recipe)
        self.assertIn("--port", recipe)
        self.assertIn('pull_timeout="1800"', recipe)
        self.assertIn("--pull-timeout", recipe)
        self.assertNotIn('port="32871"', recipe)
        self.assertNotIn("pnpm", recipe)
        self.assertNotIn("node ", recipe)
        shell = (ROOT / "scripts/just_storage_shell.sh").read_text(encoding="utf-8")
        self.assertIn('scripts/docker_dev_browser_qa.py', shell)
        self.assertIn('browser_qa_pattern=', shell)
        self.assertIn('--pull-timeout', shell)
        self.assertIn('exec "${python_cmd}" -B "${script_dir}/docker_dev_browser_qa.py"', shell)

    def test_browser_service_has_no_host_writes_or_published_ports(self):
        identity = {
            "project_name": "fullmag-worktree-fixture",
            "network_name": "fullmag-worktree-fixture_fullmag",
            "project_id": "fullmag",
            "worktree_id": "fixture",
            "checkout_kind": "worktree",
            "source_root": str(ROOT),
        }
        document = self.qa._compose_document(
            ROOT, identity, self.qa.DEFAULT_BROWSER_IMAGE,
            "fullmag-frontend-state", 3199, 180,
        )
        self.assertEqual(document["name"], identity["project_name"])
        self.assertEqual(document["volumes"], {
            "frontend-state": {"name": "fullmag-frontend-state", "external": True},
        })
        self.assertEqual(document["networks"], {
            "fullmag": {"name": identity["network_name"], "external": True},
        })
        service = document["services"]["browser-qa"]
        self.assertNotIn("ports", service)
        self.assertNotIn("network_mode", service)
        self.assertNotIn("extra_hosts", service)
        self.assertEqual(service["pull_policy"], "never")
        self.assertEqual(service["logging"], {"driver": "none"})
        self.assertEqual(service["environment"]["CONTROL_ROOM_URL"], "http://frontend:8080")
        self.assertTrue(all(mount["read_only"] for mount in service["volumes"]))
        self.assertEqual({mount["target"] for mount in service["volumes"]}, {
            "/state/development",
            "/state/development/workspace/apps/control-room/scripts",
        })

    def test_compose_fixture_keeps_owned_volume_readonly_to_matching_uid(self):
        identity = {
            "project_name": "fullmag-worktree-fixture",
            "network_name": "fullmag-worktree-fixture_fullmag",
            "project_id": "fullmag",
            "worktree_id": "fixture",
            "checkout_kind": "worktree",
            "source_root": str(ROOT),
        }
        image = "mcr.microsoft.com/playwright:v1.62.1-noble@sha256:" + "a" * 64
        document = self.qa._compose_document(ROOT, identity, image, "fullmag-frontend-state", 32871, 180)
        service = document["services"]["browser-qa"]
        self.assertEqual(service["user"], "65532:65532")
        self.assertTrue(service["read_only"])
        self.assertEqual(service["environment"]["CONTROL_ROOM_URL"], "http://frontend:8080")
        self.assertEqual(service["environment"]["NVIDIA_VISIBLE_DEVICES"], "void")
        self.assertNotIn("extra_hosts", service)
        self.assertEqual(service["volumes"][0]["read_only"], True)
        self.assertEqual(service["volumes"][1]["read_only"], True)
        self.assertEqual(document["networks"]["fullmag"]["name"], identity["network_name"])

    def test_browser_helper_inspect_enforces_uid_environment_and_mount_boundary(self):
        qa = self.qa
        identity = {
            "project_name": "fullmag-worktree-fixture",
            "network_name": "fullmag-worktree-fixture_fullmag",
            "project_id": "fullmag",
            "worktree_id": "fixture",
            "checkout_kind": "worktree",
            "source_root": str(ROOT),
        }
        class FakeControl:
            project = "fullmag-worktree-fixture"
            volume = "fullmag-control-fixture"

        browser_id = "sha256:" + "c" * 64
        document = {
            "Id": browser_id,
            "Image": browser_id,
            "Config": {
                "User": "65532:65532",
                "Env": [
                    "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
                    "CONTROL_ROOM_URL=http://frontend:8080",
                    "NVIDIA_VISIBLE_DEVICES=void",
                ],
                "Labels": {
                    "org.fullmag.source.project-id": "fullmag",
                    "org.fullmag.source.worktree-id": "fixture",
                    "org.fullmag.source.checkout-kind": "worktree",
                    "org.fullmag.compose.project": identity["project_name"],
                    "com.docker.compose.project": identity["project_name"],
                    "com.docker.compose.service": "browser-qa",
                },
            },
            "HostConfig": {
                "ReadonlyRootfs": True,
                "NetworkMode": identity["network_name"],
                "PortBindings": None,
                "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=256m"},
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges:true"],
                "ExtraHosts": None,
            },
            "State": {"Running": False, "ExitCode": 0},
            "NetworkSettings": {"Networks": {identity["network_name"]: {}}},
            "Mounts": [
                {"Type": "volume", "Name": "fullmag-frontend-state", "Destination": "/state/development", "RW": False},
                {
                    "Type": "bind",
                    "Source": str(ROOT / "apps/control-room/scripts"),
                    "Destination": "/state/development/workspace/apps/control-room/scripts",
                    "RW": False,
                },
            ],
        }
        qa._validate_browser_helper(document, FakeControl(), identity, "fullmag-frontend-state", browser_id, 0, ROOT)
        wrong_user = deepcopy(document)
        wrong_user["Config"]["User"] = "0:0"
        with self.assertRaises(qa.ControlOutcomeUnknown):
            qa._validate_browser_helper(wrong_user, FakeControl(), identity, "fullmag-frontend-state", browser_id, 0, ROOT)
        writable_mount = deepcopy(document)
        writable_mount["Mounts"][0]["RW"] = True
        with self.assertRaises(qa.ControlOutcomeUnknown):
            qa._validate_browser_helper(writable_mount, FakeControl(), identity, "fullmag-frontend-state", browser_id, 0, ROOT)

    def test_control_volume_preflight_is_read_only_and_fail_closed_when_absent(self):
        qa = self.qa

        class FakeControl:
            volume = "fullmag-control-fixture"
            shared_labels = {"com.fullmag.compose.project": "fullmag-worktree-fixture"}

        missing = SimpleNamespace(returncode=1, stdout=b"", stderr=b"no such volume")
        with patch.object(qa, "docker_capture", return_value=missing) as daemon:
            with self.assertRaises(qa.BuildControlError):
                qa._validate_existing_control_volume(FakeControl())
        daemon.assert_called_once_with(
            "volume", "inspect", "fullmag-control-fixture", allow_failure=True, timeout=60
        )

    def test_frontend_volume_preflight_requires_deterministic_owned_labels(self):
        qa = self.qa
        inputs = {
            "schema": "fullmag.docker-development-inputs.v1",
            "dependency_seed_sha256": "a" * 64,
            "toolpins_sha256": "b" * 64,
        }
        key = hashlib.sha256(
            qa.canonical({"project": "fullmag-worktree-fixture", "dependencies": "a" * 64, "tools": "b" * 64})
        ).hexdigest()
        volume_name = "fullmag-dev-frontend-v1-" + key[:24]

        class FakeControl:
            project = "fullmag-worktree-fixture"
            labels = {
                "org.fullmag.compose.project": project,
                "org.fullmag.source.worktree-id": "fixture",
            }

        labels = {
            **FakeControl.labels,
            "org.fullmag.build.role": "frontend",
            "org.fullmag.build.cache-key": key,
        }
        observed = {"Name": volume_name, "Driver": "local", "Options": {}, "Labels": labels}
        with patch.object(
            qa,
            "docker_capture",
            return_value=SimpleNamespace(returncode=0, stdout=json.dumps([observed]).encode(), stderr=b""),
        ):
            qa._validate_frontend_volume(FakeControl(), volume_name, inputs)
        drifted = deepcopy(observed)
        drifted["Labels"]["org.fullmag.build.cache-key"] = "c" * 64
        with patch.object(
            qa,
            "docker_capture",
            return_value=SimpleNamespace(returncode=0, stdout=json.dumps([drifted]).encode(), stderr=b""),
        ):
            with self.assertRaises(qa.BuildControlError):
                qa._validate_frontend_volume(FakeControl(), volume_name, inputs)

    def test_browser_image_reuses_compatible_local_digest_without_pull(self):
        qa = self.qa
        image = qa.DEFAULT_BROWSER_IMAGE
        operation = {"root": "browser-qa/attempts/" + "c" * 32,
                     "receipt": {"attempt": "c" * 32}, "daemon_pending": False}
        writes = []

        class FakeControl:
            project = "fullmag-worktree-fixture"

            def write(self, path, value):
                writes.append((path, deepcopy(value)))

        image_document = {
            "Id": "sha256:" + "d" * 64,
            "RepoDigests": [qa._canonical_repo_digest(image)],
        }
        with patch.object(qa, "_inspect_image", return_value=image_document) as inspect, \
             patch.object(qa, "docker_capture") as daemon:
            image_id, observed = qa._ensure_browser_image(
                operation, FakeControl(), {"services": {"browser-qa": {"pull_policy": "never"}}}, image, 180,
            )

        inspect.assert_called_once_with(image)
        daemon.assert_not_called()
        self.assertIs(observed, image_document)
        self.assertEqual(image_id, image_document["Id"])
        self.assertEqual(operation["receipt"]["browser_image_source"], "local-reuse")
        self.assertEqual(operation["receipt"]["browser_image_pull_state"], "reused")
        self.assertEqual(operation["receipt"]["browser_image_pull_timeout"], 180)
        self.assertTrue(any(path.endswith("/browser-image-pull.json") for path, _value in writes))

    def test_browser_image_absent_uses_same_group_compose_pull_and_inspects_pin(self):
        qa = self.qa
        image = qa.DEFAULT_BROWSER_IMAGE
        operation = {"root": "browser-qa/attempts/" + "e" * 32,
                     "receipt": {"attempt": "e" * 32}, "daemon_pending": False}
        writes = []
        daemon_calls = []
        image_document = {
            "Id": "sha256:" + "f" * 64,
            "RepoDigests": [qa._canonical_repo_digest(image)],
        }
        preflight = {"available_bytes": 40 * 1024**3,
                     "minimum_free_bytes": qa.MIN_FREE_BUILD_BYTES}

        class FakeControl:
            project = "fullmag-worktree-fixture"

            def space(self):
                return preflight

            def write(self, path, value):
                writes.append((path, deepcopy(value)))

        def fake_daemon(*args, **kwargs):
            daemon_calls.append((args, kwargs))
            return SimpleNamespace(returncode=0, stdout=b"pulled", stderr=b"")

        with patch.object(qa, "_inspect_image", side_effect=[None, image_document]), \
             patch.object(qa, "docker_capture", side_effect=fake_daemon):
            image_id, observed = qa._ensure_browser_image(
                operation,
                FakeControl(),
                {"services": {"browser-qa": {"pull_policy": "never"}}},
                image,
                180,
            )

        self.assertEqual(image_id, image_document["Id"])
        self.assertIs(observed, image_document)
        self.assertFalse(operation["daemon_pending"])
        self.assertEqual(operation["receipt"]["browser_image_source"], "compose-pull")
        self.assertEqual(operation["receipt"]["browser_image_pull_state"], "succeeded")
        self.assertEqual(operation["receipt"]["browser_image_pull_timeout"], 180)
        self.assertEqual(daemon_calls[0][0][:9], ("compose", "--project-name", "fullmag-worktree-fixture", "--ansi", "never", "-f", "-", "pull", "browser-qa"))
        pull_manifest = json.loads(daemon_calls[0][1]["data"])
        self.assertEqual(pull_manifest["services"]["browser-qa"]["pull_policy"], "missing")
        self.assertTrue(any(path.endswith("/receipt.json") and value.get("browser_image_id") == image_document["Id"] for path, value in writes))

    def test_browser_image_pull_timeout_retains_daemon_pending_and_receipt(self):
        qa = self.qa
        image = qa.DEFAULT_BROWSER_IMAGE
        operation = {"root": "browser-qa/attempts/" + "1" * 32,
                     "receipt": {"attempt": "1" * 32}, "daemon_pending": False}
        writes = []
        preflight = {"available_bytes": 40 * 1024**3,
                     "minimum_free_bytes": qa.MIN_FREE_BUILD_BYTES}

        class FakeControl:
            project = "fullmag-worktree-fixture"

            def space(self):
                return preflight

            def write(self, path, value):
                writes.append((path, deepcopy(value)))

        def timed_out(*_args, **_kwargs):
            raise qa.ControlOutcomeUnknown("Docker observation exceeded its time/output budget; daemon resources retained")

        with patch.object(qa, "_inspect_image", return_value=None), \
             patch.object(qa, "docker_capture", side_effect=timed_out):
            with self.assertRaises(qa.ControlOutcomeUnknown):
                qa._ensure_browser_image(
                    operation,
                    FakeControl(),
                    {"services": {"browser-qa": {"pull_policy": "never"}}},
                    image,
                    1,
                )

        self.assertTrue(operation["daemon_pending"])
        self.assertEqual(operation["receipt"]["browser_image_pull_state"], "outcome-unknown-resources-retained")
        self.assertTrue(any(path.endswith("/browser-image-pull.json") and value["state"] == "outcome-unknown-resources-retained" for path, value in writes))
        self.assertTrue(any(path.endswith("/receipt.json") and value["browser_image_pull_state"] == "outcome-unknown-resources-retained" for path, value in writes))

    def test_run_keeps_control_lease_helper_separate_from_browser_helper_on_error(self):
        qa = self.qa
        operation = {
            "root": "browser-qa/attempts/" + "a" * 32,
            "receipt": {
                "attempt": "a" * 32,
                "helper_container": "fullmag-control-" + "a" * 32,
            },
            "daemon_pending": False,
        }
        writes = []
        daemon_calls = []

        class FakeControl:
            project = "fullmag-worktree-fixture"

            def write(self, path, value):
                writes.append((path, deepcopy(value)))

        browser_id = "sha256:" + "b" * 64
        observed = {"Id": browser_id}
        compose_result = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

        def fake_daemon(*args, **_kwargs):
            daemon_calls.append(args)
            if args[0] == "compose":
                return compose_result
            if args[0] == "rm":
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            if args[0] == "inspect":
                return SimpleNamespace(returncode=1, stdout=b"", stderr=b"not found")
            raise AssertionError(f"unexpected daemon command: {args!r}")

        def fake_parse(*_args):
            raise qa.BuildControlError("invalid canvas evidence")

        with patch.object(qa, "_probe_public_loopback", return_value={"state": "passed"}), \
             patch.object(qa, "docker_capture", side_effect=fake_daemon), \
             patch.object(qa, "_inspect", return_value=observed), \
             patch.object(qa, "_validate_browser_helper"), \
             patch.object(qa, "_parse_result", side_effect=fake_parse):
            with self.assertRaises(qa.BuildControlError):
                qa._run(
                    operation,
                    FakeControl(),
                    {"services": {}},
                    {"project_name": "fullmag-worktree-fixture"},
                    ROOT,
                    "fullmag-frontend-state",
                    browser_id,
                    "http://127.0.0.1:32871",
                    "http://frontend:8080",
                    180,
                )

        self.assertEqual(operation["receipt"]["helper_container"], "fullmag-control-" + "a" * 32)
        self.assertEqual(operation["receipt"]["browser_container_name"], "fullmag-browser-qa-" + "a" * 12)
        self.assertEqual(operation["receipt"]["browser_container_id"], browser_id)
        self.assertEqual(operation["receipt"]["state"], "failed-confirmed")
        self.assertEqual(operation["receipt"]["error"], "invalid canvas evidence")
        self.assertEqual([call[:2] for call in daemon_calls if call[0] in {"rm", "inspect"}], [("rm", browser_id), ("inspect", browser_id)])
        self.assertTrue(any(path.endswith("/result.json") for path, _value in writes))
        receipts = [value for path, value in writes if path.endswith("/receipt.json")]
        self.assertTrue(any(value.get("browser_container_id") == browser_id for value in receipts))

    def test_result_validator_rejects_invalid_buffers_and_recorded_errors(self):
        canvas = {
            "rect": {"width": 1440, "height": 900},
            "width": 1440,
            "height": 900,
            "context_type": "WebGL2RenderingContext",
            "context_lost": False,
            "drawing_buffer_width": 1440,
            "drawing_buffer_height": 900,
        }
        payload = {
            "schema": self.qa.RESULT_SCHEMA,
            "state": "passed",
            "public_url": "http://127.0.0.1:32871",
            "probe_url": "http://frontend:8080",
            "playwright_version": "1.62.1",
            "browser_gpu_mode": "swiftshader-webgl-requested",
            "home_round_trip": True,
            "session": {
                "session_id": "session-1",
                "session_epoch": "session-1@1",
                "request_scope_epoch": "api:1",
            },
            "workspace": {"visible": True, "canvas_dom_stable": True},
            "canvas_before": canvas,
            "canvas_after": deepcopy(canvas),
            "page_errors": 0,
            "console_errors": 0,
            "request_failures": 0,
        }
        encoded = lambda value: (json.dumps(value) + "\n").encode("utf-8")
        self.assertEqual(self.qa._parse_result(encoded(payload), payload["public_url"], payload["probe_url"]), payload)
        invalid_buffer = deepcopy(payload)
        invalid_buffer["canvas_after"]["drawing_buffer_width"] = 0
        with self.assertRaises(self.qa.BuildControlError):
            self.qa._parse_result(encoded(invalid_buffer), payload["public_url"], payload["probe_url"])
        invalid_errors = deepcopy(payload)
        invalid_errors["console_errors"] = 1
        with self.assertRaises(self.qa.BuildControlError):
            self.qa._parse_result(encoded(invalid_errors), payload["public_url"], payload["probe_url"])
        invalid_session = deepcopy(payload)
        invalid_session["session"]["request_scope_epoch"] = ""
        with self.assertRaises(self.qa.BuildControlError):
            self.qa._parse_result(encoded(invalid_session), payload["public_url"], payload["probe_url"])

    def test_browser_flow_proves_existing_session_home_and_webgl(self):
        text = (ROOT / "apps/control-room/scripts/docker-dev-browser-qa.mjs").read_text(encoding="utf-8")
        for required in (
            'require("playwright/package.json")',
            "1.62.1",
            '.fm-home-overlay[data-state="home-overlay"]',
            'name: "Start"',
            'name: "Back to simulation"',
            '"/v2/sessions/current/status"',
            'elementHandle()',
            'canvasHandle.evaluate',
            '"--enable-unsafe-swiftshader"',
            '"--use-angle=swiftshader-webgl"',
            '"--no-sandbox"',
            'getContext("webgl2")',
            "isContextLost",
            "drawingBufferWidth",
            "drawingBufferHeight",
            "browser_gpu_mode",
            "canvas_dom_stable",
        ):
            self.assertIn(required, text)
        self.assertNotIn("screenshot", text.lower())
        self.assertNotIn('http://127.0.0.1:32871', text.split("const publicUrl", 1)[1].split("const probeUrl", 1)[0])
        self.assertNotIn("CONTROL_ROOM_SMOKE_ALLOW_MISSING_SESSION", text)

    def test_lock_and_managed_check_registration_are_pinned(self):
        lock = (ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
        self.assertRegex(lock, r"playwright:\n\s+specifier: \^1\.60\.0\n\s+version: 1\.62\.1")
        self.assertIn("test_docker_dev_browser_qa", (ROOT / "scripts/docker_volume_checks.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
