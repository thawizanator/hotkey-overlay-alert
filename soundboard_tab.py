import os
import sys
import subprocess
from typing import Optional

from PyQt6.QtCore import Qt, QSize, pyqtSignal, QEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QSlider, QComboBox, QLineEdit, QCheckBox, QFrame, QScrollArea,
    QDialog, QFormLayout, QFileDialog, QMessageBox, QColorDialog
)
from PyQt6.QtGui import QColor, QFont, QKeyEvent

from soundboard_engine import SoundboardEngine, SoundClip

SWATCH_COLORS = [
    "#38bdf8", # Cyan
    "#22c55e", # Green
    "#f59e0b", # Amber / Yellow
    "#ef4444", # Red
    "#a855f7", # Purple
    "#ec4899", # Pink
    "#3b82f6", # Blue
    "#14b8a6", # Teal
]


class HotkeyRecordLineEdit(QLineEdit):
    """Line edit that captures key combinations when focused."""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setPlaceholderText("Click & press keys (e.g. Ctrl+Num1, F9)...")
        self.setReadOnly(True)
        self.is_recording = False

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.start_recording()

    def start_recording(self):
        self.is_recording = True
        self.setText("Listening for shortcut...")
        self.setStyleSheet("border: 2px dashed #a855f7; color: #38bdf8; background-color: #09090b;")

    def stop_recording(self):
        self.is_recording = False
        self.setStyleSheet("")

    def keyPressEvent(self, event: QKeyEvent):
        if not self.is_recording:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return # Wait for non-modifier key

        if key == Qt.Key.Key_Escape:
            self.stop_recording()
            return

        parts = []
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")

        # Map special keys
        key_name = ""
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            key_name = f"F{key - Qt.Key.Key_F1 + 1}"
        elif key == Qt.Key.Key_Space:
            key_name = "Space"
        elif key == Qt.Key.Key_Tab:
            key_name = "Tab"
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            key_name = "Enter"
        elif key == Qt.Key.Key_Backspace:
            key_name = "Backspace"
        elif key == Qt.Key.Key_Delete:
            key_name = "Delete"
        elif key == Qt.Key.Key_Insert:
            key_name = "Insert"
        elif key == Qt.Key.Key_Home:
            key_name = "Home"
        elif key == Qt.Key.Key_End:
            key_name = "End"
        elif key == Qt.Key.Key_PageUp:
            key_name = "PageUp"
        elif key == Qt.Key.Key_PageDown:
            key_name = "PageDown"
        elif key == Qt.Key.Key_Up:
            key_name = "Up"
        elif key == Qt.Key.Key_Down:
            key_name = "Down"
        elif key == Qt.Key.Key_Left:
            key_name = "Left"
        elif key == Qt.Key.Key_Right:
            key_name = "Right"
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            key_name = chr(key)
        elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            key_name = chr(key)
        else:
            text = event.text().strip().upper()
            key_name = text if text else f"Key_{key}"

        parts.append(key_name)
        hk_str = "+".join(parts)
        self.setText(hk_str)
        self.stop_recording()


class SoundClipDialog(QDialog):
    """Modal dialog to add or edit a soundboard clip."""
    def __init__(self, clip: Optional[SoundClip] = None, categories=None, parent=None, engine: Optional[SoundboardEngine] = None):
        super().__init__(parent)
        self.engine = engine
        self.preview_player = None
        self.is_edit = clip is not None
        self.clip_id = clip.id if clip else None
        self.chosen_color = clip.color if clip else "#38bdf8"

        self.setWindowTitle("Edit Sound Clip" if self.is_edit else "Add New Sound Clip")
        self.setMinimumWidth(440)
        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
                color: #f4f4f5;
            }
            QLabel {
                color: #e4e4e7;
            }
            QLineEdit, QComboBox {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 6px 10px;
                color: #ffffff;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #38bdf8;
            }
            QPushButton {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 16, 18, 16)

        form = QFormLayout()
        form.setSpacing(10)

        # Name
        self.edit_name = QLineEdit(clip.name if clip else "")
        self.edit_name.setPlaceholderText("e.g. Airhorn, Stream Marker, Applause")
        form.addRow("Sound Name:", self.edit_name)

        # File path + Browse
        file_row = QHBoxLayout()
        self.edit_file = QLineEdit(clip.file_path if clip else "")
        self.edit_file.setPlaceholderText("Path to .wav, .mp3, .ogg, .flac...")
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_file)
        file_row.addWidget(self.edit_file, 1)
        file_row.addWidget(btn_browse)
        form.addRow("Audio File:", file_row)

        # Category
        self.combo_cat = QComboBox()
        self.combo_cat.setEditable(True)
        cats = categories if categories else ["General", "Alerts", "Stream Markers", "Hype", "Memes"]
        for c in cats:
            if c != "All":
                self.combo_cat.addItem(c)
        if clip and clip.category:
            self.combo_cat.setEditText(clip.category)
        form.addRow("Category:", self.combo_cat)

        # Color Accent Swatches
        color_row = QHBoxLayout()
        self.color_buttons = []
        for hex_col in SWATCH_COLORS:
            btn_col = QPushButton()
            btn_col.setFixedSize(24, 24)
            btn_col.setStyleSheet(f"background-color: {hex_col}; border-radius: 12px; border: {'2px solid #ffffff' if hex_col == self.chosen_color else '1px solid #3f3f46'};")
            btn_col.clicked.connect(lambda _, c=hex_col: self._select_color(c))
            self.color_buttons.append((btn_col, hex_col))
            color_row.addWidget(btn_col)
        color_row.addStretch()
        form.addRow("Accent Color:", color_row)

        # Hotkey
        hk_row = QHBoxLayout()
        self.edit_hotkey = HotkeyRecordLineEdit(clip.hotkey.upper() if clip and clip.hotkey else "")
        btn_clear_hk = QPushButton("Clear")
        btn_clear_hk.setFixedWidth(50)
        btn_clear_hk.clicked.connect(lambda: self.edit_hotkey.setText(""))
        hk_row.addWidget(self.edit_hotkey, 1)
        hk_row.addWidget(btn_clear_hk)
        form.addRow("Hotkey Shortcut:", hk_row)

        # Volume Trim Slider
        vol_row = QHBoxLayout()
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        init_vol = int((clip.volume if clip else 1.0) * 100)
        self.slider_vol.setValue(init_vol)
        self.lbl_vol_val = QLabel(f"{init_vol}%")
        self.lbl_vol_val.setFixedWidth(40)
        self.slider_vol.valueChanged.connect(lambda v: self.lbl_vol_val.setText(f"{v}%"))
        vol_row.addWidget(self.slider_vol, 1)
        vol_row.addWidget(self.lbl_vol_val)
        form.addRow("Volume Trim:", vol_row)

        # Loop checkbox
        self.chk_loop = QCheckBox("Loop audio continuously until stopped")
        self.chk_loop.setChecked(clip.loop if clip else False)
        form.addRow("", self.chk_loop)

        layout.addLayout(form)

        # Preview Button
        preview_box = QHBoxLayout()
        self.btn_preview = QPushButton("▶  Test Playback")
        self.btn_preview.setStyleSheet("background-color: #3b82f6; color: white;")
        self.btn_preview.clicked.connect(self._toggle_preview)
        preview_box.addWidget(self.btn_preview)
        preview_box.addStretch()
        layout.addLayout(preview_box)

        # Save / Cancel Action Bar
        action_bar = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self._on_cancel)
        self.btn_save = QPushButton("Save Sound")
        self.btn_save.setStyleSheet("background-color: #22c55e; color: white; padding: 7px 16px;")
        self.btn_save.clicked.connect(self._on_save)

        action_bar.addStretch()
        action_bar.addWidget(btn_cancel)
        action_bar.addWidget(self.btn_save)
        layout.addLayout(action_bar)

    def _select_color(self, hex_col):
        self.chosen_color = hex_col
        for btn, c in self.color_buttons:
            btn.setStyleSheet(f"background-color: {c}; border-radius: 12px; border: {'2px solid #ffffff' if c == hex_col else '1px solid #3f3f46'};")

    def _browse_file(self):
        start_dir = self.engine.sounds_dir if self.engine else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            start_dir,
            "Audio Files (*.wav *.mp3 *.ogg *.flac *.m4a *.aac);;All Files (*.*)"
        )
        if path:
            self.edit_file.setText(path)
            if not self.edit_name.text().strip():
                base_name = os.path.splitext(os.path.basename(path))[0]
                self.edit_name.setText(base_name.replace("_", " ").title())

    def _toggle_preview(self):
        fpath = self.edit_file.text().strip()
        if not fpath or not os.path.exists(fpath):
            QMessageBox.warning(self, "Missing File", "Please select an existing audio file first.")
            return

        if self.engine:
            temp_id = "_preview_clip_"
            if self.engine.is_clip_playing(temp_id):
                self.engine.stop_clip(temp_id)
                self.btn_preview.setText("▶  Test Playback")
            else:
                self.engine.add_clip(
                    name="Preview",
                    file_path=fpath,
                    volume=self.slider_vol.value() / 100.0,
                    loop=self.chk_loop.isChecked()
                )
                preview_clip = self.engine.clips[-1]
                preview_clip.id = temp_id
                self.engine.play_clip(temp_id)
                self.btn_preview.setText("⏹  Stop Preview")

    def _on_cancel(self):
        if self.engine:
            self.engine.stop_clip("_preview_clip_")
        self.reject()

    def _on_save(self):
        name = self.edit_name.text().strip()
        fpath = self.edit_file.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please provide a name for this sound clip.")
            return
        if not fpath or not os.path.exists(fpath):
            QMessageBox.warning(self, "Invalid File", "Please select a valid, existing audio file.")
            return

        if self.engine:
            self.engine.stop_clip("_preview_clip_")
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.edit_name.text().strip(),
            "file_path": self.edit_file.text().strip(),
            "category": self.combo_cat.currentText().strip() or "General",
            "color": self.chosen_color,
            "hotkey": self.edit_hotkey.text().strip().lower(),
            "volume": self.slider_vol.value() / 100.0,
            "loop": self.chk_loop.isChecked()
        }


class SoundCardWidget(QFrame):
    """
    Interactive tile card for a single soundboard clip.
    Includes big Play/Stop trigger, volume trim, hotkey badge, and edit/delete actions.
    """
    play_requested = pyqtSignal(str)   # clip_id
    stop_requested = pyqtSignal(str)   # clip_id
    edit_requested = pyqtSignal(str)   # clip_id
    delete_requested = pyqtSignal(str) # clip_id
    volume_changed = pyqtSignal(str, float) # clip_id, vol

    def __init__(self, clip: SoundClip, parent=None):
        super().__init__(parent)
        self.clip = clip
        self.is_playing = False

        self.setObjectName("soundCard")
        self.setMinimumSize(230, 130)
        self.setSizePolicy(self.sizePolicy().Policy.Expanding, self.sizePolicy().Policy.Fixed)

        self._update_card_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Top Info Bar: Category tag + Edit/Delete tools
        top_row = QHBoxLayout()
        self.lbl_cat = QLabel(clip.category.upper())
        self.lbl_cat.setStyleSheet(f"font-size: 9px; font-weight: bold; color: {clip.color};")
        top_row.addWidget(self.lbl_cat, 1)

        if clip.loop:
            lbl_loop = QLabel("🔁")
            lbl_loop.setToolTip("Loops continuously")
            top_row.addWidget(lbl_loop)

        btn_edit = QPushButton("Edit")
        btn_edit.setFixedHeight(20)
        btn_edit.setToolTip("Edit Sound Properties")
        btn_edit.setStyleSheet("font-size: 10px; color: #a1a1aa; background: #27272a; border: 1px solid #3f3f46; border-radius: 3px; padding: 0 4px;")
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.clip.id))
        top_row.addWidget(btn_edit)

        btn_del = QPushButton("X")
        btn_del.setFixedSize(20, 20)
        btn_del.setToolTip("Delete Sound")
        btn_del.setStyleSheet("font-size: 10px; color: #ef4444; background: #27272a; border: 1px solid #3f3f46; border-radius: 3px; font-weight: bold;")
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self.clip.id))
        top_row.addWidget(btn_del)
        layout.addLayout(top_row)

        # Main Play / Stop Button
        self.btn_play = QPushButton(f"▶  {clip.name}")
        self.btn_play.setFixedHeight(48)
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.setStyleSheet(f"""
            QPushButton {{
                background-color: #27272a;
                border: 1px solid {clip.color};
                border-radius: 8px;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: #3f3f46;
                border: 2px solid {clip.color};
            }}
        """)
        self.btn_play.clicked.connect(self._toggle_playback)
        layout.addWidget(self.btn_play)

        # Bottom Bar: Hotkey badge & Volume slider
        bot_row = QHBoxLayout()
        hk_display = self.clip.hotkey.upper() if self.clip.hotkey else "+ Key"
        self.btn_hk = QPushButton(hk_display)
        self.btn_hk.setFixedHeight(22)
        self.btn_hk.setToolTip("Click to assign / modify hotkey")
        self.btn_hk.setStyleSheet(f"""
            QPushButton {{
                background-color: #09090b;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                color: {'#38bdf8' if self.clip.hotkey else '#71717a'};
                padding: 0 6px;
            }}
            QPushButton:hover {{
                border-color: #38bdf8;
                color: #ffffff;
            }}
        """)
        self.btn_hk.clicked.connect(lambda: self.edit_requested.emit(self.clip.id))
        bot_row.addWidget(self.btn_hk)

        bot_row.addStretch()

        # Mini Volume Slider
        self.slider_trim = QSlider(Qt.Orientation.Horizontal)
        self.slider_trim.setRange(0, 100)
        self.slider_trim.setValue(int(self.clip.volume * 100))
        self.slider_trim.setFixedWidth(55)
        self.slider_trim.setToolTip(f"Trim: {int(self.clip.volume * 100)}%")
        self.slider_trim.valueChanged.connect(self._on_trim_changed)
        bot_row.addWidget(self.slider_trim)

        layout.addLayout(bot_row)

    def _update_card_style(self):
        border_col = self.clip.color if self.is_playing else "#27272a"
        bg_col = "#1c1917" if self.is_playing else "#18181b"
        self.setStyleSheet(f"""
            QFrame#soundCard {{
                background-color: {bg_col};
                border: 2px solid {border_col};
                border-radius: 10px;
            }}
        """)

    def _toggle_playback(self):
        if self.is_playing:
            self.stop_requested.emit(self.clip.id)
        else:
            self.play_requested.emit(self.clip.id)

    def set_playing_state(self, playing: bool):
        self.is_playing = playing
        self._update_card_style()
        if playing:
            self.btn_play.setText(f"⏹  STOP")
            self.btn_play.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.clip.color};
                    border: 2px solid #ffffff;
                    border-radius: 8px;
                    color: #09090b;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 4px 8px;
                }}
            """)
        else:
            self.btn_play.setText(f"▶  {self.clip.name}")
            self.btn_play.setStyleSheet(f"""
                QPushButton {{
                    background-color: #27272a;
                    border: 1px solid {self.clip.color};
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 4px 8px;
                }}
                QPushButton:hover {{
                    background-color: #3f3f46;
                    border: 2px solid {self.clip.color};
                }}
            """)

    def _on_trim_changed(self, val):
        new_vol = val / 100.0
        self.clip.volume = new_vol
        self.slider_trim.setToolTip(f"Trim: {val}%")
        self.volume_changed.emit(self.clip.id, new_vol)


class SoundboardTab(QWidget):
    """
    Main Soundboard Workspace View embedded in SettingsWindow under STREAM TOOLS.
    Features live master volume mixing, device routing, sound tile matrix, search, and instant triggers.
    """
    def __init__(self, main_win=None, engine: Optional[SoundboardEngine] = None):
        super().__init__()
        self.main_win = main_win
        self.engine = engine if engine else SoundboardEngine(self)

        self.cards: dict[str, SoundCardWidget] = {}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 10, 14, 10)
        main_layout.setSpacing(10)

        # ----------------- 1. MASTER CONTROL & TOOLBAR HEADER -----------------
        self.card_header = QFrame()
        self.card_header.setObjectName("soundboardHeader")
        self.card_header.setStyleSheet("""
            QFrame#soundboardHeader {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                color: #e4e4e7;
            }
            QPushButton {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 6px 12px;
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
            QComboBox, QLineEdit {
                background-color: #27272a;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 4px 8px;
                color: #ffffff;
            }
        """)

        header_layout = QVBoxLayout(self.card_header)
        header_layout.setSpacing(8)
        header_layout.setContentsMargins(10, 8, 10, 8)

        # Row 1: Volume, Stop All, Add, Open Folder
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        # Mute toggle
        self.btn_mute = QPushButton("Mute")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setFixedSize(42, 24)
        self.btn_mute.setToolTip("Toggle Mute")
        self.btn_mute.setStyleSheet("font-size: 11px; padding: 2px 4px; background: #27272a; border: 1px solid #3f3f46; border-radius: 4px; font-weight: bold;")
        self.btn_mute.clicked.connect(self._toggle_mute)
        row1.addWidget(self.btn_mute)

        lbl_vol = QLabel("Vol:")
        lbl_vol.setStyleSheet("font-size: 11px; font-weight: bold; color: #a1a1aa;")
        row1.addWidget(lbl_vol)

        self.slider_master = QSlider(Qt.Orientation.Horizontal)
        self.slider_master.setRange(0, 100)
        self.slider_master.setValue(int(self.engine.master_volume * 100))
        self.slider_master.setFixedWidth(70)
        self.slider_master.valueChanged.connect(self._on_master_slider_changed)
        row1.addWidget(self.slider_master)

        self.lbl_master_val = QLabel(f"{int(self.engine.master_volume * 100)}%")
        self.lbl_master_val.setFixedWidth(28)
        self.lbl_master_val.setStyleSheet("font-size: 11px; font-weight: bold;")
        row1.addWidget(self.lbl_master_val)

        row1.addStretch()

        # Solo / Exclusive mode checkbox
        self.chk_exclusive = QCheckBox("Solo")
        self.chk_exclusive.setToolTip("Solo Mode: stops other playing clips when starting a new sound")
        self.chk_exclusive.setChecked(self.engine.exclusive_mode)
        self.chk_exclusive.toggled.connect(self._on_exclusive_toggled)
        self.chk_exclusive.setStyleSheet("font-size: 10px; color: #a1a1aa;")
        row1.addWidget(self.chk_exclusive)

        # Emergency STOP ALL button
        self.btn_stop_all = QPushButton("⏹ STOP ALL")
        self.btn_stop_all.setFixedHeight(24)
        self.btn_stop_all.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                border: 1px solid #b91c1c;
                color: #ffffff;
                font-weight: bold;
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        self.btn_stop_all.clicked.connect(self.engine.stop_all)
        row1.addWidget(self.btn_stop_all)

        # Add Sound button
        self.btn_add = QPushButton("➕ Add")
        self.btn_add.setFixedHeight(24)
        self.btn_add.setStyleSheet("""
            QPushButton {
                background-color: #22c55e;
                border: 1px solid #16a34a;
                color: #ffffff;
                font-weight: bold;
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #16a34a;
            }
        """)
        self.btn_add.clicked.connect(self._open_add_dialog)
        row1.addWidget(self.btn_add)

        # Open sounds folder
        self.btn_folder = QPushButton("📁 Folder")
        self.btn_folder.setFixedHeight(24)
        self.btn_folder.setToolTip("Open audio files directory in Windows Explorer")
        self.btn_folder.setStyleSheet("font-size: 10px; padding: 2px 6px; border-radius: 4px;")
        self.btn_folder.clicked.connect(self._open_sounds_folder)
        row1.addWidget(self.btn_folder)

        header_layout.addLayout(row1)

        # Row 2: Audio Device routing & Search filter
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        lbl_device = QLabel("🎧 Device:")
        lbl_device.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        row2.addWidget(lbl_device)

        self.combo_device = QComboBox()
        self.combo_device.setFixedHeight(24)
        self.combo_device.setMaximumWidth(150)
        self.combo_device.setStyleSheet("font-size: 10px;")
        self._populate_audio_devices()
        self.combo_device.currentIndexChanged.connect(self._on_device_changed)
        row2.addWidget(self.combo_device)

        # Category filter
        lbl_filter = QLabel("Cat:")
        lbl_filter.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        row2.addWidget(lbl_filter)

        self.combo_filter_cat = QComboBox()
        self.combo_filter_cat.setFixedHeight(24)
        self.combo_filter_cat.setMaximumWidth(85)
        self.combo_filter_cat.setStyleSheet("font-size: 10px;")
        self._refresh_categories_filter()
        self.combo_filter_cat.currentIndexChanged.connect(self._apply_filters)
        row2.addWidget(self.combo_filter_cat)

        # Search bar
        self.edit_search = QLineEdit()
        self.edit_search.setFixedHeight(24)
        self.edit_search.setPlaceholderText("🔍 Search sounds...")
        self.edit_search.setStyleSheet("font-size: 10px; padding: 1px 4px;")
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.textChanged.connect(self._apply_filters)
        row2.addWidget(self.edit_search, 1)

        header_layout.addLayout(row2)
        main_layout.addWidget(self.card_header)

        # ----------------- 2. SOUND CLIPS SCROLL MATRIX -----------------
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
        """)

        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setContentsMargins(4, 4, 4, 4)

        self.scroll_area.setWidget(self.grid_container)
        main_layout.addWidget(self.scroll_area, 1)

        # Empty state label
        self.lbl_empty = QLabel("No sound clips found. Click <b>'➕ Add Sound'</b> to import audio files.")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet("font-size: 13px; color: #71717a; padding: 40px;")
        self.lbl_empty.setVisible(False)
        main_layout.addWidget(self.lbl_empty)

        # Hook engine signals
        self.engine.clip_started.connect(self._on_clip_started)
        self.engine.clip_stopped.connect(self._on_clip_stopped)
        self.engine.clips_updated.connect(self._rebuild_grid)

        # Initial populate
        self._rebuild_grid()

    def _populate_audio_devices(self):
        self.combo_device.blockSignals(True)
        self.combo_device.clear()
        self.combo_device.addItem("🔊 System Default Audio Device", "")

        devices = self.engine.get_output_devices()
        sel_idx = 0
        for idx, dev_name in enumerate(devices, start=1):
            self.combo_device.addItem(f"🎧 {dev_name}", dev_name)
            if dev_name == self.engine.selected_device_name:
                sel_idx = idx

        self.combo_device.setCurrentIndex(sel_idx)
        self.combo_device.blockSignals(False)

    def _on_device_changed(self, idx):
        dev_name = self.combo_device.currentData() or ""
        self.engine.set_output_device(dev_name)

    def _toggle_mute(self):
        new_mute = not self.engine.is_muted
        self.engine.set_muted(new_mute)
        self.btn_mute.setText("Unmute" if new_mute else "Mute")
        bg = "#ef4444" if new_mute else "#27272a"
        fg = "#ffffff" if new_mute else "#a1a1aa"
        self.btn_mute.setStyleSheet(f"font-size: 11px; padding: 2px 4px; background: {bg}; border: 1px solid #3f3f46; border-radius: 4px; font-weight: bold; color: {fg};")

    def _on_master_slider_changed(self, val):
        self.lbl_master_val.setText(f"{val}%")
        self.engine.set_master_volume(val / 100.0)

    def _on_exclusive_toggled(self, checked):
        self.engine.exclusive_mode = checked
        self.engine.save_config()

    def _open_sounds_folder(self):
        try:
            os.startfile(self.engine.sounds_dir)
        except Exception as e:
            QMessageBox.information(self, "Sounds Directory", f"Audio directory:\n{self.engine.sounds_dir}")

    def _refresh_categories_filter(self):
        cur_cat = self.combo_filter_cat.currentText()
        self.combo_filter_cat.blockSignals(True)
        self.combo_filter_cat.clear()
        cats = self.engine.get_categories()
        for c in cats:
            self.combo_filter_cat.addItem(c)
        idx = self.combo_filter_cat.findText(cur_cat)
        if idx >= 0:
            self.combo_filter_cat.setCurrentIndex(idx)
        self.combo_filter_cat.blockSignals(False)

    def _rebuild_grid(self):
        # Clear existing
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.cards.clear()

        self._refresh_categories_filter()

        # Render cards in responsive 2-column layout
        num_cols = 2
        visible_clips = self._get_filtered_clips()

        if not visible_clips:
            self.lbl_empty.setVisible(True)
            self.scroll_area.setVisible(False)
            return
        else:
            self.lbl_empty.setVisible(False)
            self.scroll_area.setVisible(True)

        for idx, clip in enumerate(visible_clips):
            card = SoundCardWidget(clip, self)
            card.play_requested.connect(self.engine.play_clip)
            card.stop_requested.connect(self.engine.stop_clip)
            card.edit_requested.connect(self._open_edit_dialog)
            card.delete_requested.connect(self._delete_clip)
            card.volume_changed.connect(lambda cid, vol: self.engine.update_clip(cid, volume=vol))

            if self.engine.is_clip_playing(clip.id):
                card.set_playing_state(True)

            self.cards[clip.id] = card
            self.grid_layout.addWidget(card, idx // num_cols, idx % num_cols)

    def _apply_filters(self):
        self._rebuild_grid()

    def _get_filtered_clips(self):
        cat_filter = self.combo_filter_cat.currentText()
        search_query = self.edit_search.text().strip().lower()

        filtered = []
        for clip in self.engine.clips:
            if cat_filter and cat_filter != "All" and clip.category.lower() != cat_filter.lower():
                continue
            if search_query and (search_query not in clip.name.lower() and search_query not in clip.category.lower()):
                continue
            filtered.append(clip)
        return filtered

    def _open_add_dialog(self):
        dlg = SoundClipDialog(
            clip=None,
            categories=self.engine.get_categories(),
            parent=self,
            engine=self.engine
        )
        if dlg.exec():
            data = dlg.get_data()
            self.engine.add_clip(**data)

    def _open_edit_dialog(self, clip_id: str):
        clip = self.engine.get_clip_by_id(clip_id)
        if not clip:
            return
        dlg = SoundClipDialog(
            clip=clip,
            categories=self.engine.get_categories(),
            parent=self,
            engine=self.engine
        )
        if dlg.exec():
            data = dlg.get_data()
            self.engine.update_clip(clip_id, **data)

    def _delete_clip(self, clip_id: str):
        clip = self.engine.get_clip_by_id(clip_id)
        if not clip:
            return
        res = QMessageBox.question(
            self,
            "Delete Sound Clip",
            f"Are you sure you want to remove '{clip.name}' from your Soundboard?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.engine.remove_clip(clip_id)

    def _on_clip_started(self, clip_id: str, name: str):
        if clip_id in self.cards:
            self.cards[clip_id].set_playing_state(True)

    def _on_clip_stopped(self, clip_id: str):
        if clip_id in self.cards:
            self.cards[clip_id].set_playing_state(False)
