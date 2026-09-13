from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from sidecar.services import marketplace
from sidecar.services.core_service import get_core
from sidecar.services.tasks import start_task

router = APIRouter(tags=["marketplace"])


class InstallModPayload(BaseModel):
    instance_name: str
    source: str = Field(default="modrinth")
    project_id: str
    project_title: str = Field(default="")
    file_id: str = Field(default="")
    download_url: str
    filename: str


@router.get("/search")
def search_mods(
    q: str = Query(default="", description="Search query"),
    source: str = Query(default="modrinth", description="'modrinth' or 'curseforge'"),
    mc_version: str = Query(default="", description="Target Minecraft version"),
    loader: str = Query(default="", description="Loader: fabric, forge, quilt, neoforge"),
    category: str = Query(default="", description="Category filter"),
    sort: str = Query(default="downloads", description="Sort parameter"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> Dict[str, Any]:
    """
    Search mods on Modrinth or CurseForge.
    All CurseForge requests are safely proxied through the Python Sidecar to preserve secrets.
    """
    src = source.lower()
    if src == "curseforge":
        return marketplace.search_curseforge(
            query=q,
            mc_version=mc_version,
            loader=loader,
            category=category,
            sort=sort,
            page=page,
            page_size=page_size,
        )
    return marketplace.search_modrinth(
        query=q,
        mc_version=mc_version,
        loader=loader,
        category=category,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/project/{source}/{project_id}")
def get_project(source: str, project_id: str) -> Dict[str, Any]:
    """
    Retrieve project details, including icon, raw icon and image/screenshot gallery.
    """
    src = source.lower()
    if src == "curseforge":
        data = marketplace.get_curseforge_project(project_id)
    else:
        data = marketplace.get_modrinth_project(project_id)

    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project not found or service error: {data['error']}",
        )
    return data


@router.get("/versions/{source}/{project_id}")
def get_versions(
    source: str,
    project_id: str,
    mc_version: str = Query(default=""),
    loader: str = Query(default=""),
) -> List[Dict[str, Any]]:
    """
    Retrieve compatible versions and file download links.
    """
    src = source.lower()
    if src == "curseforge":
        return marketplace.get_curseforge_versions(
            project_id=project_id,
            mc_version=mc_version,
            loader=loader,
        )
    return marketplace.get_modrinth_versions(
        project_id=project_id,
        mc_version=mc_version,
        loader=loader,
    )


@router.post("/install", status_code=status.HTTP_202_ACCEPTED)
def install_mod(payload: InstallModPayload) -> Dict[str, Any]:
    """
    Trigger asynchronous installation of a mod into a target instance.
    Guards against busy/running instances before spawning the task.
    Streams progress through SSE /api/events/{task_id}.
    """
    from sidecar.services import instances as inst_svc

    try:
        instance = inst_svc.get_instance(payload.instance_name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance '{payload.instance_name}' does not exist.",
        )

    # State Guard: Check if game is running
    if inst_svc.is_running(payload.instance_name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Instance '{payload.instance_name}' đang chạy game. Vui lòng tắt Minecraft trước khi cài đặt mod!",
        )

    # Clean filename
    clean_filename = payload.filename.strip()
    if not clean_filename.endswith(".jar"):
        clean_filename = f"{clean_filename}.jar"

    task_id = start_task(
        lambda ctx: marketplace.install_mod_task(
            instance_name=payload.instance_name,
            filename=clean_filename,
            download_url=payload.download_url,
            project_title=payload.project_title or payload.project_id,
            source=payload.source,
            ctx=ctx,
        ),
        name=f"install_mod:{clean_filename}",
    )

    return {
        "task_id": task_id,
        "instance_name": payload.instance_name,
        "filename": clean_filename,
        "project_title": payload.project_title,
    }
