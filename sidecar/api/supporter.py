from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from sidecar.services import core_service, elyby_auth, hwid

WORKER_API_BASE = "https://phantomx-supporter-api.hoanglonggg79.workers.dev"

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


class RedeemRequest(BaseModel):
    key: str = Field(min_length=3, max_length=100)


# ── Verification & Persistence logic ──────────────────────────────────────────


def _verify_token(token: str) -> Dict[str, Any]:
    """
    Legacy RSA token decode and verify.
    Returns a dict with:
      { valid: bool, badge?: str, discord_id?: str, issued_at?: int, error?: str }
    """
    if _public_key is None:
        return {"valid": False, "error": "Public key unavailable — sidecar misconfigured"}

    if not token or not isinstance(token, str):
        return {"valid": False, "error": "Token is required"}

    try:
        padding_needed = (4 - len(token) % 4) % 4
        padded = token + "=" * padding_needed
        try:
            raw = base64.urlsafe_b64decode(padded)
        except Exception:
            return {"valid": False, "error": "Invalid token format: Base64URL decode failed"}

        null_idx = raw.find(b"\x00")
        if null_idx == -1:
            return {"valid": False, "error": "Invalid token format: missing null separator"}

        payload_bytes = raw[:null_idx]
        signature = raw[null_idx + 1:]

        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"valid": False, "error": "Invalid payload: not valid JSON"}

        try:
            _public_key.verify(signature, payload_bytes, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            return {"valid": False, "error": "Invalid signature"}
        except Exception as e:
            return {"valid": False, "error": f"Signature verification error: {e}"}

        return {
            "valid": True,
            "badge": payload.get("tier", "supporter"),
            "discord_id": payload.get("discord_id"),
            "issued_at": payload.get("issued_at"),
        }

    except Exception as e:
        logger.warning(f"Unexpected error during token verification: {e}")
        return {"valid": False, "error": f"Verification failed: {e}"}


def _persist_cloud_supporter(result: Dict[str, Any], key_code: str, hwid_hash: str) -> None:
    """Save active Cloudflare D1 supporter status to config.json for session restore."""
    try:
        cfg = core_service.load_config_raw()
        existing_supporter = cfg.get("supporter", {})
        theme = existing_supporter.get("theme", "default")
        cfg["supporter"] = {
            "active": True,
            "type": "cloud",
            "key_code": key_code.upper(),
            "hwid": hwid_hash,
            "badge": result.get("badge", "supporter"),
            "discord_id": result.get("discord_id"),
            "redeemed_at": result.get("redeemed_at") or datetime.now(timezone.utc).isoformat(),
            "theme": theme,
        }
        core_service.save_config_raw(cfg)
        logger.info(f"Cloud supporter badge persisted for discord_id={result.get('discord_id')} key={key_code}")
    except Exception as e:
        logger.error(f"Failed to persist supporter status: {e}")


def _persist_legacy_supporter(result: Dict[str, Any], token: str) -> None:
    """Save legacy RSA supporter status to config.json."""
    try:
        cfg = core_service.load_config_raw()
        existing_supporter = cfg.get("supporter", {})
        theme = existing_supporter.get("theme", "default")
        cfg["supporter"] = {
            "active": True,
            "type": "rsa_offline",
            "badge": result.get("badge", "supporter"),
            "discord_id": result.get("discord_id"),
            "redeemed_at": datetime.now(timezone.utc).isoformat(),
            "token": token,
            "theme": theme,
        }
        core_service.save_config_raw(cfg)
        logger.info(f"Legacy supporter badge persisted for discord_id={result.get('discord_id')}")
    except Exception as e:
        logger.error(f"Failed to persist legacy supporter status: {e}")


def _revoke_supporter() -> None:
    """Remove supporter status from config.json."""
    try:
        cfg = core_service.load_config_raw()
        cfg.pop("supporter", None)
        core_service.save_config_raw(cfg)
        logger.info("Supporter badge revoked and removed from local config")
    except Exception as e:
        logger.error(f"Failed to revoke supporter status: {e}")


# ── Cloudflare Worker Client ──────────────────────────────────────────────────


def _call_worker_redeem(key: str, hwid_hash: str, uuid: Optional[str] = None) -> Dict[str, Any]:
    """Call Cloudflare Worker POST /redeem endpoint."""
    url = f"{WORKER_API_BASE}/redeem"
    payload = {
        "key_code": key.strip().upper(),
        "hwid": hwid_hash,
        "uuid": uuid,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if resp.status_code == 200 and data.get("valid"):
            return data
        # Handle error responses
        err_msg = data.get("error", f"Redeem failed with status {resp.status_code}")
        return {
            "valid": False,
            "error": err_msg,
            "revoked": data.get("revoked", False),
            "hwid_mismatch": data.get("hwid_mismatch", False),
            "status_code": resp.status_code,
        }
    except requests.RequestException as e:
        logger.error(f"Network error calling Cloudflare Worker /redeem: {e}")
        return {
            "valid": False,
            "error": "Không thể kết nối đến máy chủ Cloudflare Supporter. Vui lòng kiểm tra kết nối mạng.",
            "network_error": True,
        }


def _check_worker_status_online(key_code: str, hwid_hash: str) -> Optional[Dict[str, Any]]:
    """
    Quick status check against Cloudflare Worker (timeout 3.5s).
    Returns response dict if reachable, or None if offline/timed out.
    """
    url = f"{WORKER_API_BASE}/verify"
    payload = {"key_code": key_code, "hwid": hwid_hash}
    try:
        resp = requests.post(url, json=payload, timeout=3.5)
        if resp.status_code in (200, 403, 404):
            return resp.json()
    except Exception as e:
        logger.debug(f"Online supporter sync skipped (offline or timeout): {e}")
    return None


# ── API Endpoints ─────────────────────────────────────────────────────────────


@router.post("/redeem")
def redeem_supporter(body: RedeemRequest) -> Dict[str, Any]:
    """
    POST /api/supporter/redeem
    Redeem a supporter key code (e.g. PX-XXXX-XXXX-XXXX) via Cloudflare Worker + HWID binding.
    """
    key = body.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail={"valid": False, "error": "Mã key không được để trống"})

    current_hwid = hwid.get_hwid_hash()

    # Get active Ely.by or player UUID if available
    active_uuid = None
    try:
        profile = elyby_auth.get_public_profile()
        if profile and profile.get("uuid"):
            active_uuid = profile["uuid"]
    except Exception:
        pass

    result = _call_worker_redeem(key, current_hwid, active_uuid)
    if result.get("valid"):
        _persist_cloud_supporter(result, key_code=key, hwid_hash=current_hwid)
        return {
            "valid": True,
            "badge": result.get("badge", "supporter"),
            "discord_id": result.get("discord_id"),
        }

    # Error handling with clear messages
    status_code = result.get("status_code", 400)
    raise HTTPException(
        status_code=status_code if status_code in (400, 403, 404, 429) else 400,
        detail={
            "valid": False,
            "error": result.get("error", "Kích hoạt key không thành công"),
            "revoked": result.get("revoked", False),
            "hwid_mismatch": result.get("hwid_mismatch", False),
        },
    )


@router.post("/verify")
def verify_supporter(body: VerifyRequest) -> Dict[str, Any]:
    """
    POST /api/supporter/verify
    Universal entry point:
    - If input is a key code (e.g. starts with 'PX-' or length < 50): delegates to Cloudflare Worker redeem.
    - If input is a legacy RSA-2048 offline token: performs offline RSA verification.
    """
    input_str = body.token.strip()

    # Auto-detect Cloud Key format
    if input_str.upper().startswith("PX-") or len(input_str) < 64:
        return redeem_supporter(RedeemRequest(key=input_str))

    # Fallback to Legacy RSA token verification
    result = _verify_token(input_str)
    if result["valid"]:
        _persist_legacy_supporter(result, token=input_str)
        return {
            "valid": True,
            "badge": result.get("badge", "supporter"),
            "discord_id": result.get("discord_id"),
        }

    raise HTTPException(
        status_code=400,
        detail={"valid": False, "error": result.get("error", "Token không hợp lệ")},
    )


@router.get("/status")
def get_supporter_status() -> Dict[str, Any]:
    """
    GET /api/supporter/status
    Restore supporter status with Online-to-Offline Caching:
    1. Read local config.json.
    2. If cloud supporter:
       - Validate HWID locally.
       - If online: sync with Cloudflare Worker. If revoked/blocked, auto-revoke local cache.
       - If offline: retain cached supporter badge and theme (100% offline-friendly).
    3. If legacy RSA token: verify RSA signature.
    """
    try:
        cfg = core_service.load_config_raw()
        supporter_data: Optional[Dict[str, Any]] = cfg.get("supporter")

        if not supporter_data or not supporter_data.get("active"):
            return {"active": False}

        supporter_type = supporter_data.get("type", "cloud" if "key_code" in supporter_data else "rsa_offline")

        # ── Case 1: Cloud Supporter (HWID + Serverless) ──────────────────────
        if supporter_type == "cloud" or "key_code" in supporter_data:
            key_code = supporter_data.get("key_code")
            saved_hwid = supporter_data.get("hwid")
            current_hwid = hwid.get_hwid_hash()

            # HWID integrity check
            if saved_hwid and saved_hwid != current_hwid:
                logger.warning("Supporter config HWID does not match current machine HWID. Rejecting.")
                return {"active": False, "hwid_mismatch": True}

            # Online sync (Fast 3.5s timeout, non-blocking if offline)
            if key_code and current_hwid:
                online_check = _check_worker_status_online(key_code, current_hwid)
                if online_check is not None:
                    # Server is reachable
                    if online_check.get("revoked"):
                        logger.warning(f"Supporter key {key_code} was revoked: {online_check.get('reason')}")
                        _revoke_supporter()
                        return {
                            "active": False,
                            "revoked": True,
                            "reason": online_check.get("reason", "Key đã bị thu hồi bởi quản trị viên"),
                        }
                    if not online_check.get("valid"):
                        logger.warning(f"Supporter key {key_code} is no longer valid on server")
                        _revoke_supporter()
                        return {"active": False}

            # Offline or Online Valid: Return active status
            return {
                "active": True,
                "badge": supporter_data.get("badge", "supporter"),
                "discord_id": supporter_data.get("discord_id"),
                "redeemed_at": supporter_data.get("redeemed_at"),
                "theme": supporter_data.get("theme", "default"),
                "key_code": key_code,
            }

        # ── Case 2: Legacy RSA Offline Token ─────────────────────────────────
        token = supporter_data.get("token")
        if not token or not isinstance(token, str):
            return {"active": False}

        verify_res = _verify_token(token)
        if not verify_res.get("valid"):
            logger.warning(f"Legacy supporter token failed RSA verification: {verify_res.get('error')}")
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
    Remove supporter badge from local config.
    """
    _revoke_supporter()
    return {"active": False, "revoked": True}
