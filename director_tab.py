import os
import sys
import json
import subprocess
import webbrowser
from typing import Optional, List, Dict, Any
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QGroupBox, QListWidget, QListWidgetItem,
    QMessageBox, QDialog, QInputDialog, QColorDialog, QFormLayout, QScrollArea, QFrame,
    QCheckBox, QTabWidget, QTabBar
)
from PyQt6.QtGui import QColor, QIcon

from director_panel import DirectorPanelWindow
import theme_manager
from debug_logger import log_debug

from streamlabs_client import get_streamlabs_client
from director_security import PasskeyManager, BouncerValidator
from soundboard_spam_guard import SoundboardSpamGuard
from typing import TYPE_CHECKING, Optional, Dict, Any
if TYPE_CHECKING:
    from webrtc_p2p import WebRTCManager

def obfuscate_str(data_str: str, key: int = 140) -> str:
    if not data_str:
        return ""
    return "".join(chr(ord(c) ^ key) for c in data_str)

def get_permissions_file_path() -> str:
    appdata_root = os.environ.get("APPDATA") or os.path.expanduser("~")
    app_folder = os.path.join(appdata_root, "StreamerCalyx")
    if not os.path.exists(app_folder):
        try:
            os.makedirs(app_folder, exist_ok=True)
        except Exception:
            pass
    return os.path.join(app_folder, "director_permissions.json")

class NoScrollComboBox(QComboBox):
    """Dropdown QComboBox that ignores mouse wheel when closed to prevent accidental scrolling."""
    def wheelEvent(self, event):
        if self.view() and self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()

    def setCurrentText(self, text: str):
        if text and self.findText(text) == -1:
            insert_idx = max(0, self.count() - 1) if self.count() > 0 else 0
            self.insertItem(insert_idx, text)
        super().setCurrentText(text)

class SceneHotkeyEditDialog(QDialog):
    """Dialog to create or edit a per-scene shortcut / hotkey toggle for the Director Panel."""
    def __init__(self, name="New Shortcut", hotkey="Ctrl+Num1", target_source="", available_sources=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Scene Shortcut")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()

        self.edit_name = QLineEdit(name)
        self.edit_name.setPlaceholderText("e.g. SandMan View, Cam 2, Meme Overlay")
        form.addRow("Button Name:", self.edit_name)

        self.edit_hotkey = QLineEdit(hotkey)
        self.edit_hotkey.setPlaceholderText("e.g. Ctrl+Num6, Ctrl+Num7, Alt+F1")
        form.addRow("Hotkey Sequence:", self.edit_hotkey)

        self.combo_source = NoScrollComboBox()
        self.combo_source.setEditable(True)
        self.combo_source.addItem("-- Pure Hotkey Only (No SLOBS Source) --", "")
        if available_sources:
            for s in available_sources:
                s_name = s if isinstance(s, str) else s.get("name", "")
                if s_name:
                    self.combo_source.addItem(f"👁️ {s_name}", s_name)
        if target_source:
            idx = -1
            for i in range(self.combo_source.count()):
                if self.combo_source.itemData(i) == target_source or self.combo_source.itemText(i).replace("👁️ ", "") == target_source:
                    idx = i
                    break
            if idx >= 0:
                self.combo_source.setCurrentIndex(idx)
            else:
                self.combo_source.setEditText(target_source)
        form.addRow("SLOBS Source (Optional):", self.combo_source)

        layout.addLayout(form)

        lbl_hint = QLabel("💡 <i>If SLOBS Source is set, clicking this button in the dock toggles visibility of that source in Streamlabs Desktop while also simulating the hotkey.</i>")
        lbl_hint.setStyleSheet("font-size: 10px; color: #a1a1aa;")
        lbl_hint.setWordWrap(True)
        layout.addWidget(lbl_hint)

        btn_box = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def get_data(self):
        name = self.edit_name.text().strip() or "Shortcut"
        hotkey = self.edit_hotkey.text().strip() or "Ctrl+Num1"
        src_raw = self.combo_source.currentData()
        if src_raw is None or src_raw == "":
            src_text = self.combo_source.currentText().replace("👁️ ", "").strip()
            if "-- Pure Hotkey" in src_text:
                target_source = ""
            else:
                target_source = src_text
        else:
            target_source = str(src_raw)
        return {
            "name": name,
            "hotkey": hotkey,
            "source": target_source
        }


class GlobalSceneHotkeyEditDialog(QDialog):
    """Dialog to create or edit a shortcut and choose which Scene it belongs to."""
    def __init__(self, scenes=None, selected_scene_idx=0, name="New Shortcut", hotkey="Ctrl+Num1", target_source="", available_sources=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Scene Shortcut")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()

        self.combo_scene = NoScrollComboBox()
        for idx, sc in enumerate(scenes or []):
            sc_name = sc.get("name", f"Scene {idx+1}")
            self.combo_scene.addItem(f"🎬 {sc_name}", idx)
        if 0 <= selected_scene_idx < self.combo_scene.count():
            self.combo_scene.setCurrentIndex(selected_scene_idx)
        form.addRow("Belongs to Scene:", self.combo_scene)

        self.edit_name = QLineEdit(name)
        self.edit_name.setPlaceholderText("e.g. SandMan View, Cam 2, Meme Overlay")
        form.addRow("Button Name:", self.edit_name)

        self.edit_hotkey = QLineEdit(hotkey)
        self.edit_hotkey.setPlaceholderText("e.g. Ctrl+Num6, Ctrl+Num7, Alt+F1")
        form.addRow("Hotkey Sequence:", self.edit_hotkey)

        self.combo_source = NoScrollComboBox()
        self.combo_source.setEditable(True)
        self.combo_source.addItem("-- Pure Hotkey Only (No SLOBS Source) --", "")
        if available_sources:
            for s in available_sources:
                s_name = s if isinstance(s, str) else s.get("name", "")
                if s_name:
                    self.combo_source.addItem(f"👁️ {s_name}", s_name)
        if target_source:
            idx = -1
            for i in range(self.combo_source.count()):
                if self.combo_source.itemData(i) == target_source or self.combo_source.itemText(i).replace("👁️ ", "") == target_source:
                    idx = i
                    break
            if idx >= 0:
                self.combo_source.setCurrentIndex(idx)
            else:
                self.combo_source.setEditText(target_source)
        form.addRow("SLOBS Source (Optional):", self.combo_source)

        layout.addLayout(form)

        lbl_hint = QLabel("💡 <i>When this scene is active on the Director Dock, this shortcut button will appear. Clicking it fires the hotkey and toggles the source.</i>")
        lbl_hint.setStyleSheet("font-size: 10px; color: #a1a1aa;")
        lbl_hint.setWordWrap(True)
        layout.addWidget(lbl_hint)

        btn_box = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def get_data(self):
        scene_idx = self.combo_scene.currentData()
        name = self.edit_name.text().strip() or "Shortcut"
        hotkey = self.edit_hotkey.text().strip() or "Ctrl+Num1"
        src_raw = self.combo_source.currentData()
        if src_raw is None or src_raw == "":
            src_text = self.combo_source.currentText().replace("👁️ ", "").strip()
            if "-- Pure Hotkey" in src_text:
                target_source = ""
            else:
                target_source = src_text
        else:
            target_source = str(src_raw)
        return scene_idx, {
            "name": name,
            "hotkey": hotkey,
            "source": target_source
        }


class SceneEditDialog(QDialog):
    """Dialog to add or modify a scene card with live Streamlabs scene selection, view toggles, scene audio channels, and per-scene hotkeys."""
    def __init__(self, name="New Scene", color_hex="#22c55e", available_scenes=None, scene_id=None,
                 audio_sources=None, faders=None, show_view_toggles=None,
                 available_audio=None, available_faders=None, hotkeys=None,
                 available_sources=None, parent=None):
        super().__init__(parent)
        if isinstance(name, dict):
            sc_data = name
            name = sc_data.get("name", "New Scene")
            color_hex = sc_data.get("color", color_hex)
            scene_id = sc_data.get("id", scene_id)
            audio_sources = sc_data.get("audio_sources", audio_sources)
            faders = sc_data.get("faders", faders)
            show_view_toggles = sc_data.get("show_view_toggles", show_view_toggles)
            hotkeys = sc_data.get("hotkeys", hotkeys)

        self.setWindowTitle("Configure Scene Card")
        self.setMinimumWidth(440)
        self.chosen_color = color_hex
        self.raw_id = scene_id or ""
        self.available_audio = available_audio or []
        self.available_faders = available_faders or []
        self.available_sources = available_sources or []
        self.hotkeys = [dict(hk) for hk in hotkeys] if hotkeys is not None else []

        s_name_str = str(name or "")
        if not self.hotkeys and (show_view_toggles or ("game" in s_name_str.lower()) or ("play" in s_name_str.lower())):
            self.hotkeys = [
                {"name": "SandMan View", "hotkey": "Ctrl+Num6", "source": "SandMan View"},
                {"name": "Legal-View", "hotkey": "Ctrl+Num7", "source": "Legal-View"}
            ]

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()

        self.combo_scenes = QComboBox()
        self.combo_scenes.addItem("-- Custom Scene Name --", "")
        sel_idx = 0
        if available_scenes:
            for sc in available_scenes:
                sc_n = sc.get("name", "")
                sc_i = sc.get("id", "")
                self.combo_scenes.addItem(f"🎬 {sc_n}", sc_i)
                if sc_n.lower() == name.lower() or (self.raw_id and sc_i == self.raw_id):
                    sel_idx = self.combo_scenes.count() - 1
        if sel_idx > 0:
            self.combo_scenes.setCurrentIndex(sel_idx)
        self.combo_scenes.currentIndexChanged.connect(self._on_scene_combo_changed)
        form.addRow("Streamlabs Scene:", self.combo_scenes)

        self.edit_name = QLineEdit(name)
        form.addRow("Display Name:", self.edit_name)

        btn_row = QHBoxLayout()
        self.lbl_color_preview = QLabel("   ")
        self.lbl_color_preview.setFixedSize(30, 24)
        self._update_color_preview()

        self.btn_pick_color = QPushButton("Choose Color...")
        self.btn_pick_color.clicked.connect(self._pick_color)
        btn_row.addWidget(self.lbl_color_preview)
        btn_row.addWidget(self.btn_pick_color)
        btn_row.addStretch()
        form.addRow("Border Color:", btn_row)
        layout.addLayout(form)

        # Scene Shortcuts & SLOBS Hotkeys (Dock Buttons)
        grp_hk = QGroupBox("Scene Shortcuts & SLOBS Hotkeys (Dock Buttons)")
        lay_hk_box = QVBoxLayout(grp_hk)
        lay_hk_box.setSpacing(4)
        self.list_scene_hotkeys = QListWidget()
        self.list_scene_hotkeys.setFixedHeight(75)
        self.list_scene_hotkeys.setStyleSheet("""
            QListWidget {
                font-size: 11px;
                border: 1px solid #27272a;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 2px 4px;
            }
        """)
        lay_hk_box.addWidget(self.list_scene_hotkeys)
        self._refresh_hotkeys_list()

        hk_btn_row = QHBoxLayout()
        hk_btn_row.setSpacing(6)
        btn_add_hk = QPushButton("➕ Add Shortcut")
        btn_add_hk.setStyleSheet("font-size: 10px; padding: 2px 6px; font-weight: 500;")
        btn_add_hk.clicked.connect(self._add_scene_hotkey)
        btn_edit_hk = QPushButton("✏️ Edit")
        btn_edit_hk.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        btn_edit_hk.clicked.connect(self._edit_scene_hotkey)
        btn_rem_hk = QPushButton("🗑️ Remove")
        btn_rem_hk.setStyleSheet("font-size: 10px; padding: 2px 6px;")
        btn_rem_hk.clicked.connect(self._remove_scene_hotkey)
        hk_btn_row.addWidget(btn_add_hk)
        hk_btn_row.addWidget(btn_edit_hk)
        hk_btn_row.addWidget(btn_rem_hk)
        hk_btn_row.addStretch()
        lay_hk_box.addLayout(hk_btn_row)
        layout.addWidget(grp_hk)

        # Scene-Aware Audio Mutes
        grp_audio = QGroupBox("Active Audio Mutes for this Scene")
        lay_audio_box = QVBoxLayout(grp_audio)
        self.audio_checkboxes = {}
        target_audios = set(audio_sources) if audio_sources is not None else None
        
        candidates = list(self.available_audio)
        if not candidates:
            candidates = ["Microphone (b1)", "Discord Audio (B2)", "Everyone (b3)", "Stopify Start & End"]
        
        grid_aud = QGridLayout()
        for idx, a_name in enumerate(candidates):
            chk = QCheckBox(a_name)
            if target_audios is not None:
                chk.setChecked(a_name in target_audios)
            else:
                is_start_brb = any(k in name.lower() for k in ["start", "brb", "break", "end", "be right"])
                if is_start_brb:
                    chk.setChecked("spotify" in a_name.lower() or "music" in a_name.lower() or "vod" in a_name.lower())
                else:
                    chk.setChecked(True)
            self.audio_checkboxes[a_name] = chk
            grid_aud.addWidget(chk, idx // 2, idx % 2)
        lay_audio_box.addLayout(grid_aud)
        layout.addWidget(grp_audio)

        # Scene-Aware Volume Faders
        grp_faders = QGroupBox("Active Volume Faders for this Scene")
        lay_fader_box = QVBoxLayout(grp_faders)
        self.fader_checkboxes = {}
        target_faders = set(faders) if faders is not None else None
        
        f_candidates = list(self.available_faders)
        if not f_candidates:
            f_candidates = ["Everyone (b3)", "VOD Playlist", "Microphone (b1)", "Discord Audio (B2)", "Alerts"]
        
        grid_fad = QGridLayout()
        for idx, f_name in enumerate(f_candidates):
            chk = QCheckBox(f_name)
            if target_faders is not None:
                chk.setChecked(f_name in target_faders)
            else:
                is_start_brb = any(k in name.lower() for k in ["start", "brb", "break", "end", "be right"])
                if is_start_brb:
                    chk.setChecked("spotify" in f_name.lower() or "music" in f_name.lower() or "vod" in f_name.lower())
                else:
                    chk.setChecked(True)
            self.fader_checkboxes[f_name] = chk
            grid_fad.addWidget(chk, idx // 2, idx % 2)
        lay_fader_box.addLayout(grid_fad)
        layout.addWidget(grp_faders)

        btn_box = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def _refresh_hotkeys_list(self):
        self.list_scene_hotkeys.clear()
        for hk in self.hotkeys:
            n = hk.get("name", "Shortcut")
            seq = hk.get("hotkey", "")
            src = hk.get("source", "")
            src_desc = f" ➔ {src}" if src else " (pure hotkey)"
            self.list_scene_hotkeys.addItem(f"👁️ {n} [{seq}]{src_desc}")

    def _add_scene_hotkey(self):
        if len(self.hotkeys) >= 4:
            QMessageBox.information(self, "Limit Reached", "A maximum of 4 shortcuts can be configured per scene.")
            return
        dlg = SceneHotkeyEditDialog(
            name=f"Shortcut {len(self.hotkeys)+1}",
            hotkey="Ctrl+Num1",
            available_sources=self.available_sources,
            parent=self
        )
        if dlg.exec():
            self.hotkeys.append(dlg.get_data())
            self._refresh_hotkeys_list()

    def _edit_scene_hotkey(self):
        row = self.list_scene_hotkeys.currentRow()
        if 0 <= row < len(self.hotkeys):
            hk = self.hotkeys[row]
            dlg = SceneHotkeyEditDialog(
                name=hk.get("name", "Shortcut"),
                hotkey=hk.get("hotkey", "Ctrl+Num1"),
                target_source=hk.get("source", ""),
                available_sources=self.available_sources,
                parent=self
            )
            if dlg.exec():
                self.hotkeys[row] = dlg.get_data()
                self._refresh_hotkeys_list()

    def _remove_scene_hotkey(self):
        row = self.list_scene_hotkeys.currentRow()
        if 0 <= row < len(self.hotkeys):
            self.hotkeys.pop(row)
            self._refresh_hotkeys_list()

    def _on_scene_combo_changed(self, idx):
        if idx > 0:
            text = self.combo_scenes.currentText().replace("🎬 ", "")
            self.edit_name.setText(text)
            self.raw_id = self.combo_scenes.currentData() or ""
            is_game = ("game" in text.lower()) or ("play" in text.lower())
            if is_game and not self.hotkeys:
                self.hotkeys = [
                    {"name": "SandMan View", "hotkey": "Ctrl+Num6", "source": "SandMan View"},
                    {"name": "Legal-View", "hotkey": "Ctrl+Num7", "source": "Legal-View"}
                ]
                self._refresh_hotkeys_list()

    def _pick_color(self):
        col = QColorDialog.getColor(QColor(self.chosen_color), self, "Select Scene Border Color")
        if col.isValid():
            self.chosen_color = col.name()
            self._update_color_preview()

    def _update_color_preview(self):
        self.lbl_color_preview.setStyleSheet(f"background-color: {self.chosen_color}; border: 1px solid #ffffff; border-radius: 4px;")

    def get_data(self):
        selected_audios = [name for name, chk in self.audio_checkboxes.items() if chk.isChecked()]
        selected_faders = [name for name, chk in self.fader_checkboxes.items() if chk.isChecked()]
        show_views = len(self.hotkeys) > 0
        return (
            self.edit_name.text().strip() or "Untitled Scene",
            self.chosen_color,
            self.raw_id,
            selected_audios,
            selected_faders,
            show_views,
            self.hotkeys
        )


class AudioEditDialog(QDialog):
    """Dialog to add or modify an audio toggle source with live Streamlabs picker."""
    def __init__(self, name="New Audio", available_sources=None, source_id=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Audio Source")
        self.setFixedSize(360, 160)
        self.raw_id = source_id or ""

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()

        self.combo_sources = QComboBox()
        self.combo_sources.addItem("-- Custom Audio Name --", "")
        sel_idx = 0
        if available_sources:
            for s in available_sources:
                s_name = s.get("name", "")
                s_id = s.get("sourceId") or s.get("id", "")
                self.combo_sources.addItem(f"🔊 {s_name}", s_id)
                if s_name.lower() == name.lower() or (self.raw_id and s_id == self.raw_id):
                    sel_idx = self.combo_sources.count() - 1
        if sel_idx > 0:
            self.combo_sources.setCurrentIndex(sel_idx)
        self.combo_sources.currentIndexChanged.connect(self._on_source_combo_changed)
        form.addRow("Streamlabs Source:", self.combo_sources)

        self.edit_name = QLineEdit(name)
        form.addRow("Display Name:", self.edit_name)
        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def _on_source_combo_changed(self, idx):
        if idx > 0:
            text = self.combo_sources.currentText().replace("🔊 ", "")
            self.edit_name.setText(text)
            self.raw_id = self.combo_sources.currentData() or ""

    def get_data(self):
        return self.edit_name.text().strip() or "Audio", self.raw_id


class DirectorTab(QWidget):
    """Stream Director Settings Configuration Tab with Master Launch Button."""
    def __init__(self, main_win=None):
        super().__init__()
        self.main_win = main_win
        self.panel_window = None

        # Data defaults
        self.conn_mode = "local"
        self.remote_host = "127.0.0.1"
        self.remote_port = "59650"
        self.api_key = ""
        self.stream_url = "https://twitch.tv/thawizanator"
        self.target_monitor_idx = 0
        self.app_mode = True
        self.scenes = [
            {"name": "Scene 1", "color": "#22c55e", "id": ""},
            {"name": "Scene 2", "color": "#0284c7", "id": ""},
            {"name": "Scene 3", "color": "#ea580c", "id": ""},
            {"name": "Scene 4", "color": "#a855f7", "id": ""},
            {"name": "Scene 5", "color": "#ef4444", "id": ""},
        ]
        self.audio_toggles = [
            {"name": "Mic", "muted": False, "id": ""},
            {"name": "Game", "muted": False, "id": ""},
            {"name": "Music", "muted": False, "id": ""},
            {"name": "Discord", "muted": False, "id": ""},
            {"name": "Alerts", "muted": False, "id": ""},
            {"name": "SFX", "muted": False, "id": ""},
        ]
        self.faders = [
            {"name": "Mic", "volume": 80},
            {"name": "Game", "volume": 75},
            {"name": "Music", "volume": 60},
            {"name": "Discord", "volume": 70},
            {"name": "Alerts", "volume": 65},
        ]
        self.fader_pool = ["Mic", "Game", "Music", "Discord", "Alerts", "SFX", "Browser", "Desktop"]

        # P2P & Security settings
        self.enable_wan_p2p = False
        self.p2p_passkey_salt = ""
        self.p2p_passkey_hash = ""
        self.p2p_passkey_raw = ""
        self.allowed_twitch_user = ""
        self.p2p_target_channel = ""
        self.p2p_client_passkey = ""
        self.p2p_my_twitch_user = ""

        # Runtime P2P host / client instances
        self.host_webrtc: Optional[WebRTCManager] = None
        self.client_webrtc: Optional[WebRTCManager] = None
        self.bouncer: Optional[BouncerValidator] = None

        # Granular permissions & streamer mode
        self.user_permissions: Dict[str, dict] = {}
        self.is_streamer_mode = False
        self.perm_scene_checkboxes: Dict[str, QCheckBox] = {}
        self.perm_mute_checkboxes: Dict[str, QCheckBox] = {}
        self.perm_vol_checkboxes: Dict[str, QCheckBox] = {}
        self._updating_perm_ui = False
        self.spam_guard = SoundboardSpamGuard(parent=self)

        # Initialize Streamlabs client & wire signals
        self.slobs_client = get_streamlabs_client()
        self.slobs_client.connected.connect(self._update_slobs_status_ui)
        self.slobs_client.disconnected.connect(self._update_slobs_status_ui)
        self.slobs_client.scene_switched.connect(self._update_slobs_status_ui)
        self.slobs_client.scene_switched.connect(self._broadcast_host_state_update)
        self.slobs_client.audio_muted_changed.connect(self._broadcast_host_state_update)
        self.slobs_client.audio_volume_changed.connect(self._broadcast_host_state_update)
        self.slobs_client.scenes_updated.connect(self._on_slobs_scenes_updated)
        self.slobs_client.audio_sources_updated.connect(self._on_slobs_audio_updated)
        self.slobs_client.source_visibility_changed.connect(self._broadcast_host_state_update)

        self._is_loading = True
        self._build_ui()
        self.load_from_settings()
        self._is_loading = False

        # Initial Streamlabs check
        if not self.slobs_client.is_connected():
            self.slobs_client.connect_client()
        self._update_slobs_status_ui()
        self._refresh_fader_combos()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        self.tabs_director = QTabWidget()
        self.tabs_director.setObjectName("directorTabs")

        # ==============================================================================
        # TAB 1: 🖥️ Connection & Display
        # ==============================================================================
        tab_conn = QWidget()
        lay_tab_conn = QVBoxLayout(tab_conn)
        lay_tab_conn.setContentsMargins(4, 4, 4, 4)
        lay_tab_conn.setSpacing(6)

        scroll_conn = QScrollArea()
        scroll_conn.setWidgetResizable(True)
        scroll_conn.setFrameShape(QFrame.Shape.NoFrame)
        scroll_conn.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_conn_content = QWidget()
        lay_conn_content = QVBoxLayout(scroll_conn_content)
        lay_conn_content.setContentsMargins(2, 2, 2, 2)
        lay_conn_content.setSpacing(8)

        # ------------------ GROUP 1: CONNECTION & DISPLAY ------------------
        grp_conn = QGroupBox("Streamlabs Connection && Target Display")
        lay_conn = QVBoxLayout(grp_conn)
        lay_conn.setSpacing(6)

        # Live Streamlabs connection status card
        self.frame_slobs_status = QFrame()
        self.frame_slobs_status.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 6px;
            }
        """)
        lay_slobs_box = QHBoxLayout(self.frame_slobs_status)
        lay_slobs_box.setContentsMargins(6, 4, 6, 4)
        lay_slobs_box.setSpacing(6)

        self.lbl_slobs_status = QLabel("Checking Streamlabs Desktop...")
        self.lbl_slobs_status.setStyleSheet("font-size: 11px;")
        self.lbl_slobs_status.setTextFormat(Qt.TextFormat.RichText)
        lay_slobs_box.addWidget(self.lbl_slobs_status, 1)

        self.btn_reconnect_slobs = QPushButton("🔄 Reconnect")
        self.btn_reconnect_slobs.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_reconnect_slobs.clicked.connect(self._manual_reconnect_slobs)
        lay_slobs_box.addWidget(self.btn_reconnect_slobs)
        lay_conn.addWidget(self.frame_slobs_status)

        # Connection Mode selection row
        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Mode:"))
        self.combo_conn_mode = QComboBox()
        self.combo_conn_mode.addItem("🖥️ Local PC (Named Pipe)", "local")
        self.combo_conn_mode.addItem("🌐 Remote LAN PC (WebSocket)", "remote")
        self.combo_conn_mode.addItem("☁️ Remote Director (P2P Internet)", "webrtc_client")
        self.combo_conn_mode.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_conn_mode.setMinimumContentsLength(16)
        self.combo_conn_mode.currentIndexChanged.connect(self._on_conn_mode_changed)
        row_mode.addWidget(self.combo_conn_mode, 1)

        self.btn_autodetect = QPushButton("⚡ Auto-Detect")
        self.btn_autodetect.setToolTip("Queries local Streamlabs Desktop on this PC to discover its API Token, port, and LAN IP.")
        self.btn_autodetect.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_autodetect.clicked.connect(self._on_autodetect_clicked)
        row_mode.addWidget(self.btn_autodetect)
        lay_conn.addLayout(row_mode)

        # Remote LAN Network parameters row (Host IP & Port)
        self.row_remote_net_widget = QWidget()
        row_remote_net = QHBoxLayout(self.row_remote_net_widget)
        row_remote_net.setContentsMargins(0, 0, 0, 0)
        row_remote_net.setSpacing(6)
        row_remote_net.addWidget(QLabel("Streamlabs Host / IP:"))
        self.edit_remote_host = QLineEdit("127.0.0.1")
        self.edit_remote_host.setPlaceholderText("e.g. 192.168.1.150 or 127.0.0.1")
        self.edit_remote_host.textChanged.connect(self._on_settings_changed)
        row_remote_net.addWidget(self.edit_remote_host, 1)

        row_remote_net.addWidget(QLabel("Port:"))
        self.edit_remote_port = QLineEdit("59650")
        self.edit_remote_port.setFixedWidth(65)
        self.edit_remote_port.setPlaceholderText("59650")
        self.edit_remote_port.textChanged.connect(self._on_settings_changed)
        row_remote_net.addWidget(self.edit_remote_port)
        lay_conn.addWidget(self.row_remote_net_widget)

        # API Token Row
        self.row_api_widget = QWidget()
        row_api = QHBoxLayout(self.row_api_widget)
        row_api.setContentsMargins(0, 0, 0, 0)
        row_api.setSpacing(6)
        row_api.addWidget(QLabel("Streamlabs API Token:"))
        self.edit_api_key = QLineEdit()
        self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_api_key.setPlaceholderText("From Streamlabs Desktop -> Settings -> Remote Control -> QR Code -> Show details")
        self.edit_api_key.textChanged.connect(self._on_settings_changed)
        row_api.addWidget(self.edit_api_key, 1)

        self.btn_toggle_key = QPushButton("👁️")
        self.btn_toggle_key.setFixedSize(28, 24)
        self.btn_toggle_key.setToolTip("Show/Hide Key")
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
        row_api.addWidget(self.btn_toggle_key)
        lay_conn.addWidget(self.row_api_widget)

        # Local Mode Informational Notice (visible when local mode is selected)
        self.lbl_local_notice = QLabel("💡 <i>Local PC Mode uses the high-speed Windows Named Pipe (\\\\.\\pipe\\slobs). Zero token or network configuration required.</i>")
        self.lbl_local_notice.setWordWrap(True)
        self.lbl_local_notice.setStyleSheet("font-size: 10px; color: #a1a1aa; padding-left: 2px;")
        lay_conn.addWidget(self.lbl_local_notice)

        # ------------------ CLIENT P2P CONNECTION CARD ------------------
        self.grp_client_p2p_widget = QFrame()
        self.grp_client_p2p_widget.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #0284c7;
                border-radius: 6px;
            }
        """)
        lay_client_p2p = QVBoxLayout(self.grp_client_p2p_widget)
        lay_client_p2p.setContentsMargins(8, 6, 8, 6)
        lay_client_p2p.setSpacing(6)

        self.lbl_client_p2p_info = QLabel("💡 <i>Connect directly to the streamer's PC over encrypted P2P (WebRTC DTLS-SRTP). Zero token or router port forwarding required.</i>")
        self.lbl_client_p2p_info.setWordWrap(True)
        self.lbl_client_p2p_info.setStyleSheet("font-size: 10px; color: #93c5fd;")
        lay_client_p2p.addWidget(self.lbl_client_p2p_info)

        # Streamer's Twitch Channel
        row_cli_ch = QHBoxLayout()
        row_cli_ch.setSpacing(6)
        row_cli_ch.addWidget(QLabel("Streamer Channel:"))
        self.edit_client_channel = QLineEdit()
        self.edit_client_channel.setPlaceholderText("e.g. thawizanator")
        self.edit_client_channel.textChanged.connect(self._on_settings_changed)
        row_cli_ch.addWidget(self.edit_client_channel, 1)
        lay_client_p2p.addLayout(row_cli_ch)

        # Client Passkey Row
        row_cli_pk = QHBoxLayout()
        row_cli_pk.setSpacing(6)
        row_cli_pk.addWidget(QLabel("Director Passkey:"))
        self.edit_client_passkey = QLineEdit()
        self.edit_client_passkey.setPlaceholderText("e.g. DIR-8824-XK9P")
        self.edit_client_passkey.setStyleSheet("font-family: Consolas, monospace; font-weight: bold;")
        self.edit_client_passkey.textChanged.connect(self._on_settings_changed)
        row_cli_pk.addWidget(self.edit_client_passkey, 1)
        lay_client_p2p.addLayout(row_cli_pk)

        # Client Twitch Username Row
        row_cli_usr = QHBoxLayout()
        row_cli_usr.setSpacing(6)
        row_cli_usr.addWidget(QLabel("My Twitch User:"))
        self.edit_client_my_user = QLineEdit()
        self.edit_client_my_user.setPlaceholderText("e.g. @cool_mod (optional)")
        self.edit_client_my_user.textChanged.connect(self._on_settings_changed)
        row_cli_usr.addWidget(self.edit_client_my_user, 1)
        lay_client_p2p.addLayout(row_cli_usr)

        # Client Connect button & status row
        row_cli_act = QHBoxLayout()
        row_cli_act.setSpacing(6)
        self.btn_client_p2p_connect = QPushButton("🔗 Connect P2P Session")
        self.btn_client_p2p_connect.setStyleSheet("font-weight: 600; font-size: 11px; padding: 3px 8px; background-color: #0284c7; color: white;")
        self.btn_client_p2p_connect.clicked.connect(self._toggle_client_p2p_session)
        row_cli_act.addWidget(self.btn_client_p2p_connect)

        self.lbl_client_p2p_status = QLabel("🔴 Disconnected")
        self.lbl_client_p2p_status.setStyleSheet("font-size: 11px; color: #ef4444;")
        row_cli_act.addWidget(self.lbl_client_p2p_status, 1)
        lay_client_p2p.addLayout(row_cli_act)

        self.grp_client_p2p_widget.setVisible(False)
        lay_conn.addWidget(self.grp_client_p2p_widget)

        row_url = QHBoxLayout()
        row_url.addWidget(QLabel("Stream Live URL:"))
        self.edit_stream_url = QLineEdit(self.stream_url)
        self.edit_stream_url.setPlaceholderText("https://twitch.tv/username")
        self.edit_stream_url.textChanged.connect(self._on_settings_changed)
        row_url.addWidget(self.edit_stream_url, 1)
        lay_conn.addLayout(row_url)

        row_mon = QHBoxLayout()
        row_mon.addWidget(QLabel("Open Panel On Display:"))
        self.combo_monitor = QComboBox()
        self.refresh_monitors_list()
        self.combo_monitor.currentIndexChanged.connect(self._on_settings_changed)
        row_mon.addWidget(self.combo_monitor, 1)
        lay_conn.addLayout(row_mon)

        self.chk_app_mode = QCheckBox("Open stream in dedicated studio window (Chromium App Mode)")
        self.chk_app_mode.setChecked(self.app_mode)
        self.chk_app_mode.setToolTip("Launches Chrome or Edge maximized in clean borderless app mode without address or tab bars.")
        self.chk_app_mode.setStyleSheet("font-size: 11px; color: #e4e4e7; margin-top: 2px;")
        self.chk_app_mode.toggled.connect(self._on_settings_changed)
        lay_conn.addWidget(self.chk_app_mode)

        lay_conn_content.addWidget(grp_conn)
        lay_conn_content.addStretch()
        scroll_conn.setWidget(scroll_conn_content)
        lay_tab_conn.addWidget(scroll_conn)
        self.tabs_director.addTab(tab_conn, "🖥️ Connection && Display")

        # ==============================================================================
        # TAB 2: 🎛️ Toggles
        # ==============================================================================
        tab_toggles = QWidget()
        lay_tab_toggles = QVBoxLayout(tab_toggles)
        lay_tab_toggles.setContentsMargins(4, 4, 4, 4)
        lay_tab_toggles.setSpacing(6)

        scroll_toggles = QScrollArea()
        scroll_toggles.setWidgetResizable(True)
        scroll_toggles.setFrameShape(QFrame.Shape.NoFrame)
        scroll_toggles.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_toggles_content = QWidget()
        lay_toggles_content = QVBoxLayout(scroll_toggles_content)
        lay_toggles_content.setContentsMargins(2, 2, 2, 2)
        lay_toggles_content.setSpacing(8)

        # ------------------ GROUP 2: SCENE TOGGLES & POOL (MAX 8) ------------------
        grp_scenes = QGroupBox("Scene Toggles & Pool (Limit: 8)")
        lay_sc = QVBoxLayout(grp_scenes)
        lay_sc.setSpacing(4)

        sc_btn_row = QHBoxLayout()
        sc_btn_row.setSpacing(4)
        self.lbl_scene_count = QLabel("Scenes Pool: (5 / 8)")
        self.lbl_scene_count.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        sc_btn_row.addWidget(self.lbl_scene_count)
        sc_btn_row.addStretch()

        self.btn_autodetect_scenes = QPushButton("📥 Auto-Detect")
        self.btn_autodetect_scenes.setStyleSheet("font-size: 11px; padding: 2px 8px; font-weight: 600;")
        self.btn_autodetect_scenes.setToolTip("Automatically import your live scenes from Streamlabs Desktop")
        self.btn_autodetect_scenes.clicked.connect(self._auto_detect_scenes)
        sc_btn_row.addWidget(self.btn_autodetect_scenes)
        lay_sc.addLayout(sc_btn_row)

        slim_list_qss = """
            QListWidget {
                font-size: 11px;
                padding: 1px;
                border: 1px solid #27272a;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 1px 4px;
                margin: 0px;
                height: 19px;
                min-height: 19px;
                border-radius: 2px;
            }
            QListWidget::item:hover {
                background-color: #27272a;
            }
            QListWidget::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
        """

        self.list_scenes = QListWidget()
        self.list_scenes.setFixedHeight(120)
        self.list_scenes.setStyleSheet(slim_list_qss)
        lay_sc.addWidget(self.list_scenes)

        sc_actions_row = QHBoxLayout()
        sc_actions_row.setSpacing(6)

        self.btn_add_scene = QPushButton("➕ Add Scene")
        self.btn_add_scene.setStyleSheet("font-size: 11px; padding: 2px 8px; font-weight: 500;")
        self.btn_add_scene.clicked.connect(self._add_scene)
        sc_actions_row.addWidget(self.btn_add_scene)

        self.btn_edit_scene = QPushButton("✏️ Edit")
        self.btn_edit_scene.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_edit_scene.clicked.connect(self._edit_scene)
        sc_actions_row.addWidget(self.btn_edit_scene)

        self.btn_rem_scene = QPushButton("🗑️ Remove")
        self.btn_rem_scene.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_rem_scene.clicked.connect(self._remove_scene)
        sc_actions_row.addWidget(self.btn_rem_scene)
        sc_actions_row.addStretch()
        lay_sc.addLayout(sc_actions_row)

        lay_toggles_content.addWidget(grp_scenes)

        # ------------------ GROUP 3: AUDIO MUTE TOGGLES (POOL UP TO 8) ------------------
        grp_audio = QGroupBox("Audio Mute / Unmute Pool (Limit: 8)")
        lay_au = QVBoxLayout(grp_audio)
        lay_au.setSpacing(4)

        au_btn_row = QHBoxLayout()
        au_btn_row.setSpacing(4)
        self.lbl_audio_count = QLabel("Audio Pool: (6 / 8)")
        self.lbl_audio_count.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        au_btn_row.addWidget(self.lbl_audio_count)
        au_btn_row.addStretch()

        self.btn_autodetect_audio = QPushButton("📥 Auto-Detect")
        self.btn_autodetect_audio.setStyleSheet("font-size: 11px; padding: 2px 8px; font-weight: 600;")
        self.btn_autodetect_audio.setToolTip("Automatically import your active audio mixer sources from Streamlabs Desktop")
        self.btn_autodetect_audio.clicked.connect(self._auto_detect_audio)
        au_btn_row.addWidget(self.btn_autodetect_audio)
        lay_au.addLayout(au_btn_row)

        self.list_audio = QListWidget()
        self.list_audio.setFixedHeight(120)
        self.list_audio.setStyleSheet(slim_list_qss)
        lay_au.addWidget(self.list_audio)

        au_actions_row = QHBoxLayout()
        au_actions_row.setSpacing(6)

        self.btn_add_audio = QPushButton("➕ Add Audio")
        self.btn_add_audio.setStyleSheet("font-size: 11px; padding: 2px 8px; font-weight: 500;")
        self.btn_add_audio.clicked.connect(self._add_audio)
        au_actions_row.addWidget(self.btn_add_audio)

        self.btn_edit_audio = QPushButton("✏️ Edit")
        self.btn_edit_audio.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_edit_audio.clicked.connect(self._edit_audio)
        au_actions_row.addWidget(self.btn_edit_audio)

        self.btn_rem_audio = QPushButton("🗑️ Remove")
        self.btn_rem_audio.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_rem_audio.clicked.connect(self._remove_audio)
        au_actions_row.addWidget(self.btn_rem_audio)
        au_actions_row.addStretch()
        lay_au.addLayout(au_actions_row)

        lay_toggles_content.addWidget(grp_audio)

        # ------------------ GROUP 4: VOLUME FADERS (5 ACTIVE SLIDERS / 8 POOL) ------------------
        grp_faders = QGroupBox("Volume Sliders (5 Active Channels)")
        lay_fd = QGridLayout(grp_faders)
        lay_fd.setHorizontalSpacing(8)
        lay_fd.setVerticalSpacing(6)
        lay_fd.setContentsMargins(8, 6, 8, 6)

        lay_fd.addWidget(QLabel("Slider 1:"), 0, 0)
        self.edit_fader1 = NoScrollComboBox()
        self.edit_fader1.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.edit_fader1.setMinimumContentsLength(6)
        self.edit_fader1.currentTextChanged.connect(self._on_settings_changed)
        self.edit_fader1.activated.connect(lambda idx: self._on_fader_combo_activated(self.edit_fader1, idx))
        lay_fd.addWidget(self.edit_fader1, 0, 1)

        lay_fd.addWidget(QLabel("Slider 2:"), 0, 2)
        self.edit_fader2 = NoScrollComboBox()
        self.edit_fader2.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.edit_fader2.setMinimumContentsLength(6)
        self.edit_fader2.currentTextChanged.connect(self._on_settings_changed)
        self.edit_fader2.activated.connect(lambda idx: self._on_fader_combo_activated(self.edit_fader2, idx))
        lay_fd.addWidget(self.edit_fader2, 0, 3)

        lay_fd.addWidget(QLabel("Slider 3:"), 1, 0)
        self.edit_fader3 = NoScrollComboBox()
        self.edit_fader3.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.edit_fader3.setMinimumContentsLength(6)
        self.edit_fader3.currentTextChanged.connect(self._on_settings_changed)
        self.edit_fader3.activated.connect(lambda idx: self._on_fader_combo_activated(self.edit_fader3, idx))
        lay_fd.addWidget(self.edit_fader3, 1, 1)

        lay_fd.addWidget(QLabel("Slider 4:"), 1, 2)
        self.edit_fader4 = NoScrollComboBox()
        self.edit_fader4.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.edit_fader4.setMinimumContentsLength(6)
        self.edit_fader4.currentTextChanged.connect(self._on_settings_changed)
        self.edit_fader4.activated.connect(lambda idx: self._on_fader_combo_activated(self.edit_fader4, idx))
        lay_fd.addWidget(self.edit_fader4, 1, 3)

        lay_fd.addWidget(QLabel("Slider 5:"), 2, 0)
        self.edit_fader5 = NoScrollComboBox()
        self.edit_fader5.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.edit_fader5.setMinimumContentsLength(6)
        self.edit_fader5.currentTextChanged.connect(self._on_settings_changed)
        self.edit_fader5.activated.connect(lambda idx: self._on_fader_combo_activated(self.edit_fader5, idx))
        lay_fd.addWidget(self.edit_fader5, 2, 1)

        lbl_fader_hint = QLabel("💡 <i>Directors can right-click any slider on the dock to swap with any authorized channel in the pool!</i>")
        lbl_fader_hint.setStyleSheet("font-size: 10px; color: #a1a1aa;")
        lbl_fader_hint.setWordWrap(True)
        lay_fd.addWidget(lbl_fader_hint, 3, 0, 1, 4)

        lay_fd.setColumnStretch(1, 1)
        lay_fd.setColumnStretch(3, 1)
        lay_toggles_content.addWidget(grp_faders)

        # ------------------ GROUP 5: SCENE SHORTCUTS & SLOBS HOTKEYS ------------------
        grp_scene_hotkeys = QGroupBox("Scene Shortcuts & SLOBS Hotkeys (Dock Buttons)")
        lay_shk = QVBoxLayout(grp_scene_hotkeys)
        lay_shk.setSpacing(4)

        self.list_all_scene_hotkeys = QListWidget()
        self.list_all_scene_hotkeys.setFixedHeight(110)
        self.list_all_scene_hotkeys.setStyleSheet(slim_list_qss)
        lay_shk.addWidget(self.list_all_scene_hotkeys)

        shk_actions_row = QHBoxLayout()
        shk_actions_row.setSpacing(6)
        self.btn_add_scene_hotkey = QPushButton("➕ Add Shortcut")
        self.btn_add_scene_hotkey.setStyleSheet("font-size: 11px; padding: 2px 8px; font-weight: 500;")
        self.btn_add_scene_hotkey.clicked.connect(self._add_global_scene_hotkey)
        shk_actions_row.addWidget(self.btn_add_scene_hotkey)

        self.btn_edit_scene_hotkey = QPushButton("✏️ Edit")
        self.btn_edit_scene_hotkey.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_edit_scene_hotkey.clicked.connect(self._edit_global_scene_hotkey)
        shk_actions_row.addWidget(self.btn_edit_scene_hotkey)

        self.btn_rem_scene_hotkey = QPushButton("🗑️ Remove")
        self.btn_rem_scene_hotkey.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_rem_scene_hotkey.clicked.connect(self._remove_global_scene_hotkey)
        shk_actions_row.addWidget(self.btn_rem_scene_hotkey)
        shk_actions_row.addStretch()
        lay_shk.addLayout(shk_actions_row)

        lbl_shk_hint = QLabel("💡 <i>Configure custom hotkeys & source toggles per scene. When switching scenes on the dock, only the shortcuts for that scene will appear!</i>")
        lbl_shk_hint.setStyleSheet("font-size: 10px; color: #a1a1aa;")
        lbl_shk_hint.setWordWrap(True)
        lay_shk.addWidget(lbl_shk_hint)

        lay_toggles_content.addWidget(grp_scene_hotkeys)

        lay_toggles_content.addStretch()
        scroll_toggles.setWidget(scroll_toggles_content)
        lay_tab_toggles.addWidget(scroll_toggles)
        self.tabs_director.addTab(tab_toggles, "🎛️ Toggles")

        # ==============================================================================
        # TAB 3: 🌐 Remote (Visible ONLY when Streamer Mode is enabled)
        # ==============================================================================
        tab_remote = QWidget()
        lay_tab_remote = QVBoxLayout(tab_remote)
        lay_tab_remote.setContentsMargins(4, 4, 4, 4)
        lay_tab_remote.setSpacing(6)

        scroll_remote = QScrollArea()
        scroll_remote.setWidgetResizable(True)
        scroll_remote.setFrameShape(QFrame.Shape.NoFrame)
        scroll_remote.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_remote_content = QWidget()
        lay_remote_content = QVBoxLayout(scroll_remote_content)
        lay_remote_content.setContentsMargins(2, 2, 2, 2)
        lay_remote_content.setSpacing(8)

        # ------------------ GATEWAY SETTINGS CARD ------------------
        self.grp_gateway = QFrame()
        self.grp_gateway.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 6px;
            }
        """)
        self.grp_host_p2p_widget = self.grp_gateway  # Compatibility alias
        lay_gateway = QVBoxLayout(self.grp_gateway)
        lay_gateway.setContentsMargins(8, 6, 8, 6)
        lay_gateway.setSpacing(6)

        self.chk_enable_wan_p2p = QCheckBox("🌐 Allow Remote Co-Host / Moderator (P2P Internet)")
        self.chk_enable_wan_p2p.setStyleSheet("font-weight: 600; font-size: 11px; color: #38bdf8;")
        self.chk_enable_wan_p2p.setToolTip("Enables direct encrypted peer-to-peer control over the Internet without port forwarding or sharing API tokens.")
        self.chk_enable_wan_p2p.toggled.connect(self._on_host_p2p_toggled)
        lay_gateway.addWidget(self.chk_enable_wan_p2p)

        self.box_host_p2p_details = QWidget()
        lay_host_details = QVBoxLayout(self.box_host_p2p_details)
        lay_host_details.setContentsMargins(0, 0, 0, 0)
        lay_host_details.setSpacing(5)

        # Passkey Row
        row_host_pk = QHBoxLayout()
        row_host_pk.setSpacing(4)
        row_host_pk.addWidget(QLabel("Passkey:"))
        self.edit_host_passkey = QLineEdit()
        self.edit_host_passkey.setReadOnly(True)
        self.edit_host_passkey.setStyleSheet("font-family: Consolas, monospace; font-weight: bold; letter-spacing: 1px; color: #22c55e;")
        row_host_pk.addWidget(self.edit_host_passkey, 1)

        self.btn_new_passkey = QPushButton("⚡ New")
        self.btn_new_passkey.setToolTip("Generate a new pairing passkey")
        self.btn_new_passkey.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_new_passkey.clicked.connect(self._generate_new_passkey)
        row_host_pk.addWidget(self.btn_new_passkey)

        self.btn_copy_passkey = QPushButton("📋 Copy")
        self.btn_copy_passkey.setToolTip("Copy passkey to clipboard")
        self.btn_copy_passkey.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_copy_passkey.clicked.connect(self._copy_passkey)
        row_host_pk.addWidget(self.btn_copy_passkey)

        self.btn_revoke_passkey = QPushButton("🚫 Revoke")
        self.btn_revoke_passkey.setToolTip("Revoke passkey and disconnect any connected remote directors")
        self.btn_revoke_passkey.setStyleSheet("font-size: 11px; padding: 2px 6px; color: #ef4444;")
        self.btn_revoke_passkey.clicked.connect(self._revoke_passkey)
        row_host_pk.addWidget(self.btn_revoke_passkey)
        lay_host_details.addLayout(row_host_pk)

        # Host Status banner
        self.lbl_host_p2p_status = QLabel("🟡 Gateway Offline")
        self.lbl_host_p2p_status.setStyleSheet("font-size: 10px; color: #a1a1aa;")
        lay_host_details.addWidget(self.lbl_host_p2p_status)

        self.box_host_p2p_details.setVisible(False)
        lay_gateway.addWidget(self.box_host_p2p_details)
        lay_remote_content.addWidget(self.grp_gateway)

        # Compatibility hidden input for edit_allowed_twitch_user
        self.edit_allowed_twitch_user = QLineEdit()
        self.edit_allowed_twitch_user.setVisible(False)

        # ------------------ PERMISSIONS MATRIX GROUP ------------------
        self.grp_permissions = QGroupBox("Co-Host Whitelist && Windows-Style Permissions Matrix")
        lay_perm = QVBoxLayout(self.grp_permissions)
        lay_perm.setSpacing(6)

        lbl_perm_hint = QLabel(
            "💡 <i>Assign granular Windows-style access rights to verified Twitch co-hosts. "
            "Select a co-host to view or customize their specific permissions.</i>"
        )
        lbl_perm_hint.setWordWrap(True)
        lbl_perm_hint.setStyleSheet("font-size: 10px; color: #a1a1aa;")
        lay_perm.addWidget(lbl_perm_hint)

        # User selection row:
        row_user = QHBoxLayout()
        row_user.setSpacing(6)
        row_user.addWidget(QLabel("Co-Host / Moderator:"))
        self.combo_cohosts = QComboBox()
        self.combo_cohosts.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_cohosts.setMinimumContentsLength(14)
        self.combo_cohosts.currentIndexChanged.connect(self._on_selected_cohost_changed)
        row_user.addWidget(self.combo_cohosts, 1)

        self.btn_add_cohost = QPushButton("➕ Add User")
        self.btn_add_cohost.setStyleSheet("font-size: 11px; padding: 2px 6px; font-weight: 600;")
        self.btn_add_cohost.clicked.connect(self._on_add_cohost_clicked)
        row_user.addWidget(self.btn_add_cohost)

        self.btn_remove_cohost = QPushButton("🗑️ Remove")
        self.btn_remove_cohost.setStyleSheet("font-size: 11px; padding: 2px 6px; color: #ef4444;")
        self.btn_remove_cohost.clicked.connect(self._on_remove_cohost_clicked)
        row_user.addWidget(self.btn_remove_cohost)
        lay_perm.addLayout(row_user)

        # Master full control checkbox
        self.chk_perm_full = QCheckBox("Grant Full Control (Allow all scenes && audio channels)")
        self.chk_perm_full.setStyleSheet("font-weight: 700; font-size: 12px; color: #22c55e; margin-top: 2px;")
        self.chk_perm_full.toggled.connect(self._on_full_control_toggled)
        lay_perm.addWidget(self.chk_perm_full)

        # Vertical scroll container for granular matrix items
        self.scroll_matrix = QScrollArea()
        self.scroll_matrix.setWidgetResizable(True)
        self.scroll_matrix.setFixedHeight(175)
        self.scroll_matrix.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_matrix.setStyleSheet("""
            QScrollArea {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 6px;
            }
        """)
        self.matrix_content = QWidget()
        self.lay_matrix_items = QVBoxLayout(self.matrix_content)
        self.lay_matrix_items.setContentsMargins(8, 6, 8, 6)
        self.lay_matrix_items.setSpacing(4)
        self.scroll_matrix.setWidget(self.matrix_content)
        lay_perm.addWidget(self.scroll_matrix)

        lay_remote_content.addWidget(self.grp_permissions)
        lay_remote_content.addStretch()

        scroll_remote.setWidget(scroll_remote_content)
        lay_tab_remote.addWidget(scroll_remote)
        self.tabs_director.addTab(tab_remote, "🌐 Remote")

        main_layout.addWidget(self.tabs_director, 1)

        # ------------------ MASTER LAUNCH / CLOSE BUTTON ------------------
        launch_bar = QHBoxLayout()
        launch_bar.setSpacing(8)

        self.btn_launch_panel = QPushButton("🚀 Launch Director Panel")
        self.btn_launch_panel.setObjectName("btnLaunchDirector")
        self.btn_launch_panel.setFixedHeight(36)
        self.btn_launch_panel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_launch_button_state(is_open=False)
        self.btn_launch_panel.clicked.connect(self.toggle_director_panel)
        launch_bar.addWidget(self.btn_launch_panel, 3)

        self.btn_push_sync = QPushButton("📡 Push Sync to Directors")
        self.btn_push_sync.setFixedHeight(36)
        self.btn_push_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_push_sync.setToolTip("Immediately broadcast current scenes, audio toggles, and volume layout to all connected Remote Directors")
        self.btn_push_sync.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                border: 1px solid #0369a1;
                border-radius: 6px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)
        self.btn_push_sync.clicked.connect(self.push_sync_to_directors)
        launch_bar.addWidget(self.btn_push_sync, 2)

        main_layout.addLayout(launch_bar)

        self._on_conn_mode_changed()

    def refresh_monitors_list(self):
        self.combo_monitor.blockSignals(True)
        self.combo_monitor.clear()
        screens = QApplication.screens()
        for i, s in enumerate(screens):
            g = s.geometry()
            name = s.name() or f"Display #{i+1}"
            self.combo_monitor.addItem(f"Monitor #{i+1}: {g.width()}x{g.height()} ({name})", i)
        if 0 <= self.target_monitor_idx < len(screens):
            self.combo_monitor.setCurrentIndex(self.target_monitor_idx)
        self.combo_monitor.blockSignals(False)

    def _toggle_key_visibility(self):
        if self.edit_api_key.echoMode() == QLineEdit.EchoMode.Password:
            self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_key.setText("🔒")
        else:
            self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_key.setText("👁️")

    def _refresh_scene_list_ui(self):
        self.list_scenes.clear()
        for i, s in enumerate(self.scenes):
            it = QListWidgetItem(f"[{i+1}] {s['name']}  (Border: {s['color']})")
            it.setSizeHint(QSize(0, 19))
            self.list_scenes.addItem(it)
        count = len(self.scenes)
        self.lbl_scene_count.setText(f"Scenes Pool: ({count} / 8)")
        self.btn_add_scene.setEnabled(count < 8)
        if hasattr(self, "lay_matrix_items"):
            self._refresh_permissions_matrix_items()
        self._refresh_all_scene_hotkeys_ui()

    def _refresh_all_scene_hotkeys_ui(self):
        if not hasattr(self, "list_all_scene_hotkeys"):
            return
        self.list_all_scene_hotkeys.clear()
        for s_idx, sc in enumerate(self.scenes):
            sc_name = sc.get("name", f"Scene {s_idx+1}")
            hotkeys = sc.get("hotkeys", [])
            for hk_idx, hk in enumerate(hotkeys):
                n = hk.get("name", "Shortcut")
                seq = hk.get("hotkey", "")
                src = hk.get("source", "")
                src_desc = f" ➔ {src}" if src else " (pure hotkey)"
                item = QListWidgetItem(f"[🎬 {sc_name}] 👁️ {n} [{seq}]{src_desc}")
                item.setData(Qt.ItemDataRole.UserRole, (s_idx, hk_idx))
                self.list_all_scene_hotkeys.addItem(item)

    def _add_global_scene_hotkey(self):
        if not self.scenes:
            QMessageBox.information(self, "No Scenes", "Please configure at least one scene before adding shortcuts.")
            return
        avail_src = [it.get("name") for it in (self.slobs_client.get_cached_active_scene_items() if self.slobs_client else []) if it.get("name")]
        dlg = GlobalSceneHotkeyEditDialog(
            scenes=self.scenes,
            selected_scene_idx=0,
            available_sources=avail_src,
            parent=self
        )
        if dlg.exec():
            s_idx, hk_data = dlg.get_data()
            if 0 <= s_idx < len(self.scenes):
                if "hotkeys" not in self.scenes[s_idx]:
                    self.scenes[s_idx]["hotkeys"] = []
                if len(self.scenes[s_idx]["hotkeys"]) >= 4:
                    QMessageBox.information(self, "Limit Reached", f"A maximum of 4 shortcuts can be configured for {self.scenes[s_idx].get('name')}.")
                    return
                self.scenes[s_idx]["hotkeys"].append(hk_data)
                self.scenes[s_idx]["show_view_toggles"] = True
                self._refresh_all_scene_hotkeys_ui()
                self._on_settings_changed()
                if self.is_panel_open():
                    self.panel_window.load_configuration(
                        self.scenes, 
                        self._get_live_audio_toggles(), 
                        self._get_fader_data(), 
                        permissions=getattr(self, "_cached_client_permissions", None),
                        pool_scenes=self.scenes,
                        pool_audio=self._get_live_audio_toggles(),
                        pool_faders=self._get_active_fader_pool()
                    )

    def _edit_global_scene_hotkey(self):
        item = self.list_all_scene_hotkeys.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        s_idx, hk_idx = data
        if 0 <= s_idx < len(self.scenes) and 0 <= hk_idx < len(self.scenes[s_idx].get("hotkeys", [])):
            hk = self.scenes[s_idx]["hotkeys"][hk_idx]
            avail_src = [it.get("name") for it in (self.slobs_client.get_cached_active_scene_items() if self.slobs_client else []) if it.get("name")]
            dlg = GlobalSceneHotkeyEditDialog(
                scenes=self.scenes,
                selected_scene_idx=s_idx,
                name=hk.get("name", "Shortcut"),
                hotkey=hk.get("hotkey", "Ctrl+Num1"),
                target_source=hk.get("source", ""),
                available_sources=avail_src,
                parent=self
            )
            if dlg.exec():
                new_s_idx, new_hk_data = dlg.get_data()
                if new_s_idx == s_idx:
                    self.scenes[s_idx]["hotkeys"][hk_idx] = new_hk_data
                else:
                    self.scenes[s_idx]["hotkeys"].pop(hk_idx)
                    if "hotkeys" not in self.scenes[new_s_idx]:
                        self.scenes[new_s_idx]["hotkeys"] = []
                    self.scenes[new_s_idx]["hotkeys"].append(new_hk_data)
                    self.scenes[new_s_idx]["show_view_toggles"] = True
                self._refresh_all_scene_hotkeys_ui()
                self._on_settings_changed()
                if self.is_panel_open():
                    self.panel_window.load_configuration(
                        self.scenes, 
                        self._get_live_audio_toggles(), 
                        self._get_fader_data(), 
                        permissions=getattr(self, "_cached_client_permissions", None),
                        pool_scenes=self.scenes,
                        pool_audio=self._get_live_audio_toggles(),
                        pool_faders=self._get_active_fader_pool()
                    )

    def _remove_global_scene_hotkey(self):
        item = self.list_all_scene_hotkeys.currentItem()
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        s_idx, hk_idx = data
        if 0 <= s_idx < len(self.scenes) and 0 <= hk_idx < len(self.scenes[s_idx].get("hotkeys", [])):
            self.scenes[s_idx]["hotkeys"].pop(hk_idx)
            self._refresh_all_scene_hotkeys_ui()
            self._on_settings_changed()
            if self.is_panel_open():
                self.panel_window.load_configuration(
                    self.scenes, 
                    self._get_live_audio_toggles(), 
                    self._get_fader_data(), 
                    permissions=getattr(self, "_cached_client_permissions", None),
                    pool_scenes=self.scenes,
                    pool_audio=self._get_live_audio_toggles(),
                    pool_faders=self._get_active_fader_pool()
                )

    def _refresh_audio_list_ui(self):
        self.list_audio.clear()
        for i, a in enumerate(self.audio_toggles):
            it = QListWidgetItem(f"[{i+1}] {a['name']}")
            it.setSizeHint(QSize(0, 19))
            self.list_audio.addItem(it)
        count = len(self.audio_toggles)
        self.lbl_audio_count.setText(f"Audio Pool: ({count} / 8)")
        self.btn_add_audio.setEnabled(count < 8)
        if hasattr(self, "lay_matrix_items"):
            self._refresh_permissions_matrix_items()

    def set_streamer_mode(self, enabled: bool):
        self.is_streamer_mode = bool(enabled)
        if hasattr(self, "tabs_director") and self.tabs_director:
            visible = self.is_streamer_mode and getattr(self, "conn_mode", "local") != "webrtc_client"
            self.tabs_director.setTabVisible(2, visible)
            if not visible and self.tabs_director.currentIndex() == 2:
                self.tabs_director.setCurrentIndex(0)

    def _sync_permissions_file(self):
        try:
            app_path = get_permissions_file_path()
            with open(app_path, "w", encoding="utf-8") as f:
                json.dump(self.user_permissions, f, indent=4)
        except Exception as e:
            log_debug("DIRECTOR", f"Could not sync APPDATA director_permissions.json: {e}")
        try:
            local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "director_permissions.json")
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(self.user_permissions, f, indent=4)
        except Exception:
            pass

    def _load_permissions_file(self) -> dict:
        for path in [
            get_permissions_file_path(),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "director_permissions.json")
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            return data
                except Exception as e:
                    log_debug("DIRECTOR", f"Error reading permissions file {path}: {e}")
        return {}

    def _refresh_cohosts_combo(self):
        if not hasattr(self, "combo_cohosts"):
            return
        cur_text = self.combo_cohosts.currentText()
        self.combo_cohosts.blockSignals(True)
        self.combo_cohosts.clear()
        users = sorted(self.user_permissions.keys())
        if users:
            for u in users:
                self.combo_cohosts.addItem(f"@{u}", u)
            if cur_text and self.combo_cohosts.findText(cur_text) >= 0:
                self.combo_cohosts.setCurrentText(cur_text)
            else:
                self.combo_cohosts.setCurrentIndex(0)
        else:
            self.combo_cohosts.addItem("(No Co-Hosts Added)", "")
        self.combo_cohosts.blockSignals(False)
        self._load_selected_cohost_permissions()

    def _get_current_selected_cohost(self) -> str:
        if not hasattr(self, "combo_cohosts"):
            return ""
        data = self.combo_cohosts.currentData()
        if data:
            return str(data).strip().lower().lstrip("@")
        txt = self.combo_cohosts.currentText().strip().lower().lstrip("@")
        if txt and not txt.startswith("("):
            return txt
        return ""

    def _on_selected_cohost_changed(self):
        user = self._get_current_selected_cohost()
        if hasattr(self, "edit_allowed_twitch_user"):
            self.edit_allowed_twitch_user.setText(user)
        self._load_selected_cohost_permissions()

    def _on_add_cohost_clicked(self):
        text, ok = QInputDialog.getText(
            self,
            "Add Authorized Co-Host",
            "Enter Twitch username of the moderator / co-host (without @):"
        )
        if ok and text.strip():
            clean_user = text.strip().lower().lstrip("@")
            if not clean_user:
                return
            if clean_user in self.user_permissions:
                QMessageBox.information(self, "Already Exists", f"Co-host @{clean_user} is already in the permissions list.")
                idx = self.combo_cohosts.findText(f"@{clean_user}")
                if idx >= 0:
                    self.combo_cohosts.setCurrentIndex(idx)
                return

            # Default profile grants Full Control and all current scenes/audio
            self.user_permissions[clean_user] = {
                "full_control": True,
                "allowed_scenes": [s.get("name", "") for s in self.scenes if s.get("name")],
                "allowed_audio_mutes": [a.get("name", "") for a in self.audio_toggles if a.get("name")],
                "allowed_audio_volume": [chk_name for chk_name in getattr(self, "perm_vol_checkboxes", {}).keys()] or self._get_active_fader_pool()
            }
            self._refresh_cohosts_combo()
            idx = self.combo_cohosts.findText(f"@{clean_user}")
            if idx >= 0:
                self.combo_cohosts.setCurrentIndex(idx)
            self._sync_permissions_file()
            if self.bouncer:
                self.bouncer.set_user_permissions(self.user_permissions)
            self._on_settings_changed()

    def _on_remove_cohost_clicked(self):
        user = self._get_current_selected_cohost()
        if not user or user not in self.user_permissions:
            return
        res = QMessageBox.question(
            self,
            "Remove Co-Host",
            f"Are you sure you want to remove @{user} from the co-host permissions whitelist?\n\n"
            "They will immediately lose remote control access to your stream.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.user_permissions.pop(user, None)
            self._refresh_cohosts_combo()
            self._sync_permissions_file()
            if self.bouncer:
                self.bouncer.set_user_permissions(self.user_permissions)
            self._on_settings_changed()

    def _get_active_fader_pool(self) -> List[str]:
        pool = []
        for idx in range(1, 6):
            attr = getattr(self, f"edit_fader{idx}", None)
            if attr:
                n = attr.currentText().strip()
                if n and n != "➕ Custom Source Name..." and n not in pool:
                    pool.append(n)
        for f in getattr(self, "faders", []):
            fn = f.get("name", "").strip()
            if fn and fn not in pool:
                pool.append(fn)
        for p in getattr(self, "fader_pool", []):
            if p and p not in pool:
                pool.append(p)
        for a in getattr(self, "audio_toggles", []):
            an = a.get("name", "").strip()
            if an and an not in pool:
                pool.append(an)
        if hasattr(self, "slobs_client") and self.slobs_client:
            for s in self.slobs_client.get_cached_audio_sources():
                sn = s.get("name", "").strip()
                if sn and sn not in pool:
                    pool.append(sn)
        fallback = ["Mic", "Game", "Music", "Discord", "Alerts", "SFX", "Browser", "Desktop"]
        for fb in fallback:
            if fb not in pool:
                pool.append(fb)
        return pool[:8]

    def _refresh_permissions_matrix_items(self):
        if not hasattr(self, "lay_matrix_items"):
            return

        while self.lay_matrix_items.count() > 0:
            item = self.lay_matrix_items.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self.perm_scene_checkboxes.clear()
        self.perm_mute_checkboxes.clear()
        self.perm_vol_checkboxes.clear()

        # 1. SCENE SWITCHING PERMISSIONS
        lbl_sec_scenes = QLabel("🎬 Scene Switching Permissions (Pool)")
        lbl_sec_scenes.setStyleSheet("color: #a855f7; font-weight: bold; font-size: 11px; padding-top: 2px;")
        self.lay_matrix_items.addWidget(lbl_sec_scenes)

        if not self.scenes:
            lbl_empty_sc = QLabel("   <i>No scenes configured</i>")
            lbl_empty_sc.setStyleSheet("color: #71717a; font-size: 10px;")
            self.lay_matrix_items.addWidget(lbl_empty_sc)
        else:
            for s in self.scenes:
                s_name = s.get("name", "Untitled Scene")
                chk = QCheckBox(f"Allow switching to: {s_name}")
                chk.setStyleSheet("margin-left: 14px; font-size: 11px;")
                chk.toggled.connect(self._on_granular_perm_changed)
                self.lay_matrix_items.addWidget(chk)
                self.perm_scene_checkboxes[s_name] = chk

        # 2. AUDIO MUTE PERMISSIONS
        lbl_sec_mutes = QLabel("🔇 Audio Mute Permissions (Pool)")
        lbl_sec_mutes.setStyleSheet("color: #0284c7; font-weight: bold; font-size: 11px; padding-top: 6px;")
        self.lay_matrix_items.addWidget(lbl_sec_mutes)

        if not self.audio_toggles:
            lbl_empty_au = QLabel("   <i>No audio toggles configured</i>")
            lbl_empty_au.setStyleSheet("color: #71717a; font-size: 10px;")
            self.lay_matrix_items.addWidget(lbl_empty_au)
        else:
            for a in self.audio_toggles:
                a_name = a.get("name", "Audio Source")
                chk = QCheckBox(f"Allow muting: {a_name}")
                chk.setStyleSheet("margin-left: 14px; font-size: 11px;")
                chk.toggled.connect(self._on_granular_perm_changed)
                self.lay_matrix_items.addWidget(chk)
                self.perm_mute_checkboxes[a_name] = chk

        # 3. VOLUME SLIDER PERMISSIONS (Full 8-item Pool)
        lbl_sec_vol = QLabel("🎚️ Volume Slider Permissions (Pool)")
        lbl_sec_vol.setStyleSheet("color: #22c55e; font-weight: bold; font-size: 11px; padding-top: 6px;")
        self.lay_matrix_items.addWidget(lbl_sec_vol)

        pool_vols = self._get_active_fader_pool()
        for idx, f_name in enumerate(pool_vols):
            slot_info = f" (Slider {idx+1})" if idx < 5 else ""
            chk = QCheckBox(f"Allow channel: {f_name}{slot_info}")
            chk.setStyleSheet("margin-left: 14px; font-size: 11px;")
            chk.toggled.connect(self._on_granular_perm_changed)
            self.lay_matrix_items.addWidget(chk)
            self.perm_vol_checkboxes[f_name] = chk

        # 4. SOUNDBOARD PERMISSIONS
        lbl_sec_sound = QLabel("🔊 Soundboard Permissions")
        lbl_sec_sound.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px; padding-top: 6px;")
        self.lay_matrix_items.addWidget(lbl_sec_sound)

        self.chk_perm_soundboard = QCheckBox("Allow Soundboard Triggering")
        self.chk_perm_soundboard.setStyleSheet("margin-left: 14px; font-size: 11px;")
        self.chk_perm_soundboard.toggled.connect(self._on_granular_perm_changed)
        self.lay_matrix_items.addWidget(self.chk_perm_soundboard)

        self.lay_matrix_items.addStretch()
        self._load_selected_cohost_permissions()

    def _load_selected_cohost_permissions(self):
        user = self._get_current_selected_cohost()
        has_user = bool(user and user in self.user_permissions)

        if hasattr(self, "chk_perm_full"):
            self.chk_perm_full.setEnabled(has_user)
        if hasattr(self, "btn_remove_cohost"):
            self.btn_remove_cohost.setEnabled(has_user)

        if not has_user:
            self._updating_perm_ui = True
            if hasattr(self, "chk_perm_full"):
                self.chk_perm_full.setChecked(False)
            for chk in self.perm_scene_checkboxes.values():
                chk.setChecked(False)
                chk.setEnabled(False)
            for chk in self.perm_mute_checkboxes.values():
                chk.setChecked(False)
                chk.setEnabled(False)
            for chk in self.perm_vol_checkboxes.values():
                chk.setChecked(False)
                chk.setEnabled(False)
            if hasattr(self, "chk_perm_soundboard"):
                self.chk_perm_soundboard.setChecked(False)
                self.chk_perm_soundboard.setEnabled(False)
            self._updating_perm_ui = False
            return

        perm = self.user_permissions.get(user, {})
        is_full = perm.get("full_control", True)
        allowed_scenes = perm.get("allowed_scenes", [])
        allowed_mutes = perm.get("allowed_audio_mutes", [])
        allowed_vols = perm.get("allowed_audio_volume", [])

        self._updating_perm_ui = True
        if hasattr(self, "chk_perm_full"):
            self.chk_perm_full.setChecked(is_full)

        for s_name, chk in self.perm_scene_checkboxes.items():
            chk.setChecked(is_full or (s_name in allowed_scenes))
            chk.setEnabled(not is_full)
            chk.setStyleSheet(
                "margin-left: 14px; font-size: 11px; color: #a1a1aa;" if is_full
                else "margin-left: 14px; font-size: 11px; color: #efeff1;"
            )

        for a_name, chk in self.perm_mute_checkboxes.items():
            chk.setChecked(is_full or (a_name in allowed_mutes))
            chk.setEnabled(not is_full)
            chk.setStyleSheet(
                "margin-left: 14px; font-size: 11px; color: #a1a1aa;" if is_full
                else "margin-left: 14px; font-size: 11px; color: #efeff1;"
            )

        for f_name, chk in self.perm_vol_checkboxes.items():
            chk.setChecked(is_full or (f_name in allowed_vols))
            chk.setEnabled(not is_full)
            chk.setStyleSheet(
                "margin-left: 14px; font-size: 11px; color: #a1a1aa;" if is_full
                else "margin-left: 14px; font-size: 11px; color: #efeff1;"
            )

        if hasattr(self, "chk_perm_soundboard"):
            self.chk_perm_soundboard.setChecked(is_full or perm.get("allow_soundboard", True))
            self.chk_perm_soundboard.setEnabled(not is_full)
            self.chk_perm_soundboard.setStyleSheet(
                "margin-left: 14px; font-size: 11px; color: #a1a1aa;" if is_full
                else "margin-left: 14px; font-size: 11px; color: #efeff1;"
            )

        self._updating_perm_ui = False

    def _on_full_control_toggled(self, checked: bool):
        if self._updating_perm_ui:
            return
        user = self._get_current_selected_cohost()
        if not user or user not in self.user_permissions:
            return

        self.user_permissions[user]["full_control"] = checked
        if not checked:
            self.user_permissions[user]["allowed_scenes"] = [
                s for s, chk in self.perm_scene_checkboxes.items() if chk.isChecked()
            ]
            self.user_permissions[user]["allowed_audio_mutes"] = [
                a for a, chk in self.perm_mute_checkboxes.items() if chk.isChecked()
            ]
            self.user_permissions[user]["allowed_audio_volume"] = [
                v for v, chk in self.perm_vol_checkboxes.items() if chk.isChecked()
            ]
            if hasattr(self, "chk_perm_soundboard"):
                self.user_permissions[user]["allow_soundboard"] = self.chk_perm_soundboard.isChecked()
        else:
            self._updating_perm_ui = True
            for chk in self.perm_scene_checkboxes.values():
                chk.setChecked(True)
            for chk in self.perm_mute_checkboxes.values():
                chk.setChecked(True)
            for chk in self.perm_vol_checkboxes.values():
                chk.setChecked(True)
            if hasattr(self, "chk_perm_soundboard"):
                self.chk_perm_soundboard.setChecked(True)
            self._updating_perm_ui = False
            self.user_permissions[user]["allowed_scenes"] = list(self.perm_scene_checkboxes.keys())
            self.user_permissions[user]["allowed_audio_mutes"] = list(self.perm_mute_checkboxes.keys())
            self.user_permissions[user]["allowed_audio_volume"] = list(self.perm_vol_checkboxes.keys())
            self.user_permissions[user]["allow_soundboard"] = True

        self._load_selected_cohost_permissions()
        self._sync_permissions_file()
        if self.bouncer:
            self.bouncer.set_user_permissions(self.user_permissions)
        self._on_settings_changed()
        self._broadcast_host_state_update()

    def _on_granular_perm_changed(self):
        if self._updating_perm_ui:
            return
        user = self._get_current_selected_cohost()
        if not user or user not in self.user_permissions:
            return

        allowed_sc = [s for s, chk in self.perm_scene_checkboxes.items() if chk.isChecked()]
        allowed_mu = [a for a, chk in self.perm_mute_checkboxes.items() if chk.isChecked()]
        allowed_vo = [v for v, chk in self.perm_vol_checkboxes.items() if chk.isChecked()]
        allow_sb = self.chk_perm_soundboard.isChecked() if hasattr(self, "chk_perm_soundboard") else True

        self.user_permissions[user]["allowed_scenes"] = allowed_sc
        self.user_permissions[user]["allowed_audio_mutes"] = allowed_mu
        self.user_permissions[user]["allowed_audio_volume"] = allowed_vo
        self.user_permissions[user]["allow_soundboard"] = allow_sb

        all_scenes_checked = (len(allowed_sc) == len(self.perm_scene_checkboxes)) if self.perm_scene_checkboxes else True
        all_mutes_checked = (len(allowed_mu) == len(self.perm_mute_checkboxes)) if self.perm_mute_checkboxes else True
        all_vols_checked = (len(allowed_vo) == len(self.perm_vol_checkboxes)) if self.perm_vol_checkboxes else True

        if not (all_scenes_checked and all_mutes_checked and all_vols_checked and allow_sb):
            self.user_permissions[user]["full_control"] = False
            self._updating_perm_ui = True
            if hasattr(self, "chk_perm_full"):
                self.chk_perm_full.setChecked(False)
            self._updating_perm_ui = False
        else:
            self.user_permissions[user]["full_control"] = True
            self._updating_perm_ui = True
            if hasattr(self, "chk_perm_full"):
                self.chk_perm_full.setChecked(True)
            self._updating_perm_ui = False

        self._sync_permissions_file()
        if self.bouncer:
            self.bouncer.set_user_permissions(self.user_permissions)
        self._on_settings_changed()
        self._broadcast_host_state_update()

    def _on_conn_mode_changed(self):
        mode = self.combo_conn_mode.currentData() if hasattr(self, "combo_conn_mode") else "local"
        self.conn_mode = mode

        is_remote_lan = (mode == "remote")
        is_webrtc_client = (mode == "webrtc_client")
        is_local = (mode == "local")

        self.row_remote_net_widget.setVisible(is_remote_lan)
        self.row_api_widget.setVisible(is_remote_lan)
        self.lbl_local_notice.setVisible(is_local)
        self.btn_autodetect.setVisible(not is_webrtc_client)

        if hasattr(self, "grp_host_p2p_widget"):
            self.grp_host_p2p_widget.setVisible(not is_webrtc_client)
        if hasattr(self, "grp_client_p2p_widget"):
            self.grp_client_p2p_widget.setVisible(is_webrtc_client)

        # Update button labels and tooltips based on mode
        if hasattr(self, "btn_reconnect_slobs"):
            if is_webrtc_client:
                self.btn_reconnect_slobs.setText("🔗 Connect P2P")
                self.btn_reconnect_slobs.setToolTip("Connect or reconnect P2P session to the streamer")
            else:
                self.btn_reconnect_slobs.setText("🔄 Reconnect")
                self.btn_reconnect_slobs.setToolTip("Reconnect to Streamlabs Desktop")

        if hasattr(self, "btn_push_sync"):
            if is_webrtc_client:
                self.btn_push_sync.setText("🔄 Sync with Streamer")
                self.btn_push_sync.setToolTip("Pull latest scenes, audio toggles, and volume layout from the streamer")
            else:
                self.btn_push_sync.setText("📡 Push Sync to Directors")
                self.btn_push_sync.setToolTip("Immediately broadcast current scenes, audio toggles, and volume layout to all connected Remote Directors")

        self.set_streamer_mode(self.is_streamer_mode)
        self._update_slobs_status_ui()
        self._on_settings_changed()

    def _on_autodetect_clicked(self):
        detected = self.slobs_client.auto_detect_local_settings()
        if detected:
            token = detected.get("token", "")
            port = detected.get("port", 59650)
            local_ip = detected.get("local_ip", "127.0.0.1")

            self.edit_remote_host.setText(local_ip)
            self.edit_remote_port.setText(str(port))
            self.edit_api_key.setText(token)
            self._on_settings_changed()

            QMessageBox.information(
                self,
                "Streamlabs Auto-Detected",
                f"Successfully auto-detected settings from local Streamlabs Desktop!\n\n"
                f"• Streaming PC LAN IP: {local_ip}\n"
                f"• Remote Port: {port}\n"
                f"• API Token: {token[:8]}...{token[-4:] if len(token) > 8 else ''}\n\n"
                f"💡 If configuring Streamer Calyx on another PC on your LAN, enter these exact values on that second PC!"
            )
        else:
            QMessageBox.warning(
                self,
                "Auto-Detect Not Available",
                "Could not auto-detect settings from local Streamlabs Desktop.\n\n"
                "Please make sure Streamlabs Desktop is running on this PC, or obtain your API Token manually via:\n"
                "Streamlabs Desktop -> Settings -> Remote Control -> QR Code -> Show details."
            )

    def _update_slobs_status_ui(self, *args):
        if not hasattr(self, "lbl_slobs_status"):
            return

        is_client = getattr(self, "conn_mode", "local") == "webrtc_client"
        if is_client:
            is_connected = (self.slobs_client and self.slobs_client.is_connected()) or (getattr(self, "client_webrtc", None) and getattr(self.client_webrtc, "is_connected", False))
            if is_connected:
                act_name = getattr(self.slobs_client, "_active_scene_name", "")
                if act_name and len(act_name) > 18:
                    act_name = act_name[:16] + "..."
                act_str = f" — Active: <b>{act_name}</b>" if act_name else ""
                self.lbl_slobs_status.setText(f"<span style='color: #22c55e; font-weight: bold;'>🟢 Linked to Streamer via P2P (SLOBS Remote)</span>{act_str}")
            else:
                self.lbl_slobs_status.setText("<span style='color: #ef4444; font-weight: bold;'>🔴 P2P Disconnected</span> <span style='color: #a1a1aa;'>— Click 'Connect P2P' below to link with Streamer</span>")
            return

        if self.slobs_client and self.slobs_client.is_connected():
            _, act_name = self.slobs_client.get_active_scene_info()
            if act_name and len(act_name) > 18:
                act_name = act_name[:16] + "..."
            act_str = f" — Active: <b>{act_name}</b>" if act_name else ""
            if self.slobs_client._mode == "local":
                mode_tag = "Local Pipe"
            elif self.slobs_client._mode == "remote":
                mode_tag = f"LAN {self.slobs_client._remote_host}:{self.slobs_client._remote_port}"
            else:
                mode_tag = "Encrypted P2P WAN"
            self.lbl_slobs_status.setText(f"<span style='color: #22c55e; font-weight: bold;'>🟢 Streamlabs Connected</span> <span style='color: #a1a1aa; font-size: 10px;'>({mode_tag})</span>{act_str}")
            self._refresh_fader_combos()
        else:
            if getattr(self, "conn_mode", "local") == "local":
                mode_str = "local PC"
            elif self.conn_mode == "remote":
                mode_str = "remote LAN PC"
            else:
                mode_str = "Streamer PC (via P2P)"
            self.lbl_slobs_status.setText(f"<span style='color: #ef4444; font-weight: bold;'>🔴 Streamlabs Disconnected</span> <span style='color: #a1a1aa;'>(Launch Streamlabs on {mode_str})</span>")

    def _manual_reconnect_slobs(self):
        if self.slobs_client:
            mode = self.combo_conn_mode.currentData() if hasattr(self, "combo_conn_mode") else "local"
            if mode == "webrtc_client":
                self._toggle_client_p2p_session(force_reconnect=True)
                return

            self.slobs_client.disconnect_client()
            host = self.edit_remote_host.text().strip() if hasattr(self, "edit_remote_host") else "127.0.0.1"
            port = self.edit_remote_port.text().strip() if hasattr(self, "edit_remote_port") else 59650
            token = self.edit_api_key.text().strip() if hasattr(self, "edit_api_key") else ""
            self.slobs_client.configure_connection(mode=mode, host=host, port=port, token=token)
            ok = self.slobs_client.connect_client()
            self._update_slobs_status_ui()
            if ok:
                self._refresh_fader_combos()
                mode_str = "Local PC (Named Pipe)" if mode == "local" else f"Remote LAN (ws://{host}:{port})"
                QMessageBox.information(self, "Connected", f"Successfully connected to Streamlabs Desktop via {mode_str}!")
            else:
                mode_str = "Local Named Pipe" if mode == "local" else f"WebSocket (ws://{host}:{port})"
                QMessageBox.warning(self, "Connection Failed", f"Could not connect to Streamlabs Desktop via {mode_str}.\n\nPlease verify that Streamlabs Desktop is running and Remote Control is enabled.")

    def _on_slobs_scenes_updated(self, scenes):
        pass

    def _on_slobs_audio_updated(self, sources):
        self._refresh_fader_combos()

    def _on_fader_combo_activated(self, combo: QComboBox, idx: int):
        if combo.itemText(idx) == "➕ Custom Source Name...":
            text, ok = QInputDialog.getText(self, "Custom Source Name", "Enter audio source name:")
            if ok and text.strip():
                name = text.strip()
                combo.insertItem(combo.count() - 1, name)
                combo.setCurrentText(name)
            else:
                if combo.count() > 1:
                    combo.setCurrentIndex(0)

    def _refresh_fader_combos(self):
        sources = self.slobs_client.get_cached_audio_sources() if self.slobs_client else []
        source_names = []
        for s in sources:
            n = s.get("name", "").strip()
            if n and n not in source_names:
                source_names.append(n)

        if not source_names:
            source_names = ["Mic", "Game", "Music", "Discord", "Alerts", "SFX", "Browser", "Desktop"]

        combos_and_defaults = [
            (getattr(self, "edit_fader1", None), "Mic", 0),
            (getattr(self, "edit_fader2", None), "Game", 1),
            (getattr(self, "edit_fader3", None), "Music", 2),
            (getattr(self, "edit_fader4", None), "Discord", 3),
            (getattr(self, "edit_fader5", None), "Alerts", 4),
        ]

        for combo, default_val, idx in combos_and_defaults:
            if combo is None:
                continue
            fader_target = self.faders[idx].get("name") if (hasattr(self, "faders") and idx < len(self.faders)) else None
            cur = fader_target or combo.currentText() or default_val
            combo.blockSignals(True)
            combo.clear()
            items = list(source_names)
            if cur and cur not in items and cur != "➕ Custom Source Name...":
                items.insert(0, cur)
            for name in items:
                combo.addItem(name)
            combo.addItem("➕ Custom Source Name...")
            combo.setCurrentText(cur)
            combo.blockSignals(False)

    def _auto_detect_scenes(self):
        scenes = self.slobs_client.fetch_scenes()
        if not scenes:
            scenes = self.slobs_client.get_cached_scenes()
        if not scenes:
            QMessageBox.warning(self, "Streamlabs Not Connected", "Could not detect scenes from Streamlabs Desktop.\n\nPlease make sure Streamlabs Desktop is running.")
            return

        palette = ["#22c55e", "#0284c7", "#ea580c", "#a855f7", "#ef4444", "#eab308", "#06b6d4", "#ec4899"]
        self.scenes = []
        view_names = {"legal-view", "sandman view"}
        avail_aud = [a.get("name") for a in self.audio_toggles if a.get("name") and a.get("name").strip().lower() not in view_names]
        avail_fad = [f.get("name") for f in self._get_fader_data() if f.get("name") and f.get("name").strip().lower() not in view_names]
        for i, sc in enumerate(scenes[:8]):
            s_name = sc.get("name", f"Scene {i+1}")
            is_game = ("game" in s_name.lower()) or ("play" in s_name.lower())
            is_start_brb = any(k in s_name.lower() for k in ["start", "brb", "break", "end", "be right"])
            self.scenes.append({
                "name": s_name,
                "id": sc.get("id", ""),
                "color": palette[i % len(palette)],
                "show_view_toggles": is_game,
                "audio_sources": [a for a in avail_aud if "spotify" in a.lower() or "music" in a.lower() or "vod" in a.lower()] if is_start_brb else avail_aud,
                "faders": [f for f in avail_fad if "spotify" in f.lower() or "music" in f.lower() or "vod" in f.lower()] if is_start_brb else avail_fad
            })
        self._refresh_scene_list_ui()
        self._on_settings_changed()
        if self.is_panel_open():
            self.panel_window.load_configuration(
                self.scenes, 
                self._get_live_audio_toggles(), 
                self._get_fader_data(), 
                permissions=getattr(self, "_cached_client_permissions", None),
                pool_scenes=self.scenes,
                pool_audio=self._get_live_audio_toggles(),
                pool_faders=self._get_active_fader_pool()
            )
        QMessageBox.information(self, "Scenes Detected", f"Successfully auto-detected {len(self.scenes)} scenes from Streamlabs Desktop!")

    def _auto_detect_audio(self):
        sources = self.slobs_client.fetch_audio_sources()
        if not sources:
            sources = self.slobs_client.get_cached_audio_sources()
        if not sources:
            QMessageBox.warning(self, "Streamlabs Not Connected", "Could not detect audio sources from Streamlabs Desktop.\n\nPlease make sure Streamlabs Desktop is running.")
            return

        priority_keywords = ["mic", "discord", "spotify", "music", "game", "desktop", "alert", "chat", "soundboard"]
        def score_source(s):
            name = (s.get("name") or "").lower()
            for idx, kw in enumerate(priority_keywords):
                if kw in name:
                    return idx
            return len(priority_keywords) + 1

        unique_names = set()
        cleaned_sources = []
        for s in sources:
            n = s.get("name", "").strip()
            if n and n.lower() not in ("legal-view", "sandman view") and n not in unique_names:
                unique_names.add(n)
                cleaned_sources.append(s)

        cleaned_sources.sort(key=score_source)

        self.audio_toggles = []
        for s in cleaned_sources[:8]:
            self.audio_toggles.append({
                "name": s.get("name"),
                "id": s.get("sourceId") or s.get("id", ""),
                "muted": bool(s.get("muted", False))
            })
        self._refresh_audio_list_ui()
        self._on_settings_changed()
        self._refresh_fader_combos()
        if self.is_panel_open():
            self.panel_window.load_configuration(
                self.scenes, 
                self._get_live_audio_toggles(), 
                self._get_fader_data(), 
                permissions=getattr(self, "_cached_client_permissions", None),
                pool_scenes=self.scenes,
                pool_audio=self._get_live_audio_toggles(),
                pool_faders=self._get_active_fader_pool(),
                soundboard_engine=getattr(self.main_win, "soundboard_engine", None)
            )
        QMessageBox.information(self, "Audio Sources Detected", f"Successfully auto-detected {len(self.audio_toggles)} audio sources from Streamlabs Desktop!")

    def _add_scene(self):
        if len(self.scenes) >= 8:
            QMessageBox.information(self, "Limit Reached", "A maximum of 8 scenes can be configured in the pool.")
            return
        avail = self.slobs_client.get_cached_scenes() if self.slobs_client else []
        palette = ["#22c55e", "#0284c7", "#ea580c", "#a855f7", "#ef4444", "#eab308", "#06b6d4", "#ec4899"]
        def_col = palette[len(self.scenes) % len(palette)]
        avail_aud = [a.get("name") for a in self.audio_toggles]
        avail_fad = [f.get("name") for f in self._get_fader_data()]
        avail_src = [it.get("name") for it in (self.slobs_client.get_cached_active_scene_items() if self.slobs_client else []) if it.get("name")]
        dlg = SceneEditDialog(
            f"Scene {len(self.scenes)+1}", 
            def_col, 
            available_scenes=avail, 
            available_audio=avail_aud,
            available_faders=avail_fad,
            available_sources=avail_src,
            parent=self
        )
        if dlg.exec():
            data = dlg.get_data()
            n, c, raw_id = data[0], data[1], data[2]
            aud = data[3] if len(data) > 3 else []
            fads = data[4] if len(data) > 4 else []
            show_v = data[5] if len(data) > 5 else False
            hks = data[6] if len(data) > 6 else []
            self.scenes.append({
                "name": n, 
                "color": c, 
                "id": raw_id,
                "audio_sources": aud,
                "faders": fads,
                "show_view_toggles": show_v,
                "hotkeys": hks
            })
            self._refresh_scene_list_ui()
            self._on_settings_changed()
            if self.is_panel_open():
                self.panel_window.load_configuration(
                    self.scenes, 
                    self._get_live_audio_toggles(), 
                    self._get_fader_data(), 
                    permissions=getattr(self, "_cached_client_permissions", None),
                    pool_scenes=self.scenes,
                    pool_audio=self._get_live_audio_toggles(),
                    pool_faders=self._get_active_fader_pool(),
                    soundboard_engine=getattr(self.main_win, "soundboard_engine", None)
                )

    def _edit_scene(self):
        row = self.list_scenes.currentRow()
        if 0 <= row < len(self.scenes):
            sc = self.scenes[row]
            avail = self.slobs_client.get_cached_scenes() if self.slobs_client else []
            avail_aud = [a.get("name") for a in self.audio_toggles]
            avail_fad = [f.get("name") for f in self._get_fader_data()]
            avail_src = [it.get("name") for it in (self.slobs_client.get_cached_active_scene_items() if self.slobs_client else []) if it.get("name")]
            dlg = SceneEditDialog(
                sc["name"], 
                sc.get("color", "#22c55e"), 
                available_scenes=avail, 
                scene_id=sc.get("id"),
                audio_sources=sc.get("audio_sources"),
                faders=sc.get("faders"),
                show_view_toggles=sc.get("show_view_toggles"),
                available_audio=avail_aud,
                available_faders=avail_fad,
                hotkeys=sc.get("hotkeys"),
                available_sources=avail_src,
                parent=self
            )
            if dlg.exec():
                data = dlg.get_data()
                n, c, raw_id = data[0], data[1], data[2]
                aud = data[3] if len(data) > 3 else []
                fads = data[4] if len(data) > 4 else []
                show_v = data[5] if len(data) > 5 else False
                hks = data[6] if len(data) > 6 else sc.get("hotkeys", [])
                self.scenes[row] = {
                    "name": n, 
                    "color": c, 
                    "id": raw_id,
                    "audio_sources": aud,
                    "faders": fads,
                    "show_view_toggles": show_v,
                    "hotkeys": hks
                }
                self._refresh_scene_list_ui()
                self._on_settings_changed()
                if self.is_panel_open():
                    self.panel_window.load_configuration(
                        self.scenes, 
                        self._get_live_audio_toggles(), 
                        self._get_fader_data(), 
                        permissions=getattr(self, "_cached_client_permissions", None),
                        pool_scenes=self.scenes,
                        pool_audio=self._get_live_audio_toggles(),
                        pool_faders=self._get_active_fader_pool()
                    )

    def _remove_scene(self):
        row = self.list_scenes.currentRow()
        if 0 <= row < len(self.scenes):
            self.scenes.pop(row)
            self._refresh_scene_list_ui()
            self._on_settings_changed()
            if self.is_panel_open():
                self.panel_window.load_configuration(
                    self.scenes, 
                    self._get_live_audio_toggles(), 
                    self._get_fader_data(), 
                    permissions=getattr(self, "_cached_client_permissions", None),
                    pool_scenes=self.scenes,
                    pool_audio=self._get_live_audio_toggles(),
                    pool_faders=self._get_active_fader_pool()
                )

    def _add_audio(self):
        if len(self.audio_toggles) >= 8:
            QMessageBox.information(self, "Limit Reached", "A maximum of 8 audio mute toggles can be configured in the pool.")
            return
        avail = self.slobs_client.get_cached_audio_sources() if self.slobs_client else []
        dlg = AudioEditDialog(f"Audio {len(self.audio_toggles)+1}", available_sources=avail, parent=self)
        if dlg.exec():
            n, raw_id = dlg.get_data()
            self.audio_toggles.append({"name": n, "id": raw_id, "muted": False})
            self._refresh_audio_list_ui()
            self._on_settings_changed()
            if self.is_panel_open():
                self.panel_window.load_configuration(
                    self.scenes, 
                    self._get_live_audio_toggles(), 
                    self._get_fader_data(), 
                    permissions=getattr(self, "_cached_client_permissions", None),
                    pool_scenes=self.scenes,
                    pool_audio=self._get_live_audio_toggles(),
                    pool_faders=self._get_active_fader_pool()
                )

    def _edit_audio(self):
        row = self.list_audio.currentRow()
        if 0 <= row < len(self.audio_toggles):
            cur = self.audio_toggles[row]
            avail = self.slobs_client.get_cached_audio_sources() if self.slobs_client else []
            dlg = AudioEditDialog(cur["name"], available_sources=avail, source_id=cur.get("id"), parent=self)
            if dlg.exec():
                n, raw_id = dlg.get_data()
                self.audio_toggles[row] = {"name": n, "id": raw_id, "muted": cur.get("muted", False)}
                self._refresh_audio_list_ui()
                self._on_settings_changed()
                if self.is_panel_open():
                    self.panel_window.load_configuration(
                        self.scenes, 
                        self._get_live_audio_toggles(), 
                        self._get_fader_data(), 
                        permissions=getattr(self, "_cached_client_permissions", None),
                        pool_scenes=self.scenes,
                        pool_audio=self._get_live_audio_toggles(),
                        pool_faders=self._get_active_fader_pool()
                    )

    def _remove_audio(self):
        row = self.list_audio.currentRow()
        if 0 <= row < len(self.audio_toggles):
            self.audio_toggles.pop(row)
            self._refresh_audio_list_ui()
            self._on_settings_changed()
            if self.is_panel_open():
                self.panel_window.load_configuration(
                    self.scenes, 
                    self._get_live_audio_toggles(), 
                    self._get_fader_data(), 
                    permissions=getattr(self, "_cached_client_permissions", None),
                    pool_scenes=self.scenes,
                    pool_audio=self._get_live_audio_toggles(),
                    pool_faders=self._get_active_fader_pool()
                )

    def _set_launch_button_state(self, is_open: bool):
        if is_open:
            self.btn_launch_panel.setText("🟢 Close Director Panel")
            self.btn_launch_panel.setStyleSheet("""
                QPushButton#btnLaunchDirector {
                    background-color: #b91c1c;
                    color: #ffffff;
                    font-size: 13px;
                    font-weight: bold;
                    border: 1px solid #dc2626;
                    border-radius: 6px;
                }
                QPushButton#btnLaunchDirector:hover {
                    background-color: #dc2626;
                }
            """)
        else:
            self.btn_launch_panel.setText("🔴 Launch Director Panel")
            self.btn_launch_panel.setStyleSheet("""
                QPushButton#btnLaunchDirector {
                    background-color: #15803d;
                    color: #ffffff;
                    font-size: 13px;
                    font-weight: bold;
                    border: 1px solid #16a34a;
                    border-radius: 6px;
                }
                QPushButton#btnLaunchDirector:hover {
                    background-color: #16a34a;
                }
            """)

    def is_panel_open(self) -> bool:
        """Safely returns whether the Director Panel dock is currently open and visible."""
        if not self.panel_window:
            return False
        try:
            return bool(self.panel_window.isVisible())
        except (AttributeError, RuntimeError):
            self.panel_window = None
            return False

    def toggle_director_panel(self):
        if self.is_panel_open():
            log_debug("DIRECTOR", "Closing Director Panel via toggle")
            self.panel_window.close()
            self.panel_window = None
            self._set_launch_button_state(is_open=False)
        else:
            self.launch_director_panel()

    def launch_director_panel(self):
        log_debug("DIRECTOR", "User clicked Launch Director Panel")

        # In client P2P mode, ensure P2P session is active and request fresh state
        if getattr(self, "conn_mode", "local") == "webrtc_client":
            if not getattr(self, "client_webrtc", None) or not self.client_webrtc.isRunning():
                self._toggle_client_p2p_session()
            else:
                QTimer.singleShot(150, lambda: self.client_webrtc.send_command("REQUEST_STATE") if self.client_webrtc and self.client_webrtc.isRunning() else None)

        # 1. Instantiate or show panel first so we know exact geometry above taskbar
        if not self.is_panel_open():
            if self.panel_window is not None:
                try:
                    self.panel_window.deleteLater()
                except Exception:
                    pass
                self.panel_window = None
            self.panel_window = DirectorPanelWindow()
            self.panel_window.panel_closed.connect(self._on_panel_closed)
            self.panel_window.settings_requested.connect(self._open_settings_from_panel)
            self.panel_window.resync_requested.connect(self._on_panel_resync_requested)
            self.panel_window.view_visibility_toggled.connect(self._on_panel_view_visibility_toggled)

        fader_data = self._get_fader_data()
        perms = getattr(self, "_cached_client_permissions", None)
        self.panel_window.load_configuration(
            self.scenes, 
            self._get_live_audio_toggles(), 
            fader_data, 
            permissions=perms,
            pool_scenes=self.scenes,
            pool_audio=self._get_live_audio_toggles(),
            pool_faders=self._get_active_fader_pool(),
            soundboard_engine=getattr(self.main_win, "soundboard_engine", None)
        )

        
        target_mon = self.combo_monitor.currentData()
        if target_mon is None:
            target_mon = self.combo_monitor.currentIndex()
        if target_mon is None or target_mon < 0:
            target_mon = 0

        log_debug("DIRECTOR", f"Target monitor index: {target_mon}")
        self.panel_window.reposition_above_taskbar(target_mon)
        self.panel_window.showNormal()
        self.panel_window.raise_()
        self.panel_window.activateWindow()
        self.panel_window.force_topmost()
        geom = self.panel_window.geometry()
        log_debug("DIRECTOR", f"Director Panel shown at: ({geom.x()}, {geom.y()}, {geom.width()}x{geom.height()}) - IsVisible: {self.panel_window.isVisible()}")
        self._set_launch_button_state(is_open=True)

        # 2. Open the streamer's livestream in browser (Chromium App Mode fitted above dock, or standard browser)
        url = self.edit_stream_url.text().strip()
        if url:
            self._launch_stream_browser(url, target_mon, geom.y())

        # Automatically hide Settings window so the user gets clean separate dock view
        if self.main_win:
            self.main_win.hide()

        # Re-assert topmost after browser completes launch (multi-stage)
        QTimer.singleShot(200, self.panel_window.force_topmost)
        QTimer.singleShot(500, self.panel_window.force_topmost)
        QTimer.singleShot(1000, self.panel_window.force_topmost)
        QTimer.singleShot(2000, self.panel_window.force_topmost)
        QTimer.singleShot(3500, self.panel_window.force_topmost)

    def _find_chromium_browser(self) -> str | None:
        if sys.platform != "win32":
            return None
        import winreg
        # 1. Check registry App Paths
        for app in ["chrome.exe", "msedge.exe", "brave.exe"]:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app}") as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    if val and os.path.exists(val):
                        return val
            except Exception:
                pass
        # 2. Check well-known filesystem paths
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _launch_stream_browser(self, url: str, target_mon: int, dock_top_y: int):
        # Don't spawn duplicate browser process if already active
        if hasattr(self, "_browser_proc") and self._browser_proc is not None:
            if self._browser_proc.poll() is None:
                log_debug("DIRECTOR", "Stream browser process is already running, skipping duplicate launch")
                return

        screens = QApplication.screens()
        idx = target_mon if 0 <= target_mon < len(screens) else 0
        screen = screens[idx] if screens else None

        if screen:
            geo = screen.geometry()
            pos_x = geo.x()
            pos_y = geo.y()
            win_w = geo.width()
            win_h = max(300, dock_top_y - pos_y)
        else:
            pos_x, pos_y, win_w, win_h = 0, 0, 1360, 546

        if hasattr(self, "chk_app_mode") and self.chk_app_mode.isChecked():
            browser_exe = self._find_chromium_browser()
            if browser_exe:
                try:
                    cmd = [
                        browser_exe,
                        f"--app={url}",
                        "--start-maximized",
                    ]
                    log_debug("DIRECTOR", f"Launching studio app window maximized ({os.path.basename(browser_exe)}): {url}")
                    self._browser_proc = subprocess.Popen(cmd)
                    return
                except Exception as e:
                    log_debug("DIRECTOR", f"Failed to launch Chromium app mode: {e}")

        # Fallback to default browser
        try:
            log_debug("DIRECTOR", f"Opening livestream URL in default browser: {url}")
            webbrowser.open(url)
        except Exception as e:
            log_debug("DIRECTOR", f"Browser launch error: {e}")

    def _open_settings_from_panel(self):
        log_debug("DIRECTOR", "Settings button clicked on Director Dock")
        if self.main_win:
            self.main_win.show()
            self.main_win.raise_()
            self.main_win.activateWindow()
    def _on_panel_closed(self):
        log_debug("DIRECTOR", "Director Panel closed event received")
        self._set_launch_button_state(is_open=False)
        self.panel_window = None

    def _on_panel_view_visibility_toggled(self, source_name: str, is_visible: bool):
        log_debug("DIRECTOR", f"Panel view visibility toggled: {source_name} -> {is_visible}")
        if self.client_webrtc and self.client_webrtc.isRunning():
            self.client_webrtc.send_command("SET_VISIBILITY", source_name, is_visible)

    def _on_settings_changed(self):
        if getattr(self, "_is_loading", False):
            return
        if hasattr(self, "combo_conn_mode"):
            self.conn_mode = self.combo_conn_mode.currentData() or "local"
        if hasattr(self, "edit_remote_host"):
            self.remote_host = self.edit_remote_host.text().strip() or "127.0.0.1"
        if hasattr(self, "edit_remote_port"):
            self.remote_port = self.edit_remote_port.text().strip() or "59650"
        self.api_key = self.edit_api_key.text().strip()
        self.stream_url = self.edit_stream_url.text().strip()
        self.target_monitor_idx = self.combo_monitor.currentData() or 0
        if hasattr(self, "chk_app_mode"):
            self.app_mode = self.chk_app_mode.isChecked()
        while len(self.faders) < 5:
            self.faders.append({"name": f"Audio {len(self.faders)+1}", "volume": 75})
        for idx in range(1, 6):
            combo = getattr(self, f"edit_fader{idx}", None)
            if combo:
                self.faders[idx - 1]["name"] = combo.currentText().strip()
        self.fader_pool = self._get_active_fader_pool()
        self.save_to_settings()

        # Update live client connection configuration
        if hasattr(self, "slobs_client") and self.slobs_client:
            self.slobs_client.configure_connection(
                mode=self.conn_mode,
                host=self.remote_host,
                port=self.remote_port,
                token=self.api_key
            )

        # Update live Director Panel dock immediately if open
        if self.is_panel_open():
            self.panel_window.update_faders(self._get_fader_data())

    def export_settings(self) -> dict:
        return {
            "conn_mode": self.combo_conn_mode.currentData() if hasattr(self, "combo_conn_mode") else "local",
            "remote_host": self.edit_remote_host.text().strip() if hasattr(self, "edit_remote_host") else "127.0.0.1",
            "remote_port": self.edit_remote_port.text().strip() if hasattr(self, "edit_remote_port") else "59650",
            "api_key_obf": obfuscate_str(self.edit_api_key.text()),
            "enable_wan_p2p": self.chk_enable_wan_p2p.isChecked() if hasattr(self, "chk_enable_wan_p2p") else False,
            "p2p_passkey_salt": self.p2p_passkey_salt,
            "p2p_passkey_hash": self.p2p_passkey_hash,
            "p2p_passkey_raw": self.p2p_passkey_raw,
            "user_permissions": self.user_permissions,
            "allowed_twitch_user": self._get_current_selected_cohost() or (self.edit_allowed_twitch_user.text().strip() if hasattr(self, "edit_allowed_twitch_user") else ""),
            "p2p_target_channel": self.edit_client_channel.text().strip() if hasattr(self, "edit_client_channel") else "",
            "p2p_client_passkey": self.edit_client_passkey.text().strip() if hasattr(self, "edit_client_passkey") else "",
            "p2p_my_twitch_user": self.edit_client_my_user.text().strip() if hasattr(self, "edit_client_my_user") else "",
            "stream_url": self.edit_stream_url.text().strip(),
            "target_monitor": self.combo_monitor.currentData() or 0,
            "app_mode": self.chk_app_mode.isChecked() if hasattr(self, "chk_app_mode") else True,
            "scenes": self.scenes,
            "audio_toggles": self.audio_toggles,
            "faders": self._get_fader_data(),
            "fader_pool": self._get_active_fader_pool(),
        }

    def load_from_settings(self, settings_override: Optional[dict] = None):
        self._is_loading = True
        try:
            if settings_override is not None:
                d = settings_override
            else:
                overlay = getattr(self.main_win, "overlay", None) if self.main_win else None
                d = getattr(overlay, "director_settings", {}) if overlay else {}
            if d:
                self.conn_mode = d.get("conn_mode", "local")
                self.remote_host = d.get("remote_host", "127.0.0.1")
                self.remote_port = d.get("remote_port", "59650")
                self.api_key = obfuscate_str(d.get("api_key_obf", ""))

                self.enable_wan_p2p = d.get("enable_wan_p2p", False)
                self.p2p_passkey_salt = d.get("p2p_passkey_salt", "")
                self.p2p_passkey_hash = d.get("p2p_passkey_hash", "")
                self.p2p_passkey_raw = d.get("p2p_passkey_raw", "")
                self.allowed_twitch_user = d.get("allowed_twitch_user", "")
                self.p2p_target_channel = d.get("p2p_target_channel", "")
                self.p2p_client_passkey = d.get("p2p_client_passkey", "")
                self.p2p_my_twitch_user = d.get("p2p_my_twitch_user", "")

                # Load user permissions and sync
                self.user_permissions = d.get("user_permissions")
                if not self.user_permissions:
                    self.user_permissions = self._load_permissions_file()

                # Migrate legacy allowed_twitch_user if user_permissions is empty
                if self.allowed_twitch_user and not self.user_permissions:
                    clean_legacy = self.allowed_twitch_user.lower().strip().lstrip("@")
                    if clean_legacy:
                        self.user_permissions[clean_legacy] = {
                            "full_control": True,
                            "allowed_scenes": [s.get("name", "") for s in self.scenes if s.get("name")],
                            "allowed_audio_mutes": [a.get("name", "") for a in self.audio_toggles if a.get("name")],
                            "allowed_audio_volume": [f.get("name", "") for f in self.faders if f.get("name")]
                        }

                if self.user_permissions:
                    self._sync_permissions_file()

                if hasattr(self, "chk_enable_wan_p2p"):
                    self.chk_enable_wan_p2p.blockSignals(True)
                    self.chk_enable_wan_p2p.setChecked(self.enable_wan_p2p)
                    self.chk_enable_wan_p2p.blockSignals(False)
                    if hasattr(self, "box_host_p2p_details"):
                        self.box_host_p2p_details.setVisible(self.enable_wan_p2p)

                if hasattr(self, "edit_host_passkey"):
                    self.edit_host_passkey.setText(self.p2p_passkey_raw)
                if hasattr(self, "edit_allowed_twitch_user"):
                    self.edit_allowed_twitch_user.setText(self.allowed_twitch_user)
                if hasattr(self, "edit_client_channel"):
                    self.edit_client_channel.setText(self.p2p_target_channel or self._get_streamer_channel())
                if hasattr(self, "edit_client_passkey"):
                    self.edit_client_passkey.setText(self.p2p_client_passkey)
                if hasattr(self, "edit_client_my_user"):
                    my_user = self.p2p_my_twitch_user
                    if not my_user:
                        overlay = getattr(self.main_win, "overlay", None)
                        my_user = (getattr(overlay, "twitch_login", "") or getattr(overlay, "twitch_display_name", "")) if overlay else ""
                    self.edit_client_my_user.setText(my_user)

                if hasattr(self, "combo_conn_mode"):
                    idx = self.combo_conn_mode.findData(self.conn_mode)
                    if idx >= 0:
                        self.combo_conn_mode.setCurrentIndex(idx)
                    self._on_conn_mode_changed()
                if hasattr(self, "edit_remote_host"):
                    self.edit_remote_host.setText(self.remote_host)
                if hasattr(self, "edit_remote_port"):
                    self.edit_remote_port.setText(str(self.remote_port))
                if hasattr(self, "edit_api_key"):
                    self.edit_api_key.setText(self.api_key)

                if hasattr(self, "slobs_client") and self.slobs_client:
                    self.slobs_client.configure_connection(
                        mode=self.conn_mode,
                        host=self.remote_host,
                        port=self.remote_port,
                        token=self.api_key
                    )

                self.stream_url = d.get("stream_url", self.stream_url)
                self.edit_stream_url.setText(self.stream_url)
                self.target_monitor_idx = d.get("target_monitor", 0)
                self.app_mode = d.get("app_mode", True)
                if hasattr(self, "chk_app_mode"):
                    self.chk_app_mode.setChecked(self.app_mode)
                self.scenes = d.get("scenes", self.scenes)[:8]
                self.audio_toggles = d.get("audio_toggles", self.audio_toggles)[:8]
                loaded_faders = d.get("faders", [])
                if loaded_faders:
                    self.faders = loaded_faders
                defaults = [
                    {"name": "Mic", "volume": 80},
                    {"name": "Game", "volume": 75},
                    {"name": "Music", "volume": 60},
                    {"name": "Discord", "volume": 70},
                    {"name": "Alerts", "volume": 65},
                ]
                while len(self.faders) < 5:
                    self.faders.append(defaults[len(self.faders)])
                self.fader_pool = d.get("fader_pool", self._get_active_fader_pool())[:8]

                for idx in range(1, 6):
                    combo = getattr(self, f"edit_fader{idx}", None)
                    if combo and idx - 1 < len(self.faders):
                        fname = self.faders[idx - 1].get("name", "")
                        if fname:
                            if combo.findText(fname) == -1:
                                combo.insertItem(0, fname)
                            combo.setCurrentText(fname)

                # Auto-start host P2P if previously enabled and on local/remote host
                if self.enable_wan_p2p and self.conn_mode != "webrtc_client":
                    self._start_host_p2p()

            self.refresh_monitors_list()
            self._refresh_scene_list_ui()
            self._refresh_audio_list_ui()
            self._refresh_cohosts_combo()
            self._refresh_permissions_matrix_items()
        finally:
            self._is_loading = False

    def save_to_settings(self):
        if getattr(self, "_is_loading", False):
            return
        if hasattr(self.main_win, "overlay") and self.main_win.overlay:
            self.main_win.overlay.director_settings = self.export_settings()
            self.main_win.overlay.save_settings()

    def _get_streamer_channel(self) -> str:
        url = self.edit_stream_url.text().strip() if hasattr(self, "edit_stream_url") else ""
        if "twitch.tv/" in url:
            parts = url.split("twitch.tv/")
            ch = parts[-1].split("/")[0].split("?")[0].strip()
            if ch:
                return ch
        return "thawizanator"

    def _copy_passkey(self):
        pk = self.edit_host_passkey.text().strip() if hasattr(self, "edit_host_passkey") else ""
        if pk:
            QApplication.clipboard().setText(pk)
            QMessageBox.information(
                self,
                "Passkey Copied",
                f"Pairing Passkey copied to clipboard:\n\n{pk}\n\n"
                f"Send this passkey and your Twitch channel name ({self._get_streamer_channel()}) to your remote director."
            )

    def _revoke_passkey(self):
        res = QMessageBox.question(
            self,
            "Revoke Passkey",
            "Are you sure you want to revoke the current pairing passkey?\n\n"
            "Any currently connected remote directors will be disconnected immediately.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self._stop_host_p2p()
            self._generate_new_passkey()
            if hasattr(self, "chk_enable_wan_p2p") and self.chk_enable_wan_p2p.isChecked():
                self._start_host_p2p()

    def _generate_new_passkey(self):
        raw_pk, salt, hash_val = PasskeyManager.generate_passkey()
        self.p2p_passkey_raw = raw_pk
        self.p2p_passkey_salt = salt
        self.p2p_passkey_hash = hash_val
        if hasattr(self, "edit_host_passkey"):
            self.edit_host_passkey.setText(raw_pk)
        self._on_settings_changed()

    def _on_host_p2p_toggled(self, checked: bool):
        if hasattr(self, "box_host_p2p_details"):
            self.box_host_p2p_details.setVisible(checked)
        self.enable_wan_p2p = checked
        self._on_settings_changed()
        if checked:
            if not self.p2p_passkey_raw:
                self._generate_new_passkey()
            self._start_host_p2p()
        else:
            self._stop_host_p2p()

    def _start_host_p2p(self):
        self._stop_host_p2p()
        ch = self._get_streamer_channel()
        pk = self.p2p_passkey_raw
        if not pk:
            return

        allowed_user = self._get_current_selected_cohost() or (self.edit_allowed_twitch_user.text().strip() if hasattr(self, "edit_allowed_twitch_user") else "")
        self.bouncer = BouncerValidator(
            allowed_twitch_user=allowed_user,
            user_permissions=self.user_permissions
        )
        self.bouncer.set_whitelists(self.scenes, self.audio_toggles, self.faders, fader_pool=self._get_active_fader_pool())

        try:
            from webrtc_p2p import WebRTCManager
        except Exception as e:
            QMessageBox.critical(self, "WebRTC Error", f"Failed to load WebRTC P2P module:\n{e}")
            return

        self.host_webrtc = WebRTCManager(role="host", channel_name=ch, passkey=pk, parent=self)
        self.host_webrtc.connection_status_changed.connect(self._on_host_p2p_status_changed)
        self.host_webrtc.command_received.connect(self._on_host_p2p_command_received)
        self.host_webrtc.peer_authenticated.connect(self._on_host_p2p_peer_authenticated)
        self.host_webrtc.peer_disconnected.connect(self._on_host_p2p_peer_disconnected)
        self.host_webrtc.start()
        if hasattr(self, "lbl_host_p2p_status"):
            self.lbl_host_p2p_status.setText("<span style='color: #38bdf8;'>🟡 Listening for remote director...</span>")

    def _stop_host_p2p(self):
        if self.host_webrtc:
            try:
                self.host_webrtc.stop_session()
            except Exception:
                pass
            self.host_webrtc = None
        if hasattr(self, "lbl_host_p2p_status"):
            self.lbl_host_p2p_status.setText("<span style='color: #a1a1aa;'>🟡 Gateway Offline</span>")

    def _on_host_p2p_status_changed(self, status_tag: str, msg: str):
        if hasattr(self, "lbl_host_p2p_status"):
            if status_tag == "connected":
                self.lbl_host_p2p_status.setText(f"<span style='color: #22c55e;'>{msg}</span>")
            elif status_tag == "signaling":
                self.lbl_host_p2p_status.setText(f"<span style='color: #38bdf8;'>{msg}</span>")
            else:
                self.lbl_host_p2p_status.setText(f"<span style='color: #ef4444;'>{msg}</span>")

    def _get_live_audio_toggles(self) -> list:
        live = []
        slobs_ok = hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected()
        for a in self.audio_toggles:
            entry = dict(a)
            name = entry.get("name", "")
            if name and slobs_ok:
                entry["muted"] = self.slobs_client.get_source_muted_state(name)
            live.append(entry)
        return live

    def _get_fader_data(self):
        fader_combos = [
            (getattr(self, "edit_fader1", None), "Mic", 80),
            (getattr(self, "edit_fader2", None), "Game", 75),
            (getattr(self, "edit_fader3", None), "Music", 60),
            (getattr(self, "edit_fader4", None), "Discord", 70),
            (getattr(self, "edit_fader5", None), "Alerts", 65),
        ]
        result = []
        slobs_ok = hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected()
        for idx, (combo, def_name, def_vol) in enumerate(fader_combos):
            name = combo.currentText().strip() if combo else ""
            if not name:
                name = self.faders[idx].get("name", def_name) if idx < len(self.faders) else def_name
            vol = self.slobs_client.get_source_volume_percent(name) if slobs_ok else (
                self.faders[idx].get("volume", def_vol) if idx < len(self.faders) else def_vol
            )
            result.append({"name": name, "volume": vol})
        return result

    def _on_panel_resync_requested(self):
        if self.client_webrtc and self.client_webrtc.isRunning():
            log_debug("WEBRTC", "Panel requested state re-sync from streamer via P2P")
            self.client_webrtc.send_command("REQUEST_STATE")
        else:
            self.push_sync_to_directors()

    def push_sync_to_directors(self):
        """Immediately broadcasts current scene and audio setup to all connected remote directors (or pulls from streamer if client)."""
        if getattr(self, "conn_mode", "local") == "webrtc_client":
            if self.client_webrtc and self.client_webrtc.isRunning():
                log_debug("WEBRTC", "Director requested state sync from streamer via P2P")
                self.client_webrtc.send_command("REQUEST_STATE")
                if hasattr(self, "btn_push_sync"):
                    orig_text = self.btn_push_sync.text()
                    self.btn_push_sync.setText("🔄 Syncing...")
                    QTimer.singleShot(1500, lambda: self.btn_push_sync.setText(orig_text))
            else:
                QMessageBox.information(
                    self,
                    "P2P Not Connected",
                    "You are not connected to the streamer yet.\n\n"
                    "Please click '🔗 Connect P2P' first to link with the streamer, then click sync."
                )
            return

        log_debug("HOST_BOUNCER", "Streamer pushed state re-sync to directors")
        self._broadcast_host_state_update()
        if hasattr(self, "btn_push_sync"):
            orig_text = self.btn_push_sync.text()
            self.btn_push_sync.setText("✅ Synced!")
            QTimer.singleShot(2000, lambda: self.btn_push_sync.setText(orig_text))
        if hasattr(self, "lbl_host_p2p_status"):
            cur = self.lbl_host_p2p_status.text()
            self.lbl_host_p2p_status.setText("<span style='color: #22c55e;'>📡 Sync Pushed to Remote Directors!</span>")
            QTimer.singleShot(2500, lambda: self.lbl_host_p2p_status.setText(cur))
        if self.is_panel_open():
            self.panel_window.load_configuration(
                self.scenes, 
                self._get_live_audio_toggles(), 
                self._get_fader_data(), 
                permissions=getattr(self, "_cached_client_permissions", None),
                pool_scenes=self.scenes,
                pool_audio=self._get_live_audio_toggles(),
                pool_faders=self._get_active_fader_pool(),
                soundboard_engine=getattr(self.main_win, "soundboard_engine", None)
            )


    def _on_host_p2p_command_received(self, client_id: str, payload: dict):
        action = payload.get("action")
        if action == "HANDSHAKE":
            provided_key = payload.get("passkey", "")
            twitch_user = payload.get("twitch_user", "")
            # Verify passkey
            if not PasskeyManager.verify_passkey(provided_key, self.p2p_passkey_salt, self.p2p_passkey_hash):
                log_debug("HOST_BOUNCER", f"Handshake rejected: invalid passkey from {client_id}")
                if self.host_webrtc:
                    self.host_webrtc.reject_peer_handshake(client_id, "Invalid or expired Passkey")
                return

            # Verify Twitch identity
            is_ok, reason = self.bouncer.verify_identity(twitch_user) if self.bouncer else (True, "OK")
            if not is_ok:
                log_debug("HOST_BOUNCER", f"Handshake rejected: {reason} for client {client_id}")
                if self.host_webrtc:
                    self.host_webrtc.reject_peer_handshake(client_id, reason)
                return

            # Approved! Assemble current state and send approve
            clean_user = (twitch_user or "").strip().lstrip("@")
            log_debug("HOST_BOUNCER", f"Handshake APPROVED for @{clean_user or 'anonymous'} ({client_id})")
            if self.bouncer:
                self.bouncer.register_peer(client_id, twitch_user)
            act_id, active_name = self.slobs_client.get_active_scene_info()
            fader_data = self._get_fader_data()
            live_toggles = self._get_live_audio_toggles()
            active_pool = self._get_active_fader_pool()
            peer_perms = {}
            if clean_user:
                if self.bouncer:
                    peer_perms = self.bouncer.get_user_permissions(clean_user) or {}
                if not peer_perms:
                    for k, v in self.user_permissions.items():
                        if k.lower().strip().lstrip("@") == clean_user.lower():
                            peer_perms = v
                            break

            state = {
                "active_scene": active_name or "",
                "active_scene_id": act_id or "",
                "scenes": self.scenes,
                "audio_toggles": live_toggles,
                "faders": fader_data,
                "fader_pool": active_pool,
                "pool_scenes": self.scenes,
                "pool_audio": live_toggles,
                "pool_faders": active_pool,
                "audio_sources": self.slobs_client.get_cached_audio_sources(),
                "permissions": peer_perms,
                "user_permissions": self.user_permissions
            }
            if self.bouncer:
                self.bouncer.set_whitelists(self.scenes, live_toggles, fader_data, fader_pool=active_pool)
            if self.host_webrtc:
                self.host_webrtc.approve_peer_handshake(client_id, twitch_user, state)
            return

        # Normal commands: validate through bouncer
        if not self.bouncer:
            return
        is_valid, reason, sanitized = self.bouncer.validate_command(client_id, payload)
        if not is_valid:
            log_debug("HOST_BOUNCER", f"Command rejected: {reason} from {client_id}")
            return

        cmd_act = sanitized.get("action")
        target = sanitized.get("target")
        if cmd_act == "SWITCH_SCENE":
            log_debug("HOST_BOUNCER", f"Executing validated SWITCH_SCENE -> '{target}'")
            self.slobs_client.make_scene_active(target)
            QTimer.singleShot(400, self._broadcast_host_state_update)
        elif cmd_act == "TOGGLE_MUTE":
            log_debug("HOST_BOUNCER", f"Executing validated TOGGLE_MUTE -> '{target}' ({sanitized.get('muted')})")
            self.slobs_client.set_audio_muted(target, sanitized.get("muted", True))
            QTimer.singleShot(300, self._broadcast_host_state_update)
        elif cmd_act == "SET_VOLUME":
            log_debug("HOST_BOUNCER", f"Executing validated SET_VOLUME -> '{target}' ({sanitized.get('volume')})")
            self.slobs_client.set_audio_deflection(target, sanitized.get("volume", 0.75))
            QTimer.singleShot(300, self._broadcast_host_state_update)
        elif cmd_act == "SET_VISIBILITY":
            log_debug("HOST_BOUNCER", f"Executing validated SET_VISIBILITY -> '{target}' ({sanitized.get('visible')})")
            self.slobs_client.set_source_visibility(target, sanitized.get("visible", True))
            QTimer.singleShot(300, self._broadcast_host_state_update)
        elif cmd_act == "PLAY_SOUND":
            clip_id = sanitized.get("clip_id") or sanitized.get("target") or ""
            user = sanitized.get("user") or client_id
            engine = getattr(self.main_win, "soundboard_engine", None)
            if engine and clip_id:
                guard = getattr(self, "spam_guard", None)
                if not guard:
                    guard = SoundboardSpamGuard(parent=self)
                    self.spam_guard = guard
                allowed, reason, rem = guard.check_trigger(user)
                if not allowed:
                    log_debug("HOST_BOUNCER", f"Soundboard trigger blocked by Spam Guard for {user}: {reason}")
                    if guard.get_strike_count(user) >= 3:
                        if hasattr(engine, "play_alarm_buzzer"):
                            engine.play_alarm_buzzer()
                        else:
                            engine.play_clip("cue-buzzer")
                else:
                    log_debug("HOST_BOUNCER", f"Executing validated PLAY_SOUND -> '{clip_id}' from {user}")
                    engine.toggle_clip(clip_id)
        elif cmd_act == "REQUEST_STATE":
            log_debug("HOST_BOUNCER", f"Executing validated REQUEST_STATE from client {client_id}")
            self._broadcast_host_state_update()

    def _on_host_p2p_peer_authenticated(self, client_id: str, twitch_user: str):
        clean_user = (twitch_user or "").strip().lstrip("@")
        user_str = f"@{clean_user}" if clean_user else "anonymous"
        log_debug("HOST_BOUNCER", f"Remote Director authenticated: {user_str} ({client_id})")
        if hasattr(self, "lbl_host_p2p_status"):
            self.lbl_host_p2p_status.setText(f"<span style='color: #22c55e;'>🟢 1 Remote Director Connected ({user_str})</span>")
        # Proactively push tailored permissions and state to newly connected peer immediately
        QTimer.singleShot(200, self._broadcast_host_state_update)

    def _on_host_p2p_peer_disconnected(self, client_id: str):
        log_debug("HOST_BOUNCER", f"Remote Director disconnected: {client_id}")
        if self.bouncer:
            self.bouncer.unregister_peer(client_id)
        if hasattr(self, "lbl_host_p2p_status"):
            if self.host_webrtc and self.host_webrtc._peers:
                count = len(self.host_webrtc._peers)
                self.lbl_host_p2p_status.setText(f"<span style='color: #22c55e;'>🟢 {count} Remote Director(s) Connected</span>")
            else:
                self.lbl_host_p2p_status.setText("<span style='color: #38bdf8;'>🟡 Listening for remote director...</span>")

    def _broadcast_host_state_update(self, *args):
        if self.host_webrtc and self.host_webrtc.isRunning():
            act_id, active_name = self.slobs_client.get_active_scene_info()
            fader_data = self._get_fader_data()
            live_toggles = self._get_live_audio_toggles()
            active_pool = self._get_active_fader_pool()
            state = {
                "active_scene": active_name or "",
                "active_scene_id": act_id or "",
                "scenes": self.scenes,
                "audio_toggles": live_toggles,
                "faders": fader_data,
                "fader_pool": active_pool,
                "pool_scenes": self.scenes,
                "pool_audio": live_toggles,
                "pool_faders": active_pool,
                "audio_sources": self.slobs_client.get_cached_audio_sources(),
                "view_toggles": {
                    "Legal-View": self.slobs_client.get_source_visibility("Legal-View"),
                    "SandMan View": self.slobs_client.get_source_visibility("SandMan View"),
                },
                "user_permissions": self.user_permissions
            }
            if self.bouncer:
                self.bouncer.set_whitelists(self.scenes, live_toggles, fader_data, fader_pool=active_pool)
            self.host_webrtc.broadcast_state(state)

    def _toggle_client_p2p_session(self, force_reconnect: bool = False):
        if self.client_webrtc and self.client_webrtc.isRunning() and not force_reconnect:
            self.client_webrtc.stop_session()
            self.client_webrtc = None
            self.slobs_client.disconnect_client()
            if hasattr(self, "btn_client_p2p_connect"):
                self.btn_client_p2p_connect.setText("🔗 Connect P2P Session")
                self.btn_client_p2p_connect.setStyleSheet("font-weight: 600; font-size: 11px; padding: 3px 8px; background-color: #0284c7; color: white;")
            if hasattr(self, "lbl_client_p2p_status"):
                self.lbl_client_p2p_status.setText("🔴 Disconnected")
            self._update_slobs_status_ui()
            return

        if self.client_webrtc:
            self.client_webrtc.stop_session()
            self.client_webrtc = None

        ch = self.edit_client_channel.text().strip() if hasattr(self, "edit_client_channel") else ""
        pk = self.edit_client_passkey.text().strip() if hasattr(self, "edit_client_passkey") else ""
        user = self.edit_client_my_user.text().strip().lstrip("@") if hasattr(self, "edit_client_my_user") else ""

        if not ch or not pk:
            QMessageBox.warning(
                self,
                "Missing P2P Credentials",
                "Please enter both the Streamer's Twitch Channel and the Pairing Passkey provided by the streamer."
            )
            return

        if hasattr(self, "btn_client_p2p_connect"):
            self.btn_client_p2p_connect.setText("⏹️ Disconnect P2P")
            self.btn_client_p2p_connect.setStyleSheet("font-weight: 600; font-size: 11px; padding: 3px 8px; background-color: #ef4444; color: white;")
        if hasattr(self, "lbl_client_p2p_status"):
            self.lbl_client_p2p_status.setText("<span style='color: #38bdf8;'>🟡 Initializing P2P connection...</span>")

        try:
            from webrtc_p2p import WebRTCManager
        except Exception as e:
            QMessageBox.critical(self, "WebRTC Error", f"Failed to load WebRTC P2P module:\n{e}")
            return

        self.client_webrtc = WebRTCManager(role="client", channel_name=ch, passkey=pk, twitch_user=user, parent=self)
        self.client_webrtc.connection_status_changed.connect(self._on_client_p2p_status_changed)
        self.client_webrtc.state_received.connect(self._on_client_p2p_state_received)
        self.slobs_client.configure_connection(mode="webrtc_client")
        self.slobs_client.set_webrtc_client(self.client_webrtc)
        self.client_webrtc.start()

    def _on_client_p2p_status_changed(self, status_tag: str, msg: str):
        if hasattr(self, "lbl_client_p2p_status"):
            if status_tag == "connected":
                self.lbl_client_p2p_status.setText(f"<span style='color: #22c55e;'>{msg}</span>")
                if hasattr(self, "btn_client_p2p_connect"):
                    self.btn_client_p2p_connect.setText("⏹️ Disconnect P2P")
                    self.btn_client_p2p_connect.setStyleSheet("font-weight: 600; font-size: 11px; padding: 3px 8px; background-color: #ef4444; color: white;")
            elif status_tag == "signaling":
                self.lbl_client_p2p_status.setText(f"<span style='color: #38bdf8;'>{msg}</span>")
                if hasattr(self, "btn_client_p2p_connect"):
                    self.btn_client_p2p_connect.setText("⏹️ Disconnect P2P")
                    self.btn_client_p2p_connect.setStyleSheet("font-weight: 600; font-size: 11px; padding: 3px 8px; background-color: #f59e0b; color: white;")
            else:
                self.lbl_client_p2p_status.setText(f"<span style='color: #ef4444;'>{msg}</span>")
                if hasattr(self, "btn_client_p2p_connect"):
                    self.btn_client_p2p_connect.setText("🔗 Connect P2P Session")
                    self.btn_client_p2p_connect.setStyleSheet("font-weight: 600; font-size: 11px; padding: 3px 8px; background-color: #0284c7; color: white;")
        self._update_slobs_status_ui()

    def _on_client_p2p_state_received(self, state: dict):
        log_debug("WEBRTC", "Client received state update from streamer")
        scenes = state.get("scenes", [])
        if scenes:
            self.scenes = scenes
            self._refresh_scene_list_ui()

        audio_toggles = state.get("audio_toggles", [])
        if audio_toggles:
            self.audio_toggles = audio_toggles
            self._refresh_audio_list_ui()

        faders = state.get("faders", [])
        if faders:
            self.faders = faders
            self._refresh_fader_combos()

        pool_scenes = state.get("pool_scenes") or scenes
        pool_audio = state.get("pool_audio") or audio_toggles
        pool_faders = state.get("pool_faders") or state.get("fader_pool") or [f.get("name") for f in faders]

        perms = state.get("permissions")
        if not perms:
            my_user = ""
            if self.client_webrtc and hasattr(self.client_webrtc, "twitch_user"):
                my_user = (self.client_webrtc.twitch_user or "").strip().lower().lstrip("@")
            if not my_user and hasattr(self, "edit_client_my_user"):
                my_user = self.edit_client_my_user.text().strip().lower().lstrip("@")
            if not my_user and "user" in state:
                my_user = str(state.get("user", "")).strip().lower().lstrip("@")
            all_perms = state.get("user_permissions", {})
            for u, p in all_perms.items():
                if u.lower().strip().lstrip("@") == my_user:
                    perms = p
                    break
            if not perms and len(all_perms) == 1:
                perms = next(iter(all_perms.values()))

        self._cached_client_permissions = perms


        if self.panel_window:
            fader_payload = faders or self._get_fader_data()
            self.panel_window.load_configuration(
                self.scenes, 
                self.audio_toggles, 
                fader_payload, 
                permissions=perms,
                pool_scenes=pool_scenes,
                pool_audio=pool_audio,
                pool_faders=pool_faders
            )
            active_sc = state.get("active_scene", "")
            active_sc_id = state.get("active_scene_id", "")
            if active_sc or active_sc_id:
                self.panel_window._on_slobs_scene_switched(active_sc_id, active_sc)

            view_toggles = state.get("view_toggles", {})
            if view_toggles:
                for v_name, vis in view_toggles.items():
                    if v_name in self.panel_window.view_toggle_buttons:
                        self.panel_window.view_toggle_buttons[v_name].set_visibility_state(vis)

        self._update_slobs_status_ui()

    def closeEvent(self, event):
        self._stop_host_p2p()
        if self.client_webrtc:
            self.client_webrtc.stop_session()
            self.client_webrtc = None
        super().closeEvent(event)

    def refresh_theme_labels(self, effective):
        is_dark = (effective == "dark")
        sub_fg = "#a1a1aa" if is_dark else "#71717a"
        card_bg = "#18181b" if is_dark else "#f4f4f5"
        card_border = "#27272a" if is_dark else "#e4e4e7"
        if hasattr(self, "lbl_scene_count"):
            self.lbl_scene_count.setStyleSheet(f"font-size: 11px; color: {sub_fg};")
        if hasattr(self, "lbl_audio_count"):
            self.lbl_audio_count.setStyleSheet(f"font-size: 11px; color: {sub_fg};")
        if hasattr(self, "grp_host_p2p_widget"):
            self.grp_host_p2p_widget.setStyleSheet(f"QFrame {{ background-color: {card_bg}; border: 1px solid {card_border}; border-radius: 6px; }}")
        if hasattr(self, "grp_client_p2p_widget"):
            self.grp_client_p2p_widget.setStyleSheet(f"QFrame {{ background-color: {card_bg}; border: 1px solid #0284c7; border-radius: 6px; }}")
        if hasattr(self, "grp_permissions"):
            self.grp_permissions.setStyleSheet(f"QGroupBox {{ border: 1px solid {card_border}; border-radius: 6px; margin-top: 10px; }}")
        if hasattr(self, "scroll_matrix"):
            self.scroll_matrix.setStyleSheet(f"QScrollArea {{ background-color: {card_bg}; border: 1px solid {card_border}; border-radius: 6px; }}")
