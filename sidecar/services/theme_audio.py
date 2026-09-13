from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

from loguru import logger
import requests

from sidecar.utils import path_resolver

THEME_MUSIC_URL = "https://github.com/hoanglonggg79/storage/releases/download/010/theme.mp3"
_download_lock = threading.Lock()


def get_theme_dir() -> Path:
    base = path_resolver.get_base_dir()
    theme_dir = base / "theme"
    theme_dir.mkdir(parents=True, exist_ok=True)
    return theme_dir


def get_theme_file_path() -> Path:
    return get_theme_dir() / "theme.mp3"


def is_theme_downloaded() -> bool:
    target = get_theme_file_path()
    return target.exists() and target.stat().st_size > 50000


def ensure_theme_audio(force: bool = False) -> Dict[str, Any]:
    """
    Downloads theme.mp3 if not already present.
    Thread-safe and non-blocking when called from background threads.
    """
    target = get_theme_file_path()
    if not force and is_theme_downloaded():
        return {
            "ready": True,
            "path": str(target),
            "size": target.stat().st_size,
            "message": "Theme music ready",
        }

    with _download_lock:
        if not force and is_theme_downloaded():
            return {
                "ready": True,
                "path": str(target),
                "size": target.stat().st_size,
                "message": "Theme music ready",
            }

        logger.info(f"Downloading theme music from {THEME_MUSIC_URL}...")
        try:
            r = requests.get(THEME_MUSIC_URL, timeout=30, stream=True)
            if r.status_code != 200:
                return {
                    "ready": False,
                    "error": f"HTTP {r.status_code} while downloading theme",
                }

            tmp_target = target.with_suffix(".tmp_download")
            with open(tmp_target, "wb") as f:
                for chunk in r.iter_content(chunk_size=32768):
                    if chunk:
                        f.write(chunk)

            tmp_target.replace(target)
            logger.info(f"Theme music downloaded successfully ({target.stat().st_size} bytes)")
            return {
                "ready": True,
                "path": str(target),
                "size": target.stat().st_size,
                "message": "Theme music downloaded successfully",
            }
        except Exception as e:
            logger.warning(f"Failed to download theme music: {e}")
            return {
                "ready": False,
                "error": str(e),
            }
