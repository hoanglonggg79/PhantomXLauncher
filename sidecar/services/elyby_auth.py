from __future__ import annotations

import base64
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from loguru import logger

from sidecar.utils.path_resolver import get_base_dir, is_portable

ELYBY_AUTH_URL = "https://authserver.ely.by/auth/authenticate"
ELYBY_REFRESH_URL = "https://authserver.ely.by/auth/refresh"
ELYBY_INJECTOR_API = "https://authserver.ely.by/api/authlib-injector"

KEYRING_SERVICE = "PhantomXLauncher"
KEYRING_ACCESS = "elyby_access_token"
KEYRING_CLIENT = "elyby_client_token"
KEYRING_PROFILE = "elyby_profile_json"

PORTABLE_AUTH_FILE = "auth_elyby.json"
FERNET_SALT = b"PhantomX-Elyby-Portable-v1"

_session_cache: Optional[Dict[str, Any]] = None


class ElybyAuthError(Exception):
    def __init__(self, message: str, *, status: int = 400, code: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _normalize_uuid(raw: str) -> str:
    """Ely.by returns UUID without dashes; keep it dash-free for the game session."""
    return (raw or "").replace("-", "").lower()


def _portable_fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(FERNET_SALT + str(get_base_dir()).encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _portable_auth_path() -> Path:
    return get_base_dir() / PORTABLE_AUTH_FILE


def _keyring_available() -> bool:
    try:
        import keyring  # noqa: F401

        return True
    except Exception:
        return False


def _load_portable_blob() -> Dict[str, Any]:
    path = _portable_auth_path()
    if not path.is_file():
        return {}
    try:
        raw = path.read_bytes()
        decrypted = _portable_fernet().decrypt(raw)
        return json.loads(decrypted.decode("utf-8"))
    except Exception as e:
        logger.warning(f"Could not read portable Ely.by credentials: {e}")
        return {}


def _save_portable_blob(data: Dict[str, Any]) -> None:
    path = _portable_auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    encrypted = _portable_fernet().encrypt(payload)
    path.write_bytes(encrypted)


def _load_keyring_blob() -> Dict[str, Any]:
    if not _keyring_available():
        return {}
    import keyring

    access = keyring.get_password(KEYRING_SERVICE, KEYRING_ACCESS) or ""
    client = keyring.get_password(KEYRING_SERVICE, KEYRING_CLIENT) or ""
    profile_raw = keyring.get_password(KEYRING_SERVICE, KEYRING_PROFILE) or ""
    if not access or not client or not profile_raw:
        return {}
    try:
        profile = json.loads(profile_raw)
    except json.JSONDecodeError:
        return {}
    return {
        "access_token": access,
        "client_token": client,
        "username": profile.get("username", ""),
        "uuid": profile.get("uuid", ""),
    }


def _save_keyring_blob(data: Dict[str, Any]) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, KEYRING_ACCESS, data["access_token"])
    keyring.set_password(KEYRING_SERVICE, KEYRING_CLIENT, data["client_token"])
    profile = json.dumps({"username": data["username"], "uuid": data["uuid"]})
    keyring.set_password(KEYRING_SERVICE, KEYRING_PROFILE, profile)


def _clear_keyring_blob() -> None:
    if not _keyring_available():
        return
    import keyring

    for key in (KEYRING_ACCESS, KEYRING_CLIENT, KEYRING_PROFILE):
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except Exception:
            pass


def _load_stored() -> Dict[str, Any]:
    global _session_cache
    if _session_cache is not None:
        return dict(_session_cache)
    if is_portable():
        data = _load_portable_blob()
    else:
        data = _load_keyring_blob()
    _session_cache = dict(data) if data else None
    return dict(data) if data else {}


def _persist(data: Dict[str, Any]) -> None:
    global _session_cache
    _session_cache = dict(data)
    if is_portable():
        _save_portable_blob(data)
    else:
        _save_keyring_blob(data)


def clear_stored_credentials() -> None:
    global _session_cache
    _session_cache = None
    if is_portable():
        path = _portable_auth_path()
        if path.is_file():
            path.unlink(missing_ok=True)
    else:
        _clear_keyring_blob()


def save_elyby_credentials(
    access_token: str,
    client_token: str,
    username: str,
    uuid_value: str,
) -> None:
    _persist(
        {
            "access_token": access_token,
            "client_token": client_token,
            "username": username,
            "uuid": _normalize_uuid(uuid_value),
        }
    )
    logger.info(f"Ely.by session saved for {username}")


def get_session_credentials() -> Optional[Dict[str, str]]:
    data = _load_stored()
    if not data.get("access_token") or not data.get("client_token"):
        return None
    return {
        "access_token": data["access_token"],
        "client_token": data["client_token"],
        "username": data.get("username", ""),
        "uuid": _normalize_uuid(data.get("uuid", "")),
    }


def get_public_profile() -> Optional[Dict[str, str]]:
    creds = get_session_credentials()
    if not creds or not creds.get("username"):
        return None
    return {"username": creds["username"], "uuid": creds["uuid"]}


def _post_json(url: str, payload: Dict[str, Any], timeout: int = 30) -> requests.Response:
    try:
        return requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
    except requests.Timeout as e:
        raise ElybyAuthError(
            "Máy chủ Ely.by không phản hồi (timeout). Vui lòng thử lại sau.",
            status=503,
        ) from e
    except requests.RequestException as e:
        raise ElybyAuthError(
            "Không thể kết nối tới Ely.by. Kiểm tra mạng và thử lại.",
            status=503,
        ) from e


def login(
    username: str,
    password: str,
    client_token: str,
    totp_token: Optional[str] = None,
) -> Dict[str, Any]:
    user = (username or "").strip()
    if not user or not password:
        raise ElybyAuthError("Vui lòng nhập tên đăng nhập và mật khẩu.")

    password_payload = password if not totp_token else f"{password}:{totp_token.strip()}"
    token = client_token.strip() or str(uuid.uuid4())

    body = {
        "agent": {"name": "Minecraft", "version": 1},
        "username": user,
        "password": password_payload,
        "clientToken": token,
        "requestUser": True,
    }

    resp = _post_json(ELYBY_AUTH_URL, body)

    if resp.status_code == 401:
        try:
            err = resp.json()
        except Exception:
            err = {}
        msg = str(err.get("errorMessage") or err.get("error") or "")
        if "two factor" in msg.lower() or "2fa" in msg.lower():
            raise ElybyAuthError(
                "Vui lòng nhập mã xác thực 2 bước",
                status=401,
                code="2FA_REQUIRED",
            )
        raise ElybyAuthError(msg or "Sai tên đăng nhập hoặc mật khẩu.", status=401)

    if resp.status_code >= 500:
        raise ElybyAuthError(
            "Máy chủ Ely.by đang quá tải, vui lòng thử lại sau.",
            status=503,
        )

    if not resp.ok:
        try:
            err = resp.json()
            detail = err.get("errorMessage") or err.get("error") or resp.text
        except Exception:
            detail = resp.text or "Đăng nhập thất bại."
        raise ElybyAuthError(str(detail), status=resp.status_code)

    data = resp.json()
    access = data.get("accessToken") or ""
    selected = data.get("selectedProfile") or {}
    profile_name = selected.get("name") or user
    profile_id = _normalize_uuid(selected.get("id") or "")
    returned_client = data.get("clientToken") or token

    if not access or not profile_id:
        raise ElybyAuthError("Phản hồi Ely.by không hợp lệ (thiếu token hoặc profile).")

    save_elyby_credentials(access, returned_client, profile_name, profile_id)

    return {
        "username": profile_name,
        "uuid": profile_id,
        "client_token": returned_client,
    }


def refresh_session() -> Dict[str, Any]:
    creds = get_session_credentials()
    if not creds:
        raise ElybyAuthError("Chưa có phiên Ely.by. Vui lòng đăng nhập lại.", status=401)

    body = {
        "accessToken": creds["access_token"],
        "clientToken": creds["client_token"],
        "requestUser": True,
    }
    resp = _post_json(ELYBY_REFRESH_URL, body)

    if resp.status_code == 401:
        clear_stored_credentials()
        raise ElybyAuthError("Phiên đã hết hạn. Vui lòng đăng nhập lại.", status=401)

    if resp.status_code >= 500:
        raise ElybyAuthError(
            "Máy chủ Ely.by đang quá tải, vui lòng thử lại sau.",
            status=503,
        )

    if not resp.ok:
        clear_stored_credentials()
        raise ElybyAuthError("Không thể làm mới phiên. Vui lòng đăng nhập lại.", status=401)

    data = resp.json()
    access = data.get("accessToken") or creds["access_token"]
    selected = data.get("selectedProfile") or {}
    username = selected.get("name") or creds["username"]
    profile_id = _normalize_uuid(selected.get("id") or creds["uuid"])
    client = data.get("clientToken") or creds["client_token"]

    save_elyby_credentials(access, client, username, profile_id)
    return {"username": username, "uuid": profile_id, "client_token": client}


def logout() -> None:
    clear_stored_credentials()
    logger.info("Ely.by session cleared")
