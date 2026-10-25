#!/usr/bin/env python3
"""Verify runtime-free antenna authoring through public HTTP without executing Solve."""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import io
import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


def validate(base_url: str, authored: dict) -> dict:
    def request(path, payload=None, expected=200):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(base_url.rstrip("/") + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            response = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("Response exceeded the authoring regression read budget")
            if response.code != expected:
                raise ValueError(f"{path}: expected {expected}, got {response.code}: {raw[:1000]!r}")
            return json.loads(raw)

    def current_identity():
        status = request("/v2/sessions/current/status")
        return {"session": status["session"], "run_id": status["run"]["run_id"],
                "scene_revision": status["resources"]["scene_revision"],
                "commands_revision": status["resources"]["commands_revision"]}

    scene = authored["scene_document"]
    if not scene["objects"] or any(obj["role"] == "magnet" for obj in scene["objects"]):
        raise ValueError("Regression requires a nonmagnetic antenna scene")
    if not scene.get("antenna_field_solve_stages"):
        raise ValueError("Regression requires an authored antenna field solve stage")
    before = current_identity()
    updated = request("/v2/persistence/projects/authoring", authored)
    raw = base64.b64decode(updated["archive_base64"], validate=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read("manifest/project.json"))
        source_path = manifest.get("source")
        if not isinstance(source_path, str) or not source_path:
            raise ValueError("Nonmagnetic antenna archive has no canonical Python source")
        info = archive.getinfo(source_path)
        if info.file_size <= 0 or info.file_size > 1024 * 1024:
            raise ValueError("Canonical source has an invalid size")
        source = archive.read(info)
        ast.parse(source.decode("utf-8"))
        saved_scene = json.loads(archive.read(manifest["scene"]))
        if saved_scene != scene:
            raise ValueError("Authoring changed the supplied scene semantics")
    reopened = request("/v2/persistence/projects/open", {
        "display_name": authored["display_name"], "archive_base64": updated["archive_base64"]})
    if reopened["project_id"] != updated["project_id"] or reopened["revision"] != updated["revision"]:
        raise ValueError("Cold open changed the project identity or revision")
    if reopened.get("authoring_scene_document") != scene:
        raise ValueError("Cold open did not preserve the authored scene")
    project_id = authored["expected_project_id"]
    foreign_id = project_id[:-1] + ("0" if project_id[-1] != "0" else "1")
    for key, value in (("expected_project_id", foreign_id),
                       ("expected_revision", int(authored["expected_revision"]) + 1)):
        request("/v2/persistence/projects/authoring", {**authored, key: value}, expected=409)
    if current_identity() != before:
        raise ValueError("Runtime-free authoring changed the active session, scene or commands")
    return {"status": "pass", "project_id": updated["project_id"],
            "revision": updated["revision"], "source_path": source_path,
            "source_bytes": len(source), "source_sha256": hashlib.sha256(source).hexdigest(),
            "archive_sha256": hashlib.sha256(raw).hexdigest(), "cold_open": True,
            "foreign_identity_rejected": True, "stale_revision_rejected": True,
            "active_session_unchanged": True, "new_solve": False,
            "scope": "Publiczny zapis i cold-open projektu bez magnetyka; nie wykonanie ani kwalifikacja fizyki."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--request-file", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.resolve() in (args.request_file.resolve(), Path(__file__).resolve()):
        parser.error("report must not overwrite the request or validator")
    authored = json.loads(args.request_file.read_text())
    try:
        result = validate(args.base_url, authored)
    except Exception as error:
        args.report.write_text(json.dumps({"status": "fail", "error": str(error)}, indent=2) + "\n")
        raise
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
