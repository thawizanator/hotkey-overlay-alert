"""
Unified Hotkey & Peripheral Tab for Streamer Calyx (Phase 5)
Provides master shortcut management, real-time controller visualizer HUD,
multi-device recording (Keyboard, Mouse, Gamepad), and conflict detection.
"""

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QCheckBox, QDialog, QGroupBox, QScrollArea, QFrame, QMessageBox
)
from PyQt6.QtGui import QColor, QFont

from input_manager import InputManager, normalize_chord


ACTION_DESCRIPTIONS = {
    "primary_overlay": "Flashes or highlights the primary streamer monitor alert border overlay.",
    "macro_0": "Executes Twitch Chat Macro 1 command automatically in your channel.",
    "macro_1": "Executes Twitch Chat Macro 2 command automatically in your channel.",
    "macro_2": "Executes Twitch Chat Macro 3 command automatically in your channel.",
    "macro_3": "Executes Twitch Chat Macro 4 command automatically in your channel.",
    "macro_4": "Executes Twitch Chat Macro 5 command automatically in your channel.",
    "chronos_toggle": "Starts, pauses, or resumes the active Chronos countdown / stopwatch timer.",
    "chronos_reset": "Resets the active Chronos countdown or stopwatch timer to its starting duration.",
    "cycler_next": "Advances to the next trivia question or rotating text message on screen.",
    "cycler_prev": "Steps back to the previous trivia question or rotating text message.",
    "cycler_pause": "Pauses or resumes the automatic trivia / text cycler rotation interval.",
    "director_toggle": "Toggles the Stream Director Dock panel visibility on screen.",
    "director_scene_1": "Switches OBS / SLOBS active scene to Scene 1.",
    "director_scene_2": "Switches OBS / SLOBS active scene to Scene 2.",
    "director_scene_3": "Switches OBS / SLOBS active scene to Scene 3.",
    "director_scene_4": "Switches OBS / SLOBS active scene to Scene 4.",
    "director_scene_5": "Switches OBS / SLOBS active scene to Scene 5.",
    "director_scene_6": "Switches OBS / SLOBS active scene to Scene 6.",
    "director_scene_7": "Switches OBS / SLOBS active scene to Scene 7.",
    "director_scene_8": "Switches OBS / SLOBS active scene to Scene 8.",
    "director_mute_1": "Toggles mute / unmute on Audio Source 1 (Microphone).",
    "director_mute_2": "Toggles mute / unmute on Audio Source 2 (Desktop / Game Audio).",
    "director_mute_3": "Toggles mute / unmute on Audio Source 3 (Music / Media).",
    "director_mute_4": "Toggles mute / unmute on Audio Source 4 (Discord / Voice Chat).",
    "director_mute_5": "Toggles mute / unmute on Audio Source 5 (Alerts / Soundboard).",
    "director_mute_6": "Toggles mute / unmute on Audio Source 6.",
    "director_mute_7": "Toggles mute / unmute on Audio Source 7.",
    "director_mute_8": "Toggles mute / unmute on Audio Source 8.",
}


class ControllerVisualizerWidget(QFrame):
    """
    Live visualizer HUD for connected gamepads.
    Highlights buttons in real-time as the user presses them on their physical controller.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("controllerVisualizer")
        self.setStyleSheet("""
            QFrame#controllerVisualizer {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Header with connection indicator
        hdr_row = QHBoxLayout()
        self.lbl_status = QLabel("🎮 Controller Status: Checking...")
        self.lbl_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #adadb8;")
        hdr_row.addWidget(self.lbl_status)
        hdr_row.addStretch()

        self.lbl_slot_info = QLabel("Slot: Index 0 (XInput)")
        self.lbl_slot_info.setStyleSheet("font-size: 11px; color: #71717a;")
        hdr_row.addWidget(self.lbl_slot_info)
        layout.addLayout(hdr_row)

        # Button badges grid
        btn_grid = QHBoxLayout()
        btn_grid.setSpacing(6)

        self.badge_widgets = {}
        self._last_connected = None

        # Row 1: Shoulder & Center Controls
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        row1.addWidget(self._make_badge("LT", "LT", 26))
        row1.addWidget(self._make_badge("LB", "LB", 26))
        row1.addSpacing(6)
        row1.addWidget(self._make_badge("LS Click", "LS", 26))
        row1.addWidget(self._make_badge("Back", "Back", 36))
        row1.addWidget(self._make_badge("Guide", "Guide", 40))
        row1.addWidget(self._make_badge("Start", "Start", 36))
        row1.addWidget(self._make_badge("RS Click", "RS", 26))
        row1.addSpacing(6)
        row1.addWidget(self._make_badge("RB", "RB", 26))
        row1.addWidget(self._make_badge("RT", "RT", 26))
        row1.addStretch()
        layout.addLayout(row1)

        # Row 2: D-Pad & Face Buttons
        row2 = QHBoxLayout()
        row2.setSpacing(4)
        lbl_dpad_tag = QLabel("D-Pad:")
        lbl_dpad_tag.setStyleSheet("color: #71717a; font-size: 10px; font-weight: bold;")
        row2.addWidget(lbl_dpad_tag)
        row2.addWidget(self._make_badge("D-Pad Up", "▲", 24))
        row2.addWidget(self._make_badge("D-Pad Down", "▼", 24))
        row2.addWidget(self._make_badge("D-Pad Left", "◄", 24))
        row2.addWidget(self._make_badge("D-Pad Right", "►", 24))

        row2.addSpacing(16)

        lbl_face_tag = QLabel("Buttons:")
        lbl_face_tag.setStyleSheet("color: #71717a; font-size: 10px; font-weight: bold;")
        row2.addWidget(lbl_face_tag)
        row2.addWidget(self._make_badge("X", "X", 24))
        row2.addWidget(self._make_badge("Y", "Y", 24))
        row2.addWidget(self._make_badge("A", "A", 24))
        row2.addWidget(self._make_badge("B", "B", 24))
        row2.addStretch()
        layout.addLayout(row2)

    def _make_badge(self, b_id, b_label, width=28):
        lbl = QLabel(b_label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setFixedSize(width, 22)
        lbl.setProperty("active", False)
        self._apply_badge_style(lbl, active=False)
        self.badge_widgets[b_id] = lbl
        return lbl

    def _apply_badge_style(self, lbl, active=False):
        if active:
            lbl.setStyleSheet("""
                background-color: #9146ff;
                color: #ffffff;
                font-size: 10px;
                font-weight: bold;
                border: 1px solid #a855f7;
                border-radius: 4px;
            """)
        else:
            lbl.setStyleSheet("""
                background-color: #27272a;
                color: #a1a1aa;
                font-size: 10px;
                font-weight: 600;
                border: 1px solid #3f3f46;
                border-radius: 4px;
            """)

    def update_state(self, connected, pressed_buttons, lt, rt):
        if self._last_connected != connected:
            self._last_connected = connected
            if connected:
                self.lbl_status.setText("🎮 Controller: Connected (PowerA / XInput Device Active)")
                self.lbl_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #34d399;")
            else:
                self.lbl_status.setText("🎮 Controller: Disconnected (Plug in USB or Bluetooth gamepad)")
                self.lbl_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #ef4444;")

        pressed_set = set(pressed_buttons)
        for b_id, lbl in self.badge_widgets.items():
            is_active = b_id in pressed_set
            if lbl.property("active") != is_active:
                lbl.setProperty("active", is_active)
                self._apply_badge_style(lbl, active=is_active)


class ShortcutRecordDialog(QDialog):
    """
    1-Click multi-device shortcut recorder modal.
    Captures input across Keyboard, Mouse, and Gamepad with live conflict detection.
    """
    def __init__(self, action_id, action_name, input_mgr, current_binding, parent=None):
        super().__init__(parent)
        self.action_id = action_id
        self.action_name = action_name
        self.input_mgr = input_mgr
        self.current_binding = current_binding

        self.detected_device = current_binding.get("device", "keyboard")
        self.detected_binding = current_binding.get("binding", "")
        self.detected_hold = current_binding.get("hold", 0.0)

        self.setWindowTitle(f"Record Shortcut – {action_name}")
        self.setFixedSize(480, 310)
        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
                color: #efeff1;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Instructions
        lbl_info = QLabel(f"<b>Assigning shortcut for:</b> <span style='color:#a855f7;'>{action_name}</span><br>"
                          "Press any key on your <b>Keyboard</b>, <b>Mouse Button</b>, or <b>Controller Button / Chord</b>.")
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("font-size: 13px; color: #efeff1;")
        layout.addWidget(lbl_info)

        # Live Display Box
        self.lbl_display = QLabel("Listening for input...")
        self.lbl_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_display.setStyleSheet("""
            background-color: #121214;
            border: 2px dashed #9146ff;
            border-radius: 8px;
            padding: 16px;
            font-size: 16px;
            font-weight: bold;
            color: #38bdf8;
        """)
        layout.addWidget(self.lbl_display)

        # Conflict Warning Label
        self.lbl_conflict = QLabel("")
        self.lbl_conflict.setStyleSheet("font-size: 11px; font-weight: bold; color: #f87171;")
        self.lbl_conflict.setVisible(False)
        layout.addWidget(self.lbl_conflict)

        # Hold Threshold Controls
        hold_row = QHBoxLayout()
        hold_row.addWidget(QLabel("Activation Trigger Delay:"))
        self.combo_hold = QComboBox()
        self.combo_hold.addItem("Instant (0.0s - Tap to activate)", 0.0)
        self.combo_hold.addItem("Hold for 0.5s (Recommended for controllers)", 0.5)
        self.combo_hold.addItem("Hold for 0.75s", 0.75)
        self.combo_hold.addItem("Hold for 1.0s (Long hold shield)", 1.0)
        
        # Set existing hold
        cur_hold = float(self.detected_hold)
        for i in range(self.combo_hold.count()):
            if abs(self.combo_hold.itemData(i) - cur_hold) < 0.01:
                self.combo_hold.setCurrentIndex(i)
                break
        hold_row.addWidget(self.combo_hold)
        layout.addLayout(hold_row)

        layout.addStretch()

        # Action Buttons
        btn_box = QHBoxLayout()
        self.btn_clear = QPushButton("Clear Shortcut")
        self.btn_clear.clicked.connect(self._on_clear)
        btn_box.addWidget(self.btn_clear)

        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Shortcut")
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #9146ff;
                color: #ffffff;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #a970ff;
            }
        """)
        self.btn_save.clicked.connect(self.accept)
        btn_box.addWidget(self.btn_save)

        layout.addLayout(btn_box)

        # Suspend keyboard hooks while modal is recording
        if hasattr(self.input_mgr, "unbind_all_keyboard"):
            self.input_mgr.unbind_all_keyboard()

        # Connect to peripheral worker recording signal
        self.input_mgr.worker.set_recording_mode(True)
        self.input_mgr.worker.raw_input_captured_signal.connect(self._on_peripheral_captured)

        if self.detected_binding:
            self._update_display(self.detected_device, self.detected_binding)

    def keyPressEvent(self, event):
        """Captures keyboard keys."""
        from settings_ui import qt_key_to_keyboard_str
        key = event.key()
        if key in [Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta]:
            return # Wait for combination key

        mods = []
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier: mods.append("ctrl")
        if event.modifiers() & Qt.KeyboardModifier.AltModifier: mods.append("alt")
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier: mods.append("shift")
        if event.modifiers() & Qt.KeyboardModifier.MetaModifier: mods.append("windows")

        k_str = qt_key_to_keyboard_str(key, event.text())
        if not k_str:
            k_str = f"key_{key}"

        combo = "+".join(mods + [k_str]) if mods else k_str
        self._update_display("keyboard", combo)

    def _on_peripheral_captured(self, device, binding):
        """Called when mouse or gamepad input is recorded."""
        self._update_display(device, binding)

    def _update_display(self, device, binding):
        self.detected_device = device
        self.detected_binding = binding
        icon = "⌨️" if device == "keyboard" else ("🖱️" if device == "mouse" else "🎮")
        pretty = " + ".join(binding.split("+")) if binding else "Not Set"
        self.lbl_display.setText(f"{icon}  {pretty}")

        # Check for conflicts
        conflict = self.input_mgr.check_conflict(device, binding, exclude_action_id=self.action_id)
        if conflict:
            self.lbl_conflict.setText(f"⚠️ Conflict Warning: Already used by '{conflict['name']}' ({conflict['category']}).")
            self.lbl_conflict.setVisible(True)
        else:
            self.lbl_conflict.setVisible(False)

    def _on_clear(self):
        self.detected_binding = ""
        self.lbl_display.setText("Not Set")
        self.lbl_conflict.setVisible(False)
        if self.input_mgr and self.input_mgr.worker:
            self.input_mgr.worker.set_recording_mode(True)

    def get_result(self):
        return {
            "device": self.detected_device,
            "binding": self.detected_binding,
            "hold": self.combo_hold.currentData(),
            "enabled": bool(self.detected_binding)
        }

    def _cleanup_recording(self):
        try:
            self.input_mgr.worker.raw_input_captured_signal.disconnect(self._on_peripheral_captured)
        except Exception:
            pass
        self.input_mgr.worker.set_recording_mode(False)
        if hasattr(self.input_mgr, "_sync_keyboard_hooks"):
            self.input_mgr._sync_keyboard_hooks()

    def closeEvent(self, event):
        self._cleanup_recording()
        super().closeEvent(event)

    def accept(self):
        self._cleanup_recording()
        super().accept()

    def reject(self):
        self._cleanup_recording()
        super().reject()


class HotkeyCardWidget(QFrame):
    """
    Expandable accordion drawer card for an individual hotkey action.
    Default (collapsed): shows Hotkey Name, Type/Binding Badge, and Edit button.
    Expanded (drawer): reveals Category, Action Command / Details, Hold Delay dropdown, Set Hotkey, and Clear Hotkey buttons.
    Guarantees a responsive fit without any horizontal scrollbars or cutoffs.
    """
    def __init__(self, action_def, binding_info, parent_tab, parent=None):
        super().__init__(parent)
        self.action_def = action_def
        self.binding_info = binding_info
        self.parent_tab = parent_tab
        self.action_id = action_def["id"]
        self.is_expanded = False

        self.setObjectName("hotkeyCard")
        self._apply_frame_style(active=False)

        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # 1. HEADER ROW (Clickable)
        self.header_frame = QFrame()
        self.header_frame.setObjectName("hotkeyHeader")
        self.header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_frame.setStyleSheet("""
            QFrame#hotkeyHeader {
                background-color: transparent;
                border-radius: 6px;
            }
            QFrame#hotkeyHeader:hover {
                background-color: #27272a;
            }
        """)

        hdr_layout = QHBoxLayout(self.header_frame)
        hdr_layout.setContentsMargins(10, 7, 10, 7)
        hdr_layout.setSpacing(8)

        # Chevron indicator
        self.lbl_chevron = QLabel("▶")
        self.lbl_chevron.setStyleSheet("color: #a855f7; font-size: 11px; font-weight: bold;")
        hdr_layout.addWidget(self.lbl_chevron)

        # Hotkey Name (Display concise title)
        display_name = action_def["name"]
        if " (" in display_name and action_def.get("category") == "Twitch Macros":
            display_name = display_name.split(" (")[0]

        self.lbl_name = QLabel(display_name)
        self.lbl_name.setStyleSheet("font-size: 13px; font-weight: bold; color: #efeff1;")
        hdr_layout.addWidget(self.lbl_name)

        hdr_layout.addStretch()

        # Type & Current Shortcut Combined Badge
        self.lbl_type_badge = QLabel()
        hdr_layout.addWidget(self.lbl_type_badge)

        # Edit Button
        self.btn_edit = QPushButton("Edit  ▼")
        self.btn_edit.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
                border-radius: 4px;
                border: 1px solid #3f3f46;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        self.btn_edit.clicked.connect(self.toggle_drawer)
        hdr_layout.addWidget(self.btn_edit)

        card_layout.addWidget(self.header_frame)

        # Clicking anywhere on the header toggles the drawer
        self.header_frame.mousePressEvent = self._on_header_clicked

        # 2. DRAWER CONTAINER (Collapsed by default)
        self.drawer = QFrame()
        self.drawer.setObjectName("hotkeyDrawer")
        self.drawer.setVisible(False)
        self.drawer.setStyleSheet("""
            QFrame#hotkeyDrawer {
                background-color: #121214;
                border-top: 1px solid #27272a;
                border-radius: 0px 0px 6px 6px;
            }
        """)

        drawer_layout = QVBoxLayout(self.drawer)
        drawer_layout.setContentsMargins(12, 10, 12, 10)
        drawer_layout.setSpacing(8)

        # Row 1: Category & Details
        cat_name = self.action_def.get("category", "")
        desc_text = ACTION_DESCRIPTIONS.get(self.action_id, "Executes the bound streamer action.")
        raw_name = self.action_def.get("name", "")
        extra_detail = ""
        if " (" in raw_name and ")" in raw_name:
            extra_detail = raw_name[raw_name.find("(") + 1 : raw_name.rfind(")")]

        info_html = f"<span style='color:#adadb8;'>Category:</span> <b style='color:#a970ff;'>{cat_name}</b>"
        if extra_detail:
            info_html += f" &nbsp;•&nbsp; <span style='color:#adadb8;'>Command:</span> <code style='color:#a970ff;'>{extra_detail}</code>"
        info_html += f"<br><span style='color:#adadb8;'>Function:</span> <span style='color:#efeff1;'>{desc_text}</span>"

        lbl_info = QLabel(info_html)
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("font-size: 11px; line-height: 140%;")
        drawer_layout.addWidget(lbl_info)

        # Row 2: Hold Delay Configuration
        config_row = QHBoxLayout()
        config_row.setSpacing(8)

        lbl_hold_title = QLabel("Activation Delay:")
        lbl_hold_title.setStyleSheet("font-size: 11px; color: #adadb8;")
        config_row.addWidget(lbl_hold_title)

        self.combo_hold = QComboBox()
        self.combo_hold.addItem("Instant (0.0s - Tap to activate)", 0.0)
        self.combo_hold.addItem("Hold for 0.5s (Recommended for controllers)", 0.5)
        self.combo_hold.addItem("Hold for 0.75s", 0.75)
        self.combo_hold.addItem("Hold for 1.0s (Long hold shield)", 1.0)
        self.combo_hold.setMinimumWidth(180)
        self.combo_hold.setMaximumWidth(260)
        self.combo_hold.currentIndexChanged.connect(self._on_hold_changed)
        config_row.addWidget(self.combo_hold)
        config_row.addStretch()
        drawer_layout.addLayout(config_row)

        # Row 3: Action Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_record = QPushButton("🎮 / ⌨️  Set Hotkey")
        self.btn_record.setStyleSheet("""
            QPushButton {
                background-color: #9146ff;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 5px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #a970ff;
            }
        """)
        self.btn_record.clicked.connect(self._on_record_clicked)
        btn_row.addWidget(self.btn_record)

        self.btn_clear = QPushButton("🗑️ Clear Hotkey")
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #ef4444;
                font-size: 11px;
                font-weight: 600;
                padding: 5px 12px;
                border-radius: 4px;
                border: 1px solid #3f3f46;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                color: #f87171;
            }
        """)
        self.btn_clear.clicked.connect(self._on_clear_clicked)
        btn_row.addWidget(self.btn_clear)

        btn_row.addStretch()

        self.btn_collapse = QPushButton("▲ Close")
        self.btn_collapse.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #71717a;
                font-size: 11px;
                padding: 4px 8px;
                border: none;
            }
            QPushButton:hover {
                color: #efeff1;
            }
        """)
        self.btn_collapse.clicked.connect(self.toggle_drawer)
        btn_row.addWidget(self.btn_collapse)

        drawer_layout.addLayout(btn_row)
        card_layout.addWidget(self.drawer)

        # Update visual display with initial binding values
        self.update_binding_info(self.binding_info)

    def _apply_frame_style(self, active=False):
        border_col = "#9146ff" if active else "#3f3f46"
        self.setStyleSheet(f"""
            QFrame#hotkeyCard {{
                background-color: #18181b;
                border: 1px solid {border_col};
                border-radius: 6px;
            }}
            QFrame#hotkeyCard:hover {{
                border: 1px solid #52525b;
            }}
        """)

    def _on_header_clicked(self, event):
        self.toggle_drawer()

    def toggle_drawer(self):
        self.set_expanded(not self.is_expanded)

    def set_expanded(self, expanded):
        self.is_expanded = expanded
        self.drawer.setVisible(expanded)
        self.lbl_chevron.setText("▼" if expanded else "▶")
        self.btn_edit.setText("Done  ▲" if expanded else "Edit  ▼")
        self._apply_frame_style(active=expanded)

    def update_binding_info(self, b_info):
        self.binding_info = b_info
        device = b_info.get("device", "keyboard")
        b_str = b_info.get("binding", "")
        hold = float(b_info.get("hold", 0.0))

        # Single combined type & binding badge
        if b_str:
            disp_str = " + ".join(b_str.split("+"))
            dev_icon = "⌨️ " if device == "keyboard" else ("🖱️ " if device == "mouse" else "🎮 ")
            self.lbl_type_badge.setText(f"{dev_icon}{disp_str}")
            self.lbl_type_badge.setStyleSheet("""
                background-color: #27272a;
                color: #a970ff;
                font-weight: bold;
                font-size: 11px;
                padding: 3px 8px;
                border-radius: 4px;
                border: 1px solid #9146ff;
            """)
        else:
            self.lbl_type_badge.setText("Not Set")
            self.lbl_type_badge.setStyleSheet("""
                background-color: #18181b;
                color: #71717a;
                font-weight: 500;
                font-size: 11px;
                padding: 3px 8px;
                border-radius: 4px;
                border: 1px solid #27272a;
            """)

        # Set hold combo without triggering change signal
        self.combo_hold.blockSignals(True)
        for i in range(self.combo_hold.count()):
            if abs(self.combo_hold.itemData(i) - hold) < 0.01:
                self.combo_hold.setCurrentIndex(i)
                break
        self.combo_hold.blockSignals(False)

    def _on_hold_changed(self):
        new_hold = self.combo_hold.currentData()
        self.parent_tab.set_action_hold(self.action_id, new_hold)

    def _on_record_clicked(self):
        self.parent_tab.open_record_dialog(self.action_id, self.action_def["name"], self.binding_info)

    def _on_clear_clicked(self):
        self.parent_tab.clear_action_binding(self.action_id)


class HotkeysTab(QWidget):
    """
    Central Hotkeys & Peripherals Management View.
    Contains the controller diagnostic HUD and expandable card list for zero horizontal scrolling.
    """
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_win = main_window
        self.overlay = getattr(main_window, "overlay", None)
        self.input_mgr = getattr(self.overlay, "input_manager", None)
        self._active_slot = 0
        self.cards = {}  # action_id -> HotkeyCardWidget

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Controller Live Visualizer HUD
        self.visualizer = ControllerVisualizerWidget(self)
        layout.addWidget(self.visualizer)

        # Connect peripheral worker to visualizer
        if self.input_mgr and self.input_mgr.worker:
            self.input_mgr.worker.gamepad_status_signal.connect(self._on_gamepad_state)

        # 2. Control Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        lbl_filt = QLabel("Filter:")
        lbl_filt.setStyleSheet("color: #adadb8; font-size: 11px; font-weight: bold;")
        toolbar.addWidget(lbl_filt)

        self.combo_filter = QComboBox()
        self.combo_filter.addItems([
            "All Categories",
            "Alerts & Highlights",
            "Twitch Macros",
            "Stream Timing",
            "Trivia & Text",
            "Stream Director"
        ])
        self.combo_filter.setMinimumWidth(120)
        self.combo_filter.setMaximumWidth(140)
        self.combo_filter.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.combo_filter)

        toolbar.addStretch()

        self.btn_expand_all = QPushButton("Expand All")
        self.btn_expand_all.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #adadb8;
                border: 1px solid #3f3f46;
                font-size: 10px;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                color: #efeff1;
            }
        """)
        self.btn_expand_all.clicked.connect(lambda: self.set_all_expanded(True))
        toolbar.addWidget(self.btn_expand_all)

        self.btn_collapse_all = QPushButton("Collapse All")
        self.btn_collapse_all.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #adadb8;
                border: 1px solid #3f3f46;
                font-size: 10px;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                color: #efeff1;
            }
        """)
        self.btn_collapse_all.clicked.connect(lambda: self.set_all_expanded(False))
        toolbar.addWidget(self.btn_collapse_all)

        self.btn_reset_defaults = QPushButton("Reset Defaults")
        self.btn_reset_defaults.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                border: 1px solid #3f3f46;
                font-size: 10px;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                color: #ffffff;
            }
        """)
        self.btn_reset_defaults.clicked.connect(self.reset_all_defaults)
        toolbar.addWidget(self.btn_reset_defaults)

        layout.addLayout(toolbar)

        # Description
        lbl_desc = QLabel("Click any hotkey title to open its settings drawer. Assign shortcuts across Keyboard, Mouse, and Gamepad.")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #adadb8; font-size: 11px; margin-bottom: 2px;")
        layout.addWidget(lbl_desc)

        # 3. Scrollable Card List Area (Zero Horizontal Scrollbars!)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #27272a;
                border-radius: 6px;
                background-color: #121214;
            }
            QScrollBar:vertical {
                background-color: #18181b;
                width: 6px;
                border-radius: 3px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #3f3f46;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #9146ff;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background-color: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(5)

        self.scroll_area.setWidget(self.cards_container)
        layout.addWidget(self.scroll_area)

        # Populate cards
        self.populate_table()


    def _on_gamepad_state(self, slot, connected, pressed_buttons, lt, rt):
        """Passes live controller events to visualizer widget."""
        try:
            if connected:
                if getattr(self, "_active_slot", None) != slot:
                    self._active_slot = slot
                    self.visualizer.lbl_slot_info.setText(f"Slot: Index {slot} (XInput)")
                self.visualizer.update_state(True, pressed_buttons, lt, rt)
            elif getattr(self, "_active_slot", 0) == slot:
                self.visualizer.update_state(False, [], 0, 0)
        except (KeyboardInterrupt, SystemExit):
            pass
        except Exception:
            pass

    def populate_table(self):
        """Fills or refreshes all hotkey cards."""
        if not self.input_mgr:
            return

        actions = self.input_mgr.get_action_definitions() if hasattr(self.input_mgr, "get_action_definitions") else self.input_mgr.ACTION_DEFINITIONS

        # If cards already built, refresh their values
        if self.cards:
            for act in actions:
                act_id = act["id"]
                if act_id in self.cards:
                    b_info = self.input_mgr.bindings.get(act_id, {
                        "device": "keyboard",
                        "binding": act.get("default_key", ""),
                        "hold": 0.0,
                        "enabled": True
                    })
                    self.cards[act_id].update_binding_info(b_info)
            return

        # Build card widgets for the first time
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for act in actions:
            act_id = act["id"]
            binding_info = self.input_mgr.bindings.get(act_id, {
                "device": "keyboard",
                "binding": act.get("default_key", ""),
                "hold": 0.0,
                "enabled": True
            })
            card = HotkeyCardWidget(act, binding_info, self, self.cards_container)
            self.cards[act_id] = card
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()
        self._on_filter_changed(self.combo_filter.currentText())

    def _on_filter_changed(self, cat_text):
        for act_id, card in self.cards.items():
            if cat_text == "All Categories" or card.action_def["category"] == cat_text:
                card.setVisible(True)
            else:
                card.setVisible(False)

    def set_all_expanded(self, expanded):
        for card in self.cards.values():
            if card.isVisible():
                card.set_expanded(expanded)

    def set_action_hold(self, action_id, new_hold):
        b = self.input_mgr.bindings.get(action_id, {})
        self.input_mgr.set_binding(
            action_id=action_id,
            device=b.get("device", "keyboard"),
            binding_str=b.get("binding", ""),
            hold=new_hold,
            enabled=b.get("enabled", True)
        )
        if self.overlay and hasattr(self.overlay, "save_settings"):
            self.overlay.save_settings()

    def open_record_dialog(self, action_id, action_name, current_binding):
        dlg = ShortcutRecordDialog(action_id, action_name, self.input_mgr, current_binding, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            res = dlg.get_result()
            self.input_mgr.set_binding(
                action_id=action_id,
                device=res["device"],
                binding_str=res["binding"],
                hold=res["hold"],
                enabled=res["enabled"]
            )
            # Save to overlay config
            if self.overlay and hasattr(self.overlay, "save_settings"):
                self.overlay.save_settings()

            if hasattr(self.main_win, "tab_main") and hasattr(self.main_win.tab_main, "update_activation_hotkey_label"):
                self.main_win.tab_main.update_activation_hotkey_label()

            if action_id in self.cards:
                self.cards[action_id].update_binding_info(self.input_mgr.bindings[action_id])

    def clear_action_binding(self, action_id):
        self.input_mgr.clear_binding(action_id)
        if self.overlay and hasattr(self.overlay, "save_settings"):
            self.overlay.save_settings()
        if hasattr(self.main_win, "tab_main") and hasattr(self.main_win.tab_main, "update_activation_hotkey_label"):
            self.main_win.tab_main.update_activation_hotkey_label()
        if action_id in self.cards:
            self.cards[action_id].update_binding_info(self.input_mgr.bindings[action_id])

    def reset_all_defaults(self):
        res = QMessageBox.question(
            self,
            "Reset Shortcuts",
            "Are you sure you want to reset all shortcuts to default settings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.input_mgr.load_bindings({})
            if self.overlay and hasattr(self.overlay, "save_settings"):
                self.overlay.save_settings()
            if hasattr(self.main_win, "tab_main") and hasattr(self.main_win.tab_main, "update_activation_hotkey_label"):
                self.main_win.tab_main.update_activation_hotkey_label()
            for act_id, card in self.cards.items():
                b_info = self.input_mgr.bindings.get(act_id, {})
                card.update_binding_info(b_info)

