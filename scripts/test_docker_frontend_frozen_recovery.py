"""Focused failure-only resume and explicit frontend-generation regressions."""
import copy
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import docker_volume_frontend_frozen_recovery as frozen
import docker_volume_reconcile as reconcile
from docker_build_control import BuildControlError, canonical


def request():
    return {"schema": frozen.SCHEMA, "attempt": "a" * 32, "compose_project": "group",
            "source_root": "/selected", "port": 3203, "config_sha256": "b" * 64,
            "unknown_receipt_sha256": "c" * 64, "controller_sha256": "d" * 64,
            "frontend_helper_sha256": "e" * 64,
            "source_transition": {"path": "verification/frontend-frozen-recovery-20261027/transition.json", "sha256": "2" * 64},
            "package_documents": {"receipt": "f" * 64, "provenance": "1" * 64},
            "containers": {name: {"id": digit * 64, "image": "sha256:" + "4" * 64,
                "started_at": "2026-10-27T21:32:20Z", "fingerprint": "5" * 64}
                for name, digit in (("lease", "6"), ("backend", "7"), ("frontend", "8"))},
            "failure": {**{k: "9" * 64 for k in (
                "frontend_state_sha256", "log_sha256", "freeze_sha256", "inputs_sha256",
                "previous_receipt_sha256")}, "backend_observation": {"active_session": True}}}


class RequestContract(unittest.TestCase):
    def test_explicit_schema_and_all_three_distinct_pins(self):
        reconcile.validate_request(request())
        bad = request()
        bad["containers"]["frontend"] = dict(bad["containers"]["backend"])
        with self.assertRaises(BuildControlError):
            reconcile.validate_request(bad)

    def test_missing_extra_or_malformed_fields_are_rejected(self):
        for key in ("failure", "frontend_helper_sha256", "package_documents"):
            bad = request()
            del bad[key]
            with self.subTest(key=key), self.assertRaises(BuildControlError):
                reconcile.validate_request(bad)
        for change in ({"unexpected": True}, {"frontend_helper_sha256": "bad"},
                       {"failure": {"backend_observation": {}}}):
            with self.subTest(change=change), self.assertRaises(BuildControlError):
                reconcile.validate_request({**request(), **change})

    def test_resume_commit_is_failure_only_and_reuses_atomic_targets(self):
        control = SimpleNamespace(path=lambda value: "/control/" + value)
        args = (control, "resume/attempts/" + "a" * 32, request(),
                "resume/attempts/" + "a" * 32 + "/reconciliation/" + "b" * 64,
                "b" * 64, "c" * 64)
        script = reconcile.commit_script(*args, phase="resume", publish_verified=False)
        self.assertIn("/control/resume/current.json", script)
        self.assertNotIn("/control/resume/verified.json", script)
        self.assertIn("mv -T", script)
        with self.assertRaises(BuildControlError):
            reconcile.commit_script(*args, phase="resume", publish_verified=True)
        bad = request()
        bad["schema"] = reconcile.SCHEMA
        with self.assertRaises(BuildControlError):
            reconcile.commit_script(control, *args[1:2], bad, *args[3:],
                                    phase="resume", publish_verified=False)

    def test_existing_iteration_commit_contract_remains_closed(self):
        control = SimpleNamespace(path=lambda value: "/control/" + value)
        bad = request()
        bad["schema"] = reconcile.SCHEMA
        with self.assertRaises(BuildControlError):
            reconcile.commit_script(control, "iteration/attempts/" + "a" * 32, bad,
                                    "journal", "b" * 64, "c" * 64,
                                    phase="iteration", publish_verified=False)


class FrozenFailureContract(unittest.TestCase):
    def setUp(self):
        self.actual = {"Id": "8" * 64, "State": {
            "Status": "exited", "Running": False, "ExitCode": 1, "Pid": 0,
            "OOMKilled": False, "Dead": False, "Restarting": False, "Paused": False,
            "Error": "", "StartedAt": "2026-10-27T21:32:25Z",
            "FinishedAt": "2026-10-27T21:32:26Z"}}
        self.inputs = {"source_commit": "c" * 40}
        self.freeze = {"schema": "fullmag.docker-development-inputs-freeze.v1",
                       "manifest": {"source_commit": "d" * 40}}
        self.log = ("frontend_dev.FrontendDevError: " + frozen.ERROR + "\n").encode()

    def observe(self, *, actual=None, freeze=None, log=None):
        with patch.object(frozen, "container_file", return_value=canonical(
                self.freeze if freeze is None else freeze)), \
             patch.object(frozen, "read_raw", return_value=canonical(self.inputs)), \
             patch.object(frozen, "docker_capture", return_value=SimpleNamespace(
                 stdout=self.log if log is None else log, stderr=b"")):
            return frozen.frozen_failure(object(), self.actual if actual is None else actual)

    def test_exact_non_oom_frozen_failure_is_observed_without_writes(self):
        value = self.observe()
        self.assertEqual(value["frontend_state_sha256"],
                         frozen.digest(canonical(self.actual["State"])))
        self.assertEqual(set(value), {"frontend_state_sha256", "log_sha256",
                                     "freeze_sha256", "inputs_sha256"})

    def test_foreign_running_oom_error_or_exit_state_is_rejected(self):
        for change in ({"Running": True}, {"ExitCode": 0}, {"OOMKilled": True},
                       {"Pid": 123}, {"Error": "foreign"}, {"Restarting": True}):
            actual = copy.deepcopy(self.actual)
            actual["State"].update(change)
            with self.subTest(change=change), self.assertRaises(BuildControlError):
                self.observe(actual=actual)

    def test_unrelated_log_or_no_manifest_difference_is_rejected(self):
        with self.assertRaises(BuildControlError):
            self.observe(log=b"out of memory\n")
        with self.assertRaises(BuildControlError):
            self.observe(freeze={**self.freeze, "manifest": self.inputs})

    def test_stopped_container_reader_rejects_non_regular_archive(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w") as archive:
            entry = tarfile.TarInfo("inputs-freeze.json")
            entry.type = tarfile.SYMTYPE
            entry.linkname = "/foreign"
            archive.addfile(entry)
        with patch.object(frozen, "docker_capture", return_value=SimpleNamespace(stdout=data.getvalue())):
            with self.assertRaises(BuildControlError):
                frozen.container_file("8" * 64, "/state/development/inputs-freeze.json")


class SessionFenceContract(unittest.TestCase):
    def test_empty_session_uses_opt_in_observation_without_terminal_probe(self):
        import docker_volume_dev as dev
        observation = {"active_session": False, "run_id": None}
        with patch.object(dev, "_frontend_recovery_backend_observation", return_value=observation) as read, \
             patch.object(dev, "_terminal_session_restart_probe") as terminal:
            self.assertEqual(frozen.backend_observation("backend"), observation)
            read.assert_called_once_with("backend", allow_empty=True)
            terminal.assert_not_called()

    def test_active_session_requires_same_terminal_run(self):
        import docker_volume_dev as dev
        observation = {"active_session": True, "run_id": "run"}
        with patch.object(dev, "_frontend_recovery_backend_observation", return_value=observation), \
             patch.object(dev, "_terminal_session_restart_probe", return_value={"run": {"run_id": "run", "status": "failed"}}) as terminal:
            self.assertEqual(frozen.backend_observation("backend"), observation)
            terminal.assert_called_once_with("backend", allow_prepared=True)
        for terminal in (None, {"run": {"run_id": "foreign", "status": "failed"}},
                         {"run": {"run_id": "run", "status": "waiting_for_solve"}},
                         {"run": {"run_id": "run", "status": "running"}},
                         {"run": {"run_id": "run"}}):
            with patch.object(dev, "_frontend_recovery_backend_observation", return_value=observation), \
                 patch.object(dev, "_terminal_session_restart_probe", return_value=terminal):
                with self.assertRaises(BuildControlError):
                    frozen.backend_observation("backend")

    def test_refresh_without_explicit_pins_preserves_old_dispatch(self):
        self.assertIsNone(frozen.refresh_context(object(), SimpleNamespace(), {}, {}, {}))
        with self.assertRaises(BuildControlError):
            frozen.refresh_context(object(), SimpleNamespace(frontend_frozen_resume="a" * 32),
                                   {}, {}, {})



class CompletionFenceContract(unittest.TestCase):
    def test_failure_requires_native_completion_and_stable_observation(self):
        import docker_volume_terminal_prestart_recovery as terminal
        wanted = request()
        wanted["frontend_helper_sha256"] = frozen.digest(Path(frozen.__file__).read_bytes())
        backend = {"Id": "7" * 64, "State": {
            "StartedAt": "2026-10-27T21:32:20Z", "Health": {"Status": "healthy"}}}
        original = {"inputs": {"attempt": "a" * 32},
                    "backend_started_at": backend["State"]["StartedAt"]}
        failure = {k: v for k, v in wanted["failure"].items()
                   if k not in {"previous_receipt_sha256", "backend_observation"}}
        control = SimpleNamespace(read=lambda path: {"services": {}})
        qualified = {"qualified": True}
        with patch.object(frozen, "terminal_context", return_value={"kind": "terminal_history"}), \
             patch.object(frozen, "frozen_failure", return_value=failure), \
             patch.object(frozen, "backend_observation",
                          return_value=wanted["failure"]["backend_observation"]), \
             patch.object(frozen, "qualified_backend", return_value=(qualified, {
                 "app_source": {"commit": "c" * 40}, "helper_source": {"commit": "d" * 40},
                 "transition_manifest_sha256": "2" * 64})), \
             patch.object(terminal, "complete") as complete:
            actual = {"backend": backend, "frontend": {}}
            self.assertEqual(frozen.validate_failure(control, "root", wanted, original, actual, Path("/state"))["failure"],
                             wanted["failure"])
            self.assertEqual(complete.call_count, 1)
            self.assertEqual(complete.call_args.args[-1], qualified)
            complete.side_effect = BuildControlError("native terminal evidence differs")
            with self.assertRaisesRegex(BuildControlError, "native terminal evidence"):
                frozen.validate_failure(control, "root", wanted, original, actual, Path("/state"))

    def test_unqualified_transition_is_rejected_before_history_completion(self):
        import docker_dev_codegen as codegen
        with patch.object(codegen, "_backend_documents", return_value=({"source": {}}, {}, "f" * 64, {})), \
             patch.object(codegen, "_validate_backend", return_value=({}, None, None)), \
             patch.object(codegen, "_probe_source", return_value=({}, None)), \
             patch.object(frozen, "source_qualification", side_effect=BuildControlError("source transition differs")):
            with self.assertRaisesRegex(BuildControlError, "source transition"):
                frozen.qualified_backend(object(), "root", request(), {
                    "Id": "7" * 64, "State": {"StartedAt": "now"}, "Image": "sha256:" + "4" * 64})


if __name__ == "__main__":
    unittest.main()
