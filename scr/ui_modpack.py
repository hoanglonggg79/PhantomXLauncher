"""
PhantomX Launcher - Modpack Tab
Ports PhantomXModpackInstaller logic from modpackinstaller.py (no Tkinter).
Supports CurseForge (.zip) and Modrinth (.mrpack / .zip) formats.
After installation, the instance is registered in the launcher like any other.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar, QTextEdit, QGroupBox,
    QFileDialog, QMessageBox,
)

from core import Instance, MinecraftManager, INST_DIR

_CF_API_KEY = ""
_MAX_CONCURRENT = 8


# ═══════════════════════════════════════════════════════════════════════════════
# MODPACK INSTALL WORKER
# ═══════════════════════════════════════════════════════════════════════════════

class ModpackInstallWorker(QThread):
    """Background worker that installs a modpack and creates a launcher instance."""

    log     = pyqtSignal(str)          # log messages (forwarded to Log tab)
    progress = pyqtSignal(int, int, str)  # current, total, status
    done    = pyqtSignal(bool, str)    # success, instance_name

    def __init__(
        self,
        zip_path: str,
        instance_name: str,
        mgr: MinecraftManager,
        parent=None,
    ):
        super().__init__(parent)
        self.zip_path = Path(zip_path)
        self.instance_name = instance_name
        self.mgr = mgr
        self.instance_dir = INST_DIR / instance_name
        self.temp_dir = self.instance_dir / "_temp_pack"
        self.mods_dir = self.instance_dir / "mods"
        self.pack_type: Optional[str] = None

    def run(self):
        try:
            self._log(f"=== ĐANG CÀI MODPACK: {self.instance_name} ===")
            manifest = self._extract_and_parse()
            version_id, loader_type, loader_ver = self._setup_loader(manifest)

            # Download mods
            if AIOHTTP_AVAILABLE:
                asyncio.run(self._download_mods(manifest))
            else:
                self._download_mods_sync(manifest)

            self._apply_overrides()

            # Create and register instance in the launcher
            inst = Instance(
                name=self.instance_name,
                version_id=version_id,
                loader=loader_type,
                loader_version=loader_ver,
                game_dir=str(self.instance_dir),
            )
            inst.save()

            self._log(f"✅ Instance '{self.instance_name}' đã được tạo thành công!")
            self.done.emit(True, self.instance_name)

        except Exception as e:
            self._log(f"❌ Lỗi khi cài modpack: {e}")
            logger.exception(f"ModpackInstallWorker error: {e}")
            self.done.emit(False, self.instance_name)
        finally:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _log(self, msg: str):
        logger.info(msg)
        self.log.emit(msg)

    # ── Extract & detect format ───────────────────────────────────────────────

    def _extract_and_parse(self) -> dict:
        self._log("📂 Đang giải nén tệp lưu trữ modpack...")
        self.instance_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(self.zip_path, "r") as zf:
            zf.extractall(self.temp_dir)

        if (self.temp_dir / "manifest.json").exists():
            self.pack_type = "curseforge"
            self._log("  Detected: CurseForge format")
            return json.loads(
                (self.temp_dir / "manifest.json").read_text(encoding="utf-8")
            )
        elif (self.temp_dir / "modrinth.index.json").exists():
            self.pack_type = "modrinth"
            self._log("  Detected: Modrinth format")
            return json.loads(
                (self.temp_dir / "modrinth.index.json").read_text(encoding="utf-8")
            )
        else:
            raise ValueError(
                "Unsupported modpack format: expected CurseForge manifest.json "
                "or Modrinth modrinth.index.json"
            )

    # ── Loader installation ───────────────────────────────────────────────────

    def _setup_loader(self, manifest: dict) -> tuple[str, str, str]:
        self._log("⚙️  Thiết lập game gốc & loader...")
        gdir = str(self.instance_dir)

        if self.pack_type == "curseforge":
            mc_ver = manifest["minecraft"]["version"]
            loaders = manifest["minecraft"]["modLoaders"]
            primary = next((l for l in loaders if l.get("primary")), loaders[0])
            loader_id: str = primary["id"]  # e.g. "forge-47.2.0" or "neoforge-21.1.12"

            self._install_vanilla(mc_ver, gdir)

            # IMPORTANT: check neoforge BEFORE forge to avoid substring match bug
            if loader_id.startswith("neoforge-") or "neoforge" in loader_id.split("-")[0]:
                loader_type = "neoforge"
                loader_ver = loader_id.replace("neoforge-", "", 1)
                self._install_neoforge(mc_ver, loader_ver, gdir)
            elif "forge" in loader_id:
                loader_type = "forge"
                loader_ver = loader_id.replace("forge-", "", 1)
                self._install_forge(mc_ver, loader_ver, gdir)
            elif "fabric" in loader_id:
                loader_type = "fabric"
                loader_ver = loader_id.replace("fabric-", "", 1)
                self._install_fabric(mc_ver, loader_ver, gdir)
            elif "quilt" in loader_id:
                loader_type = "quilt"
                loader_ver = loader_id.replace("quilt-", "", 1)
                self._install_quilt(mc_ver, loader_ver, gdir)
            else:
                loader_type = "vanilla"
                loader_ver = ""

            return mc_ver, loader_type, loader_ver

        elif self.pack_type == "modrinth":
            deps = manifest.get("dependencies", {})
            mc_ver = deps.get("minecraft")
            if not mc_ver:
                raise Exception("No Minecraft version found in Modrinth dependencies")

            self._install_vanilla(mc_ver, gdir)

            if "fabric-loader" in deps:
                loader_ver = deps["fabric-loader"]
                self._install_fabric(mc_ver, loader_ver, gdir)
                return mc_ver, "fabric", loader_ver
            elif "neoforge" in deps:
                loader_ver = deps["neoforge"]
                self._install_neoforge(mc_ver, loader_ver, gdir)
                return mc_ver, "neoforge", loader_ver
            elif "forge" in deps:
                loader_ver = deps["forge"]
                self._install_forge(mc_ver, loader_ver, gdir)
                return mc_ver, "forge", loader_ver
            elif "quilt-loader" in deps:
                loader_ver = deps["quilt-loader"]
                self._install_quilt(mc_ver, loader_ver, gdir)
                return mc_ver, "quilt", loader_ver
            else:
                return mc_ver, "vanilla", ""

        raise ValueError(f"Unknown pack type: {self.pack_type}")

    def _install_vanilla(self, mc_ver: str, gdir: str):
        self._log(f"📦 Đang cài đặt Minecraft {mc_ver}...")
        self.mgr.install_vanilla(mc_ver, gdir, cb_log=self._log)

    def _install_forge(self, mc_ver: str, loader_ver: str, gdir: str):
        java = self.mgr.find_java() or "java"
        self.mgr.install_forge(mc_ver, loader_ver, gdir, java, cb_log=self._log)

    def _install_fabric(self, mc_ver: str, loader_ver: str, gdir: str):
        self.mgr.install_fabric(mc_ver, loader_ver, gdir, cb_log=self._log)

    def _install_quilt(self, mc_ver: str, loader_ver: str, gdir: str):
        self.mgr.install_quilt(mc_ver, loader_ver, gdir, cb_log=self._log)

    def _install_neoforge(self, mc_ver: str, loader_ver: str, gdir: str):
        java = self.mgr.find_java() or "java"
        self.mgr.install_neoforge(mc_ver, loader_ver, gdir, java_path=java, cb_log=self._log)

    # ── Mod download (async) ──────────────────────────────────────────────────

    async def _download_mods(self, manifest: dict):
        self._log("⬇️  Đang tải mods...")
        self.mods_dir.mkdir(parents=True, exist_ok=True)
        files = manifest.get("files", [])
        if not files:
            self._log("  Không có tệp nào để tải xuống.")
            return

        connector = aiohttp.TCPConnector(limit=_MAX_CONCURRENT)
        async with aiohttp.ClientSession(connector=connector) as session:
            if self.pack_type == "curseforge":
                tasks = [self._dl_cf_mod(session, f) for f in files]
            else:
                tasks = [self._dl_mr_mod(session, f) for f in files]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            failed = sum(1 for r in results if isinstance(r, Exception))
            if failed:
                self._log(f"  ⚠️  {failed} file(s) failed to download")

    async def _dl_cf_mod(self, session: "aiohttp.ClientSession", file_info: dict):
        headers = {
            "Accept": "application/json",
            "x-api-key": _CF_API_KEY,
        }
        url = (
            f"https://api.curseforge.com/v1/mods/"
            f"{file_info['projectID']}/files/{file_info['fileID']}"
        )
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = (await resp.json())["data"]
                    dl_url = data.get("downloadUrl")
                    file_name = data["fileName"]
                    if dl_url:
                        async with session.get(dl_url, timeout=aiohttp.ClientTimeout(total=120)) as fr:
                            if fr.status == 200:
                                content = await fr.read()
                                (self.mods_dir / file_name).write_bytes(content)
                                self._log(f"  ✔️  {file_name}")
        except Exception as e:
            self._log(f"  ❌ CurseForge download failed: {e}")
            raise

    async def _dl_mr_mod(self, session: "aiohttp.ClientSession", file_info: dict):
        dl_url = file_info.get("downloads", [None])[0]
        if not dl_url:
            return
        try:
            dest_path = self.instance_dir / file_info["path"]
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            async with session.get(dl_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    dest_path.write_bytes(content)
                    self._log(f"  ✔️  {file_info['path']}")
        except Exception as e:
            self._log(f"  ❌ Modrinth download failed: {e}")
            raise

    def _download_mods_sync(self, manifest: dict):
        import requests
        self._log("⬇️  Đang tải mods (sync mode)...")
        files = manifest.get("files", [])
        self.mods_dir.mkdir(parents=True, exist_ok=True)
        for file_info in files:
            if self.pack_type == "modrinth":
                dl_url = file_info.get("downloads", [None])[0]
                if dl_url:
                    try:
                        dest = self.instance_dir / file_info["path"]
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        r = requests.get(dl_url, timeout=120)
                        if r.status_code == 200:
                            dest.write_bytes(r.content)
                            self._log(f"  ✔️  {file_info['path']}")
                    except Exception as e:
                        self._log(f"  ❌ {e}")

    # ── Apply overrides ───────────────────────────────────────────────────────

    def _apply_overrides(self):
        self._log("🚚 Đang áp dụng ghi đè / cấu hình...")
        for ov_folder in ["overrides", "client-overrides"]:
            ov_path = self.temp_dir / ov_folder
            if not ov_path.exists():
                continue
            for item in ov_path.iterdir():
                dst = self.instance_dir / item.name
                try:
                    if item.is_dir():
                        shutil.copytree(item, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dst)
                except Exception as e:
                    self._log(f"  ⚠️  Override copy error: {e}")
            self._log(f"  ✔️  Applied overrides from '{ov_folder}'")


# ═══════════════════════════════════════════════════════════════════════════════
# MODPACK TAB
# ═══════════════════════════════════════════════════════════════════════════════

class ModpackTab(QWidget):
    instance_created = pyqtSignal(str)
    # Forwarded from worker — connected by main_window to the Log tab
    log = pyqtSignal(str)

    def __init__(self, mgr: MinecraftManager, inst_tab, parent=None):
        super().__init__(parent)
        self.mgr = mgr
        self.inst_tab = inst_tab
        self._worker: Optional[ModpackInstallWorker] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Header
        h = QHBoxLayout()
        lbl = QLabel("📦 Trình Cài Đặt Modpack")
        lbl.setObjectName("header")
        h.addWidget(lbl)
        h.addStretch()
        note = QLabel("Hỗ trợ định dạng của CurseForge & Modrinth")
        note.setObjectName("subtitle")
        h.addWidget(note)
        layout.addLayout(h)

        # Setup group
        setup_grp = QGroupBox("Tạo Instance Mới từ Modpack")
        setup_l = QVBoxLayout(setup_grp)

        # Instance name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Tên Instance:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. ATM9 Modpack")
        name_row.addWidget(self.name_edit)
        setup_l.addLayout(name_row)

        # File picker
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("File Modpack:"))
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Chọn file .zip hoặc file .mrpack ...")
        self.file_edit.setReadOnly(True)
        file_row.addWidget(self.file_edit)
        browse_btn = QPushButton("📁 Duyệt")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)
        setup_l.addLayout(file_row)

        info_lbl = QLabel(
            "ℹ️  Mọi yêu cầu của modpack (như phiên bản Minecraft, Loader) sẽ được cài đặt tự động"
            "và chuẩn đét cho Instance."
        )
        info_lbl.setStyleSheet("color: #a6adc8; font-size: 11px;")
        info_lbl.setWordWrap(True)
        setup_l.addWidget(info_lbl)

        layout.addWidget(setup_grp)

        # Action row
        btn_row = QHBoxLayout()
        self.install_btn = QPushButton("📦 Cài đặt Modpack")
        self.install_btn.setObjectName("success")
        self.install_btn.clicked.connect(self._start_install)
        btn_row.addWidget(self.install_btn)

        self.cancel_btn = QPushButton("⏹ Hủy")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Progress
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("subtitle")
        layout.addWidget(self.status_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 0)  # indeterminate
        self.prog_bar.setVisible(False)
        layout.addWidget(self.prog_bar)

        # Log
        log_grp = QGroupBox("Installation Log")
        log_l = QVBoxLayout(log_grp)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(220)
        log_l.addWidget(self.log_text)
        layout.addWidget(log_grp)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file Modpack", "",
            "Modpack Files (*.zip *.mrpack);;All Files (*)"
        )
        if path:
            self.file_edit.setText(path)
            # Auto-fill instance name from filename if empty
            if not self.name_edit.text().strip():
                stem = Path(path).stem
                self.name_edit.setText(stem)

    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        safe = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.log_text.append(
            f'<span style="color:#6c7086">[{ts}]</span> '
            f'<span style="color:#cdd6f4">{safe}</span>'
        )
        self.log_text.ensureCursorVisible()

    def _start_install(self):
        if self._worker and self._worker.isRunning():
            return

        name = self.name_edit.text().strip()
        zip_path = self.file_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "Bắt buộc", "Vui lòng nhập tên instance.")
            return
        if not zip_path or not Path(zip_path).exists():
            QMessageBox.warning(self, "Bắt buộc", "Vui lòng chọn một file modpack hợp lệ.")
            return

        # Check for duplicate instance name
        if name in self.inst_tab.instances:
            reply = QMessageBox.question(
                self, "Instance đã tồn tại",
                f"Instance có tên '{name}' đã tồn tại.\n"
                "Bạn có muốn ghi đè nó? (Tất cả các tệp sẽ được thay thế)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.log_text.clear()
        self._append_log(f"📦 Bắt đầu cài đặt modpack: {name}")
        self.install_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.prog_bar.setVisible(True)
        self.status_lbl.setText("Đang cài đặt...")

        self._worker = ModpackInstallWorker(zip_path, name, self.mgr)
        self._worker.log.connect(self._append_log)
        self._worker.log.connect(self.log)   # forward to main window Log tab
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
        self._reset_ui()
        self._append_log("⏹ Cài đặt đã bị hủy.")

    def _on_progress(self, current: int, total: int, status: str):
        self.status_lbl.setText(status)
        if total > 0:
            self.prog_bar.setRange(0, total)
            self.prog_bar.setValue(current)
        else:
            self.prog_bar.setRange(0, 0)

    def _on_done(self, success: bool, instance_name: str):
        self._reset_ui()
        if success:
            self._append_log(
                f"✅ Cài đặt modpack thành công dưới dạng instance: '{instance_name}'"
            )
            self.instance_created.emit(instance_name)
            QMessageBox.information(
                self, "Modpack Installed",
                f"✅ Modpack đã được cài đặt!\n\n"
                f"Instance '{instance_name}' đã sẵn sàng.\n"
                f"Chọn nó trong tab Instances để khởi động.",
            )
        else:
            self._append_log("❌ Cài đặt modpack thất bại. Kiểm tra log bên trên.")
            QMessageBox.critical(
                self, "Install Failed",
                "Modpack installation failed.\nCheck the log for details.",
            )

    def _reset_ui(self):
        self.install_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.prog_bar.setVisible(False)
        self.status_lbl.setText("")
