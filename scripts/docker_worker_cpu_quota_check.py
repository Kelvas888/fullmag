"""Run the fixed readiness migration regression in the retained backend."""
import hashlib
import json
import re
import time
import uuid

from docker_build_control import BuildControlError, canonical, docker_capture

ROOT = "verification/worker-cpu-quota"
REQUEST = ROOT + "/request.json"


def run(control, args, backend, image):
    try:
        identifier = uuid.UUID(args.request_id)
    except (ValueError, TypeError, AttributeError) as error:
        raise BuildControlError("Verification request ID must be a canonical UUID4") from error
    if str(identifier) != args.request_id or identifier.version != 4:
        raise BuildControlError("Verification request ID must be a canonical UUID4")
    if backend.get("State", {}).get("Running") is not False:
        raise BuildControlError("Verification requires the pinned backend stopped")
    container = backend["Id"]
    if re.fullmatch(r"[0-9a-f]{64}", container) is None:
        raise BuildControlError("Verification requires a full backend container ID")
    request = {"schema": "fullmag.worker-cpu-quota-check-request.v1", "request_id": args.request_id,
               "compose_project": control.project, "container_id": container, "image_id": image}
    relative = ROOT + "/" + args.request_id
    with control.operation("verification", {"attempt": args.attempt,
            "config_sha256": args.config_sha256, "request": request}) as operation:
        prior = control.read(REQUEST, optional=True)
        if prior is not None:
            old_id = prior.get("request_id", "")
            if re.fullmatch(r"[0-9a-f-]{36}", old_id) is None:
                raise BuildControlError("Previous verification request is invalid")
            prior_result = control.read(ROOT + "/" + old_id + "/result.json", optional=True)
            if (not isinstance(prior_result, dict)
                    or prior_result.get("schema") != "fullmag.worker-cpu-quota-check-result.v1"
                    or prior_result.get("request_sha256") != hashlib.sha256(canonical(prior) + b"\n").hexdigest()
                    or prior_result.get("state") not in {"succeeded", "failed"}):
                raise BuildControlError("Previous verification outcome is unknown; retain its evidence")
        if control.read(relative + "/request.json", optional=True) is not None:
            raise BuildControlError("Verification request ID was already used")
        control.write(relative + "/request.json", request)
        control.write(REQUEST, request)
        operation["receipt"].update(backend_container=container, request_path=relative + "/request.json")
        observed = json.loads(docker_capture("inspect", container).stdout)[0]
        if (observed.get("Id") != container or observed.get("Image") != image
                or observed.get("State", {}).get("Running") is not False
                or observed.get("State", {}).get("StartedAt") != backend["State"].get("StartedAt")):
            raise BuildControlError("Backend changed before scoped verification start")
        operation["daemon_pending"] = True
        docker_capture("start", container)
        deadline = time.monotonic() + 3700
        while True:
            observed = json.loads(docker_capture("inspect", container).stdout)[0]
            if observed.get("Id") != container or observed.get("Image") != image:
                raise BuildControlError("Backend identity changed during verification")
            if observed.get("State", {}).get("Running") is False:
                break
            if time.monotonic() >= deadline:
                raise BuildControlError("Verification is still running; retain backend and inspect its receipt")
            time.sleep(2)
        operation["daemon_pending"] = False
        result = control.read(relative + "/result.json")
        request_raw = canonical(request) + b"\n"
        if (result.get("schema") != "fullmag.worker-cpu-quota-check-result.v1"
                or result.get("request_sha256") != hashlib.sha256(request_raw).hexdigest()
                or result.get("container_id") != container or result.get("image_id") != image
                or result.get("state") != "succeeded" or result.get("exit_code") != 0
                or observed["State"].get("ExitCode") != 0 or observed["State"].get("OOMKilled") is not False
                or not observed["State"].get("StartedAt")
                or observed["State"]["StartedAt"] == backend["State"].get("StartedAt")):
            raise BuildControlError("Scoped verification did not succeed; retained log: " + relative + "/cargo-test.log")
        operation["receipt"].update(state="succeeded", verification=result, result_path=relative + "/result.json")
