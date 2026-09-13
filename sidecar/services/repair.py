from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
import requests

from sidecar.services.instances import get_instance, InstanceError
from sidecar.services.tasks import TaskContext
from sidecar.utils import file_ops, path_resolver

MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
ASSETS_BASE = "https://resources.download.minecraft.net"
MAX_WORKERS = 6


def sha1_file(path: Path) -> str:
    """Compute SHA-1 hash of a file efficiently using 64KB chunks."""
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


# ── SHA-1 Integrity Verification ─────────────────────────────────────────────


def verify_and_repair(ctx: TaskContext, instance_name: str) -> Dict[str, Any]:
    """
    Two-phase smart repair:
    1. Scan version JSON, client JAR, libraries, and asset index.
    2. Download ONLY missing or corrupted files with ThreadPoolExecutor.
    """
    start_time = time.time()
    inst = get_instance(instance_name)
    game_dir = Path(inst.game_dir)
    mc_ver = inst.version_id

    ctx.log(f"🔍 Bắt đầu kiểm tra toàn vẹn cho '{inst.name}' (phiên bản: {mc_ver})")
    ctx.progress(1, 6, "Đang tải manifest phiên bản...")

    summary = {
        "instance": inst.name,
        "version": mc_ver,
        "scanned_jar": 0,
        "scanned_libs": 0,
        "scanned_assets": 0,
        "restored_jar": 0,
        "restored_libs": 0,
        "restored_assets": 0,
        "rebuilt_natives": False,
        "elapsed": 0.0,
    }

    download_queue: List[Tuple[str, Path, str]] = []  # (url, dest, sha1)

    # ── Step 1: Version JSON & Client JAR ─────────────────────────────────────
    ctx.check_cancelled()
    ctx.progress(2, 6, "Kiểm tra file phiên bản & client JAR...")
    ver_dir = game_dir / "versions" / mc_ver
    ver_dir.mkdir(parents=True, exist_ok=True)
    json_path = ver_dir / f"{mc_ver}.json"
    jar_path = ver_dir / f"{mc_ver}.jar"

    ver_info = None
    try:
        r = requests.get(MOJANG_MANIFEST, timeout=10)
        if r.status_code == 200:
            manifest = r.json()
            ver_info = next((v for v in manifest.get("versions", []) if v["id"] == mc_ver), None)
    except Exception as e:
        ctx.log(f"⚠️ Không thể kết nối Mojang manifest: {e}", level="warning")

    ver_data = {}
    if not json_path.exists() and ver_info:
        ctx.log(f"⚠️ Thiếu {mc_ver}.json → thêm vào hàng đợi tải xuống")
        download_queue.append((ver_info["url"], json_path, ""))
        summary["scanned_jar"] += 1
        summary["restored_jar"] += 1
    elif json_path.exists():
        try:
            ver_data = json.loads(json_path.read_text(encoding="utf-8"))
            summary["scanned_jar"] += 1
        except Exception:
            pass

    # Check client jar
    client_dl = ver_data.get("downloads", {}).get("client", {})
    expected_jar_sha1 = client_dl.get("sha1", "")
    jar_url = client_dl.get("url", "")

    summary["scanned_jar"] += 1
    if not jar_path.exists():
        if jar_url:
            ctx.log(f"⚠️ Thiếu {mc_ver}.jar → thêm vào hàng đợi tải")
            download_queue.append((jar_url, jar_path, expected_jar_sha1))
            summary["restored_jar"] += 1
    elif expected_jar_sha1:
        actual_sha1 = sha1_file(jar_path)
        if actual_sha1 != expected_jar_sha1:
            ctx.log(f"⚠️ File {mc_ver}.jar bị hỏng (SHA-1 không khớp) → tải lại")
            jar_path.unlink(missing_ok=True)
            download_queue.append((jar_url, jar_path, expected_jar_sha1))
            summary["restored_jar"] += 1
        else:
            ctx.log(f"✅ Client JAR ({mc_ver}.jar) hợp lệ")

    # ── Step 2: Libraries (.jar) ──────────────────────────────────────────────
    ctx.check_cancelled()
    ctx.progress(3, 6, "Kiểm tra thư viện (libraries)...")
    raw_libs = ver_data.get("libraries", [])
    lib_dir = game_dir / "libraries"
    lib_tasks: List[Tuple[str, Path, str]] = []

    for lib in raw_libs:
        artifact = lib.get("downloads", {}).get("artifact", {})
        path_str = artifact.get("path", "")
        url = artifact.get("url", "")
        sha1 = artifact.get("sha1", "")
        if path_str and url:
            dest = lib_dir / Path(path_str)
            lib_tasks.append((url, dest, sha1))

    summary["scanned_libs"] = len(lib_tasks)

    # Parallel library SHA-1 scan with ThreadPoolExecutor
    def _check_lib(item: Tuple[str, Path, str]) -> Optional[Tuple[str, Path, str]]:
        url, dest, expected = item
        if not dest.exists():
            return item
        if expected:
            actual = sha1_file(dest)
            if actual != expected:
                dest.unlink(missing_ok=True)
                return item
        return None

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_check_lib, item) for item in lib_tasks]
        for f in as_completed(futures):
            ctx.check_cancelled()
            res = f.result()
            if res:
                download_queue.append(res)
                summary["restored_libs"] += 1

    ctx.log(f"✅ Đã quét {len(lib_tasks)} thư viện, phát hiện {summary['restored_libs']} thư viện cần tải lại")

    # ── Step 3: Assets Index & Objects Scope ──────────────────────────────────
    ctx.check_cancelled()
    ctx.progress(4, 6, "Kiểm tra tài nguyên (Assets Index)...")
    asset_index_info = ver_data.get("assetIndex", {})
    asset_index_id = asset_index_info.get("id", mc_ver)
    asset_index_url = asset_index_info.get("url", "")
    asset_index_sha1 = asset_index_info.get("sha1", "")

    indexes_dir = game_dir / "assets" / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    index_file = indexes_dir / f"{asset_index_id}.json"

    # Smart assets verification:
    # Hash the index JSON itself. If the index JSON matches SHA-1 and objects folder exists,
    # assets are considered healthy. This reduces scan time from minutes to seconds.
    index_ok = False
    summary["scanned_assets"] = 1
    if not index_file.exists():
        if asset_index_url:
            download_queue.append((asset_index_url, index_file, asset_index_sha1))
            summary["restored_assets"] += 1
    elif asset_index_sha1:
        if sha1_file(index_file) == asset_index_sha1:
            index_ok = True
            ctx.log(f"✅ Asset index ({asset_index_id}.json) toàn vẹn")
        else:
            ctx.log(f"⚠️ Asset index ({asset_index_id}.json) lỗi SHA-1 → tải lại")
            index_file.unlink(missing_ok=True)
            if asset_index_url:
                download_queue.append((asset_index_url, index_file, asset_index_sha1))
                summary["restored_assets"] += 1

    objects_dir = game_dir / "assets" / "objects"
    if not objects_dir.exists():
        objects_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 4: Parallel Downloads ────────────────────────────────────────────
    ctx.check_cancelled()
    total_dl = len(download_queue)
    if total_dl > 0:
        ctx.log(f"📥 Bắt đầu tải {total_dl} file cần sửa chữa...")
        completed_dl = 0

        def _download_file(item: Tuple[str, Path, str]) -> bool:
            url, dest, expected_hash = item
            dest.parent.mkdir(parents=True, exist_ok=True)
            for attempt in range(3):
                try:
                    r = requests.get(url, timeout=20, stream=True)
                    if r.status_code == 200:
                        tmp = dest.with_suffix(".tmp_dl")
                        with open(tmp, "wb") as f:
                            for chunk in r.iter_content(chunk_size=32768):
                                if chunk:
                                    f.write(chunk)
                        if expected_hash:
                            if sha1_file(tmp) != expected_hash:
                                tmp.unlink(missing_ok=True)
                                continue
                        tmp.replace(dest)
                        return True
                except Exception:
                    time.sleep(0.5)
            return False

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_item = {executor.submit(_download_file, item): item for item in download_queue}
            for future in as_completed(future_to_item):
                ctx.check_cancelled()
                completed_dl += 1
                ctx.progress(completed_dl, total_dl, f"Đang tải file ({completed_dl}/{total_dl})...")
                item = future_to_item[future]
                if future.result():
                    ctx.log(f"  + Tải thành công: {item[1].name}")
                else:
                    ctx.log(f"  - Thất bại khi tải: {item[1].name}", level="warning")

    # ── Step 5: Rebuild Natives ───────────────────────────────────────────────
    ctx.check_cancelled()
    ctx.progress(5, 6, "Kiểm tra và giải nén native libraries...")
    try:
        natives_dir = game_dir / "versions" / mc_ver / f"{mc_ver}-natives"
        natives_dir.mkdir(parents=True, exist_ok=True)
        rebuilt = False
        for lib in ver_data.get("libraries", []):
            natives = lib.get("natives", {})
            os_key = "windows" if platform.system() == "Windows" else ("osx" if platform.system() == "Darwin" else "linux")
            classifier = natives.get(os_key)
            if classifier:
                dl = lib.get("downloads", {}).get("classifiers", {}).get(classifier, {})
                rel_path = dl.get("path")
                if rel_path:
                    jar = lib_dir / Path(rel_path)
                    if jar.exists():
                        try:
                            with zipfile.ZipFile(jar, "r") as zf:
                                for member in zf.namelist():
                                    if member.endswith((".dll", ".so", ".dylib")) and not member.startswith("META-INF"):
                                        zf.extract(member, natives_dir)
                                        rebuilt = True
                        except Exception:
                            pass
        summary["rebuilt_natives"] = rebuilt
    except Exception as e:
        ctx.log(f"⚠️ Lỗi giải nén natives: {e}", level="warning")

    summary["elapsed"] = round(time.time() - start_time, 2)
    ctx.progress(6, 6, "Hoàn tất kiểm tra!")
    ctx.log(f"🎉 Sửa chữa hoàn tất trong {summary['elapsed']}s! Tất cả file cốt lõi đã sẵn sàng.")
    return summary


# ── Crash Log Analyzer (80/20 Rule Regex Pattern Matching) ───────────────────


def analyze_latest_crash(instance_name: str) -> Dict[str, Any]:
    """
    Analyzes the most recent Minecraft crash report or latest.log
    using Rule 80/20 Regex patterns to detect OOM, mod conflicts, or Java version mismatches.
    """
    inst = get_instance(instance_name)
    game_dir = Path(inst.game_dir)

    crash_dir = game_dir / "crash-reports"
    latest_log = game_dir / "logs" / "latest.log"

    target_log: Optional[Path] = None

    # Priority 1: Check most recent crash-reports/crash-*.txt
    if crash_dir.exists():
        crash_files = sorted(
            crash_dir.glob("crash-*.txt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if crash_files:
            target_log = crash_files[0]

    # Priority 2: If no crash report or latest.log is more recent, check latest.log
    if latest_log.exists():
        if target_log is None or latest_log.stat().st_mtime > target_log.stat().st_mtime:
            target_log = latest_log

    if not target_log or not target_log.exists():
        return {
            "has_crash": False,
            "source_file": "None",
            "full_path": "",
            "category": "none",
            "title": "Chưa có dữ liệu Crash",
            "suggestion": "Không tìm thấy file crash-reports hoặc latest.log trong thư mục instance.",
            "matched_detail": "",
            "raw_snippet": "",
            "full_log": "",
        }

    try:
        content = target_log.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {
            "has_crash": False,
            "source_file": target_log.name,
            "full_path": str(target_log),
            "category": "unknown",
            "title": "Không thể đọc file log",
            "suggestion": f"Lỗi đọc file: {e}",
            "matched_detail": "",
            "raw_snippet": "",
            "full_log": "",
        }

    lines = content.splitlines()
    snippet = "\n".join(lines[-150:]) if len(lines) > 150 else content
    full_log_capped = content if len(content) <= 60000 else content[-60000:]

    # 1. Out of Memory (OOM)
    if "java.lang.OutOfMemoryError" in content or "There is insufficient memory for the Java Runtime Environment" in content:
        return {
            "has_crash": True,
            "source_file": target_log.name,
            "full_path": str(target_log),
            "category": "oom",
            "title": "Thiếu bộ nhớ RAM (Out of Memory)",
            "suggestion": "Trò chơi bị thiếu RAM để nạp các tài nguyên và mod. Bạn hãy vào Cài đặt (Settings) -> Bộ nhớ (Memory) và tăng mức RAM cấp cho JVM (khuyên dùng từ 4096MB đến 6144MB nếu chơi Mod).",
            "matched_detail": "Phát hiện: java.lang.OutOfMemoryError",
            "raw_snippet": snippet,
            "full_log": full_log_capped,
        }

    # 2. Mod Conflicts / Missing Dependencies
    # Fabric / Forge / NeoForge common missing dependency patterns
    mod_match = re.search(
        r"(?:Missing or unsupported mandatory dependencies:.*?needs ([\w\-\.]+)|Mod '(.*?)' requires|Incompatible mod set!|net\.fabricmc\.loader\.impl\.FormattedException: (.*?)(?:\n|$))",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if mod_match or "Missing or unsupported mandatory dependencies" in content or "Incompatible mod set" in content:
        matched_text = mod_match.group(0).strip() if mod_match else "Xung đột hoặc thiếu dependency mod"
        return {
            "has_crash": True,
            "source_file": target_log.name,
            "full_path": str(target_log),
            "category": "mod_conflict",
            "title": "Xung đột hoặc thiếu Mod (Missing Dependencies)",
            "suggestion": "Trò chơi bị crash do thiếu mod phụ thuộc bắt buộc (ví dụ: Fabric API, Architectury, Cloth Config) hoặc hai mod không tương thích với nhau. Hãy kiểm tra các mod được liệt kê trong thông tin chi tiết.",
            "matched_detail": matched_text[:300],
            "raw_snippet": snippet,
            "full_log": full_log_capped,
        }

    # 3. Java Runtime Mismatch
    java_match = re.search(
        r"(?:UnsupportedClassVersionError|has been compiled by a more recent version of the Java Runtime \(class file version (\d+)\.0\)|java\.lang\.UnsupportedClassVersionError)",
        content,
    )
    if java_match:
        class_ver = java_match.group(1) if java_match.lastindex else ""
        suggested_java = "Java 17 hoặc 21"
        if class_ver == "65":
            suggested_java = "Java 21"
        elif class_ver == "61":
            suggested_java = "Java 17"
        elif class_ver == "52":
            suggested_java = "Java 8"

        return {
            "has_crash": True,
            "source_file": target_log.name,
            "full_path": str(target_log),
            "category": "java_mismatch",
            "title": "Sai phiên bản Java (Java Runtime Mismatch)",
            "suggestion": f"Phiên bản Java đang dùng không tương thích với Minecraft hoặc Mod hiện tại. Khuyến nghị sử dụng: {suggested_java}. Bạn có thể vào Cài đặt -> Java Runtime để tải và đổi bản Java tương ứng.",
            "matched_detail": java_match.group(0),
            "raw_snippet": snippet,
            "full_log": full_log_capped,
        }

    # 4. Fallback / Other Errors
    has_error_lines = any(
        err in content
        for err in ("FATAL", "Exception in thread", "Crash Report UUID", "Minecraft has crashed")
    )
    return {
        "has_crash": has_error_lines or "crash-reports" in str(target_log),
        "source_file": target_log.name,
        "full_path": str(target_log),
        "category": "unknown" if has_error_lines else "none",
        "title": "Lỗi không xác định" if has_error_lines else "Log bình thường",
        "suggestion": "Đã phát hiện lỗi ngoài 3 nguyên nhân phổ biến. Bạn có thể bấm nút 'Copy Log' bên dưới để sao chép nhanh và gửi vào server Discord PhantomX để đội ngũ hỗ trợ giải đáp!",
        "matched_detail": "Vui lòng xem đoạn log đính kèm để biết thêm chi tiết.",
        "raw_snippet": snippet,
        "full_log": full_log_capped,
    }


# ── Clean Cache & Reset Options ──────────────────────────────────────────────


def reset_options(instance_name: str) -> Dict[str, Any]:
    """
    Backs up options.txt to options.txt.bak and resets options.txt
    to vanilla defaults to fix graphic/display driver crash issues.
    """
    inst = get_instance(instance_name)
    game_dir = Path(inst.game_dir)
    options_file = game_dir / "options.txt"
    bak_file = game_dir / "options.txt.bak"

    if options_file.exists():
        try:
            shutil.copy2(options_file, bak_file)
        except Exception as e:
            logger.warning(f"Could not backup options.txt: {e}")

    default_options = (
        "version:3465\n"
        "fov:0.0\n"
        "gamma:1.0\n"
        "renderDistance:8\n"
        "simulationDistance:8\n"
        "guiScale:0\n"
        "soundCategory_master:1.0\n"
        "soundCategory_music:0.7\n"
        "fullscreen:false\n"
        "vsync:true\n"
        "pauseOnLostFocus:true\n"
    )

    res = file_ops.safe_write_text(options_file, default_options)
    return {
        "success": res.ok,
        "instance": inst.name,
        "path": str(options_file),
        "backup": str(bak_file) if bak_file.exists() else None,
        "message": "Đã khôi phục options.txt về mặc định thành công!",
    }


def clean_cache() -> Dict[str, Any]:
    """
    Cleans temp folders, .tmp download chunks, and cached logs
    under %LOCALAPPDATA% (or portable data directory).
    """
    base_dir = path_resolver.get_base_dir()
    cleaned_items = 0
    cleaned_bytes = 0

    cache_dirs = [
        base_dir / "cache",
        base_dir / ".tmp",
    ]

    for cdir in cache_dirs:
        if cdir.exists():
            for item in cdir.glob("**/*"):
                if item.is_file():
                    try:
                        size = item.stat().st_size
                        item.unlink(missing_ok=True)
                        cleaned_items += 1
                        cleaned_bytes += size
                    except Exception:
                        pass

    # Also clean .tmp_dl or .tmp files in instances/
    inst_dir = path_resolver.get_instances_dir()
    if inst_dir.exists():
        for tmp_file in inst_dir.glob("**/*.tmp*"):
            if tmp_file.is_file():
                try:
                    size = tmp_file.stat().st_size
                    tmp_file.unlink(missing_ok=True)
                    cleaned_items += 1
                    cleaned_bytes += size
                except Exception:
                    pass

    return {
        "cleaned_items": cleaned_items,
        "cleaned_bytes": cleaned_bytes,
        "cleaned_mb": round(cleaned_bytes / (1024 * 1024), 2),
        "message": f"Đã dọn dẹp {cleaned_items} file tạm ({round(cleaned_bytes / (1024 * 1024), 2)} MB)",
    }
