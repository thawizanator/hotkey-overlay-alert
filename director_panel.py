import sys
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame, QGridLayout, QApplication
)
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QIcon

class SceneCardButton(QPushButton):
    """Custom rectangular scene card with distinct colored border and active glow."""
    def __init__(self, scene_id, name, color_hex="#22c55e", parent=None):
        super().__init__(parent)
        self.scene_id = scene_id
        self.scene_name = name
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

    def update_data(self, name, color_hex):
        self.scene_name = name
        self.accent_color = color_hex
        self._update_style()

    def _update_style(self):
        bg = "#22222a" if self.is_active else "#141418"
        border_width = "3px" if self.is_active else "2px"
        border_color = self.accent_color
        status_text = "● LIVE" if self.is_active else "READY"
        status_color = self.accent_color if self.is_active else "#71717a"
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: #ffffff;
                border: {border_width} solid {border_color};
                border-radius: 6px;
                padding: 4px;
                text-align: center;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #2b2b36;
                border-color: #ffffff;
            }}
        """)
        self.setText(f"{self.scene_name}\n\n[{status_text}]")


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
        self.setFixedSize(68, 38)
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
                font-size: 10px;
                padding: 2px;
            }}
            QPushButton:hover {{
                background-color: {'#ef4444' if self.is_muted else '#3f3f46'};
                border-color: #ffffff;
            }}
        """)
        self.setText(f"{self.audio_name}\n[{status_text}]")


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
        self.lbl_name.setStyleSheet("font-size: 10px; font-weight: 600; color: #d4d4d8;")
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

    def _on_slider_moved(self, val):
        self.lbl_val.setText(f"{val}%")
        self.value_changed.emit(self.fader_id, val)


class DirectorPanelWindow(QWidget):
    """Floating control dock positioned on the chosen monitor directly above the Windows taskbar."""
    panel_closed = pyqtSignal()
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
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self.scene_buttons = []
        self.audio_buttons = []
        self.volume_faders = []
        self.active_scene_index = 0
        self._drag_pos = None

        self._build_ui()

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

    def load_configuration(self, scenes=None, audio=None, faders=None):
        """Builds or rebuilds the dynamic scene cards, audio buttons, and faders."""
        # 1. Populate Scene Cards (Up to 5)
        scenes = scenes or self.DEFAULT_SCENES
        # Clear existing
        for b in self.scene_buttons:
            b.setParent(None)
        self.scene_buttons.clear()

        for i, sc in enumerate(scenes[:5]):
            btn = SceneCardButton(i, sc.get("name", f"Scene {i+1}"), sc.get("color", "#22c55e"), self)
            if i == self.active_scene_index:
                btn.set_active(True)
            btn.clicked.connect(lambda chk, idx=i, n=btn.scene_name: self._on_scene_clicked(idx, n))
            self.lay_scenes_row.addWidget(btn)
            self.scene_buttons.append(btn)

        # 2. Populate Audio Mute Toggles (2 rows of 3)
        audio = audio or self.DEFAULT_AUDIO
        for b in self.audio_buttons:
            b.setParent(None)
        self.audio_buttons.clear()

        for i, a in enumerate(audio[:6]):
            row = i // 3
            col = i % 3
            btn = AudioMuteButton(i, a.get("name", f"Audio {i+1}"), a.get("muted", False), self)
            btn.toggled_mute.connect(lambda aid, m, n=btn.audio_name: self.audio_toggled.emit(aid, n, m))
            self.lay_audio_grid.addWidget(btn, row, col)
            self.audio_buttons.append(btn)

        # 3. Populate Volume Faders (3 Sliders)
        faders = faders or self.DEFAULT_FADERS
        for f in self.volume_faders:
            f.setParent(None)
        self.volume_faders.clear()

        for i, f in enumerate(faders[:3]):
            fader = VolumeFaderWidget(i, f.get("name", f"Audio {i+1}"), f.get("volume", 75), self)
            fader.value_changed.connect(lambda fid, v, n=fader.fader_name: self.volume_adjusted.emit(fid, n, v))
            self.lay_vol_row.addWidget(fader)
            self.volume_faders.append(fader)

    def _on_scene_clicked(self, scene_id, name):
        self.active_scene_index = scene_id
        for i, b in enumerate(self.scene_buttons):
            b.set_active(i == scene_id)
        self.scene_selected.emit(scene_id, name)

    def reposition_above_taskbar(self, monitor_index: int = 0):
        """Places the dock horizontally centered directly above the taskbar on the target screen."""
        screens = QApplication.screens()
        if not screens:
            return
        idx = monitor_index if 0 <= monitor_index < len(screens) else 0
        screen = screens[idx]
        avail = screen.availableGeometry()

        dock_height = 154
        dock_width = min(1140, int(avail.width() * 0.96))
        
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
        self.panel_closed.emit()
        super().closeEvent(event)
