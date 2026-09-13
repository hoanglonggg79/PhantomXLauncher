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

    def log(self, message: str, level: str = "info") -> None:
        self._bus.emit_log(self.task_id, message, level=level)

    def progress(self, current: int, total: int, label: str = "") -> None:
        self._bus.emit_progress(self.task_id, current, total, label)

    def cancel(self) -> None:
        """
        Flag the task as cancelled. Cooperative: the worker only stops where it
        calls check_cancelled() (or reads .cancelled), so blocking third-party
        installers keep running until their current step returns.
        """
        if self._cancelled.is_set():
            return
        self._cancelled.set()
        self.log("Cancellation requested by the client", level="warning")

    def check_cancelled(self) -> None:
        """Raise TaskCancelled if cancellation was requested. Call between steps."""
        if self._cancelled.is_set():
            raise TaskCancelled("Task cancelled")

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
            bus.emit_complete(task_id, True, result if isinstance(result, dict) else None)
        except TaskCancelled:
            logger.info(f"Task {name} ({task_id}) cancelled")
            ctx.log("Task cancelled", level="warning")
            bus.emit_complete(task_id, False, {"cancelled": True, "error": "Task cancelled"})
        except Exception as e:
            logger.exception(f"Task {name} ({task_id}) failed: {e}")
            ctx.log(f"Task failed: {e}", level="error")
            bus.emit_complete(task_id, False, {"error": str(e)})
        finally:
            with _lock:
                _running.pop(task_id, None)

    threading.Thread(target=worker, name=f"phantomx-{name}", daemon=True).start()
    logger.info(f"Task {name} started: {task_id}")
    return task_id


def get_context(task_id: str) -> Optional[TaskContext]:
    with _lock:
        return _running.get(task_id)


def request_cancel(task_id: str) -> bool:
    """
    Flag a running task as cancelled. Returns False when the id is unknown, i.e.
    the task already finished (or never existed).
    """
    ctx = get_context(task_id)
    if ctx is None:
        return False
    ctx.cancel()
    logger.info(f"Cancel requested for task {task_id}")
    return True


def running_tasks() -> list[str]:
    with _lock:
        return list(_running.keys())
