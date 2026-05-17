import os
import sys
import json
import shutil
import hashlib
import platform
import threading
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

if getattr(sys, "frozen", False):
    import multiprocessing
    multiprocessing.freeze_support()

# ── Third-party ────────────────────────────────────────────────────────────────
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton,
        QProgressBar, QTextEdit, QFileDialog, QMessageBox, QTabWidget,
        QListWidget, QListWidgetItem, QCheckBox, QGroupBox, QSplitter,
        QScrollArea, QFrame, QDialog, QDialogButtonBox, QInputDialog,
        QSizePolicy, QTreeWidget, QTreeWidgetItem, QMenu, QToolButton,
        QStatusBar, QSlider, QStackedWidget, QGridLayout
    )
    from PyQt6.QtCore import (
        Qt, QThread, pyqtSignal, QObject, QTimer, QSize, QMetaObject,
        Q_ARG, pyqtSlot, QUrl
    )
    from PyQt6.QtGui import (
        QColor, QFont, QIcon, QTextCursor, QPalette, QAction, QPixmap,
        QDesktopServices
    )
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
except ImportError:
    print("❌ PyQt6 missing. Run: pip install pyqt6")
    sys.exit(1)

try:
    import minecraft_launcher_lib as mcll
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
    def user_data_dir(a, b): return os.path.expanduser(f"~/.{a}")

# ── Logging setup ──────────────────────────────────────────────────────────────
from loguru import logger

APP_NAME    = "PhantomX"
APP_VERSION = "1.0.1"
APP_AUTHOR  = "PhantomXTeam"
KEYRING_SVC = "PhantomXLauncher"
WATERMARK   = "Maintained by HoangLong ❤️ 🇻🇳"

# ── Resolve base directory (works both frozen & normal) ────────────────────────
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

    def __init__(self, name: str, version_id: str, loader: str = "vanilla",
                 loader_version: str = "", game_dir: str = ""):
        self.name           = name
        self.version_id     = version_id
        self.loader         = loader          # vanilla | forge | fabric | quilt
        self.loader_version = loader_version
        self.game_dir       = game_dir or str(INST_DIR / name)
        self.mods: List[Dict] = []
        self.created_at     = datetime.now().isoformat()
        self.last_played    = ""
        self.play_count     = 0
        self.notes          = ""

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
# SIGNALS  (central bus)
# ═══════════════════════════════════════════════════════════════════════════════

class Signals(QObject):
    log         = pyqtSignal(str, str)        
    progress    = pyqtSignal(int, int, str)   
    java_status = pyqtSignal(bool, str)
    versions_ok = pyqtSignal(list)
    dl_done     = pyqtSignal(bool, str)
    game_exited = pyqtSignal(int)
    status_msg  = pyqtSignal(str)


# ═══════════════════════════════════════════════════════════════════════════════
# CORE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class MinecraftManager:
    FABRIC_META  = "https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
    FORGE_MAVEN  = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
    QUILT_META   = "https://meta.quiltmc.org/v3/versions/loader/{mc_version}"

    # ── Mod marketplace APIs ──────────────────────────────────────────────────
    MODRINTH_SEARCH  = "https://api.modrinth.com/v2/search"
    MODRINTH_VERSION = "https://api.modrinth.com/v2/project/{id}/version"
    CURSEFORGE_SEARCH = "https://api.curseforge.com/v1/mods/search"
    CURSEFORGE_KEY    = ""  

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
                encoding="utf-8", errors="replace"   
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

    def check_java(self) -> tuple[bool, str]:
        jp = self.find_java()
        if not jp:
            return False, "❌ Java not found — install JDK 17 or 21"
        v = self.java_version(jp)
        if v is None:
            return False, f"⚠️  Java found but version unknown ({jp})"
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
        jar     = ver_dir / f"{version_id}.jar"
        json_f  = ver_dir / f"{version_id}.json"
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
    def install_vanilla(self, version_id: str, game_dir: str,
                        cb_progress=None, cb_log=None) -> bool:
        try:
            if cb_log:
                cb_log(f"📦 Installing Minecraft {version_id}…")

            def _cb(current, maximum, label):
                try:
                    c = int(current or 0)
                    t = int(maximum or 0)
                    s = str(label or "Downloading…")
                    if cb_progress:
                        cb_progress(c, t, s)
                    if cb_log and s:
                        cb_log(f"  {s}")
                except Exception as inner:
                    logger.debug(f"Progress callback error: {inner}")

            mcll.install.install_minecraft_version(
                version_id, game_dir,
                callback={
                    "setStatus":   lambda s: _cb(0, 0, s),
                    "setProgress": lambda c: None,
                    "setMax":      lambda m: None,
                }
            )
            logger.info(f"Vanilla {version_id} installed to {game_dir}")
            return True

        except TypeError:
            try:
                if cb_log:
                    cb_log(f"📦 Retrying install with legacy callback…")

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
                logger.info(f"Vanilla {version_id} installed (legacy cb) to {game_dir}")
                return True
            except Exception as e2:
                logger.error(f"install_vanilla legacy fallback failed: {e2}")
                if cb_log:
                    cb_log(f"❌ Install error: {e2}")
                return False

        except Exception as e:
            logger.error(f"install_vanilla failed: {e}")
            if cb_log:
                cb_log(f"❌ Install error: {e}")
            return False

    def install_fabric(self, mc_version: str, loader_version: str,
                       game_dir: str, cb_log=None) -> bool:
        try:
            if cb_log:
                cb_log(f"🧵 Installing Fabric {loader_version or 'latest'} for {mc_version}…")
            lv = loader_version.strip() or None
            mcll.fabric.install_fabric(mc_version, game_dir, loader_version=lv)
            logger.info(f"Fabric installed: mc={mc_version} loader={lv}")
            return True
        except Exception as e:
            logger.error(f"install_fabric: {e}")
            if cb_log:
                cb_log(f"❌ Fabric error: {e}")
            return False

    def install_forge(self, mc_version: str, forge_version: str,
                      game_dir: str, java_path: str, cb_log=None) -> bool:
        try:
            if cb_log:
                cb_log(f"⚙️  Installing Forge {forge_version} for {mc_version}…")
            version_str = f"{mc_version}-{forge_version}" if forge_version else mc_version
            mcll.forge.install_forge_version(
                version_str, game_dir, java=java_path
            )
            logger.info(f"Forge installed: {version_str}")
            return True
        except Exception as e:
            logger.error(f"install_forge: {e}")
            if cb_log:
                cb_log(f"❌ Forge error: {e}")
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

    # ── Mod Marketplace: Modrinth ─────────────────────────────────────────────
    def search_modrinth(self, query: str, mc_version: str = "",
                        loader: str = "", limit: int = 20) -> List[Dict]:
        try:
            facets = [['project_type:mod']]
            if mc_version:
                facets.append([f'versions:{mc_version}'])
            if loader and loader != "vanilla":
                facets.append([f'categories:{loader}'])

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

    def get_modrinth_versions(self, project_id: str, mc_version: str = "",
                              loader: str = "") -> List[Dict]:
        """Get download versions for a Modrinth project."""
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

    def download_mod(self, url: str, filename: str, mods_dir: Path,
                     cb_progress=None, cb_log=None) -> bool:
        try:
            mods_dir.mkdir(parents=True, exist_ok=True)
            dest = mods_dir / filename
            if cb_log:
                cb_log(f"⬇️  Downloading {filename}…")

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
                            cb_progress(downloaded, total, f"Downloading {filename}")

            if cb_log:
                cb_log(f"✅ {filename} downloaded ({downloaded // 1024} KB)")
            logger.info(f"Mod downloaded: {dest}")
            return True
        except Exception as e:
            logger.error(f"download_mod: {e}")
            if cb_log:
                cb_log(f"❌ Download error: {e}")
            return False

    # ── Build launch command ──────────────────────────────────────────────────
    def build_command(self, version_id: str, username: str,
                      game_dir: str, max_ram: int,
                      extra_jvm: str = "",
                      java_path: str = "") -> list:
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

        try:
            uuid = str(_uuid_mod.uuid3(_uuid_mod.NAMESPACE_DNS, username))
        except Exception:
            uuid = str(_uuid_mod.uuid4())

        options = {
            "username":        username,
            "uuid":            uuid,
            "token":           "",
            "jvmArguments":    jvm_args,
            "launcherName":    APP_NAME,
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

    # ── Pre-launch optimisation ───────────────────────────────────────────────
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
                key=lambda f: f.stat().st_mtime, reverse=True
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
                mods.append({
                    "filename": f.name,
                    "path":     str(f),
                    "enabled":  enabled,
                    "size_kb":  round(f.stat().st_size / 1024, 1),
                    "sha1":     self._sha1(f),
                })
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


# ═══════════════════════════════════════════════════════════════════════════════
# WORKER THREADS
# ═══════════════════════════════════════════════════════════════════════════════

class InstallWorker(QThread):
    done = pyqtSignal(bool, str)
    log  = pyqtSignal(str)
    prog = pyqtSignal(int, int, str)

    def __init__(self, mgr: MinecraftManager, instance: Instance):
        super().__init__()
        self.mgr      = mgr
        self.instance = instance

    def run(self):
        inst = self.instance
        gdir = inst.game_dir
        Path(gdir).mkdir(parents=True, exist_ok=True)

        vanilla_ok = self.mgr.is_version_installed(inst.version_id, gdir)
        if vanilla_ok:
            self.log.emit(f"✅ Vanilla {inst.version_id} already installed — skipping download")
        else:
            ok = self.mgr.install_vanilla(
                inst.version_id, gdir,
                cb_progress=lambda c, t, s: self.prog.emit(c, t, s),
                cb_log=self.log.emit,
            )
            if not ok:
                self.done.emit(False, inst.name)
                return

        if inst.loader == "fabric":
            ok = self.mgr.install_fabric(
                inst.version_id, inst.loader_version, gdir,
                cb_log=self.log.emit,
            )
            if not ok:
                self.done.emit(False, inst.name)
                return

        elif inst.loader == "forge":
            jp = self.mgr.find_java() or "java"
            ok = self.mgr.install_forge(
                inst.version_id, inst.loader_version, gdir, jp,
                cb_log=self.log.emit,
            )
            if not ok:
                self.done.emit(False, inst.name)
                return

        inst.save()
        self.log.emit(f"✅ Instance '{inst.name}' ready!")
        self.done.emit(True, inst.name)


class LaunchWorker(QThread):
    done = pyqtSignal(int)
    log  = pyqtSignal(str)

    def __init__(self, mgr: MinecraftManager, instance: Instance,
                 username: str, max_ram: int,
                 extra_jvm: str = "", java_path: str = ""):
        super().__init__()
        self.mgr       = mgr
        self.instance  = instance
        self.username  = username
        self.max_ram   = max_ram
        self.extra_jvm = extra_jvm
        self.java_path = java_path
        self._process: Optional[subprocess.Popen] = None
        self._stop_flag = threading.Event()

    def run(self):
        inst = self.instance
        try:
            self.mgr.pre_launch_cleanup(inst.game_dir, cb_log=self.log.emit)

            launch_vid = self._resolve_version_id(inst)
            self.log.emit(f"🚀 Launching '{inst.name}' ({launch_vid}) as {self.username}…")

            cmd = self.mgr.build_command(
                launch_vid, self.username, inst.game_dir,
                self.max_ram, self.extra_jvm, self.java_path
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
                    s in line for s in
                    ["[CHAT]", "INFO", "WARN", "ERROR", "Exception", "Caused by"]
                ):
                    self.log.emit(f"🎮 {line}")
                elif line:
                    logger.debug(f"MC: {line}")

            rc = self._process.wait()
            msg = "✅ Closed normally" if rc == 0 else f"⚠️ Exit code {rc}"
            self.log.emit(msg)
            logger.info(f"Game exited: rc={rc}")
            self.done.emit(rc)

        except Exception as e:
            logger.exception(f"LaunchWorker error: {e}")
            self.log.emit(f"❌ Launch error: {e}")
            self.done.emit(-1)

    def _resolve_version_id(self, inst: Instance) -> str:
        versions_dir = Path(inst.game_dir) / "versions"
        if not versions_dir.exists():
            return inst.version_id

        all_versions = [d.name for d in versions_dir.iterdir() if d.is_dir()]

        if inst.loader in ("fabric", "forge", "quilt"):
            keyword = inst.loader.lower()
            matches = [
                v for v in sorted(all_versions, reverse=True)
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
            logger.info("Terminating game process…")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                logger.warning("Game process killed (SIGKILL)")


class ModSearchWorker(QThread):
    results_ready = pyqtSignal(list)
    error         = pyqtSignal(str)

    def __init__(self, mgr: MinecraftManager, query: str,
                 mc_version: str = "", loader: str = ""):
        super().__init__()
        self.mgr        = mgr
        self.query      = query
        self.mc_version = mc_version
        self.loader     = loader

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
    log  = pyqtSignal(str)
    prog = pyqtSignal(int, int, str)

    def __init__(self, mgr: MinecraftManager, url: str,
                 filename: str, mods_dir: Path):
        super().__init__()
        self.mgr      = mgr
        self.url      = url
        self.filename = filename
        self.mods_dir = mods_dir

    def run(self):
        ok = self.mgr.download_mod(
            self.url, self.filename, self.mods_dir,
            cb_progress=lambda c, t, s: self.prog.emit(c, t, s),
            cb_log=self.log.emit,
        )
        self.done.emit(ok, self.filename)


# ═══════════════════════════════════════════════════════════════════════════════
# MUSIC PLAYER WIDGET
# ═══════════════════════════════════════════════════════════════════════════════

class MusicPlayerWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player      = QMediaPlayer()
        self._audio_out   = QAudioOutput()
        self._player.setAudioOutput(self._audio_out)
        self._player.mediaStatusChanged.connect(self._on_status_changed)
        self._player.playbackStateChanged.connect(self._on_playback_changed)
        self._looping = True
        self._build_ui()
        self._load_music()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        icon_lbl = QLabel("🎵")
        icon_lbl.setFixedWidth(20)
        layout.addWidget(icon_lbl)

        self.track_lbl = QLabel("No music")
        self.track_lbl.setObjectName("subtitle")
        self.track_lbl.setMaximumWidth(160)
        layout.addWidget(self.track_lbl)

        self.play_btn = QPushButton("▶️")
        self.play_btn.setFixedSize(28, 28)
        self.play_btn.setToolTip("Play / Pause")
        self.play_btn.clicked.connect(self._toggle_play)
        layout.addWidget(self.play_btn)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(40)
        self.vol_slider.setFixedWidth(80)
        self.vol_slider.setToolTip("Volume")
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        layout.addWidget(self.vol_slider)

        self.mute_btn = QPushButton("🔇")
        self.mute_btn.setFixedSize(28, 28)
        self.mute_btn.setCheckable(True)
        self.mute_btn.clicked.connect(self._toggle_mute)
        layout.addWidget(self.mute_btn)

        self._audio_out.setVolume(0.40)

    def _load_music(self):
        if MUSIC_FILE.exists():
            url = QUrl.fromLocalFile(str(MUSIC_FILE.resolve()))
            self._player.setSource(url)
            self.track_lbl.setText(MUSIC_FILE.stem)
            logger.info(f"Music loaded: {MUSIC_FILE}")

        else:
            self.track_lbl.setText("theme/music.mp3 missing")
            self.play_btn.setEnabled(False)
            logger.info(f"Music file not found: {MUSIC_FILE}")

    def _toggle_play(self):
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_playback_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("🔇")
        else:
            self.play_btn.setText("▶️")

    def _on_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self._player.play()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia and self._looping:
            self._player.setPosition(0)
            self._player.play()

    def _on_volume_changed(self, value: int):
        vol = value / 100.0
        self._audio_out.setVolume(vol)
        if value == 0:
            self.mute_btn.setChecked(True)
            self.mute_btn.setText("🔇")
        else:
            if not self.mute_btn.isChecked():
                self.mute_btn.setText("🔊")

    def _toggle_mute(self, checked: bool):
        self._audio_out.setMuted(checked)
        self.mute_btn.setText("🔇" if checked else "🔊")

    def save_state(self) -> dict:
        return {
            "music_volume": self.vol_slider.value(),
            "music_muted":  self.mute_btn.isChecked(),
        }

    def load_state(self, cfg: dict):
        vol   = int(cfg.get("music_volume", 40))
        muted = bool(cfg.get("music_muted", False))
        self.vol_slider.setValue(vol)
        self.mute_btn.setChecked(muted)
        self._audio_out.setMuted(muted)
        self.mute_btn.setText("🔇" if muted else "🔊")
        # If muted on startup, the auto-play will still start but be silent.
        # Volume is already applied before play() fires via _on_status_changed.


# ═══════════════════════════════════════════════════════════════════════════════
# STYLE
# ═══════════════════════════════════════════════════════════════════════════════

DARK_QSS = """
QMainWindow, QWidget { background: #1e1e2e; color: #cdd6f4; font-family: 'Segoe UI', Arial; font-size: 13px; }
QTabWidget::pane { border: 1px solid #313244; background: #1e1e2e; }
QTabBar::tab { background: #181825; color: #a6adc8; padding: 8px 18px; border: 1px solid #313244; border-bottom: none; border-radius: 4px 4px 0 0; }
QTabBar::tab:selected { background: #313244; color: #cdd6f4; }
QTabBar::tab:hover { background: #2a2a3e; }
QPushButton { background: #89b4fa; color: #1e1e2e; border: none; border-radius: 6px; padding: 7px 16px; font-weight: bold; }
QPushButton:hover { background: #74c7ec; }
QPushButton:pressed { background: #89dceb; }
QPushButton:disabled { background: #45475a; color: #6c7086; }
QPushButton#danger { background: #f38ba8; }
QPushButton#danger:hover { background: #eba0ac; }
QPushButton#danger:disabled { background: #45475a; color: #6c7086; }
QPushButton#success { background: #a6e3a1; }
QPushButton#success:hover { background: #94e2d5; }
QPushButton#success:disabled { background: #45475a; color: #6c7086; }
QPushButton#market { background: #cba6f7; color: #1e1e2e; }
QPushButton#market:hover { background: #b4befe; }
QLineEdit, QComboBox, QSpinBox { background: #313244; border: 1px solid #45475a; border-radius: 5px; padding: 5px 8px; color: #cdd6f4; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #89b4fa; }
QComboBox::drop-down { border: none; }
QComboBox::down-arrow { image: none; width: 12px; }
QTextEdit { background: #11111b; border: 1px solid #313244; border-radius: 5px; color: #cdd6f4; font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; }
QProgressBar { background: #313244; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }
QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #89b4fa, stop:1 #cba6f7); border-radius: 4px; }
QListWidget { background: #181825; border: 1px solid #313244; border-radius: 5px; color: #cdd6f4; }
QListWidget::item:selected { background: #313244; color: #89b4fa; }
QListWidget::item:hover { background: #2a2a3e; }
QGroupBox { border: 1px solid #313244; border-radius: 6px; margin-top: 10px; padding-top: 6px; color: #89b4fa; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QScrollBar:vertical { background: #181825; width: 8px; }
QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; min-height: 20px; }
QLabel#header { font-size: 20px; font-weight: bold; color: #89b4fa; }
QLabel#subtitle { color: #a6adc8; font-size: 11px; }
QLabel#watermark { color: #585b70; font-size: 10px; }
QStatusBar { background: #181825; color: #6c7086; border-top: 1px solid #313244; }
QCheckBox { color: #cdd6f4; spacing: 6px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 2px solid #45475a; border-radius: 3px; background: #313244; }
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
QSlider::groove:horizontal { background: #313244; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #89b4fa; width: 12px; height: 12px; border-radius: 6px; margin: -4px 0; }
QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 2px; }
"""

LOG_COLORS = {
    "INFO":    "#cdd6f4",
    "SUCCESS": "#a6e3a1",
    "WARN":    "#f9e2af",
    "ERROR":   "#f38ba8",
    "DEBUG":   "#6c7086",
    "GAME":    "#89dceb",
}


# ═══════════════════════════════════════════════════════════════════════════════
# UI TABS
# ═══════════════════════════════════════════════════════════════════════════════

class InstanceTab(QWidget):
    request_install = pyqtSignal(object)
    request_launch  = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.instances: Dict[str, Instance] = {}
        self._build_ui()
        self.load_instances()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        h = QHBoxLayout()
        lbl = QLabel("Instances")
        lbl.setObjectName("header")
        h.addWidget(lbl)
        h.addStretch()
        add_btn = QPushButton("➕ New Instance")
        add_btn.clicked.connect(self.create_instance_dialog)
        h.addWidget(add_btn)
        del_btn = QPushButton("🗑 Delete")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self.delete_selected)
        h.addWidget(del_btn)
        layout.addLayout(h)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(32, 32))
        self.list_widget.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.list_widget)

        row = QHBoxLayout()
        inst_btn = QPushButton("📥 Install")
        inst_btn.setObjectName("success")
        inst_btn.clicked.connect(self._install_selected)
        row.addWidget(inst_btn)

        launch_btn = QPushButton("🎮 Launch")
        launch_btn.clicked.connect(self._launch_selected)
        row.addWidget(launch_btn)

        open_btn = QPushButton("📂 Open Folder")
        open_btn.clicked.connect(self._open_folder)
        row.addWidget(open_btn)
        layout.addLayout(row)

    def load_instances(self):
        self.instances.clear()
        self.list_widget.clear()
        if not INST_DIR.exists():
            return
        for d in sorted(INST_DIR.iterdir()):
            cfg = d / "instance.json"
            if cfg.exists():
                inst = Instance.load(cfg)
                if inst:
                    self.instances[inst.name] = inst
                    self._add_list_item(inst)

    def _add_list_item(self, inst: Instance):
        loader_icons = {"vanilla": "🟩", "fabric": "🧵", "forge": "⚙️", "quilt": "🪡"}
        icon = loader_icons.get(inst.loader, "📦")
        item = QListWidgetItem(f"{icon}  {inst.name}  —  {inst.version_id}  [{inst.loader}]")
        item.setData(Qt.ItemDataRole.UserRole, inst.name)
        self.list_widget.addItem(item)

    def _selected_instance(self) -> Optional[Instance]:
        items = self.list_widget.selectedItems()
        if not items:
            return None
        name = items[0].data(Qt.ItemDataRole.UserRole)
        return self.instances.get(name)

    def _install_selected(self):
        inst = self._selected_instance()
        if inst:
            self.request_install.emit(inst)

    def _launch_selected(self):
        inst = self._selected_instance()
        if inst:
            self.request_launch.emit(inst)

    def _on_double_click(self, _):
        self._launch_selected()

    def _open_folder(self):
        inst = self._selected_instance()
        if not inst:
            return
        path = inst.game_dir
        Path(path).mkdir(parents=True, exist_ok=True)
        _open_path(path)

    def delete_selected(self):
        inst = self._selected_instance()
        if not inst:
            return
        reply = QMessageBox.question(
            self, "Delete Instance",
            f"Delete '{inst.name}'?\nThis removes ALL files in:\n{inst.game_dir}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                shutil.rmtree(inst.game_dir, ignore_errors=True)
            except Exception as e:
                logger.error(f"Delete instance error: {e}")
            self.instances.pop(inst.name, None)
            self.load_instances()

    def create_instance_dialog(self):
        dlg = NewInstanceDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            inst = dlg.get_instance()
            if inst.name in self.instances:
                QMessageBox.warning(self, "Duplicate", f"Instance '{inst.name}' already exists.")
                return
            self.instances[inst.name] = inst
            self._add_list_item(inst)
            inst.save()

    def get_instance(self, name: str) -> Optional[Instance]:
        return self.instances.get(name)


class NewInstanceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Instance")
        self.setMinimumWidth(420)
        self.mgr = MinecraftManager()
        self._fetcher = None 
        self._build_ui()
        self._load_versions()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QGroupBox("Instance Settings")
        fl = QVBoxLayout(form)

        row = QHBoxLayout()
        row.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Vanilla 1.20")
        row.addWidget(self.name_edit)
        fl.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("MC Version:"))
        self.ver_combo = QComboBox()
        self.ver_combo.setEditable(True)
        self.ver_combo.currentTextChanged.connect(self._on_version_changed)
        row2.addWidget(self.ver_combo)
        fl.addLayout(row2)

        self.snap_cb = QCheckBox("Show snapshots")
        self.snap_cb.stateChanged.connect(self._load_versions)
        fl.addWidget(self.snap_cb)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Loader:"))
        self.loader_combo = QComboBox()
        self.loader_combo.addItems(["vanilla", "fabric", "forge"])
        self.loader_combo.currentTextChanged.connect(self._on_loader_changed)
        row3.addWidget(self.loader_combo)
        fl.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Loader Version:"))
        self.lver_combo = QComboBox()
        self.lver_combo.setEditable(True)
        self.lver_combo.setPlaceholderText("latest")
        row4.addWidget(self.lver_combo)
        fl.addLayout(row4)

        layout.addWidget(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_versions(self):
        incl_snap = self.snap_cb.isChecked()
        versions = self.mgr.get_versions(include_snapshots=incl_snap)
        self.ver_combo.clear()
        self.ver_combo.addItems([v["id"] for v in versions])

    def _on_version_changed(self, mc_ver: str):
        loader = self.loader_combo.currentText()
        if loader != "vanilla":
            self._refresh_loader_versions(loader, mc_ver)

    def _on_loader_changed(self, loader: str):
        self.lver_combo.clear()
        if loader == "vanilla":
            return
        mc_ver = self.ver_combo.currentText()
        self._refresh_loader_versions(loader, mc_ver)

    def _refresh_loader_versions(self, loader: str, mc_ver: str):
        # Stop any previous fetcher before starting a new one
        if self._fetcher and self._fetcher.isRunning():
            self._fetcher.quit()
            self._fetcher.wait(500)

        self.lver_combo.clear()
        self.lver_combo.setEnabled(False)
        self.lver_combo.setPlaceholderText("Loading…")

        mgr = self.mgr

        class _Fetcher(QThread):
            result = pyqtSignal(list)

            def __init__(self, loader, mc_ver):
                super().__init__()
                self._loader = loader
                self._mc_ver = mc_ver

            def run(self):
                if self._loader == "fabric":
                    versions = mgr.get_fabric_loaders(self._mc_ver)
                elif self._loader == "forge":
                    versions = mgr.get_forge_versions(self._mc_ver)
                else:
                    versions = []
                self.result.emit(versions[:20])

        self._fetcher = _Fetcher(loader, mc_ver)
        self._fetcher.result.connect(self._on_loader_versions_fetched)
        self._fetcher.start()

    @pyqtSlot(list)
    def _on_loader_versions_fetched(self, versions: list):
        self.lver_combo.clear()
        self.lver_combo.setEnabled(True)
        self.lver_combo.setPlaceholderText("latest")
        if versions:
            self.lver_combo.addItems(versions)

    def _validate(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Required", "Instance name is required.")
            return
        if not self.ver_combo.currentText().strip():
            QMessageBox.warning(self, "Required", "Select a Minecraft version.")
            return
        self.accept()

    def get_instance(self) -> Instance:
        return Instance(
            name=self.name_edit.text().strip(),
            version_id=self.ver_combo.currentText().strip(),
            loader=self.loader_combo.currentText(),
            loader_version=self.lver_combo.currentText().strip(),
        )


class ModTab(QWidget):

    def __init__(self, mgr: MinecraftManager, parent=None):
        super().__init__(parent)
        self.mgr = mgr
        self.current_instance: Optional[Instance] = None
        self._mods: List[Dict] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Instance:"))
        self.inst_label = QLabel("(none selected)")
        self.inst_label.setObjectName("subtitle")
        row.addWidget(self.inst_label)
        row.addStretch()
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh)
        row.addWidget(refresh_btn)
        add_mod_btn = QPushButton("➕ Add Mod (.jar)")
        add_mod_btn.clicked.connect(self.add_mod)
        row.addWidget(add_mod_btn)
        layout.addLayout(row)

        self.mod_list = QListWidget()
        layout.addWidget(self.mod_list)

        btn_row = QHBoxLayout()
        toggle_btn = QPushButton("⏯ Enable/Disable")
        toggle_btn.clicked.connect(self.toggle_selected)
        btn_row.addWidget(toggle_btn)

        del_btn = QPushButton("🗑 Remove")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self.remove_selected)
        btn_row.addWidget(del_btn)

        open_dir_btn = QPushButton("📂 Mods Folder")
        open_dir_btn.clicked.connect(self.open_mods_folder)
        btn_row.addWidget(open_dir_btn)
        layout.addLayout(btn_row)

        self.conflict_label = QLabel("")
        self.conflict_label.setStyleSheet("color: #f38ba8;")
        layout.addWidget(self.conflict_label)

    def set_instance(self, inst: Instance):
        self.current_instance = inst
        self.inst_label.setText(f"{inst.name}  [{inst.loader}  {inst.version_id}]")
        self.refresh()

    def refresh(self):
        self.mod_list.clear()
        self.conflict_label.setText("")
        if not self.current_instance:
            return
        self._mods = self.mgr.scan_mods(self.current_instance.mods_dir)
        for m in self._mods:
            status = "✅" if m["enabled"] else "⛔"
            item = QListWidgetItem(
                f"{status}  {m['filename']}  ({m['size_kb']} KB)  #{m['sha1']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, m)
            if not m["enabled"]:
                item.setForeground(QColor("#6c7086"))
            self.mod_list.addItem(item)

        base_names = [
            m["filename"].replace(".disabled", "").lower()
            for m in self._mods
        ]
        dupes = sorted({n for n in base_names if base_names.count(n) > 1})
        if dupes:
            self.conflict_label.setText(f"⚠️ Possible conflict: {', '.join(dupes)}")

    def _selected_mod(self) -> Optional[Dict]:
        items = self.mod_list.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def toggle_selected(self):
        mod = self._selected_mod()
        if mod:
            self.mgr.toggle_mod(mod["path"])
            self.refresh()

    def remove_selected(self):
        mod = self._selected_mod()
        if not mod:
            return
        reply = QMessageBox.question(
            self, "Remove Mod", f"Delete {mod['filename']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.mgr.delete_mod(mod["path"])
            self.refresh()

    def add_mod(self):
        if not self.current_instance:
            QMessageBox.warning(self, "No Instance", "Select an instance first.")
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Mod JARs", "", "Mod JARs (*.jar)"
        )
        if not files:
            return
        mods_dir = self.current_instance.mods_dir
        mods_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            dest = mods_dir / Path(f).name
            if dest.exists():
                reply = QMessageBox.question(
                    self, "Overwrite?",
                    f"{dest.name} already exists. Overwrite?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    continue
            shutil.copy2(f, dest)
            logger.info(f"Mod added: {dest}")
        self.refresh()

    def open_mods_folder(self):
        if not self.current_instance:
            return
        mods_dir = self.current_instance.mods_dir
        mods_dir.mkdir(parents=True, exist_ok=True)
        _open_path(str(mods_dir))


# ═══════════════════════════════════════════════════════════════════════════════
# MOD MARKETPLACE TAB  (Modrinth integration)
# ═══════════════════════════════════════════════════════════════════════════════

class MarketplaceTab(QWidget):

    install_signal = pyqtSignal(str)

    def __init__(self, mgr: MinecraftManager, inst_tab, parent=None):
        super().__init__(parent)
        self.mgr      = mgr
        self.inst_tab = inst_tab
        self._results: List[Dict] = []
        self._search_worker: Optional[ModSearchWorker] = None
        self._dl_worker: Optional[ModDownloadWorker] = None
        self._ver_fetcher = None           # keep reference to avoid GC
        self._current_mod: Optional[Dict] = None
        self._mod_versions: List[Dict] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        h = QHBoxLayout()
        lbl = QLabel("🛒 Mod Marketplace")
        lbl.setObjectName("header")
        h.addWidget(lbl)
        h.addStretch()
        modrinth_lbl = QLabel("Powered by Modrinth")
        modrinth_lbl.setObjectName("subtitle")
        h.addWidget(modrinth_lbl)
        layout.addLayout(h)

        search_grp = QGroupBox("Search")
        sg = QHBoxLayout(search_grp)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search mods, modpacks, resource packs…")
        self.search_edit.returnPressed.connect(self._do_search)
        sg.addWidget(self.search_edit)

        self.mc_ver_filter = QComboBox()
        self.mc_ver_filter.setEditable(True)
        self.mc_ver_filter.setPlaceholderText("MC Version (any)")
        self.mc_ver_filter.setMinimumWidth(120)
        for v in ["1.21.4", "1.21.1", "1.20.4", "1.20.1", "1.19.4",
                  "1.19.2", "1.18.2", "1.16.5"]:
            self.mc_ver_filter.addItem(v)
        self.mc_ver_filter.setCurrentIndex(-1)
        sg.addWidget(self.mc_ver_filter)

        self.loader_filter = QComboBox()
        self.loader_filter.addItems(["any loader", "fabric", "forge", "quilt", "neoforge"])
        sg.addWidget(self.loader_filter)

        self.search_btn = QPushButton("🔍 Search")
        self.search_btn.setObjectName("market")
        self.search_btn.clicked.connect(self._do_search)
        sg.addWidget(self.search_btn)

        layout.addWidget(search_grp)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.result_list = QListWidget()
        self.result_list.currentItemChanged.connect(self._on_result_selected)
        splitter.addWidget(self.result_list)

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)

        self.detail_name = QLabel("Select a mod to see details")
        self.detail_name.setObjectName("header")
        self.detail_name.setWordWrap(True)
        detail_layout.addWidget(self.detail_name)

        self.detail_desc = QTextEdit()
        self.detail_desc.setReadOnly(True)
        self.detail_desc.setMaximumHeight(160)
        detail_layout.addWidget(self.detail_desc)

        info_row = QHBoxLayout()
        self.detail_author = QLabel("")
        self.detail_author.setObjectName("subtitle")
        info_row.addWidget(self.detail_author)
        info_row.addStretch()
        self.detail_dl_count = QLabel("")
        self.detail_dl_count.setObjectName("subtitle")
        info_row.addWidget(self.detail_dl_count)
        detail_layout.addLayout(info_row)

        ver_row = QHBoxLayout()
        ver_row.addWidget(QLabel("Version:"))
        self.ver_combo = QComboBox()
        self.ver_combo.setMinimumWidth(260)
        ver_row.addWidget(self.ver_combo)
        detail_layout.addLayout(ver_row)

        inst_row = QHBoxLayout()
        inst_row.addWidget(QLabel("Install to:"))
        self.inst_combo = QComboBox()
        inst_row.addWidget(self.inst_combo)
        detail_layout.addLayout(inst_row)

        self.dl_progress = QProgressBar()
        self.dl_progress.setVisible(False)
        detail_layout.addWidget(self.dl_progress)

        self.dl_status = QLabel("")
        self.dl_status.setObjectName("subtitle")
        detail_layout.addWidget(self.dl_status)

        btn_row = QHBoxLayout()
        self.download_btn = QPushButton("⬇️  Install Mod")
        self.download_btn.setObjectName("market")
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._download_selected)
        btn_row.addWidget(self.download_btn)

        self.open_web_btn = QPushButton("🌐 Open on Modrinth")
        self.open_web_btn.setEnabled(False)
        self.open_web_btn.clicked.connect(self._open_web)
        btn_row.addWidget(self.open_web_btn)
        detail_layout.addLayout(btn_row)

        detail_layout.addStretch()
        splitter.addWidget(detail_widget)
        splitter.setSizes([350, 450])
        layout.addWidget(splitter)

        self.search_progress = QProgressBar()
        self.search_progress.setRange(0, 0)
        self.search_progress.setVisible(False)
        self.search_progress.setMaximumHeight(6)
        layout.addWidget(self.search_progress)

    def refresh_instances(self):
        current = self.inst_combo.currentText()
        self.inst_combo.clear()
        for name in self.inst_tab.instances:
            self.inst_combo.addItem(name)
        idx = self.inst_combo.findText(current)
        if idx >= 0:
            self.inst_combo.setCurrentIndex(idx)

    def _do_search(self):
        query = self.search_edit.text().strip()
        if not query:
            return

        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.quit()
            self._search_worker.wait(500)

        mc_ver = self.mc_ver_filter.currentText().strip()
        loader = self.loader_filter.currentText()
        loader = "" if loader == "any loader" else loader

        self.result_list.clear()
        self._results.clear()
        self.search_progress.setVisible(True)
        self.search_btn.setEnabled(False)

        self._search_worker = ModSearchWorker(self.mgr, query, mc_ver, loader)
        self._search_worker.results_ready.connect(self._on_search_results)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.start()

    @pyqtSlot(list)
    def _on_search_results(self, results: list):
        self.search_progress.setVisible(False)
        self.search_btn.setEnabled(True)
        self._results = results

        if not results:
            self.result_list.addItem("No results found.")
            return

        for mod in results:
            title      = mod.get("title", "Unknown")
            author     = mod.get("author", "")
            downloads  = mod.get("downloads", 0)
            categories = ", ".join(mod.get("categories", [])[:3])
            dl_fmt     = f"{downloads:,}"
            item = QListWidgetItem(
                f"{'📦' if 'mod' in mod.get('project_type','') else '🧩'}  {title}"
                f"\n    by {author}  •  ⬇ {dl_fmt}  •  {categories}"
            )
            item.setData(Qt.ItemDataRole.UserRole, mod)
            self.result_list.addItem(item)

    @pyqtSlot(str)
    def _on_search_error(self, err: str):
        self.search_progress.setVisible(False)
        self.search_btn.setEnabled(True)
        self.result_list.addItem(f"Search error: {err}")

    def _on_result_selected(self, current: QListWidgetItem, _):
        if not current:
            return
        mod = current.data(Qt.ItemDataRole.UserRole)
        if not mod or not isinstance(mod, dict):
            return

        self.detail_name.setText(mod.get("title", "Unknown"))
        self.detail_desc.setPlainText(mod.get("description", ""))
        self.detail_author.setText(f"by {mod.get('author', 'Unknown')}")
        self.detail_dl_count.setText(f"⬇ {mod.get('downloads', 0):,} downloads")

        self._current_mod = mod
        self.download_btn.setEnabled(False)
        self.open_web_btn.setEnabled(True)
        self.ver_combo.clear()
        self.ver_combo.addItem("Loading versions…")

        project_id = mod.get("project_id", mod.get("slug", ""))
        mc_ver = self.mc_ver_filter.currentText().strip()
        loader = self.loader_filter.currentText()
        loader = "" if loader == "any loader" else loader

        # Stop any previous fetcher
        if self._ver_fetcher and self._ver_fetcher.isRunning():
            self._ver_fetcher.quit()
            self._ver_fetcher.wait(500)

        class _VerFetcher(QThread):
            done = pyqtSignal(list)
            def __init__(self, mgr, pid, mc, ldr):
                super().__init__()
                self._mgr, self._pid, self._mc, self._ldr = mgr, pid, mc, ldr
            def run(self):
                self.done.emit(self._mgr.get_modrinth_versions(
                    self._pid, self._mc, self._ldr))

        self._ver_fetcher = _VerFetcher(self.mgr, project_id, mc_ver, loader)
        self._ver_fetcher.done.connect(self._on_versions_fetched)
        self._ver_fetcher.start()

    @pyqtSlot(list)
    def _on_versions_fetched(self, versions: list):
        self.ver_combo.clear()
        self._mod_versions = versions
        if not versions:
            self.ver_combo.addItem("No compatible versions")
            self.download_btn.setEnabled(False)
            return
        for v in versions[:15]:
            mc_vers = ", ".join(v.get("game_versions", [])[-2:])
            loaders = ", ".join(v.get("loaders", []))
            label   = f"{v.get('version_number','?')}  [{mc_vers}]  {loaders}"
            self.ver_combo.addItem(label, userData=v)
        self.download_btn.setEnabled(True)

    def _download_selected(self):
        if not self.inst_combo.currentText():
            QMessageBox.warning(self, "No Instance",
                                "Select an instance to install the mod to.")
            return
        idx = self.ver_combo.currentIndex()
        if idx < 0:
            return
        ver_data = self.ver_combo.itemData(idx)
        if not ver_data:
            return

        files = ver_data.get("files", [])
        if not files:
            QMessageBox.warning(self, "No File", "No downloadable file found.")
            return

        primary  = next((f for f in files if f.get("primary")), files[0])
        url      = primary.get("url", "")
        filename = primary.get("filename", "mod.jar")

        inst_name = self.inst_combo.currentText()
        inst = self.inst_tab.instances.get(inst_name)
        if not inst:
            QMessageBox.warning(self, "Instance Not Found", "Instance not found.")
            return

        dest = inst.mods_dir / filename
        if dest.exists():
            reply = QMessageBox.question(
                self, "Already Exists",
                f"{filename} is already in mods folder. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.download_btn.setEnabled(False)
        self.dl_progress.setVisible(True)
        self.dl_progress.setValue(0)
        self.dl_status.setText(f"Downloading {filename}…")

        self._dl_worker = ModDownloadWorker(
            self.mgr, url, filename, inst.mods_dir
        )
        self._dl_worker.prog.connect(
            lambda c, t, s: self._update_dl_progress(c, t)
        )
        self._dl_worker.log.connect(lambda m: self.dl_status.setText(m))
        self._dl_worker.done.connect(self._on_download_done)
        self._dl_worker.start()

    def _update_dl_progress(self, current: int, total: int):
        if total > 0:
            self.dl_progress.setMaximum(total)
            self.dl_progress.setValue(current)

    @pyqtSlot(bool, str)
    def _on_download_done(self, ok: bool, filename: str):
        self.dl_progress.setVisible(False)
        self.download_btn.setEnabled(True)
        if ok:
            self.dl_status.setText(f"✅ {filename} installed!")
            self.install_signal.emit(f"✅ Mod installed: {filename}")
        else:
            self.dl_status.setText(f"❌ Download failed: {filename}")

    def _open_web(self):
        if not self._current_mod:
            return
        slug = self._current_mod.get("slug", "")
        if slug:
            QDesktopServices.openUrl(QUrl(f"https://modrinth.com/mod/{slug}"))


class LogTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Session Log"))
        ctrl.addStretch()

        clear_btn = QPushButton("🧹 Clear")
        clear_btn.clicked.connect(self._clear)
        ctrl.addWidget(clear_btn)

        save_btn = QPushButton("💾 Save Log")
        save_btn.clicked.connect(self._save)
        ctrl.addWidget(save_btn)

        open_dir_btn = QPushButton("📂 Log Files")
        open_dir_btn.clicked.connect(lambda: _open_path(str(LOG_DIR)))
        ctrl.addWidget(open_dir_btn)
        layout.addLayout(ctrl)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)

        self._buffer: List[str] = []

    def append(self, msg: str, level: str = "INFO"):
        color = LOG_COLORS.get(level, "#cdd6f4")
        ts = datetime.now().strftime("%H:%M:%S")
        safe_msg = (
            msg.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
        )
        html = (
            f'<span style="color:#6c7086">[{ts}]</span> '
            f'<span style="color:{color}">{safe_msg}</span>'
        )
        self.text.append(html)
        self.text.ensureCursorVisible()
        self._buffer.append(f"[{ts}] {msg}")

    def _clear(self):
        self.text.clear()
        self._buffer.clear()

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log", str(LOG_DIR / "session.log"), "Log (*.log *.txt)"
        )
        if path:
            Path(path).write_text("\n".join(self._buffer), encoding="utf-8")


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config: dict = {}
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)

        acc_grp = QGroupBox("Account")
        acc_l = QVBoxLayout(acc_grp)
        row = QHBoxLayout()
        row.addWidget(QLabel("Username:"))
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("OfflinePlayer")
        row.addWidget(self.username_edit)
        acc_l.addLayout(row)
        note = QLabel("ℹ️  Offline mode only. Multiplayer on offline-mode servers only.")
        note.setObjectName("subtitle")
        acc_l.addWidget(note)
        layout.addWidget(acc_grp)

        java_grp = QGroupBox("Java")
        java_l = QVBoxLayout(java_grp)
        self.java_label = QLabel("🔍 Checking…")
        java_l.addWidget(self.java_label)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Custom Java path (optional):"))
        self.java_path_edit = QLineEdit()
        self.java_path_edit.setPlaceholderText("Leave blank to auto-detect")
        row2.addWidget(self.java_path_edit)
        browse_java = QPushButton("…")
        browse_java.setFixedWidth(30)
        browse_java.clicked.connect(self._browse_java)
        row2.addWidget(browse_java)
        java_l.addLayout(row2)
        layout.addWidget(java_grp)

        mem_grp = QGroupBox("Memory")
        mem_l = QVBoxLayout(mem_grp)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Max RAM (MB):"))
        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(512, 65536)
        self.ram_spin.setValue(2048)
        self.ram_spin.setSuffix(" MB")
        row3.addWidget(self.ram_spin)
        auto_btn = QPushButton("Auto-detect")
        auto_btn.clicked.connect(self._auto_ram)
        row3.addWidget(auto_btn)
        row3.addStretch()
        mem_l.addLayout(row3)
        layout.addWidget(mem_grp)

        jvm_grp = QGroupBox("Extra JVM Arguments")
        jvm_l = QVBoxLayout(jvm_grp)
        self.jvm_edit = QLineEdit()
        self.jvm_edit.setPlaceholderText("e.g. -Dfml.readTimeout=90")
        jvm_l.addWidget(self.jvm_edit)
        layout.addWidget(jvm_grp)

        dir_grp = QGroupBox("Data Directory")
        dir_l = QHBoxLayout(dir_grp)
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setText(str(BASE_DIR))
        dir_l.addWidget(self.dir_edit)
        open_dir_btn = QPushButton("📂")
        open_dir_btn.setFixedWidth(36)
        open_dir_btn.clicked.connect(lambda: _open_path(str(BASE_DIR)))
        dir_l.addWidget(open_dir_btn)
        layout.addWidget(dir_grp)

        misc_grp = QGroupBox("Misc")
        misc_l = QVBoxLayout(misc_grp)
        self.snap_cb = QCheckBox("Show snapshots in version lists")
        misc_l.addWidget(self.snap_cb)
        self.close_launcher_cb = QCheckBox("Hide launcher when game starts")
        misc_l.addWidget(self.close_launcher_cb)
        layout.addWidget(misc_grp)

        row_save = QHBoxLayout()
        row_save.addStretch()
        save_btn = QPushButton("💾 Save Settings")
        save_btn.setObjectName("success")
        save_btn.clicked.connect(self.save)
        row_save.addWidget(save_btn)
        layout.addLayout(row_save)

        layout.addStretch()
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.addWidget(scroll)

    def _browse_java(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select Java executable", "", "java*(*)")
        if p:
            self.java_path_edit.setText(p)

    def _auto_ram(self):
        if PSUTIL_AVAILABLE:
            total = psutil.virtual_memory().total // (1024 * 1024)
            rec = max(512, min(total - 1024, total // 2))
            self.ram_spin.setValue(rec)
        else:
            QMessageBox.information(self, "psutil missing",
                                    "Install psutil for auto-detect:\npip install psutil")

    def load(self, cfg: dict):
        self.config = cfg
        self.username_edit.setText(cfg.get("username", ""))
        self.ram_spin.setValue(int(cfg.get("ram", 2048)))
        self.jvm_edit.setText(cfg.get("extra_jvm", ""))
        self.java_path_edit.setText(cfg.get("java_path", ""))
        self.snap_cb.setChecked(bool(cfg.get("snapshots", False)))
        self.close_launcher_cb.setChecked(bool(cfg.get("close_on_launch", False)))

    def save(self) -> bool:
        self.config.update(self._read_ui())
        try:
            CONFIG_FILE.write_text(
                json.dumps(self.config, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            if KEYRING_AVAILABLE:
                keyring.set_password(KEYRING_SVC, "username", self.config["username"])
            logger.info("Settings saved")
            QMessageBox.information(self, "Saved", "✅ Settings saved successfully!")
            return True
        except Exception as e:
            logger.error(f"Save settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
            return False

    def _read_ui(self) -> dict:
        return {
            "username":        self.username_edit.text().strip(),
            "ram":             self.ram_spin.value(),
            "extra_jvm":       self.jvm_edit.text().strip(),
            "java_path":       self.java_path_edit.text().strip(),
            "snapshots":       self.snap_cb.isChecked(),
            "close_on_launch": self.close_launcher_cb.isChecked(),
        }

    def get(self) -> dict:
        merged = dict(self.config)
        merged.update(self._read_ui())
        return merged

    def set_java_status(self, ok: bool, msg: str):
        self.java_label.setText(msg)
        self.java_label.setStyleSheet(f"color: {'#a6e3a1' if ok else '#f38ba8'};")


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _open_path(path: str):
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        logger.error(f"_open_path({path}): {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PhantomX Launcher  v{APP_VERSION}")
        self.setMinimumSize(960, 680)

        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))
            logger.info(f"Icon loaded: {ICON_FILE}")
        else:
            logger.warning(f"icon.ico not found at {ICON_FILE}")

        self.mgr              = MinecraftManager()
        self.signals          = Signals()
        self.install_worker:  Optional[InstallWorker] = None
        self.launch_worker:   Optional[LaunchWorker]  = None
        self.active_instance: Optional[Instance]      = None

        self._build_ui()
        self._connect_signals()
        self._load_config()
        self._check_java_async()

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        wm_lbl = QLabel(f"  {WATERMARK}  ")
        wm_lbl.setObjectName("watermark")
        self.status_bar.addPermanentWidget(wm_lbl)
        self.status_bar.showMessage("Ready")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────────────────
        topbar = QWidget()
        topbar.setStyleSheet("background:#181825; border-bottom:1px solid #313244;")
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(16, 8, 16, 8)

        title = QLabel("⚡ PhantomX")
        title.setObjectName("header")
        tl.addWidget(title)

        sub = QLabel(f"v{APP_VERSION}  •  Minecraft Launcher")
        sub.setObjectName("subtitle")
        tl.addWidget(sub)
        tl.addStretch()

        self.music_player = MusicPlayerWidget()
        tl.addWidget(self.music_player)

        tl.addSpacing(16)

        tl.addWidget(QLabel("Instance:"))
        self.quick_inst_combo = QComboBox()
        self.quick_inst_combo.setMinimumWidth(160)
        tl.addWidget(self.quick_inst_combo)

        # ── FIX: correct initial enabled state ───────────────────────────────
        self.launch_btn = QPushButton("🎮 Launch")
        self.launch_btn.setObjectName("success")
        self.launch_btn.setEnabled(True)
        self.launch_btn.clicked.connect(self._quick_launch)
        tl.addWidget(self.launch_btn)

        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_game)
        tl.addWidget(self.stop_btn)

        root.addWidget(topbar)

        # ── Progress bar row ──────────────────────────────────────────────────
        prog_widget = QWidget()
        prog_widget.setStyleSheet("background:#181825;")
        pl = QHBoxLayout(prog_widget)
        pl.setContentsMargins(16, 4, 16, 4)
        self.prog_label = QLabel("")
        pl.addWidget(self.prog_label)
        self.prog_bar = QProgressBar()
        self.prog_bar.setVisible(False)
        pl.addWidget(self.prog_bar)
        root.addWidget(prog_widget)

        # ── Tabs ──────────────────────────────────────────────────────────────
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.inst_tab = InstanceTab()
        self.tabs.addTab(self.inst_tab, "📦 Instances")

        self.mod_tab = ModTab(self.mgr)
        self.tabs.addTab(self.mod_tab, "🧩 Mods")

        self.market_tab = MarketplaceTab(self.mgr, self.inst_tab)
        self.tabs.addTab(self.market_tab, "🛒 Marketplace")

        self.log_tab = LogTab()
        self.tabs.addTab(self.log_tab, "📋 Log")

        self.settings_tab = SettingsTab()
        self.tabs.addTab(self.settings_tab, "⚙️ Settings")

    # ── Signal wiring ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        self.signals.log.connect(lambda m, l: self.log_tab.append(m, l))
        self.signals.progress.connect(self._on_progress)
        self.signals.java_status.connect(self.settings_tab.set_java_status)
        self.signals.dl_done.connect(self._on_install_done)
        self.signals.game_exited.connect(self._on_game_exited)
        self.signals.status_msg.connect(self.status_bar.showMessage)

        self.inst_tab.request_install.connect(self._install_instance)
        self.inst_tab.request_launch.connect(self._launch_instance)
        self.inst_tab.list_widget.itemSelectionChanged.connect(self._on_inst_selection_changed)

        self.market_tab.install_signal.connect(
            lambda m: self.signals.log.emit(m, "SUCCESS")
        )

    # ── Config ────────────────────────────────────────────────────────────────
    def _load_config(self):
        cfg: dict = {}
        if CONFIG_FILE.exists():
            try:
                cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Config load error: {e}")
        if KEYRING_AVAILABLE and not cfg.get("username"):
            try:
                cfg["username"] = keyring.get_password(KEYRING_SVC, "username") or ""
            except Exception:
                pass
        self.settings_tab.load(cfg)
        self.music_player.load_state(cfg)
        self._refresh_quick_combo()

    def _refresh_quick_combo(self):
        current = self.quick_inst_combo.currentText()
        self.quick_inst_combo.clear()
        for name in self.inst_tab.instances:
            self.quick_inst_combo.addItem(name)
        idx = self.quick_inst_combo.findText(current)
        if idx >= 0:
            self.quick_inst_combo.setCurrentIndex(idx)
        self.market_tab.refresh_instances()

    # ── Java check ────────────────────────────────────────────────────────────
    def _check_java_async(self):
        def task():
            ok, msg = self.mgr.check_java()
            self.signals.java_status.emit(ok, msg)
            self.signals.log.emit(msg, "SUCCESS" if ok else "WARN")
        threading.Thread(target=task, daemon=True).start()

    # ── Instance selection ────────────────────────────────────────────────────
    def _on_inst_selection_changed(self):
        inst = self.inst_tab._selected_instance()
        if inst:
            self.mod_tab.set_instance(inst)
            self.active_instance = inst

    # ── Install ───────────────────────────────────────────────────────────────
    def _install_instance(self, inst: Instance):
        if self.install_worker and self.install_worker.isRunning():
            QMessageBox.warning(self, "Busy", "An install is already in progress.")
            return
        self.signals.log.emit(f"⬇️  Starting install: {inst.name}", "INFO")
        self.prog_bar.setVisible(True)
        self.prog_bar.setValue(0)
        self.launch_btn.setEnabled(False)

        self.install_worker = InstallWorker(self.mgr, inst)
        self.install_worker.log.connect(lambda m: self.signals.log.emit(m, "INFO"))
        self.install_worker.prog.connect(lambda c, t, s: self.signals.progress.emit(c, t, s))
        self.install_worker.done.connect(lambda ok, n: self.signals.dl_done.emit(ok, n))
        self.install_worker.start()

    def _on_install_done(self, ok: bool, name: str):
        self.prog_bar.setVisible(False)
        self.launch_btn.setEnabled(True)
        self._refresh_quick_combo()
        if ok:
            self.signals.log.emit(f"✅ '{name}' installed and ready!", "SUCCESS")
            self.signals.status_msg.emit(f"✅ {name} ready")
        else:
            self.signals.log.emit(f"❌ Install failed for '{name}'", "ERROR")
            self.signals.status_msg.emit(f"❌ Install failed: {name}")
            QMessageBox.critical(
                self, "Install Failed",
                f"Could not install '{name}'.\nCheck the Log tab for details."
            )

    # ── Launch ────────────────────────────────────────────────────────────────
    def _get_launch_params(self) -> tuple[str, int, str, str]:
        cfg = self.settings_tab.get()
        username  = cfg.get("username", "").strip()
        ram       = int(cfg.get("ram", 2048))
        extra_jvm = cfg.get("extra_jvm", "").strip()
        java_path = cfg.get("java_path", "").strip()

        if not username:
            username, ok = QInputDialog.getText(
                self, "Username Required", "Enter your offline username:"
            )
            if not ok or not username.strip():
                return "", ram, extra_jvm, java_path
            username = username.strip()

        return username, ram, extra_jvm, java_path

    def _quick_launch(self):
        name = self.quick_inst_combo.currentText()
        inst = self.inst_tab.instances.get(name)
        if not inst:
            QMessageBox.warning(self, "No Instance",
                                "Create and install an instance first.")
            return
        self._launch_instance(inst)

    def _launch_instance(self, inst: Instance):
        if self.launch_worker and self.launch_worker.isRunning():
            QMessageBox.warning(self, "Running", "A game is already running!")
            return

        username, ram, extra_jvm, java_path = self._get_launch_params()
        if not username:
            return

        if not self.mgr.is_loader_installed(inst):
            reply = QMessageBox.question(
                self, "Not Installed",
                f"'{inst.name}' doesn't seem to be installed.\nInstall now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._install_instance(inst)
            return

        java_ok, java_msg = self.mgr.check_java()
        if not java_ok:
            reply = QMessageBox.question(
                self, "Java Missing",
                f"{java_msg}\n\nTry to launch anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.signals.log.emit(f"🚀 Launching '{inst.name}' as {username}…", "INFO")

        # ── FIX: correct button state when game starts ─────────────────────
        self.launch_btn.setEnabled(False)   # can't launch twice
        self.stop_btn.setEnabled(True)      # can now stop
        self.status_bar.showMessage(f"🎮 Playing: {inst.name}")

        inst.last_played = datetime.now().isoformat()
        inst.play_count += 1
        inst.save()

        cfg = self.settings_tab.get()
        close_on_launch = cfg.get("close_on_launch", False)

        self.launch_worker = LaunchWorker(
            self.mgr, inst, username, ram, extra_jvm, java_path
        )
        self.launch_worker.log.connect(lambda m: self.signals.log.emit(m, "GAME"))
        self.launch_worker.done.connect(lambda rc: self.signals.game_exited.emit(rc))
        self.launch_worker.start()

        if close_on_launch:
            self.hide()

    def _stop_game(self):
        if self.launch_worker:
            self.signals.log.emit("⏹ Stopping game…", "WARN")
            self.launch_worker.terminate()

    def _on_game_exited(self, rc: int):
        # ── FIX: correct button state when game exits ──────────────────────
        self.launch_btn.setEnabled(True)    # ready to launch again
        self.stop_btn.setEnabled(False)     # nothing to stop
        self.launch_worker = None
        self.status_bar.showMessage(f"Game exited (code {rc})")
        if not self.isVisible():
            self.show()
            self.raise_()

    # ── Progress ──────────────────────────────────────────────────────────────
    def _on_progress(self, current: int, total: int, label: str):
        self.prog_bar.setVisible(True)
        if total > 0:
            self.prog_bar.setMaximum(total)
            self.prog_bar.setValue(current)
            pct = int(current / total * 100)
            self.prog_label.setText(f"{label}  {pct}%")
            self.status_bar.showMessage(f"{label} — {pct}%")
            if current >= total:
                self.prog_bar.setVisible(False)
                self.prog_label.setText("")
        else:
            self.prog_bar.setMaximum(0)

    # ── Close ─────────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        if self.launch_worker and self.launch_worker.isRunning():
            reply = QMessageBox.question(
                self, "Game Running",
                "Minecraft is still running.\nKill it and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._stop_game()
                self.launch_worker.wait(3000)
            else:
                event.ignore()
                return

        cfg = self.settings_tab._read_ui()
        cfg.update(self.music_player.save_state())
        self.settings_tab.config.update(cfg)
        try:
            CONFIG_FILE.write_text(
                json.dumps(self.settings_tab.config, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Auto-save on exit: {e}")

        logger.info("PhantomX closing")
        event.accept()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logger.info(
        f"Python {sys.version}  |  Platform: {platform.system()} {platform.machine()}"
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(DARK_QSS)

    # Load app-level icon so it appears in taskbar too
    if ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(ICON_FILE)))

    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        app.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    window = MainWindow()
    window.show()

    logger.info("UI shown — entering event loop")
    sys.exit(app.exec())


# ── PyInstaller guard ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()