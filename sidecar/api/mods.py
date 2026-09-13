from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from sidecar.services.mods import (
    ModError,
    delete_mod,
    list_mods,
    open_mods_folder,
    save_mod_file,
    toggle_mod,
)

router = APIRouter(tags=["mods"])

MAX_MOD_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB hard cap


def _fail(e: ModError) -> HTTPException:
    status = getattr(e, "status", None) or 400
    return HTTPException(status_code=status, detail=str(e))


# ── Request models ──────────────────────────────────────────────────────────


class ToggleModRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    enabled: bool


# ── Routes ──────────────────────────────────────────────────────────────────


@router.get("/{name}/mods")
def get_mods(name: str) -> Dict[str, Any]:
    """List all installed mods (.jar and .jar.disabled) for an instance."""
    try:
        mods = list_mods(name)
    except ModError as e:
        raise _fail(e) from e
    return {"mods": mods, "count": len(mods)}


@router.post("/{name}/mods/toggle")
def toggle_mod_route(name: str, body: ToggleModRequest) -> Dict[str, Any]:
    """Enable or disable a mod by renaming its file extension."""
    try:
        return toggle_mod(name, body.filename, body.enabled)
    except ModError as e:
        raise _fail(e) from e


@router.delete("/{name}/mods/{filename:path}")
def delete_mod_route(name: str, filename: str) -> Dict[str, Any]:
    """Permanently delete a mod file from disk."""
    try:
        return delete_mod(name, filename)
    except ModError as e:
        raise _fail(e) from e


@router.post("/{name}/mods/open-folder")
def open_mods_folder_route(name: str) -> Dict[str, Any]:
    """Open the instance's mods/ directory in the OS file manager."""
    try:
        return open_mods_folder(name)
    except ModError as e:
        raise _fail(e) from e


@router.post("/{name}/mods/upload", status_code=201)
async def upload_mod(
    name: str,
    file: UploadFile = File(..., description="A .jar mod file to add to the instance"),
) -> Dict[str, Any]:
    """
    Upload a .jar file into the instance's mods/ directory.
    Max size: 500 MB. Content-Type must be multipart/form-data.
    """
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    data = await file.read(MAX_MOD_SIZE_BYTES + 1)
    if len(data) > MAX_MOD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Mod file exceeds the 500 MB limit ({len(data)} bytes received)",
        )

    try:
        return save_mod_file(name, filename, data)
    except ModError as e:
        raise _fail(e) from e
