from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess
from typing import Any, Dict, Optional, Tuple

from loguru import logger
import psutil
import requests

from sidecar.services.core_service import get_core
from sidecar.utils import path_resolver

BUG_REPORT_WORKER_URL = "https://bugs-report.hoanglonggg79.workers.dev/"


def get_gpu_info() -> str:
    """Retrieve GPU name on Windows via PowerShell or WMIC without blocking."""
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
            if lines:
                return ", ".join(lines)
    except Exception as e:
        logger.debug(f"PowerShell GPU detection failed: {e}")

    # Fallback to WMIC
    try:
        cmd = ["wmic", "path", "win32_VideoController", "get", "name"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip() and line.strip().lower() != "name"]
            if lines:
                return ", ".join(lines)
    except Exception as e:
        logger.debug(f"WMIC GPU detection failed: {e}")

    return "Unknown GPU"


def get_system_specs() -> Dict[str, str]:
    """
    Gathers environment and hardware specifications for GDPR opt-in diagnostics.
    """
    core = get_core()

    # OS
    os_name = f"{platform.system()} {platform.release()} ({platform.architecture()[0]})"
    try:
        if platform.system() == "Windows":
            win_ver = platform.win32_ver()
            os_name = f"Windows {win_ver[0]} (Build {win_ver[1]} {win_ver[2]}) {platform.architecture()[0]}"
    except Exception:
        pass

    # CPU
    cpu_name = platform.processor() or "Unknown CPU"
    try:
        # On Windows, processor environment variable often has better model string
        cpu_env = os.environ.get("PROCESSOR_IDENTIFIER")
        if cpu_env:
            cpu_name = cpu_env
    except Exception:
        pass

    # RAM
    total_ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    ram_str = f"{total_ram_gb} GB"

    # GPU
    gpu_str = get_gpu_info()

    # Java
    java_ver_str = "Not detected"
    try:
        java_status = core.check_java()
        if java_status and java_status.get("ok"):
            java_ver_str = f"Java {java_status.get('major')} ({java_status.get('path')})"
        elif java_status:
            java_ver_str = java_status.get("message", "Invalid Java")
    except Exception as e:
        logger.debug(f"Could not check Java status: {e}")

    return {
        "os": os_name,
        "cpu": cpu_name,
        "ram": ram_str,
        "gpu": gpu_str,
        "java_version": java_ver_str,
    }


def get_latest_log_info(max_lines: int = 40) -> Tuple[Optional[Path], str]:
    """
    Finds the most relevant log file (crash-report or sidecar.log) and returns (path, snippet).
    """
    base_dir = path_resolver.get_base_dir()
    logs_dir = base_dir / "logs"
    sidecar_log = logs_dir / "sidecar.log"

    target_log = sidecar_log if sidecar_log.exists() else None

    # Check if there is any recent crash report in instances
    instances_dir = path_resolver.get_instances_dir()
    if instances_dir.exists():
        recent_crashes = []
        for crash_file in instances_dir.glob("*/crash-reports/crash-*.txt"):
            try:
                recent_crashes.append((crash_file.stat().st_mtime, crash_file))
            except Exception:
                pass
        if recent_crashes:
            recent_crashes.sort(key=lambda x: x[0], reverse=True)
            target_log = recent_crashes[0][1]

    if not target_log or not target_log.exists():
        return None, "No logs available."

    try:
        # Read last N lines safely
        with open(target_log, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            snippet = "".join(lines[-max_lines:]) if lines else "Empty log file."
            return target_log, snippet
    except Exception as e:
        return target_log, f"Could not read log file: {e}"


def get_diagnostics_context() -> Dict[str, Any]:
    """
    Returns pre-filled specs and log preview for the UI Report Bug dialog.
    """
    core = get_core()
    app_version = getattr(core, "APP_VERSION", "1.2.0")
    specs = get_system_specs()
    log_path, snippet = get_latest_log_info(40)

    return {
        "app_version": app_version,
        "specs": specs,
        "log_snippet": snippet,
        "log_file_name": target_log_name(log_path),
        "has_log_file": log_path is not None,
    }


def target_log_name(path: Optional[Path]) -> str:
    if not path:
        return ""
    return path.name


def submit_bug_report(
    title: str,
    description: str,
    steps: str = "",
    include_specs: bool = False,
    include_log: bool = True,
    website: str = "",  # Honeypot field (must be "")
) -> Dict[str, Any]:
    """
    Sends bug report to the Cloudflare Worker proxy according to Spec 1 & Spec 2.
    """
    # Bot honeypot check: If bot filled 'website', reject immediately
    if website != "":
        logger.warning("Bot honeypot triggered on submit_bug_report (website field populated).")
        return {"status": "error", "message": "Spam detected."}

    core = get_core()
    app_version = getattr(core, "APP_VERSION", "1.2.0")

    # Construct user message
    parts = []
    if title:
        parts.append(f"**Lỗi gặp phải:** {title}")
    if description:
        parts.append(f"**Mô tả chi tiết:**\n{description}")
    if steps:
        parts.append(f"**Các bước dẫn đến lỗi:**\n{steps}")

    full_message = "\n\n".join(parts) if parts else description
    if len(full_message.strip()) < 10:
        raise ValueError("Mô tả lỗi phải có tối thiểu 10 ký tự.")

    specs = get_system_specs() if include_specs else {}
    log_path, log_snippet = get_latest_log_info(40) if include_log else (None, "")

    payload = {
        "message": full_message,
        "app_version": app_version,
        "website": "",  # Honeypot
        "include_specs": include_specs,
        "specs": specs,
        "include_log": include_log,
        "log_content": log_snippet if include_log else "",
    }

    logger.info(f"Submitting bug report to Worker: {BUG_REPORT_WORKER_URL} (include_specs={include_specs}, include_log={include_log})")

    # Spec 1: multipart/form-data if include_log is True and file exists
    if include_log and log_path and log_path.exists():
        try:
            with open(log_path, "rb") as lf:
                files = {
                    "log_file": (log_path.name, lf, "text/plain"),
                }
                data = {
                    "payload_json": json.dumps(payload, ensure_ascii=False),
                }
                resp = requests.post(BUG_REPORT_WORKER_URL, data=data, files=files, timeout=20)
        except Exception as e:
            logger.error(f"Error sending multipart bug report: {e}")
            raise RuntimeError(f"Không thể kết nối đến máy chủ báo cáo lỗi: {e}")
    else:
        # Spec 2: application/json
        try:
            headers = {"Content-Type": "application/json"}
            resp = requests.post(BUG_REPORT_WORKER_URL, headers=headers, json=payload, timeout=20)
        except Exception as e:
            logger.error(f"Error sending JSON bug report: {e}")
            raise RuntimeError(f"Không thể kết nối đến máy chủ báo cáo lỗi: {e}")

    logger.info(f"Bug report response: {resp.status_code} - {resp.text[:200]}")

    if resp.status_code == 200:
        try:
            return resp.json()
        except Exception:
            return {"status": "success", "message": "Đã gửi báo cáo lỗi thành công!"}
    else:
        try:
            err_data = resp.json()
            return {"status": "error", "message": err_data.get("message") or resp.text}
        except Exception:
            return {"status": "error", "message": f"Máy chủ phản hồi mã lỗi HTTP {resp.status_code}."}
