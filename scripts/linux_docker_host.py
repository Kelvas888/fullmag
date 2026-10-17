"""Native Linux/WSL paths and bounded reads for the Docker launcher."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import sys

import fullmag_storage as storage

PROFILE = "linux-native-v1"
CERTIFICATE_TARGET = "/run/fullmag/linux-native-host.json"


def local_volume(path):
    if not sys.platform.startswith("linux"):
        raise ValueError("Native Docker storage requires Linux or WSL")
    path = storage.absolute(path, "native Linux path")
    filesystem = storage.filesystem_type(path)
    if filesystem not in {"ext4", "xfs", "btrfs"}:
        raise ValueError(f"Native Docker storage requires ext4, xfs or btrfs; observed {filesystem}: {path}")
    return {"filesystem": filesystem, "device": path.stat().st_dev}


def read_owned_regular(path, maximum=1024 * 1024):
    path = storage.absolute(path, "owned file")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError("Owned evidence is not a bounded regular file")
        data = stream.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError("Owned evidence exceeded the read limit")
        return data
