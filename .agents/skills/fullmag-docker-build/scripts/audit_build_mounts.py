"""Read-only partial audit of rendered Fullmag Compose build mounts."""
import argparse
import json
from pathlib import PurePosixPath
import sys


BUILD_PATHS = {
    "backend": ("/build", "/opt/fullmag/package"),
    "frontend": ("/state/development",),
}
RUNTIME_BINDS = {"backend": {"/state", "/user-data", "/host-ledger"}, "frontend": set()}


def normalized_target(value):
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError("mount target must be an absolute container path")
    if ".." in PurePosixPath(value).parts:
        raise ValueError("mount target contains parent traversal")
    return str(PurePosixPath(value))


def covers(target, path):
    return target == path or target == "/" or path.startswith(target + "/")


def audit(document, expected_project):
    problems = []
    if not isinstance(document, dict):
        raise ValueError("Compose document must be an object")
    if document.get("name") != expected_project:
        problems.append("Compose project does not match the selected checkout")
    services = document.get("services")
    if not isinstance(services, dict):
        raise ValueError("Compose services must be an object")
    definitions = document.get("volumes") or {}
    if not isinstance(definitions, dict):
        raise ValueError("Compose volume definitions must be an object")
    sources = []
    for role, paths in BUILD_PATHS.items():
        service = services.get(role)
        if not isinstance(service, dict):
            problems.append(f"missing application service: {role}")
            continue
        if service.get("read_only") is not True:
            problems.append(f"{role}: mutable container root is outside the persistent build-volume contract")
        environment = service.get("environment") or {}
        if not isinstance(environment, dict):
            raise ValueError("use rendered Compose JSON with an environment object")
        if role == "backend":
            provenance = environment.get("FULLMAG_PACKAGE_PROVENANCE") or "/opt/fullmag/provenance.json"
            paths = (*paths, normalized_target(provenance))
        mounts = []
        for item in service.get("volumes", []):
            if not isinstance(item, dict):
                raise ValueError("use rendered Compose JSON with normalized mount objects")
            target = normalized_target(item.get("target"))
            mounts.append((target, item))
            if item.get("type") == "volume" and item.get("source"):
                definition = definitions.get(item["source"])
                if definition is None:
                    problems.append(f"{role}: volume identity is not declared: {item['source']}")
                elif not isinstance(definition, dict):
                    raise ValueError("use normalized Compose volume definitions")
                elif definition.get("driver_opts") or definition.get("driver", "local") != "local":
                    problems.append(f"{role}: volume may map external storage via driver/options: {item['source']}")
            if item.get("type") == "bind" and item.get("read_only") is not True:
                if target not in RUNTIME_BINDS[role]:
                    problems.append(f"{role}: writable host bind at {target}")
            if any(covers(path, target) for path in paths):
                source_input = role == "frontend" and item.get("type") == "bind" and item.get("read_only") is True
                if item.get("type") != "volume" and not source_input:
                    problems.append(f"{role}: non-volume mount overlays a build directory: {target}")
        for path in paths:
            matching = [(target, item) for target, item in mounts if covers(target, path)]
            if not matching:
                problems.append(f"{role}: build path has no persistent Docker volume: {path}")
                continue
            target, mount = max(matching, key=lambda pair: len(pair[0]))
            if mount.get("type") != "volume" or mount.get("read_only") is True:
                problems.append(f"{role}: build path is not in a writable Docker volume: {path} (mount {target})")
            elif not mount.get("source"):
                problems.append(f"{role}: anonymous volume does not provide an explicit cache identity: {path}")
        source = [item for target, item in mounts if target == "/opt/fullmag/source"]
        if len(source) != 1 or source[0].get("type") != "bind" or source[0].get("read_only") is not True:
            problems.append(f"{role}: selected source must be one readonly bind")
        else:
            sources.append(source[0].get("source"))
    if len(sources) == 2 and (not sources[0] or sources[0] != sources[1]):
        problems.append("frontend and backend source checkout differs")
    return {
        "status": "FAIL" if problems else "PASS",
        "scope": "rendered application mount topology only; not a build or retention qualification",
        "problems": problems,
        "still_required": [
            "review host launcher writes and BuildKit staging",
            "inspect actual mounts, effective compiler and log paths",
            "measure allocation and verify retention after real builds",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compose_json", help="rendered Compose JSON file, or - for stdin")
    parser.add_argument("--expected-project", required=True)
    args = parser.parse_args()
    try:
        if args.compose_json == "-":
            document = json.load(sys.stdin)
        else:
            with open(args.compose_json, encoding="utf-8-sig") as source:
                document = json.load(source)
        result = audit(document, args.expected_project)
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"status": "INVALID", "error": str(error)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
