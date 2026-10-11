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
