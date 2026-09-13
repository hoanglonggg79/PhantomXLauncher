from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from loguru import logger

from sidecar.services.core_service import get_core

GITHUB_REPO = "hoanglonggg79/PhantomXLauncher"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=10"
CACHE_TTL_SECS = 3600  # 1 hour

_cache: Optional[Dict[str, Any]] = None
_cache_time: float = 0


def _parse_version_tuple(v: str) -> tuple[int, ...]:
    """Extract numeric parts for version comparison (e.g. 'v1.1.1' -> (1, 1, 1))."""
    import re
    cleaned = re.sub(r"^[^\d]*", "", (v or "").strip())
    parts = []
    for chunk in cleaned.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            break
    return tuple(parts) or (0,)


def get_changelog(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Retrieve releases and changelog information.
    Uses in-memory cache unless force_refresh is True or cache has expired.
    """
    global _cache, _cache_time

    core = get_core()
    current_version = getattr(core, "APP_VERSION", "1.2.0")

    now = time.time()
    if not force_refresh and _cache is not None and (now - _cache_time < CACHE_TTL_SECS):
        return _cache

    releases_data: List[Dict[str, Any]] = []
    try:
        logger.info(f"Fetching changelog from GitHub Releases: {RELEASES_API}")
        req = urllib.request.Request(
            RELEASES_API,
            headers={
                "User-Agent": f"PhantomX-Launcher/{current_version}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            releases_data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Could not fetch releases from GitHub: {e}")
        # If cache exists, return it even if expired
        if _cache is not None:
            return _cache
        # Otherwise return offline fallback
        return {
            "releases": [],
            "current_version": current_version,
            "has_update": False,
            "latest_version": current_version,
            "repo_url": f"https://github.com/{GITHUB_REPO}",
            "offline": True,
            "error": str(e),
        }

    formatted_releases: List[Dict[str, Any]] = []
    current_v_tuple = _parse_version_tuple(current_version)
    latest_tag = current_version
    has_update = False

    for idx, r in enumerate(releases_data):
        tag = (r.get("tag_name") or "").strip()
        v_tuple = _parse_version_tuple(tag)
        is_current = (tag.lstrip("v") == current_version.lstrip("v")) or (v_tuple == current_v_tuple)
        
        # Check if first non-prerelease release is newer than current
        if idx == 0 and not r.get("prerelease", False):
            latest_tag = tag
            if v_tuple > current_v_tuple:
                has_update = True

        formatted_releases.append(
            {
                "tag": tag,
                "name": r.get("name") or tag,
                "published_at": r.get("published_at") or "",
                "html_url": r.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases",
                "body": r.get("body") or "No release notes provided.",
                "prerelease": r.get("prerelease", False),
                "is_current": is_current,
            }
        )

    result = {
        "releases": formatted_releases,
        "current_version": current_version,
        "has_update": has_update,
        "latest_version": latest_tag,
        "repo_url": f"https://github.com/{GITHUB_REPO}",
        "offline": False,
    }

    _cache = result
    _cache_time = now
    return result


VERSION_TXT_URL = "https://raw.githubusercontent.com/hoanglonggg79/PhantomXLauncher/refs/heads/main/version.txt"


def check_version_update() -> Dict[str, Any]:
    """
    Check if a newer version exists by comparing with raw version.txt on GitHub.
    Returns current version, latest version, has_update flag, and repo URL.
    """
    core = get_core()
    current_version = getattr(core, "APP_VERSION", "1.2.0").strip()
    current_tuple = _parse_version_tuple(current_version)

    latest_version = current_version
    has_update = False
    error = None

    try:
        req = urllib.request.Request(
            VERSION_TXT_URL,
            headers={
                "User-Agent": f"PhantomX-Launcher/{current_version}",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read().decode("utf-8").strip()
            if content:
                latest_version = content
                latest_tuple = _parse_version_tuple(latest_version)
                if latest_tuple > current_tuple:
                    has_update = True
    except Exception as e:
        logger.warning(f"Could not check version.txt from GitHub: {e}")
        error = str(e)

    return {
        "current_version": current_version,
        "latest_version": latest_version,
        "has_update": has_update,
        "repo_url": f"https://github.com/{GITHUB_REPO}",
        "releases_url": f"https://github.com/{GITHUB_REPO}/releases",
        "error": error,
    }

