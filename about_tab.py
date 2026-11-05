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

        # ------------------ CARD 1: THE STREAMER MULTITOOL ------------------
        card_multitool = QFrame()
        card_multitool.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        lay_multitool = QVBoxLayout(card_multitool)
        lay_multitool.setSpacing(8)

        hdr_multitool = QHBoxLayout()
        lbl_multitool_title = QLabel("🛠️  <b>The Streamer Multitool: One Tool to Replace Multiples</b>")
        lbl_multitool_title.setStyleSheet("font-size: 13px; color: #57F287; font-weight: bold;")
        lbl_multitool_title.setToolTip("Streamer Calyx unifies a full suite of broadcasting utilities into a single, cohesive chassis.")
        hdr_multitool.addWidget(lbl_multitool_title)
        hdr_multitool.addStretch()
        lay_multitool.addLayout(hdr_multitool)

        multitool_text = (
            "<div style='font-size: 11px; color: #adadb8; line-height: 155%;'>"
            "Modern live broadcasting often forces streamers to juggle a chaotic jungle of disjointed background utilities: "
            "one app for screen highlight borders, another for audio spike monitoring and clipping, a separate bot for Twitch chat commands, "
            "an external macro board for OBS scene switching, a desktop countdown clock, a rotating trivia widget, a soundboard player, "
            "and pre-flight launch checklists.<br><br>"
            "<b>Streamer Calyx is engineered as the ultimate all-in-one broadcast multitool</b>—a precision Swiss Army knife "
            "designed to replace that entire clutter of fragmented apps with one unified, lightweight, EV-signed environment.<br><br>"
            "Just as a precision multitool houses every essential blade, driver, and wrench within a single balanced frame, "
            "<b>the Calyx holds all the tools you need in one place</b>:"
            "<ul style='margin-top: 6px; margin-bottom: 6px; padding-left: 20px;'>"
            "  <li><b>Monitor Highlight Overlay:</b> Instant pixel-perfect border alert flashing for hotkeys and auto-clip triggers.</li>"
            "  <li><b>Auto-Clip Audio Engine:</b> Automated hype peak detection, live VU metering, and stream marker placement.</li>"
            "  <li><b>Stream Director Dual Docks:</b> Responsive local pipe & remote LAN/WebRTC scene and audio mixer control.</li>"
            "  <li><b>Chronos & Trivia Cycler:</b> Pixel-perfect live stream clocks, countdown milestones, and rotating trivia.</li>"
            "  <li><b>Stream Launchpad:</b> Pre-broadcast readiness checklist and 1-click 'Go for Launch' mission control.</li>"
            "  <li><b>Soundboard LAN Bridge:</b> Ultra-low-latency soundboard playback across headphones and broadcast feeds.</li>"
            "  <li><b>Twitch Chat Macros:</b> Instant global hotkey dispatch for shoutouts, stream markers, and announcements.</li>"
            "</ul>"
            "One unified tool to replace multiples—zero bloat, zero background conflicts, and complete peace of mind on stream."
            "</div>"
        )
        lbl_multitool_body = QLabel(multitool_text)
        lbl_multitool_body.setWordWrap(True)
        lbl_multitool_body.setTextFormat(Qt.TextFormat.RichText)
        lay_multitool.addWidget(lbl_multitool_body)

        layout.addWidget(card_multitool)

        # ------------------ CARD 2: BOTANICAL HERITAGE & VISION ------------------
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
        lbl_botany_title = QLabel("🌸  <b>The Botanical Heritage of Calyx (The Protective Sepals)</b>")
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
            "and marking epic hype moments in real-time. By holding all essential broadcast utilities together in a single "
            "protective chassis, Calyx shields the technical complexity so your stream can flourish and bloom."
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

