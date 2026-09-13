from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

from loguru import logger
import requests

from sidecar.services.core_service import get_core
from sidecar.services.tasks import TaskContext
from sidecar.utils.file_ops import safe_file_operation

CURSEFORGE_WORKER_URL = "https://curseforge-proxy.hoanglonggg79.workers.dev"
CURSEFORGE_CLIENT_TOKEN = "ptx_548e813da32dc70a8f03f5a5"
MODRINTH_API_URL = "https://api.modrinth.com/v2"

USER_AGENT = "PhantomXLauncher/1.2.0 (hoanglonggg79/PhantomXLauncher)"

CURSEFORGE_HEADERS = {
    "X-PhantomX-Client-Token": CURSEFORGE_CLIENT_TOKEN,
    "User-Agent": USER_AGENT,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

MODRINTH_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

# ModLoader mapping for CurseForge (gameId = 432)
# 0 = Any, 1 = Forge, 4 = Fabric, 5 = Quilt, 6 = NeoForge
CF_LOADER_MAP = {
    "any": 0,
    "forge": 1,
    "fabric": 4,
    "quilt": 5,
    "neoforge": 6,
}


def _safe_str(val: Any) -> str:
    return str(val) if val is not None else ""


# ─────────────────────────────────────────────────────────────────────────────
# Modrinth Client
# ─────────────────────────────────────────────────────────────────────────────

def search_modrinth(
    query: str = "",
    mc_version: str = "",
    loader: str = "",
    category: str = "",
    sort: str = "downloads",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """
    Search mods on Modrinth API.
    """
    facets: List[List[str]] = [["project_type:mod"]]
    if mc_version:
        facets.append([f"versions:{mc_version}"])
    if loader and loader.lower() not in ("any", "vanilla"):
        facets.append([f"categories:{loader.lower()}"])
    if category:
        facets.append([f"categories:{category.lower()}"])

    index_sort = "downloads"
    if sort in ("relevance", "downloads", "follows", "newest", "updated"):
        index_sort = sort

    offset = max(0, (page - 1) * page_size)
    params = {
        "query": query,
        "facets": json.dumps(facets),
        "index": index_sort,
        "offset": offset,
        "limit": min(100, max(1, page_size)),
    }

    url = f"{MODRINTH_API_URL}/search"
    logger.info(f"Modrinth search: {query} (ver: {mc_version}, loader: {loader}, offset: {offset})")

    try:
        resp = requests.get(url, headers=MODRINTH_HEADERS, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Modrinth search failed: {e}")
        return {"source": "modrinth", "hits": [], "total": 0, "error": str(e)}

    hits = []
    for hit in data.get("hits", []):
        icon_url = hit.get("icon_url") or ""
        # Modrinth CDN icon URL vs raw URL
        raw_icon = icon_url
        if icon_url and "cdn.modrinth.com" in icon_url:
            raw_icon = icon_url

        hits.append({
            "id": hit.get("project_id", ""),
            "slug": hit.get("slug", ""),
            "title": hit.get("title", "Unknown Mod"),
            "description": hit.get("description", ""),
            "author": hit.get("author", "Unknown"),
            "icon_url": icon_url,
            "raw_icon_url": raw_icon,
            "downloads": hit.get("downloads", 0),
            "follows": hit.get("follows", 0),
            "categories": hit.get("categories", []),
            "loaders": [c for c in hit.get("categories", []) if c in ("fabric", "forge", "quilt", "neoforge")],
            "versions": hit.get("versions", []),
            "source": "modrinth",
            "web_url": f"https://modrinth.com/mod/{hit.get('slug') or hit.get('project_id')}",
        })

    return {
        "source": "modrinth",
        "hits": hits,
        "total": data.get("total_hits", len(hits)),
        "offset": offset,
        "limit": page_size,
    }


def get_modrinth_project(project_id: str) -> Dict[str, Any]:
    """
    Get full metadata and gallery for a Modrinth project.
    """
    url = f"{MODRINTH_API_URL}/project/{urllib.parse.quote(project_id)}"
    try:
        resp = requests.get(url, headers=MODRINTH_HEADERS, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Modrinth get project {project_id} failed: {e}")
        return {"error": str(e)}

    # Parse gallery images (screenshots)
    gallery = []
    for img in data.get("gallery", []):
        gallery.append({
            "url": img.get("url", ""),
            "raw_url": img.get("raw_url") or img.get("url", ""),
            "title": img.get("title", ""),
            "description": img.get("description", ""),
            "featured": img.get("featured", False),
        })

    icon_url = data.get("icon_url") or ""
    # Raw icon URL (if Modrinth returns an unoptimized original or if CDN has resize params)
    raw_icon = icon_url

    return {
        "source": "modrinth",
        "id": data.get("id", project_id),
        "slug": data.get("slug", ""),
        "title": data.get("title", "Unknown Mod"),
        "description": data.get("description", ""),
        "body": data.get("body", ""),
        "author": data.get("organization") or "Unknown",
        "icon_url": icon_url,
        "raw_icon_url": raw_icon,
        "downloads": data.get("downloads", 0),
        "followers": data.get("followers", 0),
        "categories": data.get("categories", []),
        "loaders": data.get("loaders", []),
        "game_versions": data.get("game_versions", []),
        "gallery": gallery,
        "web_url": f"https://modrinth.com/mod/{data.get('slug') or data.get('id')}",
        "source_url": data.get("source_url", ""),
        "issues_url": data.get("issues_url", ""),
        "wiki_url": data.get("wiki_url", ""),
    }


def get_modrinth_versions(
    project_id: str,
    mc_version: str = "",
    loader: str = "",
) -> List[Dict[str, Any]]:
    """
    Get versions and downloadable files for a Modrinth project.
    """
    url = f"{MODRINTH_API_URL}/project/{urllib.parse.quote(project_id)}/version"
    params: Dict[str, str] = {}
    if mc_version:
        params["game_versions"] = json.dumps([mc_version])
    if loader and loader.lower() not in ("any", "vanilla"):
        params["loaders"] = json.dumps([loader.lower()])

    try:
        resp = requests.get(url, headers=MODRINTH_HEADERS, params=params, timeout=12)
        resp.raise_for_status()
        raw_versions = resp.json()
    except Exception as e:
        logger.error(f"Modrinth get versions {project_id} failed: {e}")
        return []

    results = []
    for v in raw_versions:
        files = []
        for f in v.get("files", []):
            files.append({
                "id": f.get("hashes", {}).get("sha1") or f.get("filename", ""),
                "filename": f.get("filename", ""),
                "size": f.get("size", 0),
                "download_url": f.get("url", ""),
                "primary": f.get("primary", False),
            })

        # Ensure at least one primary file
        if files and not any(f["primary"] for f in files):
            files[0]["primary"] = True

        results.append({
            "id": v.get("id", ""),
            "name": v.get("name") or v.get("version_number", "Unknown"),
            "version_number": v.get("version_number", ""),
            "game_versions": v.get("game_versions", []),
            "loaders": v.get("loaders", []),
            "release_type": v.get("version_type", "release"),
            "date_published": v.get("date_published", ""),
            "downloads": v.get("downloads", 0),
            "files": files,
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# CurseForge Client (Via Cloudflare Worker Proxy)
# ─────────────────────────────────────────────────────────────────────────────

def search_curseforge(
    query: str = "",
    mc_version: str = "",
    loader: str = "",
    category: str = "",
    sort: str = "downloads",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """
    Search mods on CurseForge via Cloudflare Worker proxy.
    gameId=432 (Minecraft)
    """
    url = f"{CURSEFORGE_WORKER_URL}/v1/mods/search"
    
    # SortField: 1=Featured, 2=Popularity, 3=LastUpdated, 4=Name, 5=TotalDownloads
    sort_field = 2
    if sort == "downloads":
        sort_field = 5
    elif sort == "updated":
        sort_field = 3
    elif sort == "name":
        sort_field = 4
    elif sort == "popularity":
        sort_field = 2

    loader_type = CF_LOADER_MAP.get(loader.lower() if loader else "any", 0)

    offset = max(0, (page - 1) * page_size)
    params: Dict[str, Any] = {
        "gameId": 432,
        "pageSize": min(50, max(1, page_size)),
        "index": offset,
        "sortField": sort_field,
        "sortOrder": "desc",
    }
    if query:
        params["searchFilter"] = query
    if mc_version:
        params["gameVersion"] = mc_version
    if loader_type > 0:
        params["modLoaderType"] = loader_type
    if category:
        try:
            params["categoryId"] = int(category)
        except ValueError:
            pass

    logger.info(f"CurseForge search via worker: {query} (ver: {mc_version}, loader: {loader_type}, offset: {offset})")

    try:
        resp = requests.get(url, headers=CURSEFORGE_HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"CurseForge search failed: {e}")
        return {"source": "curseforge", "hits": [], "total": 0, "error": str(e)}

    mod_list = data.get("data", [])
    pagination = data.get("pagination", {})
    total_count = pagination.get("totalCount", len(mod_list))

    hits = []
    for mod in mod_list:
        logo = mod.get("logo") or {}
        icon_url = logo.get("thumbnailUrl") or logo.get("url") or ""
        raw_icon = logo.get("url") or icon_url

        # Extract authors
        authors = [a.get("name") for a in mod.get("authors", []) if a.get("name")]
        author_str = ", ".join(authors) if authors else "Unknown"

        # Categories
        cat_names = [c.get("name") for c in mod.get("categories", []) if c.get("name")]

        hits.append({
            "id": str(mod.get("id", "")),
            "slug": mod.get("slug", ""),
            "title": mod.get("name", "Unknown Mod"),
            "description": mod.get("summary", ""),
            "author": author_str,
            "icon_url": icon_url,
            "raw_icon_url": raw_icon,
            "downloads": mod.get("downloadCount", 0),
            "follows": mod.get("thumbsUpCount", 0),
            "categories": cat_names,
            "loaders": [],  # curseforge modLoader types are listed in files
            "versions": [],
            "source": "curseforge",
            "web_url": mod.get("links", {}).get("websiteUrl") or f"https://www.curseforge.com/minecraft/mc-mods/{mod.get('slug')}",
        })

    return {
        "source": "curseforge",
        "hits": hits,
        "total": total_count,
        "offset": offset,
        "limit": page_size,
    }


def get_curseforge_project(project_id: str) -> Dict[str, Any]:
    """
    Get full metadata and screenshots gallery for a CurseForge mod.
    """
    url = f"{CURSEFORGE_WORKER_URL}/v1/mods/{urllib.parse.quote(str(project_id))}"
    try:
        resp = requests.get(url, headers=CURSEFORGE_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", {})
    except Exception as e:
        logger.error(f"CurseForge get project {project_id} failed: {e}")
        return {"error": str(e)}

    logo = data.get("logo") or {}
    icon_url = logo.get("thumbnailUrl") or logo.get("url") or ""
    raw_icon = logo.get("url") or icon_url

    gallery = []
    for ss in data.get("screenshots", []):
        gallery.append({
            "url": ss.get("thumbnailUrl") or ss.get("url", ""),
            "raw_url": ss.get("url", ""),
            "title": ss.get("title", ""),
            "description": ss.get("description", ""),
            "featured": False,
        })

    authors = [a.get("name") for a in data.get("authors", []) if a.get("name")]
    author_str = ", ".join(authors) if authors else "Unknown"
    cat_names = [c.get("name") for c in data.get("categories", []) if c.get("name")]

    links = data.get("links", {})

    return {
        "source": "curseforge",
        "id": str(data.get("id", project_id)),
        "slug": data.get("slug", ""),
        "title": data.get("name", "Unknown Mod"),
        "description": data.get("summary", ""),
        "body": data.get("summary", ""),  # CF summary or description
        "author": author_str,
        "icon_url": icon_url,
        "raw_icon_url": raw_icon,
        "downloads": data.get("downloadCount", 0),
        "followers": data.get("thumbsUpCount", 0),
        "categories": cat_names,
        "loaders": [],
        "gallery": gallery,
        "web_url": links.get("websiteUrl") or f"https://www.curseforge.com/minecraft/mc-mods/{data.get('slug')}",
        "source_url": links.get("sourceUrl", ""),
        "issues_url": links.get("issuesUrl", ""),
        "wiki_url": links.get("wikiUrl", ""),
    }


def get_curseforge_versions(
    project_id: str,
    mc_version: str = "",
    loader: str = "",
) -> List[Dict[str, Any]]:
    """
    Get files for a CurseForge mod.
    """
    url = f"{CURSEFORGE_WORKER_URL}/v1/mods/{urllib.parse.quote(str(project_id))}/files"
    params: Dict[str, Any] = {
        "pageSize": 40,
    }
    if mc_version:
        params["gameVersion"] = mc_version
    loader_type = CF_LOADER_MAP.get(loader.lower() if loader else "any", 0)
    if loader_type > 0:
        params["modLoaderType"] = loader_type

    try:
        resp = requests.get(url, headers=CURSEFORGE_HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        raw_files = resp.json().get("data", [])
    except Exception as e:
        logger.error(f"CurseForge get files {project_id} failed: {e}")
        return []

    results = []
    for f in raw_files:
        dl_url = f.get("downloadUrl") or ""
        file_id = f.get("id", 0)

        # If downloadUrl is null, resolve using download-url endpoint or fallback
        if not dl_url and file_id:
            try:
                dl_res = requests.get(
                    f"{CURSEFORGE_WORKER_URL}/v1/mods/{project_id}/files/{file_id}/download-url",
                    headers=CURSEFORGE_HEADERS,
                    timeout=10,
                )
                if dl_res.status_code == 200:
                    dl_url = dl_res.json().get("data", "")
            except Exception as dl_err:
                logger.debug(f"Could not resolve download url for file {file_id}: {dl_err}")

        # If still empty, CurseForge CDN standard fallback pattern
        if not dl_url and file_id:
            file_id_str = str(file_id)
            part1 = file_id_str[:4]
            part2 = file_id_str[4:]
            filename = f.get("fileName", "mod.jar")
            dl_url = f"https://edge.forgecdn.net/files/{part1}/{part2}/{filename}"

        release_type_code = f.get("releaseType", 1)
        rel_type = "release" if release_type_code == 1 else "beta" if release_type_code == 2 else "alpha"

        # Game versions & loaders from gameVersions array
        game_vers = []
        loaders = []
        for gv in f.get("gameVersions", []):
            gv_lower = gv.lower()
            if gv_lower in ("fabric", "forge", "quilt", "neoforge"):
                loaders.append(gv_lower)
            elif re.match(r"^\d+\.\d+", gv):
                game_vers.append(gv)

        results.append({
            "id": str(file_id),
            "name": f.get("displayName") or f.get("fileName", "Unknown File"),
            "version_number": f.get("fileName", ""),
            "game_versions": game_vers,
            "loaders": loaders,
            "release_type": rel_type,
            "date_published": f.get("fileDate", ""),
            "downloads": f.get("downloadCount", 0),
            "files": [
                {
                    "id": str(file_id),
                    "filename": f.get("fileName", "mod.jar"),
                    "size": f.get("fileLength", 0),
                    "download_url": dl_url,
                    "primary": True,
                }
            ],
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Mod Installation Task (SSE Streamed + Windows File Locking Safe)
# ─────────────────────────────────────────────────────────────────────────────

def install_mod_task(
    instance_name: str,
    filename: str,
    download_url: str,
    project_title: str,
    source: str,
    ctx: TaskContext,
) -> Dict[str, Any]:
    """
    Download mod file and place into <instance_dir>/mods/<filename>.
    Guards against busy/running instances.
    Streams SSE progress and log events.
    """
    from sidecar.services import instances as inst_svc

    try:
        instance = inst_svc.get_instance(instance_name)
    except Exception:
        raise ValueError(f"Instance '{instance_name}' does not exist.")

    # Guard: check if instance is running / busy
    if inst_svc.is_running(instance_name):
        raise RuntimeError(
            f"Instance '{instance_name}' đang chạy game. "
            "Vui lòng tắt game Minecraft trước khi cài đặt mod mới vào thư mục mods/."
        )

    inst_dir = Path(instance.game_dir)
    mods_dir = inst_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    target_file = mods_dir / filename

    ctx.log(f"Starting installation of '{project_title}' ({source}) into instance '{instance_name}'…")
    ctx.progress(0, 100, f"Preparing to download {filename}…")

    if not download_url:
        raise ValueError(f"No valid download URL provided for {filename}.")

    # Download with streaming and cancellation checks
    ctx.check_cancelled()

    logger.info(f"Downloading mod from {download_url} to {target_file}")
    ctx.log(f"Connecting to download server…")

    headers = {"User-Agent": USER_AGENT}
    if source == "curseforge":
        headers["X-PhantomX-Client-Token"] = CURSEFORGE_CLIENT_TOKEN

    resp = requests.get(download_url, headers=headers, stream=True, timeout=30)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))
    temp_file = mods_dir / f"{filename}.part"

    downloaded = 0
    chunk_size = 65536

    try:
        with open(temp_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                ctx.check_cancelled()
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = int((downloaded / total_size) * 100)
                        ctx.progress(
                            downloaded,
                            total_size,
                            f"Downloading {filename} ({percent}%)",
                        )

        ctx.check_cancelled()
        ctx.progress(100, 100, "Finalizing file…")

        # Atomic / Safe replace using safe_file_operation
        def _commit_file():
            if target_file.exists():
                target_file.unlink()
            temp_file.replace(target_file)

        res = safe_file_operation(_commit_file)
        if not res.ok:
            raise OSError(f"Failed to move downloaded mod into place: {res.error}")

    except Exception:
        # Clean up temp file
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        raise

    # Update instance mod count cache
    try:
        mod_files = [f for f in mods_dir.iterdir() if f.name.endswith(".jar") or f.name.endswith(".jar.disabled")]
        instance.mod_count = len(mod_files)
    except Exception:
        pass

    ctx.log(f"Successfully installed '{filename}' ({downloaded // 1024} KB) into '{instance_name}'.")
    logger.info(f"Mod installed: {target_file}")

    return {
        "success": True,
        "instance_name": instance_name,
        "filename": filename,
        "size": downloaded,
        "path": str(target_file),
    }
