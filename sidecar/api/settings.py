from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from sidecar.services import core_service

router = APIRouter(tags=["settings"])


class SettingsPatch(BaseModel):
    username: Optional[str] = Field(default=None, max_length=32)
    ram: Optional[int] = Field(default=None, ge=512, le=65536)
    java_path: Optional[str] = None
    extra_jvm: Optional[str] = None
    snapshots: Optional[bool] = None
    close_on_launch: Optional[bool] = None
    auth_mode: Optional[str] = Field(default=None, pattern="^(offline|elyby)$")
    bg_music_enabled: Optional[bool] = None
    bg_music_volume: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    discord_rpc_enabled: Optional[bool] = None


@router.get("")
def read_settings() -> Dict[str, Any]:
    return core_service.load_settings()


@router.put("")
def update_settings(patch: SettingsPatch) -> Dict[str, Any]:
    return core_service.save_settings(patch.model_dump(exclude_none=True))


@router.get("/info")
def read_info() -> Dict[str, Any]:
    """Storage paths, core flags and Java status, for the About/Settings panel."""
    return core_service.app_info()


@router.get("/changelog")
def read_changelog(refresh: bool = False) -> Dict[str, Any]:
    """Release notes and updates fetched from GitHub Releases API."""
    from sidecar.services import changelog
    return changelog.get_changelog(force_refresh=refresh)


@router.get("/check-update")
def check_update() -> Dict[str, Any]:
    """Compare local version with GitHub version.txt to detect available updates."""
    from sidecar.services import changelog
    return changelog.check_version_update()

