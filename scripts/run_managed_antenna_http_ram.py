"""Bounded real antenna HTTP gate using an existing managed CPU package.

All application state remains in tmpfs. Host tools have their own immutable
manifest; they are not attributed to the solver source capsule. No build or
durable SessionStore qualification is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from urllib.request import ProxyHandler, build_opener

PROFILE = "managed-antenna-http-ram-cpu"
SCHEMA = "fullmag.managed-antenna-http-ram.v1"
TOOLS = (
    "run_managed_antenna_http_ram.py", "smoke_antenna_external_lead_inspection.py",
    "smoke_antenna_inspection_display.py", "antenna_rt0_fixture_check.py",
    "antenna_current_display_fixture_check.py", "antenna_current_source_oracle.py",
)
ORIGIN = "http://127.0.0.1:8081"
MAX_JSON = 4 << 20


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tool_manifest(root):
    paths = [root / name for name in TOOLS]
    if any(path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON
           for path in paths):
        raise ValueError("HTTP gate requires bounded regular host tool files")
    return {name: sha(root / name) for name in TOOLS}


def check_tools(root, expected):
    if set(expected) != set(TOOLS) or tool_manifest(root) != expected:
        raise ValueError("HTTP gate host tool identity changed")


def get_json(path):
    opener = build_opener(ProxyHandler({}))
    with opener.open(ORIGIN + path, timeout=3) as response:
        data = response.read(MAX_JSON + 1)
        if response.status != 200 or len(data) > MAX_JSON:
            raise ValueError("HTTP gate metadata response exceeds contract")
        return json.loads(data)


def wait_api(api, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if api.poll() is not None:
            raise ValueError("Owned RAM API exited before readiness")
        try:
            spec = get_json("/v2/platform/openapi.json")
            route = "/v2/sessions/current/data/antenna/stages/{stage_id}/external-lead-inspection"
            if all(route + suffix in spec["paths"] for suffix in
                   ("", "/display", "/payloads/{payload_kind}")):
                return
        except (OSError, ValueError, KeyError):
            pass
        time.sleep(0.25)
    raise ValueError("Owned RAM API did not expose inspection OpenAPI in time")


def stop_owned(api):
    if api is None or api.poll() is not None:
        return
    api.terminate()
    try:
        api.wait(timeout=10)
    except subprocess.TimeoutExpired:
        api.kill()
        api.wait(timeout=10)


def smoke(script, stage, export):
    # -I excludes ambient Python imports; only the pinned tools directory is
    # explicitly introduced. The numerical publisher remains the package.
    code = "import runpy,sys; sys.path.insert(0,'/tools'); runpy.run_path(sys.argv.pop(1),run_name='__main__')"
    with (export / (script + ".log")).open("wb") as log:
        completed = subprocess.run([sys.executable, "-I", "-B", "-c", code,
            "/tools/" + script, "--origin", ORIGIN, "--stage-id", stage],
            stdout=log, stderr=subprocess.STDOUT, timeout=120)
    if completed.returncode:
        raise ValueError(f"Real HTTP smoke failed: {script}; read retained log")
    raw = (export / (script + ".log")).read_bytes()
    if len(raw) > MAX_JSON:
        raise ValueError("HTTP smoke result exceeds JSON bound")
    result = json.loads(raw)
    expected_status = {
        "smoke_antenna_external_lead_inspection.py": "pass",
        "smoke_antenna_inspection_display.py": "passed",
    }.get(script)
    if expected_status is None or result.get("status") != expected_status \
            or result.get("physics_qualified") is not False:
        raise ValueError("HTTP smoke failed or promoted inspection scope")
    return result


def execute_in_container():
    export, tools = Path("/export"), Path("/tools")
    expected = json.loads((tools / "manifest.json").read_text())
    check_tools(tools, expected["tools_sha256"])
    fixture_sha = expected["fixture_sha256"]
    for name, digest in fixture_sha.items():
        path = Path("/input") / name
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError("Staged fixed scientific input changed")
    if any(os.environ.get(key) != value for key, value in {
        "FULLMAG_REPO_ROOT": "/ram/workspace",
        "FULLMAG_STATE_ROOT": "/ram/workspace/.fullmag",
        "FULLMAG_STATE_DIR": "/ram/user-state", "FULLMAG_API_PORT": "8081",
    }.items()):
        raise ValueError("HTTP gate process environment leaves RAM ownership")
    workspace = Path("/ram/workspace")
    workspace.mkdir()
    (workspace / ".fullmag").mkdir()
    for source in Path("/source").iterdir():
        if source.name == ".fullmag":
            raise ValueError("Solver capsule contains mutable state root")
        (workspace / source.name).symlink_to(source, target_is_directory=source.is_dir())
    os.chdir(workspace)
    api = None
    result = {"schema": SCHEMA, "state": "failed", "physics_qualified": False,
        "durable_session_storage_qualified": False, "reuse_LLG_FFT_qualified": False,
        "qualification": "NOT VERIFIED", "session_storage": "disposable_tmpfs",
        "tool_manifest_sha256": sha(tools / "manifest.json"),
        "native_canonical_bundle_redecoded": False, "cold_archive_import": "NOT VERIFIED"}
    try:
        with (export / "api.log").open("wb") as api_log:
            api = subprocess.Popen(["/package/bin/fullmag-api"], stdout=api_log,
                stderr=subprocess.STDOUT)
            wait_api(api)
            with (export / "solver.log").open("wb") as log:
                solve = subprocess.run(["/package/bin/fullmag-bin",
                    "/input/fem_antenna_current_source_inspection.py", "--headless",
                    "--api-port", "8081", "--expect-script-sha256",
                    fixture_sha["fem_antenna_current_source_inspection.py"],
                    "--output-dir", "/ram/result.zarr"], stdout=log,
                    stderr=subprocess.STDOUT, timeout=300)
            result["solver_exit_code"] = solve.returncode
            if solve.returncode:
                raise ValueError("Native solve failed; read retained solver.log")
            # Snapshot ownership must be produced by the real run. Do not
            # construct, inject or modify stage_execution/artifact_refs.
            deadline = time.monotonic() + 15
            metadata = None
            while time.monotonic() < deadline:
                try:
                    metadata = get_json("/v2/sessions/current/data/antenna/stages/stage-000/external-lead-inspection")
                    if metadata.get("runtime_stage_id") == "stage-000":
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.25)
            else:
                raise ValueError("Real solve did not register its inspection stage")
            (export / "inspection-metadata.json").write_text(json.dumps(metadata, sort_keys=True))
            result["http_smokes"] = {
                name: smoke(name, "stage-000", export) for name in
                ("smoke_antenna_external_lead_inspection.py", "smoke_antenna_inspection_display.py")}
            # Both API handlers invoke the full canonical disk loader. The
            # Python smoke itself correctly does not claim native decoding.
            result.update(state="warm_http_pass", runtime_stage_id="stage-000",
                native_canonical_bundle_redecoded=True,
                canonical_decoder_owner="API load_published_antenna_external_lead_solution",
                inspection_ref=metadata["outputs"][0]["inspection_ref"])
    except Exception as error:
        result["error"] = str(error)
    finally:
        try:
            stop_owned(api)
        except Exception as error:
            result.update(state="failed", shutdown_error=str(error))
        output = Path("/ram/result.zarr")
        if output.is_dir():
            shutil.copytree(output, export / "result.zarr")
        (export / "gate-result.json").write_text(json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "warm_http_pass" else 1


def http_spec(image, source, package, inputs, export, tools):
    import run_managed_antenna_ram as ram
    spec = ram.scientific_spec(image, source, package, inputs, export)
    service = spec["services"]["antenna"]
    service["volumes"].append({"type": "bind", "source": str(tools.resolve()),
                               "target": "/tools", "read_only": True})
    service["environment"]["FULLMAG_API_PORT"] = "8081"
    service["command"] = ["python3", "-I", "-B", "/tools/run_managed_antenna_http_ram.py", "execute"]
    return spec


def resolved(repo, job, commit, source, native):
    import fullmag_storage as storage
    import run_managed_antenna_ram as ram
    _, build, context, built, capsule, package = ram.resolved_build(repo, job, commit, source, native)
    return storage.resolve_layout(repo, PROFILE), build, context, built, capsule, package


def start(repo, job, commit, source_digest, native_digest):
    import fullmag_storage as storage
    import run_managed_antenna_ram as ram
    from run_managed_browser import docker
    layout, build, context, built, capsule, package = resolved(
        repo, job, commit, source_digest, native_digest)
    fixtures = ram.fixture_paths(repo)
    host_tools = repo / "scripts"
    tools_sha = tool_manifest(host_tools)
    image = json.loads(docker("image", "inspect", context["image_digest"]))[0]
    if image.get("Id") != context["image_digest"] or image.get("Config", {}).get("Volumes"):
        raise ValueError("Build image has different identity or anonymous volumes")
    storage.initialize(layout)
    root = storage.validate_path(Path(layout["build_root"]) / "runs" / uuid.uuid4().hex,
                                 Path(layout["build_storage_root"]))
    root.mkdir(parents=True, exist_ok=False)
    inputs, export, tools = root / "input", root / "export", root / "tools"
    for folder in (inputs, export, tools):
        folder.mkdir()
    for name, path in fixtures.items():
        target = inputs / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if sha(target) != ram.FIXTURE_FILES[name]:
            raise ValueError("Fixture changed during staging")
    for name in TOOLS:
        shutil.copyfile(host_tools / name, tools / name)
    check_tools(tools, tools_sha)
    storage.atomic_json(tools / "manifest.json", {"tools_sha256": tools_sha,
        "fixture_sha256": ram.FIXTURE_FILES, "solver_capsule_attribution": False})
    spec = http_spec(context["image_digest"], capsule / "tree", package, inputs, export, tools)
    storage.atomic_json(root / "compose.json", spec)
    project = "fullmag-antenna-http-ram-" + root.name
    receipt = {"schema": SCHEMA, "state": "starting", "run_root": str(root),
        "profile": PROFILE, "managed_job_id": job, "source_digest": source_digest,
        "native_source_identity": built["native_source_identity"],
        "image_digest": context["image_digest"], "compose_project": project,
        "compose_sha256": sha(root / "compose.json"), "tools_sha256": tools_sha,
        "tool_manifest_sha256": sha(tools / "manifest.json"),
        "fixture_sha256": ram.FIXTURE_FILES,
        "build_receipt_sha256": sha(build / "artifacts/build-receipt.json"),
        "session_storage": "disposable_tmpfs", "qualification": "NOT VERIFIED",
        "physics_qualified": False, "durable_session_storage_qualified": False,
        "unit_tests_compiled": False}
    try:
        args = ["compose", "-f", str(root / "compose.json"), "--project-name", project]
        docker(*args, "config", "--quiet")
        docker(*args, "up", "--detach", "--no-build", "--pull", "never")
        receipt["container_id"] = docker(*args, "ps", "--all", "--quiet", "antenna")
        ram.attest(receipt["container_id"], spec, project)
        receipt.update(state="launched_resources_retained", isolation="PASS")
    except Exception as error:
        receipt.update(state="failed_resources_retained", error=str(error))
        raise
    finally:
        storage.atomic_json(root / "receipt.json", receipt)
        print(json.dumps({"state": receipt["state"], "receipt": str(root / "receipt.json")}))
    return root


def observe(repo, root):
    import fullmag_storage as storage
    import run_managed_antenna_ram as ram
    from run_managed_browser import read_json
    from verify_saved_fem_archive_roundtrip import check_stamp
    layout = storage.resolve_layout(repo, PROFILE)
    root = storage.validate_path(root, Path(layout["build_root"]) / "runs")
    receipt = read_json(root / "receipt.json")
    if receipt.get("schema") != SCHEMA or receipt.get("run_root") != str(root) \
            or receipt.get("compose_sha256") != sha(root / "compose.json"):
        raise ValueError("HTTP RAM gate identity changed")
    native = receipt["native_source_identity"]
    _, build, context, built, capsule, package = resolved(repo, receipt["managed_job_id"],
        native["head_commit_full"], receipt["source_digest"], native["source_snapshot_sha256"])
    tools, inputs = root / "tools", root / "input"
    check_tools(tools, receipt["tools_sha256"])
    manifest = read_json(tools / "manifest.json")
    if receipt["tool_manifest_sha256"] != sha(tools / "manifest.json") \
            or manifest != {"tools_sha256": receipt["tools_sha256"],
                            "fixture_sha256": ram.FIXTURE_FILES, "solver_capsule_attribution": False}:
        raise ValueError("Pinned host-tool manifest differs")
    for name, expected in ram.FIXTURE_FILES.items():
        if sha(inputs / name) != expected or storage.is_link(inputs / name):
            raise ValueError("Pinned scientific input differs")
    spec = read_json(root / "compose.json")
    if spec != http_spec(context["image_digest"], capsule / "tree", package,
                         inputs, root / "export", tools) \
            or receipt["native_source_identity"] != built["native_source_identity"] \
            or receipt["image_digest"] != context["image_digest"] \
            or receipt["fixture_sha256"] != ram.FIXTURE_FILES \
            or receipt["build_receipt_sha256"] != sha(build / "artifacts/build-receipt.json") \
            or receipt["compose_project"] != "fullmag-antenna-http-ram-" + root.name:
        raise ValueError("HTTP gate source/build/spec binding changed")
    observed = ram.attest(receipt["container_id"], spec, receipt["compose_project"])
    state = observed["State"]
    if state.get("Status") != "exited" or state.get("Running"):
        return {"state": "pending", "container_state": state.get("Status"), "run_root": str(root)}
    receipt.update(state="failed_resources_retained", exit_code=state["ExitCode"],
                   oom_killed=state["OOMKilled"])
    try:
        if state["ExitCode"] != 0 or state["OOMKilled"] or state.get("Error"):
            raise ValueError("HTTP gate container failed; read retained logs")
        export = root / "export"
        result = read_json(export / "gate-result.json")
        if result.get("schema") != SCHEMA or result.get("state") != "warm_http_pass" \
                or result.get("solver_exit_code") != 0 \
                or result.get("native_canonical_bundle_redecoded") is not True \
                or result.get("physics_qualified") is not False \
                or result.get("durable_session_storage_qualified") is not False \
                or result.get("reuse_LLG_FFT_qualified") is not False \
                or result.get("tool_manifest_sha256") != receipt["tool_manifest_sha256"]:
            raise ValueError("HTTP gate result is missing or promotes qualification")
        for name in ("api.log", "solver.log"):
            check_stamp((export / name).read_text(encoding="utf-8"), native["head_commit_full"],
                native["source_snapshot_sha256"], dirty=native["source_snapshot_dirty"])
        if not (export / "result.zarr").is_dir() or storage.is_link(export / "result.zarr"):
            raise ValueError("Retained real solver output is absent")
        receipt.update(state="warm_http_pass_resources_retained", startup_identity="PASS",
            gate_result_sha256=sha(export / "gate-result.json"),
            api_log_sha256=sha(export / "api.log"), solver_log_sha256=sha(export / "solver.log"),
            native_canonical_bundle_redecoded=True, cold_archive_import="NOT VERIFIED")
    except Exception as error:
        receipt["error"] = str(error)
        raise
    finally:
        storage.atomic_json(root / "receipt.json", receipt)
    return {"state": receipt["state"], "run_root": str(root)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path)
    sub = parser.add_subparsers(dest="action", required=True)
    start_args = sub.add_parser("start")
    for flag in ("job-id", "commit", "source-digest", "native-snapshot-sha256"):
        start_args.add_argument("--" + flag, required=True)
    sub.add_parser("observe").add_argument("--run-root", type=Path, required=True)
    sub.add_parser("execute")
    args = parser.parse_args()
    if args.action == "execute":
        sys.exit(execute_in_container())
    if args.repo_root is None:
        parser.error("host actions require --repo-root")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if args.action == "start":
        start(args.repo_root, args.job_id, args.commit, args.source_digest, args.native_snapshot_sha256)
    else:
        print(json.dumps(observe(args.repo_root, args.run_root)))
