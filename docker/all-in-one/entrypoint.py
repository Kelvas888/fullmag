"""Fail before API startup when GPU or durable state storage is unavailable."""
import ctypes
import os
import subprocess
import uuid
from pathlib import Path


def preflight():
    kind = subprocess.check_output(["stat", "-f", "-c", "%t", "/state"], text=True).strip()
    # Same supported writer filesystem types as the managed browser route.
    if kind.lower().lstrip("0") not in {"ef53", "58465342", "9123683e", "1021994", "794c7630"}:
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


if __name__ == "__main__":
    preflight()
    os.execv("/opt/fullmag/package/bin/fullmag-api", ["fullmag-api"])
