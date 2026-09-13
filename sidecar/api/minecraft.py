from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from sidecar.services.core_service import get_manager

router = APIRouter(tags=["minecraft"])

LOADER_SUPPORT = {"fabric", "forge"}


@router.get("/versions")
def list_versions(include_snapshots: bool = Query(False)) -> Dict[str, Any]:
    """Available Minecraft versions, newest first."""
    versions = get_manager().get_versions(include_snapshots=include_snapshots)
    items = [
        {
            "id": v.get("id", ""),
            "type": v.get("type", ""),
            "release_time": v.get("releaseTime") or v.get("time") or "",
        }
        for v in versions
        if v.get("id")
    ]
    latest_release = next((i["id"] for i in items if i["type"] == "release"), "")
    logger.info(f"Served {len(items)} versions (snapshots={include_snapshots})")
    return {
        "versions": items,
        "count": len(items),
        "latest_release": latest_release,
    }


@router.get("/loaders/{loader}/{mc_version}")
def list_loader_versions(loader: str, mc_version: str) -> Dict[str, Any]:
    """Loader builds for a Minecraft version. Empty + supported=false when core has no index."""
    mgr = get_manager()
    key = loader.lower().strip()

    if key == "fabric":
        versions = mgr.get_fabric_loaders(mc_version)
    elif key == "forge":
        versions = mgr.get_forge_versions(mc_version)
    elif key in {"quilt", "neoforge", "vanilla"}:
        return {"loader": key, "mc_version": mc_version, "versions": [], "supported": False}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown loader: {loader}")

    return {
        "loader": key,
        "mc_version": mc_version,
        "versions": versions,
        "supported": True,
    }


@router.get("/java")
def java_status(mc_version: str = Query(default="", description="Optional MC version to determine required Java major")) -> Dict[str, Any]:
    """
    Detected Java runtime, compatibility status, and version mapping.

    When *mc_version* is provided, returns the required Java major for that
    version using the canonical mapping matrix:
      MC < 1.17           → Java 8
      1.17 ≤ MC < 1.20.5  → Java 17
      MC ≥ 1.20.5         → Java 21
    """
    from sidecar.services.java import required_java_for_mc, scan_java_installations

    mgr = get_manager()
    ok, message = mgr.check_java()
    path = mgr.find_java() or ""
    major = mgr.java_version(path) if path else None

    # Build the version-mapping table (always included so the UI can display it)
    version_matrix = {
        "lt_1.17": 8,
        "1.17_to_1.20.4": 17,
        "gte_1.20.5": 21,
    }

    required: Optional[int] = None
    if mc_version:
        required = required_java_for_mc(mc_version)

    # Count installed runtimes so the UI can show a "Manage" badge
    try:
        installs = scan_java_installations()
        installs_count = len(installs)
    except Exception:
        installs_count = 0

    return {
        "ok": ok,
        "message": message,
        "path": path,
        "major": major,
        "required_for_mc": required,
        "version_matrix": version_matrix,
        "installs_count": installs_count,
    }

