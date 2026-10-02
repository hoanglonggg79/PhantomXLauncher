"""
PhantomX Sidecar — Supporter state (offline-first).

This module is the *service layer* twin of `sidecar/api/supporter.py`: it owns
everything that can be answered from local state alone (config.json + HWID +
RSA signature), with **no network calls**.

Keeping it here matters because the launch path needs the supporter flag to
build the Discord "in_game" presence. `instances._launch()` must not block on a
Cloudflare round-trip — and before this module existed it imported
`sidecar.services.supporter`, which did not exist, so the RPC update silently
failed with "cannot import name 'supporter'".

The online re-validation (revoke check against the Worker) stays in the API
layer, which is allowed to be slow.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, Optional

from loguru import logger

from sidecar.services.core_service import load_config_raw

SUPPORTER_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArXoH8vIMorBF73KP4oH9
qyyIUgANCTBBkg3HUn3Bl+vu3T+cBk7iVgJA1S9SDtDJagQw0dCu2Nd+/7IUKI1p
ouZyKeWxRdYRngDbA0DqPn7Ooumd/r/h734kjhz668SGXwLmI3UIH0UrhTslmyQd
illpm9NyC7hWW7i3o1btZWdzJcKs1Efzx9jBl1UYx+ER7odgAv2BRwat19yPITsW
tODCZP5j03pFuQMUOEq7PjyrKnTKKltrK0MOloRhJ2EMINTjugWITNjsDHxIn8/o
RxQ58x5qCTS8gGCPtnllJtrR9kAVu4h9BPqIyrVxKjrNT9/inVVnKn7uX36RvIcm
/wIDAQAB
-----END PUBLIC KEY-----"""

_crypto_error: Optional[str] = None
try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    _public_key = serialization.load_pem_public_key(
        SUPPORTER_PUBLIC_KEY_PEM.encode("utf-8")
    )
    logger.debug("Supporter public key loaded successfully")
except Exception as e:  # pragma: no cover - cryptography is a hard dependency
    _public_key = None
    _crypto_error = str(e)
    logger.error(f"Failed to load supporter public key: {e}")


# ── Local read ────────────────────────────────────────────────────────────────


def get_supporter_config() -> Dict[str, Any]:
    """Raw `supporter` block from config.json ({} when absent/invalid)."""
    try:
        cfg = load_config_raw()
    except Exception as e:
        logger.debug(f"Could not read config for supporter state: {e}")
        return {}

    data = cfg.get("supporter")
    return data if isinstance(data, dict) else {}


def verify_token(token: str) -> Dict[str, Any]:
    """
    Legacy RSA-2048 offline token decode + signature verify.

    Returns `{ valid: bool, badge?, discord_id?, issued_at?, error? }`.
    """
    if _public_key is None:
        return {
            "valid": False,
            "error": f"Public key unavailable — sidecar misconfigured ({_crypto_error})",
        }
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
        signature = raw[null_idx + 1 :]

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


def _hwid_matches(data: Dict[str, Any]) -> bool:
    """HWID binding check for cloud supporter keys (fails open when unavailable)."""
    saved_hwid = data.get("hwid")
    if not saved_hwid:
        return True
    try:
        from sidecar.services.hwid import get_hwid_hash

        return saved_hwid == get_hwid_hash()
    except Exception as e:
        logger.debug(f"HWID check skipped: {e}")
        return True


def get_supporter_status() -> Dict[str, Any]:
    """
    Offline supporter status, safe to call from the launch path.

    Always returns both `active` and `valid` keys:
      * `active` — what the API layer / UI uses;
      * `valid`  — alias kept for `instances._launch()` and the Discord RPC.
    """
    try:
        data = get_supporter_config()
        if not data or not data.get("active"):
            return {"active": False, "valid": False}

        is_cloud = data.get("type", "cloud") == "cloud" or "key_code" in data

        if is_cloud:
            if not _hwid_matches(data):
                logger.warning(
                    "Supporter config HWID does not match this machine — treating as inactive"
                )
                return {"active": False, "valid": False, "hwid_mismatch": True}

            return {
                "active": True,
                "valid": True,
                "badge": data.get("badge", "supporter"),
                "discord_id": data.get("discord_id"),
                "redeemed_at": data.get("redeemed_at"),
                "theme": data.get("theme", "default"),
                "key_code": data.get("key_code"),
                "type": "cloud",
            }

        # Legacy RSA token
        token = data.get("token")
        if not token or not isinstance(token, str):
            return {"active": False, "valid": False}

        result = verify_token(token)
        if not result.get("valid"):
            logger.warning(f"Legacy supporter token rejected: {result.get('error')}")
            return {"active": False, "valid": False, "error": result.get("error")}

        return {
            "active": True,
            "valid": True,
            "badge": result.get("badge", data.get("badge", "supporter")),
            "discord_id": result.get("discord_id", data.get("discord_id")),
            "redeemed_at": data.get("redeemed_at"),
            "theme": data.get("theme", "default"),
            "type": "rsa_offline",
        }
    except Exception as e:
        logger.warning(f"Error reading local supporter status: {e}")
        return {"active": False, "valid": False, "error": str(e)}


def is_supporter() -> bool:
    """Fast boolean used by the Discord RPC presence update."""
    try:
        return bool(get_supporter_status().get("valid", False))
    except Exception:
        return False


__all__ = [
    "SUPPORTER_PUBLIC_KEY_PEM",
    "get_supporter_config",
    "get_supporter_status",
    "is_supporter",
    "verify_token",
]
