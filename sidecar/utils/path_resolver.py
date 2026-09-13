from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

APP_NAME = "PhantomX"
APP_AUTHOR = "PhantomXTeam"

PORTABLE_MARKER = "portable.txt"
PORTABLE_DIRNAME = "PhantomXData"
ENV_OVERRIDE = "PHANTOMX_DATA_DIR"


def get_executable_dir() -> Path:
    """
    The directory the application was launched from.

    Frozen (Nuitka standalone / PyInstaller): the folder holding the executable.
    Dev: the project root, i.e. the parent of the `sidecar` package.

    `sys._MEIPASS` is never used as the data root — under PyInstaller onefile it
    is a temp extraction dir wiped on exit — but it is still searched for the
    marker file, since a bundled portable.txt lands there.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _marker_dirs() -> List[Path]:
    """Directories searched for portable.txt, in priority order, de-duplicated."""
    candidates = [get_executable_dir()]

    meipass = getattr(sys, "_MEIPASS", "") or ""
    if meipass:
        candidates.append(Path(meipass))

    seen: set[str] = set()
    unique: List[Path] = []
    for path in candidates:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


@lru_cache(maxsize=1)
def is_portable() -> bool:
    """True when a portable.txt marker exists beside the executable."""
    return any((base / PORTABLE_MARKER).is_file() for base in _marker_dirs())


@lru_cache(maxsize=1)
def get_base_dir() -> Path:
    """
    Absolute storage root. Always absolute, never relative: the sidecar's cwd is
    chosen by the Tauri shell, so a relative root would resolve differently
    depending on how the process was started.
    """
    override = (os.environ.get(ENV_OVERRIDE) or "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if is_portable():
        return (get_executable_dir() / PORTABLE_DIRNAME).resolve()

    try:
        from platformdirs import user_data_dir

        return Path(user_data_dir(APP_NAME, APP_AUTHOR))
    except Exception:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local) / APP_AUTHOR / APP_NAME


def get_log_dir() -> Path:
    return get_base_dir() / "logs"


def get_instances_dir() -> Path:
    return get_base_dir() / "instances"


def get_runtimes_dir() -> Path:
    return get_base_dir() / "runtimes"


def get_cache_dir() -> Path:
    return get_base_dir() / "cache"


def get_config_file() -> Path:
    return get_base_dir() / "config.json"


def ensure_dirs() -> Path:
    """Create the storage tree if missing and return the root."""
    base = get_base_dir()
    for path in (base, get_log_dir(), get_instances_dir(), get_runtimes_dir()):
        path.mkdir(parents=True, exist_ok=True)
    return base


def reset_cache() -> None:
    """Drop memoized results. Only needed by tests that change the environment."""
    is_portable.cache_clear()
    get_base_dir.cache_clear()


def describe() -> Dict[str, Any]:
    """Diagnostic snapshot, surfaced by /api/settings/info."""
    return {
        "portable": is_portable(),
        "executable_dir": str(get_executable_dir()),
        "base_dir": str(get_base_dir()),
        "instances_dir": str(get_instances_dir()),
        "log_dir": str(get_log_dir()),
        "config_file": str(get_config_file()),
        "override_env": ENV_OVERRIDE if (os.environ.get(ENV_OVERRIDE) or "").strip() else "",
    }
