"""
PhantomX Launcher - Repair Tab
Two-phase architecture: Scan → Download Queue → Execute Downloads → Rebuild Natives
Never modifies user data (mods/, saves/, config/, etc.)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import shutil
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QProgressBar, QTextEdit, QGroupBox, QCheckBox,
    QDialog, QDialogButtonBox, QMessageBox,
)
from PyQt6.QtGui import QColor

from core import Instance, MinecraftManager, INST_DIR, BASE_DIR


# ── Constants ──────────────────────────────────────────────────────────────────
SAFE_DIRS = frozenset([
    "mods", "config", "saves", "resourcepacks",
    "shaderpacks", "screenshots", "logs",
])
MAX_CONCURRENT_DL = 16
MAX_RETRIES = 3
MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
ASSETS_BASE = "https://resources.download.minecraft.net"


# ═══════════════════════════════════════════════════════════════════════════════
# REPAIR WORKER
# ═══════════════════════════════════════════════════════════════════════════════

class RepairWorker(QThread):
    """Two-phase repair: scan first, download second."""

    progress  = pyqtSignal(int, int, str)   # current, total, status_text
    log       = pyqtSignal(str)             # log message
    done      = pyqtSignal(dict)            # summary dict
    error     = pyqtSignal(str)             # fatal error

    def __init__(
        self,
        instance: Instance,
        deep_repair: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.instance = instance
        self.deep_repair = deep_repair
        self._stop = False

    # ── Main entry ────────────────────────────────────────────────────────────
    def run(self):
        start = time.time()
        summary = {
            "scanned_jar": 0, "scanned_libs": 0, "scanned_assets": 0,
            "restored_jar": 0, "restored_libs": 0, "restored_assets": 0,
            "rebuilt_natives": False,
            "elapsed": 0.0,
        }
        try:
            inst = self.instance
            game_dir = Path(inst.game_dir)
            mc_ver = inst.version_id

            # ── Phase 1: Scan ────────────────────────────────────────────────
            download_queue: List[Tuple[str, Path, str]] = []  # (url, dest, sha1)

            # Step 1: Version files
            self.progress.emit(0, 0, "Checking version files...")
            self.log.emit(f"🔍 Checking version: {mc_ver}")
            jar_items, jar_queue = self._scan_version(game_dir, mc_ver)
            summary["scanned_jar"] = jar_items
            download_queue.extend(jar_queue)
            summary["restored_jar"] = len(jar_queue)

            if self._stop:
                return

            # Step 2: Libraries
            self.progress.emit(0, 0, "Checking libraries...")
            ver_json_path = game_dir / "versions" / mc_ver / f"{mc_ver}.json"
            ver_data = {}
            if ver_json_path.exists():
                try:
                    ver_data = json.loads(ver_json_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            lib_items, lib_queue = self._scan_libraries(game_dir, ver_data)
            summary["scanned_libs"] = lib_items
            download_queue.extend(lib_queue)
            summary["restored_libs"] = len(lib_queue)

            if self._stop:
                return

            # Step 3: Assets
            self.progress.emit(0, 0, "Checking assets...")
            asset_items, asset_queue = self._scan_assets(game_dir, ver_data)
            summary["scanned_assets"] = asset_items
            download_queue.extend(asset_queue)
            summary["restored_assets"] = len(asset_queue)

            if self._stop:
                return

            total_dl = len(download_queue)
            self.log.emit(
                f"📋 Scan complete: {total_dl} file(s) need repair"
            )

            # ── Phase 2: Download ────────────────────────────────────────────
            if download_queue:
                self.progress.emit(0, total_dl, f"Downloading missing files (0/{total_dl})...")
                if AIOHTTP_AVAILABLE:
                    asyncio.run(self._download_all(download_queue, total_dl))
                else:
                    self._download_all_sync(download_queue, total_dl)

            if self._stop:
                return

            # Step 5: Rebuild natives
            self.progress.emit(0, 0, "Rebuilding natives...")
            rebuilt = self._rebuild_natives(game_dir, mc_ver, ver_data)
            summary["rebuilt_natives"] = rebuilt

        except Exception as e:
            logger.exception(f"RepairWorker error: {e}")
            self.error.emit(str(e))
            return

        summary["elapsed"] = round(time.time() - start, 1)
        self.progress.emit(1, 1, "Completed")
        self.log.emit("✅ Repair completed!")
        self.done.emit(summary)

    def stop(self):
        self._stop = True

    # ── Phase 1 helpers ───────────────────────────────────────────────────────

    def _sha1_file(self, path: Path) -> str:
        h = hashlib.sha1()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()

    def _scan_version(
        self, game_dir: Path, mc_ver: str
    ) -> Tuple[int, List]:
        """Check version JSON and client JAR."""
        queue = []
        ver_dir = game_dir / "versions" / mc_ver
        ver_dir.mkdir(parents=True, exist_ok=True)

        # Get version info from Mojang manifest
        try:
            import requests
            r = requests.get(MOJANG_MANIFEST, timeout=10)
            manifest = r.json()
            ver_info = next(
                (v for v in manifest["versions"] if v["id"] == mc_ver), None
            )
        except Exception as e:
            self.log.emit(f"⚠️  Could not fetch manifest: {e}")
            ver_info = None

        count = 0

        # Check version JSON
        json_path = ver_dir / f"{mc_ver}.json"
        if not json_path.exists() and ver_info:
            self.log.emit(f"  ⚠️  Missing: {mc_ver}.json → queuing download")
            queue.append((ver_info["url"], json_path, ""))
            count += 1
        else:
            count += 1

        # Check client JAR
        jar_path = ver_dir / f"{mc_ver}.jar"
        count += 1
        if ver_info and json_path.exists():
            try:
                vdata = json.loads(json_path.read_text(encoding="utf-8"))
                dl_info = vdata.get("downloads", {}).get("client", {})
                expected_sha1 = dl_info.get("sha1", "")
                jar_url = dl_info.get("url", "")

                if not jar_path.exists():
                    self.log.emit(f"  ⚠️  Missing: {mc_ver}.jar → queuing download")
                    queue.append((jar_url, jar_path, expected_sha1))
                elif expected_sha1:
                    actual = self._sha1_file(jar_path)
                    if actual != expected_sha1:
                        self.log.emit(f"  ⚠️  Corrupted: {mc_ver}.jar → queuing re-download")
                        jar_path.unlink(missing_ok=True)
                        queue.append((jar_url, jar_path, expected_sha1))
                    else:
                        self.log.emit(f"  ✅ OK: {mc_ver}.jar")
            except Exception as e:
                self.log.emit(f"  ⚠️  Could not verify JAR: {e}")
        elif not jar_path.exists():
            self.log.emit(f"  ⚠️  Missing: {mc_ver}.jar (cannot verify without manifest)")

        return count, queue

    def _scan_libraries(
        self, game_dir: Path, ver_data: dict
    ) -> Tuple[int, List]:
        """Verify all libraries from version JSON."""
        queue = []
        libs = ver_data.get("libraries", [])
        lib_dir = game_dir / "libraries"
        count = 0

        lib_paths = []
        for lib in libs:
            dl = lib.get("downloads", {})
            artifact = dl.get("artifact", {})
            path_str = artifact.get("path", "")
            url = artifact.get("url", "")
            sha1 = artifact.get("sha1", "")
            if not path_str:
                continue
            dest = lib_dir / path_str
            lib_paths.append((dest, url, sha1))

        count = len(lib_paths)
        self.log.emit(f"  Checking {count} libraries...")

        # Use thread pool for SHA-1 verification
        needs_dl = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {
                ex.submit(self._check_file, dest, sha1): (dest, url, sha1)
                for dest, url, sha1 in lib_paths
            }
            for fut in as_completed(futures):
                dest, url, sha1 = futures[fut]
                ok = fut.result()
                if not ok and url:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    needs_dl.append((url, dest, sha1))

        queue.extend(needs_dl)
        self.log.emit(f"  Libraries: {len(needs_dl)} need repair out of {count}")
        return count, queue

    def _check_file(self, path: Path, expected_sha1: str) -> bool:
        if not path.exists():
            return False
        if expected_sha1:
            actual = self._sha1_file(path)
            return actual == expected_sha1
        return True

    def _scan_assets(
        self, game_dir: Path, ver_data: dict
    ) -> Tuple[int, List]:
        """Verify asset files."""
        queue = []
        asset_index_info = ver_data.get("assetIndex", {})
        index_id = asset_index_info.get("id", "")
        index_url = asset_index_info.get("url", "")

        if not index_id:
            self.log.emit("  ⚠️  No asset index found in version data")
            return 0, []

        assets_dir = game_dir / "assets"
        index_path = assets_dir / "indexes" / f"{index_id}.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)

        # Download asset index if missing
        if not index_path.exists() and index_url:
            try:
                import requests
                r = requests.get(index_url, timeout=10)
                index_path.write_bytes(r.content)
                self.log.emit(f"  📥 Downloaded asset index: {index_id}")
            except Exception as e:
                self.log.emit(f"  ⚠️  Could not download asset index: {e}")
                return 0, []

        if not index_path.exists():
            return 0, []

        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as e:
            self.log.emit(f"  ⚠️  Could not parse asset index: {e}")
            return 0, []

        objects = index_data.get("objects", {})
        count = len(objects)
        self.log.emit(f"  Checking {count} assets ({'deep' if self.deep_repair else 'fast'})...")

        needs_dl = []
        for name, info in objects.items():
            sha1 = info.get("hash", "")
            if not sha1:
                continue
            prefix = sha1[:2]
            dest = assets_dir / "objects" / prefix / sha1
            url = f"{ASSETS_BASE}/{prefix}/{sha1}"

            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                needs_dl.append((url, dest, sha1))
            elif self.deep_repair:
                actual = self._sha1_file(dest)
                if actual != sha1:
                    dest.unlink(missing_ok=True)
                    needs_dl.append((url, dest, sha1))

        queue.extend(needs_dl)
        self.log.emit(f"  Assets: {len(needs_dl)} need repair out of {count}")
        return count, queue

    # ── Phase 2: Download ──────────────────────────────────────────────────────

    async def _download_all(self, queue: List[Tuple[str, Path, str]], total: int):
        """Download all queued files concurrently with aiohttp."""
        done_count = [0]
        sem = asyncio.Semaphore(MAX_CONCURRENT_DL)

        async def _dl_one(session, url: str, dest: Path, sha1: str):
            for attempt in range(MAX_RETRIES):
                try:
                    async with sem:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                            if resp.status == 200:
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                content = await resp.read()
                                dest.write_bytes(content)
                                done_count[0] += 1
                                self.progress.emit(
                                    done_count[0], total,
                                    f"Downloading missing files ({done_count[0]}/{total})..."
                                )
                                return
                            else:
                                logger.warning(f"HTTP {resp.status} for {url}")
                except Exception as e:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(1)
                    else:
                        self.log.emit(f"  ❌ Failed: {dest.name} — {e}")

        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_DL)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [_dl_one(session, url, dest, sha1) for url, dest, sha1 in queue]
            await asyncio.gather(*tasks)

    def _download_all_sync(self, queue: List[Tuple[str, Path, str]], total: int):
        """Fallback synchronous download (no aiohttp)."""
        import requests
        for i, (url, dest, sha1) in enumerate(queue):
            for attempt in range(MAX_RETRIES):
                try:
                    r = requests.get(url, timeout=60)
                    if r.status_code == 200:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(r.content)
                        break
                except Exception as e:
                    if attempt == MAX_RETRIES - 1:
                        self.log.emit(f"  ❌ Failed: {dest.name} — {e}")
            self.progress.emit(i + 1, total, f"Downloading missing files ({i+1}/{total})...")

    # ── Phase 2: Rebuild natives ──────────────────────────────────────────────

    def _rebuild_natives(self, game_dir: Path, mc_ver: str, ver_data: dict) -> bool:
        natives_dir = game_dir / "versions" / mc_ver / "natives"
        try:
            if natives_dir.exists():
                shutil.rmtree(natives_dir, ignore_errors=True)
            natives_dir.mkdir(parents=True, exist_ok=True)

            system = platform.system().lower()
            os_key = {"windows": "windows", "darwin": "osx", "linux": "linux"}.get(system, "windows")

            libs = ver_data.get("libraries", [])
            extracted = 0
            for lib in libs:
                natives = lib.get("natives", {})
                if os_key not in natives:
                    continue
                classifier = natives[os_key]
                dl = lib.get("downloads", {}).get("classifiers", {}).get(classifier, {})
                path_str = dl.get("path", "")
                if not path_str:
                    continue
                jar_path = game_dir / "libraries" / path_str
                if not jar_path.exists():
                    continue
                rules = lib.get("rules", [])
                if not self._check_rules(rules, os_key):
                    continue
                try:
                    extract_excludes = lib.get("extract", {}).get("exclude", [])
                    with zipfile.ZipFile(jar_path, "r") as zf:
                        for name in zf.namelist():
                            if any(name.startswith(ex) for ex in extract_excludes):
                                continue
                            if name.endswith("/"):
                                continue
                            dest = natives_dir / Path(name).name
                            dest.write_bytes(zf.read(name))
                    extracted += 1
                except Exception as e:
                    self.log.emit(f"  ⚠️  Could not extract natives from {jar_path.name}: {e}")

            self.log.emit(f"  ✅ Rebuilt natives ({extracted} JARs extracted)")
            return True
        except Exception as e:
            self.log.emit(f"  ⚠️  Natives rebuild error: {e}")
            return False

    @staticmethod
    def _check_rules(rules: list, os_key: str) -> bool:
        if not rules:
            return True
        allowed = False
        for rule in rules:
            action = rule.get("action", "allow")
            os_info = rule.get("os", {})
            os_name = os_info.get("name", "")
            if not os_name or os_name == os_key:
                allowed = (action == "allow")
        return allowed


# ═══════════════════════════════════════════════════════════════════════════════
# REPAIR TAB
# ═══════════════════════════════════════════════════════════════════════════════

class RepairTab(QWidget):
    # Forward repair log messages to main window’s Log tab
    repair_log = pyqtSignal(str)

    def __init__(self, inst_tab, parent=None):
        super().__init__(parent)
        self.inst_tab = inst_tab
        self._worker: Optional[RepairWorker] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Header
        h = QHBoxLayout()
        lbl = QLabel("🔧 Repair Instance")
        lbl.setObjectName("header")
        h.addWidget(lbl)
        h.addStretch()
        layout.addLayout(h)

        # Instance selector
        sel_grp = QGroupBox("Select Instance to Repair")
        sel_l = QHBoxLayout(sel_grp)
        sel_l.addWidget(QLabel("Instance:"))
        self.inst_combo = QComboBox()
        self.inst_combo.setMinimumWidth(220)
        sel_l.addWidget(self.inst_combo)
        sel_l.addStretch()
        layout.addWidget(sel_grp)

        # Options
        opt_grp = QGroupBox("Repair Options")
        opt_l = QVBoxLayout(opt_grp)
        self.deep_cb = QCheckBox(
            "Deep Repair — verify SHA-1 hash of all assets (slower but thorough)"
        )
        opt_l.addWidget(self.deep_cb)
        note = QLabel("Fast Repair (default): checks file existence only for assets.")
        note.setStyleSheet("color: #a6adc8; font-size: 11px;")
        opt_l.addWidget(note)

        warn = QLabel(
            "⚠️  Repair never modifies: mods/ · saves/ · config/ · resourcepacks/ · shaderpacks/"
        )
        warn.setStyleSheet("color: #f9e2af; font-size: 11px;")
        opt_l.addWidget(warn)
        layout.addWidget(opt_grp)

        # Action buttons
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("🔧 Start Repair")
        self.start_btn.setObjectName("success")
        self.start_btn.clicked.connect(self._start_repair)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_repair)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Progress
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("subtitle")
        layout.addWidget(self.status_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setVisible(False)
        layout.addWidget(self.prog_bar)

        # Log output
        log_grp = QGroupBox("Repair Log")
        log_l = QVBoxLayout(log_grp)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        log_l.addWidget(self.log_text)
        layout.addWidget(log_grp)

    def refresh_instances(self):
        current = self.inst_combo.currentText()
        self.inst_combo.clear()
        for name in self.inst_tab.instances:
            self.inst_combo.addItem(name)
        idx = self.inst_combo.findText(current)
        if idx >= 0:
            self.inst_combo.setCurrentIndex(idx)

    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        safe = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.log_text.append(
            f'<span style="color:#6c7086">[{ts}]</span> '
            f'<span style="color:#cdd6f4">{safe}</span>'
        )
        self.log_text.ensureCursorVisible()

    def _start_repair(self):
        if self._worker and self._worker.isRunning():
            return

        name = self.inst_combo.currentText()
        inst = self.inst_tab.instances.get(name)
        if not inst:
            QMessageBox.warning(self, "No Instance", "Select an instance to repair.")
            return

        self.log_text.clear()
        self._append_log(f"🔧 Starting repair for: {inst.name}")
        self._append_log(f"   Version: {inst.version_id} | Loader: {inst.loader}")

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.prog_bar.setVisible(True)
        self.prog_bar.setRange(0, 0)  # indeterminate
        self.status_lbl.setText("Initializing...")

        self._worker = RepairWorker(inst, deep_repair=self.deep_cb.isChecked())
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._append_log)
        self._worker.log.connect(self.repair_log)   # forward to main Log tab
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _stop_repair(self):
        if self._worker:
            self._worker.stop()
        self._reset_ui()
        self._append_log("⏹ Repair stopped by user.")

    def _on_progress(self, current: int, total: int, status: str):
        self.status_lbl.setText(status)
        if total > 0:
            self.prog_bar.setRange(0, total)
            self.prog_bar.setValue(current)
            if current >= total:
                self.prog_bar.setVisible(False)
                self.status_lbl.setText("")
        else:
            self.prog_bar.setRange(0, 0)  # indeterminate

    def _on_done(self, summary: dict):
        self._reset_ui()
        self._show_summary(summary)

    def _on_error(self, msg: str):
        self._reset_ui()
        self._append_log(f"❌ Fatal error: {msg}")
        QMessageBox.critical(self, "Repair Error", f"Repair failed:\n{msg}")

    def _reset_ui(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.prog_bar.setVisible(False)
        self.status_lbl.setText("")

    def _show_summary(self, s: dict):
        rebuilt = "✔ Rebuilt Natives" if s.get("rebuilt_natives") else "— Natives not rebuilt"
        msg = (
            f"Repair Completed\n\n"
            f"Scanned:\n"
            f"  ✔ {s['scanned_jar']} Client JAR\n"
            f"  ✔ {s['scanned_libs']} Libraries\n"
            f"  ✔ {s['scanned_assets']} Assets\n\n"
            f"Restored:\n"
            f"  ✔ {s['restored_jar']} Client JAR\n"
            f"  ✔ {s['restored_libs']} Libraries\n"
            f"  ✔ {s['restored_assets']} Assets\n"
            f"  {rebuilt}\n\n"
            f"Elapsed Time: {s['elapsed']}s"
        )
        QMessageBox.information(self, "Repair Summary", msg)
        self._append_log(
            f"✅ Repair done in {s['elapsed']}s — "
            f"restored: {s['restored_jar']} jar, "
            f"{s['restored_libs']} libs, "
            f"{s['restored_assets']} assets"
        )
