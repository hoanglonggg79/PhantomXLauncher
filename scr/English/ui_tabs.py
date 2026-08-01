"""
PhantomX Launcher - UI components
Contains: styles, MusicPlayer, all tabs, dialogs
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from loguru import logger

try:
    import psutil
except ImportError:
    psutil = None

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton,
    QProgressBar, QTextEdit, QFileDialog, QMessageBox, QTabWidget,
    QListWidget, QListWidgetItem, QCheckBox, QGroupBox, QSplitter,
    QScrollArea, QDialog, QDialogButtonBox, QInputDialog,
    QSizePolicy, QSlider, QStatusBar,
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QSize, pyqtSlot, QUrl,
)
from PyQt6.QtGui import (
    QColor, QFont, QIcon, QTextCursor, QPixmap, QDesktopServices,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from core import (
    Instance, MinecraftManager, INST_DIR, BASE_DIR, LOG_DIR,
    MUSIC_FILE, CONFIG_FILE, KEYRING_SVC, KEYRING_AVAILABLE,
    PSUTIL_AVAILABLE, MicrosoftAuthWorker, JavaRuntimeWorker,
    ModSearchWorker, ModDownloadWorker, open_path,
)


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
    "INFO": "#cdd6f4",
    "SUCCESS": "#a6e3a1",
    "WARN": "#f9e2af",
    "ERROR": "#f38ba8",
    "DEBUG": "#6c7086",
    "GAME": "#89dceb",
}


# ═══════════════════════════════════════════════════════════════════════════════
# MUSIC PLAYER
# ═══════════════════════════════════════════════════════════════════════════════

class MusicPlayerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer()
        self._audio_out = QAudioOutput()
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
            self.play_btn.setText("⏸️")
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
            "music_muted": self.mute_btn.isChecked(),
        }

    def load_state(self, cfg: dict):
        vol = int(cfg.get("music_volume", 40))
        muted = bool(cfg.get("music_muted", False))
        self.vol_slider.setValue(vol)
        self.mute_btn.setChecked(muted)
        self._audio_out.setMuted(muted)
        self.mute_btn.setText("🔇" if muted else "🔊")


# ═══════════════════════════════════════════════════════════════════════════════
# INSTANCE TAB
# ═══════════════════════════════════════════════════════════════════════════════

class InstanceTab(QWidget):
    request_install = pyqtSignal(object)
    request_launch = pyqtSignal(object)

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
        loader_icons = {
            "vanilla": "🟩",
            "fabric": "🧵",
            "forge": "⚙️",
            "quilt": "🪡",
            "neoforge": "⚙️",
        }
        icon = loader_icons.get(inst.loader, "📦")
        item = QListWidgetItem(
            f"{icon}  {inst.name}  —  {inst.version_id}  [{inst.loader}]"
        )
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
        open_path(path)

    def delete_selected(self):
        inst = self._selected_instance()
        if not inst:
            return
        reply = QMessageBox.question(
            self,
            "Delete Instance",
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
                QMessageBox.warning(
                    self, "Duplicate", f"Instance '{inst.name}' already exists."
                )
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
        self.loader_combo.addItems(
            ["vanilla", "fabric", "forge", "quilt", "neoforge"]
        )
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
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
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
                elif self._loader in ("quilt", "neoforge"):
                    try:
                        from minecraft_launcher_lib import mod_loader
                        ml_instance = mod_loader.get_mod_loader(self._loader)
                        versions = ml_instance.get_loader_versions(
                            self._mc_ver, False
                        )
                    except Exception as e:
                        logger.error(f"Error fetching {self._loader} versions: {e}")
                        versions = []
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


# ═══════════════════════════════════════════════════════════════════════════════
# MOD TAB
# ═══════════════════════════════════════════════════════════════════════════════

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
        self.inst_label.setText(
            f"{inst.name}  [{inst.loader}  {inst.version_id}]"
        )
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
            m["filename"].replace(".disabled", "").lower() for m in self._mods
        ]
        dupes = sorted({n for n in base_names if base_names.count(n) > 1})
        if dupes:
            self.conflict_label.setText(
                f"⚠️ Possible conflict: {', '.join(dupes)}"
            )

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
            self,
            "Remove Mod",
            f"Delete {mod['filename']}?",
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
                    self,
                    "Overwrite?",
                    f"{dest.name} already exists. Overwrite?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No,
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
        open_path(str(mods_dir))


# ═══════════════════════════════════════════════════════════════════════════════
# MARKETPLACE TAB
# ═══════════════════════════════════════════════════════════════════════════════

class MarketplaceTab(QWidget):
    install_signal = pyqtSignal(str)

    def __init__(self, mgr: MinecraftManager, inst_tab, parent=None):
        super().__init__(parent)
        self.mgr = mgr
        self.inst_tab = inst_tab
        self._results: List[Dict] = []
        self._search_worker: Optional[ModSearchWorker] = None
        self._dl_worker: Optional[ModDownloadWorker] = None
        self._ver_fetcher = None
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
        self.search_edit.setPlaceholderText(
            "Search mods, modpacks, resource packs…"
        )
        self.search_edit.returnPressed.connect(self._do_search)
        sg.addWidget(self.search_edit)

        self.mc_ver_filter = QComboBox()
        self.mc_ver_filter.setEditable(True)
        self.mc_ver_filter.setPlaceholderText("MC Version (any)")
        self.mc_ver_filter.setMinimumWidth(120)
        for v in [
            "1.21.4", "1.21.1", "1.20.4", "1.20.1", "1.19.4",
            "1.19.2", "1.18.2", "1.16.5",
        ]:
            self.mc_ver_filter.addItem(v)
        self.mc_ver_filter.setCurrentIndex(-1)
        sg.addWidget(self.mc_ver_filter)

        self.loader_filter = QComboBox()
        self.loader_filter.addItems(
            ["any loader", "fabric", "forge", "quilt", "neoforge"]
        )
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
            title = mod.get("title", "Unknown")
            author = mod.get("author", "")
            downloads = mod.get("downloads", 0)
            categories = ", ".join(mod.get("categories", [])[:3])
            dl_fmt = f"{downloads:,}"
            item = QListWidgetItem(
                f"{'📦' if 'mod' in mod.get('project_type', '') else '🧩'}  {title}"
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

        if self._ver_fetcher and self._ver_fetcher.isRunning():
            self._ver_fetcher.quit()
            self._ver_fetcher.wait(500)

        class _VerFetcher(QThread):
            done = pyqtSignal(list)

            def __init__(self, mgr, pid, mc, ldr):
                super().__init__()
                self._mgr, self._pid, self._mc, self._ldr = mgr, pid, mc, ldr

            def run(self):
                self.done.emit(
                    self._mgr.get_modrinth_versions(self._pid, self._mc, self._ldr)
                )

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
            mc_vers = (
                ", ".join(v.get("game_versions", [])[-2:])
                if v.get("game_versions")
                else ""
            )
            loaders = ", ".join(v.get("loaders", []))
            label = f"{v.get('version_number', '?')}  [{mc_vers}]  {loaders}"
            self.ver_combo.addItem(label, userData=v)
        self.download_btn.setEnabled(True)

    def _download_selected(self):
        if not self.inst_combo.currentText():
            QMessageBox.warning(
                self, "No Instance", "Select an instance to install the mod to."
            )
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

        primary = next((f for f in files if f.get("primary")), files[0])
        url = primary.get("url", "")
        filename = primary.get("filename", "mod.jar")

        inst_name = self.inst_combo.currentText()
        inst = self.inst_tab.instances.get(inst_name)
        if not inst:
            QMessageBox.warning(self, "Instance Not Found", "Instance not found.")
            return

        dest = inst.mods_dir / filename
        if dest.exists():
            reply = QMessageBox.question(
                self,
                "Already Exists",
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


# ═══════════════════════════════════════════════════════════════════════════════
# LOG TAB
# ═══════════════════════════════════════════════════════════════════════════════

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
        open_dir_btn.clicked.connect(lambda: open_path(str(LOG_DIR)))
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
            msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
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
            self,
            "Save Log",
            str(LOG_DIR / "session.log"),
            "Log (*.log *.txt)",
        )
        if path:
            Path(path).write_text("\n".join(self._buffer), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS TAB
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsTab(QWidget):
    def __init__(self, mgr: MinecraftManager = None, parent=None):
        super().__init__(parent)
        self.mgr = mgr
        self.config: dict = {}
        self._java_worker: Optional[JavaRuntimeWorker] = None
        self.auth_worker: Optional[MicrosoftAuthWorker] = None
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)

        # ── Offline Account ──────────────────────────────────────────────────
        offline_grp = QGroupBox("Offline Account")
        offline_l = QVBoxLayout(offline_grp)
        row = QHBoxLayout()
        row.addWidget(QLabel("Username:"))
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("OfflinePlayer")
        row.addWidget(self.username_edit)
        offline_l.addLayout(row)
        note = QLabel("ℹ️  Offline mode only. Multiplayer on offline-mode servers only.")
        note.setObjectName("subtitle")
        offline_l.addWidget(note)
        layout.addWidget(offline_grp)

        # ── Java ─────────────────────────────────────────────────────────────
        java_grp = QGroupBox("Java")
        java_l = QVBoxLayout(java_grp)

        self.java_label = QLabel("🔍 Checking Java...")
        java_l.addWidget(self.java_label)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Custom Java path:"))
        self.java_path_edit = QLineEdit()
        self.java_path_edit.setPlaceholderText("Leave empty to use auto-detected runtime")
        row2.addWidget(self.java_path_edit)
        browse_java = QPushButton("📁")
        browse_java.setFixedWidth(40)
        browse_java.clicked.connect(self._browse_java)
        row2.addWidget(browse_java)
        java_l.addLayout(row2)

        btn_row_java = QHBoxLayout()
        self.btn_java8 = QPushButton("☕ Download Java 8")
        self.btn_java8.clicked.connect(
            lambda: self._download_java_runtime("java-runtime-legacy")
        )
        btn_row_java.addWidget(self.btn_java8)

        self.btn_java17 = QPushButton("☕ Download Java 17")
        self.btn_java17.clicked.connect(
            lambda: self._download_java_runtime("java-runtime-gamma")
        )
        btn_row_java.addWidget(self.btn_java17)

        self.btn_java21 = QPushButton("☕ Download Java 21")
        self.btn_java21.clicked.connect(
            lambda: self._download_java_runtime("java-runtime-delta")
        )
        btn_row_java.addWidget(self.btn_java21)
        java_l.addLayout(btn_row_java)

        self.java_progress = QProgressBar()
        self.java_progress.setVisible(False)
        java_l.addWidget(self.java_progress)

        self.java_status = QLabel("")
        self.java_status.setObjectName("subtitle")
        java_l.addWidget(self.java_status)

        layout.addWidget(java_grp)

        # ── Memory ───────────────────────────────────────────────────────────
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

        # ── Microsoft Account (COMING SOON) ──────────────────────────────────
        ms_grp = QGroupBox("Microsoft Account")
        ms_l = QVBoxLayout(ms_grp)

        coming_soon_lbl = QLabel(
            "⚠️  Microsoft login is <b>coming soon</b> — use Offline mode for now."
        )
        coming_soon_lbl.setStyleSheet("color: #f9e2af; font-size: 12px;")
        coming_soon_lbl.setTextFormat(Qt.TextFormat.RichText)
        ms_l.addWidget(coming_soon_lbl)

        self.account_label = QLabel("Not logged in (Offline mode)")
        self.account_label.setObjectName("subtitle")
        ms_l.addWidget(self.account_label)

        cid_row = QHBoxLayout()
        cid_row.addWidget(QLabel("Client ID:"))
        self.client_id_edit = QLineEdit()
        self.client_id_edit.setPlaceholderText(
            "Azure App Client ID — disabled (coming soon)"
        )
        self.client_id_edit.setEnabled(False)
        cid_row.addWidget(self.client_id_edit)
        ms_l.addLayout(cid_row)

        btn_row_ms = QHBoxLayout()
        self.login_btn = QPushButton("🔑 Microsoft Login (Coming Soon)")
        self.login_btn.setEnabled(False)
        self.login_btn.setToolTip("Microsoft account login is not yet available")
        btn_row_ms.addWidget(self.login_btn)

        self.logout_btn = QPushButton("🚪 Logout")
        self.logout_btn.setObjectName("danger")
        self.logout_btn.setEnabled(False)
        self.logout_btn.setToolTip("Microsoft account login is not yet available")
        btn_row_ms.addWidget(self.logout_btn)
        ms_l.addLayout(btn_row_ms)

        layout.addWidget(ms_grp)

        # ── Extra JVM Arguments ───────────────────────────────────────────────
        jvm_grp = QGroupBox("Extra JVM Arguments")
        jvm_l = QVBoxLayout(jvm_grp)
        self.jvm_edit = QLineEdit()
        self.jvm_edit.setPlaceholderText("e.g. -Dfml.readTimeout=90")
        jvm_l.addWidget(self.jvm_edit)
        layout.addWidget(jvm_grp)

        # ── Data Directory ────────────────────────────────────────────────────
        dir_grp = QGroupBox("Data Directory")
        dir_l = QHBoxLayout(dir_grp)
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setText(str(BASE_DIR))
        dir_l.addWidget(self.dir_edit)
        open_dir_btn = QPushButton("📂")
        open_dir_btn.setFixedWidth(36)
        open_dir_btn.clicked.connect(lambda: open_path(str(BASE_DIR)))
        dir_l.addWidget(open_dir_btn)
        layout.addWidget(dir_grp)

        # ── Links & Resources ────────────────────────────────────────────────
        links_grp = QGroupBox("Links & Resources")
        links_l = QHBoxLayout(links_grp)
        yt_btn = QPushButton("▶️ YouTube Channel")
        yt_btn.setToolTip("Open PhantomX YouTube channel")
        yt_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://www.youtube.com/@LongHoang-2105/")
            )
        )
        links_l.addWidget(yt_btn)
        gh_btn = QPushButton("⭐ GitHub")
        gh_btn.setToolTip("Open PhantomX GitHub repository")
        gh_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://github.com/hoanglonggg79/PhantomXLauncher")
            )
        )
        links_l.addWidget(gh_btn)
        links_l.addStretch()
        layout.addWidget(links_grp)

        # ── Misc ─────────────────────────────────────────────────────────────
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
        p, _ = QFileDialog.getOpenFileName(
            self, "Select Java executable", "", "java*(*)"
        )
        if p:
            self.java_path_edit.setText(p)

    def _auto_ram(self):
        if PSUTIL_AVAILABLE:
            total = psutil.virtual_memory().total // (1024 * 1024)
            rec = max(512, min(total - 1024, total // 2))
            self.ram_spin.setValue(rec)
        else:
            QMessageBox.information(
                self,
                "psutil missing",
                "Install psutil for auto-detect:\npip install psutil",
            )

    def load(self, cfg: dict):
        self.config = cfg
        self.username_edit.setText(cfg.get("username", ""))
        self.ram_spin.setValue(int(cfg.get("ram", 2048)))
        self.jvm_edit.setText(cfg.get("extra_jvm", ""))
        self.java_path_edit.setText(cfg.get("java_path", ""))
        self.snap_cb.setChecked(bool(cfg.get("snapshots", False)))
        self.close_launcher_cb.setChecked(bool(cfg.get("close_on_launch", False)))
        # Microsoft login is Coming Soon — always show offline status
        self.account_label.setText("Not logged in (Offline mode)")
        self.login_btn.setEnabled(False)
        self.logout_btn.setEnabled(False)

    def save(self) -> bool:
        self.config.update(self._read_ui())
        try:
            CONFIG_FILE.write_text(
                json.dumps(self.config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            if KEYRING_AVAILABLE and self.config.get("username"):
                import keyring
                keyring.set_password(
                    KEYRING_SVC, "username", self.config["username"]
                )
            logger.info("Settings saved")
            QMessageBox.information(
                self, "Saved", "✅ Settings saved successfully!"
            )
            return True
        except Exception as e:
            logger.error(f"Save settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
            return False

    def _read_ui(self) -> dict:
        return {
            "username": self.username_edit.text().strip(),
            "ram": self.ram_spin.value(),
            "extra_jvm": self.jvm_edit.text().strip(),
            "java_path": self.java_path_edit.text().strip(),
            "snapshots": self.snap_cb.isChecked(),
            "close_on_launch": self.close_launcher_cb.isChecked(),
            "microsoft_client_id": "",  # Disabled until MS login is ready
        }

    def get(self) -> dict:
        merged = dict(self.config)
        merged.update(self._read_ui())
        return merged

    def set_java_status(self, ok: bool, msg: str):
        self.java_label.setText(msg)
        self.java_label.setStyleSheet(
            f"color: {'#a6e3a1' if ok else '#f38ba8'};"
        )

    def _download_java_runtime(self, runtime_name: str):
        if not self.mgr:
            QMessageBox.warning(
                self, "Error", "MinecraftManager not initialized."
            )
            return

        self.java_progress.setVisible(True)
        self.java_progress.setValue(0)
        self.java_status.setText(f"☕ Downloading {runtime_name}...")
        self.java_status.setStyleSheet("color: #cdd6f4;")

        self.btn_java8.setEnabled(False)
        self.btn_java17.setEnabled(False)
        self.btn_java21.setEnabled(False)

        self._java_worker = JavaRuntimeWorker(self.mgr, runtime_name)
        self._java_worker.progress.connect(self._update_java_progress)
        self._java_worker.log.connect(self._update_java_log)
        self._java_worker.done.connect(self._on_java_runtime_done)
        self._java_worker.start()

    def _update_java_progress(self, current: int, total: int, label: str):
        if total > 0:
            self.java_progress.setMaximum(total)
            self.java_progress.setValue(current)
            self.java_status.setText(f"{label} ({current}/{total})")

    def _update_java_log(self, msg: str):
        self.java_status.setText(msg)

    def _on_java_runtime_done(self, java_path: Optional[str]):
        self.btn_java8.setEnabled(True)
        self.btn_java17.setEnabled(True)
        self.btn_java21.setEnabled(True)
        self.java_progress.setVisible(False)

        if java_path:
            self.java_path_edit.setText(java_path)
            self.java_status.setText("✅ Java installed successfully! Path saved.")
            self.java_status.setStyleSheet("color: #a6e3a1;")
            self.save()
        else:
            self.java_status.setText(
                "❌ Java download failed. Check the Log tab for details."
            )
            self.java_status.setStyleSheet("color: #f38ba8;")

    # ── Microsoft Auth — preserved for future use, not connected to UI yet ────

    def _start_microsoft_login(self):
        """Preserved. Will be re-enabled when Microsoft login is ready."""
        if not self.mgr:
            return
        CLIENT_ID = self.client_id_edit.text().strip()
        if not CLIENT_ID:
            QMessageBox.warning(
                self, "Error",
                "Please enter your Microsoft Azure Client ID in Settings first!",
            )
            return
        self.account_label.setText("Opening browser for login...")
        self.login_btn.setEnabled(False)
        self.logout_btn.setEnabled(False)
        self.auth_worker = MicrosoftAuthWorker(CLIENT_ID)
        self.auth_worker.login_finished.connect(self._on_login_finished)
        self.auth_worker.login_failed.connect(self._on_login_failed)
        self.auth_worker.start()

    def _on_login_finished(self, account_info: dict):
        self.config["microsoft_account"] = account_info
        self.config["username"] = account_info.get(
            "name", self.config.get("username", "")
        )
        self.username_edit.setText(self.config["username"])
        self.save()
        self._update_account_ui()
        logger.info(f"Microsoft login successful: {account_info.get('name')}")
        QMessageBox.information(
            self, "Success",
            f"Microsoft login successful!\nWelcome, {account_info.get('name')}!",
        )

    def _on_login_failed(self, err_msg: str):
        self.account_label.setText("❌ Login failed")
        self.login_btn.setEnabled(False)  # Still disabled (Coming Soon)
        self.logout_btn.setEnabled(False)
        logger.error(f"Microsoft login failed: {err_msg}")
        QMessageBox.critical(self, "Login Error", f"Login failed:\n{err_msg}")

    @pyqtSlot()
    def _update_account_ui(self):
        acc = self.config.get("microsoft_account", {})
        name = acc.get("name", acc.get("username", "Unknown"))
        self.account_label.setText(f"✅ Logged in: {name}")
        self.login_btn.setEnabled(False)
        self.logout_btn.setEnabled(False)  # Kept disabled (Coming Soon)

    def _logout_microsoft(self):
        self.config.pop("microsoft_account", None)
        self.save()
        self.account_label.setText("Not logged in (Offline mode)")
        self.login_btn.setEnabled(False)
        self.logout_btn.setEnabled(False)
