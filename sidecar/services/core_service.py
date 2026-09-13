from __future__ import annotations

import json
import threading
from typing import Any, Dict

from loguru import logger

from sidecar.logging_config import configure_logging

_core = None
_manager = None
_lock = threading.Lock()

DEFAULT_SETTINGS: Dict[str, Any] = {
    "username": "Player",
    "ram": 2048,
    "java_path": "",
    "extra_jvm": "",
    "snapshots": False,
    "close_on_launch": False,
    "auth_mode": "offline",
    "bg_music_enabled": True,
    "bg_music_volume": 0.7,
    "discord_rpc_enabled": True,
}


def get_core():
    """
    Import core_bridge on first use. core.py calls logger.remove() at import time,
    so sidecar logging is re-applied immediately afterwards.
    """
    global _core
    if _core is None:
        with _lock:
            if _core is None:
                from sidecar import core_bridge

                configure_logging()
                _core = core_bridge
                logger.info(
                    f"core loaded (QT_AVAILABLE={core_bridge.QT_AVAILABLE}, "
                    f"BASE_DIR={core_bridge.BASE_DIR})"
                )
    return _core


def get_manager():
    """Shared MinecraftManager. Per-call game_dir arguments keep it stateless enough."""
    global _manager
    if _manager is None:
        core = get_core()
        with _lock:
            if _manager is None:
                _manager = core.MinecraftManager()
    return _manager


def load_settings() -> Dict[str, Any]:
    """config.json merged over defaults. Unknown keys from the legacy app are kept."""
    core = get_core()
    cfg = dict(DEFAULT_SETTINGS)
    try:
        if core.CONFIG_FILE.exists():
            cfg.update(json.loads(core.CONFIG_FILE.read_text(encoding="utf-8")))
    except Exception as e:
        logger.warning(f"config.json unreadable, using defaults: {e}")
    return cfg


def save_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Merge a partial update into config.json without dropping legacy keys."""
    core = get_core()
    current: Dict[str, Any] = {}
    try:
        if core.CONFIG_FILE.exists():
            current = json.loads(core.CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"config.json unreadable before save: {e}")

    current.update({k: v for k, v in patch.items() if v is not None})
    core.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    core.CONFIG_FILE.write_text(
        json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"Settings saved: {sorted(patch.keys())}")

    merged = dict(DEFAULT_SETTINGS)
    merged.update(current)
    return merged


def load_config_raw() -> Dict[str, Any]:
    """
    Read config.json as-is (no defaults merged).
    Returns an empty dict if the file is missing or unreadable.
    Used by modules (e.g., supporter badge) that need raw config access.
    """
    core = get_core()
    try:
        if core.CONFIG_FILE.exists():
            return json.loads(core.CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"config.json unreadable in load_config_raw: {e}")
    return {}


def save_config_raw(data: Dict[str, Any]) -> None:
    """
    Write data to config.json, replacing the file entirely.
    The caller is responsible for merging with the existing config first.
    Used by modules (e.g., supporter badge) that need full config control.
    """
    core = get_core()
    try:
        core.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        core.CONFIG_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.debug("config.json updated via save_config_raw")
    except Exception as e:
        logger.error(f"Failed to write config.json in save_config_raw: {e}")
        raise


def app_info() -> Dict[str, Any]:
    core = get_core()
    ok, java_msg = get_manager().check_java()
    return {
        "app_name": core.APP_NAME,
        "app_version": core.APP_VERSION,
        "app_author": core.APP_AUTHOR,
        "base_dir": str(core.BASE_DIR),
        "instances_dir": str(core.INST_DIR),
        "log_dir": str(core.LOG_DIR),
        "qt_available": core.QT_AVAILABLE,
        "keyring_available": core.KEYRING_AVAILABLE,
        "psutil_available": core.PSUTIL_AVAILABLE,
        "java_ok": ok,
        "java_status": java_msg,
    }
