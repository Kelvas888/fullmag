"""Read-only, image-owned selector for a pre-admission recreate proof.

The host only supplies the three immutable pins and decodes the bounded result.
Enumeration and no-follow metadata checks run in the selected Compose group's
control helper, using the same BuildControl image and volume as other control
records.  This module never writes the control volume and never executes
application source.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
import json
import re
import shlex
from typing import Any

from docker_build_control import BuildControlError, MAX_DOCUMENT_BYTES, bounded_capture


SELECTOR_SCHEMA = "fullmag.docker-pre-admission-resume-selector.v1"
MAX_SELECTOR_ENTRIES = 256
MAX_SELECTOR_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SELECTOR_OUTPUT_BYTES = MAX_DOCUMENT_BYTES
MAX_SELECTOR_RESULT_RAW_BYTES = 5 * 1024 * 1024
MAX_STARTED_AT_BYTES = 256
ATTEMPT_RE = re.compile(r"^[0-9a-f]{32}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PHASES = ("resume", "development")
PUBLICATION_PATHS = (
    "handoff-log.json",
    "backend-build-receipt.json",
    "provenance.json",
    "storage-probe-log.json",
)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise BuildControlError("Pre-admission selector value is not canonical JSON") from error


def _strict_document(raw: bytes, label: str) -> dict[str, object]:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_DOCUMENT_BYTES:
        raise BuildControlError(label + " is missing or exceeds its byte budget")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("non-finite JSON number: " + value)

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, RecursionError) as error:
        raise BuildControlError(label + " is not valid strict JSON") from error
    if not isinstance(value, dict):
        raise BuildControlError(label + " is not a JSON object")
    if raw != _canonical(value) + b"\n":
        raise BuildControlError(label + " is not the canonical control record")
    return value


def _decode_raw(value: object, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise BuildControlError(label + " is not base64 text")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise BuildControlError(label + " is not strict base64") from error
    if not raw or len(raw) > MAX_DOCUMENT_BYTES:
        raise BuildControlError(label + " exceeds its byte budget")
    return raw


def _text_pin(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or len(value.encode("utf-8")) > MAX_STARTED_AT_BYTES
    ):
        raise BuildControlError(label + " is missing or exceeds its byte budget")
    return value


def _path_pin(value: object, phase: str, attempt: str, name: str) -> str:
    expected = f"{phase}/attempts/{attempt}/{name}"
    if value != expected:
        raise BuildControlError("Pre-admission selector returned an unexpected control path")
    return expected


def _readonly_control_helper_args(control: Any, source: str, helper_image: str) -> list[str]:
    """Keep BuildControl's group/auth flags and make only /control readonly."""

    try:
        command = list(control.helper_args(source))
        mount_indexes = [index for index, value in enumerate(command) if value == "--mount"]
        volume = control.volume
        namespace = getattr(control, "namespace", "")
    except (AttributeError, TypeError, ValueError) as error:
        raise BuildControlError("Pre-admission selector has no valid control helper") from error
    if not isinstance(volume, str) or not volume:
        raise BuildControlError("Pre-admission selector control volume is missing")
    if namespace:
        expected_control = (
            f"type=volume,src={volume},dst=/control,volume-nocopy,"
            f"volume-subpath={namespace}"
        )
        expected_registry = f"type=volume,src={volume},dst=/registry,readonly,volume-nocopy"
        expected_mounts = (expected_control, expected_registry)
    else:
        expected_mounts = (f"type=volume,src={volume},dst=/control,volume-nocopy",)
    if len(mount_indexes) != len(expected_mounts):
        raise BuildControlError("Pre-admission selector helper has an unexpected mount set")
    mounts = tuple(command[index + 1] for index in mount_indexes)
    if mounts != expected_mounts:
        raise BuildControlError("Pre-admission selector helper mount identity differs")
    command[mount_indexes[0] + 1] = expected_mounts[0] + ",readonly"
    # The base CUDA control image supplies shell probes but no Python. The
    # retained-service caller authenticates this exact backend image before
    # selecting it; keep every group, namespace and security argument intact.
    if not isinstance(helper_image, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", helper_image) is None:
        raise BuildControlError("Pre-admission selector requires the immutable retained backend image")
    try:
        anchor = command.index("--entrypoint")
        if command[anchor + 1:anchor + 3] != ["/bin/bash", control.image]:
            raise BuildControlError("Pre-admission selector helper entrypoint/image differs")
        command[anchor + 2] = helper_image
    except (ValueError, AttributeError, IndexError) as error:
        raise BuildControlError("Pre-admission selector helper entrypoint is missing") from error
    return command


# This source is intentionally self-contained.  It is passed to the immutable
# control helper image through BuildControl.helper_args; it does not import or
# execute any application checkout code.
_HELPER_SOURCE = r'''
import base64
import json
import os
import re
import stat
import sys

SCHEMA = 'fullmag.docker-pre-admission-resume-selector.v1'
MAX_ENTRIES = 256
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_RESULT_RAW_BYTES = 5 * 1024 * 1024
MAX_STARTED_AT_BYTES = 256
ATTEMPT_RE = re.compile(r'^[0-9a-f]{32}$')
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
PHASES = ('resume', 'development')
PUBLICATION_PATHS = (
    'handoff-log.json',
    'backend-build-receipt.json',
    'provenance.json',
    'storage-probe-log.json',
)
budget = {'entries': 0, 'bytes': 0}

try:
    DIRECTORY_FLAGS = (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, 'O_CLOEXEC', 0)
    )
    LEAF_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
except AttributeError as error:
    raise RuntimeError('selector platform lacks required no-follow flags') from error


def fail(message):
    raise RuntimeError(message)


def canonical(value):
    try:
        return json.dumps(
            value, sort_keys=True, separators=(',', ':'),
            ensure_ascii=False, allow_nan=False,
        ).encode('utf-8')
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise RuntimeError('value is not canonical JSON') from error


def strict_document(raw, label):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_FILE_BYTES:
        fail(label + ' is missing or exceeds its byte budget')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail(label + ' contains a duplicate JSON key')
            result[key] = value
        return result

    def reject_constant(value):
        fail(label + ' contains a non-finite JSON number: ' + value)

    try:
        value = json.loads(
            raw.decode('utf-8'),
            object_pairs_hook=unique,
            parse_constant=reject_constant,
        )
    except RuntimeError:
        raise
    except RecursionError as error:
        raise RuntimeError(label + ' is too deeply nested') from error
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(label + ' is not valid strict JSON') from error
    if not isinstance(value, dict):
        fail(label + ' is not a JSON object')
    if raw != canonical(value) + b'\n':
        fail(label + ' is not the canonical control record')
    return value


def stamp(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def file_stamp(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def stat_at(parent_fd, name, label, optional=False):
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if optional:
            return None
        fail(label + ' is missing')
    except OSError as error:
        raise RuntimeError(label + ' cannot be inspected safely') from error


def directory_snapshot(descriptor, label):
    try:
        info = os.fstat(descriptor)
    except OSError as error:
        raise RuntimeError(label + ' cannot be inspected safely') from error
    if not stat.S_ISDIR(info.st_mode):
        fail(label + ' is not a directory')
    return stamp(info)


def open_control():
    try:
        before = os.stat('/control', follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
            fail('control root is not a canonical directory')
        descriptor = os.open('/control', DIRECTORY_FLAGS)
    except RuntimeError:
        raise
    except OSError as error:
        raise RuntimeError('control root cannot be opened safely') from error
    try:
        opened = os.fstat(descriptor)
        if stamp(opened) != stamp(before):
            fail('control root changed before it was opened')
        try:
            after = os.stat('/control', follow_symlinks=False)
        except OSError as error:
            raise RuntimeError('control root disappeared while it was opened') from error
        if stamp(after) != stamp(opened):
            fail('control root changed while it was opened')
        if not stat.S_ISDIR(opened.st_mode):
            fail('control root is not a directory')
        return descriptor, stamp(opened)
    except BaseException:
        os.close(descriptor)
        raise


def verify_control(descriptor, expected, label='control root'):
    current = directory_snapshot(descriptor, label)
    if current != expected:
        fail(label + ' changed while it was inspected')
    try:
        path_info = os.stat('/control', follow_symlinks=False)
    except OSError as error:
        raise RuntimeError(label + ' disappeared') from error
    if stamp(path_info) != current:
        fail(label + ' path changed while it was inspected')


def open_directory_at(parent_fd, name, label, optional=False):
    before = stat_at(parent_fd, name, label, optional=optional)
    if before is None:
        return None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        fail(label + ' is not a canonical directory')
    try:
        descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as error:
        raise RuntimeError(label + ' cannot be opened safely') from error
    try:
        opened = os.fstat(descriptor)
        if stamp(opened) != stamp(before) or not stat.S_ISDIR(opened.st_mode):
            fail(label + ' changed before it was opened')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def open_phase_attempts(control_fd, phase):
    phase_fd = open_directory_at(
        control_fd, phase, phase + ' phase directory', optional=True
    )
    if phase_fd is None:
        return None
    try:
        return open_directory_at(
            phase_fd, 'attempts', phase + ' attempts root', optional=True
        )
    finally:
        os.close(phase_fd)


def enumerate_attempts(attempts_fd, phase):
    before = directory_snapshot(attempts_fd, phase + ' attempts root')
    entries = []
    try:
        with os.scandir(attempts_fd) as iterator:
            for entry in iterator:
                budget['entries'] += 1
                if budget['entries'] > MAX_ENTRIES:
                    fail('pre-admission selector directory-entry bound exceeded')
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError as error:
                    raise RuntimeError(
                        phase + ' attempt entry cannot be inspected safely'
                    ) from error
                if stat.S_ISLNK(info.st_mode):
                    fail('pre-admission selector contains a symlinked attempt')
                if not ATTEMPT_RE.fullmatch(entry.name):
                    fail('pre-admission selector contains an invalid attempt directory')
                if not stat.S_ISDIR(info.st_mode):
                    fail('pre-admission selector attempt is not a directory')
                entries.append((entry.name, stamp(info)))
    except RuntimeError:
        raise
    except OSError as error:
        raise RuntimeError(
            phase + ' attempts root cannot be enumerated safely'
        ) from error
    after = directory_snapshot(attempts_fd, phase + ' attempts root')
    if after != before:
        fail(phase + ' attempts root changed while it was enumerated')
    return sorted(entries), before


def open_attempt(attempts_fd, phase, attempt, expected):
    before = stat_at(attempts_fd, attempt, phase + ' attempt directory')
    if before is None or stamp(before) != expected:
        fail(phase + ' attempt directory changed before it was opened')
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        fail(phase + ' attempt directory is not canonical')
    try:
        descriptor = os.open(attempt, DIRECTORY_FLAGS, dir_fd=attempts_fd)
    except OSError as error:
        raise RuntimeError(phase + ' attempt directory cannot be opened safely') from error
    try:
        opened = os.fstat(descriptor)
        if stamp(opened) != expected or not stat.S_ISDIR(opened.st_mode):
            fail(phase + ' attempt directory changed before it was read')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def regular_at(parent_fd, name, label, optional=False):
    before = stat_at(parent_fd, name, label, optional=optional)
    if before is None:
        return None
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size <= 0
        or before.st_size > MAX_FILE_BYTES
    ):
        fail(label + ' is not a bounded regular file')
    if budget['bytes'] + before.st_size > MAX_TOTAL_BYTES:
        fail('pre-admission selector evidence exceeds its total byte bound')
    descriptor = None
    try:
        try:
            descriptor = os.open(name, LEAF_FLAGS, dir_fd=parent_fd)
        except OSError as error:
            raise RuntimeError(label + ' cannot be opened safely') from error
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino, opened.st_size)
            != (before.st_dev, before.st_ino, before.st_size)
        ):
            fail(label + ' changed before it was read')
        chunks = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                fail(label + ' changed while it was read')
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            fail(label + ' grew while it was read')
        after = os.fstat(descriptor)
        if file_stamp(after) != file_stamp(before):
            fail(label + ' changed while it was read')
        try:
            path_after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as error:
            raise RuntimeError(label + ' disappeared while it was read') from error
        if file_stamp(path_after) != file_stamp(before):
            fail(label + ' path changed while it was read')
        data = b''.join(chunks)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    budget['bytes'] += len(data)
    return data


def absent_at(parent_fd, name, label):
    info = stat_at(parent_fd, name, label, optional=True)
    if info is None:
        return
    if stat.S_ISLNK(info.st_mode):
        fail(label + ' is a symlink, not authenticated absence')
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        fail(label + ' is not an authenticated regular path')
    fail(label + ' is present')


def inspect_attempt(
    attempts_fd, phase, attempt, expected, parent, config, started, matches
):
    descriptor = open_attempt(attempts_fd, phase, attempt, expected)
    try:
        before = directory_snapshot(descriptor, phase + ' attempt directory')
        terminal_raw = regular_at(
            descriptor, 'terminal.json', phase + ' terminal', optional=True
        )
        if terminal_raw is None:
            if directory_snapshot(descriptor, phase + ' attempt directory') != before:
                fail(phase + ' attempt directory changed while it was inspected')
            return
        terminal = strict_document(terminal_raw, phase + ' terminal')
        if terminal.get('phase') != phase or terminal.get('attempt') != attempt:
            fail(phase + ' terminal is not bound to its canonical path')
        inputs = terminal.get('inputs')
        if isinstance(inputs, dict) and (
            inputs.get('attempt') == parent
            and inputs.get('config_sha256') == config
            and terminal.get('backend_started_at') == started
        ):
            if matches:
                fail('pre-admission selector found more than one pinned terminal')
            matches.append((phase, attempt, expected, terminal_raw, terminal))
        if directory_snapshot(descriptor, phase + ' attempt directory') != before:
            fail(phase + ' attempt directory changed while it was inspected')
    finally:
        os.close(descriptor)


def reopen_attempt(control_fd, phase, attempt, expected):
    attempts_fd = open_phase_attempts(control_fd, phase)
    if attempts_fd is None:
        fail(phase + ' attempts root disappeared')
    try:
        return open_attempt(attempts_fd, phase, attempt, expected)
    finally:
        os.close(attempts_fd)


def read_request():
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        fail('selector request exceeds its byte bound')
    request = strict_document(raw, 'selector request')
    if set(request) != {'parent_attempt', 'config_sha256', 'backend_started_at'}:
        fail('selector request fields are not exact')
    parent = request['parent_attempt']
    config = request['config_sha256']
    started = request['backend_started_at']
    if not isinstance(parent, str) or ATTEMPT_RE.fullmatch(parent) is None:
        fail('selector parent attempt is invalid')
    if not isinstance(config, str) or SHA256_RE.fullmatch(config) is None:
        fail('selector config digest is invalid')
    if (
        not isinstance(started, str)
        or not started
        or '\x00' in started
        or len(started.encode('utf-8')) > MAX_STARTED_AT_BYTES
    ):
        fail('selector Docker StartedAt is invalid')
    return parent, config, started


def main():
    parent, config, started = read_request()
    matches = []
    control_fd, control_stamp = open_control()
    try:
        for phase in PHASES:
            attempts_fd = open_phase_attempts(control_fd, phase)
            if attempts_fd is None:
                continue
            try:
                entries, attempts_stamp = enumerate_attempts(attempts_fd, phase)
                for attempt, expected in entries:
                    inspect_attempt(
                        attempts_fd, phase, attempt, expected,
                        parent, config, started, matches,
                    )
                if directory_snapshot(attempts_fd, phase + ' attempts root') != attempts_stamp:
                    fail(phase + ' attempts root changed while it was inspected')
            finally:
                os.close(attempts_fd)
        verify_control(control_fd, control_stamp)
        if len(matches) != 1:
            fail('pre-admission selector did not find exactly one pinned terminal')
        phase, attempt, expected, terminal_raw, terminal = matches[0]
        if attempt == parent:
            fail('pre-admission selector matched the parent attempt')
        if terminal.get('state') != 'failed-confirmed':
            fail('pre-admission selector terminal is not a confirmed failure')

        descriptor = reopen_attempt(control_fd, phase, attempt, expected)
        try:
            before = directory_snapshot(descriptor, phase + ' attempt directory')
            failure_raw = regular_at(
                descriptor, 'backend-failure-log.json', phase + ' failure log'
            )
            failure = strict_document(failure_raw, phase + ' failure log')
            if not isinstance(failure.get('log'), str):
                fail(phase + ' failure log has no bounded log text')
            published = {}
            for name in PUBLICATION_PATHS:
                absent_at(descriptor, name, phase + ' publication path ' + name)
                published[name] = False
            if directory_snapshot(descriptor, phase + ' attempt directory') != before:
                fail(phase + ' attempt directory changed while it was inspected')
            if len(terminal_raw) + len(failure_raw) > MAX_RESULT_RAW_BYTES:
                fail('pre-admission selector result exceeds its raw byte bound')
        finally:
            os.close(descriptor)
        verify_control(control_fd, control_stamp)
    finally:
        os.close(control_fd)

    result = {
        'schema': SCHEMA,
        'max_entries': MAX_ENTRIES,
        'scanned_entries': budget['entries'],
        'candidate_count': 1,
        'candidates': [{
            'phase': phase,
            'attempt': attempt,
            'terminal_path': f'{phase}/attempts/{attempt}/terminal.json',
            'terminal_raw_b64': base64.b64encode(terminal_raw).decode('ascii'),
            'failure_log_path': f'{phase}/attempts/{attempt}/backend-failure-log.json',
            'failure_log_raw_b64': base64.b64encode(failure_raw).decode('ascii'),
            'published_paths': published,
        }],
    }
    encoded = (json.dumps(
        result, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False,
    ) + '\n').encode('utf-8')
    if len(encoded) > MAX_OUTPUT_BYTES:
        fail('pre-admission selector response exceeds its byte bound')
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


main()
'''


def read_pinned_resume_evidence(
    control: Any,
    *,
    parent_attempt: str,
    config_sha256: str,
    backend_started_at: str,
    helper_image: str,
) -> dict[str, object]:
    """Return one exact pre-admission candidate from the selected helper.

    The helper is deliberately the only enumerator.  The host validates its
    bounded response and reparses every returned raw document before exposing
    the validator's ``terminal_raw``/``failure_log_raw`` contract.
    """

    if not isinstance(parent_attempt, str) or ATTEMPT_RE.fullmatch(parent_attempt) is None:
        raise BuildControlError("Pre-admission selector parent attempt is invalid")
    if not isinstance(config_sha256, str) or SHA256_RE.fullmatch(config_sha256) is None:
        raise BuildControlError("Pre-admission selector config digest is invalid")
    started = _text_pin(backend_started_at, "Pre-admission selector Docker StartedAt")
    request = _canonical({
        "backend_started_at": started,
        "config_sha256": config_sha256,
        "parent_attempt": parent_attempt,
    }) + b"\n"
    try:
        command = _readonly_control_helper_args(
            control,
            "exec /usr/local/bin/python3 -B -c " + shlex.quote(_HELPER_SOURCE),
            helper_image,
        )
        result = bounded_capture(
            command,
            data=request,
            timeout=90,
            maximum=MAX_SELECTOR_OUTPUT_BYTES,
        )
    except BuildControlError:
        raise
    except Exception as error:
        raise BuildControlError("Pre-admission selector helper failed") from error
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise BuildControlError("Pre-admission selector refused evidence" + (": " + detail if detail else ""))
    response = _strict_document(result.stdout, "Pre-admission selector response")
    if set(response) != {"schema", "max_entries", "scanned_entries", "candidate_count", "candidates"}:
        raise BuildControlError("Pre-admission selector response fields are not exact")
    if response.get("schema") != SELECTOR_SCHEMA:
        raise BuildControlError("Pre-admission selector schema differs")
    maximum = response.get("max_entries")
    scanned = response.get("scanned_entries")
    candidates = response.get("candidates")
    if (
        type(maximum) is not int
        or maximum <= 0
        or maximum > MAX_SELECTOR_ENTRIES
        or type(scanned) is not int
        or scanned < 0
        or scanned > maximum
        or not isinstance(candidates, list)
        or response.get("candidate_count") != len(candidates)
        or len(candidates) != 1
    ):
        raise BuildControlError("Pre-admission selector response bounds are invalid")

    candidate = candidates[0]
    if not isinstance(candidate, Mapping):
        raise BuildControlError("Pre-admission selector candidate is not an object")
    expected_fields = {
        "phase", "attempt", "terminal_path", "terminal_raw_b64",
        "failure_log_path", "failure_log_raw_b64", "published_paths",
    }
    if set(candidate) != expected_fields:
        raise BuildControlError("Pre-admission selector candidate fields are not exact")
    phase = candidate.get("phase")
    attempt = candidate.get("attempt")
    if not isinstance(phase, str) or phase not in PHASES:
        raise BuildControlError("Pre-admission selector candidate phase is invalid")
    if not isinstance(attempt, str) or ATTEMPT_RE.fullmatch(attempt) is None or attempt == parent_attempt:
        raise BuildControlError("Pre-admission selector candidate attempt is invalid")
    terminal_path = _path_pin(candidate.get("terminal_path"), phase, attempt, "terminal.json")
    failure_path = _path_pin(
        candidate.get("failure_log_path"), phase, attempt, "backend-failure-log.json"
    )
    published = candidate.get("published_paths")
    if (
        not isinstance(published, Mapping)
        or set(published) != set(PUBLICATION_PATHS)
        or any(value is not False for value in published.values())
    ):
        raise BuildControlError("Pre-admission publication paths are not authenticated absent")
    terminal_raw = _decode_raw(candidate.get("terminal_raw_b64"), "Pre-admission terminal")
    failure_raw = _decode_raw(candidate.get("failure_log_raw_b64"), "Pre-admission failure log")
    if len(terminal_raw) + len(failure_raw) > MAX_SELECTOR_RESULT_RAW_BYTES:
        raise BuildControlError("Pre-admission selector result exceeds its raw byte bound")
    terminal = _strict_document(terminal_raw, "Pre-admission terminal")
    failure = _strict_document(failure_raw, "Pre-admission failure log")
    inputs = terminal.get("inputs")
    if (
        terminal.get("phase") != phase
        or terminal.get("attempt") != attempt
        or terminal.get("state") != "failed-confirmed"
        or not isinstance(inputs, Mapping)
        or inputs.get("attempt") != parent_attempt
        or inputs.get("config_sha256") != config_sha256
        or terminal.get("backend_started_at") != started
    ):
        raise BuildControlError("Pre-admission terminal pins differ")
    if not isinstance(failure.get("log"), str):
        raise BuildControlError("Pre-admission failure log has no bounded log text")
    return {
        "schema": response["schema"],
        "max_entries": maximum,
        "scanned_entries": scanned,
        "candidate_count": 1,
        "candidates": [{
            "phase": phase,
            "attempt": attempt,
            "terminal_path": terminal_path,
            "terminal": terminal,
            "terminal_raw": terminal_raw,
            "failure_log_path": failure_path,
            "failure_log": failure,
            "failure_log_raw": failure_raw,
            "published_paths": dict(published),
        }],
    }
