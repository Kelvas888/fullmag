"""Bounded real antenna HTTP gate using an existing managed CPU package.

All application state remains in tmpfs. Host tools have their own immutable
manifest; they are not attributed to the solver source capsule. No build or
durable SessionStore qualification is performed. A fresh API process imports
the bounded native archive before repeating the real HTTP checks.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from urllib.request import ProxyHandler, Request, build_opener

PROFILE = "managed-antenna-http-ram-cpu"
SCHEMA = "fullmag.managed-antenna-http-ram.v1"
TOOLS = (
    "run_managed_antenna_http_ram.py", "smoke_antenna_external_lead_inspection.py",
    "smoke_antenna_inspection_display.py", "antenna_rt0_fixture_check.py",
    "antenna_current_display_fixture_check.py", "antenna_current_source_oracle.py",
)
ORIGIN = "http://127.0.0.1:8081"
MAX_JSON = 4 << 20
MAX_ARCHIVE = 16 << 20
NONMAGNETIC_SHA = "e3ce550d020ca3e2c811b87f3686890a671b6bf592521a8af5ecfdff06986199"


def fixture_contract(fixture="magnetic"):
    import run_managed_antenna_ram as ram
    files = dict(ram.FIXTURE_FILES)
    if fixture == "nonmagnetic":
        files.pop("fem_antenna_current_source_inspection.py")
        files["fem_antenna_field_only_nonmagnetic.py"] = NONMAGNETIC_SHA
    elif fixture != "magnetic":
        raise ValueError("Unsupported antenna fixture")
    return files


def sha(path):
    with Path(path).open("rb") as stream:
        digest = hashlib.sha256()
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
        return digest.hexdigest()


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


def post_json(path, payload, limit=MAX_JSON):
    body = json.dumps(payload).encode()
    if len(body) > 2 * MAX_ARCHIVE:
        raise ValueError("Archive request exceeds bounded gate support")
    request = Request(ORIGIN + path, data=body,
                      headers={"Content-Type": "application/json"}, method="POST")
    with build_opener(ProxyHandler({})).open(request, timeout=120) as response:
        raw = response.read(limit + 1)
        if response.status != 200 or len(raw) > limit:
            raise ValueError("Archive response exceeds bounded gate support")
        return json.loads(raw)


def export_archive(export):
    response = post_json("/v2/sessions/current/persistence/exports",
                         {"profile": "archive"}, 2 * MAX_ARCHIVE)
    encoded = response.get("fms_base64")
    if not isinstance(encoded, str) or len(encoded) > 2 * MAX_ARCHIVE:
        raise ValueError("Missing or oversized native archive")
    raw = base64.b64decode(encoded, validate=True)
    if not raw or len(raw) > MAX_ARCHIVE or response.get("size_bytes") != len(raw) \
            or response.get("profile") != "archive":
        raise ValueError("Native archive size/profile differs")
    (export / "snapshot.fms").write_bytes(raw)
    return encoded, response["session_id"]


def compare_cold_metadata(warm, cold):
    # Revisions and request incarnation must change; scientific identity must not.
    if not warm.get("outputs") or warm.get("runtime_stage_id") != "stage-000" \
            or warm.get("runtime_stage_id") != cold.get("runtime_stage_id") \
            or warm.get("outputs") != cold.get("outputs"):
        raise ValueError("Cold archive changed canonical inspection identity")


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
    fixture_script = expected.get("fixture_script", "fem_antenna_current_source_inspection.py")
    if fixture_script not in fixture_sha:
        raise ValueError("Fixture script is absent from pinned inputs")
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
            result["warm_api_pid"] = api.pid
            with (export / "solver.log").open("wb") as log:
                solve = subprocess.run(["/package/bin/fullmag-bin",
                    "/input/" + fixture_script, "--headless",
                    "--api-port", "8081", "--expect-script-sha256",
                    fixture_sha[fixture_script],
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
            encoded, session_id = export_archive(export)
            stop_owned(api)
            api = None
            # Original locations disappear before cold import. The archive is
            # the only route back to stage artifacts; retained trees are evidence.
            (workspace / ".fullmag").rename(Path("/ram/warm-state-retired"))
            Path("/ram/result.zarr").rename(Path("/ram/warm-result.zarr"))
            cold_root = Path("/ram/cold-state")
            if cold_root.exists():
                raise ValueError("Cold state root was not fresh")
            cold_env = dict(os.environ, FULLMAG_STATE_ROOT=str(cold_root),
                            FULLMAG_STATE_DIR="/ram/cold-user-state")
            with (export / "cold-api.log").open("wb") as cold_log:
                api = subprocess.Popen(["/package/bin/fullmag-api"], env=cold_env,
                    stdout=cold_log, stderr=subprocess.STDOUT)
                wait_api(api)
                if api.pid == result["warm_api_pid"]:
                    raise ValueError("Cold API process identity was reused")
                result["cold_api_pid"] = api.pid
                restored = post_json("/v2/sessions/current/persistence/imports",
                    {"fms_base64": encoded, "restore_mode": "visualization_only"})
                if restored.get("session_id") != session_id \
                        or restored.get("restore_mode") != "visualization_only":
                    raise ValueError("Cold imported session identity differs")
                cold = get_json("/v2/sessions/current/data/antenna/stages/stage-000/external-lead-inspection")
                compare_cold_metadata(metadata, cold)
                (export / "cold-inspection-metadata.json").write_text(json.dumps(cold, sort_keys=True))
                cold_export = export / "cold-http"
                cold_export.mkdir()
                result["cold_http_smokes"] = {name: smoke(name, "stage-000", cold_export)
                    for name in ("smoke_antenna_external_lead_inspection.py",
                                 "smoke_antenna_inspection_display.py")}
                result.update(state="cold_http_pass", cold_archive_import="PASS",
                    archive_sha256=sha(export / "snapshot.fms"),
                    cold_process_state_root=str(cold_root), cold_solver_executed=False)

    except Exception as error:
        result["error"] = str(error)
    finally:
        try:
            stop_owned(api)
        except Exception as error:
            result.update(state="failed", shutdown_error=str(error))
        output = Path("/ram/warm-result.zarr")
        if not output.is_dir():
            output = Path("/ram/result.zarr")
        if output.is_dir():
            shutil.copytree(output, export / "result.zarr")
        (export / "gate-result.json").write_text(json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "cold_http_pass" else 1


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


def start(repo, job, commit, source_digest, native_digest, fixture="magnetic"):
    import fullmag_storage as storage
    import run_managed_antenna_ram as ram
    from run_managed_browser import docker
    layout, build, context, built, capsule, package = resolved(
        repo, job, commit, source_digest, native_digest)
    fixture_sha = fixture_contract(fixture)
    fixtures = {name: storage.validate_path(repo / "examples" / name, repo) for name in fixture_sha}
    for name, path in fixtures.items():
        if storage.is_link(path) or not path.is_file() or sha(path) != fixture_sha[name]:
            raise ValueError("Fixed scientific input differs: " + name)
    fixture_script = next(name for name in fixture_sha if name.endswith(".py"))
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
        if sha(target) != fixture_sha[name]:
            raise ValueError("Fixture changed during staging")
    for name in TOOLS:
        shutil.copyfile(host_tools / name, tools / name)
    check_tools(tools, tools_sha)
    storage.atomic_json(tools / "manifest.json", {"tools_sha256": tools_sha,
        "fixture_sha256": fixture_sha, "fixture_script": fixture_script, "solver_capsule_attribution": False})
    spec = http_spec(context["image_digest"], capsule / "tree", package, inputs, export, tools)
    storage.atomic_json(root / "compose.json", spec)
    project = "fullmag-antenna-http-ram-" + root.name
    receipt = {"schema": SCHEMA, "state": "starting", "run_root": str(root),
        "profile": PROFILE, "managed_job_id": job, "source_digest": source_digest,
        "native_source_identity": built["native_source_identity"],
        "image_digest": context["image_digest"], "compose_project": project,
        "compose_sha256": sha(root / "compose.json"), "tools_sha256": tools_sha,
        "tool_manifest_sha256": sha(tools / "manifest.json"),
        "fixture_sha256": fixture_sha, "fixture": fixture, "fixture_script": fixture_script,
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
    fixture_sha = fixture_contract(receipt.get("fixture", "magnetic"))
    manifest = read_json(tools / "manifest.json")
    if receipt["tool_manifest_sha256"] != sha(tools / "manifest.json") \
            or manifest != {"tools_sha256": receipt["tools_sha256"],
                            "fixture_sha256": fixture_sha, "fixture_script": receipt["fixture_script"], "solver_capsule_attribution": False}:
        raise ValueError("Pinned host-tool manifest differs")
    for name, expected in fixture_sha.items():
        if sha(inputs / name) != expected or storage.is_link(inputs / name):
            raise ValueError("Pinned scientific input differs")
    spec = read_json(root / "compose.json")
    if spec != http_spec(context["image_digest"], capsule / "tree", package,
                         inputs, root / "export", tools) \
            or receipt["native_source_identity"] != built["native_source_identity"] \
            or receipt["image_digest"] != context["image_digest"] \
            or receipt["fixture_sha256"] != fixture_sha \
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
        if result.get("schema") != SCHEMA or result.get("state") != "cold_http_pass" \
                or result.get("solver_exit_code") != 0 \
                or result.get("native_canonical_bundle_redecoded") is not True \
                or result.get("physics_qualified") is not False \
                or result.get("durable_session_storage_qualified") is not False \
                or result.get("reuse_LLG_FFT_qualified") is not False \
                or result.get("tool_manifest_sha256") != receipt["tool_manifest_sha256"]:
            raise ValueError("HTTP gate result is missing or promotes qualification")
        for name in ("api.log", "solver.log", "cold-api.log"):
            check_stamp((export / name).read_text(encoding="utf-8"), native["head_commit_full"],
                native["source_snapshot_sha256"], dirty=native["source_snapshot_dirty"])
        if not (export / "result.zarr").is_dir() or storage.is_link(export / "result.zarr"):
            raise ValueError("Retained real solver output is absent")
        if result.get("cold_archive_import") != "PASS" or result.get("cold_solver_executed") is not False \
                or result.get("cold_process_state_root") != "/ram/cold-state" \
                or type(result.get("warm_api_pid")) is not int \
                or type(result.get("cold_api_pid")) is not int \
                or result["warm_api_pid"] <= 0 or result["cold_api_pid"] <= 0 \
                or result["warm_api_pid"] == result["cold_api_pid"] \
                or result.get("archive_sha256") != sha(export / "snapshot.fms"):
            raise ValueError("Cold archive proof is missing")
        compare_cold_metadata(read_json(export / "inspection-metadata.json"),
                              read_json(export / "cold-inspection-metadata.json"))
        receipt.update(state="cold_http_pass_resources_retained", startup_identity="PASS",
            gate_result_sha256=sha(export / "gate-result.json"),
            api_log_sha256=sha(export / "api.log"), solver_log_sha256=sha(export / "solver.log"),
            native_canonical_bundle_redecoded=True, cold_archive_import="PASS",
            cold_api_log_sha256=sha(export / "cold-api.log"),
            archive_sha256=sha(export / "snapshot.fms"))
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
    start_args.add_argument("--fixture", choices=("magnetic", "nonmagnetic"), default="magnetic")
    sub.add_parser("observe").add_argument("--run-root", type=Path, required=True)
    sub.add_parser("execute")
    args = parser.parse_args()
    if args.action == "execute":
        sys.exit(execute_in_container())
    if args.repo_root is None:
        parser.error("host actions require --repo-root")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if args.action == "start":
        start(args.repo_root, args.job_id, args.commit, args.source_digest, args.native_snapshot_sha256, args.fixture)
    else:
        print(json.dumps(observe(args.repo_root, args.run_root)))
