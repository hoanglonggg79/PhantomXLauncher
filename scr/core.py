from __future__ import annotations

import os
import sys
import json
import shutil
import hashlib
import platform
import threading
import time
import subprocess
import socket
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from loguru import logger

try:
    from PyQt6.QtCore import QThread, pyqtSignal, QObject, QUrl
    from PyQt6.QtGui import QDesktopServices
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False
    class QObject:
        pass
    class QThread:
        def __init__(self):
            pass
        def start(self):
            pass
    def pyqtSignal(*args, **kwargs):
        return None
    class QUrl:
        def __init__(self, url):
            self.url = url
    class QDesktopServices:
        @staticmethod
        def openUrl(url):
            pass

try:
    import minecraft_launcher_lib as mcll
    import minecraft_launcher_lib.microsoft_account as msa
    try:
        import minecraft_launcher_lib._helper as _mcll_helper
        import minecraft_launcher_lib.utils as _mcll_utils
        if getattr(_mcll_helper, "_user_agent_cache", None) is None:
            _mcll_helper._user_agent_cache = "minecraft-launcher-lib/8.0"
        if getattr(_mcll_utils, "_version_cache", None) is None:
            _mcll_utils._version_cache = "8.0"
    except Exception:
        pass
except ImportError:
    sys.stderr.write("❌ minecraft-launcher-lib missing. Run: pip install minecraft-launcher-lib\n")
    sys.exit(1)

import uuid as _uuid_mod

try:
    import requests
except ImportError:
    sys.stderr.write("❌ requests missing. Run: pip install requests\n")
    sys.exit(1)

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from platformdirs import user_data_dir
except ImportError:
    def user_data_dir(a, b):
        return os.path.expanduser(f"~/.{a}")


if platform.system() == "Windows":
    _ORIGINAL_POPEN_INIT = subprocess.Popen.__init__

    def _apply_hidden_subprocess_flags(kwargs: dict) -> dict:
        kwargs["creationflags"] = kwargs.get("creationflags", 0)
        kwargs["creationflags"] |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            si = kwargs.get("startupinfo")
            if si is None:
                si = subprocess.STARTUPINFO()
                kwargs["startupinfo"] = si
            si.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
            si.wShowWindow = 0  # SW_HIDE
        except Exception:
            pass
        return kwargs

    def _hidden_popen_init(self, *args, **kwargs):
        _apply_hidden_subprocess_flags(kwargs)
        _ORIGINAL_POPEN_INIT(self, *args, **kwargs)

    subprocess.Popen.__init__ = _hidden_popen_init


APP_NAME    = "PhantomX"
APP_VERSION = "1.2.1"
APP_AUTHOR  = "PhantomXTeam"
KEYRING_SVC = "PhantomXLauncher"
WATERMARK   = "Phát triển bởi HoangLong ❤️ 🇻🇳"

if getattr(sys, "frozen", False):
    _APP_BASE = Path(sys.executable).parent
else:
    _APP_BASE = Path(__file__).parent


def _resolve_base_dir() -> Path:
    try:
        from sidecar.utils.path_resolver import get_base_dir

        return get_base_dir()
    except Exception:
        return Path(user_data_dir(APP_NAME, APP_AUTHOR))


BASE_DIR    = _resolve_base_dir()
LOG_DIR     = BASE_DIR / "logs"
INST_DIR    = BASE_DIR / "instances"
CONFIG_FILE = BASE_DIR / "config.json"

THEME_DIR   = _APP_BASE / "theme"
MUSIC_FILE  = THEME_DIR / "music.mp3"
ICON_FILE   = _APP_BASE / "icon.ico"

for _d in [BASE_DIR, LOG_DIR, INST_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / f"phantomx_{datetime.now():%Y%m%d_%H%M%S}.log"

logger.remove()
if sys.stderr is not None:
    logger.add(
        sys.stderr, level="DEBUG", colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}"
    )
logger.add(
    LOG_FILE, level="DEBUG", rotation="10 MB", retention="14 days",
    encoding="utf-8",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {module}:{line} | {message}"
)
logger.info(f"PhantomX {APP_VERSION} starting — log: {LOG_FILE}")

class Instance:
    def __init__(
        self,
        name: str,
        version_id: str,
        loader: str = "vanilla",
        loader_version: str = "",
        game_dir: str = "",
    ):
        self.name = name
        self.version_id = version_id
        self.loader = loader
        self.loader_version = loader_version
        self.game_dir = game_dir or str(INST_DIR / name)
        self.mods: List[Dict] = []
        self.created_at = datetime.now().isoformat()
        self.last_played = ""
        self.play_count = 0
        self.notes = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "Instance":
        obj = cls.__new__(cls)
        obj.__dict__.update(d)
        return obj

    @property
    def instance_dir(self) -> Path:
        return Path(self.game_dir)

    @property
    def mods_dir(self) -> Path:
        return self.instance_dir / "mods"

    @property
    def config_path(self) -> Path:
        return self.instance_dir / "instance.json"

    def save(self):
        self.instance_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.to_dict(), indent=2), encoding="utf-8"
        )
        logger.debug(f"Instance saved: {self.name}")

    @classmethod
    def load(cls, path: Path) -> Optional["Instance"]:
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception as e:
            logger.error(f"Failed to load instance {path}: {e}")
            return None

class Signals(QObject):
    log = pyqtSignal(str, str)
    progress = pyqtSignal(int, int, str)
    java_status = pyqtSignal(bool, str)
    versions_ok = pyqtSignal(list)
    dl_done = pyqtSignal(bool, str)
    game_exited = pyqtSignal(int)
    status_msg = pyqtSignal(str)

# ── Download resilience for minecraft-launcher-lib ────────────────────────────
#
# Stock mcll downloads assets/libraries through `_helper.download_file`, which is
# a bare `requests.get(stream=True)` with NO timeout and NO retry, fanned out by
# `ThreadPoolExecutor(max_workers=None)` (i.e. min(32, cpu+4) parallel TLS
# connections to resources.download.minecraft.net). One connection killed by an
# antivirus TLS inspector, a corporate proxy, a flaky router or CDN throttling
# raises SSLEOFError/ConnectionResetError, which propagates straight out of
# `future.result()` and aborts the entire install with the useless message
# "Failed to install Minecraft X". These constants + the patches below make that
# failure survivable.
MCL_DOWNLOAD_WORKERS = 8      # was up to 32 concurrent TLS connections
MCL_DOWNLOAD_RETRIES = 4      # attempts per single file
MCL_DOWNLOAD_TIMEOUT = 30     # seconds, per request (stock passes none at all)
MCL_CONNECT_TIMEOUT = 10      # seconds to establish the TCP/TLS connection
INSTALL_ATTEMPTS = 3          # whole-install retries in install_vanilla()

# ── Mojang version manifest sources ──────────────────────────────────────────
#
# mcll hard-codes the legacy `launchermeta.mojang.com` host. Mojang migrated it
# to `piston-meta.mojang.com`, and a number of ISPs / antivirus products block
# the legacy host outright. Worse, the manifest request is issued *inline* by
# `mcll.install.install_minecraft_version()` as a bare `requests.get()` with no
# timeout, so it is NOT covered by the `download_file` patches below: on a
# blocked network it hangs for the OS TCP timeout (~21s on Windows) on every one
# of the INSTALL_ATTEMPTS retries and then surfaces an opaque
# "Failed to install Minecraft X".
#
# Two mitigations, in order of strength:
#   1. `ensure_version_json()` pre-seeds <game_dir>/versions/<v>/<v>.json, which
#      makes mcll skip the manifest request entirely (`install_minecraft_version`
#      short-circuits to `do_version_install` when that file exists).
#   2. Every remaining manifest URL is rewritten onto the source chain below, so
#      a blocked host falls through to a mirror instead of hanging.
MOJANG_MANIFEST_SOURCES = [
    "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
    "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json",
    "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json",
]
MANIFEST_PATH_SUFFIX = "/mc/game/version_manifest_v2.json"
LEGACY_MANIFEST_HOST = "launchermeta.mojang.com"
CURRENT_MANIFEST_HOST = "piston-meta.mojang.com"
MANIFEST_ATTEMPTS = 2         # per source — keep total worst case bounded

# Optional CDN override for networks that cannot reach Mojang's asset/library
# hosts. Set PHANTOMX_ASSET_MIRROR=https://bmclapi2.bangbang93.com to serve
# assets from <mirror>/assets/<hash> and libraries from <mirror>/maven/<path>.
ASSET_MIRROR = os.environ.get("PHANTOMX_ASSET_MIRROR", "").strip().rstrip("/")

MOJANG_UNREACHABLE_HINT = (
    "Không thể kết nối tới máy chủ của Mojang. Kiểm tra kết nối mạng, "
    "proxy/VPN hoặc phần mềm diệt virus đang chặn truy cập."
)

_mcll_resilience_applied = False


def _is_manifest_url(url: str) -> bool:
    return str(url).split("?")[0].endswith(MANIFEST_PATH_SUFFIX)


def _manifest_source_chain(url: str) -> list:
    """Rewrite a manifest URL onto the preferred-source chain, legacy host last."""
    if not _is_manifest_url(url):
        if LEGACY_MANIFEST_HOST in url:
            return [url.replace(LEGACY_MANIFEST_HOST, CURRENT_MANIFEST_HOST), url]
        return [url]
    ordered = list(MOJANG_MANIFEST_SOURCES)
    if url in ordered:
        ordered.remove(url)
        # mcll always asks for the legacy host; do not let that put it first.
        if LEGACY_MANIFEST_HOST not in url:
            ordered.insert(0, url)
    return ordered


def _get_with_source_chain(url: str, attempts: int = MANIFEST_ATTEMPTS):
    """
    GET `url`, falling through the alternative sources when it cannot be reached.

    Always passes an explicit connect/read timeout — the whole point being that
    mcll's own manifest request does not, and would otherwise hang for the OS
    TCP timeout on every retry.
    """
    last_error: Optional[BaseException] = None
    for source in _manifest_source_chain(url):
        for attempt in range(1, attempts + 1):
            try:
                response = requests.get(
                    source,
                    headers={"user-agent": "PhantomX-Sidecar/1.0"},
                    timeout=(MCL_CONNECT_TIMEOUT, MCL_DOWNLOAD_TIMEOUT),
                )
                if response.status_code == 200:
                    if source != url:
                        logger.info(f"Manifest served by fallback source: {source}")
                    return response
                last_error = RuntimeError(f"HTTP {response.status_code} from {source}")
            except Exception as exc:
                last_error = exc
            if attempt < attempts:
                time.sleep(min(0.5 * (2 ** (attempt - 1)), 3.0))
        logger.debug(f"Manifest source failed: {source} ({last_error})")

    raise requests.exceptions.ConnectionError(
        f"Không thể tải {url} từ bất kỳ nguồn nào (lỗi cuối: {last_error})"
    )


def _fetch_manifest() -> Optional[dict]:
    """Version manifest from the first reachable source, or None."""
    try:
        return _get_with_source_chain(MOJANG_MANIFEST_SOURCES[0]).json()
    except Exception as exc:
        logger.error(f"Mojang version manifest unavailable: {exc}")
        return None


def _apply_asset_mirror(data: dict) -> dict:
    """Point every asset/library URL at ASSET_MIRROR, if one is configured."""
    if not ASSET_MIRROR:
        return data
    try:
        text = json.dumps(data)
        for original, mirrored in (
            ("https://resources.download.minecraft.net", f"{ASSET_MIRROR}/assets"),
            ("https://libraries.minecraft.net", f"{ASSET_MIRROR}/maven"),
        ):
            text = text.replace(original, mirrored)
        return json.loads(text)
    except Exception as exc:
        logger.warning(f"Could not rewrite URLs onto asset mirror: {exc}")
        return data


def ensure_version_json(version_id: str, game_dir: str, _depth: int = 0) -> Optional[Path]:
    """
    Make sure <game_dir>/versions/<version_id>/<version_id>.json exists.

    This is the fix for "cannot install instance" on networks that block Mojang's
    manifest host: `mcll.install.install_minecraft_version()` only hits the
    network for the manifest when this file is missing, so seeding it here means
    the install never depends on that request — and when it is missing we fetch
    it through `_get_with_source_chain()` (timeout + mirror fallback) instead of
    mcll's bare `requests.get()`.
    """
    target = Path(game_dir) / "versions" / version_id / f"{version_id}.json"

    if target.is_file():
        try:
            json.loads(target.read_text(encoding="utf-8"))
            return target
        except Exception:
            logger.warning(f"Version JSON unreadable, re-downloading: {target}")
            try:
                target.unlink()
            except OSError:
                pass

    manifest = _fetch_manifest()
    if manifest is None:
        return None

    entry = next(
        (v for v in manifest.get("versions", []) if v.get("id") == version_id), None
    )
    if entry is None:
        logger.error(f"Version '{version_id}' not present in the Mojang manifest")
        return None

    data = None
    for candidate in (
        entry.get("url"),
        f"https://bmclapi2.bangbang93.com/version/{version_id}/json",
    ):
        if not candidate:
            continue
        try:
            data = _get_with_source_chain(candidate).json()
            break
        except Exception as exc:
            logger.debug(f"Version JSON source failed: {candidate} ({exc})")
    if not isinstance(data, dict) or not data.get("id"):
        logger.error(f"Could not download a valid version JSON for {version_id}")
        return None

    # A version that inherits from another (Forge-style) needs its parent on disk
    # too, otherwise mcll recurses into — and dies on — the manifest request.
    parent = data.get("inheritsFrom")
    if parent and _depth < 4:
        ensure_version_json(str(parent), game_dir, _depth + 1)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(_apply_asset_mirror(data), ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        logger.error(f"Could not write version JSON {target}: {exc}")
        return None

    logger.info(f"Version JSON ready: {target}")
    return target


def _resilient_download_file(
    url: str,
    path: str,
    callback: Optional[dict] = None,
    sha1: Optional[str] = None,
    lzma_compressed: bool = False,
    session=None,
    minecraft_directory=None,
    overwrite: bool = False,
) -> bool:
    """
    Drop-in replacement for `minecraft_launcher_lib._helper.download_file` that
    adds an explicit timeout and per-file retry with backoff.

    Behaviour mirrors the original otherwise: returns False when the file is
    already valid, returns False on a non-200 response, raises on checksum
    mismatch or when every attempt fails (so the caller can retry the phase).
    """
    import lzma
    from minecraft_launcher_lib._helper import (
        check_path_inside_minecraft_directory,
        get_sha1_hash,
        get_user_agent,
    )
    from minecraft_launcher_lib.exceptions import InvalidChecksum

    callback = callback or {}
    set_status = callback.get("setStatus") or (lambda *_: None)

    if minecraft_directory is not None:
        check_path_inside_minecraft_directory(minecraft_directory, path)

    # Already present and valid → nothing to do (matches stock behaviour).
    if os.path.isfile(path) and not overwrite:
        if sha1 is None:
            return False
        try:
            if get_sha1_hash(path) == sha1:
                return False
        except OSError:
            pass

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass

    set_status("Download " + os.path.basename(path))

    last_error: Optional[BaseException] = None

    for attempt in range(1, MCL_DOWNLOAD_RETRIES + 1):
        try:
            getter = session.get if session is not None else requests.get
            response = getter(
                url,
                stream=True,
                headers={"user-agent": get_user_agent()},
                timeout=MCL_DOWNLOAD_TIMEOUT,
            )
            try:
                if response.status_code != 200:
                    return False
                with open(path, "wb") as fh:
                    response.raw.decode_content = True
                    if lzma_compressed:
                        fh.write(lzma.decompress(response.content))
                    else:
                        shutil.copyfileobj(response.raw, fh)
            finally:
                try:
                    response.close()
                except Exception:
                    pass

            if sha1 is not None:
                checksum = get_sha1_hash(path)
                if checksum != sha1:
                    raise InvalidChecksum(url, path, sha1, checksum)

            return True

        except InvalidChecksum as exc:
            last_error = exc
            try:
                os.remove(path)
            except OSError:
                pass
        except Exception as exc:
            last_error = exc

        if attempt < MCL_DOWNLOAD_RETRIES:
            time.sleep(min(0.5 * (2 ** (attempt - 1)), 5.0))

    logger.debug(
        f"download_file gave up after {MCL_DOWNLOAD_RETRIES} attempts: {url} ({last_error})"
    )
    raise RuntimeError(
        f"Download failed after {MCL_DOWNLOAD_RETRIES} attempts: {url} ({last_error})"
    )


def _apply_mcll_resilience() -> None:
    """
    Patch minecraft-launcher-lib so its installers inherit our timeout/retry and
    a bounded worker count. Applied once, and never fatal: if the library layout
    changes, we log a warning and fall back to stock behaviour.
    """
    global _mcll_resilience_applied
    if _mcll_resilience_applied:
        return

    try:
        import importlib

        # 1. Replace the download primitive wherever it was imported.
        try:
            import minecraft_launcher_lib._helper as _helper_mod

            _helper_mod.download_file = _resilient_download_file
        except Exception as exc:
            logger.debug(f"mcll _helper patch skipped: {exc}")

        for sub in ("install", "runtime", "natives"):
            try:
                module = importlib.import_module(f"minecraft_launcher_lib.{sub}")
            except Exception:
                continue
            if hasattr(module, "download_file"):
                module.download_file = _resilient_download_file

        # 2. Route every manifest / version-JSON request through the source chain
        #    so it inherits a real timeout and the mirror fallbacks. `utils` and
        #    `_helper` bind `get_requests_response_cache` by name at import time,
        #    so both modules must be re-bound for the patch to take effect.
        try:
            import minecraft_launcher_lib._helper as _cache_helper_mod

            def _resilient_requests_response_cache(url: str):
                import datetime as _dt

                cache = getattr(_cache_helper_mod, "_requests_response_cache", {})
                now = _dt.datetime.now()
                entry = cache.get(url)
                if entry is not None and (now - entry["datetime"]).total_seconds() / 3600 < 1:
                    return entry["response"]

                response = _get_with_source_chain(url)
                try:
                    if response.status_code == 200:
                        cache[url] = {"response": response, "datetime": now}
                except Exception:
                    pass
                return response

            _cache_helper_mod.get_requests_response_cache = _resilient_requests_response_cache

            try:
                _utils_mod = importlib.import_module("minecraft_launcher_lib.utils")
                _utils_mod.get_requests_response_cache = _resilient_requests_response_cache
            except Exception as exc:
                logger.debug(f"mcll utils cache patch skipped: {exc}")
        except Exception as exc:
            logger.debug(f"mcll manifest cache patch skipped: {exc}")

        # 3. Cap the fan-out of the two parallel phases. install_minecraft_version
        #    does not expose max_workers, so we wrap the callees it resolves at
        #    call time.
        install_mod = importlib.import_module("minecraft_launcher_lib.install")

        original_libraries = install_mod.install_libraries
        original_assets = install_mod.install_assets

        def _bounded_install_libraries(id, libraries, path, callback, max_workers=None):
            return original_libraries(
                id, libraries, path, callback, max_workers=MCL_DOWNLOAD_WORKERS
            )

        def _bounded_install_assets(data, path, callback, max_workers=None):
            return original_assets(
                data, path, callback, max_workers=MCL_DOWNLOAD_WORKERS
            )

        install_mod.install_libraries = _bounded_install_libraries
        install_mod.install_assets = _bounded_install_assets

        _mcll_resilience_applied = True
        logger.info(
            f"mcll download resilience applied "
            f"(workers={MCL_DOWNLOAD_WORKERS}, retries={MCL_DOWNLOAD_RETRIES}, "
            f"timeout={MCL_DOWNLOAD_TIMEOUT}s)"
        )
    except Exception as exc:
        logger.warning(f"Could not apply mcll download resilience, using stock behaviour: {exc}")


class MinecraftManager:
    FABRIC_META = "https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
    FORGE_MAVEN = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
    QUILT_META = "https://meta.quiltmc.org/v3/versions/loader/{mc_version}"

    MODRINTH_SEARCH = "https://api.modrinth.com/v2/search"
    MODRINTH_VERSION = "https://api.modrinth.com/v2/project/{id}/version"
    CURSEFORGE_SEARCH = "https://api.curseforge.com/v1/mods/search"
    CURSEFORGE_KEY = ""

    _session: Optional[requests.Session] = None

    def __init__(self, game_dir: str = ""):
        self.game_dir = game_dir or str(BASE_DIR / "default")
        Path(self.game_dir).mkdir(parents=True, exist_ok=True)
        self._cf_key = os.environ.get("CF_API_KEY", self.CURSEFORGE_KEY)

    @property
    def session(self) -> requests.Session:
        if MinecraftManager._session is None:
            s = requests.Session()
            s.headers.update({"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
            MinecraftManager._session = s
        return MinecraftManager._session

    OPENJDK_WINGET_PACKAGES = {
        8: "Microsoft.OpenJDK.8",
        17: "Microsoft.OpenJDK.17",
        21: "Microsoft.OpenJDK.21",
        25: "Microsoft.OpenJDK.25",
    }

    def find_java(self) -> Optional[str]:
        candidates = []
        try:
            java_infos = mcll.java_utils.find_system_java_versions_information()
            for info in java_infos:
                p = info.get("path") if isinstance(info, dict) else getattr(info, "path", None)
                if p and Path(p).exists():
                    candidates.append(str(p))
        except Exception as e:
            logger.debug(f"mcll java_utils: {e}")

        jh = os.environ.get("JAVA_HOME")
        if jh:
            jp = Path(jh) / ("bin/java.exe" if platform.system() == "Windows" else "bin/java")
            if jp.exists():
                candidates.append(str(jp))

        java_exe = "java.exe" if platform.system() == "Windows" else "java"
        found = shutil.which(java_exe)
        if found:
            candidates.append(found)

        if platform.system() == "Windows":
            prog_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            for base in [prog_files / "Microsoft", prog_files / "Eclipse Adoptium", prog_files / "Java"]:
                if base.exists():
                    for jdk_dir in sorted(base.iterdir(), reverse=True):
                        jp = jdk_dir / "bin" / "java.exe"
                        if jp.exists():
                            candidates.append(str(jp))
            try:
                import winreg
                for hive in [winreg.HKEY_LOCAL_MACHINE]:
                    try:
                        with winreg.OpenKey(hive, r"SOFTWARE\JavaSoft\JDK") as key:
                            i = 0
                            while True:
                                try:
                                    sub = winreg.EnumKey(key, i)
                                    i += 1
                                    try:
                                        with winreg.OpenKey(key, sub) as subkey:
                                            home, _ = winreg.QueryValueEx(subkey, "JavaHome")
                                            jp = Path(home) / "bin" / "java.exe"
                                            if jp.exists():
                                                candidates.append(str(jp))
                                    except OSError:
                                        pass
                                except OSError:
                                    break
                    except OSError:
                        pass
            except Exception as e:
                logger.debug(f"Registry Java lookup failed: {e}")

        seen = set()
        unique = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique[0] if unique else None

    def required_java_for_mc(self, mc_version: str) -> int:
        """
        Minimum Java major for *mc_version*.

        Mojang switched to year-based versions in 2026: `26.1`, `26.2`, `26.3`…
        Those drops are compiled for Java 25 (class file 69.0) and refuse to run
        on anything older.

        Matrix:
          MC < 1.17           → Java 8
          1.17 ≤ MC < 1.20.5  → Java 17
          1.20.5 ≤ MC < 26    → Java 21
          MC ≥ 26             → Java 25
        """
        import re as _re

        raw = (mc_version or "").strip().lower()
        if not raw:
            return 21

        # Week snapshots: "25w46a" (1.21.x line) / "26w14a" (26.x line)
        m = _re.match(r"^(\d{2})w(\d+)[a-z]?$", raw)
        if m:
            return 25 if int(m.group(1)) >= 26 else 21

        raw = _re.sub(r"-(?:snapshot|pre|rc)[-.]?\d+$", "", raw)
        m = _re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", raw)
        if not m:
            return 21

        first = int(m.group(1))
        if first == 1:  # legacy "1.20.4"
            minor = int(m.group(2))
            patch = int(m.group(3) or 0)
            if minor < 17:
                return 8
            if (minor, patch) < (20, 5):
                return 17
            return 21
        if first >= 26:  # year-based "26.3"
            return 25
        return 21

    def find_java_for_version(self, mc_version: str) -> Optional[str]:
        try:
            target = self.required_java_for_mc(mc_version)
        except Exception:
            target = 21

        all_javas = self._scan_all_java_installs()
        for jp in all_javas:
            if self.java_version(jp) == target:
                return jp

        # No exact match: prefer the oldest runtime that is still new enough
        # (Java is backwards compatible), then the newest one we have.
        graded = [(self.java_version(jp), jp) for jp in all_javas]
        graded = [(v, jp) for v, jp in graded if v]
        sufficient = [(v, jp) for v, jp in graded if v >= target]
        if sufficient:
            return min(sufficient, key=lambda pair: pair[0])[1]
        if graded:
            return max(graded, key=lambda pair: pair[0])[1]
        if all_javas:
            return all_javas[0]
        return None

    def _scan_all_java_installs(self) -> List[str]:
        candidates = []
        try:
            java_infos = mcll.java_utils.find_system_java_versions_information()
            for info in java_infos:
                p = info.get("path") if isinstance(info, dict) else getattr(info, "path", None)
                if p and Path(p).exists():
                    candidates.append(str(p))
        except Exception as e:
            logger.debug(f"mcll java_utils: {e}")

        jh = os.environ.get("JAVA_HOME")
        if jh:
            jp = Path(jh) / ("bin/java.exe" if platform.system() == "Windows" else "bin/java")
            if jp.exists():
                candidates.append(str(jp))

        java_exe = "java.exe" if platform.system() == "Windows" else "java"
        found = shutil.which(java_exe)
        if found:
            candidates.append(found)

        if platform.system() == "Windows":
            prog_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            for base in [prog_files / "Microsoft", prog_files / "Eclipse Adoptium", prog_files / "Java"]:
                if base.exists():
                    for jdk_dir in sorted(base.iterdir(), reverse=True):
                        jp = jdk_dir / "bin" / "java.exe"
                        if jp.exists():
                            candidates.append(str(jp))
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JDK") as key:
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(key, i)
                            i += 1
                            try:
                                with winreg.OpenKey(key, sub) as subkey:
                                    home, _ = winreg.QueryValueEx(subkey, "JavaHome")
                                    jp = Path(home) / "bin" / "java.exe"
                                    if jp.exists():
                                        candidates.append(str(jp))
                            except OSError:
                                pass
                        except OSError:
                            break
            except Exception as e:
                logger.debug(f"Registry Java lookup failed: {e}")

        def _ver_key(p: str) -> int:
            v = self.java_version(p)
            return v if v is not None else -1

        candidates.sort(key=_ver_key, reverse=True)
        seen = set()
        unique = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    def java_version(self, java_path: str) -> Optional[int]:
        """
        Major Java version of the given binary, or None when it cannot run.

        On Windows, `CreateProcess` raises WinError 5 ("Access is denied") when
        the path is a directory, a stale shortcut, or a binary blocked by an
        antivirus / Controlled Folder Access rule. The old code swallowed that
        as a generic warning, so the launcher reported "unknown version" and
        then failed later inside the loader installers (which shell out to
        `java -jar`). We now try the sibling binary (java.exe <-> javaw.exe),
        fall back to `java` on PATH, and log *why* nothing worked.
        """
        import re

        def _probe(exe: str) -> tuple[bool, Optional[int], Optional[str]]:
            """(ran successfully, version, error description)."""
            if not exe or not Path(exe).is_file():
                return False, None, f"không phải tệp thực thi: {exe}"
            try:
                r = subprocess.run(
                    [exe, "-version"],
                    capture_output=True, text=True, timeout=5,
                    encoding="utf-8", errors="replace",
                )
            except PermissionError as exc:
                return False, None, f"từ chối quyền thực thi (WinError 5) — {exe}: {exc}"
            except subprocess.TimeoutExpired:
                return False, None, f"hết thời gian chờ khi chạy {exe}"
            except OSError as exc:
                return False, None, f"không thể chạy {exe}: {exc}"

            out = ((r.stderr or "") + (r.stdout or "")).lower()
            for line in out.splitlines():
                if "version" in line:
                    m = re.search(r'"(\d+)[\._]', line)
                    if m:
                        v = int(m.group(1))
                        return True, (8 if v == 1 else v), None
            return True, None, f"không đọc được số phiên bản từ {exe}"

        variants: List[str] = []
        if java_path:
            variants.append(java_path)
            low = java_path.lower()
            if low.endswith("javaw.exe"):
                variants.append(java_path[:-9] + "java.exe")
            elif low.endswith("java.exe"):
                variants.append(java_path[:-10] + "javaw.exe")

        errors: List[str] = []
        seen = set()
        for exe in variants:
            key = os.path.normcase(os.path.normpath(exe))
            if key in seen:
                continue
            seen.add(key)
            ran, version, err = _probe(exe)
            if ran:
                return version          # may be None — output parsed but empty
            if err:
                errors.append(err)

        # Every explicit candidate was unusable: try whatever `java` is on PATH
        # rather than reporting "no Java", which would abort the install.
        path_java = shutil.which("java.exe" if platform.system() == "Windows" else "java")
        if path_java and os.path.normcase(os.path.normpath(path_java)) not in seen:
            ran, version, err = _probe(path_java)
            if ran:
                logger.info(f"java_version: dùng Java trên PATH ({path_java}) thay cho '{java_path}'")
                return version
            if err:
                errors.append(err)

        for err in errors:
            logger.warning(f"java_version: {err}")
        return None

    def check_java(self, java_path: str = "") -> tuple[bool, str]:
        jp = java_path.strip() if java_path else ""
        if not jp:
            if CONFIG_FILE.exists():
                try:
                    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                    jp = cfg.get("java_path", "").strip()
                except Exception as e:
                    logger.warning(f"Config load error in check_java: {e}")

        if jp:
            if Path(jp).exists():
                v = self.java_version(jp)
                if v is None:
                    return True, f"✅ Java (Tùy chỉnh) "
                return True, f"✅ Java {v} (Tùy chỉnh) "
            else:
                logger.warning(f"Customized Java path not found: {jp}. Falling back to system Java.")

        jp = self.find_java()
        if not jp:
            return False, "❌ Không tìm thấy Java — Hãy cài đặt Java trong setting"
        v = self.java_version(jp)
        if v is None:
            return False, f"⚠️  Có Java nhưng phiên bản không thể xác định được ({jp})"
        return True, f"✅ Java {v} — {jp}"

    def get_versions(self, include_snapshots: bool = False) -> list:
        keep_types = {"release"}
        if include_snapshots:
            keep_types.add("snapshot")

        try:
            all_v = mcll.utils.get_version_list()
            res = [v for v in all_v if v.get("type") in keep_types]
            if res:
                return res
            logger.warning("mcll.utils.get_version_list returned 0 matching versions, attempting fallback.")
        except Exception as e:
            logger.warning(f"mcll.utils.get_version_list failed: {e}. Attempting direct Mojang manifest fallback.")

        # Fallback used to re-request the *same* legacy `launchermeta` host that
        # mcll just failed on, so it could never help. Go through the source
        # chain instead (piston-meta first, then mirrors).
        data = _fetch_manifest()
        if data:
            fallback_versions = [
                {
                    "id": item.get("id"),
                    "type": item.get("type"),
                    "releaseTime": item.get("releaseTime"),
                    "complianceLevel": item.get("complianceLevel", 0),
                }
                for item in data.get("versions", [])
                if item.get("type") in keep_types
            ]
            logger.info(f"Loaded {len(fallback_versions)} versions via manifest source chain.")
            return fallback_versions

        return []

    def is_version_installed(self, version_id: str, game_dir: str) -> bool:
        ver_dir = Path(game_dir) / "versions" / version_id
        jar = ver_dir / f"{version_id}.jar"
        json_f = ver_dir / f"{version_id}.json"
        ok = jar.exists() and json_f.exists()
        logger.debug(f"is_version_installed({version_id}): {ok}")
        return ok

    def is_loader_installed(self, instance: "Instance") -> bool:
        if instance.loader == "vanilla":
            return self.is_version_installed(instance.version_id, instance.game_dir)
        versions_dir = Path(instance.game_dir) / "versions"
        if not versions_dir.exists():
            return False
        keyword = instance.loader.lower()
        for d in versions_dir.iterdir():
            if d.is_dir() and keyword in d.name.lower() and instance.version_id in d.name:
                return True
        return False

    def install_vanilla(
        self, version_id: str, game_dir: str, cb_progress=None, cb_log=None
    ) -> bool:
        """
        Install (or repair) a vanilla version.

        mcll is idempotent — it skips every file whose SHA-1 already matches — so
        a transient network failure can simply be retried, and the retry resumes
        instead of starting over. Each attempt also benefits from the bounded
        concurrency and per-file retry installed by `_apply_mcll_resilience()`.
        """
        _apply_mcll_resilience()

        if cb_log:
            cb_log(f"📦 Đang cài đặt Minecraft {version_id}…")

        # Seed the version JSON ourselves. mcll only fetches the manifest when
        # this file is missing, and its fetch is a bare requests.get() with no
        # timeout against a single (often blocked) legacy host — which is what
        # made installs hang ~21s per attempt and then fail. Failing fast here
        # also avoids three pointless retries of a request we know cannot work.
        if ensure_version_json(version_id, game_dir) is None:
            logger.error(f"install_vanilla: cannot obtain version JSON for {version_id}")
            if cb_log:
                cb_log(f"❌ {MOJANG_UNREACHABLE_HINT}")
            return False

        def _cb(current, maximum, label):
            try:
                c = int(current or 0)
                t = int(maximum or 0)
                s = str(label or "Đang tải…")
                if cb_progress:
                    cb_progress(c, t, s)
                if cb_log and s:
                    cb_log(f"  {s}")
            except Exception as inner:
                logger.debug(f"Progress callback error: {inner}")

        def _cb_legacy(data):
            if isinstance(data, dict):
                c = data.get("current", 0)
                t = data.get("total", data.get("max", 0))
                s = data.get("status", data.get("label", "Downloading…"))
            else:
                c, t, s = 0, 0, str(data)
            if cb_progress and t:
                cb_progress(int(c), int(t), str(s))
            if cb_log and s:
                cb_log(f"  {s}")

        last_error: Optional[BaseException] = None
        use_legacy = False

        for attempt in range(1, INSTALL_ATTEMPTS + 1):
            try:
                if use_legacy:
                    mcll.install.install_minecraft_version(
                        version_id, game_dir, callback=_cb_legacy
                    )
                else:
                    mcll.install.install_minecraft_version(
                        version_id,
                        game_dir,
                        callback={
                            "setStatus": lambda s: _cb(0, 0, s),
                            "setProgress": lambda c: None,
                            "setMax": lambda m: None,
                        },
                    )
                logger.info(f"Vanilla {version_id} đã được cài đặt vào {game_dir}")
                return True

            except TypeError as e:
                # mcll changed its callback contract — fall back to the legacy
                # dict once, without treating it as a transient network failure.
                if not use_legacy:
                    use_legacy = True
                    logger.warning(
                        f"mcll callback signature mismatch, retrying with legacy callback: {e}"
                    )
                    if cb_log:
                        cb_log("📦 Thử cài đặt lại với legacy callback…")
                    continue
                last_error = e

            except Exception as e:
                last_error = e

            logger.warning(
                f"install_vanilla attempt {attempt}/{INSTALL_ATTEMPTS} failed: {last_error}"
            )

            if attempt < INSTALL_ATTEMPTS:
                # 1s/2s was far too short to outlive any real network hiccup.
                delay = min(3 * attempt, 15)
                if cb_log:
                    cb_log(f"⚠️ Lỗi khi tải (lần {attempt}/{INSTALL_ATTEMPTS}): {last_error}")
                    cb_log(f"🔄 Đang thử lại sau {delay}s…")
                time.sleep(delay)

        if last_error is None:
            last_error = RuntimeError("Install did not complete")

        logger.error(f"install_vanilla failed after {INSTALL_ATTEMPTS} attempts: {last_error}")
        if cb_log:
            cb_log(f"❌ Lỗi cài đặt: {last_error}")
        return False

    def install_fabric(
        self,
        mc_version: str,
        loader_version: str,
        game_dir: str,
        java_path: str = "",
        cb_log=None,
    ) -> bool:
        try:
            if cb_log:
                cb_log(f"🧵 Đang cài Fabric {loader_version or 'latest'} cho phiên bản {mc_version}…")
            lv = loader_version.strip() or None
            jp = java_path.strip() or None
            if jp and jp.lower().endswith("javaw.exe"):
                jp = jp[:-9] + "java.exe"
            mcll.fabric.install_fabric(mc_version, game_dir, loader_version=lv, java=jp)
            logger.info(f"Fabric installed: mc={mc_version} loader={lv}")
            return True
        except Exception as e:
            logger.error(f"install_fabric: {e}")
            if cb_log:
                cb_log(f"❌ Lỗi cài đặt Fabric: {e}")
            return False

    def install_forge(
        self,
        mc_version: str,
        forge_version: str,
        game_dir: str,
        java_path: str,
        cb_log=None,
    ) -> bool:
        try:
            if cb_log:
                cb_log(f"⚙️  Đang cài Forge {forge_version} cho phiên bản {mc_version}…")
            version_str = f"{mc_version}-{forge_version}" if forge_version else mc_version
            mcll.forge.install_forge_version(version_str, game_dir, java=java_path)
            logger.info(f"Forge đã được cài đặt: {version_str}")
            return True
        except PermissionError as pe:
            logger.warning(f"install_forge PermissionError (retrying): {pe}")
            if cb_log:
                cb_log(f"⚠️  Lỗi quyền — đang thử lại trong 2 giây…")
            time.sleep(2)
            try:
                mcll.forge.install_forge_version(version_str, game_dir, java=java_path)
                logger.info(f"Forge đã được cài đặt (thử lại): {version_str}")
                return True
            except Exception as e2:
                logger.error(f"install_forge retry failed: {e2}")
                if cb_log:
                    cb_log(f"❌ Forge lỗi (thử lại): {e2}")
                return False
        except Exception as e:
            logger.error(f"install_forge: {e}")
            if cb_log:
                cb_log(f"❌ Forge lỗi: {e}")
            return False

    def get_fabric_loaders(self, mc_version: str) -> list:
        try:
            url = self.FABRIC_META.format(mc_version=mc_version)
            r = self.session.get(url, timeout=10)
            r.raise_for_status()
            return [entry["loader"]["version"] for entry in r.json()]
        except Exception as e:
            logger.warning(f"get_fabric_loaders: {e}")
            return []

    def get_forge_versions(self, mc_version: str) -> list:
        try:
            r = self.session.get(self.FORGE_MAVEN, timeout=10)
            r.raise_for_status()
            data = r.json().get("promos", {})
            versions = []
            for k, v in data.items():
                if k.startswith(mc_version + "-"):
                    versions.append(v)
            return sorted(set(versions), reverse=True)
        except Exception as e:
            logger.warning(f"get_forge_versions: {e}")
            return []

    def install_quilt(
        self,
        mc_version: str,
        loader_version: str,
        game_dir: str,
        java_path: str = "",
        cb_log=None,
    ) -> bool:
        try:
            if cb_log:
                cb_log(f"🪡 Đang cài đặt Quilt {loader_version or 'latest'} cho phiên bản {mc_version}…")
            lv = loader_version.strip() or None
            jp = java_path.strip() or None
            if jp and jp.lower().endswith("javaw.exe"):
                jp = jp[:-9] + "java.exe"
            try:
                mcll.quilt.install_quilt(mc_version, game_dir, loader_version=lv, java=jp)
            except (AttributeError, TypeError):
                from minecraft_launcher_lib import mod_loader as _ml
                _loader = _ml.get_mod_loader("quilt")
                _loader.install(mc_version, game_dir, loader_version=lv, java=jp)
            logger.info(f"Quilt đã được cài đặt: {mc_version}")
            return True
        except Exception as e:
            logger.error(f"install_quilt failed: {e}")
            if cb_log:
                cb_log(f"❌ Quilt lỗi: {e}")
            return False

    def install_neoforge(
        self,
        mc_version: str,
        neoforge_version: str,
        game_dir: str,
        java_path: str = "",
        cb_log=None,
    ) -> bool:
        try:
            if cb_log:
                cb_log(f"⚙️  Đang cài đặt NeoForge {neoforge_version} cho phiên bản {mc_version}…")
            lv = neoforge_version.strip() or None
            full_neoforge = f"{mc_version}-{lv}" if lv else mc_version
            try:
                mcll.neoforge.install_neoforge_version(
                    full_neoforge, game_dir, java=java_path or None
                )
            except AttributeError:
                from minecraft_launcher_lib import mod_loader as _ml
                _loader = _ml.get_mod_loader("neoforge")
                _loader.install(mc_version, game_dir, loader_version=lv)
            logger.info(f"NeoForge đã được cài đặt: {full_neoforge}")
            return True
        except PermissionError as pe:
            logger.warning(f"install_neoforge PermissionError (retrying): {pe}")
            if cb_log:
                cb_log(f"⚠️  Lỗi quyền — đang thử lại trong 2 giây…")
            time.sleep(2)
            try:
                mcll.neoforge.install_neoforge_version(
                    full_neoforge, game_dir, java=java_path or None
                )
                return True
            except Exception as e2:
                logger.error(f"install_neoforge retry: {e2}")
                if cb_log:
                    cb_log(f"❌ NeoForge error (retry): {e2}")
                return False
        except Exception as e:
            logger.error(f"install_neoforge failed: {e}")
            if cb_log:
                cb_log(f"❌ NeoForge lỗi: {e}")
            return False

    def search_modrinth(
        self, query: str, mc_version: str = "", loader: str = "", limit: int = 20
    ) -> List[Dict]:
        try:
            facets = [["project_type:mod"]]
            if mc_version:
                facets.append([f"versions:{mc_version}"])
            if loader and loader != "vanilla":
                facets.append([f"categories:{loader}"])

            params = {
                "query": query,
                "limit": limit,
                "facets": json.dumps(facets),
            }
            r = self.session.get(self.MODRINTH_SEARCH, params=params, timeout=10)
            r.raise_for_status()
            return r.json().get("hits", [])
        except Exception as e:
            logger.warning(f"search_modrinth: {e}")
            return []

    def get_modrinth_versions(
        self, project_id: str, mc_version: str = "", loader: str = ""
    ) -> List[Dict]:
        try:
            url = self.MODRINTH_VERSION.format(id=project_id)
            params = {}
            if mc_version:
                params["game_versions"] = json.dumps([mc_version])
            if loader and loader != "vanilla":
                params["loaders"] = json.dumps([loader])
            r = self.session.get(url, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"get_modrinth_versions: {e}")
            return []

    def download_mod(
        self,
        url: str,
        filename: str,
        mods_dir: Path,
        cb_progress=None,
        cb_log=None,
    ) -> bool:
        try:
            mods_dir.mkdir(parents=True, exist_ok=True)
            dest = mods_dir / filename
            if cb_log:
                cb_log(f"⬇️  Đang tải {filename}…")

            r = self.session.get(url, stream=True, timeout=30)
            r.raise_for_status()

            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if cb_progress and total:
                            cb_progress(downloaded, total, f"Đang tải {filename}")

            if cb_log:
                cb_log(f"✅ {filename} đã được tải xuống ({downloaded // 1024} KB)")
            logger.info(f"Mod đã được tải xuống: {dest}")
            return True
        except Exception as e:
            logger.error(f"download_mod: {e}")
            if cb_log:
                cb_log(f"❌ Lỗi tải xuống: {e}")
            return False

    def build_command(
        self,
        version_id: str,
        username: str,
        game_dir: str,
        max_ram: int,
        extra_jvm: str = "",
        java_path: str = "",
        uuid: str = "",
        token: str = "",
    ) -> list:
        java = java_path or self.find_java_for_version(version_id) or self.find_java() or "java"

        jvm_args = [
            f"-Xmx{max_ram}M",
            f"-Xms{min(512, max_ram // 4)}M",
            "-XX:+UseG1GC",
            "-XX:+ParallelRefProcEnabled",
            "-XX:MaxGCPauseMillis=200",
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:+DisableExplicitGC",
            "-XX:+AlwaysPreTouch",
            "-XX:G1NewSizePercent=30",
            "-XX:G1MaxNewSizePercent=40",
            "-XX:G1HeapRegionSize=8M",
            "-XX:G1ReservePercent=20",
            "-XX:G1HeapWastePercent=5",
            "-XX:G1MixedGCCountTarget=4",
            "-XX:InitiatingHeapOccupancyPercent=15",
            "-XX:G1MixedGCLiveThresholdPercent=90",
            "-XX:G1RSetUpdatingPauseTimePercent=5",
            "-XX:SurvivorRatio=32",
            "-XX:+PerfDisableSharedMem",
            "-XX:MaxTenuringThreshold=1",
            "-Dusing.aikars.flags=https://mcflags.emc.gs",
            "-Dfile.encoding=UTF-8",
            "-Dstdout.encoding=UTF-8",
        ]
        if extra_jvm:
            jvm_args += extra_jvm.split()

        if not uuid:
            try:
                uuid = str(_uuid_mod.uuid3(_uuid_mod.NAMESPACE_DNS, username))
            except Exception:
                uuid = str(_uuid_mod.uuid4())

        options = {
            "username": username,
            "uuid": uuid,
            "token": token,
            "jvmArguments": jvm_args,
            "launcherName": APP_NAME,
            "launcherVersion": APP_VERSION,
        }
        try:
            cmd = mcll.command.get_minecraft_command(version_id, game_dir, options)
        except Exception as e:
            logger.error(f"build_command failed: {e}")
            raise

        if cmd:
            cmd[0] = java
        logger.debug(f"Launch command built ({len(cmd)} args), java={java}")
        return cmd

    def pre_launch_cleanup(self, game_dir: str, cb_log=None):
        removed = 0
        base = Path(game_dir)
        for pattern in ["*.tmp", "*.lock"]:
            for f in base.rglob(pattern):
                try:
                    f.unlink()
                    removed += 1
                except Exception:
                    pass
        crash_dir = base / "crash-reports"
        if crash_dir.exists():
            crashes = sorted(
                crash_dir.glob("*.txt"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            for old in crashes[10:]:
                try:
                    old.unlink()
                    removed += 1
                except Exception:
                    pass
        if cb_log:
            cb_log(f"🧹 Pre-launch cleanup: removed {removed} temp file(s)")
        logger.info(f"Pre-launch cleanup done ({removed} files) in {game_dir}")

    def scan_mods(self, mods_dir: Path) -> List[Dict]:
        mods = []
        if not mods_dir.exists():
            return mods
        for f in mods_dir.iterdir():
            try:
                if not f.is_file():
                    continue
                if f.suffix.lower() not in (".jar", ".disabled"):
                    continue
                enabled = f.suffix.lower() == ".jar"
                mods.append(
                    {
                        "filename": f.name,
                        "path": str(f),
                        "enabled": enabled,
                        "size_kb": round(f.stat().st_size / 1024, 1),
                        "sha1": self._sha1(f),
                    }
                )
            except OSError as e:
                logger.warning(f"scan_mods skip {f}: {e}")
        return sorted(mods, key=lambda m: m["filename"].lower())

    def toggle_mod(self, mod_path: str) -> str:
        p = Path(mod_path)
        if not p.exists():
            logger.warning(f"toggle_mod: file not found {mod_path}")
            return mod_path
        new_p = p.with_suffix(".jar" if p.suffix == ".disabled" else ".disabled")
        p.rename(new_p)
        logger.info(f"Mod toggled: {p.name} → {new_p.name}")
        return str(new_p)

    def delete_mod(self, mod_path: str):
        p = Path(mod_path)
        if p.exists():
            p.unlink()
            logger.info(f"Mod deleted: {mod_path}")
        else:
            logger.warning(f"delete_mod: file not found {mod_path}")

    @staticmethod
    def _sha1(path: Path) -> str:
        h = hashlib.sha1()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except OSError:
            return "??????"
        return h.hexdigest()[:8]

    @staticmethod
    def _sha1_full(path: Path) -> str:
        h = hashlib.sha1()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()

    def get_available_java_runtimes(self) -> list:
        try:
            return mcll.runtime.get_available_runtimes()
        except Exception as e:
            logger.error(f"get_available_java_runtimes failed: {e}")
            return []

    def install_openjdk_winget(
        self,
        java_version: int,
        cb_log=None,
    ) -> Optional[str]:
        pkg = self.OPENJDK_WINGET_PACKAGES.get(java_version)
        if not pkg:
            if cb_log:
                cb_log(f"❌ Không hỗ trợ cài đặt Java {java_version} qua Winget.")
            return None

        if platform.system() != "Windows":
            if cb_log:
                cb_log("⚠️ Winget chỉ khả dụng trên Windows. Đang thử tải Mojang runtime...")
            return self.install_java_runtime_mojang(java_version, cb_log=cb_log)

        if cb_log:
            cb_log(f"☕ Đang cài đặt OpenJDK {java_version} qua Winget ({pkg})…")
            cb_log("🔐 Cửa sổ UAC có thể xuất hiện — vui lòng chấp nhận để tiếp tục.")

        cmd = (
            f"winget install {pkg} --silent "
            f"--accept-package-agreements --accept-source-agreements"
        )

        try:
            rc, output = run_powershell_elevated_silent(cmd, cb_log=cb_log)
        except Exception as e:
            logger.error(f"install_openjdk_winget elevated powershell failed: {e}")
            if cb_log:
                cb_log(f"❌ Lỗi khi chạy Winget: {e}")
            return None

        if rc != 0:
            logger.error(f"winget install {pkg} failed with exit code {rc}")
            if cb_log:
                cb_log(f"❌ Winget cài đặt thất bại (mã lỗi {rc}).")
                cb_log(f"   Kiểm tra Log tab để biết chi tiết.")
            return None

        best = self._find_openjdk_by_major(java_version)
        if best:
            if cb_log:
                cb_log(f"✅ OpenJDK {java_version} đã được cài đặt thành công: {best}")
            self._update_java_path_in_config(best)
            return best

        if cb_log:
            cb_log("✅ Winget báo thành công nhưng chưa tìm thấy java.exe — thử làm mới PATH…")
        self._refresh_path_from_registry()
        best = self._find_openjdk_by_major(java_version)
        if best:
            if cb_log:
                cb_log(f"✅ OpenJDK {java_version} đã được cài đặt thành công: {best}")
            self._update_java_path_in_config(best)
            return best

        if cb_log:
            cb_log("⚠️ Không thể xác định đường dẫn Java mới — vui lòng kiểm tra thủ công.")
        return None

    def install_java_runtime_mojang(
        self, java_version: int, cb_log=None, cb_progress=None
    ) -> Optional[str]:
        runtime_map = {
            8: "java-runtime-legacy",
            17: "java-runtime-gamma",
            21: "java-runtime-delta",
            25: "java-runtime-epsilon",
        }
        runtime_name = runtime_map.get(java_version)
        if not runtime_name:
            if cb_log:
                cb_log(f"❌ Không hỗ trợ Java {java_version}.")
            return None

        if cb_log:
            cb_log(f"☕ Đang tải môi trường chạy Java (Mojang): {runtime_name}...")

        state = {"current": 0, "max": 0}

        def set_max(m):
            state["max"] = m
            if cb_progress:
                cb_progress(state["current"], m, "Đang tải...")

        def set_progress(c):
            state["current"] = c
            if cb_progress:
                cb_progress(c, state["max"], "Đang tải...")

        def set_status(s):
            if cb_log:
                cb_log(f"  {s}")

        try:
            mcll.runtime.install_jvm_runtime(
                runtime_name,
                self.game_dir,
                callback={
                    "setStatus": set_status,
                    "setProgress": set_progress,
                    "setMax": set_max,
                },
            )
            java_path = self._find_installed_java_path(self.game_dir, runtime_name)
            if java_path and cb_log:
                cb_log(f"✅ Cài đặt thành công: {java_path}")
            return java_path
        except Exception as e:
            logger.error(f"install_java_runtime_mojang failed: {e}")
            if cb_log:
                cb_log(f"❌ Lỗi khi cài đặt môi trường chạy Java: {e}")
            return None

    def install_java_runtime(
        self,
        runtime_name: str,
        game_dir: str = None,
        cb_log=None,
        cb_progress=None,
    ) -> Optional[str]:
        name_to_ver = {
            "java-runtime-legacy": 8,
            "java-runtime-gamma": 17,
            "java-runtime-delta": 21,
            "java-runtime-epsilon": 25,
            "java-runtime-alpha": 8,
            "java-runtime-beta": 16,
        }
        java_version = name_to_ver.get(runtime_name)
        if java_version is None:
            try:
                java_version = int(runtime_name)
            except (TypeError, ValueError):
                java_version = None

        if java_version is None:
            if cb_log:
                cb_log(f"❌ Không xác định được phiên bản Java: {runtime_name}")
            return None

        return self.install_openjdk_winget(java_version, cb_log=cb_log)

    def _find_openjdk_by_major(self, java_version: int) -> Optional[str]:
        target = "java.exe" if platform.system() == "Windows" else "java"
        prog_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        search_dirs = []
        for base in [
            prog_files / "Microsoft",
            prog_files / "Eclipse Adoptium",
            prog_files / "Java",
            prog_files / "Eclipse Foundation",
        ]:
            if base.exists():
                search_dirs.append(base)
        for base in search_dirs:
            for jdk_dir in sorted(base.iterdir(), reverse=True):
                if jdk_dir.is_dir() and f"jdk-{java_version}" in jdk_dir.name.lower():
                    jp = jdk_dir / "bin" / target
                    if jp.exists():
                        return str(jp)
        runtime_base = Path(self.game_dir) / "runtime"
        if runtime_base.exists():
            for p in runtime_base.rglob(target):
                if p.is_file() and p.parent.name == "bin":
                    if f"jdk-{java_version}" in str(p).lower() or self.java_version(str(p)) == java_version:
                        return str(p)
        return None

    def _refresh_path_from_registry(self):
        if platform.system() != "Windows":
            return
        try:
            import winreg
            for hive, flag in [
                (winreg.HKEY_LOCAL_MACHINE, 0),
                (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
            ]:
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\JavaSoft\JDK", access=winreg.KEY_READ | flag) as key:
                        i = 0
                        while True:
                            try:
                                sub = winreg.EnumKey(key, i)
                                i += 1
                                try:
                                    with winreg.OpenKey(key, sub) as subkey:
                                        home, _ = winreg.QueryValueEx(subkey, "JavaHome")
                                        bin_dir = Path(home) / "bin"
                                        if bin_dir.exists():
                                            os.environ["PATH"] = (
                                                str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                                            )
                                except OSError:
                                    pass
                            except OSError:
                                break
                except OSError:
                    pass
        except Exception as e:
            logger.debug(f"Registry PATH refresh failed: {e}")

    def _update_java_path_in_config(self, java_path: str):
        try:
            cfg = {}
            if CONFIG_FILE.exists():
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            cfg["java_path"] = java_path
            CONFIG_FILE.write_text(
                json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.info(f"Java path updated in config: {java_path}")
        except Exception as e:
            logger.warning(f"Failed to update java_path in config: {e}")

    def _find_installed_java_path(
        self, game_dir: str, runtime_name: str
    ) -> Optional[str]:
        runtime_dir = Path(game_dir) / "runtime" / runtime_name
        if not runtime_dir.exists():
            return None
        target = "java.exe" if platform.system() == "Windows" else "java"
        for p in runtime_dir.rglob(target):
            if p.is_file() and p.parent.name == "bin":
                return str(p)
        return None

class MicrosoftAuthWorker(QThread):
    login_finished = pyqtSignal(dict)
    login_failed = pyqtSignal(str)

    def __init__(self, client_id: str, port: int = 28345, timeout: int = 300):
        super().__init__()
        self.client_id = client_id
        self.port = port
        self.timeout = timeout
        self.httpd: Optional[HTTPServer] = None

    def run(self):
        redirect_url = f"http://localhost:{self.port}"
        try:
            login_data = msa.get_secure_login_data(self.client_id, redirect_url)
            
            if isinstance(login_data, tuple):
                login_url, code_verifier = login_data[0], login_data[1]
            else:
                login_url = login_data["url"]
                code_verifier = login_data["code_verifier"]

            QDesktopServices.openUrl(QUrl(login_url))

            auth_code = self._run_local_auth_server(code_verifier, redirect_url)

            if not auth_code:
                self.login_failed.emit("Quá thời gian đăng nhập hoặc phiên bị hủy.")
                return

            account_info = msa.complete_login(
                self.client_id,
                None,
                redirect_url,
                auth_code,
                code_verifier,
            )
            self.login_finished.emit(account_info)

        except Exception as e:
            self.login_failed.emit(str(e))

    def _run_local_auth_server(
        self, code_verifier: str, redirect_url: str
    ) -> Optional[str]:
        auth_code = {"value": None}
        worker_self = self

        class AuthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = parse_qs(urlparse(self.path).query)
                if "code" in query:
                    auth_code["value"] = query["code"][0]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    html = """
                    <html>
                    <body style="font-family: Arial, sans-serif; text-align: center; margin-top: 50px;">
                        <h1 style="color: #2e7d32;">Đăng nhập thành công!</h1>
                        <p>Bạn có thể đóng tab này và quay lại <b>PhantomX Launcher</b> để chơi game.</p>
                    </body>
                    </html>
                    """
                    self.wfile.write(html.encode("utf-8"))
                    QThread.currentThread().msleep(100)
                    if worker_self.httpd:
                        worker_self.httpd.shutdown()
                else:
                    self.send_response(400)
                    self.end_headers()

            def log_message(self, format, *args):
                pass

        try:
            self.httpd = HTTPServer(("localhost", self.port), AuthHandler)
            self.httpd.timeout = 0.5
            start_time = time.time()

            while auth_code["value"] is None and (time.time() - start_time) < self.timeout:
                if self.isInterruptionRequested():
                    break
                self.httpd.handle_request()

            return auth_code["value"]

        except Exception as e:
            print(f"Lỗi khởi chạy server local: {e}")
            return None
        finally:
            if self.httpd:
                self.httpd.server_close()


class InstallWorker(QThread):
    done = pyqtSignal(bool, str)
    log = pyqtSignal(str)
    prog = pyqtSignal(int, int, str)

    def __init__(self, mgr: MinecraftManager, instance: Instance):
        super().__init__()
        self.mgr = mgr
        self.instance = instance

    def run(self):
        inst = self.instance
        gdir = inst.game_dir
        Path(gdir).mkdir(parents=True, exist_ok=True)

        vanilla_ok = self.mgr.is_version_installed(inst.version_id, gdir)
        if vanilla_ok:
            self.log.emit(f"✅ Vanilla {inst.version_id} đã được cài đặt — bỏ qua tải xuống (không tải lại)")
            ok = True
        else:
            ok = self.mgr.install_vanilla(
                inst.version_id,
                gdir,
                cb_progress=lambda c, t, s: self.prog.emit(c, t, s),
                cb_log=self.log.emit,
            )
            if not ok:
                self.done.emit(False, inst.name)
                return

        jp = (
            self.mgr.find_java_for_version(inst.version_id)
            or self.mgr.find_java()
            or "java"
        )
        if jp and jp.lower().endswith("javaw.exe"):
            jp = jp[:-9] + "java.exe"

        if inst.loader == "fabric":
            ok = self.mgr.install_fabric(
                inst.version_id, inst.loader_version, gdir, java_path=jp, cb_log=self.log.emit
            )
        elif inst.loader == "forge":
            ok = self.mgr.install_forge(
                inst.version_id, inst.loader_version, gdir, jp, cb_log=self.log.emit
            )
        elif inst.loader == "quilt":
            ok = self.mgr.install_quilt(
                inst.version_id, inst.loader_version, gdir, java_path=jp, cb_log=self.log.emit
            )
        elif inst.loader == "neoforge":
            jp = (
                self.mgr.find_java_for_version(inst.version_id)
                or self.mgr.find_java()
                or "java"
            )
            ok = self.mgr.install_neoforge(
                inst.version_id,
                inst.loader_version,
                gdir,
                java_path=jp,
                cb_log=self.log.emit,
            )

        if ok:
            inst.save()
            self.log.emit(f"✅ Phiên bản '{inst.name}' sẵn sàng!")
            self.done.emit(True, inst.name)
        else:
            self.done.emit(False, inst.name)


class LaunchWorker(QThread):
    done = pyqtSignal(int)
    log = pyqtSignal(str)

    def __init__(
        self,
        mgr: MinecraftManager,
        instance: Instance,
        username: str,
        max_ram: int,
        extra_jvm: str = "",
        java_path: str = "",
        uuid: str = "",
        token: str = "",
    ):
        super().__init__()
        self.mgr = mgr
        self.instance = instance
        self.username = username
        self.max_ram = max_ram
        self.extra_jvm = extra_jvm
        self.java_path = java_path
        self.uuid = uuid
        self.token = token
        self._process: Optional[subprocess.Popen] = None
        self._stop_flag = threading.Event()

    def run(self):
        inst = self.instance
        try:
            self.mgr.pre_launch_cleanup(inst.game_dir, cb_log=self.log.emit)

            launch_vid = self._resolve_version_id(inst)
            self.log.emit(f"🚀 Đang khởi chạy '{inst.name}' ({launch_vid}) với tên {self.username}…")

            cmd = self.mgr.build_command(
                launch_vid,
                self.username,
                inst.game_dir,
                self.max_ram,
                self.extra_jvm,
                self.java_path,
                uuid=self.uuid,
                token=self.token,
            )

            kwargs: dict = dict(
                cwd=inst.game_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            self._process = subprocess.Popen(cmd, **kwargs)
            logger.info(f"Game PID: {self._process.pid}")

            for line in iter(self._process.stdout.readline, ""):
                if self._stop_flag.is_set():
                    break
                line = line.rstrip()
                if line and any(
                    s in line
                    for s in ["[CHAT]", "INFO", "WARN", "ERROR", "Exception", "Caused by"]
                ):
                    self.log.emit(f"🎮 {line}")
                elif line:
                    logger.debug(f"MC: {line}")

            rc = self._process.wait()
            msg = "✅ Đã thoát bình thường" if rc == 0 else f"⚠️ Thoát với code {rc}"
            self.log.emit(msg)
            logger.info(f"Game exited: rc={rc}")
            self.done.emit(rc)

        except Exception as e:
            logger.exception(f"LaunchWorker error: {e}")
            self.log.emit(f"❌ Lỗi khởi chạy: {e}")
            self.done.emit(-1)

    def _resolve_version_id(self, inst: Instance) -> str:
        versions_dir = Path(inst.game_dir) / "versions"
        if not versions_dir.exists():
            return inst.version_id

        all_versions = [d.name for d in versions_dir.iterdir() if d.is_dir()]

        if inst.loader in ("fabric", "forge", "quilt", "neoforge"):
            keyword = inst.loader.lower()
            matches = [
                v
                for v in sorted(all_versions, reverse=True)
                if keyword in v.lower() and inst.version_id in v
            ]
            if matches:
                logger.debug(f"Resolved {inst.loader} version: {matches[0]}")
                return matches[0]

        return inst.version_id

    def terminate(self):
        self._stop_flag.set()
        proc = self._process
        if proc is None:
            return
        if proc.poll() is None:
            logger.info("Đang kết thúc tiến trình game…")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                logger.warning("Tiến trình trò chơi đã bị buộc dừng (SIGKILL)")


class ModSearchWorker(QThread):
    results_ready = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(
        self,
        mgr: MinecraftManager,
        query: str,
        mc_version: str = "",
        loader: str = "",
    ):
        super().__init__()
        self.mgr = mgr
        self.query = query
        self.mc_version = mc_version
        self.loader = loader

    def run(self):
        try:
            results = self.mgr.search_modrinth(
                self.query, self.mc_version, self.loader
            )
            self.results_ready.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class ModDownloadWorker(QThread):
    done = pyqtSignal(bool, str)
    log = pyqtSignal(str)
    prog = pyqtSignal(int, int, str)

    def __init__(
        self, mgr: MinecraftManager, url: str, filename: str, mods_dir: Path
    ):
        super().__init__()
        self.mgr = mgr
        self.url = url
        self.filename = filename
        self.mods_dir = mods_dir

    def run(self):
        ok = self.mgr.download_mod(
            self.url,
            self.filename,
            self.mods_dir,
            cb_progress=lambda c, t, s: self.prog.emit(c, t, s),
            cb_log=self.log.emit,
        )
        self.done.emit(ok, self.filename)


class JavaRuntimeWorker(QThread):
    progress = pyqtSignal(int, int, str)
    log = pyqtSignal(str)
    done = pyqtSignal(object)

    def __init__(self, mgr: MinecraftManager, runtime_name: str):
        super().__init__()
        self.mgr = mgr
        self.runtime_name = runtime_name

    def run(self):
        java_version = None
        name_to_ver = {
            "java-runtime-legacy": 8,
            "java-runtime-gamma": 17,
            "java-runtime-delta": 21,
            "java-runtime-epsilon": 25,
            "java-runtime-alpha": 8,
            "java-runtime-beta": 16,
        }
        if self.runtime_name in name_to_ver:
            java_version = name_to_ver[self.runtime_name]
        else:
            try:
                java_version = int(self.runtime_name)
            except (TypeError, ValueError):
                java_version = None

        if java_version is not None and java_version in self.mgr.OPENJDK_WINGET_PACKAGES:
            java_path = self.mgr.install_openjdk_winget(
                java_version,
                cb_log=self.log.emit,
            )
        else:
            java_path = self.mgr.install_java_runtime_mojang(
                java_version or 0,
                cb_log=self.log.emit,
                cb_progress=lambda c, t, s: self.progress.emit(c, t, s),
            )
        self.done.emit(java_path)


class DiscordPresence:
    def __init__(self, client_id: str = "1526783238406672475"):
        self.client_id = client_id
        self.client = None
        self._running = False
        self._start_time = int(time.time())

    def connect(self):
        try:
            from pypresence import Presence
            self.client = Presence(self.client_id)
            self.client.connect()
            self._running = True
            self._start_time = int(time.time())
            logger.info("Discord Rich Presence connected.")
        except Exception as e:
            logger.debug(f"Could not connect to Discord Rich Presence: {e}")
            self.client = None

    def update_presence(
        self,
        state: str,
        details: str,
        large_image: str = "icon",
        large_text: str = "PhantomX Launcher",
    ):
        if not self.client or not self._running:
            self.connect()
        if self.client and self._running:
            try:
                self.client.update(
                    state=state,
                    details=details,
                    large_image=large_image,
                    large_text=large_text,
                    start=self._start_time,
                )
            except Exception as e:
                logger.debug(f"Failed to update Discord presence: {e}")
                self._running = False
                self.client = None

    def clear(self):
        if self.client:
            try:
                self.client.clear()
            except Exception:
                pass

    def close(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
            self._running = False


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def run_powershell_elevated_silent(command: str, cb_log=None) -> tuple[int, str]:
    if platform.system() != "Windows":
        try:
            r = subprocess.run(
                ["sh", "-c", command],
                capture_output=True, text=True, timeout=900,
            )
            return r.returncode, (r.stdout or "") + (r.stderr or "")
        except Exception as e:
            logger.error(f"run_powershell_elevated_silent non-Windows failed: {e}")
            return -1, str(e)

    ps_cmd = (
        f"-NoProfile -NonInteractive -WindowStyle Hidden -Command "
        f"& {{ $ErrorActionPreference='Stop'; {command} | Out-String | Write-Output; "
        f"exit $LASTEXITCODE }}"
    )

    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            if cb_log:
                cb_log("⚡ Đã có quyền Administrator — Vui lòng chờ cài đặt...")
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", command],
                capture_output=True, text=True, timeout=900,
                encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            out = (r.stdout or "") + "\n" + (r.stderr or "")
            return r.returncode, out

        if cb_log:
            cb_log("🔐 Yêu cầu quyền Administrator… (Cửa sổ UAC sẽ xuất hiện) - Vui lòng cho phép UAC và chờ cài đặt")

        class _SHELLEXECUTEINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("fMask", ctypes.c_ulong),
                ("hwnd", ctypes.c_void_p),
                ("lpVerb", ctypes.c_wchar_p),
                ("lpFile", ctypes.c_wchar_p),
                ("lpParameters", ctypes.c_wchar_p),
                ("lpDirectory", ctypes.c_wchar_p),
                ("nShow", ctypes.c_int),
                ("hInstApp", ctypes.c_void_p),
                ("lpIDList", ctypes.c_void_p),
                ("lpClass", ctypes.c_wchar_p),
                ("hkeyClass", ctypes.c_void_p),
                ("dwHotKey", ctypes.c_ulong),
                ("hIcon", ctypes.c_void_p),
                ("hProcess", ctypes.c_void_p),
            ]

        SEE_MASK_NOCLOSEPROCESS = 0x00000040
        SW_HIDE = 0
        sei = _SHELLEXECUTEINFO()
        sei.cbSize = ctypes.sizeof(_SHELLEXECUTEINFO)
        sei.fMask = SEE_MASK_NOCLOSEPROCESS
        sei.lpVerb = "runas"
        sei.lpFile = "powershell.exe"
        sei.lpParameters = ps_cmd
        sei.nShow = SW_HIDE

        ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
        if not ok:
            err = ctypes.get_last_error()
            if err == 1223:
                if cb_log:
                    cb_log("❌ UAC bị hủy — không cài đặt được Java.")
                return 1223, "UAC cancelled by user"
            if cb_log:
                cb_log(f"❌ ShellExecuteExW thất bại (mã {err}).")
            return err, f"ShellExecuteExW failed with code {err}"

        hProc = sei.hProcess
        if hProc:
            try:
                ctypes.windll.kernel32.WaitForSingleObject(hProc, 0xFFFFFFFF)
                exit_code = ctypes.c_ulong(0)
                ctypes.windll.kernel32.GetExitCodeProcess(hProc, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(hProc)
                return int(exit_code.value), ""
            except Exception as e:
                logger.warning(f"Failed waiting for elevated process: {e}")
                return -1, str(e)

        return 0, ""

    except Exception as e:
        logger.error(f"run_powershell_elevated_silent failed: {e}")
        if cb_log:
            cb_log(f"❌ Lỗi khi chạy PowerShell nâng cao: {e}")
        return -1, str(e)


def open_path(path: str):
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        logger.error(f"open_path({path}): {e}")


def _safe_remove(path: Path, retries: int = 3, delay: float = 1.5):
    for attempt in range(retries):
        try:
            if path.exists():
                path.unlink()
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


def _safe_rmtree(path: Path, retries: int = 3, delay: float = 1.5):
    for attempt in range(retries):
        try:
            if path.exists():
                shutil.rmtree(path)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


def _safe_move(src: Path, dst: Path, retries: int = 3, delay: float = 1.5):
    for attempt in range(retries):
        try:
            shutil.move(str(src), str(dst))
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise
