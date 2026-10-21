"""Publish explicit CPU quota migration intent for one waiting backend gate."""
from __future__ import annotations

import hashlib
import re
import uuid

from docker_build_control import BuildControlError, docker_capture

REQUEST_RELATIVE = "runtime-control/runtime-service/worker-cpu-quota-migration.json"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_PACKAGE_RECEIPT = """import os,stat,sys
p='/opt/fullmag/package/backend-build-receipt.json'
fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
try:
 s=os.fstat(fd)
 if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>8*1024*1024:
  raise RuntimeError('invalid backend package receipt')
 with os.fdopen(fd,'rb',closefd=False) as stream: data=stream.read(8*1024*1024+1)
 if len(data)!=s.st_size: raise RuntimeError('backend package receipt changed during read')
 sys.stdout.buffer.write(data)
finally: os.close(fd)
"""


def validate_intent(request_id, expected_generation):
    try:
        identifier = uuid.UUID(request_id)
    except (ValueError, TypeError, AttributeError) as error:
        raise BuildControlError("Migration request ID must be a canonical UUID4") from error
    if str(identifier) != request_id or identifier.version != 4:
        raise BuildControlError("Migration request ID must be a canonical UUID4")
    if not isinstance(expected_generation, str) or _SHA256.fullmatch(expected_generation) is None:
        raise BuildControlError("Migration requires an exact previous readiness SHA256")
    return {"request_id": request_id, "expected_generation": expected_generation}


def publish_request(control, operation, intent, gate, backend_id, image):
    intent = validate_intent(intent.get("request_id"), intent.get("expected_generation"))
    try:
        boot = uuid.UUID(gate["boot_id"])
        valid_boot = str(boot) == gate["boot_id"] and boot.version in range(1, 6)
    except (KeyError, TypeError, AttributeError, ValueError):
        valid_boot = False
    if (gate.get("schema") != "fullmag.worker-cgroup-request.v1"
            or gate.get("compose_project") != control.project
            or gate.get("container_id") != backend_id
            or not isinstance(backend_id, str) or _SHA256.fullmatch(backend_id) is None
            or not isinstance(image, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None
            or not isinstance(gate.get("nonce"), str) or _NONCE.fullmatch(gate["nonce"]) is None
            or not valid_boot or type(gate.get("pid")) is not int or gate["pid"] < 1
            or not isinstance(gate.get("process_start_token"), str)
            or re.fullmatch(r"[0-9]+", gate["process_start_token"]) is None):
        raise BuildControlError("Migration requires the exact live backend cgroup identity")
    raw = docker_capture("exec", backend_id, "/usr/local/bin/python3", "-I", "-B", "-c", _PACKAGE_RECEIPT).stdout
    if not raw or len(raw) > 8 * 1024 * 1024:
        raise BuildControlError("Migration package receipt exceeds its bounds")
    request = {
        "schema": "fullmag.worker-cpu-quota-migration-request.v1", **intent,
        "compose_project": control.project, "container_id": backend_id, "image_id": image,
        "cgroup_nonce": gate["nonce"], "boot_id": gate["boot_id"], "pid": gate["pid"],
        "process_start_token": gate["process_start_token"],
        "package_receipt_sha256": hashlib.sha256(raw).hexdigest(),
    }
    previous = control.read(REQUEST_RELATIVE, optional=True)
    if previous is not None and previous != request:
        raise BuildControlError("Migration differs from the existing request; retain it for reconciliation")
    if previous is None:
        control.write(REQUEST_RELATIVE, request)
    operation["receipt"]["worker_cpu_quota_migration_request"] = request
    operation["receipt"]["worker_cpu_quota_migration_request_path"] = REQUEST_RELATIVE
