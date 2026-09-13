from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sidecar.services import elyby_auth as svc

router = APIRouter(tags=["auth"])


class ElybyLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)
    totp_token: Optional[str] = Field(default=None, max_length=16)
    clientToken: str = Field(default="", max_length=64)


class ElybyRefreshRequest(BaseModel):
    accessToken: str = Field(min_length=1)
    clientToken: str = Field(min_length=1)


def _auth_error(e: svc.ElybyAuthError) -> HTTPException:
    body: Dict[str, Any] = {"error": e.code or "AUTH_ERROR", "message": str(e)}
    return HTTPException(status_code=e.status, detail=body)


@router.post("/elyby/login")
def elyby_login(body: ElybyLoginRequest) -> Dict[str, Any]:
    """Authenticate with Ely.by (Yggdrasil). Passwords are never logged."""
    try:
        profile = svc.login(
            body.username,
            body.password,
            body.clientToken,
            body.totp_token,
        )
    except svc.ElybyAuthError as e:
        raise _auth_error(e) from e

    return {
        "profile": {"username": profile["username"], "uuid": profile["uuid"]},
        "client_token": profile["client_token"],
    }


@router.post("/elyby/refresh")
def elyby_refresh(body: Optional[ElybyRefreshRequest] = None) -> Dict[str, Any]:
    """Refresh Ely.by access token using stored or supplied credentials."""
    try:
        profile = svc.refresh_session()
    except svc.ElybyAuthError as e:
        raise _auth_error(e) from e

    return {
        "profile": {"username": profile["username"], "uuid": profile["uuid"]},
        "client_token": profile.get("client_token"),
    }


@router.get("/elyby/profile")
def elyby_profile() -> Dict[str, Any]:
    """Return the currently stored Ely.by profile, if any."""
    profile = svc.get_public_profile()
    return {"profile": profile, "logged_in": profile is not None}


@router.post("/elyby/logout")
def elyby_logout() -> Dict[str, Any]:
    svc.logout()
    return {"logged_in": False}
