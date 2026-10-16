#!/usr/bin/env python3
"""Focused regression for host-ledger owner-marker publication bytes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


HELPER = Path(__file__).with_name("lib") / "docker_host_ledger.sh"


def _owner_marker_writer() -> str:
    source = HELPER.read_text(encoding="utf-8")
    function_start = source.index("write_owner_marker() {")
    command_prefix = "  python3 -c 'import os, sys\n"
    command_start = source.index(command_prefix, function_start) + len("  python3 -c '")
    command_end = source.index("\n' \"$(host_root_path", command_start)
    command = source[command_start:command_end]
    return command


def _run_writer(command: str, marker: Path, temporary: Path, payload: str) -> None:
    # The maintenance image runs as root.  The local regression remains
    # executable as an ordinary user by making only chown a no-op when needed;
    # publication and byte-level checks still execute the embedded code.
    wrapper = (
        "import os\n"
        "if not hasattr(os, 'O_NOFOLLOW'): os.O_NOFOLLOW = 0\n"
        "if getattr(os, 'geteuid', lambda: 1)() != 0: os.chown = lambda *_args: None\n"
        f"exec(compile({command!r}, '<host-ledger-owner-marker>', 'exec'))\n"
    )
    subprocess.run(
        [sys.executable, "-c", wrapper, str(marker), str(temporary), payload],
        check=True,
    )


def main() -> int:
    command = _owner_marker_writer()
    payload = json.dumps(
        {
            "schema": "fullmag.host-ledger-owner.v1",
            "profile": "host-ledger-v1",
            "project_id": "fullmag-test",
            "backing_image": "/storage/build-volumes/fullmag-host-ledger-v1.ext4",
            "mount_root": "/mnt/fullmag-host-ledger-fullmag-test",
            "filesystem_uuid": "11111111-1111-1111-1111-111111111111",
            "image_size_bytes": 134217728,
            "mount_target": "/host-ledger",
            "runtime_uid": 65532,
            "runtime_gid": 65532,
            "owner_token": "22222222-2222-2222-2222-222222222222",
        },
        separators=(",", ":"),
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        marker = root / "owner.json"
        temporary = root / "owner.json.tmp"
        _run_writer(command, marker, temporary, payload)
        raw = marker.read_bytes()
        expected = payload.encode("utf-8") + b"\n"
        if raw != expected:
            raise AssertionError(f"published marker bytes differ: {raw!r}")
        if raw.count(b"\n") != 1:
            raise AssertionError("published marker must contain exactly one trailing LF")
        if json.loads(raw.decode("utf-8")) != json.loads(payload):
            raise AssertionError("published marker is not valid JSON")
        if temporary.exists():
            raise AssertionError("temporary owner marker was not removed")
    print("host-ledger owner marker payload roundtrip: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
