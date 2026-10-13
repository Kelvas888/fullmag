"""Verify the native CLI initializer for an operator-pinned host policy.

This fixture proves configuration and ledger initialization only. Its CPU
topology is synthetic and it never launches a runtime service or worker.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import uuid
from datetime import datetime, timezone

import fullmag_storage as storage
from windows.verify_compute_cancellation_api import (
    _api_environment,
    _canonical_json_sha256,
    _run_store_initializer,
)


INITIALIZER_TIMEOUT_SECONDS = 30
HOST_POLICY_SCHEMA = "host_resource_ledger_policy.v1"
HOST_EXECUTION_SCHEMA = "runtime_service_host_execution.v1"
CONFIG_SCHEMA_V1 = "runtime_service_config.v1"
CONFIG_SCHEMA_V2 = "runtime_service_config.v2"
SYNTHETIC_TOPOLOGY_SHA256 = hashlib.sha256(
    b"fullmag synthetic host initialization topology fixture v1"
).hexdigest()


def _persist(path: Path, value: dict) -> None:
    storage.atomic_json(path, value)


def _check(name: str, condition: bool, evidence: dict,
           evidence_path: Path, receipt: dict, detail: object = None) -> None:
    if not condition:
        raise AssertionError(f"{name} failed: {detail!r}")
    evidence["checks"].append(name)
    receipt["checks"].append("compute-host-initialization-" + name)
    _persist(evidence_path, evidence)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _tree_snapshot(root: Path) -> dict[str, str]:
    """Hash a fixture tree without following links or changing its contents."""
    if not root.exists():
        return {"<root>": "missing"}
    snapshot: dict[str, str] = {"<root>": "directory"}
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in list(directories):
            path = current_path / name
            if path.is_symlink():
                raise RuntimeError(f"fixture state contains a symlink: {path}")
            snapshot[path.relative_to(root).as_posix()] = "directory"
        for name in files:
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f"fixture state contains a non-regular file: {path}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            snapshot[path.relative_to(root).as_posix()] = digest
    return dict(sorted(snapshot.items()))


def _file_digest(path: Path) -> str:
    if not path.exists():
        return "missing"
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"expected a regular durable state file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _durable_state_snapshot(store_root: Path, ledger_root: Path) -> dict[str, str]:
    return {
        "application": _file_digest(store_root / "runtime-services" / "APPLICATION.json"),
        "ledger_marker": _file_digest(ledger_root / "HOST_RESOURCE_LEDGER.init.json"),
        "ledger": _file_digest(ledger_root / "HOST_RESOURCE_LEDGER.json"),
    }


def _canonical_windows_path(path: Path) -> str:
    """Match std::fs::canonicalize's Windows path used by SessionStore."""
    if os.name != "nt":
        raise RuntimeError("host initialization verification requires native Windows")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    get_final_path.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    file_read_attributes = 0x80
    share_all = 0x1 | 0x2 | 0x4
    open_existing = 3
    file_flag_backup_semantics = 0x02000000
    handle = create_file(
        str(path),
        file_read_attributes,
        share_all,
        None,
        open_existing,
        file_flag_backup_semantics,
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_final_path(handle, buffer, len(buffer), 0)
        if length == 0 or length >= len(buffer):
            raise ctypes.WinError(ctypes.get_last_error())
        canonical_path = buffer.value
    finally:
        close_handle(handle)
    return canonical_path


def _expected_store_id(store_root: Path) -> str:
    """Mirror HostResourceLedger::store_id's Windows canonical-path encoding."""
    encoded_path = _canonical_windows_path(store_root).encode("utf-16-le")
    return "sha256:" + hashlib.sha256(encoded_path).hexdigest()


def _fixture_config(store_root: Path, *, host_execution: bool = True) -> dict:
    compute_id = "native-local.compute.cpu"
    preparation_id = "native-local.preparation.cpu"
    budget = {
        "cpu_millis": 1000,
        "memory_bytes": 1024 * 1024,
        "gpu_memory_bytes": 0,
        "storage_bytes": 1024 * 1024,
    }
    config = {
        "schema_version": CONFIG_SCHEMA_V2 if host_execution else CONFIG_SCHEMA_V1,
        "store_root": str(store_root),
        "target_id": "native-local",
        "compute_pool_id": "native-local.compute",
        "preparation_pool_id": "native-local.preparation",
        "compute_resources": [{
            "resource_id": compute_id,
            "kind": "cpu",
            "budget": budget,
        }],
        "preparation_resources": [{
            "resource_id": preparation_id,
            "budget": budget,
        }],
        "worker_timeout_seconds": 3600,
        "preparation_timeout_seconds": 3600,
        "heartbeat_interval_milliseconds": 1000,
        "startup_timeout_seconds": 60,
        "drain_timeout_seconds": 60,
    }
    if host_execution:
        config["host_execution"] = {
            "schema_version": HOST_EXECUTION_SCHEMA,
            "ledger_root": str(store_root / "shared-host-ledger"),
            "policy": {
                "schema_version": HOST_POLICY_SCHEMA,
                "host_id": "fixture-host-initialization",
                "topology_sha256": SYNTHETIC_TOPOLOGY_SHA256,
                "revision": 1,
                "owner_epoch": 1,
                "total_budget": {
                    "cpu_millis": 4000,
                    "memory_bytes": 8 * 1024 * 1024,
                    "gpu_memory_bytes": 0,
                    "storage_bytes": 8 * 1024 * 1024,
                },
            },
            "compute_max_concurrency": 1,
            "preparation_max_concurrency": 1,
            "compute_placements": {
                compute_id: {"cpu_ids": [], "gpu_uuid": None},
            },
            "preparation_cpu_ids": {preparation_id: []},
        }
    return config


def _reserve_ephemeral_port() -> int:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return int(reservation.getsockname()[1])


def _remember_store_process(receipt: dict, evidence: dict, case_root: Path,
                            start_index: int, case_name: str) -> None:
    processes = receipt.get("processes", [])
    if len(processes) <= start_index:
        return
    record = processes[start_index]
    record["label"] = "compute-host-initialization-scoped-store-initialize"
    record["case"] = case_name
    log_path = case_root / "compute-cancellation-store-init.log"
    record["log_path"] = str(log_path)
    evidence["processes"].append(dict(record))


def _new_case(repo: Path, run_root: Path, native: dict,
              store_initializer: Path, receipt: dict, evidence: dict,
              case_name: str) -> dict:
    case_root = run_root / "compute-host-initialization" / case_name
    case_root.mkdir(parents=True, exist_ok=False)
    scope = str(uuid.uuid4())
    scope_root = Path(native["runs_root"]) / "workspaces" / scope
    if os.path.lexists(scope_root):
        raise RuntimeError("Unique managed host-initialization scope already exists")
    store_root = scope_root / "session-store"
    environment = _api_environment(
        repo, case_root, native, _reserve_ephemeral_port(), scope
    )
    Path(environment["FULLMAG_STATE_ROOT"]).mkdir(parents=True, exist_ok=False)
    evidence["scopes"].append({
        "case": case_name,
        "scope": scope,
        "store_root": str(store_root),
        "host_policy_is_synthetic": True,
    })
    _persist(run_root / "compute-host-initialization-evidence.json", evidence)
    process_start = len(receipt.setdefault("processes", []))
    try:
        _run_store_initializer(
            store_initializer, repo, environment, case_root, receipt
        )
    finally:
        _remember_store_process(
            receipt, evidence, case_root, process_start, case_name
        )
        _persist(run_root / "compute-host-initialization-evidence.json", evidence)
    if not store_root.is_dir() or not (store_root / "objects").is_dir():
        raise RuntimeError(f"Production CLI did not initialize scoped store for {case_name}")
    store_root = Path(_canonical_windows_path(store_root))
    evidence["scopes"][-1]["store_root"] = str(store_root)
    evidence["fixture_seeded"] = True
    _persist(run_root / "compute-host-initialization-evidence.json", evidence)
    return {
        "case": case_name,
        "case_root": case_root,
        "scope": scope,
        "scope_root": scope_root,
        "store_root": store_root,
        "environment": environment,
    }


def _run_host_initializer(executable: Path, repo: Path, environment: dict[str, str],
                          case: dict, config_path: Path, config_sha256: str,
                          receipt: dict, evidence: dict,
                          evidence_path: Path) -> tuple[int, object, str]:
    case_name = case["case"]
    attempt = len([
        record for record in evidence["processes"]
        if record.get("case") == case_name
        and record.get("label") == "compute-host-initialization-native-cli"
    ]) + 1
    log_path = case["case_root"] / f"host-initializer-{attempt}.log"
    record = {
        "label": "compute-host-initialization-native-cli",
        "case": case_name,
        "pid": None,
        "log_path": str(log_path),
        "waited": False,
        "expected_configuration_sha256": config_sha256,
    }
    receipt["processes"].append(record)
    child: subprocess.Popen | None = None
    timed_out = False
    try:
        with log_path.open("wb") as log:
            child = subprocess.Popen(
                [
                    str(executable),
                    "runtime",
                    "initialize-host-application",
                    "--config",
                    str(config_path),
                    "--config-sha256",
                    config_sha256,
                ],
                cwd=repo,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            record["pid"] = child.pid
            try:
                record["exit_code"] = child.wait(timeout=INITIALIZER_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                timed_out = True
                _reap_owned_child(child, record)
            record["waited"] = child.poll() is not None
        record["log_sha256"] = hashlib.sha256(log_path.read_bytes()).hexdigest()
        output = log_path.read_text(encoding="utf-8", errors="replace")
        if not record["waited"]:
            raise RuntimeError(f"Owned host-initializer child was not reaped: {record!r}")
        if timed_out:
            raise TimeoutError(f"Owned host-initializer child exceeded its timeout: {record!r}")
        result: object = None
        if record["exit_code"] == 0:
            for line in reversed(output.splitlines()):
                try:
                    result = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
            if not isinstance(result, dict):
                raise RuntimeError("Host initializer did not return one JSON object")
        record["output_sha256"] = hashlib.sha256(output.encode("utf-8")).hexdigest()
        evidence["processes"].append(dict(record))
        _persist(evidence_path, evidence)
        return int(record["exit_code"]), result, output
    except BaseException as error:
        if child is not None:
            try:
                _reap_owned_child(child, record)
            except BaseException as cleanup_error:
                record["cleanup_error"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
        record["error"] = f"{type(error).__name__}: {error}"
        if log_path.exists():
            record["log_sha256"] = hashlib.sha256(log_path.read_bytes()).hexdigest()
        if not any(
            item.get("pid") == record.get("pid")
            and item.get("label") == record["label"]
            for item in evidence["processes"]
        ):
            evidence["processes"].append(dict(record))
        _persist(evidence_path, evidence)
        raise


def _reap_owned_child(child: subprocess.Popen, record: dict) -> None:
    if child.poll() is None:
        record["stop_requested_by_verifier"] = True
        try:
            child.terminate()
        except OSError:
            pass
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            record["forced_exit_of_owned_child"] = True
            try:
                child.kill()
            except OSError:
                pass
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                record["waited"] = False
                record["exit_code"] = child.poll()
                raise RuntimeError("Owned host initializer did not exit after forced termination")
    record["exit_code"] = child.returncode
    record["waited"] = child.poll() is not None


def _initialize(executable: Path, repo: Path, case: dict, config: dict,
                receipt: dict, evidence: dict, evidence_path: Path,
                *, config_name: str = "operator-host-config.json",
                pin: str | None = None) -> tuple[int, object, str, Path, str]:
    config_path = case["case_root"] / config_name
    _write_json(config_path, config)
    digest = _canonical_json_sha256(config)
    return (*_run_host_initializer(
        executable,
        repo,
        case["environment"],
        case,
        config_path,
        digest if pin is None else pin,
        receipt,
        evidence,
        evidence_path,
    ), config_path, digest)


def _expect_rejection(name: str, executable: Path, repo: Path, case: dict,
                      config: dict, expected_error: str, receipt: dict,
                      evidence: dict, evidence_path: Path,
                      *, config_name: str = "operator-host-config.json",
                      pin: str | None = None) -> None:
    exit_code, _body, output, _config_path, _digest = _initialize(
        executable, repo, case, config, receipt, evidence, evidence_path,
        config_name=config_name, pin=pin,
    )
    _check(
        name + "-rejected-by-native-cli",
        exit_code != 0 and expected_error.casefold() in output.casefold(),
        evidence, evidence_path, receipt,
        {"exit_code": exit_code, "expected_error": expected_error, "output": output[-1000:]},
    )


def exercise(api: Path, repo: Path, run_root: Path, receipt: dict) -> None:
    """Exercise the native host initializer without launching a service."""
    fixture_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    evidence_path = run_root / "compute-host-initialization-evidence.json"
    evidence = {
        "schema": "fullmag.compute-host-initialization-evidence.v1",
        "state": "running",
        "fixture_sha256": fixture_sha256,
        "fixture_seeded": False,
        "synthetic_topology_sha256": SYNTHETIC_TOPOLOGY_SHA256,
        "qualification": (
            "managed native CLI initialization of a scoped application configuration "
            "and host ledger using an explicit synthetic CPU-only policy; no host "
            "topology or hardware proof, service owner, scheduler, worker claim, "
            "solver, Submit, enforcement, physics, or release qualification"
        ),
        "fixture_metadata": (
            "synthetic CPU config, partial-ledger sentinel, and OWNER/LAUNCH/"
            "admission-fence metadata are fixture inputs, not process or lifecycle proof"
        ),
        "scopes": [],
        "processes": [],
        "checks": [],
    }
    receipt.setdefault("checks", [])
    receipt.setdefault("processes", [])
    _persist(evidence_path, evidence)
    try:
        if os.name != "nt":
            raise RuntimeError("Managed native host initialization is Windows-only")
        native = storage.resolve_layout(repo, "windows-native-fdm-cpu-dev")
        initializer = api.parent / "fullmag.exe"
        if not initializer.is_file():
            raise RuntimeError("Verified native package lacks sibling fullmag.exe")

        cases_root = run_root / "compute-host-initialization"
        cases_root.mkdir(parents=True, exist_ok=False)

        success = _new_case(
            repo, run_root, native, initializer, receipt, evidence, "success"
        )
        config = _fixture_config(success["store_root"])
        exit_code, body, _output, config_path, config_sha256 = _initialize(
            initializer, repo, success, config, receipt, evidence, evidence_path
        )
        _check(
            "native-cli-initializes-scoped-store",
            exit_code == 0,
            evidence, evidence_path, receipt,
            {"exit_code": exit_code, "store_root": str(success["store_root"])},
        )
        expected_store_id = _expected_store_id(success["store_root"])
        identity_ok = (
            isinstance(body, dict)
            and body.get("schema_version") == "runtime_host_initialization.v1"
            and body.get("status") == "configuration_and_ledger_ready"
            and body.get("configuration_sha256") == config_sha256
            and body.get("store_id") == expected_store_id
            and body.get("target_id") == "native-local"
            and body.get("host_id") == config["host_execution"]["policy"]["host_id"]
            and body.get("policy_revision") == 1
            and body.get("owner_epoch") == 1
            and body.get("topology_sha256") == SYNTHETIC_TOPOLOGY_SHA256
            and body.get("execution_available") is False
        )
        _check(
            "response-reports-pinned-synthetic-host-identity-and-no-execution",
            identity_ok,
            evidence, evidence_path, receipt,
            {"response": body, "expected_store_id": expected_store_id},
        )

        application_path = success["store_root"] / "runtime-services" / "APPLICATION.json"
        ledger_root = Path(config["host_execution"]["ledger_root"])
        marker_path = ledger_root / "HOST_RESOURCE_LEDGER.init.json"
        ledger_path = ledger_root / "HOST_RESOURCE_LEDGER.json"
        application_bytes = application_path.read_bytes()
        marker_bytes = marker_path.read_bytes()
        ledger_bytes = ledger_path.read_bytes()
        application_document = json.loads(application_bytes.decode("utf-8"))
        ledger_document = json.loads(ledger_bytes.decode("utf-8"))
        _check(
            "application-and-empty-host-ledger-published",
            application_document == config
            and ledger_document.get("policy") == config["host_execution"]["policy"]
            and ledger_document.get("reservations") == [],
            evidence, evidence_path, receipt,
            {"application_path": str(application_path), "ledger_root": str(ledger_root)},
        )

        retry_code, retry_body, _retry_output, _retry_path, _retry_digest = _initialize(
            initializer, repo, success, config, receipt, evidence, evidence_path,
            config_name="operator-host-config-retry.json",
        )
        _check(
            "exact-retry-preserves-config-and-ledger-bytes",
            retry_code == 0
            and retry_body == body
            and application_path.read_bytes() == application_bytes
            and marker_path.read_bytes() == marker_bytes
            and ledger_path.read_bytes() == ledger_bytes,
            evidence, evidence_path, receipt,
            {"retry_response": retry_body},
        )

        changed = json.loads(json.dumps(config))
        changed["host_execution"]["policy"]["revision"] = 2
        changed_state = _durable_state_snapshot(success["store_root"], ledger_root)
        _expect_rejection(
            "changed-config", initializer, repo, success, changed,
            "persisted application configuration differs from the requested host configuration",
            receipt, evidence, evidence_path, config_name="changed-host-config.json",
        )
        _check(
            "changed-config-rejection-preserves-application-and-ledger",
            _durable_state_snapshot(success["store_root"], ledger_root) == changed_state,
            evidence, evidence_path, receipt,
        )

        wrong_pin = "0" * 64 if config_sha256 != "0" * 64 else "1" * 64
        wrong_pin_state = _tree_snapshot(success["store_root"])
        _expect_rejection(
            "wrong-pin", initializer, repo, success, config,
            "configuration digest differs from the operator pin",
            receipt, evidence, evidence_path, config_name="wrong-pin-config.json",
            pin=wrong_pin,
        )
        _check(
            "wrong-pin-rejection-preserves-store-tree",
            _tree_snapshot(success["store_root"]) == wrong_pin_state,
            evidence, evidence_path, receipt,
        )

        v1_candidate_case = _new_case(
            repo, run_root, native, initializer, receipt, evidence, "v1-candidate"
        )
        v1_candidate = _fixture_config(v1_candidate_case["store_root"], host_execution=False)
        v1_ledger_root = v1_candidate_case["store_root"] / "shared-host-ledger"
        v1_before = _durable_state_snapshot(v1_candidate_case["store_root"], v1_ledger_root)
        _expect_rejection(
            "v1-candidate", initializer, repo, v1_candidate_case, v1_candidate,
            "host application initialization requires a v2 host execution binding",
            receipt, evidence, evidence_path,
        )
        _check(
            "v1-candidate-rejection-does-not-publish-application-or-ledger",
            _durable_state_snapshot(v1_candidate_case["store_root"], v1_ledger_root) == v1_before,
            evidence, evidence_path, receipt,
        )

        existing_v1_case = _new_case(
            repo, run_root, native, initializer, receipt, evidence, "existing-v1"
        )
        existing_v1 = _fixture_config(existing_v1_case["store_root"], host_execution=False)
        existing_v1_path = existing_v1_case["store_root"] / "runtime-services" / "APPLICATION.json"
        _write_json(existing_v1_path, existing_v1)
        v2_candidate = _fixture_config(existing_v1_case["store_root"])
        existing_v1_bytes = existing_v1_path.read_bytes()
        existing_v1_ledger_root = Path(v2_candidate["host_execution"]["ledger_root"])
        _expect_rejection(
            "existing-v1-config", initializer, repo, existing_v1_case, v2_candidate,
            "persisted application configuration differs from the requested host configuration",
            receipt, evidence, evidence_path,
        )
        _check(
            "existing-v1-config-remains-byte-identical-without-ledger",
            existing_v1_path.read_bytes() == existing_v1_bytes
            and not existing_v1_ledger_root.exists(),
            evidence, evidence_path, receipt,
        )

        partial_case = _new_case(
            repo, run_root, native, initializer, receipt, evidence, "partial-ledger"
        )
        partial_config = _fixture_config(partial_case["store_root"])
        partial_ledger_root = Path(partial_config["host_execution"]["ledger_root"])
        partial_ledger_root.mkdir(parents=True, exist_ok=False)
        partial_marker = partial_ledger_root / "HOST_RESOURCE_LEDGER.init.json"
        partial_marker.write_bytes(b"synthetic partial-ledger rejection fixture\n")
        partial_marker_bytes = partial_marker.read_bytes()
        partial_app_path = partial_case["store_root"] / "runtime-services" / "APPLICATION.json"
        _expect_rejection(
            "partial-ledger", initializer, repo, partial_case, partial_config,
            "host resource ledger has partial initialization",
            receipt, evidence, evidence_path,
        )
        partial_app_bytes = partial_app_path.read_bytes()
        _check(
            "partial-ledger-failure-keeps-pinned-config-and-partial-bytes",
            json.loads(partial_app_bytes.decode("utf-8")) == partial_config
            and partial_marker.read_bytes() == partial_marker_bytes
            and not (partial_ledger_root / "HOST_RESOURCE_LEDGER.json").exists(),
            evidence, evidence_path, receipt,
        )
        _expect_rejection(
            "partial-ledger-retry", initializer, repo, partial_case, partial_config,
            "host resource ledger has partial initialization",
            receipt, evidence, evidence_path, config_name="partial-ledger-retry.json",
        )
        _check(
            "partial-ledger-retry-preserves-pinned-config-and-partial-bytes",
            partial_app_path.read_bytes() == partial_app_bytes
            and partial_marker.read_bytes() == partial_marker_bytes
            and not (partial_ledger_root / "HOST_RESOURCE_LEDGER.json").exists(),
            evidence, evidence_path, receipt,
        )

        for record_name in (
            "runtime-services/OWNER.lock",
            "runtime-services/OWNER.json",
            "runtime-services/LAUNCH.json",
        ):
            case_name = "existing-" + Path(record_name).name.lower().replace(".", "-")
            owner_case = _new_case(
                repo, run_root, native, initializer, receipt, evidence, case_name
            )
            owner_config = _fixture_config(owner_case["store_root"])
            record_path = owner_case["store_root"] / Path(record_name)
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_bytes = b"synthetic owner or launch metadata fixture; not process proof\n"
            record_path.write_bytes(record_bytes)
            owner_ledger_root = Path(owner_config["host_execution"]["ledger_root"])
            _expect_rejection(
                case_name, initializer, repo, owner_case, owner_config,
                "runtime service already has an owner or launch record",
                receipt, evidence, evidence_path,
            )
            _check(
                case_name + "-metadata-preserved-without-application-or-ledger",
                record_path.read_bytes() == record_bytes
                and not (owner_case["store_root"] / "runtime-services" / "APPLICATION.json").exists()
                and not owner_ledger_root.exists(),
                evidence, evidence_path, receipt,
            )

        fence_case = _new_case(
            repo, run_root, native, initializer, receipt, evidence, "admission-fence"
        )
        fence_config = _fixture_config(fence_case["store_root"])
        fence_ledger_root = Path(fence_config["host_execution"]["ledger_root"])
        fence_path = fence_case["store_root"] / "development" / "ADMISSION-FENCE.json"
        fence = {
            "schema": "fullmag.development-admission-fence.v1",
            "owner_token": str(uuid.uuid4()),
            "nonce": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        _write_json(fence_path, fence)
        fence_bytes = fence_path.read_bytes()
        fence_state = _durable_state_snapshot(fence_case["store_root"], fence_ledger_root)
        _expect_rejection(
            "active-development-admission-fence", initializer, repo, fence_case,
            fence_config,
            "host initialization refused while development admission is closed",
            receipt, evidence, evidence_path,
        )
        _check(
            "synthetic-admission-fence-preserved-without-application-or-ledger",
            fence_path.read_bytes() == fence_bytes
            and _durable_state_snapshot(fence_case["store_root"], fence_ledger_root) == fence_state,
            evidence, evidence_path, receipt,
            {"fixture_metadata_only": True, "path": str(fence_path)},
        )

        _check(
            "verifier-source-remained-unchanged",
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == fixture_sha256,
            evidence, evidence_path, receipt, fixture_sha256,
        )
        evidence["state"] = "completed"
        receipt["compute_host_initialization_fixture_seeded"] = True
        receipt["compute_host_initialization_fixture_sha256"] = fixture_sha256
        receipt["compute_host_initialization_evidence"] = str(evidence_path)
        receipt["compute_host_initialization_qualification"] = evidence["qualification"]
    except Exception as error:
        evidence["state"] = "failed"
        evidence["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        _persist(evidence_path, evidence)
