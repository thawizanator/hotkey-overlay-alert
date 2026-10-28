import os
import sys
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QCheckBox, QSlider, QPushButton, QGroupBox, QFrame, 
    QColorDialog, QScrollArea, QMessageBox, QGridLayout, QSizePolicy
)
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont

try:
    from theme_manager import theme_manager
except ImportError:
    class DummyTheme:
        def get_surface_color(self, t): return "#18181b" if t == "dark" else "#ffffff"
        def get_border_color(self, t): return "#27272a" if t == "dark" else "#e4e4e7"
        def get_text_color(self, t): return "#ffffff" if t == "dark" else "#18181b"
        def get_secondary_text_color(self, t): return "#a1a1aa" if t == "dark" else "#71717a"
        def get_accent_color(self, t): return "#0284c7"
    theme_manager = DummyTheme()

from auto_clip_engine import AutoClipEngine


class DiscordVUMeterWidget(QWidget):
    """
    Discord-style interactive 4-zone Audio VU Meter.
    Renders 4 distinct color zones:
      - Green:  Normal speech / Ambient
      - Yellow: Elevated talking
      - Orange: Possible hype moment
      - Red:    Full peak trigger event
    Includes live bouncing bar, moving average baseline marker, and trigger threshold marker.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setMinimumWidth(260)

        self.current_level = 0.0      # 0.0 to 1.0
        self.display_level = 0.0      # Smooth decay
        self.current_zone = AutoClipEngine.ZONE_GREEN
        self.baseline = 0.05
        self.threshold = 0.70

        # Animation timer for smooth meter fallback
        self._decay_timer = QTimer(self)
        self._decay_timer.setInterval(25)
        self._decay_timer.timeout.connect(self._on_decay_tick)
        self._decay_timer.start()

    def update_meter(self, level: float, zone: int, baseline: float, threshold: float):
        self.current_level = max(0.0, min(1.0, level))
        self.current_zone = zone
        self.baseline = baseline
        self.threshold = threshold
        if self.current_level > self.display_level:
            self.display_level = self.current_level
        self.update()

    def _on_decay_tick(self):
        if self.display_level > self.current_level:
            self.display_level = max(self.current_level, self.display_level - 0.04)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bar_h = 16
        bar_y = (h - bar_h) // 2

        # 1. Background Groove
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#18181b"))
        painter.drawRoundedRect(0, bar_y, w, bar_h, 4, 4)

        # 2. Segmented LED Bars
        num_segments = 40
        seg_gap = 2
        total_gaps = (num_segments - 1) * seg_gap
        seg_w = (w - total_gaps) / num_segments

        lit_segments = int(self.display_level * num_segments)
        thresh_seg = int(self.threshold * num_segments)
        orange_seg = int(self.threshold * 0.78 * num_segments)
        yellow_seg = int(self.threshold * 0.42 * num_segments)

        for i in range(num_segments):
            seg_x = i * (seg_w + seg_gap)
            is_lit = i < lit_segments

            # Determine segment color zone
            if i >= thresh_seg:
                color = QColor("#ef4444") if is_lit else QColor("#450a0a")  # Red
            elif i >= orange_seg:
                color = QColor("#f97316") if is_lit else QColor("#431407")  # Orange
            elif i >= yellow_seg:
                color = QColor("#eab308") if is_lit else QColor("#422006")  # Yellow
            else:
                color = QColor("#22c55e") if is_lit else QColor("#052e16")  # Green

            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(seg_x, bar_y + 2, seg_w, bar_h - 4), 2, 2)

        # 3. Baseline Indicator (Subtle cyan line)
        base_x = self.baseline * w
        painter.setPen(QPen(QColor("#38bdf8"), 2, Qt.PenStyle.DashLine))
        painter.drawLine(int(base_x), bar_y - 2, int(base_x), bar_y + bar_h + 2)

        # 4. Trigger Threshold Indicator (Bright white/yellow bar)
        thresh_x = self.threshold * w
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(int(thresh_x), bar_y - 4, int(thresh_x), bar_y + bar_h + 4)


class AutoClipTab(QWidget):
    """
    Settings Tab for Auto-Clip & Stream Markers.
    Allows streamers to configure audio input, Discord-style sensitivity,
    alert colors, scene filters, and review captured clips.
    """
    settings_changed = pyqtSignal()

    def __init__(self, main_win=None, engine: AutoClipEngine = None, parent=None):
        super().__init__(parent)
        self.main_win = main_win
        self.engine = engine or AutoClipEngine(self)

        self._build_ui()
        self._load_from_engine()

        # Connect engine signals
        self.engine.level_updated.connect(self._on_level_updated)
        self.engine.cooldown_tick.connect(self._on_cooldown_tick)
        self.engine.status_changed.connect(self._on_status_changed)
        self.engine.marker_triggered.connect(self._on_marker_triggered)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)

        # ------------------ HEADER ------------------
        hdr = QVBoxLayout()
        hdr.setSpacing(6)

        row_title = QHBoxLayout()
        lbl_title = QLabel("🎙️ AUTO-CLIP & STREAM MARKERS")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8; letter-spacing: 0.5px;")
        row_title.addWidget(lbl_title)
        row_title.addStretch()

        self.btn_audio_diag = QPushButton("🩺 Audio Diagnostics...")
        self.btn_audio_diag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_audio_diag.setStyleSheet("""
            QPushButton {
                background-color: #1e1e24;
                color: #38bdf8;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        self.btn_audio_diag.clicked.connect(self._open_audio_diagnostics)
        row_title.addWidget(self.btn_audio_diag)
        hdr.addLayout(row_title)

        # Master Enable Toggle Switch
        row_master = QHBoxLayout()
        self.switch_master_enable = QCheckBox("Enable Auto-Clip Monitoring (Hype & Scream Detection)")
        self.switch_master_enable.setStyleSheet("""
            QCheckBox {
                font-size: 12px;
                font-weight: bold;
                color: #22c55e;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        self.switch_master_enable.setChecked(True)
        self.switch_master_enable.toggled.connect(self._on_master_enable_toggled)
        row_master.addWidget(self.switch_master_enable)
        row_master.addStretch()
        hdr.addLayout(row_master)

        lbl_sub = QLabel("Continuously monitors audio levels to detect hype reactions, laughter, and screams. "
                         "Automatically drops live Twitch stream markers and logs 60s clip windows (40s pre-context / 20s aftermath).")
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("font-size: 11px; color: #a1a1aa; line-height: 1.3;")
        hdr.addWidget(lbl_sub)
        lay.addLayout(hdr)

        # Streamer Mode Disabled Alert Banner
        self.banner_streamer_mode = QFrame()
        self.banner_streamer_mode.setStyleSheet("""
            QFrame {
                background-color: #271717;
                border: 1px solid #ef4444;
                border-radius: 6px;
                padding: 6px 10px;
            }
        """)
        lay_banner = QHBoxLayout(self.banner_streamer_mode)
        lay_banner.setContentsMargins(4, 4, 4, 4)
        lbl_banner = QLabel("⚠️ <b>Streamer Mode is currently disabled.</b> Enable Streamer Mode in General Settings to activate live audio monitoring and Twitch stream clipping.")
        lbl_banner.setWordWrap(True)
        lbl_banner.setStyleSheet("color: #fca5a5; font-size: 11px;")
        lay_banner.addWidget(lbl_banner)
        lay.addWidget(self.banner_streamer_mode)
        self.banner_streamer_mode.setVisible(False)

        # ------------------ CARD 1: AUDIO INPUT & VU METER ------------------
        self.grp_meter = QGroupBox("Audio Input && Real-Time Meter")
        lay_meter = QVBoxLayout(self.grp_meter)
        lay_meter.setSpacing(8)

        # Device row
        row_dev = QHBoxLayout()
        row_dev.addWidget(QLabel("Input Device:"))
        self.combo_device = QComboBox()
        self.combo_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_device.setMinimumContentsLength(8)
        self.combo_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_device.currentIndexChanged.connect(self._on_device_changed)
        row_dev.addWidget(self.combo_device, 1)

        self.btn_refresh_dev = QPushButton("🔄 Refresh")
        self.btn_refresh_dev.setFixedWidth(82)
        self.btn_refresh_dev.clicked.connect(self._populate_devices)
        row_dev.addWidget(self.btn_refresh_dev)
        lay_meter.addLayout(row_dev)

        # Input Gain Trim Slider Row
        self.row_gain = QHBoxLayout()
        self.lbl_gain_title = QLabel("Input Gain Trim:")
        self.lbl_gain_title.setFixedWidth(105)
        self.row_gain.addWidget(self.lbl_gain_title)

        self.slider_gain = QSlider(Qt.Orientation.Horizontal)
        self.slider_gain.setRange(25, 200)
        self.slider_gain.setValue(100)
        self.slider_gain.valueChanged.connect(self._on_gain_changed)
        self.row_gain.addWidget(self.slider_gain, 1)

        self.lbl_gain_val = QLabel("100%")
        self.lbl_gain_val.setFixedWidth(40)
        self.lbl_gain_val.setStyleSheet("font-weight: bold; font-family: monospace; color: #38bdf8;")
        self.row_gain.addWidget(self.lbl_gain_val)

        self.btn_reset_gain = QPushButton("Reset")
        self.btn_reset_gain.setFixedWidth(50)
        self.btn_reset_gain.setStyleSheet("font-size: 10px; padding: 2px 4px;")
        self.btn_reset_gain.setToolTip("Reset gain trim to 100% (unity gain)")
        self.btn_reset_gain.clicked.connect(lambda: self.slider_gain.setValue(100))
        self.row_gain.addWidget(self.btn_reset_gain)
        lay_meter.addLayout(self.row_gain)

        # Live VU Meter Widget
        self.vu_meter = DiscordVUMeterWidget(self)
        lay_meter.addWidget(self.vu_meter)

        # Legend & Stats Row
        row_legend = QHBoxLayout()
        self.lbl_stats = QLabel("Ambient: 5% | Threshold: 70% | Level: 0%")
        self.lbl_stats.setStyleSheet("font-size: 10px; color: #a1a1aa; font-family: monospace;")
        row_legend.addWidget(self.lbl_stats)
        row_legend.addStretch()

        self.lbl_status = QLabel("● Active")
        self.lbl_status.setStyleSheet("font-size: 10px; font-weight: bold; color: #22c55e;")
        row_legend.addWidget(self.lbl_status)
        lay_meter.addLayout(row_legend)

        # Color legend chips in a 2x2 grid to prevent any horizontal overflow
        grid_chips = QGridLayout()
        grid_chips.setSpacing(4)
        grid_chips.setContentsMargins(0, 2, 0, 2)
        chips = [
            ("Green", "#22c55e", "Normal Speech"),
            ("Yellow", "#eab308", "Elevated Banter"),
            ("Orange", "#f97316", "Possible Moment"),
            ("Red", "#ef4444", "Peak Trigger Event")
        ]
        for idx, (name, col, desc) in enumerate(chips):
            chip = QLabel(f"<span style='color: {col}; font-size: 11px;'>■</span> <b>{name}</b> <span style='color: #71717a;'>({desc})</span>")
            chip.setStyleSheet("font-size: 9.5px; color: #d4d4d8;")
            grid_chips.addWidget(chip, idx // 2, idx % 2)
        lay_meter.addLayout(grid_chips)

        lay.addWidget(self.grp_meter)

        # ------------------ CARD 2: SENSITIVITY & TIMING ------------------
        self.grp_sens = QGroupBox("Sensitivity && Peak Trigger Tuning")
        lay_sens = QVBoxLayout(self.grp_sens)
        lay_sens.setSpacing(10)

        self.chk_auto_sens = QCheckBox("Auto-determine sensitivity (Discord-style adaptive baseline)")
        self.chk_auto_sens.setStyleSheet("font-weight: 600; font-size: 11px;")
        self.chk_auto_sens.toggled.connect(self._on_auto_sens_toggled)
        lay_sens.addWidget(self.chk_auto_sens)

        # Spike Trigger Offset Slider Row (Adaptive Offset)
        self.row_offset = QHBoxLayout()
        self.lbl_offset_title = QLabel("Spike Trigger Offset:")
        self.lbl_offset_title.setFixedWidth(145)
        self.row_offset.addWidget(self.lbl_offset_title)

        self.slider_offset = QSlider(Qt.Orientation.Horizontal)
        self.slider_offset.setRange(15, 60)
        self.slider_offset.setValue(30)
        self.slider_offset.valueChanged.connect(self._on_offset_changed)
        self.row_offset.addWidget(self.slider_offset, 1)

        self.lbl_offset_val = QLabel("+30%")
        self.lbl_offset_val.setFixedWidth(40)
        self.lbl_offset_val.setStyleSheet("font-weight: bold; font-family: monospace; color: #38bdf8;")
        self.row_offset.addWidget(self.lbl_offset_val)
        lay_sens.addLayout(self.row_offset)

        self.lbl_offset_hint = QLabel("💡 <i>Adaptive Offset: Sets how high above your normal speaking volume audio must spike to trigger a clip marker (+30% is recommended).</i>")
        self.lbl_offset_hint.setStyleSheet("font-size: 10px; color: #71717a;")
        self.lbl_offset_hint.setWordWrap(True)
        lay_sens.addWidget(self.lbl_offset_hint)

        # Manual Threshold Slider Row
        self.row_thresh = QHBoxLayout()
        self.lbl_thresh_title = QLabel("Manual Trigger Threshold:")
        self.lbl_thresh_title.setFixedWidth(145)
        self.row_thresh.addWidget(self.lbl_thresh_title)

        self.slider_thresh = QSlider(Qt.Orientation.Horizontal)
        self.slider_thresh.setRange(20, 100)
        self.slider_thresh.setValue(70)
        self.slider_thresh.valueChanged.connect(self._on_manual_thresh_changed)
        self.row_thresh.addWidget(self.slider_thresh, 1)

        self.lbl_thresh_val = QLabel("70%")
        self.lbl_thresh_val.setFixedWidth(40)
        self.lbl_thresh_val.setStyleSheet("font-weight: bold; font-family: monospace;")
        self.row_thresh.addWidget(self.lbl_thresh_val)
        lay_sens.addLayout(self.row_thresh)

        # Sustained Duration Filter Row
        row_dur = QHBoxLayout()
        lbl_dur_title = QLabel("Minimum Peak Duration:")
        lbl_dur_title.setFixedWidth(145)
        row_dur.addWidget(lbl_dur_title)

        self.slider_duration = QSlider(Qt.Orientation.Horizontal)
        self.slider_duration.setRange(100, 800)
        self.slider_duration.setValue(250)
        self.slider_duration.valueChanged.connect(self._on_duration_changed)
        row_dur.addWidget(self.slider_duration, 1)

        self.lbl_dur_val = QLabel("250 ms")
        self.lbl_dur_val.setFixedWidth(50)
        self.lbl_dur_val.setStyleSheet("font-weight: bold; font-family: monospace;")
        row_dur.addWidget(self.lbl_dur_val)
        lay_sens.addLayout(row_dur)

        lbl_dur_hint = QLabel("💡 <i>Filters out acoustic spikes like clicks or desk bumps. Audio must stay elevated for this duration to count.</i>")
        lbl_dur_hint.setStyleSheet("font-size: 10px; color: #71717a;")
        lbl_dur_hint.setWordWrap(True)
        lay_sens.addWidget(lbl_dur_hint)

        self.chk_log_orange = QCheckBox("Log Orange 'Possible Moments' to text file (Approaching peak)")
        self.chk_log_orange.setStyleSheet("font-size: 11px;")
        self.chk_log_orange.toggled.connect(self._on_log_orange_toggled)
        lay_sens.addWidget(self.chk_log_orange)

        lay.addWidget(self.grp_sens)

        # ------------------ CARD 3: TRIGGER ACTIONS & STREAM FEEDBACK ------------------
        self.grp_actions = QGroupBox("Trigger Actions && Streamer Feedback")
        lay_actions = QVBoxLayout(self.grp_actions)
        lay_actions.setSpacing(10)

        # Twitch Stream Marker Checkbox & Indented Label Input
        self.chk_twitch = QCheckBox("Drop Live Twitch Stream Marker on Primary Peak")
        self.chk_twitch.setChecked(True)
        self.chk_twitch.setStyleSheet("font-weight: 600; font-size: 11px;")
        lay_actions.addWidget(self.chk_twitch)

        row_tw_desc = QHBoxLayout()
        row_tw_desc.setContentsMargins(22, 0, 0, 0)
        lbl_tw_title = QLabel("Marker Label:")
        lbl_tw_title.setStyleSheet("font-size: 10.5px; color: #a1a1aa;")
        row_tw_desc.addWidget(lbl_tw_title)

        self.combo_marker_desc = QComboBox()
        self.combo_marker_desc.setEditable(True)
        self.combo_marker_desc.addItems(["Auto-Clip/Markers", "Hype Peak", "Clip Window: -40s / +20s"])
        self.combo_marker_desc.currentTextChanged.connect(self._on_marker_desc_changed)
        row_tw_desc.addWidget(self.combo_marker_desc, 1)
        lay_actions.addLayout(row_tw_desc)

        # Monitor Border Flash Alert
        row_flash = QHBoxLayout()
        self.chk_flash = QCheckBox("Flash Monitor Border Alert on Peak Detection")
        self.chk_flash.setChecked(True)
        self.chk_flash.toggled.connect(self._on_flash_toggled)
        row_flash.addWidget(self.chk_flash, 1)

        lbl_col = QLabel("Color:")
        lbl_col.setStyleSheet("font-size: 10.5px; color: #a1a1aa;")
        row_flash.addWidget(lbl_col)

        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(36, 20)
        self.btn_color.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_color.clicked.connect(self._on_pick_color)
        row_flash.addWidget(self.btn_color)

        self.lbl_color_hex = QLabel("#f59e0b")
        self.lbl_color_hex.setStyleSheet("font-family: monospace; font-size: 10px; color: #a1a1aa;")
        row_flash.addWidget(self.lbl_color_hex)
        lay_actions.addLayout(row_flash)

        # Sound Chime
        self.chk_chime = QCheckBox("Play Audio Confirmation Chime in Headphones")
        self.chk_chime.setChecked(True)
        self.chk_chime.toggled.connect(self._on_chime_toggled)
        lay_actions.addWidget(self.chk_chime)

        # Cooldown Status Badge
        self.lbl_cooldown = QLabel("⏱️ Cooldown Status: Inactive (Armed & Ready)")
        self.lbl_cooldown.setStyleSheet("font-size: 11px; font-weight: bold; color: #22c55e;")
        lay_actions.addWidget(self.lbl_cooldown)

        lay.addWidget(self.grp_actions)

        # ------------------ CARD 4: ACTIVE SCENE WHITELIST ------------------
        self.grp_scenes = QGroupBox("Active Scenes Filter")
        lay_scenes = QVBoxLayout(self.grp_scenes)
        lay_scenes.setSpacing(6)

        lbl_sc_info = QLabel("Select which broadcast scenes Auto-Clip monitoring is active on. "
                             "Monitoring automatically pauses during quiet chatting or BRB scenes.")
        lbl_sc_info.setStyleSheet("font-size: 10px; color: #a1a1aa;")
        lbl_sc_info.setWordWrap(True)
        lay_scenes.addWidget(lbl_sc_info)

        self.lay_scene_grid = QGridLayout()
        self.lay_scene_grid.setSpacing(6)
        lay_scenes.addLayout(self.lay_scene_grid)
        self.scene_checkboxes = {}
        self._populate_scene_checkboxes()

        lay.addWidget(self.grp_scenes)

        # ------------------ CARD 5: LOG MANAGEMENT ------------------
        self.grp_log = QGroupBox("Clip Window History (cooldown_clips.txt)")
        lay_log = QVBoxLayout(self.grp_log)
        lay_log.setSpacing(6)

        lbl_log_desc = QLabel("All secondary peaks detected during cooldown periods (and optional orange moments) "
                              "are logged with their calculated 60-second clip boundaries (40s before / 20s after).")
        lbl_log_desc.setStyleSheet("font-size: 10px; color: #a1a1aa;")
        lbl_log_desc.setWordWrap(True)
        lay_log.addWidget(lbl_log_desc)

        row_log_btns = QHBoxLayout()
        self.btn_open_log = QPushButton("📂 Open Clips Log File")
        self.btn_open_log.setFixedHeight(28)
        self.btn_open_log.clicked.connect(self.engine.open_log_file)
        row_log_btns.addWidget(self.btn_open_log)

        self.btn_clear_log = QPushButton("🗑️ Clear Log")
        self.btn_clear_log.setFixedHeight(28)
        self.btn_clear_log.clicked.connect(self._on_clear_log)
        row_log_btns.addWidget(self.btn_clear_log)
        row_log_btns.addStretch()
        lay_log.addLayout(row_log_btns)

        lay.addWidget(self.grp_log)

        self.cards = [self.grp_meter, self.grp_sens, self.grp_actions, self.grp_scenes, self.grp_log]

        lay.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

    # ------------------ UI Helpers & Load / Save ------------------

    def _populate_devices(self):
        """Populates the input device dropdown with all available audio sources."""
        self.combo_device.blockSignals(True)
        self.combo_device.clear()

        devices = self.engine.get_available_devices()
        selected_idx = 0

        for i, d in enumerate(devices):
            desc = d.description()
            tag = " (Default)" if d.isDefault() else ""
            self.combo_device.addItem(f"{desc}{tag}", desc)
            if self.engine.selected_device_name and desc.strip() == self.engine.selected_device_name.strip():
                selected_idx = i

        self.combo_device.setCurrentIndex(selected_idx)
        self.combo_device.blockSignals(False)

    def _populate_scene_checkboxes(self):
        """Builds checkboxes for default & configured scenes."""
        scenes = ["In-Game", "Banter", "BRB", "Starting", "Ending", "Scene 6"]
        if self.main_win and hasattr(self.main_win, "settings_window") and hasattr(self.main_win.settings_window, "tab_director"):
            dir_scenes = self.main_win.settings_window.tab_director.scenes
            if dir_scenes:
                scenes = [s.get("name") for s in dir_scenes if s.get("name")]

        # Clear existing
        while self.lay_scene_grid.count():
            item = self.lay_scene_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.scene_checkboxes.clear()

        cols = 2
        for i, sc_name in enumerate(scenes):
            chk = QCheckBox(sc_name)
            chk.setToolTip(sc_name)
            chk.setChecked(sc_name in self.engine.active_scenes)
            chk.toggled.connect(self._on_scene_toggled)
            self.scene_checkboxes[sc_name] = chk
            self.lay_scene_grid.addWidget(chk, i // cols, i % cols)

    def _load_from_engine(self):
        """Loads values from AutoClipEngine into the UI."""
        self._populate_devices()
        self.switch_master_enable.blockSignals(True)
        self.switch_master_enable.setChecked(self.engine.enabled)
        self.switch_master_enable.blockSignals(False)
        self._on_master_enable_toggled(self.engine.enabled)

        gain_pct = int(getattr(self.engine, "input_gain", 1.0) * 100)
        self.slider_gain.setValue(gain_pct)
        self.lbl_gain_val.setText(f"{gain_pct}%")

        self.chk_auto_sens.setChecked(self.engine.auto_sensitivity)
        offset_pct = int(self.engine.trigger_offset * 100)
        self.slider_offset.setValue(offset_pct)
        self.lbl_offset_val.setText(f"+{offset_pct}%")
        self.slider_thresh.setValue(int(self.engine.manual_threshold * 100))
        self.lbl_thresh_val.setText(f"{int(self.engine.manual_threshold * 100)}%")
        self.slider_duration.setValue(self.engine.min_duration_ms)
        self.lbl_dur_val.setText(f"{self.engine.min_duration_ms} ms")
        self.chk_log_orange.setChecked(self.engine.log_orange_moments)
        self.chk_flash.setChecked(self.engine.flash_overlay)
        self._update_color_preview(self.engine.alert_color)
        self.chk_chime.setChecked(self.engine.play_chime)
        self.combo_marker_desc.setEditText(self.engine.marker_description)
        self._on_auto_sens_toggled(self.engine.auto_sensitivity)

    def _update_color_preview(self, hex_color: str):
        self.engine.alert_color = hex_color
        self.btn_color.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #ffffff; border-radius: 4px;")
        self.lbl_color_hex.setText(hex_color)

    # ------------------ Slot Callbacks ------------------

    def _on_master_enable_toggled(self, checked: bool):
        self.engine.enabled = checked
        if checked:
            self.switch_master_enable.setStyleSheet("font-size: 12px; font-weight: bold; color: #22c55e;")
            self.switch_master_enable.setText("Enable Auto-Clip Monitoring (ACTIVE)")
            self.lbl_status.setText("● Active")
            self.lbl_status.setStyleSheet("font-size: 10px; font-weight: bold; color: #22c55e;")
            self.engine.start_monitoring()
        else:
            self.switch_master_enable.setStyleSheet("font-size: 12px; font-weight: bold; color: #71717a;")
            self.switch_master_enable.setText("Enable Auto-Clip Monitoring (DISABLED)")
            self.lbl_status.setText("● Disabled")
            self.lbl_status.setStyleSheet("font-size: 10px; font-weight: bold; color: #71717a;")
            self.engine.stop_monitoring()
            self.vu_meter.update_meter(0.0, self.engine.ZONE_GREEN, self.engine.current_baseline, self.engine.current_threshold)

        if hasattr(self, "cards"):
            for c in self.cards:
                c.setEnabled(checked)
        self.settings_changed.emit()

    def _open_audio_diagnostics(self):
        from audio_diagnostics import AudioDiagnosticsDialog
        overlay = getattr(self.main_win, "overlay", None) if self.main_win else None
        dlg = AudioDiagnosticsDialog(self, overlay_app=overlay, engine=self.engine)
        dlg.exec()

    def _on_device_changed(self):
        dev_desc = self.combo_device.currentData()
        if dev_desc:
            self.engine.set_device_by_name(dev_desc)
            self.settings_changed.emit()

    def _on_gain_changed(self, val: int):
        self.engine.input_gain = val / 100.0
        self.lbl_gain_val.setText(f"{val}%")
        self.settings_changed.emit()

    def _on_auto_sens_toggled(self, checked: bool):
        self.engine.auto_sensitivity = checked
        self.slider_thresh.setEnabled(not checked)
        self.lbl_thresh_title.setStyleSheet("color: #71717a;" if checked else "color: #ffffff;")
        self.lbl_thresh_val.setStyleSheet("color: #71717a;" if checked else "color: #ffffff;")

        self.slider_offset.setEnabled(checked)
        self.lbl_offset_title.setStyleSheet("color: #ffffff;" if checked else "color: #71717a;")
        self.lbl_offset_val.setStyleSheet("font-weight: bold; font-family: monospace; color: #38bdf8;" if checked else "color: #71717a;")
        self.lbl_offset_hint.setStyleSheet("font-size: 10px; color: #71717a;" if checked else "font-size: 10px; color: #52525b;")
        self.settings_changed.emit()

    def _on_offset_changed(self, val: int):
        self.engine.trigger_offset = val / 100.0
        self.lbl_offset_val.setText(f"+{val}%")
        if self.engine.auto_sensitivity:
            offset = self.engine.trigger_offset
            self.engine.current_threshold = min(0.98, max(0.68, self.engine.current_baseline + offset))
            self.vu_meter.update_meter(self.vu_meter.current_level, self.vu_meter.current_zone, self.engine.current_baseline, self.engine.current_threshold)
            self.lbl_stats.setText(
                f"Ambient: {int(self.engine.current_baseline * 100)}% | Trigger: {int(self.engine.current_threshold * 100)}% | Current: {int(self.vu_meter.current_level * 100)}%"
            )
        self.settings_changed.emit()

    def _on_manual_thresh_changed(self, val: int):
        self.engine.manual_threshold = val / 100.0
        self.lbl_thresh_val.setText(f"{val}%")
        if not self.engine.auto_sensitivity:
            self.engine.current_threshold = self.engine.manual_threshold
            self.vu_meter.update_meter(self.vu_meter.current_level, self.vu_meter.current_zone, self.engine.current_baseline, self.engine.current_threshold)
            self.lbl_stats.setText(
                f"Ambient: {int(self.engine.current_baseline * 100)}% | Trigger: {int(self.engine.current_threshold * 100)}% | Current: {int(self.vu_meter.current_level * 100)}%"
            )
        self.settings_changed.emit()

    def _on_duration_changed(self, val: int):
        self.engine.min_duration_ms = val
        self.lbl_dur_val.setText(f"{val} ms")
        self.settings_changed.emit()

    def _on_log_orange_toggled(self, checked: bool):
        self.engine.log_orange_moments = checked
        self.settings_changed.emit()

    def _on_flash_toggled(self, checked: bool):
        self.engine.flash_overlay = checked
        self.settings_changed.emit()

    def _on_chime_toggled(self, checked: bool):
        self.engine.play_chime = checked
        self.settings_changed.emit()

    def _on_marker_desc_changed(self, text: str):
        self.engine.marker_description = text.strip() or "Auto-Clip/Markers"
        self.settings_changed.emit()

    def _on_pick_color(self):
        cur = QColor(self.engine.alert_color)
        chosen = QColorDialog.getColor(cur, self, "Select Marker Highlight Alert Color")
        if chosen.isValid():
            self._update_color_preview(chosen.name())
            self.settings_changed.emit()

    def _on_scene_toggled(self):
        active = [name for name, chk in self.scene_checkboxes.items() if chk.isChecked()]
        self.engine.active_scenes = active
        self.settings_changed.emit()

    def _on_clear_log(self):
        res = QMessageBox.question(self, "Clear Log", "Are you sure you want to clear cooldown_clips.txt?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if res == QMessageBox.StandardButton.Yes:
            self.engine.clear_log_file()

    # ------------------ Engine Signal Listeners ------------------

    def _on_level_updated(self, level: float, zone: int, baseline: float, threshold: float):
        self.vu_meter.update_meter(level, zone, baseline, threshold)
        self.lbl_stats.setText(
            f"Ambient: {int(baseline * 100)}% | Trigger: {int(threshold * 100)}% | Current: {int(level * 100)}%"
        )

    def _on_cooldown_tick(self, rem: int):
        if rem > 0:
            self.lbl_cooldown.setText(f"⏱️ Cooldown Active: {rem}s remaining (Secondary peaks logged to file)")
            self.lbl_cooldown.setStyleSheet("font-size: 11px; font-weight: bold; color: #f59e0b;")
        else:
            self.lbl_cooldown.setText("⏱️ Cooldown Status: Inactive (Armed & Ready)")
            self.lbl_cooldown.setStyleSheet("font-size: 11px; font-weight: bold; color: #22c55e;")

    def _on_status_changed(self, msg: str, is_active: bool):
        if not self.engine.enabled or msg == "Disabled":
            tag = "Disabled"
            col = "#71717a"
        elif is_active:
            tag = "Active"
            col = "#22c55e"
        else:
            tag = "Paused"
            col = "#eab308"
        self.lbl_status.setText(f"● {tag}")
        self.lbl_status.setToolTip(f"Auto-Clip Status: {msg}")
        self.lbl_status.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {col};")

    def _on_marker_triggered(self, payload: dict):
        # Update cooldown immediately
        self.lbl_cooldown.setText(f"🔥 PEAK TRIGGERED! Cooldown: {self.engine.cooldown_duration_sec}s")
        self.lbl_cooldown.setStyleSheet("font-size: 11px; font-weight: bold; color: #ef4444;")

    def set_streamer_mode(self, enabled: bool):
        """Disables or enables the tab controls and displays warning banner when Streamer Mode is OFF."""
        is_active = bool(enabled)
        self.banner_streamer_mode.setVisible(not is_active)
        self.engine.set_streamer_mode(is_active)
        if not is_active:
            self.lbl_status.setText("● Inactive (Streamer Mode OFF)")
            self.lbl_status.setStyleSheet("font-size: 10px; font-weight: bold; color: #71717a;")
            if hasattr(self, "cards"):
                for c in self.cards:
                    c.setEnabled(False)
            self.switch_master_enable.setEnabled(False)
        else:
            self.switch_master_enable.setEnabled(True)
            self._on_master_enable_toggled(self.engine.enabled)
