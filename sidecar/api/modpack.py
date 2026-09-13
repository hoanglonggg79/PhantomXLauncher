from __future__ import annotations

from pathlib import Path
import shutil
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from loguru import logger
from pydantic import BaseModel, Field

from sidecar.services import modpack as modpack_svc
from sidecar.services.instances import validate_name
from sidecar.services.tasks import start_task
from sidecar.utils import path_resolver

router = APIRouter(tags=["modpack"])


class ModpackInstallPayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    source: str = Field(default="curseforge", pattern="^(curseforge|modrinth|local)$")
    local_path: Optional[str] = None
    project_id: Optional[str] = None
    file_id: Optional[str] = None


@router.post("/upload")
async def upload_modpack(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    POST /api/marketplace/modpack/upload
    Save uploaded .zip / .mrpack archive to cache and inspect metadata.
    """
    filename = file.filename or "modpack.zip"
    ext = Path(filename).suffix.lower()
    if ext not in (".zip", ".mrpack"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Định dạng không được hỗ trợ. Vui lòng tải lên file .zip hoặc .mrpack!",
        )

    cache_dir = path_resolver.get_cache_dir() / "modpack_uploads"
    cache_dir.mkdir(parents=True, exist_ok=True)

    dest_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
    dest_path = cache_dir / dest_filename

    try:
        with open(dest_path, "wb") as f:
            while chunk := await file.read(65536):
                f.write(chunk)
    except Exception as e:
        logger.error(f"Failed to write uploaded modpack file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Không thể lưu file tải lên trên máy chủ.",
        )

    try:
        info = modpack_svc.inspect_modpack(dest_path)
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tệp không hợp lệ: {e}",
        )

    return {
        "temp_path": str(dest_path),
        "filename": filename,
        "format": info["format"],
        "detected_name": info["name"],
        "mc_version": info["mc_version"],
        "loader": info["loader"],
        "loader_version": info["loader_version"],
        "mod_count": info["mod_count"],
    }


@router.post("/install", status_code=status.HTTP_202_ACCEPTED)
def install_modpack(payload: ModpackInstallPayload) -> Dict[str, Any]:
    """
    POST /api/marketplace/modpack/install
    Trigger asynchronous installation of a modpack into a new instance.
    Runs in background via start_task() and streams progress via SSE.
    """
    try:
        clean_name = validate_name(payload.name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    inst_root = path_resolver.get_instances_dir()
    if (inst_root / clean_name / "instance.json").exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Instance mang tên '{clean_name}' đã tồn tại. Vui lòng chọn tên khác!",
        )

    # Check local path
    if not payload.local_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thiếu đường dẫn tệp modpack (local_path).",
        )

    local_file = Path(payload.local_path)
    if not local_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tệp modpack tạm thời không tồn tại trên hệ thống.",
        )

    task_id = start_task(
        lambda ctx: modpack_svc.install_modpack_task(
            ctx=ctx,
            instance_name=clean_name,
            zip_path=local_file,
            source=payload.source,
            cleanup_archive=True,
        ),
        name=f"modpack_install:{clean_name}",
    )

    return {
        "task_id": task_id,
        "name": clean_name,
    }
