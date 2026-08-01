"""
PhantomX Launcher - Main Window
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QProgressBar,
    QMessageBox, QInputDialog, QStatusBar, QTabWidget,
)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QIcon, QDesktopServices

import minecraft_launcher_lib.microsoft_account as msa
import requests

from core import (
    APP_NAME, APP_VERSION, WATERMARK, ICON_FILE, CONFIG_FILE,
    KEYRING_SVC, KEYRING_AVAILABLE,
    Instance, Signals, MinecraftManager,
    InstallWorker, LaunchWorker, DiscordPresence, open_path,
)
from ui_tabs import (
    DARK_QSS,
    MusicPlayerWidget,
    InstanceTab,
    ModTab,
    MarketplaceTab,
    LogTab,
    SettingsTab,
)
from ui_repair import RepairTab
from ui_modpack import ModpackTab


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

        self.mgr = MinecraftManager()
        self.signals = Signals()
        self.install_worker: Optional[InstallWorker] = None
        self.launch_worker: Optional[LaunchWorker] = None
        self.active_instance: Optional[Instance] = None

        self.discord_rpc = DiscordPresence()
        threading.Thread(target=self.discord_rpc.connect, daemon=True).start()

        self._build_ui()
        self._connect_signals()
        self._load_config()
        self._check_java_async()
        self.update_rpc_launcher()
        self._check_updates()

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

        # Top bar
        topbar = QWidget()
        topbar.setStyleSheet(
            "background:#181825; border-bottom:1px solid #313244;"
        )
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(16, 8, 16, 8)

        title = QLabel("PhantomX")
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

        self.launch_btn = QPushButton("🎮 Khởi Chạy")
        self.launch_btn.setObjectName("success")
        self.launch_btn.setEnabled(True)
        self.launch_btn.clicked.connect(self._quick_launch)
        tl.addWidget(self.launch_btn)

        self.stop_btn = QPushButton("⏹ Dừng")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_game)
        tl.addWidget(self.stop_btn)

        root.addWidget(topbar)

        # Progress bar row
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

        # Tabs
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.inst_tab = InstanceTab()
        self.tabs.addTab(self.inst_tab, "📦 Quản Lý Phiên Bản")

        self.mod_tab = ModTab(self.mgr)
        self.tabs.addTab(self.mod_tab, "🧩 Mods")

        self.market_tab = MarketplaceTab(self.mgr, self.inst_tab)
        self.tabs.addTab(self.market_tab, "🛒 Chợ Mod")

        self.modpack_tab = ModpackTab(self.mgr, self.inst_tab)
        self.tabs.addTab(self.modpack_tab, "📦 Modpack")

        self.log_tab = LogTab()
        self.tabs.addTab(self.log_tab, "📋 Log")

        self.repair_tab = RepairTab(self.inst_tab)
        self.tabs.addTab(self.repair_tab, "🔧 Sửa Chữa")

        self.settings_tab = SettingsTab(self.mgr)
        self.tabs.addTab(self.settings_tab, "⚙️ Cài Đặt")

    # ── Signal wiring ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        self.signals.log.connect(lambda m, l: self.log_tab.append(m, l))
        self.signals.progress.connect(self._on_progress)
        self.signals.java_status.connect(self.settings_tab.set_java_status)
        self.settings_tab.settings_saved.connect(self._check_java_async)
        self.signals.dl_done.connect(self._on_install_done)
        self.signals.game_exited.connect(self._on_game_exited)
        self.signals.status_msg.connect(self.status_bar.showMessage)

        self.inst_tab.request_install.connect(self._install_instance)
        self.inst_tab.request_launch.connect(self._launch_instance)
        self.inst_tab.list_widget.itemSelectionChanged.connect(
            self._on_inst_selection_changed
        )

        self.market_tab.install_signal.connect(
            lambda m: self.signals.log.emit(m, "SUCCESS")
        )

        # Modpack tab: forward log to log tab, refresh instances on completion
        self.modpack_tab.log.connect(
            lambda m: self.signals.log.emit(m, "INFO")
        )
        self.modpack_tab.instance_created.connect(self._on_modpack_installed)

        # Repair tab: forward log to log tab
        self.repair_tab.repair_log.connect(
            lambda m: self.signals.log.emit(m, "INFO")
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
                import keyring
                cfg["username"] = (
                    keyring.get_password(KEYRING_SVC, "username") or ""
                )
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
        # Refresh new tabs
        try:
            self.repair_tab.refresh_instances()
        except Exception:
            pass

    def _on_modpack_installed(self, instance_name: str):
        """Called when ModpackTab finishes installing a modpack."""
        self.inst_tab.load_instances()
        self._refresh_quick_combo()
        self.signals.log.emit(
            f"✅ Modpack instance '{instance_name}' Đã được đăng ký.", "SUCCESS"
        )
        self.signals.status_msg.emit(f"✅ Modpack đã sẵn sàng: {instance_name}")

    # ── Java check ────────────────────────────────────────────────────────────
    def _check_java_async(self):
        def task():
            cfg = self.settings_tab.get()
            custom_path = cfg.get("java_path", "").strip()
            ok, msg = self.mgr.check_java(custom_path)
            self.signals.java_status.emit(ok, msg)
            self.signals.log.emit(msg, "SUCCESS" if ok else "WARN")

        threading.Thread(target=task, daemon=True).start()

    # ── Instance selection ───────────────────────────────────────────────────
    def _on_inst_selection_changed(self):
        inst = self.inst_tab._selected_instance()
        if inst:
            self.mod_tab.set_instance(inst)
            self.active_instance = inst

    def _on_progress(self, current: int, total: int, label: str = ""):
        try:
            if total and total > 0:
                self.prog_bar.setMaximum(int(total))
                self.prog_bar.setValue(int(current))
            if label:
                self.prog_label.setText(str(label))
        except Exception as e:
            logger.debug(f"Progress UI update error: {e}")

    # ── Install ───────────────────────────────────────────────────────────────
    def _install_instance(self, inst: Instance):
        if self.install_worker and self.install_worker.isRunning():
            QMessageBox.warning(
                self, "Bận", "Một quá trình cài đặt khác đang được thực hiện."
            )
            return
        self.signals.log.emit(f"⬇️  Bắt đầu cài đặt: {inst.name}", "INFO")
        self.prog_bar.setVisible(True)
        self.prog_bar.setValue(0)
        self.launch_btn.setEnabled(False)

        self.install_worker = InstallWorker(self.mgr, inst)
        self.install_worker.log.connect(
            lambda m: self.signals.log.emit(m, "INFO")
        )
        self.install_worker.prog.connect(
            lambda c, t, s: self.signals.progress.emit(c, t, s)
        )
        self.install_worker.done.connect(
            lambda ok, n: self.signals.dl_done.emit(ok, n)
        )
        self.install_worker.start()

    def _on_install_done(self, ok: bool, name: str):
        self.prog_bar.setVisible(False)
        self.launch_btn.setEnabled(True)
        self._refresh_quick_combo()
        if ok:
            self.signals.log.emit(
                f"✅ '{name}' Đã cài đặt và sẵn sàng!", "SUCCESS"
            )
            self.signals.status_msg.emit(f"✅ {name} Sẵn sàng")
        else:
            self.signals.log.emit(f"❌ Cài đặt thất bại cho '{name}'", "ERROR")
            self.signals.status_msg.emit(f"❌ Cài đặt thất bại: {name}")
            QMessageBox.critical(
                self,
                "Cài Đặt Thất Bại",
                f"Không thể cài đặt '{name}'.\nKiểm tra tab Log để biết chi tiết."
            )

    # ── Launch ────────────────────────────────────────────────────────────────
    def _get_launch_params(self) -> tuple[str, int, str, str, str, str]:
        cfg = self.settings_tab.get()
        username = cfg.get("username", "").strip()
        ram = int(cfg.get("ram", 2048))
        extra_jvm = cfg.get("extra_jvm", "").strip()
        java_path = cfg.get("java_path", "").strip()

        if not username:
            username, ok = QInputDialog.getText(
                self, "Cần tên người dùng", "Nhập tên người dùng để chơi ngoại tuyến của bạn:"
            )
            if not ok or not username.strip():
                return "", ram, extra_jvm, java_path, "", ""
            username = username.strip()

        uuid = ""
        token = ""
        acc = self.settings_tab.config.get("microsoft_account", {})
        if acc:
            try:
                client_id = self.settings_tab.config.get(
                    "microsoft_client_id", ""
                )
                if acc.get("refresh_token"):
                    try:
                        if hasattr(msa, "complete_refresh"):
                            refreshed = msa.complete_refresh(
                                client_id, acc.get("refresh_token")
                            )
                        elif hasattr(msa, "refresh"):
                            refreshed = msa.refresh(
                                client_id, acc.get("refresh_token")
                            )
                        else:
                            refreshed = None
                        if isinstance(refreshed, dict):
                            acc.update(refreshed)
                            self.settings_tab.config["microsoft_account"] = acc
                            self.settings_tab.save()
                    except Exception as e:
                        logger.debug(f"Could not refresh MS token: {e}")
                token = (
                    acc.get("access_token")
                    or acc.get("accessToken")
                    or acc.get("token")
                    or ""
                )
                uuid = (
                    acc.get("id") or acc.get("uuid") or acc.get("xuid") or ""
                )
                if not uuid and isinstance(acc.get("profile"), dict):
                    uuid = acc["profile"].get("id", "")
            except Exception as e:
                logger.debug(f"MS account processing error: {e}")

        return username, ram, extra_jvm, java_path, uuid, token

    def _quick_launch(self):
        name = self.quick_inst_combo.currentText()
        inst = self.inst_tab.instances.get(name)
        if not inst:
            QMessageBox.warning(
                self,
                "Không có phiên bản nào",
                "Tạo và cài đặt một phiên bản trước.",
            )
            return
        self._launch_instance(inst)

    def _launch_instance(self, inst: Instance):
        if self.launch_worker and self.launch_worker.isRunning():
            QMessageBox.warning(self, "Đang chạy", "Một tab game đã và đang chạy!")
            return

        username, ram, extra_jvm, java_path, uuid, token = (
            self._get_launch_params()
        )
        if not username:
            return

        if not self.mgr.is_loader_installed(inst):
            reply = QMessageBox.question(
                self,
                "Chưa được cài đặt",
                f"'{inst.name}' dường như chưa được cài đặt.\nCài đặt ngay?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._install_instance(inst)
            return

        java_ok, java_msg = self.mgr.check_java(java_path)
        if not java_ok:
            reply = QMessageBox.question(
                self,
                "Thiếu Java",
                f"{java_msg}\n\nVẫn muốn khởi động?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.signals.log.emit(
            f"🚀 Đang chạy '{inst.name}' với tên {username}…", "INFO"
        )
        self.launch_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_bar.showMessage(f"🎮 Đang chơi: {inst.name}")

        inst.last_played = datetime.now().isoformat()
        inst.play_count += 1
        inst.save()

        cfg = self.settings_tab.get()
        close_on_launch = cfg.get("close_on_launch", False)

        self.launch_worker = LaunchWorker(
            self.mgr,
            inst,
            username,
            ram,
            extra_jvm=extra_jvm,
            java_path=java_path,
            uuid=uuid,
            token=token,
        )
        self.launch_worker.log.connect(
            lambda m: self.signals.log.emit(m, "GAME")
        )
        self.launch_worker.done.connect(
            lambda rc: self.signals.game_exited.emit(rc)
        )
        self.launch_worker.start()

        try:
            self.discord_rpc.update_presence(
                state=f"Đang chơi: {inst.name}",
                details=f"Phiên bản Minecraft {inst.version_id}",
                large_image="icon",
                large_text=f"{inst.name}",
            )
        except Exception:
            pass

        if close_on_launch:
            self.hide()

    def _stop_game(self):
        if self.launch_worker:
            self.signals.log.emit("⏹ Dừng game…", "WARN")
            self.launch_worker.terminate()

    def _on_game_exited(self, rc: int):
        self.launch_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.launch_worker = None
        self.status_bar.showMessage(f"Game đã thoát (code {rc})")
        try:
            self.update_rpc_launcher()
        except Exception:
            pass
        if not self.isVisible():
            self.show()
            self.raise_()

    def update_rpc_launcher(self):
        try:
            self.discord_rpc.update_presence(
                state="Ở giao diện chính",
                details="Đang chuẩn bị chơi game",
                large_image="icon",
                large_text="PhantomX Launcher",
            )
        except Exception:
            pass

    def closeEvent(self, event):
        if self.launch_worker and self.launch_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Game đang chạy",
                "Minecraft vẫn đang chạy.\nTắt tiến trình và thoát?",
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
                json.dumps(
                    self.settings_tab.config, indent=2, ensure_ascii=False
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Auto-save on exit: {e}")

        try:
            self.discord_rpc.clear()
            self.discord_rpc.close()
        except Exception:
            pass

        logger.info("PhantomX closing")
        event.accept()

    # ── Update checker (non-blocking, soft prompt) ────────────────────────────
    def _check_updates(self):
        local_version = str(APP_VERSION).strip().lower().lstrip("v")

        def _ver_tuple(v: str):
            """Convert '1.2.3' / '1.2' / '1.2.3-beta' → (1, 2, 3)"""
            try:
                clean = v.split("-")[0].split("+")[0]
                parts = [int(x) for x in clean.split(".") if x.isdigit() or x.isnumeric()]
                while len(parts) < 3:
                    parts.append(0)
                return tuple(parts[:3])
            except Exception:
                return (0, 0, 0)

        def task():
            try:
                url = (
                    "https://raw.githubusercontent.com/hoanglonggg79/"
                    "PhantomXLauncher/refs/heads/main/version.txt"
                )
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PhantomXLauncher"
                }
                r = requests.get(url, headers=headers, timeout=6)

                if r.status_code != 200:
                    return

                remote = r.text.strip()
                if not remote:
                    return

                remote_cleaned = remote.lower().lstrip("v")

                if _ver_tuple(remote_cleaned) > _ver_tuple(local_version):
                    def show_update():
                        reply = QMessageBox.question(
                            self,
                            "⭐ Có bản cập nhật",
                            (
                                f"Đã có bản cập nhật mới: v{remote}\n"
                                f"Bạn đang sử dụng phiên bản: v{APP_VERSION}\n\n"
                                "Mở GitHub releases để tải phiên bản mới nhất?"
                            ),
                            QMessageBox.StandardButton.Yes
                            | QMessageBox.StandardButton.No,
                        )
                        if reply == QMessageBox.StandardButton.Yes:
                            QDesktopServices.openUrl(
                                QUrl(
                                    "https://github.com/hoanglonggg79/"
                                    "PhantomXLauncher/releases/latest"
                                )
                            )

                    QTimer.singleShot(0, show_update)

            except Exception as e:
                logger.debug(f"Update check failed: {e}")

        threading.Thread(target=task, daemon=True).start()
