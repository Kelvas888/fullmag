#!/usr/bin/env python3
"""Validate bounded C04 measurements from a real verbose CTest log.

Complete phase coverage is diagnostic evidence only. The current native schema
has no object/copy-origin binding: pairing and scientific qualification remain
NOT VERIFIED, including when the measurement parser exits successfully.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

PREFIX = "FULLMAG_FLOQUET_FACTOR_MATRIX_SNAPSHOT "
SCHEMA = "fullmag.floquet-factor-matrix-snapshot.v1"
PHASES = (
    "A_shifted_pmat_before_live_setup",
    "B_live_pc_pmat_before_duplicate",
    "C_owned_copy_before_fresh_setup",
)
MAX_LINE_BYTES = 9216
MAX_RECORDS = 2048
REQUIRED_TESTS = ("fem_modal_eigen_contract", "fem_modal_eigen_mixed_dense_contract")


def validate_snapshot(record: object) -> list[str]:
    """Require actual measured values, not unavailable/not-applicable markers."""
    if not isinstance(record, dict):
        return ["snapshot root is not an object"]
    errors = []
    if record.get("schema") != SCHEMA or record.get("phase") not in PHASES:
        errors.append("unsupported snapshot schema or phase")
    if record.get("status") != "measured" or record.get("applicable_n4") is not True:
        errors.append("snapshot is not a measured applicable 4x4 matrix")
    if record.get("truncated") is not False:
        errors.append("snapshot is truncated or has no truncation declaration")
    for key in ("size_available", "type_available", "getters_attempted", "values_attempted",
                "values_available", "missing_diagonal_available", "nonzero_state_available"):
        if record.get(key) is not True:
            errors.append(f"{key} is not true")
    for key in ("size", "type", "ownership", "values", "diagonal", "nonzero_state"):
        if record.get(key + "_error_available") is not True or type(record.get(key + "_error")) is not int \
                or record[key + "_error"] != 0:
            errors.append(f"{key} getter has missing/error evidence")
    for key in ("rows", "columns"):
        if type(record.get(key)) is not int or record[key] != 4:
            errors.append(f"{key} is not four")
    if not isinstance(record.get("type"), str) or not record["type"]:
        errors.append("matrix type is missing")
    if type(record.get("nonzero_state")) is not int or record["nonzero_state"] < 0 \
            or record.get("nonzero_state_scope") != "same_matrix_only":
        errors.append("nonzero state or its comparison scope is invalid")
    missing = record.get("missing_diagonal")
    first = record.get("first_missing_diagonal")
    if type(missing) is not bool or (missing and (type(first) is not int or not 0 <= first < 4)) \
            or (missing is False and first is not None):
        errors.append("missing-diagonal evidence is invalid")
    byte_count = record.get("real_byte_count")
    if type(byte_count) is not int or byte_count not in (4, 8, 16) \
            or record.get("raw_encoding") != "native_memory_order_hex":
        errors.append("raw scalar representation is invalid")
    entries = record.get("entries")
    if not isinstance(entries, list) or len(entries) != 16:
        return errors + ["snapshot requires exactly sixteen entries"]
    positions = set()
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("entry is not an object")
            continue
        row, column = entry.get("row"), entry.get("column")
        if type(row) is not int or type(column) is not int or not 0 <= row < 4 or not 0 <= column < 4:
            errors.append("entry coordinates are invalid")
            continue
        if (row, column) in positions:
            errors.append("duplicate entry coordinates")
        positions.add((row, column))
        if entry.get("diagonal") is not (row == column):
            errors.append("entry diagonal flag contradicts coordinates")
        for part in ("real", "imaginary"):
            value = entry.get(part)
            if entry.get(part + "_finite") is not True or type(value) not in (int, float):
                errors.append(f"entry {part} is unavailable/nonfinite")
            else:
                try:
                    if not math.isfinite(float(value)):
                        errors.append(f"entry {part} is nonfinite")
                except (OverflowError, ValueError):
                    errors.append(f"entry {part} cannot be represented")
            raw = entry.get(part + "_raw_hex")
            if type(byte_count) is not int or not isinstance(raw, str) \
                    or len(raw) != 2 * byte_count or re.fullmatch("[0-9a-f]+", raw) is None:
                errors.append(f"entry {part} raw bytes are invalid")
    if positions != {(row, column) for row in range(4) for column in range(4)}:
        errors.append("entry coverage is incomplete")
    return errors


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("nonfinite JSON number")
    return parsed


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"nonstandard JSON constant {value}")

def parse_log(path: Path, required_tests: tuple[str, ...] = REQUIRED_TESTS) -> dict:
    names = {}
    records = []
    unscoped_markers = 0
    other_test_markers = 0
    errors = []
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for line_number, raw in enumerate(stream, 1):
                digest.update(raw)
                line = raw.decode("utf-8", errors="replace")
                start = re.search(r"Start\s+(\d+):\s+(\S+)", line)
                if start:
                    names[int(start[1])] = start[2]
                offset = line.find(PREFIX)
                if offset < 0:
                    continue
                context = re.search(r"(?:^|\s)(\d+):\s*$", line[:offset])
                if context is None:
                    # CTest may repeat failed-test stderr without the verbose
                    # test-ID prefix. Never assign those repeats to an attempt.
                    unscoped_markers += 1
                    continue
                if names.get(int(context[1])) not in required_tests:
                    other_test_markers += 1
                    continue
                if len(raw) > MAX_LINE_BYTES or len(records) >= MAX_RECORDS:
                    errors.append(f"line {line_number}: diagnostic bound exceeded")
                    continue
                try:
                    record = json.loads(line[offset + len(PREFIX):], parse_float=_finite_json_float,
                                        parse_constant=_reject_json_constant)
                except (ValueError, TypeError) as error:
                    errors.append(f"line {line_number}: invalid snapshot JSON: {error}")
                    continue
                records.append({"line": line_number, "ctest_id": int(context[1]), "snapshot": record})
        log_hash = digest.hexdigest()
    except OSError as error:
        errors.append(f"cannot read native log: {error}")
        log_hash = None
    coverage = {}
    for name in required_tests:
        selected = [item for item in records if names.get(item["ctest_id"]) == name]
        measured = {phase: [] for phase in PHASES}
        rejected = []
        for item in selected:
            problems = validate_snapshot(item["snapshot"])
            if problems:
                rejected.append({"line": item["line"], "reasons": problems})
            else:
                measured[item["snapshot"]["phase"]].append(item)
        missing = [phase for phase, items in measured.items() if not items]
        if missing:
            errors.append(f"{name}: no valid measurement for {','.join(missing)}")
        if rejected:
            errors.append(f"{name}: {len(rejected)} invalid/unavailable snapshots")
        coverage[name] = {"measurement_status": "complete" if not missing and not rejected else "incomplete",
                          "valid_counts_by_phase": {phase: len(items) for phase, items in measured.items()},
                          "rejected": rejected}
    return {
        "schema": "fullmag.ci.floquet-factor-matrix-snapshot-report.v1",
        "status": "failed" if errors else "measured_unpaired",
        "measurement_status": "incomplete" if errors else "complete",
        "pairing_status": "NOT VERIFIED",
        "pairing_reason": "native snapshots lack object IDs and explicit copy-origin/attempt binding; phase coverage cannot pair matrices",
        "scientific_qualification": "NOT VERIFIED",
        "ctest_result_modified": False,
        "log_path": str(path), "log_sha256": log_hash,
        "required_tests": list(required_tests), "coverage": coverage,
        "records": records, "reasons": errors,
        "unscoped_markers_not_used_for_coverage": unscoped_markers,
        "other_test_markers_not_used_for_coverage": other_test_markers,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = parse_log(args.log)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(f"C04 measurements: {report['measurement_status']}; pairing: NOT VERIFIED; {args.output}")
    return 0 if report["measurement_status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
