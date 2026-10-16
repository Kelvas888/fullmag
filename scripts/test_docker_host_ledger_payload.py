#!/usr/bin/env python3
"""Focused regression for host-ledger owner-marker publication bytes."""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


HELPER = Path(__file__).with_name("lib") / "docker_host_ledger.sh"


def _inline_python_snippets() -> list[str]:
    source = HELPER.read_text(encoding="utf-8")
    marker = "python3 -c '"
    snippets = re.findall(r"python3 -c '([^']*)'", source, flags=re.DOTALL)
    if len(snippets) != source.count(marker):
        raise AssertionError("could not extract every inline python3 -c snippet")
    if len(snippets) < 7:
        raise AssertionError(f"unexpectedly few inline python snippets: {len(snippets)}")
    return snippets


def _assert_inline_python_parses() -> None:
    for index, snippet in enumerate(_inline_python_snippets(), start=1):
        try:
            ast.parse(snippet, filename=f"docker_host_ledger.sh:inline-python-{index}")
        except SyntaxError as error:
            raise AssertionError(f"inline Python snippet {index} does not parse: {error}") from error


def _shell_function(source: str, name: str, next_name: str) -> str:
    start = source.index(f"{name}() {{")
    end = source.index(f"\n{next_name}() {{", start)
    return source[start:end]


def _run_mount_receipt_probe() -> None:
    source = HELPER.read_text(encoding="utf-8")
    read_mount_state = _shell_function(source, "read_mount_state", "verify_image_file")
    emit_receipt = _shell_function(source, "emit_receipt", "cleanup")
    probe = textwrap.dedent(
        f"""
        set -Eeuo pipefail
        host() {{
            [[ "$1" == "findmnt" ]] || {{ echo "unexpected host command: $*" >&2; return 99; }}
            printf '%s\\n' '/dev/loop5 ext4 11111111-1111-1111-1111-111111111111'
        }}
        MOUNT_ROOT='/mnt/fullmag-host-ledger-fullmag-test'
        MOUNT_ACTIVE=0
        MOUNT_SOURCE=''
        LOOP_DEVICE=''
        FILESYSTEM_UUID=''
        MOUNT_TARGET='/host-ledger'
        IMAGE_SIZE_BYTES=134217728
        PROFILE='host-ledger-v1'
        PROJECT_ID='fullmag-test'
        BACKING_IMAGE='/storage/build-volumes/fullmag-host-ledger-v1.ext4'
        {read_mount_state}
        {emit_receipt}
        read_mount_state
        emit_receipt validated 0
        """
    )
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "host-ledger-loop-receipt-probe.sh"
        script.write_text(probe, encoding="utf-8")
        result = subprocess.run(
            ["bash", str(script)], check=True, text=True, capture_output=True
        )
    receipt = json.loads(result.stdout)
    if receipt.get("loop_device") != "/dev/loop5":
        raise AssertionError(f"receipt lost the full loop device path: {receipt!r}")
    if receipt.get("mount_active") is not True or receipt.get("state") != "validated":
        raise AssertionError(f"mount-state probe did not produce a validated receipt: {receipt!r}")


def _run_recovery_probe(root: Path, expected_success: bool) -> None:
    source = HELPER.read_text(encoding="utf-8")
    inspect_recovery_mount_root = _shell_function(
        source, "inspect_recovery_mount_root", "admit_existing_mount"
    )
    probe = textwrap.dedent(
        f"""
        set -Eeuo pipefail
        fail() {{ echo "$*" >&2; exit 2; }}
        host() {{ "$@"; }}
        MOUNT_ROOT="$1"
        LEDGER_CHILD_NAME='ledger'
        LEDGER_ROOT="$MOUNT_ROOT/ledger"
        {inspect_recovery_mount_root}
        inspect_recovery_mount_root
        """
    )
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "host-ledger-recovery-probe.sh"
        script.write_text(probe, encoding="utf-8")
        result = subprocess.run(
            ["bash", str(script), str(root)], text=True, capture_output=True
        )
    actual_success = result.returncode == 0
    if actual_success != expected_success:
        raise AssertionError(
            f"recovery probe result mismatch for {root!r}: "
            f"expected success={expected_success}, returncode={result.returncode}, "
            f"stderr={result.stderr!r}"
        )


def _assert_recovery_mount_guards() -> None:
    with tempfile.TemporaryDirectory() as directory:
        parent = Path(directory)

        empty = parent / "empty"
        (empty / "lost+found").mkdir(parents=True)
        (empty / "ledger").mkdir()
        _run_recovery_probe(empty, True)

        unexpected = parent / "unexpected"
        (unexpected / "lost+found").mkdir(parents=True)
        (unexpected / "ledger").mkdir()
        (unexpected / "extra").touch()
        _run_recovery_probe(unexpected, False)

        newline_name = parent / "newline"
        (newline_name / "lost+found").mkdir(parents=True)
        (newline_name / "ledger").mkdir()
        (newline_name / "unexpected\nentry").touch()
        _run_recovery_probe(newline_name, False)

        real_root = parent / "real-root"
        (real_root / "lost+found").mkdir(parents=True)
        (real_root / "ledger").mkdir()
        root_symlink = parent / "root-symlink"
        root_symlink.symlink_to(real_root, target_is_directory=True)
        _run_recovery_probe(root_symlink, False)

        nonempty_child = parent / "nonempty-child"
        (nonempty_child / "lost+found").mkdir(parents=True)
        (nonempty_child / "ledger").mkdir()
        (nonempty_child / "ledger" / "data\nentry").touch()
        _run_recovery_probe(nonempty_child, False)


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
    _assert_inline_python_parses()
    _run_mount_receipt_probe()
    _assert_recovery_mount_guards()
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
