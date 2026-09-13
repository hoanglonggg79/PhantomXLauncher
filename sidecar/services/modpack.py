from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import shutil
import uuid
import zipfile
from typing import Any, Dict, List, Literal, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from loguru import logger

from sidecar.services.core_service import get_core, get_manager, load_settings
from sidecar.services.instances import (
    CONFIG_NAME,
    InstanceError,
    save_instance,
    serialize,
    validate_name,
)
from sidecar.services.java import resolve_java_executable
from sidecar.services.tasks import TaskCancelled, TaskContext
from sidecar.utils import path_resolver
from sidecar.utils.file_ops import (
    safe_copy,
    safe_copytree,
    safe_delete,
    safe_rename,
    safe_rmtree,
    safe_write_text,
)

CF_API_KEY = "$2a$10$ikdeyDd1WBkPxFYhOxVAN.ZiJj6dPeAXte47fffCVxI6Ot6S3oEHm"
CURSEFORGE_WORKER_URL = "https://curseforge-proxy.hoanglonggg79.workers.dev"
CURSEFORGE_CLIENT_TOKEN = "ptx_548e813da32dc70a8f03f5a5"
USER_AGENT = "PhantomXLauncher/1.2.0 (hoanglonggg79/PhantomXLauncher)"

CF_HEADERS = {
    "Accept": "application/json",
    "x-api-key": CF_API_KEY,
    "User-Agent": USER_AGENT,
}

CF_PROXY_HEADERS = {
    "X-PhantomX-Client-Token": CURSEFORGE_CLIENT_TOKEN,
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

MR_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
}

BINARY_DL_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
}

MAX_PARALLEL_DOWNLOADS = 4


def _sanitize_instance_name(name: str) -> str:
    """Strip invalid characters for Windows paths and instance naming."""
    clean = re.sub(r'[\/\\:*?"<>|]', '', name).strip()
    return clean or "MyModpack"


def detect_modpack_format(zip_path: Path) -> Literal["curseforge", "modrinth", "unknown"]:
    """Examine archive root or immediate wrapper folder to determine modpack format."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            if "manifest.json" in names or any(n.endswith("/manifest.json") for n in names):
                return "curseforge"
            if "modrinth.index.json" in names or any(n.endswith("/modrinth.index.json") for n in names):
                return "modrinth"
    except Exception as e:
        logger.warning(f"Failed to inspect zip {zip_path}: {e}")
    return "unknown"


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path, ctx: Optional[TaskContext] = None) -> None:
    """Extract ZIP entries safely, preventing Zip Slip directory traversal."""
    dest_root = dest.resolve()
    dest_root.mkdir(parents=True, exist_ok=True)

    for member in zf.infolist():
        if ctx:
            ctx.check_cancelled()

        if not member.filename or member.filename == "/":
            continue

        target = (dest_root / member.filename).resolve()
        if not target.is_relative_to(dest_root):
            raise ValueError(f"Unsafe ZIP path detected: {member.filename}")

        if member.is_dir() or member.filename.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def inspect_modpack(zip_path: Path) -> Dict[str, Any]:
    """
    Read manifest metadata from modpack archive without full extraction.
    Returns: { format, name, mc_version, loader, loader_version, mod_count }
    """
    if not zip_path.is_file():
        raise FileNotFoundError(f"Modpack archive not found: {zip_path}")

    fmt = detect_modpack_format(zip_path)
    if fmt == "unknown":
        raise ValueError("Unsupported modpack format: expected CurseForge manifest.json or Modrinth modrinth.index.json")

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        if fmt == "curseforge":
            entry = next((n for n in namelist if n == "manifest.json" or n.endswith("/manifest.json")), None)
            if not entry:
                raise ValueError("CurseForge manifest.json not found in archive")

            with zf.open(entry) as f:
                data = json.loads(f.read().decode("utf-8"))

            raw_name = data.get("name", zip_path.stem)
            name = _sanitize_instance_name(raw_name)
            mc_info = data.get("minecraft", {})
            mc_ver = mc_info.get("version", "")
            mod_loaders = mc_info.get("modLoaders", [])
            primary = next((l for l in mod_loaders if l.get("primary")), mod_loaders[0] if mod_loaders else {})
            loader_id = primary.get("id", "vanilla")

            loader_kind = "vanilla"
            loader_ver = ""
            if "-" in loader_id:
                parts = loader_id.split("-", 1)
                loader_kind = parts[0].lower()
                loader_ver = parts[1]
                if loader_ver.startswith(f"{mc_ver}-"):
                    loader_ver = loader_ver[len(mc_ver) + 1:]
            elif loader_id:
                loader_kind = loader_id.lower()

            files = data.get("files", [])
            return {
                "format": "curseforge",
                "name": name,
                "mc_version": mc_ver,
                "loader": loader_kind,
                "loader_version": loader_ver,
                "mod_count": len(files),
            }

        elif fmt == "modrinth":
            entry = next((n for n in namelist if n == "modrinth.index.json" or n.endswith("/modrinth.index.json")), None)
            if not entry:
                raise ValueError("Modrinth modrinth.index.json not found in archive")

            with zf.open(entry) as f:
                data = json.loads(f.read().decode("utf-8"))

            raw_name = data.get("name", zip_path.stem)
            name = _sanitize_instance_name(raw_name)
            deps = data.get("dependencies", {})
            mc_ver = deps.get("minecraft", "")

            loader_kind = "vanilla"
            loader_ver = ""
            if "fabric-loader" in deps:
                loader_kind = "fabric"
                loader_ver = deps["fabric-loader"]
            elif "neoforge" in deps:
                loader_kind = "neoforge"
                loader_ver = deps["neoforge"]
            elif "forge" in deps:
                loader_kind = "forge"
                loader_ver = deps["forge"]
            elif "quilt-loader" in deps:
                loader_kind = "quilt"
                loader_ver = deps["quilt-loader"]

            if loader_ver.startswith(f"{mc_ver}-"):
                loader_ver = loader_ver[len(mc_ver) + 1:]

            files = data.get("files", [])
            return {
                "format": "modrinth",
                "name": name,
                "mc_version": mc_ver,
                "loader": loader_kind,
                "loader_version": loader_ver,
                "mod_count": len(files),
            }

    raise ValueError(f"Unknown format: {fmt}")


# ── CurseForge File Resolution & Download ────────────────────────────────────


def _resolve_and_download_cf_file(
    file_info: Dict[str, Any], mods_dir: Path, session: requests.Session
) -> Tuple[bool, str]:
    """Download single CurseForge mod file using Cloudflare Worker or direct API."""
    project_id = file_info.get("projectID")
    file_id = file_info.get("fileID")
    required = file_info.get("required", True)

    file_name = f"mod_{project_id}_{file_id}.jar"
    dl_url = ""

    # 1. Try resolving file info via worker proxy
    try:
        url = f"{CURSEFORGE_WORKER_URL}/v1/mods/{project_id}/files/{file_id}"
        resp = session.get(url, headers=CF_PROXY_HEADERS, timeout=12)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            file_name = data.get("fileName") or file_name
            dl_url = data.get("downloadUrl") or ""
    except Exception as e:
        logger.debug(f"CF proxy metadata failed for {project_id}/{file_id}: {e}")

    # 1b. If dl_url missing, try worker download-url endpoint
    if not dl_url:
        try:
            url = f"{CURSEFORGE_WORKER_URL}/v1/mods/{project_id}/files/{file_id}/download-url"
            resp = session.get(url, headers=CF_PROXY_HEADERS, timeout=12)
            if resp.status_code == 200:
                dl_url = resp.json().get("data") or ""
        except Exception as e:
            logger.debug(f"CF proxy download-url failed for {project_id}/{file_id}: {e}")

    # 2. Fallback to direct CF API metadata
    if not dl_url:
        try:
            url = f"https://api.curseforge.com/v1/mods/{project_id}/files/{file_id}"
            resp = session.get(url, headers=CF_HEADERS, timeout=12)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                file_name = data.get("fileName") or file_name
                dl_url = data.get("downloadUrl") or ""
        except Exception as e:
            logger.debug(f"Direct CF API metadata failed for {project_id}/{file_id}: {e}")

    # 2b. Fallback to direct CF API download-url
    if not dl_url:
        try:
            url = f"https://api.curseforge.com/v1/mods/{project_id}/files/{file_id}/download-url"
            resp = session.get(url, headers=CF_HEADERS, timeout=12)
            if resp.status_code == 200:
                dl_url = resp.json().get("data") or ""
        except Exception as e:
            logger.debug(f"Direct CF API download-url failed for {project_id}/{file_id}: {e}")

    # 3. Fallback to CDN standard path pattern if downloadUrl is restricted
    if not dl_url and file_id:
        file_id_str = str(file_id)
        if len(file_id_str) >= 4:
            part1 = file_id_str[:4]
            part2 = file_id_str[4:]
            dl_url = f"https://edge.forgecdn.net/files/{part1}/{part2}/{file_name}"

    if not dl_url:
        if not required:
            logger.warning(f"Optional CF mod download URL unavailable: {project_id}/{file_id}")
            return (False, file_name)
        raise RuntimeError(f"Could not resolve download URL for CF mod {project_id}/{file_id}")

    # 4. Download file
    dest = mods_dir / file_name
    try:
        with session.get(dl_url, headers=BINARY_DL_HEADERS, timeout=60, stream=True) as fr:
            fr.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in fr.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

        if not dest.exists() or dest.stat().st_size == 0:
            dest.unlink(missing_ok=True)
            raise IOError(f"Downloaded file {file_name} is empty")

        return (True, file_name)
    except Exception as e:
        if not required:
            logger.warning(f"Optional CF file download failed {file_name}: {e}")
            return (False, file_name)
        raise


# ── Modrinth File Download ───────────────────────────────────────────────────


def _download_mr_file(
    file_info: Dict[str, Any], instance_dir: Path, session: requests.Session
) -> Tuple[bool, str]:
    """Download single Modrinth mod file with mirror fallbacks."""
    rel_path = file_info.get("path", "")
    downloads = file_info.get("downloads", [])
    if not downloads or not rel_path:
        return (False, rel_path or "unknown")

    # Filter out server-only mods if client is unsupported
    env = file_info.get("env", {})
    if env.get("client") == "unsupported":
        logger.info(f"Skipping server-only mod for client: {rel_path}")
        return (True, rel_path)

    dest = (instance_dir / rel_path).resolve()
    if not dest.is_relative_to(instance_dir.resolve()):
        raise ValueError(f"Unsafe file path detected in Modrinth manifest: {rel_path}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    success = False
    last_err: Optional[Exception] = None
    for dl_url in downloads:
        try:
            with session.get(dl_url, headers=BINARY_DL_HEADERS, timeout=60, stream=True) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)

            if dest.exists() and dest.stat().st_size > 0:
                success = True
                break
            dest.unlink(missing_ok=True)
        except Exception as e:
            last_err = e
            dest.unlink(missing_ok=True)
            continue

    if not success:
        if last_err:
            raise last_err
        raise IOError(f"Downloaded Modrinth file {rel_path} is empty or all download URLs failed")

    return (True, Path(rel_path).name)


# ── Modpack Staging & Installation Core Worker ───────────────────────────────


def install_modpack_task(
    ctx: TaskContext,
    instance_name: str,
    zip_path: Path,
    source: str = "curseforge",
    cleanup_archive: bool = False,
) -> Dict[str, Any]:
    """
    Main background installation task for modpacks.
    Emits progress and log frames through TaskContext/EventBus.
    """
    clean_name = validate_name(instance_name)
    inst_root = path_resolver.get_instances_dir()
    final_dir = inst_root / clean_name

    if (final_dir / CONFIG_NAME).exists():
        raise InstanceError(f"Instance already exists: '{clean_name}'")

    staging_dir = inst_root / f"_staging_{clean_name}_{uuid.uuid4().hex[:8]}"
    temp_pack = staging_dir / "_temp_pack"
    mods_dir = staging_dir / "mods"

    committed = False
    session: Optional[requests.Session] = None

    try:
        ctx.log(f"=== Bắt đầu cài đặt Modpack: {clean_name} ===")

        staging_dir.mkdir(parents=True, exist_ok=True)
        temp_pack.mkdir(parents=True, exist_ok=True)
        mods_dir.mkdir(parents=True, exist_ok=True)

        ctx.check_cancelled()

        # 1. Unpack archive into temporary folder
        ctx.log("📂 Đang giải nén gói modpack...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extract_zip(zf, temp_pack, ctx=ctx)

        ctx.check_cancelled()

        # Check if archive unpacked inside a single wrapper directory
        pack_root = temp_pack
        if not (pack_root / "manifest.json").exists() and not (pack_root / "modrinth.index.json").exists():
            for sub in pack_root.iterdir():
                if sub.is_dir() and not sub.name.startswith("."):
                    if (sub / "manifest.json").exists() or (sub / "modrinth.index.json").exists():
                        pack_root = sub
                        break

        # 2. Inspect manifest
        fmt = "curseforge" if (pack_root / "manifest.json").exists() else "modrinth" if (pack_root / "modrinth.index.json").exists() else ""
        if fmt == "curseforge":
            manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
        elif fmt == "modrinth":
            manifest = json.loads((pack_root / "modrinth.index.json").read_text(encoding="utf-8"))
        else:
            raise ValueError("Không tìm thấy manifest (manifest.json hoặc modrinth.index.json) hợp lệ trong modpack.")

        ctx.log(f"  Định dạng modpack: {fmt.upper()}")

        # 3. Determine MC and Loader versions
        if fmt == "curseforge":
            mc_info = manifest.get("minecraft", {})
            mc_version = mc_info.get("version", "")
            mod_loaders = mc_info.get("modLoaders", [])
            primary = next((l for l in mod_loaders if l.get("primary")), mod_loaders[0] if mod_loaders else {})
            loader_id = primary.get("id", "vanilla")

            loader = "vanilla"
            loader_ver = ""
            if "-" in loader_id:
                parts = loader_id.split("-", 1)
                loader = parts[0].lower()
                loader_ver = parts[1]
                if loader_ver.startswith(f"{mc_version}-"):
                    loader_ver = loader_ver[len(mc_version) + 1:]
            elif loader_id:
                loader = loader_id.lower()
            files = manifest.get("files", [])
        else:
            deps = manifest.get("dependencies", {})
            mc_version = deps.get("minecraft", "")
            loader = "vanilla"
            loader_ver = ""
            if "fabric-loader" in deps:
                loader = "fabric"
                loader_ver = deps["fabric-loader"]
            elif "neoforge" in deps:
                loader = "neoforge"
                loader_ver = deps["neoforge"]
            elif "forge" in deps:
                loader = "forge"
                loader_ver = deps["forge"]
            elif "quilt-loader" in deps:
                loader = "quilt"
                loader_ver = deps["quilt-loader"]

            if loader_ver.startswith(f"{mc_version}-"):
                loader_ver = loader_ver[len(mc_version) + 1:]

            files = manifest.get("files", [])

        if not mc_version:
            raise ValueError("Không xác định được phiên bản Minecraft từ manifest.")

        ctx.log(f"🎮 Minecraft: {mc_version} | Loader: {loader} {loader_ver}")

        # 4. Provision Vanilla & Loader in staging directory
        mgr = get_manager()
        core = get_core()
        settings = load_settings()
        java_path = str(settings.get("java_path") or "")

        ctx.log(f"📦 Đang tải và cài đặt Minecraft {mc_version}...")
        if not mgr.install_vanilla(mc_version, str(staging_dir), cb_progress=ctx.progress, cb_log=ctx.log):
            raise RuntimeError(f"Không thể cài đặt Minecraft {mc_version}")

        ctx.check_cancelled()

        if loader != "vanilla":
            ctx.log(f"⚙️ Đang cài đặt loader {loader} ({loader_ver or 'mới nhất'})...")
            java = resolve_java_executable(mc_version, java_path)
            if not java:
                java = mgr.find_java_for_version(mc_version) or mgr.find_java() or ""
            if java and java.lower().endswith("javaw.exe"):
                java = java[:-9] + "java.exe"

            if loader == "fabric":
                ok = mgr.install_fabric(mc_version, loader_ver, str(staging_dir), java_path=java, cb_log=ctx.log)
            elif loader == "quilt":
                ok = mgr.install_quilt(mc_version, loader_ver, str(staging_dir), java_path=java, cb_log=ctx.log)
            elif loader == "forge":
                forge_ver = loader_ver
                if forge_ver.startswith(f"{mc_version}-"):
                    forge_ver = forge_ver[len(mc_version) + 1:]
                if not forge_ver:
                    candidates = mgr.get_forge_versions(mc_version)
                    if not candidates:
                        raise RuntimeError(f"Không tìm thấy phiên bản Forge cho {mc_version}")
                    forge_ver = candidates[0]
                ok = mgr.install_forge(mc_version, forge_ver, str(staging_dir), java, cb_log=ctx.log)
            elif loader == "neoforge":
                neoforge_ver = loader_ver
                if neoforge_ver.startswith(f"{mc_version}-"):
                    neoforge_ver = neoforge_ver[len(mc_version) + 1:]
                ok = mgr.install_neoforge(mc_version, neoforge_ver, str(staging_dir), java, cb_log=ctx.log)
            else:
                ok = False

            if not ok:
                raise RuntimeError(f"Không thể cài đặt loader {loader} cho {mc_version}")

        ctx.check_cancelled()

        # 5. Download Mod Files Concurrently
        total_mods = len(files)
        ctx.log(f"⬇️ Đang tải {total_mods} mod(s)...")

        completed_mods = 0
        failed_mods = 0

        session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=MAX_PARALLEL_DOWNLOADS * 2,
            pool_maxsize=MAX_PARALLEL_DOWNLOADS * 2,
            max_retries=2,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        def _worker(f_item: Dict[str, Any]) -> Tuple[bool, str]:
            if fmt == "curseforge":
                return _resolve_and_download_cf_file(f_item, mods_dir, session)
            else:
                return _download_mr_file(f_item, staging_dir, session)

        if total_mods > 0:
            pool = ThreadPoolExecutor(max_workers=MAX_PARALLEL_DOWNLOADS)
            try:
                future_to_file = {pool.submit(_worker, f_item): f_item for f_item in files}

                for future in as_completed(future_to_file):
                    if ctx.cancelled:
                        for f in future_to_file:
                            f.cancel()
                        pool.shutdown(wait=False, cancel_futures=True)
                        raise TaskCancelled("Task cancelled")

                    try:
                        ok, label = future.result()
                        if ok:
                            completed_mods += 1
                        else:
                            failed_mods += 1
                    except Exception as dl_err:
                        failed_mods += 1
                        logger.warning(f"Mod download error: {dl_err}")

                    progress_done = completed_mods + failed_mods
                    ctx.progress(
                        progress_done,
                        total_mods,
                        f"Đang tải mod: {progress_done}/{total_mods}",
                    )
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

        ctx.log(f"✅ Hoàn tất tải mod: {completed_mods} thành công, {failed_mods} bỏ qua/lỗi.")
        ctx.check_cancelled()

        # 6. Apply Overrides
        ctx.log("🚚 Đang sao chép cấu hình ghi đè (overrides)...")
        custom_ov = manifest.get("overrides") if isinstance(manifest.get("overrides"), str) else "overrides"
        override_candidates = [custom_ov, "overrides", "client-overrides"]
        seen_overrides = set()
        for override_name in override_candidates:
            if not override_name or override_name in seen_overrides:
                continue
            seen_overrides.add(override_name)
            ov_dir = pack_root / override_name
            if ov_dir.is_dir():
                for item in ov_dir.iterdir():
                    ctx.check_cancelled()
                    target_dst = staging_dir / item.name
                    if item.is_dir():
                        safe_copytree(item, target_dst, dirs_exist_ok=True)
                    else:
                        safe_copy(item, target_dst)
                ctx.log(f"  Đã áp dụng cấu hình từ '{override_name}'")

        ctx.check_cancelled()

        # 7. Clean temp pack folder before atomic commit
        safe_rmtree(temp_pack)

        # 8. Atomic commit to final directory (RULE 3)
        ctx.log("🚀 Đang hoàn tất cấu hình instance...")
        if final_dir.exists():
            safe_rmtree(final_dir).unwrap()
        safe_rename(staging_dir, final_dir).unwrap()
        committed = True

        # 9. Save instance.json
        inst = core.Instance(
            name=clean_name,
            version_id=mc_version,
            loader=loader,
            loader_version=loader_ver,
            game_dir=str(final_dir),
        )
        save_instance(inst)

        ctx.log(f"🎉 Instance '{clean_name}' đã được cài đặt thành công và sẵn sàng khởi chạy!")
        return {
            "instance": serialize(inst),
            "mod_count": completed_mods,
            "failed_count": failed_mods,
        }

    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        # Clean up staging dir if install didn't commit
        if not committed and staging_dir.exists():
            safe_rmtree(staging_dir)
        # Clean up temporary upload zip if requested
        if cleanup_archive and zip_path.exists():
            safe_delete(zip_path)

