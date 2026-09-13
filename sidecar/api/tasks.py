from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from sidecar.services.tasks import request_cancel, running_tasks

router = APIRouter(tags=["tasks"])


@router.get("")
def list_running_tasks() -> Dict[str, Any]:
    """Task ids with a live worker thread."""
    ids = running_tasks()
    return {"tasks": ids, "count": len(ids)}


@router.delete("/{task_id}/cancel")
def cancel_task(task_id: str) -> Dict[str, Any]:
    """
    Flag a task as cancelled. Cancellation is cooperative: the worker stops at its
    next check_cancelled(), so this returns immediately with cancelled=true while
    the terminal `complete` frame still arrives on the SSE stream.
    """
    if not request_cancel(task_id):
        raise HTTPException(status_code=404, detail=f"No running task with id {task_id}")
    return {"task_id": task_id, "cancelled": True}
