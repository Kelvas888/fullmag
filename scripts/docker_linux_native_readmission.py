"""Prepare one stopped Linux DEV group's device evidence; never admit or start it."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import uuid

from docker_build_control import BuildControl, BuildControlError, canonical, docker_capture
from docker_volume_reconcile import SHA, TOKEN, digest, fingerprint, read_raw, require, write_immutable
import linux_native_host as host

SCHEMA = "fullmag.docker-linux-device-readmission.v1"
CONTROLLERS = ("docker_linux_native_readmission.py", "linux_native_host.py",
               "docker_build_control.py", "docker_volume_container_recovery.py",
               "docker_volume_stop_unadmitted.py", "docker_volume_reconcile.py")
NATIVE_PINS = ("runtime-control/runtime-services/OWNER.json",
               "runtime-control/runtime-services/LAUNCH.json",
               "runtime-control/runtime-service/process-tree.json")


def validate_request(r):
    fields = {"schema", "source_revision", "controller_inputs", "boot_id", "engine_id",
              "compose_path", "compose_sha256", "failed_resume_path", "failed_resume_sha256",
              "containers", "native_pins", "storage_pins"}
    require(isinstance(r, dict) and set(r) == fields and r["schema"] == SCHEMA,
            "Exact Linux readmission request required")
    require(isinstance(r["source_revision"], str)
            and re.fullmatch(r"[0-9a-f]{40}", r["source_revision"]), "Invalid source revision")
    require(isinstance(r["boot_id"], str)
            and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", r["boot_id"]),
            "Exact current boot identity required")
    require(isinstance(r["engine_id"], str) and 0 < len(r["engine_id"]) <= 256,
            "Exact Docker engine identity required")
    for name, pattern in (("compose_path", r"development/attempts/[0-9a-f]{32}/compose.json"),
                          ("failed_resume_path", r"resume/attempts/[0-9a-f]{32}/terminal.json")):
        require(isinstance(r[name], str) and re.fullmatch(pattern, r[name]), "Invalid " + name)
    for name in ("compose_sha256", "failed_resume_sha256"):
        require(isinstance(r[name], str) and SHA.fullmatch(r[name]), "Invalid " + name)
    for name, keys in (("controller_inputs", CONTROLLERS), ("native_pins", NATIVE_PINS)):
        require(isinstance(r[name], dict) and set(r[name]) == set(keys)
                and all(isinstance(v, str) and SHA.fullmatch(v) for v in r[name].values()),
                "Incomplete " + name)
    require(isinstance(r["containers"], dict) and set(r["containers"]) == {"backend", "frontend"},
            "Both stopped service pins required")
    for pin in r["containers"].values():
        require(isinstance(pin, dict) and set(pin) == {"id", "fingerprint", "state"}
                and all(isinstance(pin[k], str) and SHA.fullmatch(pin[k]) for k in ("id", "fingerprint"))
                and isinstance(pin["state"], dict) and pin["state"].get("Status") == "exited"
                and pin["state"].get("Running") is False and pin["state"].get("Pid") == 0
                and pin["state"].get("OOMKilled") is False, "Exact stopped service state required")
    require(len({pin["id"] for pin in r["containers"].values()}) == 2, "Services must be distinct")
    require(isinstance(r["storage_pins"], dict)
            and r["storage_pins"].get("engine_id") == r["engine_id"], "Storage engine pin differs")


def archive_preparation(p):
    result = dict(p)
    result["original"] = {k: base64.b64encode(v).decode("ascii") for k, v in p["original"].items()}
    result["candidate_raw"] = base64.b64encode(p["candidate_raw"]).decode("ascii")
    return result


def restore_preparation(p):
    result = dict(p)
    result["original"] = {k: base64.b64decode(v, validate=True) for k, v in p["original"].items()}
    result["candidate_raw"] = base64.b64decode(p["candidate_raw"], validate=True)
    return result


def observe(control, source, layout, r, allowed_helpers=()):
    from docker_dev import storage
    require(not control.namespace, "Namespaced controls need their own recovery")
    require(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == r["boot_id"], "Host rebooted")
    require(docker_capture("info", "--format", "{{.ID}}").stdout.decode().strip() == r["engine_id"],
            "Docker engine changed")
    revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], check=True,
                              stdout=subprocess.PIPE).stdout.decode().strip()
    require(revision == r["source_revision"], "Source revision changed")
    for name, sha in r["controller_inputs"].items():
        require(digest((source / "scripts" / name).read_bytes()) == sha, "Controller changed: " + name)
    compose_raw = read_raw(control, r["compose_path"])
    terminal_raw = read_raw(control, r["failed_resume_path"])
    require(digest(compose_raw) == r["compose_sha256"]
            and digest(terminal_raw) == r["failed_resume_sha256"], "Retained authority changed")
    compose, terminal = json.loads(compose_raw), json.loads(terminal_raw)
    require(compose.get("name") == terminal.get("compose_project") == control.project
            and terminal.get("state") == "failed-confirmed", "Interrupted resume is not closed")
    state = storage.validate_path(Path(r["storage_pins"]["state_root"]),
                                  Path(layout["runtime_root"]), "retained Linux state")
    ids = docker_capture("ps", "--all", "--no-trunc", "--filter",
                         "label=com.docker.compose.project=" + control.project,
                         "--format", "{{.ID}}").stdout.decode().split()
    actuals = json.loads(docker_capture("inspect", *ids).stdout) if ids else []
    services = {}
    for actual in actuals:
        if actual.get("Name", "").lstrip("/") in allowed_helpers:
            continue
        name = actual.get("Config", {}).get("Labels", {}).get("com.docker.compose.service")
        require(name in r["containers"] and name not in services, "Unexpected group resource")
        pin = r["containers"][name]
        require(actual["Id"] == pin["id"] and fingerprint(actual) == pin["fingerprint"]
                and actual["State"] == pin["state"], "Stopped service incarnation changed: " + name)
        services[name] = actual
    require(set(services) == {"backend", "frontend"}, "Stopped service inventory differs")
    backend = services["backend"]
    mounts = {m["Destination"]: m for m in backend["Mounts"]}
    require(mounts.get("/state", {}).get("Source") == str(state)
            and mounts["/state"].get("Type") == "bind"
            and mounts.get("/opt/fullmag/source", {}).get("Source") == str(source)
            and mounts["/opt/fullmag/source"].get("RW") is False
            and backend["Image"] == r["storage_pins"].get("image_id"), "Retained source/storage image differs")
    from docker_volume_stop_unadmitted import _runtime_control_volume_mount
    volume, _ = _runtime_control_volume_mount(backend, control.project)
    require(volume == control.volume, "Native control volume differs")
    protected = {m.get("Name") for a in services.values() for m in a["Mounts"] if m.get("Name")}
    running = docker_capture("ps", "--no-trunc", "--format", "{{.ID}}").stdout.decode().split()
    for actual in (json.loads(docker_capture("inspect", *running).stdout) if running else []):
        if actual.get("Name", "").lstrip("/") in allowed_helpers:
            continue
        for mount in actual.get("Mounts", []):
            source_path = mount.get("Source", "")
            overlap = (source_path and source_path.startswith("/")
                       and (Path(source_path) == state or Path(source_path) in state.parents
                            or state in Path(source_path).parents))
            require(not (mount.get("Name") in protected or overlap), "A live container consumes retained data")
    return state, compose, backend


# Locks are shared Linux inodes, opened readonly. No namespace admission or data
# publication occurs in this helper. EOF aborts it and releases every guard.
GUARD = r"""
import fcntl, hashlib, json, os, pathlib, stat, sys
P=pathlib.Path
payload=json.loads(sys.stdin.buffer.readline(1024*1024))
locks=[]
def metadata(path):
    before=path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1: raise RuntimeError('unsafe retained file')
    return before
for path in [P('/control/operation.lock'),*[P('/control/runtime-control/runtime-services')/n for n in ('STARTUP-GATE.lock','LAUNCH.lock','OWNER.lock')],P('/host-ledger/ledger/WRITER.lock'),P('/retained/WRITER.lock')]:
    before=metadata(path); fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    opened=os.fstat(fd); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    after=metadata(path)
    if (before.st_dev,before.st_ino)!=(opened.st_dev,opened.st_ino) or (after.st_dev,after.st_ino)!=(opened.st_dev,opened.st_ino): raise RuntimeError('lock inode changed')
    locks.append(fd)
def file_hash(path):
    before=metadata(path)
    if before.st_size>2*1024**3: raise RuntimeError('retained file exceeds budget')
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    after=metadata(path)
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns): raise RuntimeError('retained file changed while hashing')
    return h.hexdigest(),before.st_size

def snapshot():
    if P('/control/active').exists() or P('/control/active').is_symlink(): raise RuntimeError('another operation is active')
    for relative,sha in payload['control_pins'].items():
        if file_hash(P('/control')/relative)[0]!=sha: raise RuntimeError('pinned native/control document changed')
    ledger=P('/host-ledger/ledger/HOST_RESOURCE_LEDGER.json')
    if metadata(ledger).st_size>8*1024**2: raise RuntimeError('ledger is unbounded')
    document=json.loads(ledger.read_bytes()); reservations=document.get('reservations')
    if isinstance(reservations,dict): reservations=list(reservations.values())
    if not isinstance(reservations,list) or any(not isinstance(v,dict) or v.get('state')!='released' for v in reservations): raise RuntimeError('active or unknown reservation')
    rows={}; total=0
    def walk_error(error): raise error
    for parent,dirs,files in os.walk('/retained',followlinks=False,onerror=walk_error):
        if any(P(parent,n).is_symlink() for n in dirs): raise RuntimeError('linked retained directory')
        for name in files:
            path=P(parent,name); sha,size=file_hash(path); total+=size
            rows[path.relative_to('/retained').as_posix()]=[sha,size]
            if len(rows)>50000 or total>2*1024**3: raise RuntimeError('retained inventory exceeds budget')
    raw=json.dumps(rows,sort_keys=True,separators=(',',':')).encode()
    return {'store_sha256':hashlib.sha256(raw).hexdigest(),'file_count':len(rows),'total_bytes':total,'ledger_sha256':file_hash(ledger)[0]}
before=snapshot(); print(json.dumps({'state':'locked','snapshot':before}),flush=True)
if sys.stdin.buffer.readline(16)!=b'CHECK\n': raise RuntimeError('host did not request verification')
if snapshot()!=before: raise RuntimeError('retained state changed during readmission')
print(json.dumps({'state':'preserved','snapshot':before}),flush=True)
if sys.stdin.buffer.readline(16)!=b'RELEASE\n': raise RuntimeError('host did not confirm terminal receipt')
"""


def run(args):
    from docker_dev import _select_source, _compose_identity
    from docker_volume_container_recovery import _ledger_snapshot_mount
    from docker_volume_toolchain_reconcile import host_clients
    root = Path(args.source_root).resolve(strict=True)
    source, layout = _select_source(root, str(root))
    identity = _compose_identity(layout)
    # Resolve the control volume using an already-retained immutable image.
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", args.image_id), "Immutable retained image required")
    control = BuildControl(identity, args.image_id)
    request_raw = read_raw(control, args.request)
    require(digest(request_raw) == args.request_sha256, "Request CAS differs")
    r = json.loads(request_raw); validate_request(r)
    require(args.image_id == r["storage_pins"].get("image_id"), "Helper image differs from retained backend")
    host_clients(source)
    state, compose, backend = observe(control, source, layout, r)
    ledger_mount, _ = _ledger_snapshot_mount(control, backend, compose)
    store = state / "runs/docker-all/session-store"
    require(store.is_dir() and not store.is_symlink(), "Retained accepted store absent")
    name = "fullmag-storage-readmission-" + uuid.uuid4().hex
    command = control.helper_args("exec python3 -I -B -c " + shlex.quote(GUARD), name=name)
    i = command.index("--entrypoint")
    command[i:i] = ["--mount", ledger_mount,
                   "--mount", "type=bind,src=" + str(store) + ",dst=/retained,readonly"]
    pins = dict(r["native_pins"], **{r["compose_path"]: r["compose_sha256"],
                                      r["failed_resume_path"]: r["failed_resume_sha256"],
                                      args.request: args.request_sha256})
    base = "verification/linux-native-readmission/" + args.request_sha256
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        process.stdin.write(canonical({"control_pins": pins}) + b"\n"); process.stdin.flush()
        ready = json.loads(control._line(process))
        require(ready.get("state") == "locked", "Readmission guards were not acquired")
        observe(control, source, layout, r, (name,))
        saved = read_raw(control, base + "/preparation.json", optional=True)
        preparation = (restore_preparation(json.loads(saved)) if saved is not None
                       else host.prepare_device_readmission(state, r["storage_pins"]))
        require(preparation["pins"] == r["storage_pins"], "Archived preparation pins differ")
        host._readmission_phase(state, preparation)
        archived = archive_preparation(preparation)
        write_immutable(control, base + "/preparation.json", canonical(archived) + b"\n")
        require(restore_preparation(json.loads(read_raw(control, base + "/preparation.json"))) == preparation,
                "Archived preparation readback differs")
        if args.apply:
            require(process.poll() is None, "Readmission guard exited before host publication")
            observe(control, source, layout, r, (name,))
            result = host.apply_device_readmission(state, preparation)
        else:
            result = {"state": "validated-only", "namespace_admitted": False}
        require(process.poll() is None, "Readmission guard exited during host publication")
        process.stdin.write(b"CHECK\n"); process.stdin.flush()
        after = json.loads(control._line(process))
        require(after.get("state") == "preserved" and after.get("snapshot") == ready["snapshot"],
                "Protected data preservation not proven")
        observe(control, source, layout, r, (name,))
        receipt = {"schema": SCHEMA, "request_sha256": args.request_sha256,
                   "candidate_sha256": preparation["candidate_sha256"],
                   "snapshot": ready["snapshot"], "services_started": False, "solve_replayed": False,
                   "state": result["state"], "namespace_admitted": False}
        write_immutable(control, base + ("/terminal.json" if args.apply else "/preview.json"), canonical(receipt) + b"\n")
        process.stdin.write(b"RELEASE\n"); process.stdin.flush(); process.stdin.close()
        require(process.wait(timeout=30) == 0, "Readmission helper completion unproven")
        print(json.dumps(receipt, sort_keys=True))
    finally:
        if process.stdin and not process.stdin.closed: process.stdin.close()
        if process.poll() is None:
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: pass
        if process.poll() is not None:
            diagnostic = process.stderr.read(8192).decode("utf-8", "replace")
            if diagnostic: print(diagnostic, file=__import__('sys').stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", required=True)
    p.add_argument("--request", required=True)
    p.add_argument("--request-sha256", required=True)
    p.add_argument("--image-id", required=True)
    p.add_argument("--apply", action="store_true")
    run(p.parse_args())


if __name__ == "__main__":
    main()
