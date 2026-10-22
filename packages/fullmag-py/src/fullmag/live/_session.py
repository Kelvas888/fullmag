"""One live connection between a Python process and a running Fullmag session."""
from __future__ import annotations

import contextlib
import logging
import math
import sys
import threading
import time
import uuid
from types import SimpleNamespace
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

from fullmag.client import Client, CommandHandle, NotFoundError, Target
from fullmag.client.events import EventStream, LiveEvent, Subscription
from fullmag.client.fmtb import TableRows
from fullmag.client.fmvp import FieldVector

from ._scene import SceneNotReady, build_world_scene, plan_transactions

__all__ = ["LiveCommandResult", "LiveSession"]

_LOG = logging.getLogger("fullmag.live")
_SESSION_DEFAULTS = {"device": "cpu", "precision": "double"}
# Presence heartbeat period; the API lists clients for 30 s after the last one.
_HEARTBEAT_INTERVAL_S = 10.0
_STAGE_TARGET = Target.current_stage()
# Mirrors the API's read-only terminal session states.
_TERMINAL_SESSION_STATUSES = frozenset({"stopping", "stopped", "cancelled", "failed", "completed", "closed"})


@dataclass
class LiveCommandResult:
    """What ``fm.relax()``/``fm.run()`` return in live mode."""

    command_id: str
    kind: str
    status: str
    completion_status: Optional[str]
    detail: Mapping[str, Any] = field(repr=False, default_factory=dict)

    @classmethod
    def from_handle(cls, handle: CommandHandle) -> "LiveCommandResult":
        detail = handle.detail
        completion = detail.get("completion_status")
        return cls(handle.command_id, handle.kind, handle.status, None if completion is None else str(completion), detail)


class LiveSession:
    """Synchronises the DSL world of this process with the server's current session."""

    def __init__(
        self,
        client: Client,
        state: Any,
        *,
        source_path: Optional[Path] = None,
        command_timeout: Optional[float] = None,
    ) -> None:
        self.client = client
        self.state = state
        self.source_path = source_path or _default_source_path()
        self.command_timeout = command_timeout
        self.baseline: Optional[dict[str, Any]] = None
        self.revision: Optional[int] = None
        self.pending = False
        self.closed = False
        self._batch_depth = 0
        self.transactions_committed = 0
        self.events: Optional[EventStream] = None
        self.client_id = f"python-{uuid.uuid4().hex[:12]}"
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    # ---- lifecycle -------------------------------------------------------

    def attach(self, *, new_session: bool, backend: str) -> None:
        """Bind to the current server session, creating one when needed."""
        try:
            current = None if new_session else self.client.sessions.current()
        except NotFoundError:
            current = None
        # A terminal session rejects every mutating command, so a script
        # starts a fresh one instead of attaching to it.
        terminal = isinstance(current, Mapping) and current.get("status") in _TERMINAL_SESSION_STATUSES
        if current is None or terminal:
            self.client.sessions.create(
                "fullmag-python-live",
                backend=backend,
                replace_current=new_session or terminal,
                **_SESSION_DEFAULTS,
            )
        scene = self.client.model.scene()
        self.revision = _revision_of(scene)
        self._start_presence()
        # The script owns the scene: the first buildable world replaces it.
        self.baseline = None
        self.sync(strict=False)

    def close(self) -> None:
        self.closed = True
        self._stop_presence()
        if self.events is not None:
            self.events.close()
            self.events = None
        self.client.command_waiter = None
        self.client.close()

    def _start_presence(self) -> None:
        """Heartbeat presence so the Control Room shows that a script drives the session."""
        label = self.source_path.name

        def beat() -> None:
            while not self._heartbeat_stop.is_set():
                try:
                    self.client.sessions.heartbeat(self.client_id, label=label)
                except Exception as error:  # presence is informational and must not break the script
                    _LOG.debug("presence heartbeat failed: %s", error)
                self._heartbeat_stop.wait(_HEARTBEAT_INTERVAL_S)

        self._heartbeat_thread = threading.Thread(target=beat, name="fullmag-live-presence", daemon=True)
        self._heartbeat_thread.start()

    def _stop_presence(self) -> None:
        if self._heartbeat_thread is None:
            return
        self._heartbeat_stop.set()
        self._heartbeat_thread.join(timeout=2.0)
        self._heartbeat_thread = None
        try:
            self.client.sessions.leave(self.client_id)
        except Exception as error:
            _LOG.debug("presence leave failed: %s", error)

    def start_events(self) -> EventStream:
        """Start the realtime event stream; command waits then wake on events."""
        if self.events is None:
            self.events = EventStream(self.client.url).start()
            self.client.command_waiter = lambda _command_id, pause: self.events.wait_for_change(pause) if self.events else time.sleep(pause)
        return self.events

    def on(self, event_type: str, callback: Any) -> Subscription:
        """Call ``callback(event)`` for each realtime event of ``event_type`` (``"*"`` = all)."""
        return self.start_events().subscribe(event_type, callback)

    def __repr__(self) -> str:
        return f"LiveSession({self.client.url!r}, revision={self.revision}, pending={self.pending})"

    # ---- synchronisation -------------------------------------------------

    def after_dsl_call(self) -> None:
        if self.closed:
            return
        if self._batch_depth:
            self.pending = True
            return
        self.sync(strict=False)

    def sync(self, *, strict: bool = True) -> int:
        """Commit the difference between the world and the session; return transactions sent.

        With ``strict=False`` an incomplete world (e.g. a magnet without ``Ms``)
        is kept pending and sent by a later call; actions use ``strict=True``.
        """
        try:
            scene = build_world_scene(self.source_path)
        except SceneNotReady as error:
            self.pending = True
            if strict:
                raise RuntimeError(f"the live scene is incomplete: {error}") from error
            _LOG.debug("live sync deferred: %s", error)
            return 0
        transactions = plan_transactions(self.baseline, scene, self.revision)
        for index, transaction in enumerate(transactions):
            if index and self.revision is not None:
                transaction["base_revision"] = self.revision
            response = self.client.model.commit(transaction)
            self.revision = int(response["scene_revision"])
            self.transactions_committed += 1
        self.baseline = scene
        self.pending = False
        return len(transactions)

    @contextlib.contextmanager
    def transaction(self) -> Iterator["LiveSession"]:
        """Group DSL calls into one synchronisation (one revision for one change set)."""
        self._batch_depth += 1
        try:
            yield self
        finally:
            self._batch_depth -= 1
        if self._batch_depth == 0:
            self.sync(strict=False)

    # ---- runtime commands -----------------------------------------------

    def submit(self, kind: str, *, wait: bool = True, target: Optional[Mapping[str, Any]] = None, **fields: Any) -> LiveCommandResult | CommandHandle:
        if kind in {"run", "relax", "solve", "compute_fields", "compute_energies"}:
            self.sync(strict=True)
            precondition = {"scene_revision": self.revision} if self.revision is not None else None
            handle = self.client.commands.submit(kind, target=target or Target.study(), precondition=precondition, reason="python_live", **fields)
        else:
            handle = self.client.commands.submit(kind, target=target or _STAGE_TARGET, reason="python_live", **fields)
        if not wait:
            return handle
        handle.wait(timeout=self.command_timeout)
        return LiveCommandResult.from_handle(handle)

    def submit_stage(self, kind: str, stage_index: int, **fields: Any) -> LiveCommandResult:
        """Run the authored stage ``stage_index`` (Docker accepted runs need an explicit stage)."""
        return self.submit(kind, target=Target.stage_index(stage_index), **fields)  # type: ignore[return-value]

    @contextlib.contextmanager
    def paused(self) -> Iterator["LiveSession"]:
        """Pause the run, apply edits, resume — also when the block raises (ADR 0068 D3)."""
        self.submit("pause")
        try:
            with self.transaction():
                yield self
        finally:
            self.submit("resume")

    # ---- data -------------------------------------------------------------

    def field(self, quantity_id: str, **query: Any) -> Optional[FieldVector]:
        return self.client.data.read_field(quantity_id, **query)

    def table(self, table_id: str, *, columns: Optional[tuple[str, ...]] = None, **query: Any) -> TableRows:
        return self.client.data.read_table(table_id, columns=columns, **query)

    def latest_step(self) -> SimpleNamespace:
        """The newest scalar row of the session as a step-like object (``mx``, ``e_total``, ...)."""
        window = self.client.data.scalars(tail=1)
        rows = window.get("rows") or []
        if not rows:
            raise RuntimeError("the live session has no scalar samples yet; run fm.relax() or fm.run() first")
        return SimpleNamespace(**dict(zip(window.get("columns") or [], rows[-1])))

    def latest_result(self) -> SimpleNamespace:
        """A result-like object whose ``final_magnetization`` is the session's current ``m``."""
        vector = self.field("m")
        if vector is None:
            raise RuntimeError("the live session has no magnetization field yet")
        return SimpleNamespace(final_magnetization=vector.values.tolist(), field=vector)

    def run_until(
        self,
        predicate: Any,
        *,
        chunk_time: float,
        max_time: Optional[float] = None,
        max_chunks: Optional[int] = None,
        max_solver_steps: Optional[int] = None,
        relax: bool = False,
        relax_fields: Optional[Mapping[str, Any]] = None,
        stage_index: Optional[int] = None,
    ) -> Optional[LiveCommandResult]:
        """Run in chunks of ``chunk_time`` until ``predicate(step)`` is true (spec §5.4).

        ``step`` is :meth:`latest_step`. At least one of ``max_time``,
        ``max_chunks`` or ``max_solver_steps`` (counted from the session's
        ``step`` column) bounds the loop. Each chunk costs one command round
        trip and one scalar read.
        """
        if not math.isfinite(chunk_time) or chunk_time <= 0.0:
            raise ValueError("chunk_time must be a positive number of seconds")
        if max_time is None and max_chunks is None and max_solver_steps is None:
            raise ValueError("run_until needs max_time, max_chunks or max_solver_steps as a guard")
        start_step = _step_count(self) if max_solver_steps is not None else 0
        elapsed, chunks, last = 0.0, 0, None
        while (max_chunks is None or chunks < max_chunks) and (max_time is None or elapsed < max_time):
            span = chunk_time if max_time is None else min(chunk_time, max_time - elapsed)
            target = None if stage_index is None else Target.stage_index(stage_index)
            if relax:
                last = self.submit("relax", target=target, max_relaxation_time_s=span, **dict(relax_fields or {}))
            else:
                last = self.submit("run", target=target, until_seconds=span)
            elapsed += span
            chunks += 1
            step = self.latest_step()
            if predicate(step):
                break
            if max_solver_steps is not None and int(getattr(step, "step", 0)) - start_step >= max_solver_steps:
                break
        return last  # type: ignore[return-value]

    def export_script(self) -> str:
        response = self.client.model.script()
        return str(response.get("source", "")) if isinstance(response, Mapping) else str(response)


def _step_count(session: "LiveSession") -> int:
    try:
        return int(getattr(session.latest_step(), "step", 0))
    except RuntimeError:
        return 0


def _revision_of(scene: Any) -> Optional[int]:
    if isinstance(scene, Mapping):
        value = scene.get("revision")
        if value is None and isinstance(scene.get("scene"), Mapping):
            value = scene["scene"].get("revision")
        return int(value) if value is not None else None
    return None


def _default_source_path() -> Path:
    main = sys.modules.get("__main__")
    script = getattr(main, "__file__", None)
    return Path(script).resolve() if script else Path.cwd() / "fullmag_live_session.py"
