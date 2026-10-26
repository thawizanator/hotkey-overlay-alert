import sys
import time
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame, QGridLayout, QApplication, QStyleOption, QStyle,
    QMenu, QSizeGrip
)
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QIcon

from streamlabs_client import get_streamlabs_client

class SceneCardButton(QPushButton):
    """Custom rectangular scene card with distinct colored border, active glow, and slot swapping context menu."""
    def __init__(self, scene_id, name, color_hex="#22c55e", raw_id=None, parent=None):
        super().__init__(parent)
        self.scene_id = scene_id
        self.scene_name = name
        self.scene_raw_id = raw_id
        self.accent_color = color_hex
        self.is_active = False
        self.is_locked = False
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setMinimumWidth(68)
        self._update_style()

    def set_active(self, active: bool):
        if getattr(self, "is_locked", False):
            self.is_active = False
            self.setChecked(False)
            return
        self.is_active = active
        self.setChecked(active)
        self._update_style()

    def set_locked(self, locked: bool):
        self.is_locked = locked
        self.setEnabled(not locked)
        if locked:
            self.setToolTip("🔒 Locked: Permission not granted by Streamer")
            self.is_active = False
            self.setChecked(False)
        else:
            self.setToolTip("Click to switch scene | Right-click to swap slot from pool")
        self._update_style()

    def update_data(self, name, color_hex, raw_id=None):
        self.scene_name = name
        self.accent_color = color_hex
        if raw_id is not None:
            self.scene_raw_id = raw_id
        self._update_style()

    def contextMenuEvent(self, event):
        panel = self.window()
        if not panel or not hasattr(panel, "pool_scenes"):
            return
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 4px;
                color: #ffffff;
                font-size: 11px;
            }
            QMenu::item {
                padding: 4px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #52525b;
            }
            QMenu::separator {
                height: 1px;
                background: #27272a;
                margin: 4px 0px;
            }
        """)
        title_act = menu.addAction("⇄ Swap Scene Slot:")
        title_act.setEnabled(False)
        menu.addSeparator()

        for sc in getattr(panel, "pool_scenes", []):
            sc_n = sc.get("name", "Scene")
            sc_c = sc.get("color", "#22c55e")
            sc_id = sc.get("id", "")
            permitted = panel.is_scene_permitted(sc_n, sc_id)
            if not permitted:
                act = menu.addAction(f"🎬 {sc_n} [🔒 LOCKED]")
                act.setEnabled(False)
            else:
                is_curr = (sc_n == self.scene_name or (sc_id and sc_id == getattr(self, "scene_raw_id", "")))
                prefix = "✓ " if is_curr else "   "
                act = menu.addAction(f"{prefix}🎬 {sc_n}")
                act.triggered.connect(lambda chk, s=sc: self._swap_to_scene(s))

        menu.addSeparator()
        if len(panel.scene_buttons) < 8 and len(panel.scene_buttons) < len(getattr(panel, "pool_scenes", [])):
            act_add = menu.addAction("➕ Add Scene Slot")
            act_add.triggered.connect(panel.add_scene_slot)
        if len(panel.scene_buttons) > 1:
            act_rem = menu.addAction("🗑️ Remove This Slot")
            act_rem.triggered.connect(lambda: panel.remove_scene_slot(self))

        menu.exec(event.globalPos())

    def _swap_to_scene(self, sc: dict):
        panel = self.window()
        self.update_data(sc.get("name", "Scene"), sc.get("color", "#22c55e"), raw_id=sc.get("id"))
        if hasattr(panel, "re_evaluate_scene_states"):
            panel.re_evaluate_scene_states()
        if hasattr(panel, "_sync_with_slobs_state"):
            panel._sync_with_slobs_state()

    @staticmethod
    def _get_contrast_color(hex_color: str) -> str:
        """Returns high-contrast text color ('#09090b' or '#ffffff') for a given background hex color."""
        try:
            c = hex_color.lstrip('#')
            if len(c) == 6:
                r = int(c[0:2], 16)
                g = int(c[2:4], 16)
                b = int(c[4:6], 16)
                luminance = (r * 299 + g * 587 + b * 114) / 1000
                if luminance > 160:
                    return "#09090b"
        except Exception:
            pass
        return "#ffffff"

    def _update_style(self):
        disp_name = self.scene_name
        if len(disp_name) > 13:
            disp_name = disp_name[:12] + "…"
        if getattr(self, "is_locked", False):
            self.setToolTip(f"🔒 {self.scene_name} (Permission locked)")
            self.setStyleSheet("""
                QPushButton {
                    background-color: #121214;
                    color: #52525b;
                    border: 1px dashed #3f3f46;
                    border-radius: 6px;
                    padding: 2px 4px;
                    text-align: center;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)
            self.setText(f"🔒 {disp_name}")
            return

        self.setToolTip(f"{self.scene_name}\n(Click to switch | Right-click to swap)")

        if self.is_active:
            # Solid vibrant fill with the configured scene accent color and dynamic contrast text
            bg = self.accent_color
            border = "2px solid #ffffff"
            text_color = self._get_contrast_color(self.accent_color)
            status_dot = "● "
            hover_bg = self.accent_color
        else:
            # Clean dark button with accent border
            bg = "#141418"
            border = f"2px solid {self.accent_color}"
            text_color = "#e4e4e7"
            status_dot = "🎬 "
            hover_bg = "#22222a"
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {text_color};
                border: {border};
                border-radius: 6px;
                padding: 2px 4px;
                text-align: center;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border-color: #ffffff;
            }}
        """)
        self.setText(f"{status_dot}{disp_name}")


class AudioMuteButton(QPushButton):
    """Toggle button for audio muting with red muted badge."""
    toggled_mute = pyqtSignal(int, bool)  # (audio_id, is_muted)

    def __init__(self, audio_id, name, is_muted=False, parent=None, raw_id=None):
        super().__init__(parent)
        self.audio_id = audio_id
        self.audio_name = name
        self.audio_raw_id = raw_id
        self.is_muted = is_muted
        self.is_locked = False
        self.setCheckable(True)
        self.setChecked(is_muted)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(92, 40)
        self._update_style()
        self.clicked.connect(self._on_click)

    def _on_click(self):
        if getattr(self, "is_locked", False):
            return
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

    def set_locked(self, locked: bool):
        self.is_locked = locked
        self.setEnabled(not locked)
        if locked:
            self.setToolTip("🔒 Locked: Permission not granted by Streamer")
        else:
            self.setToolTip("Click to toggle mute | Right-click to swap slot from pool")
        self._update_style()

    def contextMenuEvent(self, event):
        panel = self.window()
        if not panel or not hasattr(panel, "pool_audio"):
            return
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 4px;
                color: #ffffff;
                font-size: 11px;
            }
            QMenu::item {
                padding: 4px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #52525b;
            }
            QMenu::separator {
                height: 1px;
                background: #27272a;
                margin: 4px 0px;
            }
        """)
        title_act = menu.addAction("⇄ Swap Audio Mute Slot:")
        title_act.setEnabled(False)
        menu.addSeparator()

        for a in getattr(panel, "pool_audio", []):
            an = a.get("name", "Audio")
            aid = a.get("id", "")
            permitted = panel.is_audio_permitted(an)
            if not permitted:
                act = menu.addAction(f"🔊 {an} [🔒 LOCKED]")
                act.setEnabled(False)
            else:
                is_curr = (an == self.audio_name)
                prefix = "✓ " if is_curr else "   "
                act = menu.addAction(f"{prefix}🔊 {an}")
                act.triggered.connect(lambda chk, item=a: self._swap_to_audio(item))

        menu.addSeparator()
        if len(panel.audio_buttons) < 8 and len(panel.audio_buttons) < len(getattr(panel, "pool_audio", [])):
            act_add = menu.addAction("➕ Add Mute Slot")
            act_add.triggered.connect(panel.add_audio_slot)
        if len(panel.audio_buttons) > 1:
            act_rem = menu.addAction("🗑️ Remove This Slot")
            act_rem.triggered.connect(lambda: panel.remove_audio_slot(self))

        menu.exec(event.globalPos())

    def _swap_to_audio(self, a: dict):
        panel = self.window()
        self.audio_name = a.get("name", "Audio")
        self.audio_raw_id = a.get("id", "")
        self.set_muted_silently(a.get("muted", False))
        if hasattr(panel, "re_evaluate_audio_states"):
            panel.re_evaluate_audio_states()
        if hasattr(panel, "slobs_client") and panel.slobs_client and panel.slobs_client.is_connected():
            muted = panel.slobs_client.get_source_muted_state(self.audio_name)
            self.set_muted_silently(muted)

    def _update_style(self):
        disp_name = self.audio_name
        if len(disp_name) > 13:
            disp_name = disp_name[:12] + "…"
        if getattr(self, "is_locked", False):
            self.setStyleSheet("""
                QPushButton {
                    background-color: #18181b;
                    color: #52525b;
                    border: 1px dashed #27272a;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 9px;
                    padding: 1px 3px;
                }
            """)
            self.setText(f"{disp_name}\n[🔒 LOCKED]")
            return

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
        self.setText(f"{disp_name}\n[{status_text}]")


class ViewToggleButton(QPushButton):
    """Toggle button for live scene source visibility (e.g., SandMan View, Legal-View)."""
    toggled_visibility = pyqtSignal(str, bool)

    def __init__(self, name: str, is_visible: bool = False, hotkey_hint: str = "", parent=None):
        super().__init__(parent)
        self.source_name = name
        self.hotkey_hint = hotkey_hint
        self.is_visible = is_visible
        self.is_locked = False
        self.setCheckable(True)
        self.setChecked(is_visible)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)
        self.setMinimumWidth(85)
        self._update_style()
        self.clicked.connect(self._on_click)

    def _on_click(self):
        if getattr(self, "is_locked", False):
            return
        new_vis = not self.is_visible
        self.is_visible = new_vis
        self.setChecked(new_vis)
        self._update_style()
        self.toggled_visibility.emit(self.source_name, new_vis)

    def set_visibility_state(self, visible: bool):
        self.is_visible = visible
        self.blockSignals(True)
        self.setChecked(visible)
        self.blockSignals(False)
        self._update_style()

    def set_locked(self, locked: bool):
        self.is_locked = locked
        self.setEnabled(not locked)
        self._update_style()

    def _update_style(self):
        disp_name = self.source_name
        if len(disp_name) > 16:
            disp_name = disp_name[:14] + "…"
        if getattr(self, "is_locked", False):
            self.setStyleSheet("""
                QPushButton {
                    background-color: #121214;
                    color: #52525b;
                    border: 1px dashed #3f3f46;
                    border-radius: 6px;
                    padding: 2px 4px;
                    font-size: 9px;
                    font-weight: bold;
                }
            """)
            self.setText(f"🔒 {disp_name}")
            return

        if self.is_visible:
            bg = "#14291e"
            border = "2px solid #22c55e"
            color = "#4ade80"
            status = "SHOW"
        else:
            bg = "#18181b"
            border = "1px solid #3f3f46"
            color = "#a1a1aa"
            status = "HIDE"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                border: {border};
                border-radius: 6px;
                padding: 2px 4px;
                font-size: 9px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: #ffffff;
            }}
        """)
        hint_label = f" · {self.hotkey_hint}" if getattr(self, "hotkey_hint", "") else ""
        self.setText(f"👁️ {disp_name}\n[{status}{hint_label}]")
        if getattr(self, "hotkey_hint", ""):
            self.setToolTip(f"{self.source_name} ({self.hotkey_hint})\nClick to fire hotkey & toggle visibility in SLOBS")
        else:
            self.setToolTip(f"{self.source_name}\nClick to toggle visibility in SLOBS")


class SmoothSlider(QSlider):
    """
    Vertical volume slider providing continuous smooth scrubbing on direct click & drag,
    and granular 2% mouse wheel adjustments without discrete 10% jumps.
    """
    def __init__(self, orientation=Qt.Orientation.Vertical, parent=None):
        super().__init__(orientation, parent)
        self.setTracking(True)
        self.setSingleStep(1)
        self.setPageStep(5)

    def mousePressEvent(self, event):
        if not self.isEnabled():
            return
        if event.button() == Qt.MouseButton.LeftButton:
            val = self._pos_to_val(event.position().y())
            self.setValue(val)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.isEnabled():
            return
        if event.buttons() & Qt.MouseButton.LeftButton:
            val = self._pos_to_val(event.position().y())
            self.setValue(val)
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        if not self.isEnabled():
            return
        delta = event.angleDelta().y()
        if delta != 0:
            step = 2 if delta > 0 else -2
            new_val = max(self.minimum(), min(self.maximum(), self.value() + step))
            self.setValue(new_val)
            event.accept()
        else:
            super().wheelEvent(event)

    def _pos_to_val(self, pos_y: float) -> int:
        h = self.height()
        if h <= 0:
            return self.value()
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), int(pos_y), h, True
        )


class VolumeFaderWidget(QWidget):
    """Vertical volume slider with label and value readout."""
    value_changed = pyqtSignal(int, int)  # (fader_id, value 0-100)

    def __init__(self, fader_id, name="Audio", initial_val=75, parent=None):
        super().__init__(parent)
        self.fader_id = fader_id
        self.fader_name = name
        self.is_locked = False
        self._is_dragging = False
        self._pending_val = None
        self._last_interaction = 0.0

        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.setInterval(40)  # ~25 fps throttle to stay cleanly within security bouncer limit
        self._throttle_timer.timeout.connect(self._flush_pending_value)

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

        self.slider = SmoothSlider(Qt.Orientation.Vertical, self)
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
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.valueChanged.connect(self._on_slider_moved)
        layout.addWidget(self.slider, 0, Qt.AlignmentFlag.AlignCenter)

        self.lbl_val = QLabel(f"{initial_val}%")
        self.lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_val.setStyleSheet("font-size: 9px; color: #a1a1aa; font-family: monospace;")
        layout.addWidget(self.lbl_val)

    def set_label(self, name: str):
        self.fader_name = name
        self.lbl_name.setText(name)

    def set_locked(self, locked: bool):
        self.is_locked = locked
        self.slider.setEnabled(not locked)
        if locked:
            self.setToolTip("🔒 Locked: Permission not granted by Streamer")
            self.lbl_name.setStyleSheet("font-size: 9px; font-weight: 600; color: #52525b;")
            self.lbl_val.setText("🔒")
            self.lbl_val.setStyleSheet("font-size: 9px; color: #52525b; font-family: monospace;")
        else:
            self.setToolTip("Scroll wheel or drag to adjust | Right-click to swap channel from pool")
            self.lbl_name.setStyleSheet("font-size: 9px; font-weight: 600; color: #d4d4d8;")
            self.lbl_val.setText(f"{self.slider.value()}%")
            self.lbl_val.setStyleSheet("font-size: 9px; color: #a1a1aa; font-family: monospace;")

    def contextMenuEvent(self, event):
        panel = self.window()
        if not panel or not hasattr(panel, "pool_faders"):
            return
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 4px;
                color: #ffffff;
                font-size: 11px;
            }
            QMenu::item {
                padding: 4px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #52525b;
            }
            QMenu::separator {
                height: 1px;
                background: #27272a;
                margin: 4px 0px;
            }
        """)
        title_act = menu.addAction("⇄ Swap Slider Channel:")
        title_act.setEnabled(False)
        menu.addSeparator()

        for fp in getattr(panel, "pool_faders", []):
            fn = fp.get("name") if isinstance(fp, dict) else str(fp)
            permitted = panel.is_volume_permitted(fn)
            if not permitted:
                act = menu.addAction(f"🎚️ {fn} [🔒 LOCKED]")
                act.setEnabled(False)
            else:
                is_curr = (fn == self.fader_name)
                prefix = "✓ " if is_curr else "   "
                act = menu.addAction(f"{prefix}🎚️ {fn}")
                act.triggered.connect(lambda chk, name=fn: self._swap_to_fader(name))

        menu.addSeparator()
        if len(panel.volume_faders) < 8 and len(panel.volume_faders) < len(getattr(panel, "pool_faders", [])):
            act_add = menu.addAction("➕ Add Slider Slot")
            act_add.triggered.connect(panel.add_fader_slot)
        if len(panel.volume_faders) > 1:
            act_rem = menu.addAction("🗑️ Remove This Slider")
            act_rem.triggered.connect(lambda: panel.remove_fader_slot(self))

        menu.exec(event.globalPos())

    def _swap_to_fader(self, name: str):
        panel = self.window()
        self.set_label(name)
        if hasattr(panel, "re_evaluate_volume_states"):
            panel.re_evaluate_volume_states()
        if hasattr(panel, "slobs_client") and panel.slobs_client and panel.slobs_client.is_connected():
            vol = panel.slobs_client.get_source_volume_percent(name)
            self.set_value_silently(vol)

    def set_value_silently(self, val: int):
        """Updates slider position visually without emitting value_changed signal."""
        if self._is_dragging or getattr(self, "is_locked", False):
            return  # Never overwrite slider position while user is holding mouse down or locked
        if hasattr(self, "_last_interaction") and time.time() - self._last_interaction < 0.8:
            return  # Never overwrite slider position while user was actively scrolling or adjusting recently
        clamped = max(0, min(100, int(val)))
        self.slider.blockSignals(True)
        self.slider.setValue(clamped)
        self.lbl_val.setText(f"{clamped}%")
        self.slider.blockSignals(False)

    def _on_slider_pressed(self):
        self._is_dragging = True
        self._last_interaction = time.time()

    def _on_slider_released(self):
        self._is_dragging = False
        self._last_interaction = time.time()
        if self._pending_val is not None:
            self._flush_pending_value()

    def _on_slider_moved(self, val):
        if getattr(self, "is_locked", False):
            return
        self._last_interaction = time.time()
        self.lbl_val.setText(f"{val}%")
        self._pending_val = val
        if not self._throttle_timer.isActive():
            self._flush_pending_value()
            self._throttle_timer.start()

    def _flush_pending_value(self):
        if self._pending_val is not None and not getattr(self, "is_locked", False):
            val = self._pending_val
            self._pending_val = None
            self.value_changed.emit(self.fader_id, val)


class DirectorPanelWindow(QWidget):
    """Floating control dock positioned on the chosen monitor directly above the Windows taskbar."""
    panel_closed = pyqtSignal()
    settings_requested = pyqtSignal()
    resync_requested = pyqtSignal()
    scene_selected = pyqtSignal(int, str)
    audio_toggled = pyqtSignal(int, str, bool)
    volume_adjusted = pyqtSignal(int, str, int)
    view_visibility_toggled = pyqtSignal(str, bool)

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
        {"name": "Mic", "volume": 80},
        {"name": "Game", "volume": 75},
        {"name": "Music", "volume": 60},
        {"name": "Discord", "volume": 70},
        {"name": "Alerts", "volume": 65},
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

        self.view_toggle_buttons = {}
        self.pool_scenes = list(self.DEFAULT_SCENES)
        self.pool_audio = list(self.DEFAULT_AUDIO)
        self.pool_faders = [f["name"] for f in self.DEFAULT_FADERS]
        self._active_scene_name = ""
        self._active_scene_id = ""
        self._last_permissions = None

        self._build_ui()

        # Connect to StreamlabsClient for live IPC control & event sync
        self.slobs_client = get_streamlabs_client()
        self.slobs_client.connected.connect(self._on_slobs_connected)
        self.slobs_client.disconnected.connect(self._on_slobs_disconnected)
        self.slobs_client.scene_switched.connect(self._on_slobs_scene_switched)
        self.slobs_client.audio_muted_changed.connect(self._on_slobs_audio_muted_changed)
        self.slobs_client.audio_volume_changed.connect(self._on_slobs_audio_volume_changed)
        self.slobs_client.source_visibility_changed.connect(self._on_slobs_source_visibility_changed)

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

        self.btn_resync = QPushButton("🔄")
        self.btn_resync.setFixedSize(20, 20)
        self.btn_resync.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_resync.setToolTip("Re-sync Director Panel layout and audio state with Streamer")
        self.btn_resync.setStyleSheet("""
            QPushButton {
                background: #27272a;
                color: #a1a1aa;
                border: 1px solid #3f3f46;
                border-radius: 10px;
                font-size: 10px;
            }
            QPushButton:hover {
                background: #0284c7;
                color: #ffffff;
                border-color: #38bdf8;
            }
        """)
        self.btn_resync.clicked.connect(self._on_resync_clicked)
        top_bar.addWidget(self.btn_resync)

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

        self.lay_scenes_grid = QGridLayout()
        self.lay_scenes_grid.setContentsMargins(0, 0, 0, 0)
        self.lay_scenes_grid.setSpacing(4)
        lay_scenes_box.addLayout(self.lay_scenes_grid)
        content_row.addWidget(self.grp_scenes, 4)

        # SECTION 2: IN-GAME VIEW TOGGLES (SLOBS Source Visibility)
        self.grp_view_toggles = QFrame()
        self.grp_view_toggles.setObjectName("cardViewToggles")
        self.grp_view_toggles.setStyleSheet("""
            QFrame#cardViewToggles {
                background-color: #121214;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        lay_view_box = QVBoxLayout(self.grp_view_toggles)
        lay_view_box.setContentsMargins(6, 4, 6, 4)
        lay_view_box.setSpacing(4)

        lbl_sec_views = QLabel("SLOBS HOTKEYS")
        lbl_sec_views.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sec_views.setStyleSheet("font-size: 9px; font-weight: bold; color: #38bdf8; letter-spacing: 0.5px;")
        lay_view_box.addWidget(lbl_sec_views)

        self.lay_views_row = QHBoxLayout()
        self.lay_views_row.setSpacing(6)
        lay_view_box.addLayout(self.lay_views_row)

        for v_name, v_hint in [("SandMan View", "Ctrl+Num6"), ("Legal-View", "Ctrl+Num7")]:
            btn_v = ViewToggleButton(v_name, is_visible=False, hotkey_hint=v_hint, parent=self)
            btn_v.toggled_visibility.connect(self._on_view_toggle_clicked)
            self.lay_views_row.addWidget(btn_v)
            self.view_toggle_buttons[v_name] = btn_v

        content_row.addWidget(self.grp_view_toggles, 2)

        # SECTION 3: AUDIO MUTE TOGGLES (2x3 Grid)
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

        # SECTION 4: VOLUME ADJUST SLIDERS (Faders)
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
        content_row.addWidget(self.grp_volume, 3)

        root.addLayout(content_row)

        # Apply dark sleek dock styling
        self.setStyleSheet("""
            QWidget#DirectorPanelWindow {
                background-color: #0d0d0f;
                border: 2px solid #27272a;
                border-radius: 8px;
            }
        """)

        # Add resize grip to bottom-right corner for frameless resizing
        self.size_grip = QSizeGrip(self)
        self.size_grip.setStyleSheet("background: transparent;")
        self.size_grip.setFixedSize(14, 14)

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
                w.hide()
                w.setParent(None)
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

    def is_scene_permitted(self, name: str, sid: str = "") -> bool:
        """Checks if a scene name or raw ID is permitted by streamer permissions."""
        if not self._last_permissions or self._last_permissions.get("full_control", False):
            return True
        raw_allowed = [str(s).strip().lower() for s in self._last_permissions.get("allowed_scenes", [])]
        bn = (name or "").strip().lower()
        bid = (sid or "").strip().lower()
        for a in raw_allowed:
            if a and (a == bn or a in bn or bn in a or (bid and a == bid)):
                return True
        return False

    def is_audio_permitted(self, name: str) -> bool:
        """Checks if an audio toggle source name is permitted by streamer permissions."""
        if not self._last_permissions or self._last_permissions.get("full_control", False):
            return True
        raw_allowed = [str(m).strip().lower() for m in self._last_permissions.get("allowed_audio_mutes", [])]
        an = (name or "").strip().lower()
        for m in raw_allowed:
            if m and (m == an or m in an or an in m):
                return True
        return False

    def is_volume_permitted(self, name: str) -> bool:
        """Checks if a volume slider channel is permitted by streamer permissions."""
        if not self._last_permissions or self._last_permissions.get("full_control", False):
            return True
        raw_allowed = [str(v).strip().lower() for v in self._last_permissions.get("allowed_audio_volume", [])]
        fn = (name or "").strip().lower()
        for v in raw_allowed:
            if v and (v == fn or v in fn or fn in v):
                return True
        return False

    def re_evaluate_scene_states(self):
        """Re-applies lock status to all active scene cards based on permissions."""
        for btn in self.scene_buttons:
            permitted = self.is_scene_permitted(btn.scene_name, getattr(btn, "scene_raw_id", ""))
            btn.set_locked(not permitted)

    def re_evaluate_audio_states(self):
        """Re-applies lock status to all active audio mute buttons based on permissions."""
        for btn in self.audio_buttons:
            permitted = self.is_audio_permitted(btn.audio_name)
            btn.set_locked(not permitted)

    def re_evaluate_volume_states(self):
        """Re-applies lock status to all active volume faders based on permissions."""
        for f in self.volume_faders:
            permitted = self.is_volume_permitted(f.fader_name)
            f.set_locked(not permitted)

    def add_scene_slot(self):
        """Adds another scene card slot (up to 8) populated from pool_scenes."""
        if len(self.scene_buttons) >= 8:
            return
        idx = len(self.scene_buttons)
        active_names = {b.scene_name for b in self.scene_buttons}
        candidate = next((sc for sc in self.pool_scenes if sc.get("name") not in active_names), None)
        if not candidate:
            candidate = {"name": f"Scene {idx+1}", "color": "#0284c7"}
        btn = SceneCardButton(
            idx,
            candidate.get("name", f"Scene {idx+1}"),
            candidate.get("color", "#0284c7"),
            raw_id=candidate.get("id"),
            parent=self
        )
        btn.clicked.connect(lambda chk, i=idx, b=btn: self._on_scene_clicked(i, b.scene_name, b))
        self.scene_buttons.append(btn)
        self._reflow_scenes_grid()
        self.re_evaluate_scene_states()
        if hasattr(self, "_active_scene_name") and self._active_scene_name:
            self._on_slobs_scene_switched(self._active_scene_id, self._active_scene_name)

    def remove_scene_slot(self, btn):
        """Removes a scene slot from the dock panel."""
        if len(self.scene_buttons) <= 1:
            return
        if btn in self.scene_buttons:
            self.scene_buttons.remove(btn)
            self.lay_scenes_grid.removeWidget(btn)
            btn.hide()
            btn.setParent(None)
            btn.deleteLater()
            for i, b in enumerate(self.scene_buttons):
                b.scene_id = i
            self._reflow_scenes_grid()

    def _reflow_scenes_grid(self):
        """Reflows visible scene buttons evenly into a 2-row grid with dynamic columns."""
        while self.lay_scenes_grid.count():
            self.lay_scenes_grid.takeAt(0)
        visible_btns = [b for b in self.scene_buttons if not b.isHidden()]
        if not visible_btns:
            visible_btns = self.scene_buttons
        cols = max(2, (len(visible_btns) + 1) // 2)
        for i, b in enumerate(visible_btns):
            row = i // cols
            col = i % cols
            self.lay_scenes_grid.addWidget(b, row, col)

    def add_audio_slot(self):
        """Adds another audio mute slot (up to 8) populated from pool_audio."""
        if len(self.audio_buttons) >= 8:
            return
        idx = len(self.audio_buttons)
        active_names = {b.audio_name for b in self.audio_buttons}
        candidate = next((a for a in self.pool_audio if a.get("name") not in active_names), None)
        if not candidate:
            candidate = {"name": f"Audio {idx+1}", "muted": False}
        btn = AudioMuteButton(idx, candidate.get("name", f"Audio {idx+1}"), candidate.get("muted", False), self, raw_id=candidate.get("id"))
        btn.toggled_mute.connect(lambda aid, m, b=btn: self._on_audio_toggled(aid, b.audio_name, m))
        self.audio_buttons.append(btn)
        self._reflow_audio_grid()
        self.re_evaluate_audio_states()
        if hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
            muted = self.slobs_client.get_source_muted_state(btn.audio_name)
            btn.set_muted_silently(muted)

    def remove_audio_slot(self, btn):
        """Removes an audio mute slot from the dock panel."""
        if len(self.audio_buttons) <= 1:
            return
        if btn in self.audio_buttons:
            self.audio_buttons.remove(btn)
            self.lay_audio_grid.removeWidget(btn)
            btn.hide()
            btn.setParent(None)
            btn.deleteLater()
            for i, b in enumerate(self.audio_buttons):
                b.audio_id = i
            self._reflow_audio_grid()

    def _reflow_audio_grid(self):
        """Reflows visible audio buttons evenly into a 2-row grid with dynamic columns."""
        while self.lay_audio_grid.count():
            self.lay_audio_grid.takeAt(0)
        visible_btns = [b for b in self.audio_buttons if not b.isHidden()]
        if not visible_btns:
            visible_btns = self.audio_buttons
        cols = max(1, (len(visible_btns) + 1) // 2)
        for i, b in enumerate(visible_btns):
            row = i // cols
            col = i % cols
            self.lay_audio_grid.addWidget(b, row, col)

    def add_fader_slot(self):
        """Adds another volume fader slot (up to 8) populated from pool_faders."""
        if len(self.volume_faders) >= 8:
            return
        idx = len(self.volume_faders)
        active_names = {f.fader_name for f in self.volume_faders}
        candidate = next((fp for fp in self.pool_faders if (fp.get("name") if isinstance(fp, dict) else str(fp)) not in active_names), None)
        name = candidate.get("name") if isinstance(candidate, dict) else (str(candidate) if candidate else f"Audio {idx+1}")
        vol = candidate.get("volume", 75) if isinstance(candidate, dict) else 75
        fader = VolumeFaderWidget(idx, name, vol, self)
        fader.value_changed.connect(lambda fid, v, fw=fader: self._on_volume_adjusted(fid, fw.fader_name, v))
        self.lay_vol_row.addWidget(fader)
        self.volume_faders.append(fader)
        self.re_evaluate_volume_states()
        if hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
            v = self.slobs_client.get_source_volume_percent(name)
            fader.set_value_silently(v)

    def remove_fader_slot(self, fader):
        """Removes a volume fader from the dock panel."""
        if len(self.volume_faders) <= 1:
            return
        if fader in self.volume_faders:
            self.volume_faders.remove(fader)
            self.lay_vol_row.removeWidget(fader)
            fader.hide()
            fader.setParent(None)
            fader.deleteLater()
            for i, f in enumerate(self.volume_faders):
                f.fader_id = i

    def load_configuration(self, scenes=None, audio=None, faders=None, permissions=None, pool_scenes=None, pool_audio=None, pool_faders=None):
        """Builds or rebuilds the dynamic scene cards, audio buttons, and faders with permission gating and preselection pools."""
        if permissions is not None and bool(permissions):
            self._last_permissions = permissions
        elif hasattr(self, "_last_permissions"):
            permissions = self._last_permissions

        if pool_scenes is not None:
            self.pool_scenes = list(pool_scenes)
        elif scenes is not None:
            self.pool_scenes = list(scenes)

        if pool_audio is not None:
            self.pool_audio = list(pool_audio)
        elif audio is not None:
            self.pool_audio = list(audio)

        if pool_faders is not None:
            self.pool_faders = list(pool_faders)
        elif faders is not None:
            self.pool_faders = [f.get("name") if isinstance(f, dict) else str(f) for f in faders]

        # 1. Populate Scene Cards (Up to 8)
        scenes = (scenes or self.DEFAULT_SCENES)[:8]
        scenes_match = (
            len(self.scene_buttons) == len(scenes)
            and all(
                b.scene_name == sc.get("name", f"Scene {idx+1}")
                and (getattr(b, "scene_raw_id", None) or "") == (sc.get("id") or "")
                for idx, (b, sc) in enumerate(zip(self.scene_buttons, scenes))
            )
        )
        if not scenes_match:
            self._clear_layout(self.lay_scenes_grid)
            self.scene_buttons.clear()
            for i, sc in enumerate(scenes):
                btn = SceneCardButton(
                    i,
                    sc.get("name", f"Scene {i+1}"),
                    sc.get("color", "#22c55e"),
                    raw_id=sc.get("id"),
                    parent=self
                )
                btn.scene_config = sc
                if i == self.active_scene_index:
                    btn.set_active(True)
                btn.clicked.connect(lambda chk, idx=i, b=btn: self._on_scene_clicked(idx, b.scene_name, b))
                self.scene_buttons.append(btn)
            self._reflow_scenes_grid()
        else:
            for i, sc in enumerate(scenes):
                b = self.scene_buttons[i]
                b.accent_color = sc.get("color", b.accent_color)
                if sc.get("id"):
                    b.scene_raw_id = sc.get("id")
                b.scene_config = sc

        # 2. Populate Audio Mute Toggles (Up to 8 in dynamic 2-row grid)
        audio = (audio or self.DEFAULT_AUDIO)[:8]
        audio_match = (
            len(self.audio_buttons) == len(audio)
            and all(
                b.audio_name == a.get("name", f"Audio {idx+1}")
                for idx, (b, a) in enumerate(zip(self.audio_buttons, audio))
            )
        )
        if not audio_match:
            self._clear_layout(self.lay_audio_grid)
            self.audio_buttons.clear()
            for i, a in enumerate(audio):
                btn = AudioMuteButton(i, a.get("name", f"Audio {i+1}"), a.get("muted", False), self, raw_id=a.get("id"))
                btn.toggled_mute.connect(lambda aid, m, b=btn: self._on_audio_toggled(aid, b.audio_name, m))
                self.audio_buttons.append(btn)
            self._reflow_audio_grid()
        else:
            for i, a in enumerate(audio):
                self.audio_buttons[i].set_muted_silently(a.get("muted", False))

        # 3. Populate Volume Faders (Up to 8 active, default 5)
        faders = (faders or self.DEFAULT_FADERS)[:8]
        faders_match = (
            len(self.volume_faders) == len(faders)
            and all(
                f.fader_name == fi.get("name", f"Audio {idx+1}")
                for idx, (f, fi) in enumerate(zip(self.volume_faders, faders))
            )
        )
        if not faders_match:
            self._clear_layout(self.lay_vol_row)
            self.volume_faders.clear()
            for i, f in enumerate(faders):
                fader = VolumeFaderWidget(i, f.get("name", f"Audio {i+1}"), f.get("volume", 75), self)
                fader.value_changed.connect(lambda fid, v, fw=fader: self._on_volume_adjusted(fid, fw.fader_name, v))
                self.lay_vol_row.addWidget(fader)
                self.volume_faders.append(fader)
        else:
            for i, fi in enumerate(faders):
                if "volume" in fi:
                    self.volume_faders[i].set_value_silently(fi["volume"])

        # 4. Apply Granular Permissions Scoping
        self.re_evaluate_scene_states()
        self.re_evaluate_audio_states()
        self.re_evaluate_volume_states()

        # 5. Trigger initial scene-aware reflow
        cur_sc = self.scene_buttons[self.active_scene_index] if 0 <= self.active_scene_index < len(self.scene_buttons) else None
        cur_name = cur_sc.scene_name if cur_sc else (getattr(self, "_active_scene_name", "") or "")
        cur_id = getattr(cur_sc, "scene_raw_id", "") if cur_sc else (getattr(self, "_active_scene_id", "") or "")
        self.reflow_for_active_scene(cur_name, cur_id)

        if hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
            self._sync_with_slobs_state()

    def _on_scene_clicked(self, scene_id, name, btn):
        self.active_scene_index = scene_id
        for b in self.scene_buttons:
            b.set_active(b == btn)
        self.reflow_for_active_scene(name, getattr(btn, "scene_raw_id", ""))
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

    def _fire_view_hotkey(self, source_name: str):
        """Simulates the hotkey sequence configured in Streamlabs Desktop for the view."""
        sn_lower = (source_name or "").strip().lower()
        hotkey_str = None
        vk_code = None
        scan_code = None

        if "sandman" in sn_lower:
            hotkey_str = "ctrl+num 6"
            vk_code = 0x66  # VK_NUMPAD6
            scan_code = 0x4D  # Scan code for Numpad 6
        elif "legal" in sn_lower:
            hotkey_str = "ctrl+num 7"
            vk_code = 0x67  # VK_NUMPAD7
            scan_code = 0x47  # Scan code for Numpad 7

        if not vk_code:
            return

        # 1. Fire via python keyboard library using hardware scan codes (LCTRL=29, Numpad=77 or 71)
        try:
            import keyboard
            keyboard.press(29)  # LCTRL scan code
            keyboard.press(scan_code)
            time.sleep(0.02)
            keyboard.release(scan_code)
            keyboard.release(29)
        except Exception:
            try:
                import keyboard
                keyboard.send(hotkey_str)
            except Exception:
                pass

        # 2. Also simulate via Windows Win32 API keybd_event with scan codes and virtual keys
        if sys.platform == "win32" and vk_code:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                VK_CONTROL = 0x11
                KEYEVENTF_KEYUP = 0x0002
                scan_ctrl = 0x1D

                # Press Ctrl + Numpad
                user32.keybd_event(VK_CONTROL, scan_ctrl, 0, 0)
                time.sleep(0.01)
                user32.keybd_event(vk_code, scan_code, 0, 0)
                time.sleep(0.02)
                # Release Numpad + Ctrl
                user32.keybd_event(vk_code, scan_code, KEYEVENTF_KEYUP, 0)
                time.sleep(0.01)
                user32.keybd_event(VK_CONTROL, scan_ctrl, KEYEVENTF_KEYUP, 0)
            except Exception:
                pass

    def _on_view_toggle_clicked(self, source_name: str, is_visible: bool):
        self.view_visibility_toggled.emit(source_name, is_visible)
        # 1. Fire the configured hotkey sequence (Ctrl + Num6 / Ctrl + Num7)
        self._fire_view_hotkey(source_name)
        # 2. Also set visibility directly via live SLOBS RPC for all matching view items
        if hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
            self.slobs_client.set_source_visibility(source_name, is_visible)

    def _on_slobs_source_visibility_changed(self, source_name: str, is_visible: bool):
        target = source_name.strip().lower()
        for name, btn in self.view_toggle_buttons.items():
            btn_lower = name.strip().lower()
            is_match = False
            if btn_lower == target or btn_lower in target or target in btn_lower:
                is_match = True
            elif "legal" in btn_lower and "legal" in target:
                is_match = True
            elif "sandman" in btn_lower and "sandman" in target:
                is_match = True

            if is_match:
                btn.set_visibility_state(is_visible)

    def reflow_for_active_scene(self, scene_name: str, scene_id: str = ""):
        """
        Dynamically adjusts visible view toggles, audio mute buttons, and volume faders
        based on the active scene's configuration.
        """
        sc_config = None
        s_name_lower = (scene_name or "").strip().lower()
        s_id_lower = (scene_id or "").strip().lower()
        sc_id_target = s_id_lower

        # Find matching scene config from scene_buttons or pool_scenes
        for b in self.scene_buttons:
            b_name = b.scene_name.strip().lower()
            b_id = (getattr(b, "scene_raw_id", "") or "").strip().lower()
            if (s_id_lower and b_id == s_id_lower) or (s_name_lower and (b_name == s_name_lower or b_name in s_name_lower or s_name_lower in b_name)):
                sc_config = getattr(b, "scene_config", None)
                if not sc_id_target and b_id:
                    sc_id_target = b_id
                break

        if not sc_config and hasattr(self, "pool_scenes"):
            for sc in self.pool_scenes:
                p_name = sc.get("name", "").strip().lower()
                p_id = (sc.get("id", "") or "").strip().lower()
                if (s_id_lower and p_id == s_id_lower) or (s_name_lower and (p_name == s_name_lower or p_name in s_name_lower or s_name_lower in p_name)):
                    sc_config = sc
                    if not sc_id_target and p_id:
                        sc_id_target = p_id
                    break

        # 1. Scoping View Toggles (Only for In-Game scene)
        if sc_config and "show_view_toggles" in sc_config:
            show_views = bool(sc_config["show_view_toggles"])
        else:
            show_views = ("game" in s_name_lower) or ("play" in s_name_lower)

        if hasattr(self, "grp_view_toggles") and self.grp_view_toggles:
            self.grp_view_toggles.setVisible(show_views)

        # 2. View Toggle Names that should NEVER be shown in audio buttons or faders
        view_names = {"legal-view", "sandman view"}
        if hasattr(self, "view_toggle_buttons"):
            for vn in self.view_toggle_buttons.keys():
                view_names.add(vn.strip().lower())

        # 3. Scoping Audio Mute Buttons
        allowed_audio = sc_config.get("audio_sources") if sc_config else None
        is_break_or_start = any(k in s_name_lower for k in ["start", "brb", "break", "end", "be right"])

        for b in self.audio_buttons:
            bn_lower = b.audio_name.strip().lower()
            if bn_lower in view_names:
                b.setVisible(False)
                continue

            if allowed_audio is not None and len(allowed_audio) > 0:
                match = any(a.strip().lower() == bn_lower or a.strip().lower() in bn_lower or bn_lower in a.strip().lower() for a in allowed_audio)
                b.setVisible(match)
            elif is_break_or_start:
                b.setVisible("spotify" in bn_lower or "music" in bn_lower or "vod" in bn_lower)
            elif hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
                target_sc_id = sc_id_target or getattr(self, "_active_scene_id", "")
                in_scene = self.slobs_client.is_source_in_scene(b.audio_name, getattr(b, "audio_raw_id", ""), scene_id=target_sc_id)
                b.setVisible(in_scene)
            else:
                b.setVisible(True)

        self._reflow_audio_grid()

        # 4. Scoping Volume Faders
        allowed_faders = sc_config.get("faders") if sc_config else None
        for f in self.volume_faders:
            fn_lower = f.fader_name.strip().lower()
            if fn_lower in view_names:
                f.setVisible(False)
                continue

            if allowed_faders is not None and len(allowed_faders) > 0:
                match = any(a.strip().lower() == fn_lower or a.strip().lower() in fn_lower or fn_lower in a.strip().lower() for a in allowed_faders)
                f.setVisible(match)
            elif is_break_or_start:
                f.setVisible("spotify" in fn_lower or "music" in fn_lower or "vod" in fn_lower)
            elif hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
                target_sc_id = sc_id_target or getattr(self, "_active_scene_id", "")
                in_scene = self.slobs_client.is_source_in_scene(f.fader_name, scene_id=target_sc_id)
                f.setVisible(in_scene)
            else:
                f.setVisible(True)

        self.adjustSize()
        self.reposition_above_taskbar()

    def _on_resync_clicked(self):
        """User clicked the re-sync button on the Director Panel dock."""
        if hasattr(self, "btn_resync"):
            self.btn_resync.setEnabled(False)
            QTimer.singleShot(1000, lambda: self.btn_resync.setEnabled(True) if hasattr(self, "btn_resync") else None)
        if hasattr(self, "slobs_client") and self.slobs_client and self.slobs_client.is_connected():
            self._sync_with_slobs_state()
        self.resync_requested.emit()

    def _on_slobs_connected(self):
        if hasattr(self, "lbl_status"):
            self.lbl_status.setText("<span style='color: #22c55e;'>● Connected</span>")
        self._sync_with_slobs_state()

    def _on_slobs_disconnected(self):
        if hasattr(self, "lbl_status"):
            self.lbl_status.setText("<span style='color: #ef4444;'>● Disconnected</span>")

    def _on_slobs_scene_switched(self, scene_id, scene_name):
        self._active_scene_id = scene_id or ""
        self._active_scene_name = scene_name or ""
        target = (scene_name or "").strip().lower()
        target_id = (scene_id or "").strip().lower()
        for i, b in enumerate(self.scene_buttons):
            if getattr(b, "is_locked", False):
                continue
            b_name = b.scene_name.strip().lower()
            raw_id = (getattr(b, "scene_raw_id", None) or "").strip().lower()
            is_match = False
            if raw_id and target_id and raw_id == target_id:
                is_match = True
            elif b_name and target and (b_name == target or b_name in target or target in b_name):
                is_match = True
            b.set_active(is_match)
            if is_match:
                self.active_scene_index = i
        self.reflow_for_active_scene(scene_name, scene_id)

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

        # 4. Sync view toggles
        for name, btn in self.view_toggle_buttons.items():
            vis = self.slobs_client.get_source_visibility(name)
            btn.set_visibility_state(vis)

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

    def reposition_above_taskbar(self, monitor_index: int = -1):
        """Places the dock horizontally centered directly above the taskbar on the target screen."""
        screens = QApplication.screens()
        if not screens:
            return
        if monitor_index is not None and 0 <= monitor_index < len(screens):
            self._current_monitor_index = monitor_index
        idx = getattr(self, "_current_monitor_index", 0)
        if idx < 0 or idx >= len(screens):
            idx = 0
        screen = screens[idx]
        avail = screen.availableGeometry()

        self.adjustSize()
        hint = self.sizeHint()
        dock_height = max(hint.height(), 145)
        
        # Strictly clamp dock width so it never overflows the screen (especially narrow/vertical displays)
        max_allowed_w = max(320, avail.width() - 16)
        dock_width = min(max_allowed_w, max(hint.width(), 380))
        
        # Position X centered on that screen, Y right above the taskbar
        pos_x = avail.x() + (avail.width() - dock_width) // 2
        pos_y = avail.bottom() - dock_height + 1

        self.setGeometry(pos_x, pos_y, dock_width, dock_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "size_grip") and self.size_grip:
            self.size_grip.move(self.width() - self.size_grip.width() - 2, self.height() - self.size_grip.height() - 2)

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
                self.slobs_client.source_visibility_changed.disconnect(self._on_slobs_source_visibility_changed)
        except Exception:
            pass
        self.panel_closed.emit()
        super().closeEvent(event)
