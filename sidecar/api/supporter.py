from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from sidecar.services import core_service

SUPPORTER_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArXoH8vIMorBF73KP4oH9
qyyIUgANCTBBkg3HUn3Bl+vu3T+cBk7iVgJA1S9SDtDJagQw0dCu2Nd+/7IUKI1p
ouZyKeWxRdYRngDbA0DqPn7Ooumd/r/h734kjhz668SGXwLmI3UIH0UrhTslmyQd
illpm9NyC7hWW7i3o1btZWdzJcKs1Efzx9jBl1UYx+ER7odgAv2BRwat19yPITsW
tODCZP5j03pFuQMUOEq7PjyrKnTKKltrK0MOloRhJ2EMINTjugWITNjsDHxIn8/o
RxQ58x5qCTS8gGCPtnllJtrR9kAVu4h9BPqIyrVxKjrNT9/inVVnKn7uX36RvIcm
/wIDAQAB
-----END PUBLIC KEY-----"""

try:
    _public_key = serialization.load_pem_public_key(SUPPORTER_PUBLIC_KEY_PEM.encode("utf-8"))
    logger.debug("Supporter public key loaded successfully")
except Exception as e:
    _public_key = None
    logger.error(f"Failed to load supporter public key: {e}")

# ── Request / Response models ─────────────────────────────────────────────────

router = APIRouter(tags=["supporter"])


class VerifyRequest(BaseModel):
    token: str = Field(min_length=1, max_length=2048)


# ── Verification logic ────────────────────────────────────────────────────────


def _verify_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify a supporter token.

    Returns a dict with:
      { valid: bool, badge?: str, discord_id?: str, issued_at?: int, error?: str }
    """
    if _public_key is None:
        return {"valid": False, "error": "Public key unavailable — sidecar misconfigured"}

    if not token or not isinstance(token, str):
        return {"valid": False, "error": "Token is required"}

    try:
        # Decode Base64URL (urlsafe, auto-pad)
        padding_needed = (4 - len(token) % 4) % 4
        padded = token + "=" * padding_needed
        try:
            raw = base64.urlsafe_b64decode(padded)
        except Exception:
            return {"valid": False, "error": "Invalid token format: Base64URL decode failed"}

        # Split at null byte — payload | 0x00 | RSA signature
        null_idx = raw.find(b"\x00")
        if null_idx == -1:
            return {"valid": False, "error": "Invalid token format: missing null separator"}

        payload_bytes = raw[:null_idx]
        signature = raw[null_idx + 1:]

        # Parse JSON payload
        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"valid": False, "error": "Invalid payload: not valid JSON"}

        # RSA-SHA256-PKCS1v15 verification
        try:
            _public_key.verify(signature, payload_bytes, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            return {"valid": False, "error": "Invalid signature"}
        except Exception as e:
            return {"valid": False, "error": f"Signature verification error: {e}"}

        # Token valid
        return {
            "valid": True,
            "badge": payload.get("tier", "supporter"),
            "discord_id": payload.get("discord_id"),
            "issued_at": payload.get("issued_at"),
        }

    except Exception as e:
        logger.warning(f"Unexpected error during token verification: {e}")
        return {"valid": False, "error": f"Verification failed: {e}"}


def _persist_supporter(result: Dict[str, Any], token: str) -> None:
    """Save active supporter status to config.json for session restore."""
    try:
        cfg = core_service.load_config_raw()
        existing_supporter = cfg.get("supporter", {})
        theme = existing_supporter.get("theme", "default")
        cfg["supporter"] = {
            "active": True,
            "badge": result.get("badge", "supporter"),
            "discord_id": result.get("discord_id"),
            "redeemed_at": datetime.now(timezone.utc).isoformat(),
            "token": token,
            "theme": theme,
        }
        core_service.save_config_raw(cfg)
        logger.info(f"Supporter badge persisted for discord_id={result.get('discord_id')}")
    except Exception as e:
        logger.error(f"Failed to persist supporter status: {e}")


def _revoke_supporter() -> None:
    """Remove supporter status from config.json."""
    try:
        cfg = core_service.load_config_raw()
        cfg.pop("supporter", None)
        core_service.save_config_raw(cfg)
        logger.info("Supporter badge revoked")
    except Exception as e:
        logger.error(f"Failed to revoke supporter status: {e}")


# ── API Endpoints ─────────────────────────────────────────────────────────────


@router.post("/verify")
def verify_supporter(body: VerifyRequest) -> Dict[str, Any]:
    """
    POST /api/supporter/verify
    Accepts { "token": string }.
    100% offline RSA-2048 verification — no network calls.

    Returns:
        200: { "valid": true, "badge": "supporter", "discord_id": "..." }
        400: { "valid": false, "error": "..." }
    """
    result = _verify_token(body.token)

    if result["valid"]:
        _persist_supporter(result, token=body.token)
        # Return only public fields to frontend
        return {
            "valid": True,
            "badge": result.get("badge", "supporter"),
            "discord_id": result.get("discord_id"),
        }

    # Verification failed — raise 400
    raise HTTPException(
        status_code=400,
        detail={"valid": False, "error": result.get("error", "Invalid token")},
    )


@router.get("/status")
def get_supporter_status() -> Dict[str, Any]:
    """
    GET /api/supporter/status
    Read the persisted supporter status from config.json.
    Verifies the RSA-2048 token against the public key every time to prevent manual tampering.

    Returns: { "active": bool, "badge"?, "discord_id"?, "redeemed_at"?, "theme"? }
    """
    try:
        cfg = core_service.load_config_raw()
        supporter_data: Optional[Dict[str, Any]] = cfg.get("supporter")

        if not supporter_data or not supporter_data.get("active"):
            return {"active": False}

        token = supporter_data.get("token")
        if not token or not isinstance(token, str):
            logger.warning("Supporter status in config.json is missing a valid token. Rejecting.")
            return {"active": False}

        verify_res = _verify_token(token)
        if not verify_res.get("valid"):
            logger.warning(
                f"Supporter token failed RSA verification during status check: {verify_res.get('error')}"
            )
            return {"active": False}

        return {
            "active": True,
            "badge": verify_res.get("badge", supporter_data.get("badge", "supporter")),
            "discord_id": verify_res.get("discord_id", supporter_data.get("discord_id")),
            "redeemed_at": supporter_data.get("redeemed_at"),
            "theme": supporter_data.get("theme", "default"),
        }
    except Exception as e:
        logger.warning(f"Error reading supporter status: {e}")
        return {"active": False}


class ThemeRequest(BaseModel):
    theme: str = Field(pattern="^(default|cyberpunk|synthwave)$")


@router.put("/theme")
def update_supporter_theme(body: ThemeRequest) -> Dict[str, Any]:
    """
    PUT /api/supporter/theme
    Persist chosen supporter theme in config.json.
    """
    try:
        cfg = core_service.load_config_raw()
        supporter_data = cfg.get("supporter", {})
        supporter_data["theme"] = body.theme
        cfg["supporter"] = supporter_data
        core_service.save_config_raw(cfg)
        logger.info(f"Supporter theme updated to '{body.theme}'")
        return {"ok": True, "theme": body.theme}
    except Exception as e:
        logger.error(f"Failed to save supporter theme: {e}")
        raise HTTPException(status_code=500, detail="Failed to save theme")


@router.delete("/revoke")
def revoke_supporter() -> Dict[str, Any]:
    """
    DELETE /api/supporter/revoke
    Remove supporter badge from local config (cosmetic revoke, no server call).
    """
    _revoke_supporter()
    return {"active": False, "revoked": True}

