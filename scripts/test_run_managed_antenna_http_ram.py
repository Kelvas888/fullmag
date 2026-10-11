"""Interpreted lifecycle/isolation regressions; never compile native tests."""
import copy
import json
from pathlib import Path
import subprocess

import pytest
from scripts import run_managed_antenna_http_ram as gate
from scripts import run_managed_antenna_ram as ram


def document(tmp_path):
    return gate.http_spec("sha256:" + "a" * 64, tmp_path / "source",
        tmp_path / "package", tmp_path / "input", tmp_path / "export", tmp_path / "tools")


def inspection(spec):
    service = spec["services"]["antenna"]
    return [{"Image": service["image"], "Config": {"User": "65532:65532",
        "Cmd": service["command"], "Entrypoint": [], "WorkingDir": service["working_dir"],
        "Env": [f"{key}={value}" for key, value in service["environment"].items()],
        "Labels": {"com.docker.compose.project": "project", "com.docker.compose.service": "antenna"}},
        "HostConfig": {"NetworkMode": "none", "PortBindings": {}, "ReadonlyRootfs": True,
            "Privileged": False, "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
            "Memory": 2 * 1024**3, "NanoCpus": 2 * 10**9, "PidsLimit": 128,
            "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=64m", "/ram": "rw,nosuid,nodev,size=768m,mode=1777"}},
        "Mounts": [{"Type": "bind", "Source": m["source"], "Destination": m["target"],
                    "RW": not m["read_only"]} for m in service["volumes"]]}]


def test_readonly_tools_are_distinct_from_capsule_and_state_is_ram(tmp_path):
    spec = document(tmp_path)
    service = spec["services"]["antenna"]
    assert "ports" not in service and service["network_mode"] == "none"
    assert [(m["target"], m["read_only"]) for m in service["volumes"]] == [
        ("/source", True), ("/package", True), ("/input", True),
        ("/export", False), ("/tools", True)]
    assert service["environment"]["FULLMAG_API_PORT"] == "8081"
    assert service["environment"]["FULLMAG_STATE_ROOT"] == "/ram/workspace/.fullmag"
    assert service["environment"]["FULLMAG_STATE_DIR"] == "/ram/user-state"
    assert service["command"] == ["python3", "-I", "-B", "/tools/run_managed_antenna_http_ram.py", "execute"]


@pytest.mark.parametrize("mutation", ["tools_rw", "ports", "network", "state", "image", "command", "tmpfs"])
def test_changed_runtime_is_rejected(tmp_path, monkeypatch, mutation):
    spec = document(tmp_path)
    observed = inspection(spec)
    item = observed[0]
    if mutation == "tools_rw": item["Mounts"][-1]["RW"] = True
    elif mutation == "ports": item["HostConfig"]["PortBindings"] = {"8081/tcp": [{}]}
    elif mutation == "network": item["HostConfig"]["NetworkMode"] = "bridge"
    elif mutation == "state": item["Config"]["Env"].append("FULLMAG_STATE_ROOT=/export")
    elif mutation == "image": item["Image"] = "sha256:" + "b" * 64
    elif mutation == "command": item["Config"]["Cmd"] = ["true"]
    elif mutation == "tmpfs": item["HostConfig"]["Tmpfs"]["/ram"] = "rw,size=2g"
    monkeypatch.setattr(ram, "docker", lambda *args: json.dumps(observed))
    with pytest.raises(ValueError):
        ram.attest("container", spec, "project")


def test_exact_runtime_is_attested(tmp_path, monkeypatch):
    spec = document(tmp_path)
    observed = inspection(spec)
    monkeypatch.setattr(ram, "docker", lambda *args: json.dumps(observed))
    assert ram.attest("container", spec, "project") == observed[0]


def test_pin_host_tools_and_reject_tampering(tmp_path):
    for name in gate.TOOLS:
        (tmp_path / name).write_bytes(name.encode())
    manifest = gate.tool_manifest(tmp_path)
    gate.check_tools(tmp_path, manifest)
    (tmp_path / gate.TOOLS[1]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="identity changed"):
        gate.check_tools(tmp_path, manifest)
    with pytest.raises(ValueError, match="identity changed"):
        gate.check_tools(tmp_path, {**manifest, "unowned.py": "a" * 64})


def test_tool_manifest_matches_actual_import_dependencies():
    repo = Path(__file__).resolve().parents[1]
    manifest = gate.tool_manifest(repo / "scripts")
    assert set(manifest) == set(gate.TOOLS)
    assert "antenna_current_source_oracle.py" in manifest
    assert "run_managed_antenna_ram.py" not in manifest


@pytest.mark.parametrize("script,status", [
    ("smoke_antenna_external_lead_inspection.py", "pass"),
    ("smoke_antenna_inspection_display.py", "passed"),
])
def test_smoke_runs_pinned_tools_with_bounded_timeout(tmp_path, monkeypatch, script, status):
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        kwargs["stdout"].write(json.dumps({"status": status, "physics_qualified": False}).encode())
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(gate.subprocess, "run", run)
    result = gate.smoke(script, "stage-000", tmp_path)
    assert result["status"] == status
    command, options = calls[0]
    assert command[-5:] == ["/tools/" + script, "--origin", gate.ORIGIN,
                           "--stage-id", "stage-000"]
    assert command[1:4] == ["-I", "-B", "-c"]
    assert options["timeout"] == 120


@pytest.mark.parametrize("script,module_name", [
    ("smoke_antenna_external_lead_inspection.py", "metadata_smoke"),
    ("smoke_antenna_inspection_display.py", "display_smoke"),
])
def test_gate_consumes_real_frozen_smoke_contract(tmp_path, monkeypatch, script, module_name):
    import test_smoke_antenna_inspection_display as frozen
    result = frozen.FrozenInspection(2).run(getattr(frozen, module_name))
    def run(command, **kwargs):
        kwargs["stdout"].write(json.dumps(result).encode())
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(gate.subprocess, "run", run)
    assert gate.smoke(script, "stage-000", tmp_path) == result


@pytest.mark.parametrize("result,code", [({"status": "fail", "physics_qualified": False}, 0),
    ({"status": "passed", "physics_qualified": True}, 0),
    ({"status": "passed", "physics_qualified": False}, 1),
    ({"status": "pass", "physics_qualified": False}, 0)])
def test_smoke_failure_and_scope_promotion_rejected(tmp_path, monkeypatch, result, code):
    def run(command, **kwargs):
        kwargs["stdout"].write(json.dumps(result).encode())
        return subprocess.CompletedProcess(command, code)
    monkeypatch.setattr(gate.subprocess, "run", run)
    with pytest.raises(ValueError):
        gate.smoke("smoke_antenna_inspection_display.py", "stage-000", tmp_path)


def test_api_readiness_requires_real_inspection_contract(monkeypatch):
    class Api:
        def poll(self): return None
    calls = []
    def fetch(path):
        calls.append(path)
        route = "/v2/sessions/current/data/antenna/stages/{stage_id}/external-lead-inspection"
        return {"paths": {route + suffix: {} for suffix in ("", "/display", "/payloads/{payload_kind}")}}
    monkeypatch.setattr(gate, "get_json", fetch)
    gate.wait_api(Api())
    assert calls == ["/v2/platform/openapi.json"]


def test_api_exit_fails_before_solver(monkeypatch):
    class Api:
        def poll(self): return 1
    monkeypatch.setattr(gate, "get_json", lambda *args: pytest.fail("dead API must not be read"))
    with pytest.raises(ValueError, match="exited"):
        gate.wait_api(Api())


def test_timeout_stops_only_owned_api():
    class Api:
        def __init__(self): self.calls = []
        def poll(self): return None
        def terminate(self): self.calls.append("terminate")
        def kill(self): self.calls.append("kill")
        def wait(self, timeout):
            self.calls.append(("wait", timeout))
            if "kill" not in self.calls: raise subprocess.TimeoutExpired("owned-api", timeout)
    api = Api()
    gate.stop_owned(api)
    assert api.calls == ["terminate", ("wait", 10), "kill", ("wait", 10)]


def test_nonterminal_build_prevents_storage_and_docker(tmp_path, monkeypatch):
    import fullmag_storage as storage
    import run_managed_browser as browser
    def reject(*args): raise ValueError("Managed CPU release must be terminal and successful")
    monkeypatch.setattr(gate, "resolved", reject)
    monkeypatch.setattr(storage, "initialize", lambda *args: pytest.fail("no writes"))
    monkeypatch.setattr(browser, "docker", lambda *args: pytest.fail("no Docker"))
    with pytest.raises(ValueError, match="terminal"):
        gate.start(tmp_path, "a" * 32, "b" * 40, "c" * 64, "d" * 64)



def test_nonmagnetic_fixture_is_explicit_and_shares_only_source_assets():
    magnetic = gate.fixture_contract()
    nonmagnetic = gate.fixture_contract("nonmagnetic")
    assert "fem_antenna_current_source_inspection.py" in magnetic
    assert "fem_antenna_current_source_inspection.py" not in nonmagnetic
    assert nonmagnetic["fem_antenna_field_only_nonmagnetic.py"] == gate.NONMAGNETIC_SHA
    assert {k: v for k, v in magnetic.items() if k.startswith("assets/")} == {
        k: v for k, v in nonmagnetic.items() if k.startswith("assets/")}
    with pytest.raises(ValueError):
        gate.fixture_contract("unknown")


def test_native_archive_bytes_are_retained_without_reencoding(tmp_path, monkeypatch):
    import base64
    raw = b"native archive bytes"
    encoded = base64.b64encode(raw).decode()
    calls = []
    def post(path, payload, limit):
        calls.append((path, payload, limit))
        return {"profile": "archive", "session_id": "native-session",
                "fms_base64": encoded, "size_bytes": len(raw)}
    monkeypatch.setattr(gate, "post_json", post)
    assert gate.export_archive(tmp_path) == (encoded, "native-session")
    assert (tmp_path / "snapshot.fms").read_bytes() == raw
    assert calls == [("/v2/sessions/current/persistence/exports",
                      {"profile": "archive"}, 2 * gate.MAX_ARCHIVE)]


@pytest.mark.parametrize("mutation", ["invalid_base64", "size", "profile", "empty", "large"])
def test_corrupt_or_oversized_archive_is_not_retained(tmp_path, monkeypatch, mutation):
    import base64
    result = {"profile": "archive", "session_id": "s",
              "fms_base64": base64.b64encode(b"bytes").decode(), "size_bytes": 5}
    if mutation == "invalid_base64": result["fms_base64"] = "!!!"
    elif mutation == "size": result["size_bytes"] = 6
    elif mutation == "profile": result["profile"] = "compact"
    elif mutation == "empty": result.update(fms_base64="", size_bytes=0)
    elif mutation == "large": monkeypatch.setattr(gate, "MAX_ARCHIVE", 3)
    monkeypatch.setattr(gate, "post_json", lambda *args: result)
    with pytest.raises(ValueError):
        gate.export_archive(tmp_path)
    assert not (tmp_path / "snapshot.fms").exists()


def test_cold_incarnation_changes_but_scientific_content_must_not():
    warm = {"runtime_stage_id": "stage-000", "request_scope_epoch": "old",
            "outputs": [{"inspection_ref": {"content_digest": "sha256:pinned"},
                         "payload_units": {"current": "A/m^2"}}]}
    cold = {**warm, "request_scope_epoch": "fresh"}
    gate.compare_cold_metadata(warm, cold)
    altered = copy.deepcopy(cold)
    altered["outputs"][0]["inspection_ref"]["content_digest"] = "sha256:other"
    with pytest.raises(ValueError, match="identity"):
        gate.compare_cold_metadata(warm, altered)
    with pytest.raises(ValueError):
        gate.compare_cold_metadata(warm, {**cold, "runtime_stage_id": "stage-001"})
    with pytest.raises(ValueError):
        gate.compare_cold_metadata({}, {})


def test_http_error_retains_exact_bounded_non_json_bytes(monkeypatch):
    import io
    from urllib.error import HTTPError
    raw = b"inspection unavailable \xff"
    class Opener:
        def open(self, url, timeout):
            assert timeout == 3
            raise HTTPError(url, 404, "Not Found", {}, io.BytesIO(raw))
    monkeypatch.setattr(gate, "build_opener", lambda *args: Opener())
    with pytest.raises(gate.HttpDiagnosticError) as captured:
        gate.get_json("/inspection")
    diagnostic = captured.value.diagnostic
    assert diagnostic["status"] == 404
    assert gate.base64.b64decode(diagnostic["body_base64"]) == raw
    assert diagnostic["body_truncated"] is False


def test_204_stage_resource_is_retained_as_absent_not_invalid_json(monkeypatch):
    import io
    class Response(io.BytesIO):
        code = 204
    class Opener:
        def open(self, *args, **kwargs): return Response(b"")
    monkeypatch.setattr(gate, "build_opener", lambda *args: Opener())
    with pytest.raises(gate.HttpDiagnosticError) as captured:
        gate.get_json("/stages")
    assert captured.value.diagnostic == {"path": "/stages", "status": 204,
        "body": "", "body_base64": "", "body_truncated": False}


def test_oversized_error_body_is_truncated_and_never_marked_pass(monkeypatch):
    import io
    from urllib.error import HTTPError
    class Opener:
        def open(self, url, **kwargs):
            raise HTTPError(url, 500, "Failed", {}, io.BytesIO(b"x" * (gate.MAX_JSON + 2)))
    monkeypatch.setattr(gate, "build_opener", lambda *args: Opener())
    with pytest.raises(gate.HttpDiagnosticError) as captured:
        gate.get_json("/inspection")
    diagnostic = captured.value.diagnostic
    assert len(gate.base64.b64decode(diagnostic["body_base64"])) == 65536
    assert diagnostic["body_truncated"] is True
    assert diagnostic["error"] == "metadata response exceeds contract"


def test_poll_failure_retains_last_http_error_and_real_resource_ownership(tmp_path, monkeypatch):
    ticks = iter([0, 0, 16])
    monkeypatch.setattr(gate.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(gate.time, "sleep", lambda *args: None)
    calls = []
    def get(path):
        calls.append(path)
        if path.endswith("external-lead-inspection"):
            raise gate.HttpDiagnosticError({"path": path, "status": 404,
                "body": '{"message":"no stage execution state"}'})
        if path.endswith("stages/execution"):
            raise gate.HttpDiagnosticError({"path": path, "status": 204, "body": ""})
        if path.endswith("runs/current"):
            return {"run_id": "actual-run", "revision": 11,
                    "artifact_dir": "/ram/result.zarr", "final_total_energy": 42}
        if path.endswith("data/artifacts"):
            return [{"path": "stage-000/actual-record.json"}]
        return {"session_id": "actual-session", "unrelated_secret": "excluded"}
    monkeypatch.setattr(gate, "get_json", get)
    with pytest.raises(ValueError, match="did not register"):
        gate.wait_inspection(tmp_path)
    diagnostic = json.loads((tmp_path / "inspection-failure-diagnostic.json").read_text())
    assert diagnostic["last_poll_error"]["status"] == 404
    assert "no stage execution state" in diagnostic["last_poll_error"]["body"]
    resources = diagnostic["resources"]
    assert resources["/v2/sessions/current/simulation/stages/execution"]["status"] == 204
    assert resources["/v2/sessions/current/simulation/runs/current"]["resource"] == {
        "run_id": "actual-run", "revision": 11, "artifact_dir": "/ram/result.zarr"}
    assert "unrelated_secret" not in json.dumps(diagnostic)
    assert len(calls) == 6


def test_wrong_200_stage_is_retained_but_correct_stage_writes_no_failure(tmp_path, monkeypatch):
    ticks = iter([0, 0, 16])
    monkeypatch.setattr(gate.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(gate.time, "sleep", lambda *args: None)
    wrong = {"runtime_stage_id": "authored-antenna", "outputs": []}
    monkeypatch.setattr(gate, "get_json", lambda path: wrong)
    with pytest.raises(ValueError, match="did not register"):
        gate.wait_inspection(tmp_path)
    diagnostic = json.loads((tmp_path / "inspection-failure-diagnostic.json").read_text())
    assert diagnostic["last_200_inspection_metadata"] == wrong
    assert diagnostic["last_poll_error"]["status"] == 200
    (tmp_path / "inspection-failure-diagnostic.json").unlink()
    ticks = iter([0, 0])
    monkeypatch.setattr(gate.time, "monotonic", lambda: next(ticks))
    correct = {"runtime_stage_id": "stage-000"}
    monkeypatch.setattr(gate, "get_json", lambda path: correct)
    assert gate.wait_inspection(tmp_path) == correct
    assert not (tmp_path / "inspection-failure-diagnostic.json").exists()
