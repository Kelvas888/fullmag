#!/usr/bin/env python3
"""Read-only display HTTP checks, not solver or scientific qualification.

Bundle framing comparison is independently bounded to the fixture decoder's
2 MiB limit. Native integrity validation remains authoritative.
"""
import argparse
from hashlib import sha256
import json
import struct
from urllib.parse import quote, urlencode

import antenna_rt0_fixture_check as framing
from smoke_antenna_external_lead_inspection import (
    MAX_BINARY_BYTES, MAX_METADATA_BYTES, json_body, request, require,
    session_scope, strong_etag, validate_resource,
)


def verify(origin, stage_id):
    path = f"/v2/sessions/current/data/antenna/stages/{quote(stage_id, safe='')}/external-lead-inspection"
    resource = json_body(request(origin, path, {}, MAX_METADATA_BYTES), 200)
    _, digest = validate_resource(resource, stage_id)
    headers = {"x-fullmag-session-scope": session_scope(resource, resource["request_scope_epoch"])}
    query = urlencode({"content_digest": digest})
    response = request(origin, f"{path}/display?{query}", headers, MAX_METADATA_BYTES)
    display = json_body(response, 200)
    for key, value in {
        "schema_version": "antenna_inspection_display.v1", "status": "inspection_only",
        "qualification": "NOT VERIFIED", "field_scope": "external_electrode_truncation",
        "normalization": "raw_authored_current", "content_digest": digest,
        "runtime_stage_id": stage_id, "record_content_digest": resource["record_content_digest"],
    }.items():
        require(display.get(key) == value, f"display {key} mismatch")
    for key in ("session_id", "session_epoch", "request_scope_epoch", "run_id", "stage_revision"):
        require(display.get(key) == resource[key], f"display owner {key} mismatch")
    require(display.get("capabilities") == {"display": True, "per_ampere_basis": False,
        "source_fft": False, "llg_drive": False, "current_density": False}, "display capability promotion")
    etag = strong_etag(response)
    cached = request(origin, f"{path}/display?{query}", {**headers, "If-None-Match": etag}, MAX_METADATA_BYTES)
    require(cached.status == 304 and not cached.body, "display conditional response mismatch")
    payloads = {}
    specs = {
        "device_positions": ("float64_le", "node_xyz_interleaved", "m", 8),
        "device_topology": ("uint32_le", "tet4_connectivity", "1", 4),
        "device_potential": ("float64_le", "authored_device_vertex_order", "V", 8),
        "sample_positions": ("float64_le", "sample_xyz_interleaved", "m", 8),
        "magnetic_field": ("float64_le", "sample_xyz_interleaved", "A/m", 8),
    }
    for kind, (scalar, layout, unit, width) in specs.items():
        desc = display[kind]
        require((desc["scalar_type"], desc["layout"], desc["unit"]) == (scalar, layout, unit), f"{kind} metadata mismatch")
        require(type(desc["value_count"]) is int and 0 < desc["value_count"]
                and desc["byte_count"] == desc["value_count"] * width <= MAX_BINARY_BYTES, f"{kind} shape mismatch")
        binary_path = f"{path}/payloads/{kind}?{query}"
        result = request(origin, binary_path, headers, desc["byte_count"])
        require(result.status == 200 and len(result.body) == desc["byte_count"]
                and sha256(result.body).hexdigest() == desc["sha256"], f"{kind} integrity mismatch")
        binary_etag = strong_etag(result)
        ranged = request(origin, binary_path, {**headers, "Range": f"bytes=0-{width - 1}"}, width)
        require(ranged.status == 206 and ranged.body == result.body[:width], f"{kind} range mismatch")
        cached = request(origin, binary_path, {**headers, "If-None-Match": binary_etag}, desc["byte_count"])
        require(cached.status == 304 and not cached.body, f"{kind} conditional mismatch")
        payloads[kind] = result.body
    node_count, cell_count = display["device_node_count"], display["device_cell_count"]
    require(display["device_positions"]["value_count"] == node_count * 3
            and display["device_potential"]["value_count"] == node_count
            and display["device_topology"]["value_count"] == cell_count * 4, "device cardinality mismatch")
    require(display["sample_positions"]["value_count"] == display["magnetic_field"]["value_count"], "H carrier mismatch")
    ids_response = request(origin, f"{path}/payloads/device_vertex_ids?{query}", headers, node_count * 8)
    require(ids_response.status == 200 and len(ids_response.body) == node_count * 8, "device IDs unavailable")
    ids = [row[0] for row in struct.iter_unpack("<Q", ids_response.body)]
    raw = request(origin, f"{path}/payloads/bundle?{query}", headers, framing.LIMIT)
    require(raw.status == 200, "bundle unavailable for independent display comparison")
    outer = framing.fields(raw.body)
    charge = framing.fields(framing.one(outer, "charge_record", 3))
    vertices = framing.group(charge, "vertices", framing.one(charge, "vertices", 2),
        [("vertex_id", 2)] + [("xyz_m", 4)] * 3 + [("potential_v", 4), ("reaction_a", 4), ("vertex_component_id", 2)], skip=1)
    elements = framing.group(charge, "elements", framing.one(charge, "elements", 2),
        [("attribute", 2)] + [("vertex_id", 2)] * 4 + [("conductivity_spm", 4)])
    by_id = {row[0]: row for row in vertices}
    expected_xyz = b"".join(struct.pack("<d", value) for identity in ids for value in by_id[identity][1:4])
    require(expected_xyz == payloads["device_positions"], "device XYZ differs from retained ordered IDs")
    expected_v = b"".join(struct.pack("<d", by_id[identity][4]) for identity in ids)
    require(expected_v == payloads["device_potential"], "device V differs from retained ordered IDs")
    indices = {identity: index for index, identity in enumerate(ids)}
    expected_cells = []
    for row in elements:
        owned = [identity in indices for identity in row[1:5]]
        require(not any(owned) or all(owned), "mixed device/lead tetrahedron")
        if all(owned):
            expected_cells.extend(indices[identity] for identity in row[1:5])
    require(b"".join(struct.pack("<I", value) for value in expected_cells) == payloads["device_topology"], "device topology differs from retained bundle")
    wrong = urlencode({"content_digest": "sha256:" + ("0" * 64 if digest != "sha256:" + "0" * 64 else "1" * 64)})
    require(request(origin, f"{path}/display?{wrong}", headers, MAX_METADATA_BYTES).status == 409, "stale display digest accepted")
    return {"status": "passed", "qualification": "HTTP display transport only, not native scientific qualification",
            "runtime_stage_id": stage_id, "device_nodes": node_count, "device_cells": cell_count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="http://127.0.0.1:8081")
    parser.add_argument("--stage-id", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.origin, args.stage_id), indent=2))
