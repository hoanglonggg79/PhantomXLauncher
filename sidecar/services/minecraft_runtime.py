from __future__ import annotations

from pathlib import Path

import requests
from loguru import logger

from sidecar.utils.path_resolver import get_runtimes_dir

AUTHLIB_GITHUB_API = "https://api.github.com/repos/yushijinhun/authlib-injector/releases/latest"
AUTHLIB_JAR_NAME = "authlib-injector.jar"
AUTHLIB_INJECTOR_URL = "https://authserver.ely.by/api/authlib-injector"


def authlib_injector_path() -> Path:
    return get_runtimes_dir() / AUTHLIB_JAR_NAME


def _pick_jar_asset(release: dict) -> str | None:
    for asset in release.get("assets") or []:
        name = asset.get("name") or ""
        if name.endswith(".jar") and "authlib-injector" in name.lower():
            return asset.get("browser_download_url")
    return None


def ensure_authlib_injector() -> Path:
    """
    Ensure authlib-injector.jar exists under the runtimes directory.
    Downloads the latest release from GitHub if missing.
    """
    target = authlib_injector_path()
    if target.is_file() and target.stat().st_size > 0:
        return target.resolve()

    get_runtimes_dir().mkdir(parents=True, exist_ok=True)
    logger.info("Downloading authlib-injector.jar for Ely.by…")

    try:
        meta = requests.get(
            AUTHLIB_GITHUB_API,
            headers={"Accept": "application/vnd.github+json"},
            timeout=30,
        )
        meta.raise_for_status()
        release = meta.json()
    except Exception as e:
        raise RuntimeError(f"Could not fetch authlib-injector release info: {e}") from e

    download_url = _pick_jar_asset(release)
    if not download_url:
        tag = release.get("tag_name") or "latest"
        download_url = f"https://github.com/yushijinhun/authlib-injector/releases/download/{tag}/authlib-injector-{tag.lstrip('v')}.jar"

    try:
        resp = requests.get(download_url, timeout=120, stream=True)
        resp.raise_for_status()
        target.write_bytes(resp.content)
    except Exception as e:
        raise RuntimeError(f"Failed to download authlib-injector.jar: {e}") from e

    if not target.is_file() or target.stat().st_size < 1024:
        raise RuntimeError("Downloaded authlib-injector.jar looks invalid.")

    logger.info(f"authlib-injector.jar ready at {target}")
    return target.resolve()


def build_authlib_jvm_arg(jar_path: Path | None = None) -> str:
    path = (jar_path or ensure_authlib_injector()).resolve()
    # Windows paths: forward slashes are fine in -javaagent
    normalized = str(path).replace("\\", "/")
    return f"-javaagent:{normalized}={AUTHLIB_INJECTOR_URL}"


def prepend_authlib_jvm(extra_jvm: str, jar_path: Path | None = None) -> str:
    agent = build_authlib_jvm_arg(jar_path)
    rest = (extra_jvm or "").strip()
    return f"{agent} {rest}".strip() if rest else agent
