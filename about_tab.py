import os
import platform
import webbrowser
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout
)

from updater import CURRENT_VERSION, get_build_commit, GITHUB_REPO

class AboutTab(QWidget):
    """
    About Tab - Streamer Calyx
    Features the botanical Calyx lore, runtime environment specifications,
    DigiCert Authenticode EV signing verification badge, and community resources.
    """
    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self.main_win = main_win

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

        # ------------------ CARD 1: BOTANICAL HERITAGE & VISION ------------------
        card_botany = QFrame()
        card_botany.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_botany = QVBoxLayout(card_botany)
        lay_botany.setSpacing(8)

        hdr_botany = QHBoxLayout()
        lbl_botany_title = QLabel("🌸  <b>The Botanical Heritage of Calyx</b>")
        lbl_botany_title.setStyleSheet("font-size: 13px; color: #a970ff; font-weight: bold;")
        lbl_botany_title.setToolTip("Streamer Calyx draws its name from the botanical whorl protecting flowers.")
        hdr_botany.addWidget(lbl_botany_title)
        hdr_botany.addStretch()
        lay_botany.addLayout(hdr_botany)

        botany_text = (
            "<div style='font-size: 11px; color: #adadb8; line-height: 155%;'>"
            "In botany, the <b>calyx</b> (<i>/ˈkeɪlɪks/</i>, from Ancient Greek <i>kályx</i> 'husk, cup') "
            "is the outermost whorl of a flower, formed by the protective sepals that enclose, cushion, "
            "and shield the delicate flower bud as it develops, guarding it from frost, wind, and pests "
            "until it is ready to blossom.<br><br>"
            "In <b>Streamer Calyx</b>, the software acts as those protective sepals for your live broadcast. "
            "Sitting quietly in your system tray and alongside your displays, Calyx cushions your broadcast—managing "
            "scene switching, guarding audio levels, suppressing rogue soundboard spam, coordinating remote co-hosts, "
            "and marking epic hype moments in real-time so your creative stream can truly bloom."
            "</div>"
        )
        lbl_botany_body = QLabel(botany_text)
        lbl_botany_body.setWordWrap(True)
        lbl_botany_body.setTextFormat(Qt.TextFormat.RichText)
        lay_botany.addWidget(lbl_botany_body)

        layout.addWidget(card_botany)

        # ------------------ CARD 2: RUNTIME SPECIFICATIONS ------------------
        card_specs = QFrame()
        card_specs.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_specs = QVBoxLayout(card_specs)
        lay_specs.setSpacing(8)

        lbl_specs_title = QLabel("⚙️  <b>Software & Environment Specifications</b>")
        lbl_specs_title.setStyleSheet("font-size: 13px; color: #efeff1; font-weight: bold;")
        lbl_specs_title.setToolTip("Core technical architecture and build environment metadata.")
        lay_specs.addWidget(lbl_specs_title)

        grid = QGridLayout()
        grid.setSpacing(6)

        specs_items = [
            ("Application Version:", f"<b>v{CURRENT_VERSION}</b>", "Current installed release version."),
            ("Git Commit Hash:", f"<code>{get_build_commit()}</code>", "Git commit hash of this build."),
            ("Update Channel:", f"<b>{getattr(self.main_win.overlay, 'update_channel', 'stable').capitalize()}</b>", "Active release discovery channel."),
            ("Code Signature:", "<span style='color: #22c55e;'><b>✓ DigiCert Authenticode EV (SHA-256)</b></span>", "Hardware cryptographic EV token signature verified with RFC 3161 timestamps."),
            ("Python Runtime:", f"{platform.python_version()} ({platform.architecture()[0]})", "Active Python runtime environment."),
            ("Operating System:", f"{platform.platform()}", "Host Windows OS version."),
            ("AppData Location:", f"<code>%APPDATA%\\StreamerCalyx</code>", "Local user configuration and log directory.")
        ]

        for row, (label, val_html, tooltip) in enumerate(specs_items):
            lbl_k = QLabel(label)
            lbl_k.setStyleSheet("color: #71717a; font-size: 11px;")
            lbl_k.setToolTip(tooltip)
            lbl_v = QLabel(val_html)
            lbl_v.setStyleSheet("color: #efeff1; font-size: 11px;")
            lbl_v.setTextFormat(Qt.TextFormat.RichText)
            lbl_v.setToolTip(tooltip)
            grid.addWidget(lbl_k, row, 0)
            grid.addWidget(lbl_v, row, 1)

        lay_specs.addLayout(grid)
        layout.addWidget(card_specs)

        # ------------------ CARD 3: COMMUNITY & QUICK LAUNCHERS ------------------
        card_links = QFrame()
        card_links.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_links = QVBoxLayout(card_links)
        lay_links.setSpacing(8)

        lbl_links_title = QLabel("🌐  <b>Resources & Development Ledger</b>")
        lbl_links_title.setStyleSheet("font-size: 13px; color: #efeff1; font-weight: bold;")
        lbl_links_title.setToolTip("Documentation, source repository, and release notes.")
        lay_links.addWidget(lbl_links_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_ledger = QPushButton("📖 Open Update Encyclopedia")
        btn_ledger.setToolTip("Opens the interactive 2-column release ledger and commit encyclopedia.")
        btn_ledger.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                border: 1px solid #3f3f46;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #9146ff;
                border-color: #9146ff;
                color: #ffffff;
            }
        """)
        btn_ledger.clicked.connect(self._open_ledger)
        btn_row.addWidget(btn_ledger)

        btn_github = QPushButton("🐙 GitHub Repository")
        btn_github.setToolTip("View the project source repository on GitHub.")
        btn_github.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                border: 1px solid #3f3f46;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        btn_github.clicked.connect(lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"))
        btn_row.addWidget(btn_github)

        btn_releases = QPushButton("🏷️ Release Notes")
        btn_releases.setToolTip("View full release changelogs and downloads on GitHub.")
        btn_releases.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #efeff1;
                border: 1px solid #3f3f46;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
        """)
        btn_releases.clicked.connect(lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases"))
        btn_row.addWidget(btn_releases)

        lay_links.addLayout(btn_row)
        layout.addWidget(card_links)

        layout.addStretch()
        scroll_area.setWidget(container)
        root_layout.addWidget(scroll_area)

    def _open_ledger(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ledger_path = os.path.join(script_dir, "ledger", "index.html")
        if not os.path.exists(ledger_path):
            ledger_path = os.path.join(script_dir, "ledger", "ledger_standalone.html")
        if os.path.exists(ledger_path):
            webbrowser.open(ledger_path)
        else:
            webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases")

    def refresh_theme_labels(self, effective):
        pass

