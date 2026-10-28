"""
Streamer Calyx - Audio Input Diagnostics Suite
Provides non-invasive 5-second acoustic analysis, telemetry collection,
and diagnostic reporting for microphone and VoiceMeeter audio routing.
Does NOT record or save any audio files (privacy-safe).
"""

import os
import sys
import math
import time
import struct
import datetime
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QProgressBar, QTextEdit, QMessageBox, QFrame
)
from PyQt6.QtGui import QColor, QPainter, QPen, QGuiApplication
from PyQt6.QtMultimedia import QMediaDevices, QAudioSource, QAudioDevice, QAudioFormat

from updater import CURRENT_VERSION, get_build_commit, get_full_version_string
from debug_logger import log_debug
import theme_manager

APP_DIR = os.path.join(os.environ.get("APPDATA", ""), "StreamerCalyx")


class MiniVUMeter(QFrame):
    """Compact live VU meter for the diagnostic dialog."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(18)
        self.current_level = 0.0

    def set_level(self, val: float):
        self.current_level = max(0.0, min(1.0, val))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#18181b"))
        painter.drawRoundedRect(0, 0, w, h, 3, 3)

        # Segments
        num_segments = 36
        gap = 2
        seg_w = (w - (num_segments - 1) * gap) / num_segments
        lit = int(self.current_level * num_segments)

        for i in range(num_segments):
            is_lit = i < lit
            # Zone colors matching engine
            if i >= 25:    # Red (~0.68)
                c = QColor("#ef4444") if is_lit else QColor("#450a0a")
            elif i >= 19:  # Orange (~0.52)
                c = QColor("#f97316") if is_lit else QColor("#431407")
            elif i >= 10:  # Yellow (~0.28)
                c = QColor("#eab308") if is_lit else QColor("#422006")
            else:          # Green (<0.28)
                c = QColor("#22c55e") if is_lit else QColor("#052e16")

            x = i * (seg_w + gap)
            painter.setBrush(c)
            painter.drawRoundedRect(QRectF(x, 2, seg_w, h - 4), 1.5, 1.5)


class AudioDiagnosticsDialog(QDialog):
    """
    Modal dialog allowing streamers to benchmark audio levels, verify zone placement,
    and generate telemetry reports for bug reports or troubleshooting.
    """
    def __init__(self, parent=None, overlay_app=None, engine=None):
        super().__init__(parent)
        self.overlay_app = overlay_app
        self.engine = engine
        self.setObjectName("AudioDiagnosticsDialog")
        self.setWindowTitle("Audio Input Diagnostics & Calibration Suite")
        self.resize(580, 640)

        # State
        self.is_testing = False
        self.test_tick = 0
        self.total_ticks = 100  # 100 * 50ms = 5000ms = 5 seconds
        self.audio_source = None
        self.audio_io = None
        self.samples_rms = []
        self.samples_peak = []
        self.samples_level = []
        self.samples_dbfs = []
        self.clip_count = 0
        self.report_text = ""

        # Timers
        self.timer_sample = QTimer(self)
        self.timer_sample.setInterval(50)
        self.timer_sample.timeout.connect(self._on_sample_tick)

        self._build_ui()
        self._populate_devices()

        pref = getattr(self.overlay_app, "theme_preference", "system") if self.overlay_app else "system"
        theme_manager.apply_theme_to_window(self, pref)

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(14, 14, 14, 14)

        # Header
        hdr = QVBoxLayout()
        hdr.setSpacing(2)
        lbl_title = QLabel("🎙️ AUDIO INPUT DIAGNOSTICS & CALIBRATION")
        lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        hdr.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Runs a non-invasive 5-second acoustic analysis on your input device (microphone or VoiceMeeter). "
            "Telemetry is computed in real-time without recording or saving audio files."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        hdr.addWidget(lbl_desc)
        lay.addLayout(hdr)

        # Device Selection Row
        row_dev = QHBoxLayout()
        row_dev.addWidget(QLabel("Test Input Device:"))
        self.combo_device = QComboBox()
        self.combo_device.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        row_dev.addWidget(self.combo_device, 1)

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setFixedWidth(75)
        self.btn_refresh.clicked.connect(self._populate_devices)
        row_dev.addWidget(self.btn_refresh)
        lay.addLayout(row_dev)

        # 5-Second Test Control Box
        box_test = QFrame()
        box_test.setStyleSheet("QFrame { background-color: #1e1e24; border: 1px solid #3f3f46; border-radius: 6px; padding: 8px; }")
        lay_test = QVBoxLayout(box_test)
        lay_test.setSpacing(8)

        self.btn_start_test = QPushButton("▶️ Start 5-Second Diagnostic Test")
        self.btn_start_test.setFixedHeight(34)
        self.btn_start_test.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #38bdf8;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:disabled {
                background-color: #3f3f46;
                color: #71717a;
                border: 1px solid #52525b;
            }
        """)
        self.btn_start_test.clicked.connect(self.start_diagnostic_test)
        lay_test.addWidget(self.btn_start_test)

        # Phase / Prompt Label
        self.lbl_prompt = QLabel("Click 'Start 5-Second Diagnostic Test' to begin calibration.")
        self.lbl_prompt.setStyleSheet("font-size: 11px; font-weight: 600; color: #fbbf24;")
        self.lbl_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay_test.addWidget(self.lbl_prompt)

        # Progress bar
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setFixedHeight(12)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setStyleSheet("""
            QProgressBar { background-color: #18181b; border: 1px solid #3f3f46; border-radius: 3px; }
            QProgressBar::chunk { background-color: #38bdf8; border-radius: 2px; }
        """)
        lay_test.addWidget(self.prog_bar)

        # Live Mini VU Meter
        self.meter_live = MiniVUMeter(self)
        lay_test.addWidget(self.meter_live)

        lay.addWidget(box_test)

        # Report Viewer
        lay.addWidget(QLabel("<b>Diagnostic Telemetry Summary:</b>"))
        self.txt_report = QTextEdit()
        self.txt_report.setReadOnly(True)
        self.txt_report.setStyleSheet("font-family: 'Consolas', 'Courier New', monospace; font-size: 10.5px; background-color: #121214; color: #d4d4d8; border: 1px solid #27272a; border-radius: 4px;")
        self.txt_report.setPlaceholderText("Diagnostic test results and telemetry metrics will appear here after completing the 5-second test...")
        lay.addWidget(self.txt_report)

        # Action Buttons
        row_actions = QHBoxLayout()
        self.btn_copy = QPushButton("📋 Copy Diagnostic Report")
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self.copy_report)
        row_actions.addWidget(self.btn_copy)

        self.btn_bug_report = QPushButton("🐞 Attach to Bug Report...")
        self.btn_bug_report.setEnabled(False)
        self.btn_bug_report.clicked.connect(self.attach_to_bug_report)
        row_actions.addWidget(self.btn_bug_report)

        row_actions.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setFixedWidth(75)
        btn_close.clicked.connect(self._on_close)
        row_actions.addWidget(btn_close)

        lay.addLayout(row_actions)

    def _populate_devices(self):
        self.combo_device.clear()
        devices = QMediaDevices.audioInputs()
        selected_idx = 0
        target_name = ""
        if self.engine and self.engine.selected_device_name:
            target_name = self.engine.selected_device_name.strip()

        for idx, d in enumerate(devices):
            desc = d.description()
            tag = " (Default)" if d.isDefault() else ""
            self.combo_device.addItem(f"{desc}{tag}", desc)
            if target_name and desc.strip() == target_name:
                selected_idx = idx

        self.combo_device.setCurrentIndex(selected_idx)

    def start_diagnostic_test(self):
        if self.is_testing:
            return

        self.is_testing = True
        self.test_tick = 0
        self.samples_rms.clear()
        self.samples_peak.clear()
        self.samples_level.clear()
        self.samples_dbfs.clear()
        self.clip_count = 0
        self.prog_bar.setValue(0)

        self.btn_start_test.setEnabled(False)
        self.combo_device.setEnabled(False)
        self.btn_copy.setEnabled(False)
        self.btn_bug_report.setEnabled(False)
        self.txt_report.clear()

        # Start audio capture on chosen device
        device_desc = self.combo_device.currentData()
        target_dev = None
        for d in QMediaDevices.audioInputs():
            if d.description() == device_desc:
                target_dev = d
                break
        if not target_dev:
            target_dev = QMediaDevices.defaultAudioInput()

        fmt = target_dev.preferredFormat()
        self._target_device_name = target_dev.description()
        self._target_rate = fmt.sampleRate() or 48000
        self._target_channels = max(1, fmt.channelCount())
        self._target_format = fmt.sampleFormat()
        self._target_is_default = target_dev.isDefault()

        try:
            self.audio_source = QAudioSource(target_dev, fmt, self)
            self.audio_io = self.audio_source.start()
            self.timer_sample.start()
            log_debug("AUDIO_DIAG", f"Started diagnostic audio test on: {self._target_device_name}")
        except Exception as e:
            log_debug("AUDIO_DIAG", f"Error starting diagnostic audio capture: {e}")
            self._cleanup_test()
            QMessageBox.critical(self, "Audio Error", f"Unable to access audio input device: {e}")

    def _on_sample_tick(self):
        self.test_tick += 1
        pct = int((self.test_tick / self.total_ticks) * 100)
        self.prog_bar.setValue(pct)

        # Update prompt
        if self.test_tick <= 50:
            rem = max(1, (50 - self.test_tick) // 20 + 1)
            self.lbl_prompt.setText(f"🗣️ Phase 1/2 ({rem}s): Speak normally into your mic at standard talking volume...")
            self.lbl_prompt.setStyleSheet("font-size: 11px; font-weight: 600; color: #38bdf8;")
        else:
            rem = max(1, (100 - self.test_tick) // 20 + 1)
            self.lbl_prompt.setText(f"🔥 Phase 2/2 ({rem}s): Laugh loudly, cheer, or shout to test peak reaction level...")
            self.lbl_prompt.setStyleSheet("font-size: 11px; font-weight: 600; color: #f97316;")

        # Read samples
        if self.audio_io:
            try:
                raw_bytes = self.audio_io.readAll().data()
                byte_len = len(raw_bytes) if raw_bytes else 0
                if byte_len >= 2:
                    gain = getattr(self.engine, "input_gain", 1.0) if self.engine else 1.0
                    peak = 0.0
                    rms = 0.0

                    # 1. 32-bit Floating Point PCM (Standard for WASAPI / Windows 11 & VoiceMeeter)
                    if getattr(self, "_target_format", None) == QAudioFormat.SampleFormat.Float:
                        num_floats = byte_len // 4
                        if num_floats > 0:
                            floats = struct.unpack(f"<{num_floats}f", raw_bytes[:num_floats * 4])
                            peak = min(1.0, max(abs(f) for f in floats) * gain)
                            sum_sq = sum((f * gain) ** 2 for f in floats)
                            rms = min(1.0, math.sqrt(sum_sq / len(floats)))
                    # 2. 32-bit Signed Integer PCM
                    elif getattr(self, "_target_format", None) == QAudioFormat.SampleFormat.Int32:
                        num_ints = byte_len // 4
                        if num_ints > 0:
                            ints = struct.unpack(f"<{num_ints}i", raw_bytes[:num_ints * 4])
                            peak = min(1.0, (max(abs(i) for i in ints) / 2147483647.0) * gain)
                            sum_sq = sum(((i / 2147483647.0) * gain) ** 2 for i in ints)
                            rms = min(1.0, math.sqrt(sum_sq / len(ints)))
                    # 3. 16-bit Signed Integer PCM (Standard Fallback)
                    else:
                        num_shorts = byte_len // 2
                        if num_shorts > 0:
                            shorts = struct.unpack(f"<{num_shorts}h", raw_bytes[:num_shorts * 2])
                            peak = min(1.0, (max(abs(s) for s in shorts) / 32767.0) * gain)
                            sum_sq = sum(((s / 32767.0) * gain) ** 2 for s in shorts)
                            rms = min(1.0, math.sqrt(sum_sq / len(shorts)))

                    # Check clipping (digital saturation)
                    if peak >= 0.999:
                        self.clip_count += 1

                    # Stevens perceptual level (square-root curve)
                    p_rms = math.sqrt(rms) if rms > 0.0 else 0.0
                    p_peak = math.sqrt(peak) if peak > 0.0 else 0.0
                    level = min(1.0, max(0.0, 0.65 * p_rms + 0.35 * p_peak))

                    dbfs = 20.0 * math.log10(max(1e-5, rms))

                    self.samples_rms.append(rms)
                    self.samples_peak.append(peak)
                    self.samples_level.append(level)
                    self.samples_dbfs.append(dbfs)
                    self.meter_live.set_level(level)
            except Exception as e:
                log_debug("AUDIO_DIAG", f"Sample read exception: {e}")

        # Finish test
        if self.test_tick >= self.total_ticks:
            self._finish_test()

    def _finish_test(self):
        self._cleanup_test()
        self.lbl_prompt.setText("✅ 5-Second Diagnostic Test Complete! Review your report below.")
        self.lbl_prompt.setStyleSheet("font-size: 11px; font-weight: bold; color: #22c55e;")
        self.meter_live.set_level(0.0)

        # Generate report
        self.report_text = self._build_report()
        self.txt_report.setPlainText(self.report_text)
        self.btn_copy.setEnabled(True)
        self.btn_bug_report.setEnabled(True)

        # Save report to APP_DIR/audio_diagnostic.txt
        try:
            os.makedirs(APP_DIR, exist_ok=True)
            report_file = os.path.join(APP_DIR, "audio_diagnostic.txt")
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(self.report_text)
            log_debug("AUDIO_DIAG", f"Saved audio diagnostic report to {report_file}")
        except Exception as e:
            log_debug("AUDIO_DIAG", f"Failed saving report file: {e}")

    def _cleanup_test(self):
        self.timer_sample.stop()
        if self.audio_source:
            try:
                self.audio_source.stop()
            except Exception:
                pass
            self.audio_source = None
            self.audio_io = None
        self.is_testing = False
        self.btn_start_test.setEnabled(True)
        self.combo_device.setEnabled(True)

    def _build_report(self) -> str:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_samples = len(self.samples_level)

        if total_samples == 0:
            return "ERROR: No audio samples were captured during the diagnostic test. Please check device selection."

        # Compute statistics
        avg_rms = sum(self.samples_rms) / total_samples
        max_rms = max(self.samples_rms)
        max_peak = max(self.samples_peak)
        avg_level = sum(self.samples_level) / total_samples
        max_level = max(self.samples_level)

        # Phase 1 (Speech: first half) & Phase 2 (Peak: second half)
        half = total_samples // 2
        speech_samples = self.samples_level[:half]
        peak_samples = self.samples_level[half:]
        avg_speech_level = (sum(speech_samples) / len(speech_samples)) if speech_samples else avg_level
        max_shout_level = max(peak_samples) if peak_samples else max_level

        # Noise floor (lowest 15% of samples)
        sorted_levels = sorted(self.samples_level)
        noise_idx = max(1, int(total_samples * 0.15))
        ambient_noise_floor = sum(sorted_levels[:noise_idx]) / noise_idx

        # Decibels
        rms_dbfs = 20.0 * math.log10(max(1e-5, avg_rms))
        peak_dbfs = 20.0 * math.log10(max(1e-5, max_peak))
        noise_dbfs = 20.0 * math.log10(max(1e-5, ambient_noise_floor))
        crest_factor = peak_dbfs - rms_dbfs

        # Zone Distribution
        green_cnt = sum(1 for x in self.samples_level if x < 0.28)
        yellow_cnt = sum(1 for x in self.samples_level if 0.28 <= x < 0.52)
        orange_cnt = sum(1 for x in self.samples_level if 0.52 <= x < 0.68)
        red_cnt = sum(1 for x in self.samples_level if x >= 0.68)

        pct_green = (green_cnt / total_samples) * 100.0
        pct_yellow = (yellow_cnt / total_samples) * 100.0
        pct_orange = (orange_cnt / total_samples) * 100.0
        pct_red = (red_cnt / total_samples) * 100.0

        # Health assessment
        findings = []
        if 0.28 <= avg_speech_level <= 0.48:
            findings.append("✓ Normal speaking volume sits in the Yellow zone (30%-48%) [OPTIMAL CALIBRATION].")
        elif avg_speech_level < 0.28:
            findings.append("⚠️ Normal speaking volume is too low (<28% - resting in Green). Increase microphone gain or VoiceMeeter fader.")
        else:
            findings.append("⚠️ Normal speaking volume is elevated (>48% - resting in Orange). Lower microphone gain slightly.")

        if max_shout_level >= 0.68:
            findings.append(f"✓ Peak laugh/shout reached {int(max_shout_level*100)}%, cleanly crossing into the Red trigger zone.")
        else:
            findings.append(f"⚠️ Peak laugh/shout reached only {int(max_shout_level*100)}% (below Red zone threshold 68%). Consider lowering Spike Trigger Offset slider.")

        if self.clip_count > 0:
            findings.append(f"⚠️ Digital clipping detected ({self.clip_count} frames saturated at 0 dBFS). Lower hardware mic input gain.")
        else:
            findings.append("✓ Clean acoustic headroom with zero digital clipping or distortion detected.")

        if ambient_noise_floor < 0.15:
            findings.append(f"✓ Low ambient noise floor ({int(ambient_noise_floor*100)}% / {noise_dbfs:.1f} dBFS) - Room background noise is well isolated.")
        else:
            findings.append(f"⚠️ Elevated ambient background noise ({int(ambient_noise_floor*100)}% / {noise_dbfs:.1f} dBFS). Check fan/room acoustics or adjust baseline.")

        fmt = getattr(self, "_target_format", None)
        if fmt == QAudioFormat.SampleFormat.Float:
            sample_fmt_str = "32-Bit IEEE Floating Point PCM (Standard WASAPI)"
        elif fmt == QAudioFormat.SampleFormat.Int32:
            sample_fmt_str = "32-Bit Signed Integer PCM"
        elif fmt == QAudioFormat.SampleFormat.Int16:
            sample_fmt_str = "16-Bit Signed Integer PCM (Little Endian)"
        else:
            sample_fmt_str = f"PCM ({fmt})"

        # Engine settings if available
        eng_lines = []
        if self.engine:
            eng_lines = [
                f"Master Enabled:           {'Yes' if self.engine.enabled else 'No (Disabled)'}",
                f"Input Gain Trim:          {int(getattr(self.engine, 'input_gain', 1.0) * 100)}%",
                f"Auto-Sensitivity Mode:    {'Yes (Discord-Style)' if self.engine.auto_sensitivity else 'No (Manual Threshold)'}",
                f"Spike Trigger Offset:     +{int(self.engine.trigger_offset * 100)}%",
                f"Current Red Threshold:    {int(self.engine.current_threshold * 100)}%",
                f"Current Baseline Floor:   {int(self.engine.current_baseline * 100)}%",
                f"Session Voice Anchor:     {int(getattr(self.engine, 'session_voice_anchor', 0.35) * 100)}% (Quiet Game Shield)",
                f"Minimum Peak Duration:    {self.engine.min_duration_ms} ms",
                f"Twitch Marker on Peak:    {'Yes' if self.engine.enabled else 'No'}",
                f"Active Scenes Whitelist:  {self.engine.active_scenes}"
            ]

        lines = [
            "=" * 78,
            "STREAMER CALYX - AUDIO INPUT DIAGNOSTIC TELEMETRY REPORT",
            f"Generated: {now_str}",
            f"Application Version: {get_full_version_string()}",
            "=" * 78,
            "",
            "[1. AUDIO DEVICE CONFIGURATION]",
            f"Device Name:              {self._target_device_name}",
            f"System Default Device:    {'Yes' if self._target_is_default else 'No'}",
            f"Sample Rate:              {self._target_rate} Hz",
            f"Channel Count:            {self._target_channels} (Stereo)" if self._target_channels == 2 else f"Channel Count:            {self._target_channels} (Mono)",
            f"Sample Format:            {sample_fmt_str}",
            "",
            "[2. SIGNAL LEVEL TELEMETRY (5-Second Analysis)]",
            f"Ambient Room Noise Floor: {int(ambient_noise_floor * 100)}% ({noise_dbfs:.1f} dBFS)",
            f"Average Speech Level:     {int(avg_speech_level * 100)}% ({rms_dbfs:.1f} dBFS)",
            f"Peak Shout/Laugh Level:   {int(max_shout_level * 100)}% ({peak_dbfs:.1f} dBFS)",
            f"Dynamic Crest Factor:     {crest_factor:.1f} dB",
            f"Digital Audio Clipping:   {'None detected' if self.clip_count == 0 else f'{self.clip_count} saturated samples detected'}",
            "",
            "[3. ZONE DISTRIBUTION TELEMETRY]",
            f"🟢 Green  (Ambient / Whispers):  {pct_green:5.1f}%  (Level < 28%)",
            f"🟡 Yellow (Normal Talking):      {pct_yellow:5.1f}%  (Level 28% - 52%)",
            f"🟠 Orange (Elevated Banter):     {pct_orange:5.1f}%  (Level 52% - 68%)",
            f"🔴 Red    (Peak Reaction Spikes): {pct_red:5.1f}%  (Level >= 68%)",
            ""
        ]

        if eng_lines:
            lines.append("[4. AUTOCLIP ENGINE ACTIVE SETTINGS]")
            lines.extend(eng_lines)
            lines.append("")

        lines.append("[5. DIAGNOSTIC ASSESSMENT & CALIBRATION VERDICT]")
        for f in findings:
            lines.append(f"  {f}")
        lines.append("")
        lines.append("=" * 78)

        return "\n".join(lines)

    def copy_report(self):
        if not self.report_text:
            return
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(self.report_text)
        QMessageBox.information(self, "Copied", "Audio diagnostic telemetry report copied to clipboard.")

    def attach_to_bug_report(self):
        from bug_report_dialog import BugReportDialog
        dlg = BugReportDialog(self, self.overlay_app)
        dlg.exec()

    def _on_close(self):
        self._cleanup_test()
        self.accept()

    def closeEvent(self, event):
        self._cleanup_test()
        super().closeEvent(event)
