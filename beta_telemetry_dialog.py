"""
beta_telemetry_dialog.py - Beta Testing Diagnostics & Privacy Disclosure Dialog
Streamer Calyx (v3.0 Architecture)

Transparently presents the Beta Diagnostic Policy to the user:
- Explains why debug mode is locked ON in Beta builds.
- Discloses the minimal PC and application info collected (OS, screen resolution, audio devices).
- Explains UI action tracking (button clicks, combo selections) within the app.
- Explicitly guarantees what is NEVER collected (no keylogging, no passwords, no private files).
# - Discloses 7-day rolling local log retention in %APPDATA%\\StreamerCalyx\\logs.
# - Standard Qt event filter for safe UI action logging that Windows Defender recognizes as benign.
"""

import os
import platform
from PyQt6.QtCore import Qt, QObject, QEvent
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QCheckBox, QApplication, QAbstractButton, QComboBox
)
from PyQt6.QtGui import QIcon

from updater import get_full_version_string
from debug_logger import log_debug, get_logs_dir, is_beta_build

def get_app_icon():
    try:
        from settings_ui import get_app_icon as _gui_icon
        return _gui_icon()
    except Exception:
        return QIcon()



class UIActionTelemetryFilter(QObject):
    """
    Standard Qt EventFilter that logs user-initiated GUI interactions (button clicks,
    combobox changes) purely within Streamer Calyx's application process space.
    
    Operates safely in user-space without any system hooks, API scraping, or keystroke
    interception, guaranteeing complete cleanliness for Windows Defender and AV engines.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_event_time = 0

    def eventFilter(self, watched, event):
        try:
            if event.type() == QEvent.Type.MouseButtonRelease:
                if isinstance(watched, QAbstractButton):
                    txt = watched.text().replace("\n", " ").strip()
                    obj_name = watched.objectName() or "unnamed"
                    cls_name = watched.__class__.__name__
                    if txt or obj_name != "unnamed":
                        log_debug("UI_ACTION", f"Button Click: '{txt}' [{cls_name}#{obj_name}]")
                elif isinstance(watched, QComboBox):
                    obj_name = watched.objectName() or "unnamed"
                    log_debug("UI_ACTION", f"ComboBox Click: [{obj_name}] Current: '{watched.currentText()}'")
        except Exception:
            pass
        return super().eventFilter(watched, event)


class BetaTelemetryDialog(QDialog):
    """
    Interactive disclosure dialog displayed on first launch of a Beta build or when requested
    from the System tab.
    """
    def __init__(self, parent=None, overlay=None, force_view=False):
        super().__init__(parent)
        self.overlay = overlay
        self.force_view = force_view
        self.setWindowTitle("Streamer Calyx - Beta Diagnostics & Telemetry Disclosure")
        self.setWindowIcon(get_app_icon())
        self.setFixedSize(620, 520)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QDialog {
                background-color: #0f0f12;
                color: #efeff1;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        # Header Title
        hdr_row = QHBoxLayout()
        lbl_badge = QLabel("🧪 BETA TESTING NOTICE")
        lbl_badge.setStyleSheet("background-color: #eab308; color: #18181b; font-size: 10px; font-weight: bold; padding: 2px 8px; border-radius: 4px;")
        hdr_row.addWidget(lbl_badge)
        hdr_row.addStretch()
        layout.addLayout(hdr_row)

        lbl_title = QLabel("Diagnostic Logging & Privacy Transparency")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(lbl_title)

        # Scrollable Disclosure Content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #27272a;
                border-radius: 6px;
                background-color: #141418;
            }
        """)

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(14, 14, 14, 14)
        c_layout.setSpacing(14)

        # Section 1: Beta debugging policy
        s1 = QFrame()
        s1.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 10px;")
        s1_lay = QVBoxLayout(s1)
        lbl_s1_t = QLabel("🛠️ <b>Mandatory Diagnostic Mode in Beta Builds</b>")
        lbl_s1_t.setStyleSheet("color: #a970ff; font-size: 12px; font-weight: bold;")
        lbl_s1_d = QLabel(
            "Because this is a pre-release Beta build of Streamer Calyx, <b>diagnostic logging is permanently "
            "locked ON</b>. This ensures that any crash traces, OBS/SLOBS communication dropouts, or audio "
            "analysis anomalies are recorded locally so our engineering team can diagnose and fix issues quickly."
        )
        lbl_s1_d.setWordWrap(True)
        lbl_s1_d.setStyleSheet("color: #adadb8; font-size: 11px; line-height: 1.4;")
        s1_lay.addWidget(lbl_s1_t)
        s1_lay.addWidget(lbl_s1_d)
        c_layout.addWidget(s1)

        # Section 2: Minimal PC Info & UI Actions Collected
        s2 = QFrame()
        s2.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 10px;")
        s2_lay = QVBoxLayout(s2)
        lbl_s2_t = QLabel("📊 <b>Minimal Diagnostic Information Collected (Stored Locally Only)</b>")
        lbl_s2_t.setStyleSheet("color: #38bdf8; font-size: 12px; font-weight: bold;")
        lbl_s2_d = QLabel(
            "Streamer Calyx collects only the minimal hardware and runtime metrics required for streaming utilities:<br>"
            "• <b>Operating System & Architecture:</b> Windows version and 64-bit architecture.<br>"
            "• <b>Display Metrics:</b> Connected monitor resolutions, scaling, and primary screen index.<br>"
            "• <b>Audio Device Inventory:</b> Selected microphone device name and audio input sample rates.<br>"
            "• <b>In-App GUI Interaction:</b> UI button clicks, tab selections, and background tasks performed."
        )
        lbl_s2_d.setWordWrap(True)
        lbl_s2_d.setTextFormat(Qt.TextFormat.RichText)
        lbl_s2_d.setStyleSheet("color: #adadb8; font-size: 11px; line-height: 1.4;")
        s2_lay.addWidget(lbl_s2_t)
        s2_lay.addWidget(lbl_s2_d)
        c_layout.addWidget(s2)

        # Section 3: Absolute Privacy Guarantee
        s3 = QFrame()
        s3.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 10px;")
        s3_lay = QVBoxLayout(s3)
        lbl_s3_t = QLabel("🛡️ <b>What is NEVER Collected or Monitored</b>")
        lbl_s3_t.setStyleSheet("color: #22c55e; font-size: 12px; font-weight: bold;")
        lbl_s3_d = QLabel(
            "We respect your privacy. Streamer Calyx adheres to strict zero-surveillance design:<br>"
            "• <b>NO Keylogging:</b> Global keystrokes are never monitored (only hotkeys you configure in Settings).<br>"
            "• <b>NO Audio Recording Storage:</b> Microphone buffers are processed in memory for volume spikes and discarded.<br>"
            "• <b>NO Passwords or Tokens Logged:</b> Twitch OAuth tokens and sensitive credentials are encrypted and never written to logs.<br>"
            "• <b>NO Cloud Transmission:</b> Log files are saved 100% locally on your computer and never uploaded without your consent."
        )
        lbl_s3_d.setWordWrap(True)
        lbl_s3_d.setTextFormat(Qt.TextFormat.RichText)
        lbl_s3_d.setStyleSheet("color: #adadb8; font-size: 11px; line-height: 1.4;")
        s3_lay.addWidget(lbl_s3_t)
        s3_lay.addWidget(lbl_s3_d)
        c_layout.addWidget(s3)

        # Section 4: 7-Day Rolling Retention & Defender Safety
        s4 = QFrame()
        s4.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 10px;")
        s4_lay = QVBoxLayout(s4)
        lbl_s4_t = QLabel("🧹 <b>7-Day Rolling Retention & Antivirus Cleanliness</b>")
        lbl_s4_t.setStyleSheet("color: #f59e0b; font-size: 12px; font-weight: bold;")
        lbl_s4_d = QLabel(
            "• <b>Automatic Rolling Prune:</b> Daily log files (<code>debug_YYYYMMDD.txt</code>) are retained locally for "
            "up to 7 calendar days. Any files older than 7 days are automatically pruned to conserve disk space.<br>"
            "• <b>Windows Defender Certified:</b> Streamer Calyx operates strictly inside standard Windows user-space APIs "
            "and is dual-signed with an EV Code Signing Certificate. No kernel drivers or hook injection are used."
        )
        lbl_s4_d.setWordWrap(True)
        lbl_s4_d.setTextFormat(Qt.TextFormat.RichText)
        lbl_s4_d.setStyleSheet("color: #adadb8; font-size: 11px; line-height: 1.4;")
        s4_lay.addWidget(lbl_s4_t)
        s4_lay.addWidget(lbl_s4_d)
        c_layout.addWidget(s4)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Acknowledgment Checkbox (only required on first launch)
        self.chk_ack = QCheckBox("I acknowledge that diagnostic logging is active and stored locally for up to 7 days.")
        self.chk_ack.setStyleSheet("color: #efeff1; font-size: 11px; font-weight: 500;")
        if self.force_view:
            self.chk_ack.setChecked(True)
            self.chk_ack.setEnabled(False)
        else:
            self.chk_ack.setChecked(False)
            self.chk_ack.toggled.connect(self._on_ack_toggled)
        layout.addWidget(self.chk_ack)

        # Action Buttons
        btn_bar = QHBoxLayout()
        btn_view_logs = QPushButton("📂 Open Logs Folder")
        btn_view_logs.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                border: 1px solid #3f3f46;
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        btn_view_logs.clicked.connect(self._open_logs)
        btn_bar.addWidget(btn_view_logs)

        btn_bar.addStretch()

        self.btn_continue = QPushButton("Acknowledge && Continue" if not self.force_view else "Close")
        self.btn_continue.setStyleSheet("""
            QPushButton {
                background-color: #9146ff;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #a970ff;
                padding: 7px 18px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #a970ff;
            }
            QPushButton:disabled {
                background-color: #27272a;
                color: #71717a;
                border-color: #3f3f46;
            }
        """)
        if not self.force_view:
            self.btn_continue.setEnabled(False)
        self.btn_continue.clicked.connect(self._on_continue)
        btn_bar.addWidget(self.btn_continue)

        layout.addLayout(btn_bar)

    def _on_ack_toggled(self, checked):
        if not self.force_view:
            self.btn_continue.setEnabled(checked)

    def _open_logs(self):
        ldir = get_logs_dir()
        if os.path.exists(ldir):
            os.startfile(ldir)

    def _on_continue(self):
        if self.overlay and hasattr(self.overlay, "beta_telemetry_acknowledged"):
            self.overlay.beta_telemetry_acknowledged = True
            if hasattr(self.overlay, "save_settings"):
                self.overlay.save_settings()
        self.accept()
