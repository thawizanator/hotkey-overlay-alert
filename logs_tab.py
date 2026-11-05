import os
import sys
import subprocess
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QPlainTextEdit, QCheckBox, QApplication
)

from debug_logger import (
    get_logs_dir, get_debug_log_path, get_mirror_log_path,
    get_crash_log_path, get_all_log_files, prune_old_logs, log_debug
)
from audio_diagnostics import AudioDiagnosticsDialog
from bug_report_dialog import BugReportDialog

class LogsTab(QWidget):
    """
    Dedicated Logs & Diagnostics View.
    Allows streamers to view live logs, switch between daily logs, open log folders,
    prune old logs, and launch audio diagnostics or bug reporting.
    """
    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self.main_win = main_win
        self.overlay = getattr(main_win, "overlay", None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # ------------------ TOP CONTROLS ROW ------------------
        ctrl_card = QFrame()
        ctrl_card.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        lay_ctrl = QVBoxLayout(ctrl_card)
        lay_ctrl.setSpacing(6)

        row_sel = QHBoxLayout()
        row_sel.setSpacing(8)
        lbl_sel = QLabel("Active Log File:")
        lbl_sel.setStyleSheet("font-size: 11px; font-weight: bold; color: #efeff1;")
        lbl_sel.setToolTip("Select which daily debug log file to inspect.")
        row_sel.addWidget(lbl_sel)

        self.combo_logs = QComboBox()
        self.combo_logs.setMinimumWidth(200)
        self.combo_logs.setToolTip("Daily log files stored locally in %APPDATA%\\StreamerCalyx\\logs")
        self.combo_logs.currentIndexChanged.connect(self._on_log_file_selected)
        row_sel.addWidget(self.combo_logs, 1)

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setToolTip("Reload the log file contents and scan for new log entries.")
        self.btn_refresh.setStyleSheet("background-color: #27272a; color: #efeff1; border: 1px solid #3f3f46; padding: 4px 10px; border-radius: 4px; font-size: 11px;")
        self.btn_refresh.clicked.connect(self.load_selected_log)
        row_sel.addWidget(self.btn_refresh)

        self.btn_copy = QPushButton("📋 Copy Log")
        self.btn_copy.setToolTip("Copy displayed log contents to clipboard.")
        self.btn_copy.setStyleSheet("background-color: #27272a; color: #efeff1; border: 1px solid #3f3f46; padding: 4px 10px; border-radius: 4px; font-size: 11px;")
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        row_sel.addWidget(self.btn_copy)

        self.chk_autoscroll = QCheckBox("Auto-scroll to bottom")
        self.chk_autoscroll.setChecked(True)
        self.chk_autoscroll.setStyleSheet("font-size: 11px; color: #adadb8;")
        self.chk_autoscroll.setToolTip("Automatically jump to the latest log entries when refreshed.")
        row_sel.addWidget(self.chk_autoscroll)

        lay_ctrl.addLayout(row_sel)
        layout.addWidget(ctrl_card)

        # ------------------ LOG VIEWER PANE ------------------
        self.log_viewer = QPlainTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_viewer.setStyleSheet("""
            QPlainTextEdit {
                background-color: #121214;
                color: #efeff1;
                border: 1px solid #27272a;
                border-radius: 6px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                padding: 6px;
            }
        """)
        layout.addWidget(self.log_viewer, 1)

        # ------------------ BOTTOM ACTIONS BAR ------------------
        act_card = QFrame()
        act_card.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        lay_act = QVBoxLayout(act_card)
        lay_act.setSpacing(6)

        row_btns1 = QHBoxLayout()
        row_btns1.setSpacing(8)

        self.btn_open_folder = QPushButton("📂 Open Logs Folder")
        self.btn_open_folder.setToolTip("Open the local logs directory (%APPDATA%\\StreamerCalyx\\logs) in Windows Explorer.")
        self.btn_open_folder.setStyleSheet("background-color: #27272a; color: #efeff1; border: 1px solid #3f3f46; padding: 5px 12px; border-radius: 4px; font-size: 11px;")
        self.btn_open_folder.clicked.connect(self._open_logs_folder)
        row_btns1.addWidget(self.btn_open_folder)

        self.btn_prune = QPushButton("🧹 Prune Old Logs (>7 Days)")
        self.btn_prune.setToolTip("Manually delete logs older than 7 days to free disk space.")
        self.btn_prune.setStyleSheet("background-color: #27272a; color: #efeff1; border: 1px solid #3f3f46; padding: 5px 12px; border-radius: 4px; font-size: 11px;")
        self.btn_prune.clicked.connect(self._prune_logs_now)
        row_btns1.addWidget(self.btn_prune)
        lay_act.addLayout(row_btns1)

        row_btns1b = QHBoxLayout()
        row_btns1b.setSpacing(8)

        self.btn_open_debug = QPushButton("📄 Open debug.txt")
        self.btn_open_debug.setToolTip("Open active debug mirror in default text editor.")
        self.btn_open_debug.setStyleSheet("background-color: #27272a; color: #efeff1; border: 1px solid #3f3f46; padding: 5px 12px; border-radius: 4px; font-size: 11px;")
        self.btn_open_debug.clicked.connect(self._open_debug_file)
        row_btns1b.addWidget(self.btn_open_debug)

        self.btn_open_crash = QPushButton("💥 Open crash_log.txt")
        self.btn_open_crash.setToolTip("Open crash log file in default text editor.")
        self.btn_open_crash.setStyleSheet("background-color: #27272a; color: #efeff1; border: 1px solid #3f3f46; padding: 5px 12px; border-radius: 4px; font-size: 11px;")
        self.btn_open_crash.clicked.connect(self._open_crash_file)
        row_btns1b.addWidget(self.btn_open_crash)
        lay_act.addLayout(row_btns1b)

        row_btns2 = QHBoxLayout()
        row_btns2.setSpacing(8)

        self.btn_audio_diag = QPushButton("🎤 Run Audio Input Diagnostics...")
        self.btn_audio_diag.setToolTip("Run 5-second acoustic benchmark and WASAPI float device analysis.")
        self.btn_audio_diag.setStyleSheet("background-color: #27272a; color: #38bdf8; border: 1px solid #0284c7; padding: 5px 12px; border-radius: 4px; font-size: 11px; font-weight: bold;")
        self.btn_audio_diag.clicked.connect(self._run_audio_diag)
        row_btns2.addWidget(self.btn_audio_diag)

        self.btn_bug_report = QPushButton("🐞 Submit Bug Report...")
        self.btn_bug_report.setToolTip("Open transparent bug report dialog with sanitized system logs.")
        self.btn_bug_report.setStyleSheet("background-color: #27272a; color: #ef4444; border: 1px solid #dc2626; padding: 5px 12px; border-radius: 4px; font-size: 11px; font-weight: bold;")
        self.btn_bug_report.clicked.connect(self._submit_bug_report)
        row_btns2.addWidget(self.btn_bug_report)
        lay_act.addLayout(row_btns2)

        layout.addWidget(act_card)

        # Initial populate
        self._refresh_file_list()

    def _refresh_file_list(self):
        self.combo_logs.blockSignals(True)
        self.combo_logs.clear()
        files = get_all_log_files()
        active = get_debug_log_path()
        sel_idx = 0

        if files:
            for idx, f in enumerate(files):
                bname = os.path.basename(f)
                prefix = "★ [Today Active] " if f == active else ""
                self.combo_logs.addItem(f"{prefix}{bname}", f)
                if f == active:
                    sel_idx = idx
        else:
            if active and os.path.exists(active):
                self.combo_logs.addItem(os.path.basename(active), active)
            else:
                self.combo_logs.addItem("No logs found", "")

        self.combo_logs.setCurrentIndex(sel_idx)
        self.combo_logs.blockSignals(False)
        self.load_selected_log()

    def _on_log_file_selected(self, index):
        self.load_selected_log()

    def load_selected_log(self):
        fpath = self.combo_logs.currentData()
        if not fpath or not os.path.exists(fpath):
            self.log_viewer.setPlainText("Log file does not exist or has not been created yet.")
            return

        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                tail_lines = lines[-600:]
                content = "".join(tail_lines)
                self.log_viewer.setPlainText(content)

            if self.chk_autoscroll.isChecked():
                scrollbar = self.log_viewer.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
            self.log_viewer.setPlainText(f"Error reading log file: {e}")

    def _copy_to_clipboard(self):
        text = self.log_viewer.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.btn_copy.setText("✓ Copied!")
            QTimer.singleShot(1500, lambda: self.btn_copy.setText("📋 Copy Log"))

    def _open_logs_folder(self):
        ldir = get_logs_dir()
        if ldir and os.path.exists(ldir):
            os.startfile(ldir)
        else:
            appdata = os.environ.get("APPDATA", "")
            sc_dir = os.path.join(appdata, "StreamerCalyx")
            if os.path.exists(sc_dir):
                os.startfile(sc_dir)

    def _open_debug_file(self):
        f = get_mirror_log_path() or get_debug_log_path()
        if f and os.path.exists(f):
            os.startfile(f)

    def _open_crash_file(self):
        f = get_crash_log_path()
        if f and os.path.exists(f):
            os.startfile(f)

    def _prune_logs_now(self):
        prune_old_logs(max_days=7)
        self._refresh_file_list()
        self.btn_prune.setText("✓ Swept!")
        QTimer.singleShot(1500, lambda: self.btn_prune.setText("🧹 Prune Old Logs (>7 Days)"))

    def _run_audio_diag(self):
        dlg = AudioDiagnosticsDialog(self.main_win)
        dlg.exec()

    def _submit_bug_report(self):
        dlg = BugReportDialog(self.main_win)
        dlg.exec()

    def refresh_theme_labels(self, effective):
        pass

