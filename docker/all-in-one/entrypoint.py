"""Fail before API startup when GPU or durable state storage is unavailable."""
import ctypes
import hashlib
import json
import re
import os
import subprocess
import sys
import signal
import threading
import time
import uuid
from pathlib import Path


def _publish_linux_readback(probe, directory_fd, name, payload):
    """Publish guest attestations readable by the host's distinct UID."""
    probe._publish_at(directory_fd, name, payload)
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory_fd)
    try:
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def linux_storage_probe(require_restart, root=Path("/state"),
                        certificate=Path("/run/fullmag/linux-native-host.json")):
    """Qualify native Linux storage using pinned, no-follow file operations."""
    import windows_folder_probe as probe

    host = json.loads(probe.read_regular(certificate))
    image = os.environ.get("FULLMAG_RUNTIME_IMAGE_ID", "")
    if (not isinstance(host, dict)
            or host.get("schema") != "fullmag.linux-native-host.v1"
            or host.get("storage_profile") != "linux-native-v1"
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", image)
            or host.get("image_id") != image
            or not isinstance(host.get("owner_token"), str)
            or not re.fullmatch(r"[0-9a-f]{32}", host["owner_token"])
            or type(host.get("restart_verified")) is not bool):
        raise RuntimeError("Invalid native Linux host admission")
    payload = (host["owner_token"] + ":" + image).encode("ascii")
    expected = hashlib.sha256(payload).hexdigest()
    if host.get("restart_expected_sha256") != expected:
        raise RuntimeError("Invalid native Linux restart digest")
    if require_restart and host["restart_verified"] is not True:
        raise RuntimeError("Native Linux host has not confirmed restart readback")

    root_fd = probe._open_pinned_directory(root)
    try:
        if probe._read_regular_at(root_fd, ".linux-native-sentinel", 256) != payload:
            raise RuntimeError("Native Linux host sentinel mismatch")
        restart_name = ".linux-native-restart"
        existed = probe._exists_at(root_fd, restart_name)
        if existed:
            if probe._read_regular_at(root_fd, restart_name, 256) != payload:
                raise RuntimeError("Restart sentinel changed")
        elif require_restart:
            raise RuntimeError("Restart sentinel is missing")
        else:
            _publish_linux_readback(probe, root_fd, restart_name, payload)

        directory_fd = probe._ensure_directory_at(root_fd, ".linux-native-probe")
        try:
            # Replace a prior value and read back after the durable rename.
            probe._publish_at(directory_fd, "publication.bin", b"before")
            probe._publish_at(directory_fd, "publication.bin", payload)
            if probe._read_regular_at(directory_fd, "publication.bin", 256) != payload:
                raise RuntimeError("Native Linux atomic publication mismatch")
            probe._child_lock_probe(directory_fd)
            probe._sqlite_probe(directory_fd, host["owner_token"])
        finally:
            os.close(directory_fd)
        result = {"schema": "fullmag.linux-native-probe.v1",
                  "storage_profile": "linux-native-v1", "image_id": image,
                  "owner_token": host["owner_token"],
                  "checks": {"file_sync": True, "directory_sync": True,
                             "atomic_replace": True, "process_lock": True,
                             "sqlite_transactions": True, "restart_readback": existed}}
        _publish_linux_readback(probe, root_fd, ".linux-native-probe.json",
                                json.dumps(result, indent=2).encode("utf-8"))
        return result
    finally:
        os.close(root_fd)


def preflight():
    kind = subprocess.check_output(["stat", "-f", "-c", "%t", "/state"], text=True).strip()
    profile = os.environ.get("FULLMAG_SESSION_STORAGE_PROFILE")
    if profile == "linux-native-v1":
        if kind.lower().lstrip("0") not in {"ef53", "58465342", "9123683e"}:
            raise RuntimeError(f"Unsupported native Linux durable filesystem 0x{kind}; "
                               "use ext4, XFS or Btrfs storage")
        linux_storage_probe(require_restart="--storage-probe" not in sys.argv)
    # Preserve the Windows operational admission route.
    elif kind.lower().lstrip("0") == "1021997" and os.environ.get("FULLMAG_SESSION_STORAGE_PROFILE") == "windows-folder-v1":
        from windows_folder_probe import run
        run(require_restart="--storage-probe" not in sys.argv)
    elif kind.lower().lstrip("0") not in {"ef53", "58465342", "9123683e", "1021994", "794c7630"}:
        raise RuntimeError(f"Unsupported durable session filesystem 0x{kind}; "
                           "configure supported project storage; no ephemeral fallback")
    driver = ctypes.CDLL("libcuda.so.1")
    if driver.cuInit(0) != 0:
        raise RuntimeError("NVIDIA CUDA driver initialization failed")
    count = ctypes.c_int()
    if driver.cuDeviceGetCount(ctypes.byref(count)) != 0 or count.value < 1:
        raise RuntimeError("No NVIDIA CUDA GPU available")
    for directory in ("/state/.fullmag", "/state/cuda-cache", "/state/.fullmag/mesh-cache"):
        Path(directory).mkdir(parents=True, exist_ok=True)
    probe = Path("/state/.fullmag") / (".write-probe-" + uuid.uuid4().hex)
    with probe.open("xb") as stream:
        stream.write(b"fullmag-state-preflight\n")
        stream.flush()
        os.fsync(stream.fileno())
    probe.unlink()


def serve():
    import runtime_service as service
    stopping = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: stopping.set())
    paths = service.prepare_storage()
    service.ensure_configuration(paths)
    bootstrap = service.initialize_accepted_store(paths)
    api = subprocess.Popen(["/opt/fullmag/package/bin/fullmag-api"],
                           env=service.process_environment(paths))
    handle = None
    receipt = {"schema": "fullmag.docker-process-tree.v1", "state": "starting",
               "api_pid": api.pid, "accepted_store": str(paths.store),
               "bootstrap": bootstrap, "qualification": "NOT VERIFIED"}
    receipt_path = paths.state_root / "runtime-service/process-tree.json"
    result = 1
    last_full_api_probe = 0.0
    try:
        service._atomic_json(receipt_path, receipt, "process tree receipt")
        handle = service.start(paths, api_port=8081, expected_binding=bootstrap["binding"])
        last_full_api_probe = time.monotonic()
        receipt.update(state="ready", service_owner=handle.owner)
        service._atomic_json(receipt_path, receipt, "process tree receipt")
        while not stopping.wait(1):
            status = api.poll()
            if status is not None:
                raise RuntimeError(f"Fullmag API exited unexpectedly ({status})")
            now = time.monotonic()
            full_api_probe = now - last_full_api_probe >= 5.0
            service.check(handle, full_api_probe=full_api_probe)
            if full_api_probe:
                last_full_api_probe = now
        result = 0
    except Exception as error:
        pinned_handle = getattr(error, "pinned_handle", None)
        if isinstance(pinned_handle, service.RuntimeHandle):
            handle = pinned_handle
            receipt["service_owner"] = handle.owner
            if getattr(error, "owner_pin_durable", False):
                receipt["owner_pin"] = str(service._owner_pin_path(paths, handle.owner))
                receipt["owner_pin_state"] = "durably-pinned-before-startup-observation"
            else:
                try:
                    receipt["owner_pin_candidate"] = str(
                        service._owner_pin_path(paths, handle.owner)
                    )
                except Exception:
                    pass
                receipt["owner_pin_state"] = (
                    "confirmed-owner-awaiting-authenticated-reprobe"
                )
        receipt.update(state="failed_outcome_retained", error=str(error))
        if api.poll() is None:
            api.terminate()
        try:
            receipt["api_exit_code"] = api.wait(timeout=10)
        except subprocess.TimeoutExpired:
            receipt["api_shutdown"] = "unknown"
        service._atomic_json(receipt_path, receipt, "process tree receipt")
        # Failed observation must preserve a possibly live detached service.
        # Keep PID 1 alive with admission closed until an explicit stop.
        while not stopping.wait(1):
            pass
    finally:
        # Close this container's admission before draining its authenticated
        # scheduler owner. Never infer completion from an unconfirmed timeout.
        if api.poll() is None:
            api.terminate()
        try:
            receipt["api_exit_code"] = api.wait(timeout=10)
            if handle is not None:
                receipt["terminal_service_owner"] = service.stop(handle, timeout=30)
                receipt["state"] = "drained"
            else:
                receipt.update(
                    state="shutdown_unknown",
                    shutdown_error="no pinned runtime service owner was available for authenticated drain",
                )
        except Exception as error:
            receipt.update(state="shutdown_unknown", shutdown_error=str(error))
            raise
        finally:
            service._atomic_json(receipt_path, receipt, "process tree receipt")
    return result


def serve_frontend():
    import frontend_dev
    stopping = threading.Event()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda *_: stopping.set())
    handle = None
    try:
        handle = frontend_dev.start(stopping)
        while not stopping.wait(1):
            frontend_dev.check(handle)
        return 0
    except Exception as error:
        handle = getattr(error, "frontend_handle", handle)
        raise
    finally:
        if handle is not None:
            frontend_dev.stop(handle)


if __name__ == "__main__":
    role = os.environ.get("FULLMAG_DOCKER_ROLE", "backend")
    if role == "frontend":
        if "--storage-probe" in sys.argv:
            raise RuntimeError("Frontend cannot run the session storage probe")
        sys.exit(serve_frontend())
    if role != "backend":
        raise RuntimeError("Unsupported Fullmag Docker role")
    preflight()
    if "--storage-probe" in sys.argv:
        sys.exit(0)
    sys.exit(serve())
