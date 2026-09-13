from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from sidecar.services.instances import (
    InstanceError,
    require_instance_dir,
)
from sidecar.utils.file_ops import safe_delete, safe_rename
import os
import platform
import subprocess

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOD_EXT = ".jar"
DISABLED_EXT = ".jar.disabled"

# Whitelist: only names that end with these suffixes are treated as mods.
VALID_SUFFIXES = (MOD_EXT, DISABLED_EXT)

# Reject path traversal and Windows-reserved names in mod filenames.
_UNSAFE_RE = re.compile(r'[\\/:<>"|?*\x00-\x1f]')
_RESERVED_RE = re.compile(
    r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\.|$)", re.IGNORECASE
)
_MAX_FILENAME_LEN = 200


class ModError(Exception):
    """Business-logic error from mod operations (maps to HTTP 4xx)."""

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mods_dir(instance_path: Path, create: bool = False) -> Path:
    mods = instance_path / "mods"
    if create:
        mods.mkdir(parents=True, exist_ok=True)
    return mods


def _validate_filename(filename: str) -> str:
    """
    Ensure a client-supplied mod filename is safe before touching the filesystem.
    Must end with .jar or .jar.disabled and contain no path separators or
    reserved characters.
    """
    name = (filename or "").strip()
    if not name:
        raise ModError("filename must not be empty", status=400)
    if len(name) > _MAX_FILENAME_LEN:
        raise ModError("filename is too long (max 200 chars)", status=400)
    if _UNSAFE_RE.search(name):
        raise ModError(
            "filename contains invalid characters (no slashes, colons, or control chars)",
            status=400,
        )
    if _RESERVED_RE.match(name):
        raise ModError("filename uses a Windows-reserved device name", status=400)
    if not name.lower().endswith(VALID_SUFFIXES):
        raise ModError(
            "Only .jar or .jar.disabled files are accepted", status=400
        )
    # Reject any attempt to escape the mods directory
    if name.startswith((".", "/", "\\")):
        raise ModError("filename must not start with a dot or separator", status=400)
    return name


def _serialize_mod(mod_path: Path) -> Dict[str, Any]:
    """Turn a Path inside mods/ into the wire format the frontend expects."""
    filename = mod_path.name
    enabled = filename.lower().endswith(MOD_EXT) and not filename.lower().endswith(
        DISABLED_EXT
    )
    display_name = filename
    if display_name.lower().endswith(DISABLED_EXT):
        display_name = display_name[: -len(DISABLED_EXT)]
    elif display_name.lower().endswith(MOD_EXT):
        display_name = display_name[: -len(MOD_EXT)]

    try:
        size = mod_path.stat().st_size
    except OSError:
        size = 0

    return {
        "filename": filename,
        "display_name": display_name,
        "size": size,
        "enabled": enabled,
    }


def _open_in_file_manager(path: Path) -> None:
    system = platform.system()
    if system == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_mods(name: str) -> List[Dict[str, Any]]:
    """
    Scan <instance>/mods/ and return every .jar / .jar.disabled file.
    Returns an empty list if the mods folder doesn't exist yet.
    """
    clean, instance_path = require_instance_dir(name)
    mods_path = _mods_dir(instance_path)

    if not mods_path.is_dir():
        return []

    mods: List[Dict[str, Any]] = []
    try:
        for entry in sorted(mods_path.iterdir()):
            if not entry.is_file():
                continue
            lo = entry.name.lower()
            if lo.endswith(MOD_EXT) or lo.endswith(DISABLED_EXT):
                mods.append(_serialize_mod(entry))
    except OSError as exc:
        logger.warning(f"Could not list mods for '{clean}': {exc}")
    return mods


def toggle_mod(name: str, filename: str, enabled: bool) -> Dict[str, Any]:
    """
    Enable (rename to .jar) or disable (rename to .jar.disabled) a mod.
    Uses safe_rename from file_ops so Windows file-locking is handled properly.
    """
    clean, instance_path = require_instance_dir(name)
    safe_fn = _validate_filename(filename)
    mods_path = _mods_dir(instance_path)

    src = mods_path / safe_fn
    if not src.is_file():
        raise ModError(f"Mod file not found: {safe_fn}", status=404)

    lo = safe_fn.lower()
    if enabled:
        # .jar.disabled → .jar
        if not lo.endswith(DISABLED_EXT):
            # Already enabled — idempotent
            return {"mod": _serialize_mod(src), "changed": False}
        dest_name = safe_fn[: -len(DISABLED_EXT)] + MOD_EXT
    else:
        # .jar → .jar.disabled
        if lo.endswith(DISABLED_EXT):
            # Already disabled — idempotent
            return {"mod": _serialize_mod(src), "changed": False}
        dest_name = safe_fn + ".disabled"

    dest = mods_path / dest_name
    res = safe_rename(src, dest, label=f"toggle mod '{safe_fn}'")
    if not res.ok:
        locked_hint = " (is Minecraft still running?)" if res.locked else ""
        raise ModError(
            f"Could not rename '{safe_fn}'{locked_hint}: {res.error}",
            status=409 if res.locked else 500,
        )

    logger.info(
        f"Mod toggled: instance={clean} file={safe_fn} → {dest_name} enabled={enabled}"
    )
    return {"mod": _serialize_mod(dest), "changed": True}


def delete_mod(name: str, filename: str) -> Dict[str, Any]:
    """
    Permanently remove a mod file from disk.
    Raises ModError(409) if the file is locked by another process.
    """
    clean, instance_path = require_instance_dir(name)
    safe_fn = _validate_filename(filename)
    mods_path = _mods_dir(instance_path)

    target = mods_path / safe_fn
    if not target.is_file():
        raise ModError(f"Mod file not found: {safe_fn}", status=404)

    res = safe_delete(target, missing_ok=False, label=f"delete mod '{safe_fn}'")
    if not res.ok:
        locked_hint = " (is Minecraft still running?)" if res.locked else ""
        raise ModError(
            f"Could not delete '{safe_fn}'{locked_hint}: {res.error}",
            status=409 if res.locked else 500,
        )

    logger.info(f"Mod deleted: instance={clean} file={safe_fn}")
    return {"filename": safe_fn, "deleted": True}


def open_mods_folder(name: str) -> Dict[str, Any]:
    """Reveal the instance's mods/ directory in the OS file manager."""
    clean, instance_path = require_instance_dir(name)
    mods_path = _mods_dir(instance_path, create=True)

    try:
        _open_in_file_manager(mods_path)
    except OSError as exc:
        raise ModError(f"Could not open the mods folder: {exc}") from exc

    logger.info(f"Opened mods folder for '{clean}': {mods_path}")
    return {"name": clean, "path": str(mods_path), "opened": True}


def save_mod_file(name: str, filename: str, data: bytes) -> Dict[str, Any]:
    """
    Write uploaded .jar bytes into <instance>/mods/.
    Only .jar extension is accepted for uploads (not .jar.disabled).
    """
    clean, instance_path = require_instance_dir(name)

    safe_fn = _validate_filename(filename)
    lo = safe_fn.lower()
    if not lo.endswith(MOD_EXT) or lo.endswith(DISABLED_EXT):
        raise ModError("Only .jar files can be uploaded", status=400)

    mods_path = _mods_dir(instance_path, create=True)
    dest = mods_path / safe_fn

    try:
        dest.write_bytes(data)
    except PermissionError as exc:
        raise ModError(
            f"Cannot write '{safe_fn}' — file may be locked: {exc}",
            status=409,
        ) from exc
    except OSError as exc:
        raise ModError(f"Cannot write '{safe_fn}': {exc}", status=500) from exc

    logger.info(
        f"Mod uploaded: instance={clean} file={safe_fn} size={len(data)} bytes"
    )
    return {"mod": _serialize_mod(dest), "uploaded": True}
