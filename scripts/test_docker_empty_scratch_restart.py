"""Empty scratch proof checks without Docker or runtime mutations."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import docker_empty_scratch_restart as scratch


class EmptyScratchTests(unittest.TestCase):
    def fixture(self):
        session = "session-probe"
        instance = "11111111-1111-4111-8111-111111111111"
        return {"api_instance": instance,
            "session": {"session_id": session, "status": "awaiting_command", "script": None, "script_path": ""},
            "status": {"session": {"session_id": session, "created_at": "123", "session_epoch": session + "@123",
                "request_scope_epoch": instance + ":1"}, "run": None, "solver": {"state": "awaiting_command"},
                "metrics": {"total_steps": 0, "uptime_seconds": 10}, "domain": {"cell_count": 0},
                "resources": {"scene_revision": 0, "commands_revision": 0, "domain_generation_id": "0"}},
            "scene": {"version": "scene.v2", "revision": 0, "scene": {"id": session, "source_of_truth": "ui"},
                "study": {"demag_enabled": False, "exchange_enabled": False}, "outputs": {}, "objects": []},
            "commands": {"commands": [], "revision": 0, **{key: 0 for key in ("pending_count", "accepted_count",
                "dispatched_count", "running_count", "completed_count", "rejected_count", "failed_count")}},
            "compute_queue": {"schema_version": "compute_queue.v1", "items": []},
            "health": {"status": "ok", "active_session": True},
            "runtime_service": {"configured": True, "state": "ready", "reason": {"code": "service_ready"}}}

    def test_only_uptime_is_excluded_from_stable_fingerprint(self):
        value = self.fixture()
        digest = scratch.validate_export(value, "session-probe")
        value["status"]["metrics"]["uptime_seconds"] += 10
        self.assertEqual(scratch.validate_export(value, "session-probe"), digest)
        value["scene"]["editor"] = {"object_view_mode": "context"}
        self.assertNotEqual(scratch.validate_export(value, "session-probe"), digest)

    def test_refuses_changed_model_session_or_accepted_work(self):
        for path, replacement in ((('scene', 'revision'), 1), (('scene', 'objects'), [{"id": "object"}]),
                (('session', 'session_id'), 'session-other'), (('session', 'script'), 'print(1)'),
                (('status', 'run'), {"run_id": "accepted"}), (('commands', 'accepted_count'), 1),
                (('compute_queue', 'items'), [{"task_id": "task"}])):
            with self.subTest(path=path):
                value = self.fixture()
                value[path[0]][path[1]] = replacement
                with self.assertRaises(RuntimeError):
                    scratch.validate_export(value, "session-probe")

    def test_probe_checks_store_ledger_and_rechecks_api(self):
        paths = dict(zip(("/v2/sessions/current", "/v2/sessions/current/status", "/v2/sessions/current/model/scene",
            "/v2/sessions/current/simulation/commands", "/v2/platform/compute/queue", "/v2/platform/runtime-service",
            "/v2/platform/health"), ("session", "status", "scene", "commands", "compute_queue", "runtime_service", "health")))
        for obstacle in (None, "run", "journal", "fence", "reservation", "changed"):
            with self.subTest(obstacle=obstacle), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                store, ledger = root / "store", root / "ledger"
                store.mkdir(); ledger.mkdir()
                (store / "WRITER.lock").touch(); (ledger / "WRITER.lock").touch()
                (ledger / "HOST_RESOURCE_LEDGER.json").write_text(json.dumps({"reservations":
                    [{"state": "held"}] if obstacle == "reservation" else []}))
                if obstacle in ("run", "journal", "fence"):
                    target = store / {"run": "runs", "journal": "live_command_journals", "fence": "development"}[obstacle]
                    target.mkdir(); (target / "record.json").write_text("{}")
                value = self.fixture()
                calls = []
                class Response:
                    status = 200
                    headers = {"x-fullmag-api-instance": value["api_instance"]}
                    def __init__(self, payload): self.payload = payload
                    def __enter__(self): return self
                    def __exit__(self, *args): pass
                    def read(self, maximum): return json.dumps(self.payload).encode()
                def get(url, **kwargs):
                    key = paths[url.removeprefix("http://127.0.0.1:8081")]
                    calls.append(key)
                    item = copy.deepcopy(value[key])
                    if obstacle == "changed" and len(calls) > 7 and key == "scene":
                        item["editor"] = {"changed": True}
                    return Response(item)
                with patch("urllib.request.urlopen", side_effect=get):
                    if obstacle is None:
                        proof = scratch.probe("session-probe", str(store), str(ledger))
                        self.assertEqual(proof["export"], value)
                        self.assertEqual(len(calls), 14)
                    else:
                        with self.assertRaises(RuntimeError):
                            scratch.probe("session-probe", str(store), str(ledger))


if __name__ == "__main__":
    unittest.main()
