"""
PhantomX Launcher - Core module
Contains: constants, data models, MinecraftManager, workers, Discord RPC
"""

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

# ── Third-party ────────────────────────────────────────────────────────────────
try:
    from PyQt6.QtCore import QThread, pyqtSignal, QObject, QUrl
    from PyQt6.QtGui import QDesktopServices
except ImportError:
    print("❌ PyQt6 missing. Run: pip install pyqt6")
    sys.exit(1)

try:
    import minecraft_launcher_lib as mcll
    import minecraft_launcher_lib.microsoft_account as msa
except ImportError:
    print("❌ minecraft-launcher-lib missing. Run: pip install minecraft-launcher-lib")
    sys.exit(1)

import uuid as _uuid_mod

try:
    import requests
except ImportError:
    print("❌ requests missing. Run: pip install requests")
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


# ── App constants ──────────────────────────────────────────────────────────────
APP_NAME    = "PhantomX"
APP_VERSION = "1.1.0"
APP_AUTHOR  = "PhantomXTeam"
KEYRING_SVC = "PhantomXLauncher"
WATERMARK   = "Phát triển bởi HoangLong ❤️ 🇻🇳"

if getattr(sys, "frozen", False):
    _APP_BASE = Path(sys.executable).parent
else:
    _APP_BASE = Path(__file__).parent

BASE_DIR    = Path(user_data_dir(APP_NAME, APP_AUTHOR))
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


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNALS
# ═══════════════════════════════════════════════════════════════════════════════

class Signals(QObject):
    log = pyqtSignal(str, str)
    progress = pyqtSignal(int, int, str)
    java_status = pyqtSignal(bool, str)
    versions_ok = pyqtSignal(list)
    dl_done = pyqtSignal(bool, str)
    game_exited = pyqtSignal(int)
    status_msg = pyqtSignal(str)


# ═══════════════════════════════════════════════════════════════════════════════
# CORE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class MinecraftManager:
    FABRIC_META = "https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
    FORGE_MAVEN = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
    QUILT_META = "https://meta.quiltmc.org/v3/versions/loader/{mc_version}"

    MODRINTH_SEARCH = "https://api.modrinth.com/v2/search"
    MODRINTH_VERSION = "https://api.modrinth.com/v2/project/{id}/version"
    CURSEFORGE_SEARCH = "https://api.curseforge.com/v1/mods/search"
    CURSEFORGE_KEY = "$2a$10$ikdeyDd1WBkPxFYhOxVAN.ZiJj6dPeAXte47fffCVxI6Ot6S3oEHm"

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

    # ── Java ──────────────────────────────────────────────────────────────────
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

        return candidates[0] if candidates else None

    def java_version(self, java_path: str) -> Optional[int]:
        try:
            r = subprocess.run(
                [java_path, "-version"],
                capture_output=True, text=True, timeout=5,
                encoding="utf-8", errors="replace",
            )
            out = (r.stderr + r.stdout).lower()
            import re
            for line in out.splitlines():
                if "version" in line:
                    m = re.search(r'"(\d+)[\._]', line)
                    if m:
                        v = int(m.group(1))
                        return 8 if v == 1 else v
        except Exception as e:
            logger.warning(f"java_version check failed: {e}")
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

    # ── Version list ──────────────────────────────────────────────────────────
    def get_versions(self, include_snapshots: bool = False) -> list:
        try:
            all_v = mcll.utils.get_version_list()
            keep_types = {"release"}
            if include_snapshots:
                keep_types.add("snapshot")
            return [v for v in all_v if v.get("type") in keep_types]
        except Exception as e:
            logger.error(f"get_versions failed: {e}")
            return []

    # ── Installation checks ───────────────────────────────────────────────────
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

    # ── Install / download ────────────────────────────────────────────────────
    def install_vanilla(
        self, version_id: str, game_dir: str, cb_progress=None, cb_log=None
    ) -> bool:
        try:
            if cb_log:
                cb_log(f"📦 Đang cài đặt Minecraft {version_id}…")

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

        except TypeError:
            try:
                if cb_log:
                    cb_log("📦 Thử cài đặt lại với legacy callback…")

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

                mcll.install.install_minecraft_version(
                    version_id, game_dir, callback=_cb_legacy
                )
                logger.info(f"Vanilla {version_id} đã được cài đặt (legacy cb) vào {game_dir}")
                return True
            except Exception as e2:
                logger.error(f"install_vanilla legacy fallback failed: {e2}")
                if cb_log:
                    cb_log(f"❌ Lỗi cài đặt: {e2}")
                return False

        except Exception as e:
            logger.error(f"install_vanilla failed: {e}")
            if cb_log:
                cb_log(f"❌ Lỗi cài đặt: {e}")
            return False

    def install_fabric(
        self, mc_version: str, loader_version: str, game_dir: str, cb_log=None
    ) -> bool:
        try:
            if cb_log:
                cb_log(f"🧵 Đang cài Fabric {loader_version or 'latest'} cho phiên bản {mc_version}…")
            lv = loader_version.strip() or None
            mcll.fabric.install_fabric(mc_version, game_dir, loader_version=lv)
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
            # Run Forge installer via Java CLI to avoid PermissionError in Program Files
            mcll.forge.install_forge_version(version_str, game_dir, java=java_path)
            logger.info(f"Forge đã được cài đặt: {version_str}")
            return True
        except PermissionError as pe:
            # Retry once after a short delay (antivirus file lock)
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
        self, mc_version: str, loader_version: str, game_dir: str, cb_log=None
    ) -> bool:
        try:
            if cb_log:
                cb_log(f"🪡 Đang cài đặt Quilt {loader_version or 'latest'} cho phiên bản {mc_version}…")
            lv = loader_version.strip() or None
            # Try direct quilt module first (newer mcll), fall back to mod_loader API
            try:
                mcll.quilt.install_quilt(mc_version, game_dir, loader_version=lv)
            except AttributeError:
                from minecraft_launcher_lib import mod_loader as _ml
                _loader = _ml.get_mod_loader("quilt")
                _loader.install(mc_version, game_dir, loader_version=lv)
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
            # Try direct neoforge module first, fall back to mod_loader API
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

    # ── Mod Marketplace: Modrinth ─────────────────────────────────────────────
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

    # ── Build launch command ──────────────────────────────────────────────────
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
        java = java_path or self.find_java() or "java"

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

    # ── Pre-launch optimisation ─────────────────────────────────────────────
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

    # ── Mod management helpers ────────────────────────────────────────────────
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
        """Return full 40-char SHA-1 hex digest."""
        h = hashlib.sha1()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()

    # ── Java Runtime (Mojang) ─────────────────────────────────────────────────
    def get_available_java_runtimes(self) -> list:
        try:
            return mcll.runtime.get_available_runtimes()
        except Exception as e:
            logger.error(f"get_available_java_runtimes failed: {e}")
            return []

    def install_java_runtime(
        self,
        runtime_name: str,
        game_dir: str = None,
        cb_log=None,
        cb_progress=None,
    ) -> Optional[str]:
        try:
            if not game_dir:
                game_dir = self.game_dir

            if cb_log:
                cb_log(f"☕ Đang tải môi trường chạy Java: {runtime_name}...")

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

            mcll.runtime.install_jvm_runtime(
                runtime_name,
                game_dir,
                callback={
                    "setStatus": set_status,
                    "setProgress": set_progress,
                    "setMax": set_max,
                },
            )

            java_path = self._find_installed_java_path(game_dir, runtime_name)
            if java_path and cb_log:
                cb_log(f"✅ Cài đặt thành công: {java_path}")
            return java_path

        except Exception as e:
            logger.error(f"install_java_runtime failed: {e}")
            if cb_log:
                cb_log(f"❌ Lỗi khi cài đặt môi trường chạy Java: {e}")
            return None

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


# ═══════════════════════════════════════════════════════════════════════════════
# WORKER THREADS
# ═══════════════════════════════════════════════════════════════════════════════

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
            
            # Nếu login_data trả về Tuple 2 hoặc 3 phần tử:
            if isinstance(login_data, tuple):
                login_url, code_verifier = login_data[0], login_data[1]
            else:
                # Dành cho trường hợp dùng bản cũ trả về dict
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

        if inst.loader == "fabric":
            ok = self.mgr.install_fabric(
                inst.version_id, inst.loader_version, gdir, cb_log=self.log.emit
            )
        elif inst.loader == "forge":
            jp = self.mgr.find_java() or "java"
            ok = self.mgr.install_forge(
                inst.version_id, inst.loader_version, gdir, jp, cb_log=self.log.emit
            )
        elif inst.loader == "quilt":
            ok = self.mgr.install_quilt(
                inst.version_id, inst.loader_version, gdir, cb_log=self.log.emit
            )
        elif inst.loader == "neoforge":
            jp = self.mgr.find_java() or "java"
            ok = self.mgr.install_neoforge(
                inst.version_id,
                inst.loader_version,
                gdir,
                java_path=jp,
                cb_log=self.log.emit,
            )
        # loader == "vanilla" → ok already True

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
        java_path = self.mgr.install_java_runtime(
            self.runtime_name,
            cb_log=self.log.emit,
            cb_progress=lambda c, t, s: self.progress.emit(c, t, s),
        )
        self.done.emit(java_path)


# ═══════════════════════════════════════════════════════════════════════════════
# DISCORD RICH PRESENCE
# ═══════════════════════════════════════════════════════════════════════════════

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
    """Remove a directory tree with retries on PermissionError."""
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
    """Move a file/dir with retries on PermissionError."""
    for attempt in range(retries):
        try:
            shutil.move(str(src), str(dst))
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise
