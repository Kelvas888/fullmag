"""Build only the owned ring QA session's mesh through the typed v2 client.

Run inside the selected Compose group, with its fullmag Python package on
PYTHONPATH. The receipt must be in that group's Docker volume. No Solve.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from fullmag.client import Client

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--session-id", required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
if args.output.exists():
    raise RuntimeError("A receipt already exists; inspect the accepted command instead of replaying it")
args.output.parent.mkdir(parents=True, exist_ok=True)
record = {"schema": "fullmag.viewport-ring-mesh-qa.v1", "state": "preflight"}


def save() -> None:
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


with Client("http://backend:8081", timeout=30) as client:
    before = client.sessions.status()
    identity_keys = ("session_id", "session_epoch", "request_scope_epoch")
    identity = {key: before["session"][key] for key in identity_keys}
    if identity["session_id"] != args.session_id:
        raise RuntimeError("Current session differs from the explicitly pinned QA session")
    client.session_scope = urlencode({"session": identity["session_id"],
        "epoch": identity["session_epoch"], "request_scope_epoch": identity["request_scope_epoch"]})
    scene = client.model.scene()
    if (scene.get("scene", {}).get("name") != "permalloy_layer_cofeb_rings_relax_300nm"
            or sorted(obj.get("name", "") for obj in scene["objects"])
            != ["cofeb_top_ring", "permalloy_layer"]):
        raise RuntimeError("Current model is not the expected two-object ring fixture")
    if before["domain"]["cell_count"] != 0:
        raise RuntimeError("Primitive-stage precondition failed: this session already has a mesh")
    record.update(session=identity, scene_revision=scene["revision"], before_domain=before["domain"],
        before_resources=before["resources"], client_intent_id="viewport-depth-mesh-" +
        hashlib.sha256(client.session_scope.encode()).hexdigest()[:24], state="submitting")
    save()
    try:
        handle = client.commands.submit("mesh_build", client_intent_id=record["client_intent_id"],
            reason="viewport_depth_qa", mesh_reason="shared-domain", mesh_target={"kind": "study_domain"})
        record.update(state="accepted", command_id=handle.command_id)
        save()
        terminal = handle.wait(timeout=600)
        record.update(state="terminal", terminal=terminal)
        save()
        after = client.sessions.status()
        after_identity = {key: after["session"][key] for key in identity_keys}
        if after_identity != identity or after["domain"]["cell_count"] <= 0:
            raise RuntimeError("Mesh completion did not publish a non-empty domain in the pinned session")
        if after["resources"].get("mesh_build_revision", 0) <= before["resources"].get("mesh_build_revision", 0):
            raise RuntimeError("Mesh command did not advance its owning resource revision")
        record.update(state="passed", after_domain=after["domain"], after_resources=after["resources"],
            requested_execution=terminal.get("requested_execution"), resolved_execution=terminal.get("resolved_execution"))
        save()
        print(json.dumps({key: record[key] for key in ("state", "command_id", "after_domain")}))
    except BaseException as error:
        record.update(state="failed-or-outcome-unknown", error=str(error))
        save()
        raise
