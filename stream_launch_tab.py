import os
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QCheckBox, QLineEdit, QMessageBox
)
from PyQt6.QtGui import QColor

from streamlabs_client import get_streamlabs_client
from debug_logger import log_debug

DEFAULT_CHECKLIST = [
    "Hydration prepared & water bottle filled",
    "OBS / Streamlabs Desktop running in Admin mode",
    "Game launched & tested in borderless windowed mode",
    "Discord / VoiceMeeter audio levels balanced with co-hosts",
    "Stream title, category, and Twitch tags updated",
    "Phone & peripheral notifications muted"
]

class StreamLaunchTab(QWidget):
    """
    Stream Launch Mission Control Tab
    Features NASA-style automated pre-flight diagnostics, custom checklist items,
    and a prominent master 'GO FOR LAUNCH' action that triggers SLOBS streaming,
    starts Chronos stream timers, and activates the Trivia cycler.
    """
    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self.main_win = main_win
        self.overlay = getattr(main_win, "overlay", None)
        self.slobs_client = get_streamlabs_client()

        self._custom_checkboxes = []
        self._is_live = False

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 8, 12, 8)
        root_layout.setSpacing(8)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        # ------------------ TOP HERO: GO FOR LAUNCH CARD ------------------
        card_launch = QFrame()
        card_launch.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #18181b, stop:1 #27272a);
                border: 2px solid #9146ff;
                border-radius: 8px;
                padding: 14px;
            }
        """)
        lay_launch = QVBoxLayout(card_launch)
        lay_launch.setSpacing(10)

        hdr_row = QHBoxLayout()
        lbl_title = QLabel("🚀  <b>MISSION CONTROL - STREAM LAUNCHPAD</b>")
        lbl_title.setStyleSheet("font-size: 14px; color: #efeff1; font-weight: bold; letter-spacing: 0.5px;")
        lbl_title.setToolTip("Central command orchestrator to verify all systems and initiate your broadcast.")
        hdr_row.addWidget(lbl_title)
        hdr_row.addStretch()

        self.lbl_stream_status = QLabel("<span style='color: #a1a1aa;'>● STANDBY</span>")
        self.lbl_stream_status.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_stream_status.setStyleSheet("font-size: 11px; font-weight: bold; padding: 2px 8px; background: #121214; border-radius: 4px; border: 1px solid #3f3f46;")
        hdr_row.addWidget(self.lbl_stream_status)
        lay_launch.addLayout(hdr_row)

        desc_lbl = QLabel(
            "Verify all pre-flight systems below. When ready, trigger the master launch to go live in Streamlabs, "
            "synchronize Chronos stream clocks, and start your Rotating Trivia cycler."
        )
        desc_lbl.setStyleSheet("font-size: 11px; color: #adadb8;")
        desc_lbl.setWordWrap(True)
        lay_launch.addWidget(desc_lbl)

        # Big Master Launch Button
        self.btn_master_launch = QPushButton("🚀  GO FOR LAUNCH")
        self.btn_master_launch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_master_launch.setToolTip("Initiates Streamlabs broadcast, starts Chronos count-up timer, and activates Trivia cycler.")
        self.btn_master_launch.setStyleSheet("""
            QPushButton {
                background-color: #9146ff;
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
                padding: 12px 20px;
                border-radius: 6px;
                border: 1px solid #a970ff;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background-color: #a970ff;
                border-color: #c084fc;
            }
            QPushButton:pressed {
                background-color: #7c3aed;
            }
        """)
        self.btn_master_launch.clicked.connect(self._on_master_launch_clicked)
        lay_launch.addWidget(self.btn_master_launch)

        layout.addWidget(card_launch)

        # ------------------ CARD 2: AUTOMATED DIAGNOSTICS CHECKLIST ------------------
        card_auto = QFrame()
        card_auto.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_auto = QVBoxLayout(card_auto)
        lay_auto.setSpacing(8)

        lbl_auto_title = QLabel("🛰️  <b>Automated System Telemetry & Readiness</b>")
        lbl_auto_title.setStyleSheet("font-size: 12px; color: #efeff1; font-weight: bold;")
        lbl_auto_title.setToolTip("Live hardware, IPC pipe, and API connectivity status.")
        lay_auto.addWidget(lbl_auto_title)

        self.lbl_chk_slobs = QLabel("• 📡 Streamlabs Desktop: Checking...")
        self.lbl_chk_slobs.setToolTip("Named Pipe and WebSocket RPC connection to Streamlabs Desktop.")
        self.lbl_chk_scene = QLabel("• 🎬 Active Broadcast Scene: Checking...")
        self.lbl_chk_scene.setToolTip("Verifies active broadcast scene name.")
        self.lbl_chk_twitch = QLabel("• 🟣 Twitch Integration: Checking...")
        self.lbl_chk_twitch.setToolTip("Twitch OAuth token validity and target broadcaster channel.")
        self.lbl_chk_audio = QLabel("• 🎙️ Auto-Clip Audio Capture: Checking...")
        self.lbl_chk_audio.setToolTip("Input capture device status and background level tracking.")
        self.lbl_chk_overlay = QLabel("• 🖼️ Monitor Highlight Overlay: Checking...")
        self.lbl_chk_overlay.setToolTip("Hardware border highlight readiness.")

        for lbl in [self.lbl_chk_slobs, self.lbl_chk_scene, self.lbl_chk_twitch, self.lbl_chk_audio, self.lbl_chk_overlay]:
            lbl.setStyleSheet("font-size: 11px; color: #adadb8;")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lay_auto.addWidget(lbl)

        btn_refresh = QPushButton("🔄 Refresh System Telemetry")
        btn_refresh.setToolTip("Re-poll Streamlabs, Twitch token, and audio devices.")
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                border: 1px solid #3f3f46;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        btn_refresh.clicked.connect(self.refresh_telemetry)
        lay_auto.addWidget(btn_refresh)

        layout.addWidget(card_auto)

        # ------------------ CARD 3: STREAMER PRE-FLIGHT CHECKLIST ------------------
        card_manual = QFrame()
        card_manual.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        self.lay_manual = QVBoxLayout(card_manual)
        self.lay_manual.setSpacing(6)

        hdr_man = QHBoxLayout()
        lbl_man_title = QLabel("📝  <b>Streamer Pre-Flight Checklist</b>")
        lbl_man_title.setStyleSheet("font-size: 12px; color: #efeff1; font-weight: bold;")
        lbl_man_title.setToolTip("Personalized pre-flight routine. Checked items are saved to config.")
        hdr_man.addWidget(lbl_man_title)
        hdr_man.addStretch()

        btn_reset_chk = QPushButton("Reset Checks")
        btn_reset_chk.setToolTip("Uncheck all items for your next stream.")
        btn_reset_chk.setStyleSheet("background-color: #27272a; color: #a1a1aa; border: 1px solid #3f3f46; font-size: 10px; padding: 2px 6px; border-radius: 3px;")
        btn_reset_chk.clicked.connect(self._reset_all_checks)
        hdr_man.addWidget(btn_reset_chk)
        self.lay_manual.addLayout(hdr_man)

        self.chk_container = QVBoxLayout()
        self.chk_container.setSpacing(4)
        self.lay_manual.addLayout(self.chk_container)

        # Add custom item bar
        row_add = QHBoxLayout()
        self.txt_new_item = QLineEdit()
        self.txt_new_item.setPlaceholderText("Add custom pre-stream checklist item...")
        self.txt_new_item.setStyleSheet("background-color: #27272a; color: #efeff1; border: 1px solid #3f3f46; padding: 4px 8px; font-size: 11px; border-radius: 4px;")
        self.txt_new_item.returnPressed.connect(self._add_custom_item)
        row_add.addWidget(self.txt_new_item)

        btn_add = QPushButton("➕ Add Item")
        btn_add.setStyleSheet("background-color: #27272a; color: #efeff1; border: 1px solid #3f3f46; padding: 4px 10px; font-size: 11px; border-radius: 4px;")
        btn_add.clicked.connect(self._add_custom_item)
        row_add.addWidget(btn_add)
        self.lay_manual.addLayout(row_add)

        layout.addWidget(card_manual)

        layout.addStretch()
        scroll_area.setWidget(container)
        root_layout.addWidget(scroll_area)

        # Populate saved or default checklist
        self._populate_checklist()
        self.refresh_telemetry()

        # Connect periodic auto-refresh timer (every 4 seconds)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.setInterval(4000)
        self.telemetry_timer.timeout.connect(self.refresh_telemetry)
        self.telemetry_timer.start()

    def refresh_telemetry(self):
        """Polls active hardware, pipe, and account states."""
        try:
            # 1. SLOBS Status
            connected = self.slobs_client.is_connected()
            if connected:
                self.lbl_chk_slobs.setText("• 📡 Streamlabs Desktop: <b style='color: #22c55e;'>Connected (Live Pipe)</b>")
                sc_name = getattr(self.slobs_client, "_active_scene_name", "") or "Active"
                self.lbl_chk_scene.setText(f"• 🎬 Active Broadcast Scene: <b style='color: #38bdf8;'>{sc_name}</b>")
            else:
                self.lbl_chk_slobs.setText("• 📡 Streamlabs Desktop: <b style='color: #ef4444;'>Disconnected / Not Running</b>")
                self.lbl_chk_scene.setText("• 🎬 Active Broadcast Scene: <span style='color: #71717a;'>Waiting for SLOBS...</span>")

            # 2. Twitch Status
            token = getattr(self.overlay, "twitch_token", "")
            channel = getattr(self.overlay, "twitch_channel", "")
            if token and channel:
                self.lbl_chk_twitch.setText(f"• 🟣 Twitch Integration: <b style='color: #a855f7;'>Linked (@{channel})</b>")
            else:
                self.lbl_chk_twitch.setText("• 🟣 Twitch Integration: <span style='color: #eab308;'>Not Linked (Offline Mode)</span>")

            # 3. Audio Capture Status
            eng = getattr(self.overlay, "auto_clip_engine", None)
            if eng and getattr(eng, "enabled", False) and getattr(eng, "streamer_mode", False):
                dev_name = eng.current_device.description() if eng.current_device else "Active Input"
                self.lbl_chk_audio.setText(f"• 🎙️ Auto-Clip Audio: <b style='color: #22c55e;'>Armed ({dev_name[:28]})</b>")
            else:
                self.lbl_chk_audio.setText("• 🎙️ Auto-Clip Audio: <span style='color: #a1a1aa;'>Standby / Opt-In</span>")

            # 4. Overlay Status
            border_armed = getattr(self.overlay, "primary_hotkey_enabled", False)
            border_col = getattr(self.overlay, "border_color", None)
            col_hex = border_col.name() if border_col else "#ff0000"
            if border_armed:
                self.lbl_chk_overlay.setText(f"• 🖼️ Monitor Highlight: <b style='color: {col_hex};'>Armed (Active)</b>")
            else:
                self.lbl_chk_overlay.setText("• 🖼️ Monitor Highlight: <span style='color: #a1a1aa;'>Ready (Hotkeys Disabled)</span>")

        except Exception as e:
            log_debug("LAUNCHPAD", f"Telemetry refresh notice: {e}")

    def _populate_checklist(self):
        # Clear existing
        while self.chk_container.count() > 0:
            item = self.chk_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._custom_checkboxes = []

        saved_items = getattr(self.overlay, "launch_checklist", None)
        if not saved_items:
            cfg = getattr(self.overlay, "config", {})
            saved_items = cfg.get("launch_checklist", []) if isinstance(cfg, dict) else []
        if not saved_items:
            saved_items = [{"text": t, "checked": False} for t in DEFAULT_CHECKLIST]

        for item_data in saved_items:
            text = item_data.get("text", "") if isinstance(item_data, dict) else str(item_data)
            checked = item_data.get("checked", False) if isinstance(item_data, dict) else False
            self._add_checkbox_widget(text, checked)

    def _add_checkbox_widget(self, text: str, checked: bool = False):
        row = QHBoxLayout()
        chk = QCheckBox(text)
        chk.setChecked(checked)
        chk.setStyleSheet("font-size: 11px; color: #efeff1;")
        chk.toggled.connect(self._save_checklist_state)
        row.addWidget(chk)
        row.addStretch()

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(16, 16)
        btn_del.setToolTip("Delete this checklist item")
        btn_del.setStyleSheet("background: transparent; color: #71717a; border: none; font-size: 10px;")
        btn_del.clicked.connect(lambda: self._delete_checkbox_item(row, chk))
        row.addWidget(btn_del)

        self.chk_container.addLayout(row)
        self._custom_checkboxes.append((chk, row))

    def _add_custom_item(self):
        text = self.txt_new_item.text().strip()
        if not text:
            return
        self._add_checkbox_widget(text, False)
        self.txt_new_item.clear()
        self._save_checklist_state()

    def _delete_checkbox_item(self, row_layout, chk_widget):
        for idx, (c, r) in enumerate(self._custom_checkboxes):
            if c == chk_widget:
                self._custom_checkboxes.pop(idx)
                break
        while row_layout.count() > 0:
            it = row_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._save_checklist_state()

    def _reset_all_checks(self):
        for chk, _ in self._custom_checkboxes:
            chk.setChecked(False)
        self._save_checklist_state()

    def _save_checklist_state(self):
        items = []
        for chk, _ in self._custom_checkboxes:
            items.append({"text": chk.text(), "checked": chk.isChecked()})
        if self.overlay:
            self.overlay.launch_checklist = items
            if hasattr(self.overlay, "save_settings"):
                self.overlay.save_settings()


    def _on_master_launch_clicked(self):
        if not self._is_live:
            # Trigger Launch!
            log_debug("LAUNCHPAD", "Master 'GO FOR LAUNCH' triggered by user.")
            
            # 1. Start Stream in SLOBS if connected
            if self.slobs_client.is_connected():
                try:
                    self.slobs_client._call_rpc("toggleStreaming", "StreamingService")
                    log_debug("LAUNCHPAD", "Dispatched toggleStreaming to Streamlabs StreamingService.")
                except Exception as e:
                    log_debug("LAUNCHPAD", f"Error toggling streaming: {e}")
            else:
                log_debug("LAUNCHPAD", "Streamlabs not connected; continuing local timers.")

            # 2. Start Chronos Timers
            if hasattr(self.overlay, "chronos_engine") and self.overlay.chronos_engine:
                try:
                    self.overlay.chronos_engine.start()
                    log_debug("LAUNCHPAD", "Started Chronos stream timers.")
                except Exception as e:
                    log_debug("LAUNCHPAD", f"Chronos start error: {e}")

            # 3. Start Rotating Trivia Cycler
            if hasattr(self.overlay, "cycler_engine") and self.overlay.cycler_engine:
                try:
                    self.overlay.cycler_engine.start()
                    log_debug("LAUNCHPAD", "Started Trivia / Rotating Text cycler.")
                except Exception as e:
                    log_debug("LAUNCHPAD", f"Cycler start error: {e}")

            # 4. Flash temporary green confirmation border
            if hasattr(self.overlay, "flash_temporary_alert"):
                self.overlay.flash_temporary_alert(duration_ms=2000, color=QColor("#22c55e"))

            # 5. Play chime
            if hasattr(self.overlay, "soundboard_engine") and self.overlay.soundboard_engine:
                try:
                    self.overlay.soundboard_engine.play_marker_chime()
                except Exception:
                    pass

            self._is_live = True
            self.lbl_stream_status.setText("<span style='color: #22c55e;'>● BROADCAST ACTIVE</span>")
            self.btn_master_launch.setText("🔴  STREAM LIVE (STOP BROADCAST)")
            self.btn_master_launch.setStyleSheet("""
                QPushButton {
                    background-color: #ef4444;
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 12px 20px;
                    border-radius: 6px;
                    border: 1px solid #f87171;
                    letter-spacing: 1px;
                }
                QPushButton:hover {
                    background-color: #dc2626;
                }
            """)
            if hasattr(self.overlay, "show_hud_toast"):
                self.overlay.show_hud_toast("🚀 STREAM LAUNCH INITIATED! Good luck with your broadcast!", True)
        else:
            # Stop broadcast
            confirm = QMessageBox.question(
                self,
                "End Stream Broadcast?",
                "Are you sure you want to stop the live stream and stop timers?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                log_debug("LAUNCHPAD", "User ended broadcast from launchpad.")
                if self.slobs_client.is_connected():
                    try:
                        self.slobs_client._call_rpc("stopStreaming", "StreamingService")
                    except Exception:
                        pass
                if hasattr(self.overlay, "chronos_engine") and self.overlay.chronos_engine:
                    self.overlay.chronos_engine.stop()
                if hasattr(self.overlay, "cycler_engine") and self.overlay.cycler_engine:
                    self.overlay.cycler_engine.stop()

                self._is_live = False
                self.lbl_stream_status.setText("<span style='color: #a1a1aa;'>● STANDBY</span>")
                self.btn_master_launch.setText("🚀  GO FOR LAUNCH")
                self.btn_master_launch.setStyleSheet("""
                    QPushButton {
                        background-color: #9146ff;
                        color: #ffffff;
                        font-size: 14px;
                        font-weight: bold;
                        padding: 12px 20px;
                        border-radius: 6px;
                        border: 1px solid #a970ff;
                        letter-spacing: 1px;
                    }
                    QPushButton:hover {
                        background-color: #a970ff;
                    }
                """)

    def refresh_theme_labels(self, effective):
        pass

