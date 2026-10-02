from __future__ import annotations

import sys
import os
from pathlib import Path

# Inject scr/ into sys.path so we can import core
_SIDECAR_ROOT = Path(__file__).parent
_PROJECT_ROOT = _SIDECAR_ROOT.parent
_SCR_DIR = _PROJECT_ROOT / "scr"

if str(_SCR_DIR) not in sys.path:
    sys.path.insert(0, str(_SCR_DIR))

# Now import from scr.core
# The surgical import guard we added ensures this works without PyQt6
try:
    from scr.core import (
        MinecraftManager,
        Instance,
        DiscordPresence,
        APP_NAME,
        APP_VERSION,
        APP_AUTHOR,
        BASE_DIR,
        LOG_DIR,
        INST_DIR,
        CONFIG_FILE,
        KEYRING_SVC,
        KEYRING_AVAILABLE,
        PSUTIL_AVAILABLE,
        QT_AVAILABLE,
    )
except ImportError:
    from core import (
        MinecraftManager,
        Instance,
        DiscordPresence,
        APP_NAME,
        APP_VERSION,
        APP_AUTHOR,
        BASE_DIR,
        LOG_DIR,
        INST_DIR,
        CONFIG_FILE,
        KEYRING_SVC,
        KEYRING_AVAILABLE,
        PSUTIL_AVAILABLE,
        QT_AVAILABLE,
    )


def check_java(java_path: str = "") -> dict:
    """
    Java status as a dict, for /api/system/diagnostics.

    `MinecraftManager.check_java()` returns a (bool, str) tuple meant for the UI
    badge; diagnostics needs the resolved path and major version too. Kept here
    so the diagnostics module can call `core.check_java()` without building its
    own manager (and without tripping over core.py's logger setup).

    Returns ``{ok, message, path, major}`` — never raises.
    """
    try:
        import json as _json

        # Reuse the shared manager: constructing a fresh MinecraftManager() would
        # create BASE_DIR/default as a side effect of a read-only diagnostics call.
        try:
            from sidecar.services.core_service import get_manager

            manager = get_manager()
        except Exception:
            manager = MinecraftManager()

        path = (java_path or "").strip()

        # No explicit path: fall back to the one saved in config.json, otherwise
        # `check_java()` below resolves it — but we still need it for `major`.
        if not path and CONFIG_FILE.exists():
            try:
                cfg = _json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                path = str(cfg.get("java_path") or "").strip()
            except Exception:
                path = ""

        ok, message = manager.check_java(path)

        if not (path and Path(path).is_file()):
            path = manager.find_java() or path

        major = manager.java_version(path) if path and Path(path).is_file() else None

        # Last resort: the scan in the java service sees runtimes that
        # `find_java()` misses (managed jre-XX folders, Adoptium, Zulu, …).
        if major is None or not path:
            try:
                from sidecar.services.java import scan_java_installations

                installs = [i for i in scan_java_installations() if i.get("path")]
                if installs:
                    best = max(installs, key=lambda i: i.get("major") or 0)
                    if not path:
                        path = best["path"]
                        ok, message = True, f"✅ Java {best.get('major')} — {path}"
                    if major is None:
                        major = best.get("major")
            except Exception:
                pass

        return {
            "ok": bool(ok),
            "message": message,
            "path": path or "",
            "major": major,
        }
    except Exception as exc:  # diagnostics must never fail the whole report
        return {"ok": False, "message": str(exc), "path": "", "major": None}


if "_CF_API_KEY" in os.environ and "CF_API_KEY" not in os.environ:
    os.environ["CF_API_KEY"] = os.environ["_CF_API_KEY"]

# Similarly for _USER_AGENT and _MAX_CONCURRENT (used by ui_modpack.py, not core.py yet)
if "_USER_AGENT" in os.environ and "USER_AGENT" not in os.environ:
    os.environ["USER_AGENT"] = os.environ["_USER_AGENT"]
if "_MAX_CONCURRENT" in os.environ and "MAX_CONCURRENT" not in os.environ:
    os.environ["MAX_CONCURRENT"] = os.environ["_MAX_CONCURRENT"]

# core.py runs logger.remove() at import time, which drops the sidecar's sinks.
# Re-apply them so logs keep landing in the storage root instead of core's own file.
from sidecar.logging_config import configure_logging  # noqa: E402

configure_logging()

__all__ = [
    "MinecraftManager",
    "Instance",
    "check_java",
    "DiscordPresence",
    "APP_NAME",
    "APP_VERSION",
    "APP_AUTHOR",
    "BASE_DIR",
    "LOG_DIR",
    "INST_DIR",
    "CONFIG_FILE",
    "KEYRING_SVC",
    "KEYRING_AVAILABLE",
    "PSUTIL_AVAILABLE",
    "QT_AVAILABLE",
]
