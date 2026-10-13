"""Resolve legacy CUDA ordinals to the process-visible CUDA device UUID.

This module deliberately uses only the CUDA Driver API. It does not create a
CUDA context, inspect NVML, change the process environment, or claim that a
device UUID is an authorized physical-host allocation. Callers must validate
the captured UUID against their pinned host policy.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from dataclasses import dataclass


_CUDA_SUCCESS = 0
_LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800
_MAX_VISIBLE_DEVICES = 256
_MAX_ERROR_LENGTH = 240
_INHERITED_CUDA_VISIBLE_DEVICES = os.environ.get("CUDA_VISIBLE_DEVICES")


class _CUuuid(ctypes.Structure):
    _fields_ = [("bytes", ctypes.c_ubyte * 16)]


@dataclass(frozen=True, slots=True)
class _Discovery:
    process_id: int
    cuda_visible_devices: str | None
    device_uuids: tuple[str, ...] | None
    resolution_error: str | None


_lock = threading.RLock()
_discovery: _Discovery | None = None


def _load_cuda_driver() -> object:
    if sys.platform == "win32":
        return ctypes.WinDLL(
            "nvcuda.dll", winmode=_LOAD_LIBRARY_SEARCH_SYSTEM32
        )
    if sys.platform.startswith("linux"):
        return ctypes.CDLL("libcuda.so.1")
    raise OSError("CUDA Driver API discovery is supported only on Windows and Linux")


def _check_cuda_status(status: int, operation: str) -> None:
    if status != _CUDA_SUCCESS:
        raise RuntimeError(f"{operation} returned CUDA status {status}")


def _canonical_gpu_uuid(raw_uuid: bytes) -> str:
    if len(raw_uuid) != 16:
        raise RuntimeError("CUDA Driver API returned an invalid UUID length")
    value = raw_uuid.hex()
    return (
        f"GPU-{value[0:8]}-{value[8:12]}-{value[12:16]}-"
        f"{value[16:20]}-{value[20:32]}"
    )


def _enumerate_visible_cuda_devices() -> tuple[str, ...]:
    driver = _load_cuda_driver()
    init = driver.cuInit
    init.argtypes = [ctypes.c_uint]
    init.restype = ctypes.c_int
    get_count = driver.cuDeviceGetCount
    get_count.argtypes = [ctypes.POINTER(ctypes.c_int)]
    get_count.restype = ctypes.c_int
    get_device = driver.cuDeviceGet
    get_device.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    get_device.restype = ctypes.c_int
    get_uuid = driver.cuDeviceGetUuid_v2
    get_uuid.argtypes = [ctypes.POINTER(_CUuuid), ctypes.c_int]
    get_uuid.restype = ctypes.c_int

    _check_cuda_status(init(0), "cuInit")
    count = ctypes.c_int()
    _check_cuda_status(get_count(ctypes.byref(count)), "cuDeviceGetCount")
    if count.value < 0:
        raise RuntimeError("cuDeviceGetCount returned a negative device count")
    if count.value > _MAX_VISIBLE_DEVICES:
        raise RuntimeError(
            f"visible CUDA device count exceeds {_MAX_VISIBLE_DEVICES}"
        )

    uuids: list[str] = []
    for ordinal in range(count.value):
        device = ctypes.c_int()
        _check_cuda_status(
            get_device(ctypes.byref(device), ordinal), "cuDeviceGet"
        )
        uuid = _CUuuid()
        # The v2 UUID may identify a MIG instance. Exact physical-GPU
        # membership must still be checked by the pinned host-policy owner.
        _check_cuda_status(
            get_uuid(ctypes.byref(uuid), device.value), "cuDeviceGetUuid_v2"
        )
        gpu_uuid = _canonical_gpu_uuid(bytes(uuid.bytes))
        if gpu_uuid in uuids:
            raise RuntimeError("CUDA Driver API returned duplicate visible device UUIDs")
        uuids.append(gpu_uuid)
    return tuple(uuids)


def _short_error(error: Exception) -> str:
    message = " ".join(str(error).split()) or error.__class__.__name__
    return message[:_MAX_ERROR_LENGTH]


def _get_discovery() -> _Discovery:
    global _discovery

    with _lock:
        process_id = os.getpid()
        current_mask = os.environ.get("CUDA_VISIBLE_DEVICES")
        cached = _discovery
        if cached is not None:
            if cached.process_id != process_id:
                return _Discovery(
                    process_id=process_id,
                    cuda_visible_devices=cached.cuda_visible_devices,
                    device_uuids=None,
                    resolution_error=(
                        "CUDA discovery cache was inherited across a process fork; "
                        "start a fresh process to bind a legacy ordinal"
                    ),
                )
            if current_mask != cached.cuda_visible_devices:
                return _Discovery(
                    process_id=process_id,
                    cuda_visible_devices=cached.cuda_visible_devices,
                    device_uuids=None,
                    resolution_error=(
                        "CUDA_VISIBLE_DEVICES changed after CUDA driver discovery; "
                        "the initialized ordinal mapping is ambiguous"
                    ),
                )
            return cached

        inherited_mask = _INHERITED_CUDA_VISIBLE_DEVICES
        if current_mask != inherited_mask:
            _discovery = _Discovery(
                process_id=process_id,
                cuda_visible_devices=inherited_mask,
                device_uuids=None,
                resolution_error=(
                    "CUDA_VISIBLE_DEVICES changed after Fullmag import; "
                    "the inherited ordinal mapping is ambiguous"
                ),
            )
            return _discovery

        try:
            device_uuids = _enumerate_visible_cuda_devices()
            resolution_error = None
        except Exception as error:
            device_uuids = None
            resolution_error = _short_error(error)

        if os.environ.get("CUDA_VISIBLE_DEVICES") != inherited_mask:
            device_uuids = None
            resolution_error = (
                "CUDA_VISIBLE_DEVICES changed during CUDA driver discovery; "
                "the ordinal mapping is ambiguous"
            )

        _discovery = _Discovery(
            process_id=process_id,
            cuda_visible_devices=inherited_mask,
            device_uuids=device_uuids,
            resolution_error=resolution_error,
        )
        return _discovery


def legacy_cuda_binding(ordinal: int) -> dict[str, object]:
    """Return export metadata for one legacy process-visible CUDA ordinal."""
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
        raise ValueError("CUDA device ordinal must be a nonnegative integer")

    discovery = _get_discovery()
    gpu_uuid: str | None = None
    error = discovery.resolution_error
    if error is None:
        assert discovery.device_uuids is not None
        if ordinal >= len(discovery.device_uuids):
            error = (
                f"CUDA ordinal {ordinal} is outside the visible device range "
                f"[0, {len(discovery.device_uuids)})"
            )
        else:
            gpu_uuid = discovery.device_uuids[ordinal]

    result: dict[str, object] = {
        "schema_version": "legacy_cuda_binding.v1",
        "ordinal": ordinal,
        "cuda_visible_devices": discovery.cuda_visible_devices,
        "gpu_uuid": gpu_uuid,
    }
    if error is not None:
        result["resolution_error"] = _short_error(RuntimeError(error))
    return result


__all__ = ["legacy_cuda_binding"]
