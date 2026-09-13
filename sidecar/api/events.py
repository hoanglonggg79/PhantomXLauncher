from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from sidecar.services.bus import (
    CompleteEvent,
    LogEvent,
    ProgressEvent,
    get_event_bus,
    now_iso,
)


router = APIRouter(tags=["events"])

# Emitted when the queue stays quiet, so the client's watchdog can tell "task is
# slow" from "connection is dead". Must be a real data frame: EventSource never
# fires onmessage for SSE comments, which is all sse-starlette's own ping sends.
HEARTBEAT_SECONDS = 5.0


def _sse(payload: dict) -> dict:
    """
    Wrap a payload as an SSE frame. sse-starlette expands a yielded dict as
    ServerSentEvent(**dict), so the JSON has to live in the "data" field.
    """
    return {"data": json.dumps(payload, ensure_ascii=False)}


@router.get("/events/{task_id}")
async def stream_task_events(task_id: str):
    """
    SSE endpoint: streams progress, log, and completion events for a task.

    EventSource cannot set headers, so the token may be passed as ?token=<token>.

    Client usage:
        const source = new EventSource(
            `http://127.0.0.1:${port}/api/events/${taskId}?token=${token}`
        );
        source.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.type === 'progress') { ... }
            if (data.type === 'complete') { source.close(); }
        };
    """
    bus = get_event_bus()
    queue = bus.subscribe(task_id)

    logger.info(f"SSE client connected for task {task_id}")

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield _sse(
                        {"type": "heartbeat", "task_id": task_id, "timestamp": now_iso()}
                    )
                    continue

                if isinstance(event, ProgressEvent):
                    payload = {
                        "type": "progress",
                        "task_id": event.task_id,
                        "current": event.current,
                        "total": event.total,
                        "label": event.label,
                        "timestamp": event.timestamp,
                    }
                elif isinstance(event, LogEvent):
                    payload = {
                        "type": "log",
                        "task_id": event.task_id,
                        "level": event.level,
                        "message": event.message,
                        "timestamp": event.timestamp,
                    }
                elif isinstance(event, CompleteEvent):
                    yield _sse(
                        {
                            "type": "complete",
                            "task_id": event.task_id,
                            "success": event.success,
                            "result": event.result,
                            "timestamp": event.timestamp,
                        }
                    )
                    break
                else:
                    logger.warning(f"Unknown event type: {type(event)}")
                    continue

                yield _sse(payload)

        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for task {task_id}")

        finally:
            bus.unsubscribe(task_id)
            logger.info(f"SSE client disconnected for task {task_id}")

    return EventSourceResponse(event_generator())


@router.get("/events")
async def list_active_tasks():
    """
    List all active tasks with queues (for debugging).
    """
    return {"active_tasks": get_event_bus().active_tasks()}
