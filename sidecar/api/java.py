from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sidecar.services import java as java_svc

router = APIRouter(tags=["java"])

VALID_MAJORS = {8, 17, 21}


class InstallJavaRequest(BaseModel):
    major: int = Field(
        description="Java major version to install (8, 17, or 21).",
        examples=[21],
    )


@router.get("/list")
def list_java_installs() -> Dict[str, Any]:
    """
    Scan the system for all JRE/JDK installations and return the list.

    Sources checked (in order):
      - JAVA_HOME environment variable
      - System PATH (first `java` on PATH)
      - Windows Registry (JavaHome values)
      - Well-known install directories
      - PhantomX-managed runtimes (<runtimes_dir>/jre-*/bin/java.exe)
    """
    installs = java_svc.scan_java_installations()
    return {
        "installs": installs,
        "count": len(installs),
    }


@router.post("/install", status_code=202)
def install_java(body: InstallJavaRequest) -> Dict[str, Any]:
    """
    Start a background task that downloads and installs JRE *major* from the
    Eclipse Temurin (Adoptium) API.  Returns 202 with `{task_id, major}`
    immediately; follow progress on GET /api/events/{task_id}.

    Supported majors: 8, 17, 21.
    """
    if body.major not in VALID_MAJORS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported Java version: {body.major}. Must be one of {sorted(VALID_MAJORS)}.",
        )

    task_id = java_svc.download_java(body.major)
    return {
        "task_id": task_id,
        "major": body.major,
    }
