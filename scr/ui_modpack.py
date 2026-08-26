from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
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

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar, QTextEdit, QGroupBox,
    QFileDialog, QMessageBox,
)

from core import Instance, MinecraftManager, INST_DIR

_CF_API_KEY = ""
_MAX_CONCURRENT = 6
_USER_AGENT = "PhantomXLauncher/1.1.1 (email)"

MR_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "*/*",
}
CF_HEADERS = {
    "Accept": "application/json",
    "x-api-key": _CF_API_KEY,
    "User-Agent": _USER_AGENT,
}
_INSTANCE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\- ]+$")


class _InstallCancelled(Exception):
    """Raised when the user requests cooperative cancellation."""


def validate_instance_name(name: str) -> str:
    """Whitelist instance names to prevent path traversal and invalid paths."""
    name = name.strip()
    if not name:
        raise ValueError("Tên instance không được để trống.")
    if not _INSTANCE_NAME_RE.fullmatch(name):
        raise ValueError(
            "Tên instance chỉ được chứa chữ cái, số, dấu gạch dưới (_), "
            "dấu gạch ngang (-) và khoảng trắng."
        )
    return name


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path, interrupt_check=None) -> None:
    """Extract ZIP entries safely, preventing Zip Slip and directory read errors."""
    dest_root = dest.resolve()
    dest_root.mkdir(parents=True, exist_ok=True)

    for member in zf.infolist():
        if interrupt_check and interrupt_check():
            raise _InstallCancelled()

        # Skip entries with empty names (some archives include them)
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


def _verify_downloaded_file(path: Path, label: str) -> None:
    if not path.exists():
        raise IOError(f"Download verification failed: {label} was not written to disk")
    if path.stat().st_size == 0:
        path.unlink(missing_ok=True)
        raise IOError(f"Download verification failed: {label} is empty")


# ═══════════════════════════════════════════════════════════════════════════════
# MODPACK INSTALL WORKER
# ═══════════════════════════════════════════════════════════════════════════════

class ModpackInstallWorker(QThread):
    """Background worker that installs a modpack and creates a launcher instance."""

    log = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(bool, str)

    def __init__(
        self,
        zip_path: str,
        instance_name: str,
        mgr: MinecraftManager,
        is_overwrite: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.zip_path = Path(zip_path)
        self.instance_name = instance_name
        self.mgr = mgr
        self.is_overwrite = is_overwrite
        self.final_dir = INST_DIR / instance_name
        self.staging_dir = INST_DIR / f"_staging_{instance_name}_{uuid.uuid4().hex[:8]}"
        self.instance_dir = self.staging_dir
        self.temp_dir = self.staging_dir / "_temp_pack"
        self.mods_dir = self.staging_dir / "mods"
        self.pack_type: Optional[str] = None
        self._committed = False
        self._async_tasks: list[asyncio.Task] = []

    def run(self):
        try:
            self._check_cancelled()
            self._log(f"=== ĐANG CÀI MODPACK: {self.instance_name} ===")
            if self.is_overwrite:
                self._log("  Chế độ: Ghi đè instance hiện có (staging an toàn)")

            manifest = self._extract_and_parse()
            self._check_cancelled()
            version_id, loader_type, loader_ver = self._setup_loader(manifest)
            self._check_cancelled()

            if AIOHTTP_AVAILABLE:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._download_mods(manifest))
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            else:
                self._download_mods_sync(manifest)

            self._check_cancelled()
            self._apply_overrides()
            self._check_cancelled()
            self._commit_install()

            inst = Instance(
                name=self.instance_name,
                version_id=version_id,
                loader=loader_type,
                loader_version=loader_ver,
                game_dir=str(self.final_dir),
            )
            inst.save()

            self._log(f"✅ Instance '{self.instance_name}' đã được tạo thành công!")
            self.done.emit(True, self.instance_name)

        except _InstallCancelled:
            self._log("⏹ Cài đặt đã bị hủy.")
            self.done.emit(False, self.instance_name)
        except Exception as e:
            self._log(f"❌ Lỗi khi cài modpack: {e}")
            logger.exception(f"ModpackInstallWorker error: {e}")
            self.done.emit(False, self.instance_name)
        finally:
            self._cleanup()

    def _check_cancelled(self) -> None:
        if self.isInterruptionRequested():
            raise _InstallCancelled()

    def _log(self, msg: str):
        logger.info(msg)
        self.log.emit(msg)

    def _commit_install(self) -> None:
        """Atomically replace the old instance with the staged install."""
        if self.final_dir.exists():
            shutil.rmtree(self.final_dir, ignore_errors=True)
        self.staging_dir.rename(self.final_dir)
        self.instance_dir = self.final_dir
        self.mods_dir = self.final_dir / "mods"
        self.temp_dir = self.final_dir / "_temp_pack"
        self._committed = True

    def _cleanup(self) -> None:
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        if not self._committed and self.staging_dir.exists():
            shutil.rmtree(self.staging_dir, ignore_errors=True)

    # ── Extract & detect format ───────────────────────────────────────────────

    def _extract_and_parse(self) -> dict:
        self._log("📂 Đang giải nén tệp lưu trữ modpack...")
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(self.zip_path, "r") as zf:
            _safe_extract_zip(zf, self.temp_dir, interrupt_check=self.isInterruptionRequested)

        if (self.temp_dir / "manifest.json").exists():
            self.pack_type = "curseforge"
            self._log("  Detected: CurseForge format")
            return json.loads(
                (self.temp_dir / "manifest.json").read_text(encoding="utf-8")
            )
        if (self.temp_dir / "modrinth.index.json").exists():
            self.pack_type = "modrinth"
            self._log("  Detected: Modrinth format")
            return json.loads(
                (self.temp_dir / "modrinth.index.json").read_text(encoding="utf-8")
            )
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
            loader_id: str = primary["id"]

            self._install_vanilla(mc_ver, gdir)

            parts = loader_id.split("-", 1)
            loader_kind = parts[0].lower()
            loader_ver = parts[1] if len(parts) > 1 else ""

            if loader_kind == "neoforge":
                self._install_neoforge(mc_ver, loader_ver, gdir)
                return mc_ver, "neoforge", loader_ver
            if loader_kind == "forge":
                self._install_forge(mc_ver, loader_ver, gdir)
                return mc_ver, "forge", loader_ver
            if loader_kind == "fabric":
                self._install_fabric(mc_ver, loader_ver, gdir)
                return mc_ver, "fabric", loader_ver
            if loader_kind == "quilt":
                self._install_quilt(mc_ver, loader_ver, gdir)
                return mc_ver, "quilt", loader_ver
            return mc_ver, "vanilla", ""

        if self.pack_type == "modrinth":
            deps = manifest.get("dependencies", {})
            mc_ver = deps.get("minecraft")
            if not mc_ver:
                raise Exception("No Minecraft version found in Modrinth dependencies")

            self._install_vanilla(mc_ver, gdir)

            if "fabric-loader" in deps:
                loader_ver = deps["fabric-loader"]
                self._install_fabric(mc_ver, loader_ver, gdir)
                return mc_ver, "fabric", loader_ver
            if "neoforge" in deps:
                loader_ver = deps["neoforge"]
                self._install_neoforge(mc_ver, loader_ver, gdir)
                return mc_ver, "neoforge", loader_ver
            if "forge" in deps:
                loader_ver = deps["forge"]
                self._install_forge(mc_ver, loader_ver, gdir)
                return mc_ver, "forge", loader_ver
            if "quilt-loader" in deps:
                loader_ver = deps["quilt-loader"]
                self._install_quilt(mc_ver, loader_ver, gdir)
                return mc_ver, "quilt", loader_ver
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
        total = len(files)
        if not total:
            self._log("  Không có tệp nào để tải xuống.")
            return

        self.progress.emit(0, total, "Preparing downloads...")

        timeout = aiohttp.ClientTimeout(total=180, sock_connect=30, sock_read=120)
        connector = aiohttp.TCPConnector(limit=_MAX_CONCURRENT)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks: list[asyncio.Task] = []
            for file_info in files:
                self._check_cancelled()
                if self.pack_type == "curseforge":
                    tasks.append(asyncio.create_task(self._dl_cf_mod(session, file_info)))
                else:
                    tasks.append(asyncio.create_task(self._dl_mr_mod(session, file_info)))
            self._async_tasks = tasks

            completed = 0
            failed_required = 0
            for finished in asyncio.as_completed(tasks):
                if self.isInterruptionRequested():
                    for task in tasks:
                        task.cancel()
                    raise _InstallCancelled()
                try:
                    label = await finished
                    completed += 1
                    self.progress.emit(
                        completed,
                        total,
                        f"Downloading mods... {completed} / {total} — {label}",
                    )
                except _InstallCancelled:
                    raise
                except Exception as e:
                    completed += 1
                    if isinstance(e, _OptionalDownloadFailed):
                        self._log(f"  ⚠️  Optional file skipped: {e.label}")
                        self.progress.emit(
                            completed,
                            total,
                            f"Downloading mods... {completed} / {total}",
                        )
                    else:
                        failed_required += 1
                        self.progress.emit(
                            completed,
                            total,
                            f"Downloading mods... {completed} / {total}",
                        )

            if failed_required:
                raise Exception(f"{failed_required} required file(s) failed to download")

    async def _dl_cf_mod(self, session: "aiohttp.ClientSession", file_info: dict) -> str:
        self._check_cancelled()
        required = file_info.get("required", True)
        project_id = file_info["projectID"]
        file_id = file_info["fileID"]
        label = f"project {project_id} / file {file_id}"

        try:
            meta_url = f"https://api.curseforge.com/v1/mods/{project_id}/files/{file_id}"
            async with session.get(meta_url, headers=CF_HEADERS) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise Exception(
                        f"CurseForge metadata HTTP {resp.status} for {label}: {body[:200]}"
                    )
                data = (await resp.json())["data"]
                file_name = data["fileName"]
                label = file_name
                dl_url = data.get("downloadUrl")

            if not dl_url:
                self._log(f"  ⚠ downloadUrl is null -> trying fallback endpoint: {file_name}")
                dl_url = (
                    f"https://www.curseforge.com/api/v1/mods/{project_id}/files/{file_id}/download"
                )

            self._check_cancelled()
            async with session.get(dl_url, headers=CF_HEADERS) as fr:
                if fr.status != 200:
                    raise Exception(
                        f"CurseForge download HTTP {fr.status} for {file_name}"
                    )
                content = await fr.read()

            dest = self.mods_dir / file_name
            dest.write_bytes(content)
            _verify_downloaded_file(dest, file_name)
            self._log(f"  ✔️  {file_name}")
            return file_name

        except Exception as e:
            msg = str(e)
            if not required:
                raise _OptionalDownloadFailed(label, msg) from e
            self._log(
                f"  ❌ Failed to download: {label}\n\n"
                f"Project ID: {project_id}\n"
                f"File ID: {file_id}\n\n"
                f"{msg}"
            )
            raise

    async def _dl_mr_mod(self, session: "aiohttp.ClientSession", file_info: dict) -> str:
        self._check_cancelled()
        label = file_info.get("path", "unknown")
        dl_url = file_info.get("downloads", [None])[0]
        if not dl_url:
            raise Exception(f"Modrinth download URL missing for {label}")

        try:
            dest_path = self.instance_dir / file_info["path"]
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            async with session.get(dl_url, headers=MR_HEADERS) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise Exception(
                        f"Modrinth download HTTP {resp.status} for {label}: {body[:200]}"
                    )
                content = await resp.read()

            dest_path.write_bytes(content)
            _verify_downloaded_file(dest_path, label)
            self._log(f"  ✔️  {label}")
            return label

        except Exception as e:
            self._log(f"  ❌ Modrinth download failed for {label}: {e}")
            raise

    def _download_mods_sync(self, manifest: dict):
        import requests

        self._log("⬇️  Đang tải mods (sync mode)...")
        files = manifest.get("files", [])
        self.mods_dir.mkdir(parents=True, exist_ok=True)
        total = len(files)
        if not total:
            self._log("  Không có tệp nào để tải xuống.")
            return

        self.progress.emit(0, total, "Preparing downloads...")
        failed_required = 0
        completed = 0

        for file_info in files:
            self._check_cancelled()
            try:
                if self.pack_type == "curseforge":
                    label = self._dl_cf_mod_sync(requests, file_info)
                else:
                    label = self._dl_mr_mod_sync(requests, file_info)
                completed += 1
                self.progress.emit(
                    completed,
                    total,
                    f"Downloading mods... {completed} / {total} — {label}",
                )
            except _InstallCancelled:
                raise
            except _OptionalDownloadFailed as e:
                completed += 1
                self._log(f"  ⚠️  Optional file skipped: {e.label}")
                self.progress.emit(
                    completed,
                    total,
                    f"Downloading mods... {completed} / {total}",
                )
            except Exception:
                completed += 1
                failed_required += 1
                self.progress.emit(
                    completed,
                    total,
                    f"Downloading mods... {completed} / {total}",
                )

        if failed_required:
            raise Exception(f"{failed_required} required file(s) failed to download")

    def _dl_cf_mod_sync(self, requests_mod, file_info: dict) -> str:
        required = file_info.get("required", True)
        project_id = file_info["projectID"]
        file_id = file_info["fileID"]
        label = f"project {project_id} / file {file_id}"

        try:
            meta_url = f"https://api.curseforge.com/v1/mods/{project_id}/files/{file_id}"
            resp = requests_mod.get(meta_url, headers=CF_HEADERS, timeout=30)
            if resp.status_code != 200:
                raise Exception(
                    f"CurseForge metadata HTTP {resp.status_code} for {label}: {resp.text[:200]}"
                )
            data = resp.json()["data"]
            file_name = data["fileName"]
            label = file_name
            dl_url = data.get("downloadUrl")

            if not dl_url:
                self._log(f"  ⚠ downloadUrl is null -> trying fallback endpoint: {file_name}")
                dl_url = (
                    f"https://www.curseforge.com/api/v1/mods/{project_id}/files/{file_id}/download"
                )

            self._check_cancelled()
            fr = requests_mod.get(dl_url, headers=CF_HEADERS, timeout=180)
            if fr.status_code != 200:
                raise Exception(f"CurseForge download HTTP {fr.status_code} for {file_name}")

            dest = self.mods_dir / file_name
            dest.write_bytes(fr.content)
            _verify_downloaded_file(dest, file_name)
            self._log(f"  ✔️  {file_name}")
            return file_name

        except Exception as e:
            if not required:
                raise _OptionalDownloadFailed(label, str(e)) from e
            self._log(
                f"  ❌ Failed to download: {label}\n\n"
                f"Project ID: {project_id}\n"
                f"File ID: {file_id}\n\n"
                f"{e}"
            )
            raise

    def _dl_mr_mod_sync(self, requests_mod, file_info: dict) -> str:
        label = file_info.get("path", "unknown")
        dl_url = file_info.get("downloads", [None])[0]
        if not dl_url:
            raise Exception(f"Modrinth download URL missing for {label}")

        dest = self.instance_dir / file_info["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        resp = requests_mod.get(dl_url, headers=MR_HEADERS, timeout=180)
        if resp.status_code != 200:
            raise Exception(
                f"Modrinth download HTTP {resp.status_code} for {label}: {resp.text[:200]}"
            )
        dest.write_bytes(resp.content)
        _verify_downloaded_file(dest, label)
        self._log(f"  ✔️  {label}")
        return label

    # ── Apply overrides ───────────────────────────────────────────────────────

    def _apply_overrides(self):
        self._log("🚚 Đang áp dụng ghi đè / cấu hình...")
        for ov_folder in ["overrides", "client-overrides"]:
            ov_path = self.temp_dir / ov_folder
            if not ov_path.exists():
                continue
            for item in ov_path.iterdir():
                self._check_cancelled()
                dst = self.instance_dir / item.name
                try:
                    if item.is_dir():
                        shutil.copytree(item, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dst)
                except Exception as e:
                    self._log(f"  ⚠️  Override copy error: {e}")
            self._log(f"  ✔️  Applied overrides from '{ov_folder}'")


class _OptionalDownloadFailed(Exception):
    def __init__(self, label: str, reason: str):
        self.label = label
        self.reason = reason
        super().__init__(reason)


# ═══════════════════════════════════════════════════════════════════════════════
# MODPACK TAB
# ═══════════════════════════════════════════════════════════════════════════════

class ModpackTab(QWidget):
    instance_created = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(self, mgr: MinecraftManager, inst_tab, parent=None):
        super().__init__(parent)
        self.mgr = mgr
        self.inst_tab = inst_tab
        self._worker: Optional[ModpackInstallWorker] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        h = QHBoxLayout()
        lbl = QLabel("📦 Trình Cài Đặt Modpack")
        lbl.setObjectName("header")
        h.addWidget(lbl)
        h.addStretch()
        note = QLabel("Hỗ trợ định dạng của CurseForge & Modrinth")
        note.setObjectName("subtitle")
        h.addWidget(note)
        layout.addLayout(h)

        setup_grp = QGroupBox("Tạo Instance Mới từ Modpack")
        setup_l = QVBoxLayout(setup_grp)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Tên Instance:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. ATM9 Modpack")
        name_row.addWidget(self.name_edit)
        setup_l.addLayout(name_row)

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

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("subtitle")
        layout.addWidget(self.status_lbl)

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 0)
        self.prog_bar.setVisible(False)
        layout.addWidget(self.prog_bar)

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
            if not self.name_edit.text().strip():
                self.name_edit.setText(Path(path).stem)

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

        raw_name = self.name_edit.text()
        zip_path = self.file_edit.text().strip()

        try:
            name = validate_instance_name(raw_name)
        except ValueError as e:
            QMessageBox.warning(self, "Tên không hợp lệ", str(e))
            return

        if not zip_path or not Path(zip_path).exists():
            QMessageBox.warning(self, "Bắt buộc", "Vui lòng chọn một file modpack hợp lệ.")
            return

        instance_exists = (
            name in self.inst_tab.instances
            or (INST_DIR / name).exists()
        )
        is_overwrite = False
        if instance_exists:
            reply = QMessageBox.question(
                self, "Instance đã tồn tại",
                f"Instance có tên '{name}' đã tồn tại.\n"
                "Bạn có muốn ghi đè nó? (Tất cả các tệp sẽ được thay thế)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            is_overwrite = True

        self.log_text.clear()
        self._append_log(f"📦 Bắt đầu cài đặt modpack: {name}")
        self.install_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.prog_bar.setVisible(True)
        self.prog_bar.setRange(0, 0)
        self.status_lbl.setText("Đang cài đặt...")

        self._worker = ModpackInstallWorker(
            zip_path, name, self.mgr, is_overwrite=is_overwrite
        )
        self._worker.log.connect(self._append_log)
        self._worker.log.connect(self.log)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self.cancel_btn.setEnabled(False)
            self.status_lbl.setText("Đang hủy...")
            self._worker.requestInterruption()

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
            if not (self._worker and self._worker.isInterruptionRequested()):
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
