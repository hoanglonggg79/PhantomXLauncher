from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from sidecar.services import diagnostics

router = APIRouter(tags=["diagnostics"])


class BugReportPayload(BaseModel):
    title: str = Field(default="", max_length=150)
    description: str = Field(min_length=10, max_length=4000)
    steps: str = Field(default="", max_length=4000)
    include_specs: bool = Field(default=False)
    include_log: bool = Field(default=True)
    website: str = Field(default="")  # Honeypot


@router.get("/diagnostics")
def get_diagnostics() -> Dict[str, Any]:
    """
    Retrieve current system specs and log preview for the Bug Report dialog.
    """
    return diagnostics.get_diagnostics_context()


@router.post("/report-bug")
def report_bug(payload: BugReportPayload) -> Dict[str, Any]:
    """
    Submit a bug report to the Cloudflare Worker proxy.
    Supports multipart/form-data log file attachment and JSON payloads.
    """
    try:
        result = diagnostics.submit_bug_report(
            title=payload.title,
            description=payload.description,
            steps=payload.steps,
            include_specs=payload.include_specs,
            include_log=payload.include_log,
            website=payload.website,
        )
        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Lỗi gửi báo cáo."),
            )
        return result
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Lỗi khi gửi báo cáo: {e}",
        )


# ── Discord Rich Presence & Theme Audio ──────────────────────────────────────


class DiscordRpcPayload(BaseModel):
    status: str = Field(default="idle", pattern="^(idle|marketplace|in_game)$")
    instance_name: Optional[str] = None
    loader: Optional[str] = None
    mc_version: Optional[str] = None
    is_supporter: Optional[bool] = None


@router.post("/discord_rpc")
def update_discord_rpc(payload: DiscordRpcPayload) -> Dict[str, Any]:
    """
    Safely update Discord Rich Presence via background service.
    All Asset IDs and Discord API credentials remain strictly within Python Sidecar.
    """
    from sidecar.services.discord_rpc import get_discord_rpc_service
    from sidecar.services.core_service import load_settings

    settings = load_settings()
    rpc_enabled = bool(settings.get("discord_rpc_enabled", True))

    svc = get_discord_rpc_service()
    svc.set_enabled(rpc_enabled)
    if rpc_enabled:
        svc.update_presence(
            status=payload.status,
            instance_name=payload.instance_name,
            loader=payload.loader,
            mc_version=payload.mc_version,
            is_supporter=payload.is_supporter,
        )
    return {"status": "ok", "rpc_enabled": rpc_enabled}


@router.post("/theme/prepare")
def prepare_theme_audio() -> Dict[str, Any]:
    """
    Pre-downloads the background music theme to %LOCALAPPDATA%\\PhantomXTeam\\PhantomX\\theme\\theme.mp3
    """
    from sidecar.services import theme_audio
    return theme_audio.ensure_theme_audio()


@router.get("/theme/status")
def get_theme_status() -> Dict[str, Any]:
    """
    Checks whether the background music theme is present locally.
    """
    from sidecar.services import theme_audio
    return {
        "downloaded": theme_audio.is_theme_downloaded(),
        "path": str(theme_audio.get_theme_file_path()),
    }


@router.get("/theme/audio")
def stream_theme_audio():
    """
    Streams theme.mp3 over local HTTP so React HTML5 audio player
    can play it without file:// scope restrictions.
    """
    from fastapi.responses import FileResponse
    from sidecar.services import theme_audio

    target = theme_audio.get_theme_file_path()
    if not target.exists():
        # Trigger download in background if missing
        theme_audio.ensure_theme_audio()
        if not target.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Theme audio is not yet downloaded",
            )

    return FileResponse(
        target,
        media_type="audio/mpeg",
        filename="theme.mp3",
    )
