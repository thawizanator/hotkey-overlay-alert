import sys
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame, QGridLayout, QApplication, QStyleOption, QStyle
)
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QIcon

from streamlabs_client import get_streamlabs_client

class SceneCardButton(QPushButton):
    """Custom rectangular scene card with distinct colored border and active glow."""
    def __init__(self, scene_id, name, color_hex="#22c55e", raw_id=None, parent=None):
        super().__init__(parent)
        self.scene_id = scene_id
        self.scene_name = name
        self.scene_raw_id = raw_id
        self.accent_color = color_hex
        self.is_active = False
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(84)
        self.setMinimumWidth(100)
        self._update_style()

    def set_active(self, active: bool):
        self.is_active = active
        self.setChecked(active)
        self._update_style()

    def update_data(self, name, color_hex, raw_id=None):
        self.scene_name = name
        self.accent_color = color_hex
        if raw_id:
            self.scene_raw_id = raw_id
        self._update_style()

    def _update_style(self):
        bg = "#22222a" if self.is_active else "#141418"
        border_width = "3px" if self.is_active else "2px"
        border_color = self.accent_color
        status_text = "● LIVE" if self.is_active else "READY"
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: #ffffff;
                border: {border_width} solid {border_color};
                border-radius: 6px;
                padding: 4px;
                text-align: center;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #2b2b36;
                border-color: #ffffff;
            }}
        """)
        disp_name = self.scene_name
        if len(disp_name) > 22:
            disp_name = disp_name[:20] + "…"
        self.setText(f"{disp_name}\n\n[{status_text}]")


class AudioMuteButton(QPushButton):
    """Toggle button for audio muting with red muted badge."""
    toggled_mute = pyqtSignal(int, bool)  # (audio_id, is_muted)

    def __init__(self, audio_id, name, is_muted=False, parent=None):
        super().__init__(parent)
        self.audio_id = audio_id
        self.audio_name = name
        self.is_muted = is_muted
        self.setCheckable(True)
        self.setChecked(is_muted)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(92, 40)
        self._update_style()
        self.clicked.connect(self._on_click)

    def _on_click(self):
        self.is_muted = not self.is_muted
        self.setChecked(self.is_muted)
        self._update_style()
        self.toggled_mute.emit(self.audio_id, self.is_muted)

    def set_muted(self, muted: bool):
        self.is_muted = muted
        self.setChecked(muted)
        self._update_style()

    def set_muted_silently(self, muted: bool):
        """Updates mute state visually without triggering toggled_mute signal."""
        self.is_muted = muted
        self.blockSignals(True)
        self.setChecked(muted)
        self.blockSignals(False)
        self._update_style()

    def _update_style(self):
        if self.is_muted:
            bg = "#dc2626"
            fg = "#ffffff"
            status_text = "MUTED"
            border = "#b91c1c"
        else:
            bg = "#27272a"
            fg = "#f4f4f5"
            status_text = "ON"
            border = "#3f3f46"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 5px;
                font-weight: bold;
                font-size: 9px;
                padding: 1px 3px;
            }}
            QPushButton:hover {{
                background-color: {'#ef4444' if self.is_muted else '#3f3f46'};
                border-color: #ffffff;
            }}
        """)
        disp_name = self.audio_name
        if len(disp_name) > 13:
            disp_name = disp_name[:12] + "…"
        self.setText(f"{disp_name}\n[{status_text}]")


class VolumeFaderWidget(QWidget):
    """Vertical volume slider with label and value readout."""
    value_changed = pyqtSignal(int, int)  # (fader_id, value 0-100)

    def __init__(self, fader_id, name="Audio", initial_val=75, parent=None):
        super().__init__(parent)
        self.fader_id = fader_id
        self.fader_name = name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_name = QLabel(name)
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setMaximumWidth(88)
        self.lbl_name.setStyleSheet("font-size: 9px; font-weight: 600; color: #d4d4d8;")
        layout.addWidget(self.lbl_name)

        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setRange(0, 100)
        self.slider.setValue(initial_val)
        self.slider.setFixedHeight(75)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setStyleSheet("""
            QSlider::groove:vertical {
                background: #27272a;
                width: 6px;
                border-radius: 3px;
            }
            QSlider::sub-page:vertical {
                background: #3f3f46;
                border-radius: 3px;
            }
            QSlider::add-page:vertical {
                background: #0284c7;
                border-radius: 3px;
            }
            QSlider::handle:vertical {
                background: #00a8ff;
                border: 1px solid #ffffff;
                height: 14px;
                margin: 0 -4px;
                border-radius: 3px;
            }
            QSlider::handle:vertical:hover {
                background: #38bdf8;
            }
        """)
        self.slider.valueChanged.connect(self._on_slider_moved)
        layout.addWidget(self.slider, 0, Qt.AlignmentFlag.AlignCenter)

        self.lbl_val = QLabel(f"{initial_val}%")
        self.lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_val.setStyleSheet("font-size: 9px; color: #a1a1aa; font-family: monospace;")
        layout.addWidget(self.lbl_val)

    def set_label(self, name: str):
        self.fader_name = name
        self.lbl_name.setText(name)

    def set_value_silently(self, val: int):
        """Updates slider position visually without emitting value_changed signal."""
        clamped = max(0, min(100, int(val)))
        self.slider.blockSignals(True)
        self.slider.setValue(clamped)
        self.lbl_val.setText(f"{clamped}%")
        self.slider.blockSignals(False)

    def _on_slider_moved(self, val):
        self.lbl_val.setText(f"{val}%")
        self.value_changed.emit(self.fader_id, val)


class DirectorPanelWindow(QWidget):
    """Floating control dock positioned on the chosen monitor directly above the Windows taskbar."""
    panel_closed = pyqtSignal()
    settings_requested = pyqtSignal()
    scene_selected = pyqtSignal(int, str)
    audio_toggled = pyqtSignal(int, str, bool)
    volume_adjusted = pyqtSignal(int, str, int)

    DEFAULT_SCENES = [
        {"name": "Scene 1", "color": "#22c55e"},
        {"name": "Scene 2", "color": "#0284c7"},
        {"name": "Scene 3", "color": "#ea580c"},
        {"name": "Scene 4", "color": "#a855f7"},
        {"name": "Scene 5", "color": "#ef4444"},
    ]

    DEFAULT_AUDIO = [
        {"name": "Mic", "muted": False},
        {"name": "Game", "muted": False},
        {"name": "Music", "muted": False},
        {"name": "Discord", "muted": False},
        {"name": "Alerts", "muted": False},
        {"name": "SFX", "muted": False},
    ]

    DEFAULT_FADERS = [
        {"name": "Audio 1", "volume": 80},
        {"name": "Audio 2", "volume": 75},
        {"name": "Audio 3", "volume": 60},
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DirectorPanelWindow")
        self.setWindowTitle("🎬 Stream Director Dock")
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)

        self.scene_buttons = []
        self.audio_buttons = []
        self.volume_faders = []
        self.active_scene_index = 0
        self._drag_pos = None

        self._build_ui()

        # Connect to StreamlabsClient for live IPC control & event sync
        self.slobs_client = get_streamlabs_client()
        self.slobs_client.connected.connect(self._on_slobs_connected)
        self.slobs_client.disconnected.connect(self._on_slobs_disconnected)
        self.slobs_client.scene_switched.connect(self._on_slobs_scene_switched)
        self.slobs_client.audio_muted_changed.connect(self._on_slobs_audio_muted_changed)
        self.slobs_client.audio_volume_changed.connect(self._on_slobs_audio_volume_changed)

        if self.slobs_client.is_connected():
            self._on_slobs_connected()
        else:
            self._on_slobs_disconnected()
            self.slobs_client.connect_client()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 6)
        root.setSpacing(4)

        # ------------------ TOP BAR (Drag handle + title + close) ------------------
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 0, 4, 0)
        top_bar.setSpacing(6)

        lbl_drag = QLabel("🎬  <b>STREAM DIRECTOR DOCK</b>")
        lbl_drag.setStyleSheet("font-size: 11px; color: #a1a1aa; letter-spacing: 0.5px;")
        top_bar.addWidget(lbl_drag)
        top_bar.addStretch()

        self.lbl_status = QLabel("<span style='color: #22c55e;'>● Connected</span>")
        self.lbl_status.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_status.setStyleSheet("font-size: 10px; padding-right: 6px;")
        top_bar.addWidget(self.lbl_status)

        btn_settings = QPushButton("⚙️")
        btn_settings.setFixedSize(20, 20)
        btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_settings.setToolTip("Open Stream Director Settings")
        btn_settings.setStyleSheet("""
            QPushButton {
                background: #27272a;
                color: #a1a1aa;
                border: 1px solid #3f3f46;
                border-radius: 10px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #3f3f46;
                color: #ffffff;
                border-color: #71717a;
            }
        """)
        btn_settings.clicked.connect(self.settings_requested.emit)
        top_bar.addWidget(btn_settings)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(20, 20)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setToolTip("Close Stream Director Dock")
        btn_close.setStyleSheet("""
            QPushButton {
                background: #27272a;
                color: #a1a1aa;
                border: 1px solid #3f3f46;
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #ef4444;
                color: #ffffff;
                border-color: #dc2626;
            }
        """)
        btn_close.clicked.connect(self.close)
        top_bar.addWidget(btn_close)
        root.addLayout(top_bar)

        # ------------------ MAIN CONTENT ROW ------------------
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(8)

        # SECTION 1: SCENE TOGGLES (Limit: 5)
        self.grp_scenes = QFrame()
        self.grp_scenes.setObjectName("cardScenes")
        self.grp_scenes.setStyleSheet("""
            QFrame#cardScenes {
                background-color: #121214;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        lay_scenes_box = QVBoxLayout(self.grp_scenes)
        lay_scenes_box.setContentsMargins(6, 4, 6, 4)
        lay_scenes_box.setSpacing(4)

        lbl_sec_scenes = QLabel("SCENE SELECTION")
        lbl_sec_scenes.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sec_scenes.setStyleSheet("font-size: 9px; font-weight: bold; color: #71717a; letter-spacing: 0.5px;")
        lay_scenes_box.addWidget(lbl_sec_scenes)

        self.lay_scenes_row = QHBoxLayout()
        self.lay_scenes_row.setSpacing(6)
        lay_scenes_box.addLayout(self.lay_scenes_row)
        content_row.addWidget(self.grp_scenes, 5)

        # SECTION 2: AUDIO MUTE TOGGLES (2x3 Grid)
        self.grp_audio = QFrame()
        self.grp_audio.setObjectName("cardAudio")
        self.grp_audio.setStyleSheet("""
            QFrame#cardAudio {
                background-color: #121214;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        lay_audio_box = QVBoxLayout(self.grp_audio)
        lay_audio_box.setContentsMargins(6, 4, 6, 4)
        lay_audio_box.setSpacing(4)

        lbl_sec_audio = QLabel("MUTE / UNMUTE AUDIO")
        lbl_sec_audio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sec_audio.setStyleSheet("font-size: 9px; font-weight: bold; color: #71717a; letter-spacing: 0.5px;")
        lay_audio_box.addWidget(lbl_sec_audio)

        self.lay_audio_grid = QGridLayout()
        self.lay_audio_grid.setSpacing(4)
        lay_audio_box.addLayout(self.lay_audio_grid)
        content_row.addWidget(self.grp_audio, 3)

        # SECTION 3: VOLUME ADJUST SLIDERS (3 Faders)
        self.grp_volume = QFrame()
        self.grp_volume.setObjectName("cardVolume")
        self.grp_volume.setStyleSheet("""
            QFrame#cardVolume {
                background-color: #121214;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        lay_vol_box = QVBoxLayout(self.grp_volume)
        lay_vol_box.setContentsMargins(6, 4, 6, 4)
        lay_vol_box.setSpacing(4)

        lbl_sec_vol = QLabel("VOLUME ADJUST")
        lbl_sec_vol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sec_vol.setStyleSheet("font-size: 9px; font-weight: bold; color: #71717a; letter-spacing: 0.5px;")
        lay_vol_box.addWidget(lbl_sec_vol)

        self.lay_vol_row = QHBoxLayout()
        self.lay_vol_row.setSpacing(8)
        self.lay_vol_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_vol_box.addLayout(self.lay_vol_row)
        content_row.addWidget(self.grp_volume, 2)

        root.addLayout(content_row)

        # Apply dark sleek dock styling
        self.setStyleSheet("""
            QWidget#DirectorPanelWindow {
                background-color: #0d0d0f;
                border: 2px solid #27272a;
                border-radius: 8px;
            }
        """)

        # Populate defaults
        self.load_configuration()

    def _clear_layout(self, layout):
        """Safely removes and deletes all child widgets and items from a layout."""
        if not layout:
            return
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def update_faders(self, faders_data: list):
        """Live updates existing fader labels and volume values in-place without destroying widgets or collapsing layouts."""
        if not faders_data:
            return
        for i, f_info in enumerate(faders_data[:len(self.volume_faders)]):
            fader_widget = self.volume_faders[i]
            name = f_info.get("name", f"Audio {i+1}")
            fader_widget.set_label(name)
            # Sync volume percent from Streamlabs if connected
            if hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
                vol = self.slobs_client.get_source_volume_percent(name)
                fader_widget.set_value_silently(vol)
            elif "volume" in f_info:
                fader_widget.set_value_silently(f_info["volume"])

    def load_configuration(self, scenes=None, audio=None, faders=None):
        """Builds or rebuilds the dynamic scene cards, audio buttons, and faders."""
        # 1. Populate Scene Cards (Up to 5)
        scenes = scenes or self.DEFAULT_SCENES
        # Clear existing
        self._clear_layout(self.lay_scenes_row)
        self.scene_buttons.clear()

        for i, sc in enumerate(scenes[:5]):
            btn = SceneCardButton(
                i,
                sc.get("name", f"Scene {i+1}"),
                sc.get("color", "#22c55e"),
                raw_id=sc.get("id"),
                parent=self
            )
            if i == self.active_scene_index:
                btn.set_active(True)
            btn.clicked.connect(lambda chk, idx=i, b=btn: self._on_scene_clicked(idx, b.scene_name, b))
            self.lay_scenes_row.addWidget(btn)
            self.scene_buttons.append(btn)

        # 2. Populate Audio Mute Toggles (2 rows of 3)
        audio = audio or self.DEFAULT_AUDIO
        self._clear_layout(self.lay_audio_grid)
        self.audio_buttons.clear()

        for i, a in enumerate(audio[:6]):
            row = i // 3
            col = i % 3
            btn = AudioMuteButton(i, a.get("name", f"Audio {i+1}"), a.get("muted", False), self)
            btn.toggled_mute.connect(lambda aid, m, b=btn: self._on_audio_toggled(aid, b.audio_name, m))
            self.lay_audio_grid.addWidget(btn, row, col)
            self.audio_buttons.append(btn)

        # 3. Populate Volume Faders (3 Sliders)
        faders = faders or self.DEFAULT_FADERS
        self._clear_layout(self.lay_vol_row)
        self.volume_faders.clear()

        for i, f in enumerate(faders[:3]):
            fader = VolumeFaderWidget(i, f.get("name", f"Audio {i+1}"), f.get("volume", 75), self)
            fader.value_changed.connect(lambda fid, v, fw=fader: self._on_volume_adjusted(fid, fw.fader_name, v))
            self.lay_vol_row.addWidget(fader)
            self.volume_faders.append(fader)

        if hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
            self._sync_with_slobs_state()

    def _on_scene_clicked(self, scene_id, name, btn):
        self.active_scene_index = scene_id
        for b in self.scene_buttons:
            b.set_active(b == btn)
        self.scene_selected.emit(scene_id, name)
        if hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
            target = getattr(btn, "scene_raw_id", None) or name
            self.slobs_client.make_scene_active(target)

    def _on_audio_toggled(self, aid, name, is_muted):
        self.audio_toggled.emit(aid, name, is_muted)
        if hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
            self.slobs_client.set_audio_muted(name, is_muted)

    def _on_volume_adjusted(self, fid, name, val):
        self.volume_adjusted.emit(fid, name, val)
        if hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
            self.slobs_client.set_audio_deflection(name, val / 100.0)

    def _on_slobs_connected(self):
        if hasattr(self, "lbl_status"):
            self.lbl_status.setText("<span style='color: #22c55e;'>● Connected</span>")
        self._sync_with_slobs_state()

    def _on_slobs_disconnected(self):
        if hasattr(self, "lbl_status"):
            self.lbl_status.setText("<span style='color: #ef4444;'>● Disconnected</span>")

    def _on_slobs_scene_switched(self, scene_id, scene_name):
        target = scene_name.strip().lower()
        for b in self.scene_buttons:
            b_name = b.scene_name.strip().lower()
            raw_id = getattr(b, "scene_raw_id", None)
            if b_name == target or (raw_id and raw_id == scene_id):
                b.set_active(True)
            else:
                b.set_active(False)

    def _on_slobs_audio_muted_changed(self, source_name_or_id, is_muted):
        target = source_name_or_id.strip().lower()
        for b in self.audio_buttons:
            b_name = b.audio_name.strip().lower()
            if b_name == target or b_name in target or target in b_name:
                b.set_muted_silently(is_muted)

    def _on_slobs_audio_volume_changed(self, source_name_or_id, deflection):
        target = source_name_or_id.strip().lower()
        for f in self.volume_faders:
            f_name = f.fader_name.strip().lower()
            if f_name == target or f_name in target or target in f_name:
                f.set_value_silently(int(round(deflection * 100)))

    def _sync_with_slobs_state(self):
        if not self.slobs_client or not self.slobs_client.is_connected():
            return
        # 1. Sync active scene
        sc_id, sc_name = self.slobs_client.get_active_scene_info()
        if sc_name:
            self._on_slobs_scene_switched(sc_id or "", sc_name)

        # 2. Sync audio buttons
        for b in self.audio_buttons:
            muted = self.slobs_client.get_source_muted_state(b.audio_name)
            b.set_muted_silently(muted)

        # 3. Sync volume faders
        for f in self.volume_faders:
            vol = self.slobs_client.get_source_volume_percent(f.fader_name)
            f.set_value_silently(vol)

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)

    def force_topmost(self):
        """Ensures the window stays on top at the OS level using Win32 API without stealing input focus."""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                user32.SetWindowPos.argtypes = [
                    wintypes.HWND, wintypes.HWND,
                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    wintypes.UINT
                ]
                user32.SetWindowPos.restype = wintypes.BOOL
                hwnd = wintypes.HWND(int(self.winId()))
                HWND_TOPMOST = wintypes.HWND(-1)
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                SWP_SHOWWINDOW = 0x0040
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
            except Exception:
                pass

    def reposition_above_taskbar(self, monitor_index: int = 0):
        """Places the dock horizontally centered directly above the taskbar on the target screen."""
        screens = QApplication.screens()
        if not screens:
            return
        idx = monitor_index if 0 <= monitor_index < len(screens) else 0
        screen = screens[idx]
        avail = screen.availableGeometry()

        self.adjustSize()
        hint = self.sizeHint()
        dock_height = max(hint.height(), 154)
        dock_width = min(1140, max(hint.width(), int(avail.width() * 0.96)))
        if dock_width > avail.width():
            dock_width = avail.width()
        
        # Position X centered on that screen, Y right above the taskbar
        pos_x = avail.x() + (avail.width() - dock_width) // 2
        pos_y = avail.bottom() - dock_height + 1

        self.setGeometry(pos_x, pos_y, dock_width, dock_height)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def closeEvent(self, event):
        if hasattr(self, "_topmost_timer") and self._topmost_timer:
            self._topmost_timer.stop()
        try:
            if hasattr(self, "slobs_client") and self.slobs_client:
                self.slobs_client.connected.disconnect(self._on_slobs_connected)
                self.slobs_client.disconnected.disconnect(self._on_slobs_disconnected)
                self.slobs_client.scene_switched.disconnect(self._on_slobs_scene_switched)
                self.slobs_client.audio_muted_changed.disconnect(self._on_slobs_audio_muted_changed)
                self.slobs_client.audio_volume_changed.disconnect(self._on_slobs_audio_volume_changed)
        except Exception:
            pass
        self.panel_closed.emit()
        super().closeEvent(event)
