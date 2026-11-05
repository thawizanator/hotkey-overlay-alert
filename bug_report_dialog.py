import os
import sys
import urllib.parse
import webbrowser
import platform
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QCheckBox, QGroupBox, QListWidget,
    QMessageBox, QApplication, QFrame
)
from PyQt6.QtGui import QIcon, QGuiApplication

from updater import CURRENT_VERSION, GITHUB_REPO, get_full_version_string, get_build_commit, get_clickable_version_html
from diagnostics import get_system_info, bundle_logs, APP_DIR
import theme_manager


class CollectedInfoDialog(QDialog):
    """Modal dialog presenting the exact diagnostic data that will be included in the report."""
    def __init__(self, parent=None, overlay_app=None):
        super().__init__(parent)
        self.overlay_app = overlay_app
        self.setObjectName("CollectedInfoDialog")
        self.setWindowTitle("Preview Collected Diagnostic Information")
        self.resize(560, 480)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        lbl_header = QLabel("<b>Diagnostic Data Collection Preview</b>")
        lbl_header.setStyleSheet("font-size: 14px;")
        layout.addWidget(lbl_header)

        lbl_sub = QLabel(
            "Below is the exact environment and system configuration data that will be "
            "included with your report. No private passwords, tokens, or personal directory "
            "paths are included."
        )
        lbl_sub.setWordWrap(True)
        layout.addWidget(lbl_sub)

        self.txt_preview = QTextEdit()
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setStyleSheet("font-family: 'Consolas', 'Courier New', monospace; font-size: 11px;")
        layout.addWidget(self.txt_preview)

        # Populate
        self.raw_text = self._format_info()
        self.txt_preview.setPlainText(self.raw_text)

        # Button Row
        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 Copy to Clipboard")
        btn_copy.clicked.connect(self._copy_info)
        btn_layout.addWidget(btn_copy)
        btn_layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setFixedWidth(80)
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

        pref = getattr(self.overlay_app, "theme_preference", "system") if self.overlay_app else "system"
        theme_manager.apply_theme_to_window(self, pref)

    def _format_info(self) -> str:
        info = get_system_info(self.overlay_app)
        lines = []
        for k, v in info.items():
            if isinstance(v, list):
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines)

    def _copy_info(self):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(self.raw_text)
        QMessageBox.information(self, "Copied", "Diagnostic information copied to clipboard.")


class BugReportDialog(QDialog):
    """Comprehensive Bug Report Form with dynamic steps to reproduce, diagnostics preview, and GitHub integration."""
    def __init__(self, parent=None, overlay_app=None):
        super().__init__(parent)
        self.overlay_app = overlay_app
        self.setObjectName("BugReportDialog")
        self.setWindowTitle(f"Submit a Bug Report ({get_full_version_string()})")
        self.resize(560, 680)

        pref = getattr(self.overlay_app, "theme_preference", "system") if self.overlay_app else "system"
        self.effective_theme = theme_manager.get_effective_theme(pref)
        sec_color = theme_manager.get_secondary_text_color(self.effective_theme)
        tert_color = theme_manager.get_tertiary_text_color(self.effective_theme)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(14, 14, 14, 14)

        # Header
        v_link = get_clickable_version_html(color=sec_color, underline=True)
        lbl_title = QLabel(f"<b>🐞 Submit a Bug Report</b> <span style='font-size: 11px; color: {sec_color}; font-weight: normal;'>({v_link})</span>")
        lbl_title.setTextFormat(Qt.TextFormat.RichText)
        lbl_title.setOpenExternalLinks(True)
        lbl_title.setStyleSheet("font-size: 15px;")
        main_layout.addWidget(lbl_title)

        lbl_desc = QLabel(
            "Found an issue? Report it directly to our GitHub repository. "
            "Please provide steps to reproduce so we can resolve it quickly."
        )
        lbl_desc.setStyleSheet(f"color: {sec_color}; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        main_layout.addWidget(lbl_desc)

        # Section 1: Issue Title
        main_layout.addWidget(QLabel("<b>Issue Title:</b> <span style='color: #ef4444;'>*</span>"))
        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText("Brief summary (e.g. Border overlay flickers on secondary monitor)")
        main_layout.addWidget(self.edit_title)

        # Section 2: Problem Description
        main_layout.addWidget(QLabel("<b>Problem Description:</b> <span style='color: #ef4444;'>*</span>"))
        self.edit_desc = QTextEdit()
        self.edit_desc.setPlaceholderText("Explain what happened and what you expected to happen instead...")
        self.edit_desc.setFixedHeight(95)
        main_layout.addWidget(self.edit_desc)

        # Section 3: Steps to Recreate Error
        main_layout.addWidget(QLabel("<b>Steps to Recreate Error:</b>"))
        
        step_input_layout = QHBoxLayout()
        step_input_layout.setSpacing(6)
        self.edit_step = QLineEdit()
        self.edit_step.setPlaceholderText("Type a step and press Enter or 'Add Step'...")
        self.edit_step.returnPressed.connect(self._add_step)
        step_input_layout.addWidget(self.edit_step)

        self.btn_add_step = QPushButton("➕ Add Step")
        self.btn_add_step.clicked.connect(self._add_step)
        step_input_layout.addWidget(self.btn_add_step)
        main_layout.addLayout(step_input_layout)

        # Step List
        self.list_steps = QListWidget()
        self.list_steps.setFixedHeight(110)
        main_layout.addWidget(self.list_steps)

        step_btn_layout = QHBoxLayout()
        step_btn_layout.setSpacing(6)
        self.btn_remove_step = QPushButton("🗑️ Remove Selected Step")
        self.btn_remove_step.clicked.connect(self._remove_step)
        step_btn_layout.addWidget(self.btn_remove_step)

        self.btn_clear_steps = QPushButton("🧹 Clear All Steps")
        self.btn_clear_steps.clicked.connect(self._clear_steps)
        step_btn_layout.addWidget(self.btn_clear_steps)
        step_btn_layout.addStretch()
        main_layout.addLayout(step_btn_layout)

        # Section 4: Diagnostics & Logs Group
        grp_diag = QGroupBox("Diagnostic Inclusions")
        grp_diag_layout = QVBoxLayout(grp_diag)
        grp_diag_layout.setSpacing(8)

        # Row 1: System info checkbox + Preview button
        row_sys = QHBoxLayout()
        self.chk_sys_info = QCheckBox("Include App && System Data (OS, Runtimes, Monitors)")
        self.chk_sys_info.setChecked(True)
        row_sys.addWidget(self.chk_sys_info)
        row_sys.addStretch()

        self.btn_preview_info = QPushButton("👁️ Preview Collected Info")
        self.btn_preview_info.clicked.connect(self._preview_collected_info)
        row_sys.addWidget(self.btn_preview_info)
        grp_diag_layout.addLayout(row_sys)

        # Row 2: Logs bundle checkbox
        self.chk_bundle_logs = QCheckBox("Bundle Application Logs (debug.txt, crash_log.txt, updater_log.txt)")
        self.chk_bundle_logs.setChecked(True)
        grp_diag_layout.addWidget(self.chk_bundle_logs)

        lbl_log_note = QLabel(
            "<i>Note: Sensitive credentials and user paths are automatically sanitized. "
            "A bundle file will be generated and its folder opened so you can drag-and-drop it into the GitHub issue.</i>"
        )
        lbl_log_note.setStyleSheet(f"color: {tert_color}; font-size: 11px;")
        lbl_log_note.setWordWrap(True)
        grp_diag_layout.addWidget(lbl_log_note)

        main_layout.addWidget(grp_diag)

        # Section 5: Action Buttons
        btn_action_layout = QHBoxLayout()
        btn_action_layout.setSpacing(10)

        self.btn_copy_markdown = QPushButton("📋 Copy Report to Clipboard")
        self.btn_copy_markdown.clicked.connect(self._copy_report_only)
        btn_action_layout.addWidget(self.btn_copy_markdown)

        btn_action_layout.addStretch()

        self.btn_submit_github = QPushButton("🚀 Open GitHub && Submit Issue")
        self.btn_submit_github.setObjectName("btn_submit_github")
        self.btn_submit_github.setStyleSheet("""
            QPushButton#btn_submit_github {
                background-color: #9146ff;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #772ce8;
                border-radius: 5px;
                padding: 4px 14px;
                min-height: 22px;
            }
            QPushButton#btn_submit_github:hover {
                background-color: #772ce8;
            }
        """)
        self.btn_submit_github.clicked.connect(self._submit_to_github)
        btn_action_layout.addWidget(self.btn_submit_github)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(75)
        self.btn_cancel.clicked.connect(self.reject)
        btn_action_layout.addWidget(self.btn_cancel)

        main_layout.addLayout(btn_action_layout)

        theme_manager.apply_theme_to_window(self, pref)

    def _add_step(self):
        text = self.edit_step.text().strip()
        if not text:
            return
        count = self.list_steps.count() + 1
        self.list_steps.addItem(f"{count}. {text}")
        self.edit_step.clear()
        self.edit_step.setFocus()

    def _remove_step(self):
        row = self.list_steps.currentRow()
        if row >= 0:
            self.list_steps.takeItem(row)
            self._renumber_steps()

    def _clear_steps(self):
        self.list_steps.clear()

    def _renumber_steps(self):
        """Ensures step numbering remains sequential 1..N after removals."""
        items = []
        for i in range(self.list_steps.count()):
            txt = self.list_steps.item(i).text()
            # strip leading numbers e.g. "3. foo" -> "foo"
            if ". " in txt:
                txt = txt.split(". ", 1)[1]
            items.append(txt)
        self.list_steps.clear()
        for i, itm in enumerate(items, 1):
            self.list_steps.addItem(f"{i}. {itm}")

    def _preview_collected_info(self):
        dlg = CollectedInfoDialog(self, self.overlay_app)
        dlg.exec()

    def _build_markdown_report(self) -> tuple:
        """Constructs (title, full_markdown_body, concise_github_url_body)."""
        title = self.edit_title.text().strip()
        desc = self.edit_desc.toPlainText().strip()

        steps = []
        for i in range(self.list_steps.count()):
            steps.append(self.list_steps.item(i).text())

        # Markdown assembly
        md = []
        md.append(f"### 📝 Problem Description\n{desc}\n")

        md.append("### 🔄 Steps to Reproduce")
        if steps:
            for s in steps:
                md.append(f"- {s}")
        else:
            md.append("- No specific reproduction steps provided.")
        md.append("")

        if self.chk_sys_info.isChecked():
            sys_info = get_system_info(self.overlay_app)
            md.append("### 💻 Environment & Diagnostics")
            md.append("| Property | Value |")
            md.append("| :--- | :--- |")
            for k, v in sys_info.items():
                if k == "Monitors" and isinstance(v, list):
                    md.append(f"| **Monitors** | {', '.join(v)} |")
                else:
                    md.append(f"| **{k}** | {v} |")
            md.append("")

        if self.chk_bundle_logs.isChecked():
            md.append("### 📋 Application Logs")
            md.append("*(Log bundle `bug_report_bundle.txt` generated with sanitized debug, crash, and updater logs. Please attach it if required.)*\n")

        full_body = "\n".join(md)

        # For the URL query string, we limit the length if too large for browser address bar
        url_body = full_body
        if len(url_body) > 3500:
            url_body = full_body[:3400] + "\n\n*(Full report copied to clipboard - press Ctrl+V to paste full details)*"

        return title, full_body, url_body

    def _copy_report_only(self):
        title = self.edit_title.text().strip()
        desc = self.edit_desc.toPlainText().strip()
        if not title:
            QMessageBox.warning(self, "Title Required", "Please enter a brief Issue Title.")
            self.edit_title.setFocus()
            return
        if not desc:
            QMessageBox.warning(self, "Description Required", "Please provide a description of what went wrong.")
            self.edit_desc.setFocus()
            return

        title, full_body, _ = self._build_markdown_report()
        clipboard_content = f"# [BUG] {title}\n\n{full_body}"
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(clipboard_content)

        if self.chk_bundle_logs.isChecked():
            bundle_file, _ = bundle_logs(self.overlay_app)
            self._reveal_file_in_explorer(bundle_file)

        QMessageBox.information(
            self,
            "Report Copied",
            "The bug report markdown has been copied to your clipboard!\n\n"
            + ("The log bundle has also been saved and its folder opened." if self.chk_bundle_logs.isChecked() else "")
        )

    def _reveal_file_in_explorer(self, filepath: str):
        """Opens Windows Explorer with the target file highlighted."""
        if not filepath or not os.path.exists(filepath):
            return
        try:
            subprocess.Popen(f'explorer /select,"{os.path.normpath(filepath)}"')
        except Exception:
            try:
                os.startfile(os.path.dirname(filepath))
            except Exception:
                pass

    def _submit_to_github(self):
        title = self.edit_title.text().strip()
        desc = self.edit_desc.toPlainText().strip()
        if not title:
            QMessageBox.warning(self, "Title Required", "Please enter a brief Issue Title.")
            self.edit_title.setFocus()
            return
        if not desc:
            QMessageBox.warning(self, "Description Required", "Please provide a description of what went wrong.")
            self.edit_desc.setFocus()
            return

        title, full_body, url_body = self._build_markdown_report()

        # Copy to clipboard
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(f"# [BUG] {title}\n\n{full_body}")

        bundle_path = None
        if self.chk_bundle_logs.isChecked():
            bundle_path, _ = bundle_logs(self.overlay_app)
            self._reveal_file_in_explorer(bundle_path)

        # Build GitHub Issue URL
        params = {
            "title": f"[BUG] {title}",
            "body": url_body
        }
        query_str = urllib.parse.urlencode(params)
        issue_url = f"https://github.com/{GITHUB_REPO}/issues/new?{query_str}"

        # Open in browser
        webbrowser.open(issue_url)

        msg = (
            "<b>GitHub Issue Prepared!</b><br><br>"
            "1. <b>Browser Opened:</b> Your default browser has opened to the GitHub Issue submission page.<br>"
            "2. <b>Clipboard:</b> The complete report markdown has been copied to your clipboard (press <code>Ctrl+V</code> if needed).<br>"
        )
        if bundle_path:
            msg += (
                "3. <b>Log Bundle:</b> <code>bug_report_bundle.txt</code> was saved and opened in Explorer. "
                "You can drag and drop it directly into the GitHub issue comment box to attach it!<br>"
            )

        QMessageBox.information(self, "Issue Submitted to Browser", msg)
        self.accept()
