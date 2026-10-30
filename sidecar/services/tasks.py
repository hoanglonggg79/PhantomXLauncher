from __future__ import annotations

import threading
from typing import Callable, Optional

from loguru import logger

from sidecar.services.bus import get_event_bus


class TaskCancelled(Exception):
    """Raised inside a worker when the client cancelled the task."""


class TaskContext:
    """Handles passed to a worker: emits onto the task's SSE stream."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._bus = get_event_bus()
        self._cancelled = threading.Event()
        # Name of the step currently running. Recorded so a cancel can say *where*
        # it landed, and so a late cancel can be reported honestly.
        self._stage = "starting"

    @property
    def stage(self) -> str:
        return self._stage

    def mark_stage(self, stage: str) -> None:
        """
        Declare the step about to run. Raises TaskCancelled when a cancel already
        arrived, so the worker stops before doing more work instead of after.
        """
        self._stage = stage
        self.check_cancelled(stage)

    def log(self, message: str, level: str = "info") -> None:
        self._bus.emit_log(self.task_id, message, level=level)

    def progress(self, current: int, total: int, label: str = "") -> None:
        self._bus.emit_progress(self.task_id, current, total, label)

    def cancel(self, *, actor: str = "client") -> None:
        """
        Flag the task as cancelled. Cooperative: the worker only stops where it
        calls check_cancelled()/mark_stage() (or reads .cancelled), so blocking
        third-party installers keep running until their current step returns.
        """
        if self._cancelled.is_set():
            return
        self._cancelled.set()
        logger.info(
            f"Cancel requested by {actor} for task {self.task_id} at stage '{self._stage}'"
        )
        self.log(
            f"Cancellation requested by {actor} (stage: {self._stage})", level="warning"
        )

    def check_cancelled(self, step: str = "") -> None:
        """Raise TaskCancelled if cancellation was requested. Call between steps."""
        if self._cancelled.is_set():
            raise TaskCancelled(f"Task cancelled at stage '{step or self._stage}'")

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()


_running: dict[str, TaskContext] = {}
_lock = threading.Lock()


def start_task(
    fn: Callable[[TaskContext], Optional[dict]],
    *,
    name: str = "task",
) -> str:
    """
    Create a task id, run fn(ctx) on a daemon thread, and emit a terminal
    complete event whether it returns or raises. Returns the task id
    immediately so the client can subscribe to /api/events/{task_id}.
    """
    bus = get_event_bus()
    task_id = bus.create_task()
    ctx = TaskContext(task_id)

    with _lock:
        _running[task_id] = ctx

    def worker():
        try:
            result = fn(ctx)
            payload = result if isinstance(result, dict) else None
            if ctx.cancelled:
                # The cancel arrived while the last blocking step was finishing.
                # The work may be done, but the client asked to stop: never report
                # a clean success, and say which stage the cancel landed on.
                logger.info(
                    f"Task {name} ({task_id}) returned after cancel "
                    f"(stage '{ctx.stage}') — emitting cancelled, not success"
                )
                ctx.log(
                    f"Task finished after cancellation was requested (stage: {ctx.stage})",
                    level="warning",
                )
                bus.emit_complete(
                    task_id,
                    False,
                    {
                        "cancelled": True,
                        "error": "Task cancelled",
                        "stage": ctx.stage,
                        "partial_result": payload,
                    },
                )
                return
            bus.emit_complete(task_id, True, payload)
        except TaskCancelled as e:
            logger.info(f"Task {name} ({task_id}) cancelled at stage '{ctx.stage}': {e}")
            ctx.log(f"Task cancelled at stage '{ctx.stage}'", level="warning")
            bus.emit_complete(
                task_id,
                False,
                {"cancelled": True, "error": "Task cancelled", "stage": ctx.stage},
            )
        except Exception as e:
            logger.exception(f"Task {name} ({task_id}) failed at stage '{ctx.stage}': {e}")
            ctx.log(f"Task failed at stage '{ctx.stage}': {e}", level="error")
            bus.emit_complete(task_id, False, {"error": str(e), "stage": ctx.stage})
        finally:
            with _lock:
                _running.pop(task_id, None)

    threading.Thread(target=worker, name=f"phantomx-{name}", daemon=True).start()
    logger.info(f"Task {name} started: {task_id}")
    return task_id


def get_context(task_id: str) -> Optional[TaskContext]:
    with _lock:
        return _running.get(task_id)


def request_cancel(task_id: str, *, actor: str = "client") -> bool:
    """
    Flag a running task as cancelled. Returns False when the id is unknown, i.e.
    the task already finished (or never existed).
    """
    ctx = get_context(task_id)
    if ctx is None:
        logger.info(
            f"Cancel ignored for task {task_id}: no live worker (already finished or unknown)"
        )
        return False
    ctx.cancel(actor=actor)
    return True


def running_tasks() -> list[str]:
    with _lock:
        return list(_running.keys())
