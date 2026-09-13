from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from sidecar.services import repair
from sidecar.services.instances import InstanceError
from sidecar.services.tasks import start_task

router = APIRouter(tags=["repair"])


@router.post("/{name}/verify-integrity", status_code=status.HTTP_202_ACCEPTED)
def verify_integrity(name: str) -> Dict[str, Any]:
    """
    Triggers background SHA-1 integrity check & selective repair for an instance.
    Streams progress and logs via SSE /api/events/{task_id}.
    """
    try:
        task_id = start_task(
            lambda ctx: repair.verify_and_repair(ctx, name),
            name=f"verify-{name}",
        )
        return {"task_id": task_id, "instance": name}
    except InstanceError as ie:
        raise HTTPException(status_code=ie.status, detail=ie.message)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khởi chạy kiểm tra toàn vẹn: {e}",
        )


@router.get("/{name}/analyze-crash")
def analyze_crash(name: str) -> Dict[str, Any]:
    """
    Analyzes the latest crash report or log of an instance using 80/20 regex pattern matching.
    """
    try:
        return repair.analyze_latest_crash(name)
    except InstanceError as ie:
        raise HTTPException(status_code=ie.status, detail=ie.message)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi phân tích crash log: {e}",
        )


@router.post("/{name}/reset-options")
def reset_options(name: str) -> Dict[str, Any]:
    """
    Resets options.txt to vanilla defaults for troubleshooting display/crash issues.
    """
    try:
        return repair.reset_options(name)
    except InstanceError as ie:
        raise HTTPException(status_code=ie.status, detail=ie.message)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi đặt lại options.txt: {e}",
        )


@router.post("/clean-cache")
def clean_cache() -> Dict[str, Any]:
    """
    Cleans temporary downloads, .tmp files, and cached data under PhantomX storage.
    """
    try:
        return repair.clean_cache()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi dọn dẹp cache: {e}",
        )
