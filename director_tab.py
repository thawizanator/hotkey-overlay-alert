import os
import sys
import subprocess
import webbrowser
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QGroupBox, QListWidget, QListWidgetItem,
    QMessageBox, QDialog, QInputDialog, QColorDialog, QFormLayout, QScrollArea, QFrame,
    QCheckBox
)
from PyQt6.QtGui import QColor, QIcon

from director_panel import DirectorPanelWindow
import theme_manager
from debug_logger import log_debug

from streamlabs_client import get_streamlabs_client

def obfuscate_str(data_str: str, key: int = 140) -> str:
    if not data_str:
        return ""
    return "".join(chr(ord(c) ^ key) for c in data_str)

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

class SceneEditDialog(QDialog):
    """Dialog to add or modify a scene card with live Streamlabs scene selection."""
    def __init__(self, name="New Scene", color_hex="#22c55e", available_scenes=None, scene_id=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Scene Card")
        self.setFixedSize(360, 200)
        self.chosen_color = color_hex
        self.raw_id = scene_id or ""

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

        btn_box = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def _on_scene_combo_changed(self, idx):
        if idx > 0:
            text = self.combo_scenes.currentText().replace("🎬 ", "")
            self.edit_name.setText(text)
            self.raw_id = self.combo_scenes.currentData() or ""

    def _pick_color(self):
        col = QColorDialog.getColor(QColor(self.chosen_color), self, "Select Scene Border Color")
        if col.isValid():
            self.chosen_color = col.name()
            self._update_color_preview()

    def _update_color_preview(self):
        self.lbl_color_preview.setStyleSheet(f"background-color: {self.chosen_color}; border: 1px solid #ffffff; border-radius: 4px;")

    def get_data(self):
        return self.edit_name.text().strip() or "Untitled Scene", self.chosen_color, self.raw_id


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
    def __init__(self, main_win):
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
        ]

        # Initialize Streamlabs client & wire signals
        self.slobs_client = get_streamlabs_client()
        self.slobs_client.connected.connect(self._update_slobs_status_ui)
        self.slobs_client.disconnected.connect(self._update_slobs_status_ui)
        self.slobs_client.scene_switched.connect(self._update_slobs_status_ui)
        self.slobs_client.scenes_updated.connect(self._on_slobs_scenes_updated)
        self.slobs_client.audio_sources_updated.connect(self._on_slobs_audio_updated)

        self._build_ui()
        self.load_from_settings()

        # Initial Streamlabs check
        if not self.slobs_client.is_connected():
            self.slobs_client.connect_client()
        self._update_slobs_status_ui()
        self._refresh_fader_combos()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # Scroll area for compact height
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(8)

        # ------------------ GROUP 1: REMOTE AUTH & MONITOR ------------------
        grp_conn = QGroupBox("Streamlabs Connection & Target Display")
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
        lay_slobs_box.setContentsMargins(8, 5, 8, 5)
        lay_slobs_box.setSpacing(8)

        self.lbl_slobs_status = QLabel("Checking Streamlabs Desktop...")
        self.lbl_slobs_status.setStyleSheet("font-size: 11px;")
        self.lbl_slobs_status.setTextFormat(Qt.TextFormat.RichText)
        lay_slobs_box.addWidget(self.lbl_slobs_status, 1)

        self.btn_reconnect_slobs = QPushButton("🔄 Reconnect")
        self.btn_reconnect_slobs.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_reconnect_slobs.clicked.connect(self._manual_reconnect_slobs)
        lay_slobs_box.addWidget(self.btn_reconnect_slobs)
        lay_conn.addWidget(self.frame_slobs_status)

        # Connection Mode selection row
        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Connection Mode:"))
        self.combo_conn_mode = QComboBox()
        self.combo_conn_mode.addItem("🖥️  Local PC (Named Pipe — Auto / Zero-Config)", "local")
        self.combo_conn_mode.addItem("🌐  Remote LAN PC (WebSocket — Port 59650)", "remote")
        self.combo_conn_mode.currentIndexChanged.connect(self._on_conn_mode_changed)
        row_mode.addWidget(self.combo_conn_mode, 1)

        self.btn_autodetect = QPushButton("⚡ Auto-Detect Local Token")
        self.btn_autodetect.setToolTip("Queries local Streamlabs Desktop on this PC to automatically discover its API Token, port, and LAN IP.")
        self.btn_autodetect.setStyleSheet("font-size: 11px; padding: 2px 8px;")
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
        self.lbl_local_notice.setStyleSheet("font-size: 10px; color: #a1a1aa; padding-left: 2px;")
        lay_conn.addWidget(self.lbl_local_notice)

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

        scroll_layout.addWidget(grp_conn)

        # ------------------ GROUP 2: SCENE TOGGLES (MAX 5) ------------------
        grp_scenes = QGroupBox("Scene Toggles (Limit: 5)")
        lay_sc = QVBoxLayout(grp_scenes)
        lay_sc.setSpacing(4)

        sc_btn_row = QHBoxLayout()
        self.lbl_scene_count = QLabel("Active Scenes: (5 / 5)")
        self.lbl_scene_count.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        sc_btn_row.addWidget(self.lbl_scene_count)
        sc_btn_row.addStretch()

        self.btn_autodetect_scenes = QPushButton("📥 Auto-Detect")
        self.btn_autodetect_scenes.setStyleSheet("font-size: 11px; padding: 2px 6px; font-weight: 600;")
        self.btn_autodetect_scenes.setToolTip("Automatically import your live scenes from Streamlabs Desktop")
        self.btn_autodetect_scenes.clicked.connect(self._auto_detect_scenes)
        sc_btn_row.addWidget(self.btn_autodetect_scenes)

        self.btn_add_scene = QPushButton("➕ Add")
        self.btn_add_scene.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_add_scene.clicked.connect(self._add_scene)
        sc_btn_row.addWidget(self.btn_add_scene)

        self.btn_edit_scene = QPushButton("✏️ Edit")
        self.btn_edit_scene.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_edit_scene.clicked.connect(self._edit_scene)
        sc_btn_row.addWidget(self.btn_edit_scene)

        self.btn_rem_scene = QPushButton("🗑️ Remove")
        self.btn_rem_scene.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_rem_scene.clicked.connect(self._remove_scene)
        sc_btn_row.addWidget(self.btn_rem_scene)
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
        self.list_scenes.setFixedHeight(102)
        self.list_scenes.setStyleSheet(slim_list_qss)
        lay_sc.addWidget(self.list_scenes)
        scroll_layout.addWidget(grp_scenes)

        # ------------------ GROUP 3: AUDIO MUTE TOGGLES ------------------
        grp_audio = QGroupBox("Audio Mute / Unmute Toggles (Up to 6)")
        lay_au = QVBoxLayout(grp_audio)
        lay_au.setSpacing(4)

        au_btn_row = QHBoxLayout()
        self.lbl_audio_count = QLabel("Active Audio Toggles: (6 / 6)")
        self.lbl_audio_count.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        au_btn_row.addWidget(self.lbl_audio_count)
        au_btn_row.addStretch()

        self.btn_autodetect_audio = QPushButton("📥 Auto-Detect")
        self.btn_autodetect_audio.setStyleSheet("font-size: 11px; padding: 2px 6px; font-weight: 600;")
        self.btn_autodetect_audio.setToolTip("Automatically import your active audio mixer sources from Streamlabs Desktop")
        self.btn_autodetect_audio.clicked.connect(self._auto_detect_audio)
        au_btn_row.addWidget(self.btn_autodetect_audio)

        self.btn_add_audio = QPushButton("➕ Add")
        self.btn_add_audio.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_add_audio.clicked.connect(self._add_audio)
        au_btn_row.addWidget(self.btn_add_audio)

        self.btn_edit_audio = QPushButton("✏️ Edit")
        self.btn_edit_audio.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_edit_audio.clicked.connect(self._edit_audio)
        au_btn_row.addWidget(self.btn_edit_audio)

        self.btn_rem_audio = QPushButton("🗑️ Remove")
        self.btn_rem_audio.setStyleSheet("font-size: 11px; padding: 2px 6px;")
        self.btn_rem_audio.clicked.connect(self._remove_audio)
        au_btn_row.addWidget(self.btn_rem_audio)
        lay_au.addLayout(au_btn_row)

        self.list_audio = QListWidget()
        self.list_audio.setFixedHeight(120)
        self.list_audio.setStyleSheet(slim_list_qss)
        lay_au.addWidget(self.list_audio)
        scroll_layout.addWidget(grp_audio)

        # ------------------ GROUP 4: VOLUME FADERS (3 SLIDERS) ------------------
        grp_faders = QGroupBox("Volume Sliders (3 Channels)")
        lay_fd = QGridLayout(grp_faders)
        lay_fd.setHorizontalSpacing(10)
        lay_fd.setVerticalSpacing(8)
        lay_fd.setContentsMargins(10, 8, 10, 8)

        lay_fd.addWidget(QLabel("Slider 1:"), 0, 0)
        self.edit_fader1 = NoScrollComboBox()
        self.edit_fader1.currentTextChanged.connect(self._on_settings_changed)
        self.edit_fader1.activated.connect(lambda idx: self._on_fader_combo_activated(self.edit_fader1, idx))
        lay_fd.addWidget(self.edit_fader1, 0, 1)

        lay_fd.addWidget(QLabel("Slider 2:"), 0, 2)
        self.edit_fader2 = NoScrollComboBox()
        self.edit_fader2.currentTextChanged.connect(self._on_settings_changed)
        self.edit_fader2.activated.connect(lambda idx: self._on_fader_combo_activated(self.edit_fader2, idx))
        lay_fd.addWidget(self.edit_fader2, 0, 3)

        lay_fd.addWidget(QLabel("Slider 3:"), 1, 0)
        self.edit_fader3 = NoScrollComboBox()
        self.edit_fader3.currentTextChanged.connect(self._on_settings_changed)
        self.edit_fader3.activated.connect(lambda idx: self._on_fader_combo_activated(self.edit_fader3, idx))
        lay_fd.addWidget(self.edit_fader3, 1, 1)

        lay_fd.setColumnStretch(1, 1)
        lay_fd.setColumnStretch(3, 1)
        scroll_layout.addWidget(grp_faders)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # ------------------ MASTER LAUNCH / CLOSE BUTTON ------------------
        self.btn_launch_panel = QPushButton("🚀 Launch Director Panel")
        self.btn_launch_panel.setObjectName("btnLaunchDirector")
        self.btn_launch_panel.setFixedHeight(36)
        self.btn_launch_panel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_launch_button_state(is_open=False)
        self.btn_launch_panel.clicked.connect(self.toggle_director_panel)
        main_layout.addWidget(self.btn_launch_panel)

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
        self.lbl_scene_count.setText(f"Active Scenes: ({count} / 5)")
        self.btn_add_scene.setEnabled(count < 5)

    def _refresh_audio_list_ui(self):
        self.list_audio.clear()
        for i, a in enumerate(self.audio_toggles):
            it = QListWidgetItem(f"[{i+1}] {a['name']}")
            it.setSizeHint(QSize(0, 19))
            self.list_audio.addItem(it)
        count = len(self.audio_toggles)
        self.lbl_audio_count.setText(f"Active Audio Toggles: ({count} / 6)")
        self.btn_add_audio.setEnabled(count < 6)

    def _on_conn_mode_changed(self):
        is_remote = (self.combo_conn_mode.currentData() == "remote")
        self.row_remote_net_widget.setVisible(is_remote)
        self.row_api_widget.setVisible(is_remote)
        self.lbl_local_notice.setVisible(not is_remote)
        self.conn_mode = "remote" if is_remote else "local"
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
                f"💡 If configuring HotKey Overlay Alert on another PC on your LAN, enter these exact values on that second PC!"
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
        if self.slobs_client and self.slobs_client.is_connected():
            _, act_name = self.slobs_client.get_active_scene_info()
            act_str = f" — Active: <b>{act_name}</b>" if act_name else ""
            mode_tag = "Local Pipe" if self.slobs_client._mode == "local" else f"LAN {self.slobs_client._remote_host}:{self.slobs_client._remote_port}"
            self.lbl_slobs_status.setText(f"<span style='color: #22c55e; font-weight: bold;'>🟢 Streamlabs Desktop Connected</span> <span style='color: #a1a1aa; font-size: 10px;'>({mode_tag})</span>{act_str}")
            self._refresh_fader_combos()
        else:
            mode_str = "local PC" if getattr(self, "conn_mode", "local") == "local" else "remote LAN PC"
            self.lbl_slobs_status.setText(f"<span style='color: #ef4444; font-weight: bold;'>🔴 Streamlabs Desktop Disconnected</span> <span style='color: #a1a1aa;'>(Launch Streamlabs Desktop on {mode_str} to link)</span>")

    def _manual_reconnect_slobs(self):
        if self.slobs_client:
            self.slobs_client.disconnect_client()
            mode = self.combo_conn_mode.currentData() if hasattr(self, "combo_conn_mode") else "local"
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
            source_names = ["Mic", "Game", "Music", "Discord", "Desktop", "Alerts"]

        for combo, default_val in [
            (self.edit_fader1, "Mic"),
            (self.edit_fader2, "Game"),
            (self.edit_fader3, "Music")
        ]:
            if not hasattr(self, "edit_fader1"):
                continue
            cur = combo.currentText() or default_val
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

        palette = ["#22c55e", "#0284c7", "#ea580c", "#a855f7", "#ef4444"]
        self.scenes = []
        for i, sc in enumerate(scenes[:5]):
            self.scenes.append({
                "name": sc.get("name", f"Scene {i+1}"),
                "id": sc.get("id", ""),
                "color": palette[i % len(palette)]
            })
        self._refresh_scene_list_ui()
        self._on_settings_changed()
        if self.is_panel_open():
            fader_data = [
                {"name": self.edit_fader1.currentText().strip() or "Audio 1", "volume": self.faders[0].get("volume", 80)},
                {"name": self.edit_fader2.currentText().strip() or "Audio 2", "volume": self.faders[1].get("volume", 75)},
                {"name": self.edit_fader3.currentText().strip() or "Audio 3", "volume": self.faders[2].get("volume", 60)},
            ]
            self.panel_window.load_configuration(self.scenes, self.audio_toggles, fader_data)
        QMessageBox.information(self, "Scenes Detected", f"Successfully auto-detected {len(self.scenes)} scenes from Streamlabs Desktop!")

    def _auto_detect_audio(self):
        sources = self.slobs_client.fetch_audio_sources()
        if not sources:
            sources = self.slobs_client.get_cached_audio_sources()
        if not sources:
            QMessageBox.warning(self, "Streamlabs Not Connected", "Could not detect audio sources from Streamlabs Desktop.\n\nPlease make sure Streamlabs Desktop is running.")
            return

        priority_keywords = ["mic", "discord", "spotify", "music", "game", "desktop", "alert", "chat"]
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
            if n and n not in unique_names:
                unique_names.add(n)
                cleaned_sources.append(s)

        cleaned_sources.sort(key=score_source)

        self.audio_toggles = []
        for s in cleaned_sources[:6]:
            self.audio_toggles.append({
                "name": s.get("name"),
                "id": s.get("sourceId") or s.get("id", ""),
                "muted": bool(s.get("muted", False))
            })
        self._refresh_audio_list_ui()
        self._on_settings_changed()
        self._refresh_fader_combos()
        if self.is_panel_open():
            fader_data = [
                {"name": self.edit_fader1.currentText().strip() or "Audio 1", "volume": self.faders[0].get("volume", 80)},
                {"name": self.edit_fader2.currentText().strip() or "Audio 2", "volume": self.faders[1].get("volume", 75)},
                {"name": self.edit_fader3.currentText().strip() or "Audio 3", "volume": self.faders[2].get("volume", 60)},
            ]
            self.panel_window.load_configuration(self.scenes, self.audio_toggles, fader_data)
        QMessageBox.information(self, "Audio Sources Detected", f"Successfully auto-detected {len(self.audio_toggles)} audio sources from Streamlabs Desktop!")

    def _add_scene(self):
        if len(self.scenes) >= 5:
            QMessageBox.information(self, "Limit Reached", "A maximum of 5 scenes can be configured on the panel.")
            return
        avail = self.slobs_client.get_cached_scenes() if self.slobs_client else []
        dlg = SceneEditDialog(f"Scene {len(self.scenes)+1}", "#22c55e", available_scenes=avail, parent=self)
        if dlg.exec():
            n, c, raw_id = dlg.get_data()
            self.scenes.append({"name": n, "color": c, "id": raw_id})
            self._refresh_scene_list_ui()
            self._on_settings_changed()
            if self.is_panel_open():
                self.panel_window.load_configuration(self.scenes, self.audio_toggles, self.faders)

    def _edit_scene(self):
        row = self.list_scenes.currentRow()
        if 0 <= row < len(self.scenes):
            sc = self.scenes[row]
            avail = self.slobs_client.get_cached_scenes() if self.slobs_client else []
            dlg = SceneEditDialog(sc["name"], sc.get("color", "#22c55e"), available_scenes=avail, scene_id=sc.get("id"), parent=self)
            if dlg.exec():
                n, c, raw_id = dlg.get_data()
                self.scenes[row] = {"name": n, "color": c, "id": raw_id}
                self._refresh_scene_list_ui()
                self._on_settings_changed()
                if self.is_panel_open():
                    self.panel_window.load_configuration(self.scenes, self.audio_toggles, self.faders)

    def _remove_scene(self):
        row = self.list_scenes.currentRow()
        if 0 <= row < len(self.scenes):
            self.scenes.pop(row)
            self._refresh_scene_list_ui()
            self._on_settings_changed()
            if self.is_panel_open():
                self.panel_window.load_configuration(self.scenes, self.audio_toggles, self.faders)

    def _add_audio(self):
        if len(self.audio_toggles) >= 6:
            QMessageBox.information(self, "Limit Reached", "A maximum of 6 audio mute toggles can be configured.")
            return
        avail = self.slobs_client.get_cached_audio_sources() if self.slobs_client else []
        dlg = AudioEditDialog(f"Audio {len(self.audio_toggles)+1}", available_sources=avail, parent=self)
        if dlg.exec():
            n, raw_id = dlg.get_data()
            self.audio_toggles.append({"name": n, "id": raw_id, "muted": False})
            self._refresh_audio_list_ui()
            self._on_settings_changed()
            if self.is_panel_open():
                self.panel_window.load_configuration(self.scenes, self.audio_toggles, self.faders)

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
                    self.panel_window.load_configuration(self.scenes, self.audio_toggles, self.faders)

    def _remove_audio(self):
        row = self.list_audio.currentRow()
        if 0 <= row < len(self.audio_toggles):
            self.audio_toggles.pop(row)
            self._refresh_audio_list_ui()
            self._on_settings_changed()
            if self.is_panel_open():
                self.panel_window.load_configuration(self.scenes, self.audio_toggles, self.faders)

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

        fader_data = [
            {"name": self.edit_fader1.currentText().strip() or "Audio 1", "volume": self.faders[0].get("volume", 80)},
            {"name": self.edit_fader2.currentText().strip() or "Audio 2", "volume": self.faders[1].get("volume", 75)},
            {"name": self.edit_fader3.currentText().strip() or "Audio 3", "volume": self.faders[2].get("volume", 60)},
        ]
        self.panel_window.load_configuration(self.scenes, self.audio_toggles, fader_data)
        
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
        from PyQt6.QtCore import QTimer
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

    def _on_settings_changed(self):
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
        if hasattr(self, "edit_fader1"):
            self.faders[0]["name"] = self.edit_fader1.currentText().strip()
        if hasattr(self, "edit_fader2"):
            self.faders[1]["name"] = self.edit_fader2.currentText().strip()
        if hasattr(self, "edit_fader3"):
            self.faders[2]["name"] = self.edit_fader3.currentText().strip()
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
            fader_data = [
                {"name": self.faders[0]["name"] or "Audio 1", "volume": self.faders[0].get("volume", 80)},
                {"name": self.faders[1]["name"] or "Audio 2", "volume": self.faders[1].get("volume", 75)},
                {"name": self.faders[2]["name"] or "Audio 3", "volume": self.faders[2].get("volume", 60)},
            ]
            self.panel_window.update_faders(fader_data)

    def export_settings(self) -> dict:
        return {
            "conn_mode": self.combo_conn_mode.currentData() if hasattr(self, "combo_conn_mode") else "local",
            "remote_host": self.edit_remote_host.text().strip() if hasattr(self, "edit_remote_host") else "127.0.0.1",
            "remote_port": self.edit_remote_port.text().strip() if hasattr(self, "edit_remote_port") else "59650",
            "api_key_obf": obfuscate_str(self.edit_api_key.text()),
            "stream_url": self.edit_stream_url.text().strip(),
            "target_monitor": self.combo_monitor.currentData() or 0,
            "app_mode": self.chk_app_mode.isChecked() if hasattr(self, "chk_app_mode") else True,
            "scenes": self.scenes,
            "audio_toggles": self.audio_toggles,
            "faders": [
                {"name": self.edit_fader1.currentText().strip() or "Mic", "volume": self.faders[0].get("volume", 80)},
                {"name": self.edit_fader2.currentText().strip() or "Game", "volume": self.faders[1].get("volume", 75)},
                {"name": self.edit_fader3.currentText().strip() or "Music", "volume": self.faders[2].get("volume", 60)},
            ]
        }

    def load_from_settings(self, settings_override: Optional[dict] = None):
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
            self.scenes = d.get("scenes", self.scenes)
            self.audio_toggles = d.get("audio_toggles", self.audio_toggles)
            self.faders = d.get("faders", self.faders)
            if len(self.faders) >= 3 and hasattr(self, "edit_fader1"):
                for combo, default_val, idx in [
                    (self.edit_fader1, "Mic", 0),
                    (self.edit_fader2, "Game", 1),
                    (self.edit_fader3, "Music", 2)
                ]:
                    fname = self.faders[idx].get("name", default_val)
                    if combo.findText(fname) == -1:
                        combo.insertItem(0, fname)
                    combo.setCurrentText(fname)

        self.refresh_monitors_list()
        self._refresh_scene_list_ui()
        self._refresh_audio_list_ui()

    def save_to_settings(self):
        if hasattr(self.main_win, "overlay") and self.main_win.overlay:
            self.main_win.overlay.director_settings = self.export_settings()
            self.main_win.overlay.save_settings()

    def refresh_theme_labels(self, effective):
        is_dark = (effective == "dark")
        sub_fg = "#a1a1aa" if is_dark else "#71717a"
        if hasattr(self, "lbl_scene_count"):
            self.lbl_scene_count.setStyleSheet(f"font-size: 11px; color: {sub_fg};")
        if hasattr(self, "lbl_audio_count"):
            self.lbl_audio_count.setStyleSheet(f"font-size: 11px; color: {sub_fg};")
