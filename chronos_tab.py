import os
import sys
import datetime
import subprocess

from PyQt6.QtCore import Qt, QDateTime, QTime, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QLineEdit, QCheckBox, QGroupBox,
    QStackedWidget, QDateTimeEdit, QMessageBox, QApplication, QFrame
)
from PyQt6.QtGui import QGuiApplication, QFont

from chronos_engine import ChronosEngine, ChronosMode, ChronosState, DEFAULT_OBS_FILE
import theme_manager

class ChronosTab(QWidget):
    """Interactive Stream Timing Suite with real-time OBS file sync."""
    def __init__(self, main_win, engine: ChronosEngine):
        super().__init__()
        self.main_win = main_win
        self.engine = engine

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(14, 10, 14, 10)

        # ---------------- 1. BIG DIGITAL READOUT BANNER ----------------
        self.card_display = QFrame()
        self.card_display.setObjectName("chronosDisplayCard")
        self.card_display.setStyleSheet("""
            QFrame#chronosDisplayCard {
                background-color: #18181b;
                border: 1px solid #2d2d30;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        display_lay = QVBoxLayout(self.card_display)
        display_lay.setSpacing(6)
        display_lay.setContentsMargins(14, 10, 14, 10)

        # Top row: mode indicator & status badge
        top_status_row = QHBoxLayout()
        self.lbl_mode_badge = QLabel("COUNTDOWN TIMER")
        self.lbl_mode_badge.setStyleSheet("font-size: 11px; font-weight: bold; color: #a1a1aa;")
        top_status_row.addWidget(self.lbl_mode_badge, 1)

        self.lbl_status_pill = QLabel("■ STOPPED")
        self.lbl_status_pill.setStyleSheet("""
            background-color: #3f3f46;
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            padding: 2px 10px;
            border-radius: 10px;
        """)
        top_status_row.addWidget(self.lbl_status_pill)
        display_lay.addLayout(top_status_row)

        # Large Digital Time Display
        self.lbl_time_display = QLabel("10:00")
        self.lbl_time_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_time_display.setStyleSheet("""
            font-family: 'Consolas', 'Segoe UI', monospace;
            font-size: 40px;
            font-weight: bold;
            color: #9146ff;
            margin: 4px 0px;
        """)
        display_lay.addWidget(self.lbl_time_display)

        # Action Buttons Row
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(8)

        self.btn_toggle = QPushButton("▶ Start")
        self.btn_toggle.setObjectName("btn_chronos_start")
        self.btn_toggle.setStyleSheet("""
            QPushButton#btn_chronos_start {
                background-color: #9146ff;
                color: #ffffff;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #772ce8;
                border-radius: 5px;
                padding: 5px 16px;
                min-height: 24px;
            }
            QPushButton#btn_chronos_start:hover {
                background-color: #772ce8;
            }
        """)
        self.btn_toggle.clicked.connect(self._toggle_start_pause)
        ctrl_layout.addWidget(self.btn_toggle)

        self.btn_reset = QPushButton("↺ Reset")
        self.btn_reset.setFixedWidth(75)
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        ctrl_layout.addWidget(self.btn_reset)

        ctrl_layout.addSpacing(10)

        # Quick Adjustments
        self.btn_add1 = QPushButton("+1 Min")
        self.btn_add1.clicked.connect(lambda: self.engine.add_seconds(60))
        ctrl_layout.addWidget(self.btn_add1)

        self.btn_add5 = QPushButton("+5 Min")
        self.btn_add5.clicked.connect(lambda: self.engine.add_seconds(300))
        ctrl_layout.addWidget(self.btn_add5)

        self.btn_sub1 = QPushButton("-1 Min")
        self.btn_sub1.clicked.connect(lambda: self.engine.add_seconds(-60))
        ctrl_layout.addWidget(self.btn_sub1)

        ctrl_layout.addStretch()
        display_lay.addLayout(ctrl_layout)

        main_layout.addWidget(self.card_display)

        # ---------------- 2. TIMER MODE & CONFIGURATION ----------------
        grp_config = QGroupBox("Timer Configuration")
        grp_config_lay = QVBoxLayout(grp_config)
        grp_config_lay.setSpacing(8)

        # Mode row
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Timer Mode:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("⏳ Countdown Timer", ChronosMode.COUNT_DOWN)
        self.combo_mode.addItem("⏱️ Stopwatch (Count Up)", ChronosMode.COUNT_UP)
        self.combo_mode.addItem("🎯 Countdown to Target Date & Time", ChronosMode.COUNTDOWN_TO_DATE)
        self.combo_mode.addItem("📅 Count Up Since Target Date & Time", ChronosMode.COUNTUP_FROM_DATE)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_combo_changed)
        mode_row.addWidget(self.combo_mode)
        mode_row.addStretch()
        grp_config_lay.addLayout(mode_row)

        # Stacked configuration options per mode
        self.stack_mode_config = QStackedWidget()

        # Page 0: Countdown
        page_countdown = QWidget()
        lay_cd = QVBoxLayout(page_countdown)
        lay_cd.setContentsMargins(0, 4, 0, 0)
        lay_cd.setSpacing(6)

        row_dur = QHBoxLayout()
        row_dur.addWidget(QLabel("Duration:"))
        self.spin_cd_hours = QSpinBox()
        self.spin_cd_hours.setRange(0, 99)
        self.spin_cd_hours.setSuffix(" h")
        self.spin_cd_hours.valueChanged.connect(self._on_countdown_spinners_changed)
        row_dur.addWidget(self.spin_cd_hours)

        self.spin_cd_mins = QSpinBox()
        self.spin_cd_mins.setRange(0, 59)
        self.spin_cd_mins.setValue(10)
        self.spin_cd_mins.setSuffix(" m")
        self.spin_cd_mins.valueChanged.connect(self._on_countdown_spinners_changed)
        row_dur.addWidget(self.spin_cd_mins)

        self.spin_cd_secs = QSpinBox()
        self.spin_cd_secs.setRange(0, 59)
        self.spin_cd_secs.setSuffix(" s")
        self.spin_cd_secs.valueChanged.connect(self._on_countdown_spinners_changed)
        row_dur.addWidget(self.spin_cd_secs)
        row_dur.addStretch()
        lay_cd.addLayout(row_dur)

        row_cd_msg = QHBoxLayout()
        row_cd_msg.addWidget(QLabel("Completion Message:"))
        self.txt_cd_msg = QLineEdit()
        self.txt_cd_msg.setPlaceholderText("e.g., STREAM STARTING SOON!")
        self.txt_cd_msg.setText(self.engine.countdown_completion_msg)
        self.txt_cd_msg.textChanged.connect(self._on_cd_msg_changed)
        row_cd_msg.addWidget(self.txt_cd_msg)
        lay_cd.addLayout(row_cd_msg)
        self.stack_mode_config.addWidget(page_countdown)

        # Page 1: Stopwatch / Count Up
        page_countup = QWidget()
        lay_cu = QVBoxLayout(page_countup)
        lay_cu.setContentsMargins(0, 4, 0, 0)
        lay_cu.setSpacing(6)

        row_cap = QHBoxLayout()
        row_cap.addWidget(QLabel("Target Cap (optional):"))
        self.spin_cu_hours = QSpinBox()
        self.spin_cu_hours.setRange(0, 99)
        self.spin_cu_hours.setSuffix(" h")
        self.spin_cu_hours.valueChanged.connect(self._on_countup_cap_changed)
        row_cap.addWidget(self.spin_cu_hours)

        self.spin_cu_mins = QSpinBox()
        self.spin_cu_mins.setRange(0, 59)
        self.spin_cu_mins.setSuffix(" m")
        self.spin_cu_mins.valueChanged.connect(self._on_countup_cap_changed)
        row_cap.addWidget(self.spin_cu_mins)

        self.spin_cu_secs = QSpinBox()
        self.spin_cu_secs.setRange(0, 59)
        self.spin_cu_secs.setSuffix(" s")
        self.spin_cu_secs.valueChanged.connect(self._on_countup_cap_changed)
        row_cap.addWidget(self.spin_cu_secs)
        row_cap.addStretch()
        lay_cu.addLayout(row_cap)

        self.chk_cu_stop_at_cap = QCheckBox("Stop timer when target cap is reached")
        self.chk_cu_stop_at_cap.setChecked(self.engine.count_up_stop_at_cap)
        self.chk_cu_stop_at_cap.toggled.connect(self._on_cu_stop_at_cap_toggled)
        lay_cu.addWidget(self.chk_cu_stop_at_cap)
        self.stack_mode_config.addWidget(page_countup)

        # Page 2: Countdown to Date & Time
        page_date_cd = QWidget()
        lay_dcd = QVBoxLayout(page_date_cd)
        lay_dcd.setContentsMargins(0, 4, 0, 0)
        lay_dcd.setSpacing(6)

        row_dt = QHBoxLayout()
        row_dt.addWidget(QLabel("Target Date & Time:"))
        self.dt_target = QDateTimeEdit()
        self.dt_target.setCalendarPopup(True)
        self.dt_target.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.dt_target.setDateTime(QDateTime.fromSecsSinceEpoch(int(self.engine.target_date.timestamp())))
        self.dt_target.dateTimeChanged.connect(self._on_target_datetime_changed)
        row_dt.addWidget(self.dt_target)
        row_dt.addStretch()
        lay_dcd.addLayout(row_dt)

        row_dcd_msg = QHBoxLayout()
        row_dcd_msg.addWidget(QLabel("Completion Message:"))
        self.txt_dcd_msg = QLineEdit()
        self.txt_dcd_msg.setPlaceholderText("e.g., EVENT STARTED!")
        self.txt_dcd_msg.setText(self.engine.date_completion_msg)
        self.txt_dcd_msg.textChanged.connect(self._on_dcd_msg_changed)
        row_dcd_msg.addWidget(self.txt_dcd_msg)
        lay_dcd.addLayout(row_dcd_msg)
        self.stack_mode_config.addWidget(page_date_cd)

        # Page 3: Count Up Since Date & Time
        page_since = QWidget()
        lay_since = QVBoxLayout(page_since)
        lay_since.setContentsMargins(0, 4, 0, 0)
        lay_since.setSpacing(6)

        row_since = QHBoxLayout()
        row_since.addWidget(QLabel("Milestone Date & Time:"))
        self.dt_since = QDateTimeEdit()
        self.dt_since.setCalendarPopup(True)
        self.dt_since.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.dt_since.setDateTime(QDateTime.fromSecsSinceEpoch(int(self.engine.since_date.timestamp())))
        self.dt_since.dateTimeChanged.connect(self._on_since_datetime_changed)
        row_since.addWidget(self.dt_since)
        row_since.addStretch()
        lay_since.addLayout(row_since)
        self.stack_mode_config.addWidget(page_since)

        grp_config_lay.addWidget(self.stack_mode_config)
        main_layout.addWidget(grp_config)

        # ---------------- 3. OBS FILE SYNC & OUTPUT TEMPLATE ----------------
        grp_obs = QGroupBox("OBS / Streamlabs Text Sync")
        grp_obs_lay = QVBoxLayout(grp_obs)
        grp_obs_lay.setSpacing(8)

        # Path banner row
        path_box = QHBoxLayout()
        path_box.addWidget(QLabel("Output File:"))
        self.txt_obs_path = QLineEdit(DEFAULT_OBS_FILE)
        self.txt_obs_path.setReadOnly(True)
        self.txt_obs_path.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        path_box.addWidget(self.txt_obs_path)
        grp_obs_lay.addLayout(path_box)

        # Prefix / Suffix template
        template_row = QHBoxLayout()
        template_row.setSpacing(8)
        template_row.addWidget(QLabel("Prefix:"))
        self.txt_prefix = QLineEdit()
        self.txt_prefix.setPlaceholderText("e.g., Starting Soon: ")
        self.txt_prefix.setText(self.engine.prefix)
        self.txt_prefix.textChanged.connect(self._on_prefix_changed)
        template_row.addWidget(self.txt_prefix)

        template_row.addWidget(QLabel("Suffix:"))
        self.txt_suffix = QLineEdit()
        self.txt_suffix.setPlaceholderText("e.g.,  | !discord")
        self.txt_suffix.setText(self.engine.suffix)
        self.txt_suffix.textChanged.connect(self._on_suffix_changed)
        template_row.addWidget(self.txt_suffix)
        grp_obs_lay.addLayout(template_row)

        # File actions row
        file_btns = QHBoxLayout()
        file_btns.setSpacing(8)

        self.btn_copy_path = QPushButton("📋 Copy File Path")
        self.btn_copy_path.clicked.connect(self._copy_file_path)
        file_btns.addWidget(self.btn_copy_path)

        self.btn_open_folder = QPushButton("📂 Open Folder")
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        file_btns.addWidget(self.btn_open_folder)

        self.btn_open_file = QPushButton("📄 Open obs_timer.txt")
        self.btn_open_file.clicked.connect(self._open_output_file)
        file_btns.addWidget(self.btn_open_file)
        file_btns.addStretch()
        grp_obs_lay.addLayout(file_btns)

        # Checkboxes
        self.chk_write_file = QCheckBox("Write live timer updates to obs_timer.txt")
        self.chk_write_file.setChecked(self.engine.write_to_file)
        self.chk_write_file.toggled.connect(self._on_write_file_toggled)
        grp_obs_lay.addWidget(self.chk_write_file)

        self.chk_clear_on_reset = QCheckBox("Clear text file when timer is reset (leave blank instead of showing duration)")
        self.chk_clear_on_reset.setChecked(self.engine.clear_file_on_reset)
        self.chk_clear_on_reset.toggled.connect(self._on_clear_on_reset_toggled)
        grp_obs_lay.addWidget(self.chk_clear_on_reset)

        main_layout.addWidget(grp_obs)
        main_layout.addStretch()

        # Connect engine signals
        self.engine.tick.connect(self._on_engine_tick)
        self.engine.state_changed.connect(self._on_engine_state_changed)
        self.engine.completed.connect(self._on_engine_completed)

        # Initial UI synchronization
        self._sync_ui_from_engine()

    def _sync_ui_from_engine(self):
        # Set mode combobox
        idx = self.combo_mode.findData(self.engine.mode)
        if idx >= 0:
            self.combo_mode.setCurrentIndex(idx)
        self.stack_mode_config.setCurrentIndex(idx if idx >= 0 else 0)

        # Set spinboxes
        tot = self.engine.countdown_initial
        self.spin_cd_hours.setValue(tot // 3600)
        self.spin_cd_mins.setValue((tot % 3600) // 60)
        self.spin_cd_secs.setValue(tot % 60)

        cap = self.engine.count_up_target_cap
        self.spin_cu_hours.setValue(cap // 3600)
        self.spin_cu_mins.setValue((cap % 3600) // 60)
        self.spin_cu_secs.setValue(cap % 60)

        # Trigger tick update
        disp, sec = self.engine._get_current_display()
        self._on_engine_tick(disp, self.engine.state, sec)

    def _toggle_start_pause(self):
        self.engine.toggle_start_pause()
        self._persist_settings()

    def _on_reset_clicked(self):
        self.engine.reset()
        self._persist_settings()

    def _on_mode_combo_changed(self, idx):
        mode = self.combo_mode.currentData()
        self.stack_mode_config.setCurrentIndex(idx)
        self.engine.set_mode(mode)
        
        titles = {
            ChronosMode.COUNT_DOWN: "COUNTDOWN TIMER",
            ChronosMode.COUNT_UP: "STOPWATCH (COUNT UP)",
            ChronosMode.COUNTDOWN_TO_DATE: "COUNTDOWN TO DATE",
            ChronosMode.COUNTUP_FROM_DATE: "COUNT UP SINCE DATE"
        }
        self.lbl_mode_badge.setText(titles.get(mode, "STREAM TIMER"))
        self._persist_settings()

    def _on_countdown_spinners_changed(self):
        tot = (self.spin_cd_hours.value() * 3600) + (self.spin_cd_mins.value() * 60) + self.spin_cd_secs.value()
        self.engine.countdown_initial = max(1, tot)
        if self.engine.state in (ChronosState.STOPPED, ChronosState.COMPLETED):
            self.engine.countdown_remaining = self.engine.countdown_initial
            self.engine._publish_current_state()
        self._persist_settings()

    def _on_countup_cap_changed(self):
        cap = (self.spin_cu_hours.value() * 3600) + (self.spin_cu_mins.value() * 60) + self.spin_cu_secs.value()
        self.engine.count_up_target_cap = cap
        self._persist_settings()

    def _on_cu_stop_at_cap_toggled(self, checked):
        self.engine.count_up_stop_at_cap = checked
        self._persist_settings()

    def _on_cd_msg_changed(self, text):
        self.engine.countdown_completion_msg = text
        self._persist_settings()

    def _on_target_datetime_changed(self, dt):
        self.engine.target_date = datetime.datetime.fromtimestamp(dt.toSecsSinceEpoch())
        if self.engine.state in (ChronosState.STOPPED, ChronosState.COMPLETED):
            self.engine._publish_current_state()
        self._persist_settings()

    def _on_dcd_msg_changed(self, text):
        self.engine.date_completion_msg = text
        self._persist_settings()

    def _on_since_datetime_changed(self, dt):
        self.engine.since_date = datetime.datetime.fromtimestamp(dt.toSecsSinceEpoch())
        if self.engine.state in (ChronosState.STOPPED, ChronosState.COMPLETED):
            self.engine._publish_current_state()
        self._persist_settings()

    def _on_prefix_changed(self, text):
        self.engine.prefix = text
        self.engine._publish_current_state()
        self._persist_settings()

    def _on_suffix_changed(self, text):
        self.engine.suffix = text
        self.engine._publish_current_state()
        self._persist_settings()

    def _on_write_file_toggled(self, checked):
        self.engine.write_to_file = checked
        self._persist_settings()

    def _on_clear_on_reset_toggled(self, checked):
        self.engine.clear_file_on_reset = checked
        self._persist_settings()

    def _copy_file_path(self):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(DEFAULT_OBS_FILE)
        QMessageBox.information(
            self,
            "Path Copied",
            f"OBS Timer file path copied to clipboard:\n\n{DEFAULT_OBS_FILE}\n\n"
            "In OBS or Streamlabs, add a Text (GDI+) source, check 'Read from file', and paste this path!"
        )

    def _open_output_folder(self):
        folder = os.path.dirname(DEFAULT_OBS_FILE)
        try:
            subprocess.Popen(f'explorer "{os.path.normpath(folder)}"')
        except Exception:
            try:
                os.startfile(folder)
            except Exception:
                pass

    def _open_output_file(self):
        if not os.path.exists(DEFAULT_OBS_FILE):
            self.engine._publish_current_state()
        try:
            os.startfile(DEFAULT_OBS_FILE)
        except Exception:
            pass

    def _persist_settings(self):
        if hasattr(self.main_win, "overlay") and hasattr(self.main_win.overlay, "save_settings"):
            self.main_win.overlay.save_settings()

    def _on_engine_tick(self, display_text: str, state: str, sec: int):
        self.lbl_time_display.setText(display_text)
        self._update_state_ui(state)

    def _on_engine_state_changed(self, new_state: str):
        self._update_state_ui(new_state)

    def _on_engine_completed(self, message: str):
        self.lbl_time_display.setText(message)
        self._update_state_ui(ChronosState.COMPLETED)

    def _update_state_ui(self, state: str):
        if state == ChronosState.RUNNING:
            self.btn_toggle.setText("⏸ Pause")
            self.btn_toggle.setStyleSheet("""
                QPushButton#btn_chronos_start {
                    background-color: #d97706;
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 13px;
                    border: 1px solid #b45309;
                    border-radius: 5px;
                    padding: 5px 16px;
                    min-height: 24px;
                }
                QPushButton#btn_chronos_start:hover {
                    background-color: #b45309;
                }
            """)
            self.lbl_status_pill.setText("● RUNNING")
            self.lbl_status_pill.setStyleSheet("""
                background-color: #15803d;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 10px;
                border-radius: 10px;
            """)
        elif state == ChronosState.PAUSED:
            self.btn_toggle.setText("▶ Resume")
            self.btn_toggle.setStyleSheet("""
                QPushButton#btn_chronos_start {
                    background-color: #9146ff;
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 13px;
                    border: 1px solid #772ce8;
                    border-radius: 5px;
                    padding: 5px 16px;
                    min-height: 24px;
                }
                QPushButton#btn_chronos_start:hover {
                    background-color: #772ce8;
                }
            """)
            self.lbl_status_pill.setText("❚❚ PAUSED")
            self.lbl_status_pill.setStyleSheet("""
                background-color: #b45309;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 10px;
                border-radius: 10px;
            """)
        elif state == ChronosState.COMPLETED:
            self.btn_toggle.setText("↺ Restart")
            self.btn_toggle.setStyleSheet("""
                QPushButton#btn_chronos_start {
                    background-color: #9146ff;
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 13px;
                    border: 1px solid #772ce8;
                    border-radius: 5px;
                    padding: 5px 16px;
                    min-height: 24px;
                }
            """)
            self.lbl_status_pill.setText("✓ COMPLETED")
            self.lbl_status_pill.setStyleSheet("""
                background-color: #7c3aed;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 10px;
                border-radius: 10px;
            """)
        else:  # STOPPED
            self.btn_toggle.setText("▶ Start")
            self.btn_toggle.setStyleSheet("""
                QPushButton#btn_chronos_start {
                    background-color: #9146ff;
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 13px;
                    border: 1px solid #772ce8;
                    border-radius: 5px;
                    padding: 5px 16px;
                    min-height: 24px;
                }
                QPushButton#btn_chronos_start:hover {
                    background-color: #772ce8;
                }
            """)
            self.lbl_status_pill.setText("■ STOPPED")
            self.lbl_status_pill.setStyleSheet("""
                background-color: #3f3f46;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 10px;
                border-radius: 10px;
            """)

    def refresh_theme_labels(self, effective: str):
        is_dark = (effective == "dark")
        card_bg = "#18181b" if is_dark else "#ffffff"
        card_border = "#2d2d30" if is_dark else "#d4d4d8"
        self.card_display.setStyleSheet(f"""
            QFrame#chronosDisplayCard {{
                background-color: {card_bg};
                border: 1px solid {card_border};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        mode_color = "#a1a1aa" if is_dark else "#71717a"
        self.lbl_mode_badge.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {mode_color};")
