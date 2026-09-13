from __future__ import annotations

import asyncio
import uuid
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger

MAX_QUEUED_EVENTS = 2000


def now_iso() -> str:
    """UTC timestamp shared by every SSE frame (also used by api/events.py)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class ProgressEvent:
    """Progress update from a long-running task."""
    task_id: str
    current: int
    total: int
    label: str
    timestamp: str


@dataclass
class LogEvent:
    """Log message from a task."""
    task_id: str
    level: str
    message: str
    timestamp: str


@dataclass
class CompleteEvent:
    """Task completion signal."""
    task_id: str
    success: bool
    result: Optional[dict]
    timestamp: str


class EventBus:
    """
    Singleton event bus managing task -> SSE subscriber fan-out.

    Queues are created by create_task(), before any worker thread starts, so
    events emitted before the SSE client connects are buffered instead of lost.

    Usage:
        bus = get_event_bus()
        task_id = bus.create_task()

        # From worker thread:
        bus.emit_progress(task_id, current, total, label)
        bus.emit_log(task_id, "message")
        bus.emit_complete(task_id, success=True, result={...})

        # From SSE handler (async):
        queue = bus.subscribe(task_id)
        event = await queue.get()
    """

    def __init__(self):
        self._subscribers: Dict[str, asyncio.Queue] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Attach the bus to the server's event loop (called at app startup)."""
        self._loop = loop

    def create_task(self) -> str:
        """Generate a task ID and open its queue immediately."""
        task_id = str(uuid.uuid4())
        self._subscribers[task_id] = asyncio.Queue(maxsize=MAX_QUEUED_EVENTS)
        logger.debug(f"EventBus: {task_id} created")
        return task_id

    def subscribe(self, task_id: str) -> asyncio.Queue:
        """
        Subscribe to events for a task. Returns the task's asyncio.Queue,
        creating it if the caller subscribed to an unknown task.
        """
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

        if task_id not in self._subscribers:
            self._subscribers[task_id] = asyncio.Queue(maxsize=MAX_QUEUED_EVENTS)
            logger.debug(f"EventBus: {task_id} subscribed (queue created on demand)")

        return self._subscribers[task_id]

    def unsubscribe(self, task_id: str):
        """Remove a subscriber (called when SSE client disconnects)."""
        if self._subscribers.pop(task_id, None) is not None:
            logger.debug(f"EventBus: {task_id} unsubscribed")

    def active_tasks(self) -> List[str]:
        return list(self._subscribers.keys())

    @staticmethod
    def _deliver(queue: asyncio.Queue, event) -> None:
        """Runs on the event loop. Drops the oldest event when the queue is full."""
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
                queue.put_nowait(event)
            except Exception:
                pass

    def _emit(self, task_id: str, event: ProgressEvent | LogEvent | CompleteEvent):
        """
        Thread-safe emit: called from worker threads, puts event onto asyncio.Queue.
        """
        queue = self._subscribers.get(task_id)
        if queue is None:
            logger.debug(f"EventBus: {task_id} has no queue, dropping event")
            return

        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._deliver, queue, event)
        else:
            logger.warning(f"EventBus: loop not running, cannot emit to {task_id}")

    def emit_progress(self, task_id: str, current: int, total: int, label: str):
        """Emit progress update (thread-safe, called from cb_progress)."""
        self._emit(
            task_id,
            ProgressEvent(
                task_id=task_id,
                current=int(current or 0),
                total=int(total or 0),
                label=str(label or ""),
                timestamp=now_iso(),
            ),
        )

    def emit_log(self, task_id: str, message: str, level: str = "info"):
        """Emit log message (thread-safe, called from cb_log)."""
        self._emit(
            task_id,
            LogEvent(task_id=task_id, level=level, message=str(message), timestamp=now_iso()),
        )

    def emit_complete(self, task_id: str, success: bool, result: Optional[dict] = None):
        """Emit task completion (thread-safe)."""
        self._emit(
            task_id,
            CompleteEvent(task_id=task_id, success=success, result=result, timestamp=now_iso()),
        )
        logger.info(f"EventBus: {task_id} completed (success={success})")


_bus_instance: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global EventBus singleton."""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = EventBus()
    return _bus_instance
