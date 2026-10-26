import sys
import os
import json
import time
import webbrowser
import urllib.request
import urllib.parse
import urllib.error
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox, QPushButton, QSlider, QColorDialog, 
                             QMessageBox, QLineEdit, QTabWidget, QCheckBox, 
                             QGroupBox, QProgressBar, QDialog, QButtonGroup, 
                             QStackedWidget, QFrame)
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QKeySequence, QShortcut
from http.server import BaseHTTPRequestHandler, HTTPServer

from updater import (UpdateCheckWorker, DownloadWorker, apply_update_and_restart, 
                     CURRENT_VERSION, BUILD_COMMIT, get_build_commit, get_full_version_string,
                     get_clickable_version_html, get_commit_url,
                     is_newer_version, GITHUB_REPO)
from debug_logger import log_debug, get_crash_log_path, get_debug_log_path
import theme_manager
from bug_report_dialog import BugReportDialog
from chronos_tab import ChronosTab
from cycler_tab import CyclerTab
from director_tab import DirectorTab
from hotkey_tab import HotkeysTab

SPEED_MAPPING = {"Snail": 0.01, "Turtle": 0.02, "Squirrel": 0.04, "Cheetah": 0.08, "Lightning": 0.15, "Always On": 0.00}
TWITCH_COMMANDS = [
    "/marker [username]", 
    "/marker [description]", 
    "/announce [description]", 
    "/announceblue [description]", 
    "/announcegreen [description]", 
    "/announceorange [description]", 
    "/announcepurple [description]", 
    "/shoutout [username]"
]

def fetch_twitch_user_info(token, client_id):
    """
    Validates the token with Twitch and retrieves user ID, login, and display name.
    Returns (login, user_id, display_name) or (None, None, None) on failure.
    """
    try:
        val_url = "https://id.twitch.tv/oauth2/validate"
        req = urllib.request.Request(val_url, headers={"Authorization": f"OAuth {token}"})
        with urllib.request.urlopen(req) as res:
            val_data = json.loads(res.read().decode('utf-8'))
            user_id = val_data.get("user_id")
            login = val_data.get("login")

        display_name = login
        if client_id and login:
            try:
                user_url = f"https://api.twitch.tv/helix/users?login={urllib.parse.quote(login)}"
                user_req = urllib.request.Request(user_url, headers={
                    "Client-ID": client_id,
                    "Authorization": f"Bearer {token}"
                })
                with urllib.request.urlopen(user_req) as u_res:
                    u_data = json.loads(u_res.read().decode('utf-8'))
                    users = u_data.get("data", [])
                    if users:
                        display_name = users[0].get("display_name", login)
            except Exception:
                pass

        return login, user_id, display_name
    except Exception as e:
        log_debug("TWITCH_OAUTH", f"Error validating Twitch token: {e}")
        return None, None, None


class TwitchAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Ignore favicon requests cleanly without interrupting OAuth flow
        if self.path.startswith("/favicon.ico"):
            self.send_response(204)
            self.end_headers()
            return

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # Handle callback when JavaScript forwards the token or error from URL hash
        if parsed.path == "/callback" or "access_token" in params or "token=" in self.path or "error" in params:
            token = None
            if "access_token" in params:
                token = params["access_token"][0]
            elif "token=" in self.path:
                try:
                    token = self.path.split("token=")[1].split("&")[0]
                except Exception:
                    pass

            error_msg = params.get("error_description", params.get("error", [None]))[0]

            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()

            worker = getattr(self.server, "worker", None)

            if token:
                if worker is not None:
                    worker.token_captured = token
                    worker.token_received.emit(token)

                html_response = """
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset='utf-8'>
                    <title>Twitch Linked! - Streamer Calyx</title>
                    <style>
                        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0e0e10; color: #efeff1; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
                        .card { background: #18181b; border: 1px solid #303032; border-radius: 8px; padding: 32px 40px; text-align: center; max-width: 480px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
                        h2 { color: #57F287; margin-top: 0; }
                        p { color: #adadb8; line-height: 1.5; font-size: 15px; }
                    </style>
                </head>
                <body>
                    <div class='card'>
                        <h2>Account Connected Successfully!</h2>
                        <p>Your Twitch account has been authenticated with Streamer Calyx.</p>
                        <p>You can now close this tab and return to the application settings.</p>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html_response.encode('utf-8'))
            else:
                if worker is not None:
                    worker.auth_error.emit(error_msg or "Authentication failed or was cancelled by user.")
                html_response = f"""
                <!DOCTYPE html>
                <html>
                <head><meta charset='utf-8'><title>Error - Streamer Calyx</title>
                <style>body {{ font-family: sans-serif; background: #0e0e10; color: #efeff1; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }} .card {{ background: #18181b; border: 1px solid #ff5555; border-radius: 8px; padding: 32px 40px; text-align: center; max-width: 480px; }} h2 {{ color: #ff5555; }}</style>
                </head>
                <body>
                    <div class='card'>
                        <h2>Authentication Failed</h2>
                        <p>{error_msg or 'Access token was not granted.'}</p>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html_response.encode('utf-8'))
            return

        # Implicit grant sends access_token in URL fragment (#access_token=...)
        # We serve a bridge page containing JavaScript to extract the fragment and redirect
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        bridge_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Authorizing with Twitch...</title>
            <script>
                window.onload = function() {
                    var hash = window.location.hash.substring(1);
                    if (hash) {
                        window.location.href = "/callback?" + hash;
                    } else {
                        var search = window.location.search;
                        if (search) {
                            window.location.href = "/callback" + search;
                        } else {
                            document.getElementById("status").innerText = "Waiting for authorization response...";
                        }
                    }
                };
            </script>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0e0e10; color: #efeff1; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
                .spinner { border: 4px solid #303032; border-top: 4px solid #9146ff; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 16px; }
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                .card { background: #18181b; border: 1px solid #303032; border-radius: 8px; padding: 32px 40px; text-align: center; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="spinner"></div>
                <div id="status">Connecting with Twitch...</div>
            </div>
        </body>
        </html>
        """
        self.wfile.write(bridge_html.encode('utf-8'))

    def log_message(self, format, *args):
        # Suppress routine HTTP access log noise
        pass


class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


class TwitchAuthWorker(QThread):
    token_received = pyqtSignal(str)
    auth_error = pyqtSignal(str)

    def __init__(self, client_id, port=17563, redirect_uri=None):
        super().__init__()
        self.client_id = client_id
        self.port = port
        self.redirect_uri = redirect_uri or f"http://localhost:{self.port}"
        self.running = True
        self.token_captured = None

    def run(self):
        server = None
        try:
            server = ReusableHTTPServer(("", self.port), TwitchAuthHandler)
            server.worker = self
            server.timeout = 0.5

            scopes = "channel:manage:broadcast+moderator:manage:announcements+moderator:manage:shoutouts+user:write:chat+user:read:chat"
            encoded_redirect = urllib.parse.quote(self.redirect_uri, safe="")
            auth_url = f"https://id.twitch.tv/oauth2/authorize?client_id={self.client_id}&redirect_uri={encoded_redirect}&response_type=token&scope={scopes}&force_verify=true"

            webbrowser.open(auth_url)

            start_time = time.time()
            while self.running and not self.token_captured:
                server.handle_request()
                if time.time() - start_time > 120:
                    self.auth_error.emit("Twitch authorization timed out after 2 minutes.")
                    break

            if self.token_captured:
                time.sleep(0.5)
        except Exception as e:
            log_debug("TWITCH_OAUTH", f"TwitchAuthWorker Error: {e}")
            self.auth_error.emit(str(e))
        finally:
            if server:
                try:
                    server.server_close()
                except Exception:
                    pass

    def stop(self):
        self.running = False


# ==============================================================================
# TAB 1: MAIN TAB (Display & Overlay Mode, Primary Hotkey)
# ==============================================================================
class MainTab(QWidget):
    def __init__(self, main_win):
        super().__init__()
        self.main_win = main_win
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        # Group 1: Display & Overlay Mode
        grp_mode = QGroupBox("Display && Overlay Mode")
        lay_mode = QVBoxLayout(grp_mode)
        lay_mode.setSpacing(6)

        self.chk_streamer = QCheckBox("Streamer Mode (In-Game Transparent HUD Overlays)")
        self.chk_streamer.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.chk_streamer.setChecked(getattr(self.main_win.overlay, "streamer_mode", False))
        self.chk_streamer.toggled.connect(self.on_streamer_toggled)
        lay_mode.addWidget(self.chk_streamer)

        self.lbl_mode_desc = QLabel()
        self.lbl_mode_desc.setWordWrap(True)
        self.lbl_mode_desc.setTextFormat(Qt.TextFormat.RichText)
        lay_mode.addWidget(self.lbl_mode_desc)
        layout.addWidget(grp_mode)

        # Group 2: Primary Activation Hotkey
        grp_hk = QGroupBox("Primary Monitor Highlight Hotkey")
        lay_hk = QVBoxLayout(grp_hk)
        lay_hk.setSpacing(8)

        self.chk_enable_primary_hk = QCheckBox("Enable Primary Monitor Highlight Hotkey")
        self.chk_enable_primary_hk.setStyleSheet("font-weight: bold;")
        self.chk_enable_primary_hk.setChecked(getattr(self.main_win.overlay, "primary_hotkey_enabled", False))
        self.chk_enable_primary_hk.toggled.connect(self.on_enable_primary_hk_toggled)
        lay_hk.addWidget(self.chk_enable_primary_hk)

        self.lbl_hotkey = QLabel()
        self.lbl_hotkey.setStyleSheet("font-size: 13px;")
        lay_hk.addWidget(self.lbl_hotkey)

        hk_btn_layout = QHBoxLayout()
        self.btn_change_hk = QPushButton("Change Hotkey")
        self.btn_change_hk.setCheckable(True)
        self.main_win.setup_row_key_catcher(self.btn_change_hk)
        self.btn_change_hk.clicked.connect(self.on_activation_hotkey_btn_clicked)

        self.btn_reset_hk = QPushButton("Reset Default (Ctrl + Add)")
        self.btn_reset_hk.clicked.connect(self.reset_activation_hotkey)

        hk_btn_layout.addWidget(self.btn_change_hk)
        hk_btn_layout.addWidget(self.btn_reset_hk)
        lay_hk.addLayout(hk_btn_layout)
        layout.addWidget(grp_hk)

        layout.addStretch()

        self.lbl_hint = QLabel()
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.lbl_hint)

        self.refresh_theme_labels(theme_manager.get_effective_theme(getattr(self.main_win.overlay, "theme_preference", "system")))
        self.update_activation_hotkey_label()

    def refresh_theme_labels(self, effective):
        sec_color = theme_manager.get_secondary_text_color(effective)
        tert_color = theme_manager.get_tertiary_text_color(effective)
        self.lbl_mode_desc.setText(
            f"<span style='color: {sec_color}; font-size: 12px;'>"
            "• <b>Checked (Streamer Mode):</b> Uses non-intrusive transparent in-game HUD alerts "
            "and auto-fading toasts so game captures and full-screen games are never interrupted.<br>"
            "• <b>Unchecked (Desktop Mode):</b> Uses standard modal window dialogs with title bars "
            "and persistent confirmation popups, designed for channel moderators and desktop users."
            "</span>"
        )
        self.lbl_hint.setText(
            f"<span style='color: {tert_color}; font-size: 11px;'>"
            "💡 Tip: Streamer Calyx runs quietly in your Windows system tray. "
            "Right-click the <b>wizanator icon</b> anytime to reopen settings or exit."
            "</span>"
        )

    def on_streamer_toggled(self, checked):
        if hasattr(self.main_win.overlay, "set_streamer_mode"):
            self.main_win.overlay.set_streamer_mode(checked)
        if hasattr(self.main_win, "tab_director") and self.main_win.tab_director:
            self.main_win.tab_director.set_streamer_mode(checked)

    def on_enable_primary_hk_toggled(self, checked):
        if hasattr(self.main_win.overlay, "set_primary_hotkey_enabled"):
            self.main_win.overlay.set_primary_hotkey_enabled(checked)
        self.update_activation_hotkey_label()

    def update_activation_hotkey_label(self):
        current = getattr(self.main_win.overlay, "activation_hotkey", "ctrl+add")
        enabled = getattr(self.main_win.overlay, "primary_hotkey_enabled", True)
        
        # Check if peripheral manager has a mouse or gamepad binding
        input_mgr = getattr(self.main_win.overlay, "input_manager", None)
        if input_mgr and "primary_overlay" in input_mgr.bindings:
            b_info = input_mgr.bindings["primary_overlay"]
            dev = b_info.get("device", "keyboard")
            b_str = b_info.get("binding", "")
            enabled = b_info.get("enabled", enabled)
            if b_str:
                if dev == "gamepad":
                    formatted = f"🎮 {b_str}"
                elif dev == "mouse":
                    formatted = f"🖱️ {b_str}"
                else:
                    formatted = format_hotkey_display(b_str)
            else:
                formatted = "Not Set"
        else:
            formatted = format_hotkey_display(current)

        if enabled:
            self.lbl_hotkey.setText(f"Active Highlight Hotkey: <b>{formatted}</b>")
        else:
            self.lbl_hotkey.setText(f"Active Highlight Hotkey: <span style='color: #71717a;'><b>{formatted}</b> (Disabled)</span>")
        self.btn_change_hk.setEnabled(enabled)
        self.btn_reset_hk.setEnabled(enabled)

    def on_activation_hotkey_btn_clicked(self):
        btn = self.btn_change_hk
        if btn.isChecked():
            btn._original_text = "Change Hotkey"
            btn._recorded_keys = []
            btn.setText("Press key(s)... (Click to Finish)")
            btn.setStyleSheet("background-color: #3b2d54; color: #ffeb3b; font-weight: bold; padding: 4px; border: 2px solid #9146ff;")
        else:
            btn.setStyleSheet("")
            recorded = getattr(btn, "_recorded_keys", [])
            if recorded:
                new_hk = "+".join(recorded)
                self.main_win.overlay.rebind_activation_hotkey(new_hk)
                self.main_win.overlay.save_settings()
                if hasattr(self.main_win, "tab_hotkeys"):
                    self.main_win.tab_hotkeys.populate_table()
            btn.setText("Change Hotkey")
            btn._recorded_keys = []
            self.update_activation_hotkey_label()

    def reset_activation_hotkey(self):
        self.btn_change_hk.setChecked(False)
        self.btn_change_hk.setStyleSheet("")
        self.btn_change_hk.setText("Change Hotkey")
        self.btn_change_hk._recorded_keys = []
        self.main_win.overlay.rebind_activation_hotkey("ctrl+add")
        self.main_win.overlay.save_settings()
        if hasattr(self.main_win, "tab_hotkeys"):
            self.main_win.tab_hotkeys.populate_table()
        self.update_activation_hotkey_label()


# ==============================================================================
# TAB 2: MONITOR TAB (Monitor selection & identification)
# ==============================================================================
class MonitorTab(QWidget):
    def __init__(self, main_win):
        super().__init__()
        self.main_win = main_win
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        grp_mon = QGroupBox("Target Monitor Selection")
        lay_mon = QVBoxLayout(grp_mon)
        lay_mon.setSpacing(10)

        lay_mon.addWidget(QLabel("Select which display should be highlighted when the alert triggers:"))
        self.monitor_combo = QComboBox()
        self.refresh_monitors()
        self.monitor_combo.currentIndexChanged.connect(self.change_monitor)
        lay_mon.addWidget(self.monitor_combo)

        self.btn_identify = QPushButton("🔍 Identify Displays (Show Numbers On-Screen)")
        self.btn_identify.setStyleSheet("padding: 3px 8px; font-weight: bold;")
        self.btn_identify.clicked.connect(self.main_win.overlay.identify_monitors)
        lay_mon.addWidget(self.btn_identify)

        layout.addWidget(grp_mon)

        self.lbl_info = QLabel()
        self.lbl_info.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        self.update_monitor_info()
        layout.addWidget(self.lbl_info)

        # Group 2: Multi-Monitor DPI & Scaling Behavior
        grp_dpi = QGroupBox("Multi-Monitor DPI && Scaling Behavior")
        lay_dpi = QVBoxLayout(grp_dpi)
        lay_dpi.setSpacing(6)

        dpi_row = QHBoxLayout()
        dpi_row.setSpacing(10)
        dpi_row.addWidget(QLabel("DPI Awareness Mode:"))
        self.combo_dpi = QComboBox()
        self.combo_dpi.addItem("System Aware (Uniform across monitors - No resizing glitch)", "system")
        self.combo_dpi.addItem("Per-Monitor V2 (Per-display crisp scaling - standard Qt)", "per_monitor")
        cur_dpi = getattr(self.main_win.overlay, "dpi_mode", "system")
        idx_dpi = self.combo_dpi.findData(cur_dpi)
        if idx_dpi >= 0:
            self.combo_dpi.setCurrentIndex(idx_dpi)
        self.combo_dpi.currentIndexChanged.connect(self.on_dpi_mode_changed)
        dpi_row.addWidget(self.combo_dpi)
        dpi_row.addStretch()
        lay_dpi.addLayout(dpi_row)

        self.lbl_dpi_desc = QLabel(
            "<b>System Aware (Recommended):</b> Keeps the application window size uniform across displays "
            "and prevents the window from violently resizing or blowing up when straddling monitors with "
            "different DPI scales (e.g. 100% and 175%).<br>"
            "<i>Note: Changing DPI awareness requires restarting the application to take effect.</i>"
        )
        self.lbl_dpi_desc.setWordWrap(True)
        self.lbl_dpi_desc.setTextFormat(Qt.TextFormat.RichText)
        lay_dpi.addWidget(self.lbl_dpi_desc)
        layout.addWidget(grp_dpi)

        layout.addStretch()

    def on_dpi_mode_changed(self, index):
        val = self.combo_dpi.currentData()
        old_val = getattr(self.main_win.overlay, "dpi_mode", "system")
        if val != old_val:
            self.main_win.overlay.dpi_mode = val
            self.main_win.overlay.save_settings()
            QMessageBox.information(
                self,
                "Restart Required",
                "<b>DPI Awareness Setting Saved</b><br><br>"
                "Windows requires the application to restart for new DPI awareness settings to take effect.<br><br>"
                "Please restart Streamer Calyx when convenient."
            )

    def refresh_monitors(self):
        self.monitor_combo.blockSignals(True)
        self.monitor_combo.clear()
        screens = QApplication.screens()
        for i, s in enumerate(screens):
            geom = s.geometry()
            name = s.name() or f"Display #{i+1}"
            self.monitor_combo.addItem(f"Monitor #{i + 1}: {geom.width()}x{geom.height()} ({name})")
        idx = getattr(self.main_win.overlay, "target_monitor_index", 0)
        if idx < len(screens):
            self.monitor_combo.setCurrentIndex(idx)
        self.monitor_combo.blockSignals(False)

    def change_monitor(self, idx):
        if idx >= 0:
            self.main_win.overlay.target_monitor_index = idx
            self.main_win.overlay.update_monitor_geometry(idx)
            self.main_win.overlay.save_settings()
            self.update_monitor_info()

    def refresh_theme_labels(self, effective):
        sec_color = theme_manager.get_secondary_text_color(effective)
        self.lbl_info.setStyleSheet(f"color: {sec_color}; font-size: 12px;")
        if hasattr(self, "lbl_dpi_desc") and self.lbl_dpi_desc:
            self.lbl_dpi_desc.setStyleSheet(f"color: {sec_color}; font-size: 11px;")

    def update_monitor_info(self):
        pref = getattr(self.main_win.overlay, "theme_preference", "system")
        effective = theme_manager.get_effective_theme(pref)
        self.refresh_theme_labels(effective)
        idx = getattr(self.main_win.overlay, "target_monitor_index", 0)
        screens = QApplication.screens()
        if idx < len(screens):
            s = screens[idx]
            g = s.geometry()
            self.lbl_info.setText(f"Active Highlight Target: <b>Monitor #{idx+1}</b> ({g.width()}x{g.height()} at offset {g.x()},{g.y()})")
        else:
            self.lbl_info.setText("Active Highlight Target: Primary Display")


# ==============================================================================
# TAB 3: ALERT OVERLAY TAB (Border Customization, Animation & Speed)
# ==============================================================================
class AlertOverlayTab(QWidget):
    def __init__(self, main_win):
        super().__init__()
        self.main_win = main_win
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # Group 1: Appearance
        grp_app = QGroupBox("Border Highlight Appearance")
        lay_app = QVBoxLayout(grp_app)
        lay_app.setSpacing(8)

        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Highlight Color:"))
        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(45, 24)
        self.btn_color.setStyleSheet(f"background-color: {self.main_win.overlay.border_color.name()}; border: 1px solid black; border-radius: 4px;")
        self.btn_color.clicked.connect(self.pick_color)
        color_layout.addWidget(self.btn_color)
        self.btn_pick_text = QPushButton("Select Color...")
        self.btn_pick_text.clicked.connect(self.pick_color)
        color_layout.addWidget(self.btn_pick_text)
        color_layout.addStretch()
        lay_app.addLayout(color_layout)

        # Thickness slider
        thick_header = QHBoxLayout()
        thick_header.addWidget(QLabel("Border Thickness:"))
        self.lbl_thickness_val = QLabel(f"{self.main_win.overlay.border_thickness} px")
        self.lbl_thickness_val.setStyleSheet("font-weight: bold;")
        thick_header.addWidget(self.lbl_thickness_val)
        thick_header.addStretch()
        lay_app.addLayout(thick_header)

        self.slider_thickness = QSlider(Qt.Orientation.Horizontal)
        self.slider_thickness.setRange(2, 30)
        self.slider_thickness.setValue(self.main_win.overlay.border_thickness)
        self.slider_thickness.valueChanged.connect(self.adjust_thickness)
        lay_app.addWidget(self.slider_thickness)

        # Opacity slider
        opac_header = QHBoxLayout()
        opac_header.addWidget(QLabel("Border Opacity / Transparency:"))
        self.lbl_opacity_val = QLabel(f"{int(self.main_win.overlay.border_opacity * 100)} %")
        self.lbl_opacity_val.setStyleSheet("font-weight: bold;")
        opac_header.addWidget(self.lbl_opacity_val)
        opac_header.addStretch()
        lay_app.addLayout(opac_header)

        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(10, 100)
        self.slider_opacity.setValue(int(self.main_win.overlay.border_opacity * 100))
        self.slider_opacity.valueChanged.connect(self.adjust_opacity)
        lay_app.addWidget(self.slider_opacity)

        layout.addWidget(grp_app)

        # Group 2: Flashing & Effects
        grp_fx = QGroupBox("Breathing && Flashing Effects")
        lay_fx = QVBoxLayout(grp_fx)
        lay_fx.setSpacing(8)

        flash_state = "ON" if self.main_win.overlay.is_flashing else "OFF"
        self.btn_flash = QPushButton(f"Toggle Breathing/Flashing Effect: {flash_state}")
        self.btn_flash.setStyleSheet("font-weight: bold; padding: 3px 8px;")
        self.btn_flash.clicked.connect(self.toggle_flash)
        lay_fx.addWidget(self.btn_flash)

        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Animation Speed:"))
        self.speed_combo = QComboBox()
        for s in SPEED_MAPPING.keys():
            self.speed_combo.addItem(s)
        self.speed_combo.setCurrentText(self.main_win.overlay.flash_speed_name)
        self.speed_combo.currentIndexChanged.connect(self.change_speed)
        speed_layout.addWidget(self.speed_combo)
        lay_fx.addLayout(speed_layout)

        layout.addWidget(grp_fx)
        layout.addStretch()

    def pick_color(self):
        color = QColorDialog.getColor(self.main_win.overlay.border_color, self, "Select Border Color")
        if color.isValid():
            self.main_win.overlay.border_color = color
            self.btn_color.setStyleSheet(f"background-color: {color.name()}; border: 1px solid black; border-radius: 4px;")
            self.main_win.overlay.update()
            self.main_win.overlay.save_settings()

    def adjust_thickness(self, val):
        self.lbl_thickness_val.setText(f"{val} px")
        self.main_win.overlay.border_thickness = val
        self.main_win.overlay.update()
        self.main_win.overlay.save_settings()

    def adjust_opacity(self, val):
        self.lbl_opacity_val.setText(f"{val} %")
        self.main_win.overlay.border_opacity = val / 100.0
        if not self.main_win.overlay.is_flashing or self.main_win.overlay.flash_speed_name == "Always On":
            self.main_win.overlay.setWindowOpacity(self.main_win.overlay.border_opacity)
        self.main_win.overlay.save_settings()

    def toggle_flash(self):
        if self.main_win.overlay.is_flashing:
            self.main_win.overlay.stop_flash()
            self.btn_flash.setText("Toggle Breathing/Flashing Effect: OFF")
        else:
            self.main_win.overlay.start_flash()
            self.btn_flash.setText("Toggle Breathing/Flashing Effect: ON")
        self.main_win.overlay.save_settings()

    def change_speed(self, idx):
        if idx >= 0:
            self.main_win.overlay.update_flash_speed(self.speed_combo.currentText())


# ==============================================================================
# TAB 4: TWITCH TAB (Helix Integration, OAuth, Macro Rows)
# ==============================================================================
class TwitchTab(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_win = main_window
        self.auth_worker = None
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # Group 1: Account
        grp_acc = QGroupBox("Twitch Account Connection")
        lay_acc = QVBoxLayout(grp_acc)
        lay_acc.setSpacing(6)

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("font-size: 13px; padding: 2px;")
        lay_acc.addWidget(self.lbl_status)

        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Broadcaster Channel:"))
        self.txt_channel = QLineEdit()
        self.txt_channel.setFixedWidth(180)
        self.txt_channel.setPlaceholderText("e.g. channel_name")
        self.txt_channel.setText(self.main_win.overlay.twitch_channel)
        self.txt_channel.textChanged.connect(self._on_broadcaster_channel_changed)
        channel_layout.addWidget(self.txt_channel)
        channel_layout.addStretch()
        lay_acc.addLayout(channel_layout)

        btn_box = QHBoxLayout()
        self.btn_login = QPushButton("🔑 Login / Link with Twitch Account")
        self.btn_login.setStyleSheet("background-color: #6441a5; color: white; font-weight: bold; padding: 3px 10px; border-radius: 4px;")
        self.btn_login.clicked.connect(self.start_twitch_oauth)
        btn_box.addWidget(self.btn_login)

        self.btn_unlink = QPushButton("Disconnect")
        self.btn_unlink.setStyleSheet("background-color: #4b4b4e; color: white; padding: 3px 8px; border-radius: 4px;")
        self.btn_unlink.clicked.connect(self.unlink_twitch_account)
        btn_box.addWidget(self.btn_unlink)
        btn_box.addStretch()
        lay_acc.addLayout(btn_box)

        layout.addWidget(grp_acc)

        # Group 2: Macros
        grp_mac = QGroupBox("Custom Twitch Macro Hotkeys (Max 4 Commands)")
        lay_mac = QVBoxLayout(grp_mac)
        lay_mac.setSpacing(6)

        self.entries_layout = QVBoxLayout()
        self.rows = []
        lay_mac.addLayout(self.entries_layout)

        macro_actions_layout = QHBoxLayout()
        self.btn_add = QPushButton("➕ Add Hotkey Entry")
        self.btn_add.clicked.connect(self.add_entry_row)
        macro_actions_layout.addWidget(self.btn_add)

        self.btn_save = QPushButton("💾 Save Twitch Hotkeys")
        self.btn_save.setStyleSheet("background-color: #2e6930; color: white; font-weight: bold; padding: 3px 10px;")
        self.btn_save.clicked.connect(self.save_macros)
        macro_actions_layout.addWidget(self.btn_save)
        macro_actions_layout.addStretch()
        lay_mac.addLayout(macro_actions_layout)

        layout.addWidget(grp_mac)
        layout.addStretch()

        for m in self.main_win.overlay.twitch_macros:
            self.create_row_ui(m["command"], m["hotkey"])

        self.update_connection_ui()

    def _on_broadcaster_channel_changed(self, text):
        self.main_win.overlay.twitch_channel = text.strip()
        self.main_win.overlay.save_settings()

    def update_connection_ui(self):
        token = getattr(self.main_win.overlay, "twitch_token", "")
        login = getattr(self.main_win.overlay, "twitch_login", "")
        display = getattr(self.main_win.overlay, "twitch_display_name", "") or login
        user_id = getattr(self.main_win.overlay, "twitch_user_id", "")

        if token:
            info_text = f"🟢 Connected as: <b>{display}</b>"
            if login and display and login.lower() != display.lower():
                info_text += f" (@{login})"
            if user_id:
                info_text += f" <span style='color: gray;'>(ID: {user_id})</span>"
            self.lbl_status.setText(info_text)
            self.btn_login.setText("🔄 Re-link Account")
            self.btn_login.setStyleSheet("background-color: #2e6930; color: white; font-weight: bold; padding: 3px 10px; border-radius: 4px;")
            self.btn_unlink.setVisible(True)
        else:
            self.lbl_status.setText("⚪ Status: <b>Not Connected</b> (Click below to link Twitch)")
            self.btn_login.setText("🔑 Login / Link with Twitch Account")
            self.btn_login.setStyleSheet("background-color: #6441a5; color: white; font-weight: bold; padding: 3px 10px; border-radius: 4px;")
            self.btn_unlink.setVisible(False)

    def start_twitch_oauth(self):
        self.btn_login.setText("Waiting for browser authorization...")
        self.btn_login.setEnabled(False)
        client_id_str = str(self.main_win.overlay.twitch_client_id).strip()
        redirect_uri_str = getattr(self.main_win.overlay, "twitch_redirect_uri", "http://localhost:17563")

        if self.auth_worker and self.auth_worker.isRunning():
            self.auth_worker.stop()
            self.auth_worker.wait()

        self.auth_worker = TwitchAuthWorker(client_id_str, redirect_uri=redirect_uri_str)
        self.auth_worker.token_received.connect(self.handle_incoming_token)
        self.auth_worker.auth_error.connect(self.handle_auth_error)
        self.auth_worker.start()

    def handle_auth_error(self, err_msg):
        self.btn_login.setEnabled(True)
        self.update_connection_ui()
        QMessageBox.warning(self, "Authorization Notice", f"Twitch linking was not completed:\n\n{err_msg}")

    def handle_incoming_token(self, token):
        self.btn_login.setEnabled(True)
        client_id_str = str(self.main_win.overlay.twitch_client_id).strip()
        login, user_id, display_name = fetch_twitch_user_info(token, client_id_str)

        if not login:
            login = self.txt_channel.text().strip() or getattr(self.main_win.overlay, "twitch_channel", "")
            display_name = login

        self.main_win.overlay.twitch_token = token
        self.main_win.overlay.twitch_login = login or ""
        self.main_win.overlay.twitch_display_name = display_name or login or ""
        if user_id:
            self.main_win.overlay.twitch_user_id = str(user_id)

        # Default broadcaster channel to user's channel if currently blank
        current_broadcaster = self.txt_channel.text().strip() or getattr(self.main_win.overlay, "twitch_channel", "")
        if not current_broadcaster:
            self.main_win.overlay.twitch_channel = login or ""
            self.txt_channel.setText(self.main_win.overlay.twitch_channel)
        else:
            self.main_win.overlay.twitch_channel = current_broadcaster
            self.txt_channel.setText(current_broadcaster)

        self.update_connection_ui()
        self.main_win.overlay.save_settings()

        handle_note = f" (@{login})" if login and display_name and login.lower() != display_name.lower() else ""
        QMessageBox.information(
            self,
            "Success",
            f"Your Twitch account has been linked successfully!\n\n"
            f"Connected as: {self.main_win.overlay.twitch_display_name}{handle_note}\n"
            f"User ID: {self.main_win.overlay.twitch_user_id or 'Auto-detected'}\n"
            f"Broadcaster Channel: {self.main_win.overlay.twitch_channel}\n\n"
            f"Credentials saved."
        )

    def unlink_twitch_account(self):
        confirm = QMessageBox.question(
            self,
            "Unlink Twitch Account",
            "Are you sure you want to disconnect and unlink your Twitch account?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.main_win.overlay.twitch_token = ""
            self.main_win.overlay.twitch_login = ""
            self.main_win.overlay.twitch_display_name = ""
            self.main_win.overlay.twitch_user_id = ""
            self.main_win.overlay.save_settings()
            self.update_connection_ui()
            QMessageBox.information(self, "Disconnected", "Twitch account unlinked successfully.")

    def add_entry_row(self):
        if len(self.rows) >= 4:
            return
        self.create_row_ui("/marker [username]", "set hotkey...")

    def create_row_ui(self, saved_command, saved_hotkey):
        row_widget = QWidget()
        row_lay = QHBoxLayout()
        row_lay.setContentsMargins(0, 2, 0, 2)
        combo = QComboBox()
        for cmd in TWITCH_COMMANDS:
            combo.addItem(cmd)
        if saved_command == "/marker":
            saved_command = "/marker [username]"
        combo.setCurrentText(saved_command)

        btn_hk = QPushButton(saved_hotkey)
        btn_hk.setCheckable(True)
        btn_hk.clicked.connect(lambda checked, b=btn_hk: self.on_hotkey_btn_clicked(b))

        btn_del = QPushButton("Remove")
        row_lay.addWidget(combo)
        row_lay.addWidget(btn_hk)
        row_lay.addWidget(btn_del)
        row_widget.setLayout(row_lay)
        self.entries_layout.addWidget(row_widget)

        r_data = {"widget": row_widget, "combo": combo, "btn_hk": btn_hk}
        self.rows.append(r_data)
        btn_del.clicked.connect(lambda: self.remove_entry_row(r_data))
        self.main_win.setup_row_key_catcher(btn_hk)

    def on_hotkey_btn_clicked(self, btn):
        if btn.isChecked():
            btn._original_text = btn.text()
            btn._recorded_keys = []
            btn.setText("Press key(s)... (Click to Finish)")
            btn.setStyleSheet("background-color: #3b2d54; color: #ffeb3b; font-weight: bold; padding: 4px; border: 2px solid #9146ff;")
        else:
            btn.setStyleSheet("")
            recorded = getattr(btn, "_recorded_keys", [])
            if recorded:
                btn.setText("+".join(recorded))
            else:
                orig = getattr(btn, "_original_text", "set hotkey...")
                if "Click to Finish" in orig or orig in ("Press key(s)...", "set hotkey..."):
                    btn.setText("set hotkey...")
                else:
                    btn.setText(orig)
            btn._recorded_keys = []
            self.save_macros()

    def remove_entry_row(self, r_data):
        try:
            btn_hk = r_data.get("btn_hk")
            if btn_hk:
                btn_hk.removeEventFilter(self.main_win)
            w = r_data.get("widget")
            if w:
                self.entries_layout.removeWidget(w)
                w.deleteLater()
            if r_data in self.rows:
                self.rows.remove(r_data)
            self.save_macros()
        except Exception as e:
            log_debug("ERROR", f"Error in remove_entry_row: {e}")

    def save_macros(self):
        self.main_win.overlay.twitch_channel = self.txt_channel.text().strip()
        def clean_hk(txt):
            t = txt.replace(" (Click to Finish)", "").strip()
            if t in ("set hotkey...", "Press key(s)...", "Press Key..."):
                return ""
            return t

        p_macros = [
            {"command": r["combo"].currentText(), "hotkey": normalize_hotkey(clean_hk(r["btn_hk"].text()))}
            for r in self.rows
            if normalize_hotkey(clean_hk(r["btn_hk"].text()))
        ]
        self.main_win.overlay.twitch_macros = p_macros
        self.main_win.overlay.save_settings()
        self.main_win.overlay.rebind_twitch_macros()


# ==============================================================================
# TAB 5: SYSTEM TAB (Update checker, Auto-updater, Logs & Diagnostics)
# ==============================================================================
class SystemTab(QWidget):
    def __init__(self, main_win):
        super().__init__()
        self.main_win = main_win
        self.check_worker = None
        self.download_worker = None
        self.latest_tag = None
        self.latest_download_url = None
        self.latest_release_url = None

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 8, 12, 8)

        # Group 1: Software Updates
        grp_upd = QGroupBox("Application Updates")
        lay_upd = QVBoxLayout(grp_upd)
        lay_upd.setSpacing(5)

        status_box = QHBoxLayout()
        self.lbl_cur_ver = QLabel(f"Installed Version: <b>v{CURRENT_VERSION}</b> <span style='color: #a1a1aa; font-size: 11px;'>(Commit: <code>{get_build_commit()}</code>)</span>")
        self.lbl_cur_ver.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_update_status = QLabel("<span style='color: #a1a1aa;'>Status: Checking...</span>")
        self.lbl_update_status.setTextFormat(Qt.TextFormat.RichText)
        status_box.addWidget(self.lbl_cur_ver)
        status_box.addSpacing(14)
        status_box.addWidget(self.lbl_update_status)
        status_box.addStretch()
        lay_upd.addLayout(status_box)

        btn_upd_box = QHBoxLayout()
        btn_upd_box.setSpacing(10)
        self.btn_check_update = QPushButton("🔄 Check for Updates Now")
        self.btn_check_update.clicked.connect(self.check_updates_clicked)
        btn_upd_box.addWidget(self.btn_check_update)

        self.btn_view_release = QPushButton("View on GitHub")
        self.btn_view_release.clicked.connect(lambda: webbrowser.open(self.latest_release_url or f"https://github.com/{GITHUB_REPO}/releases"))
        btn_upd_box.addWidget(self.btn_view_release)
        lay_upd.addLayout(btn_upd_box)

        # Prominent Download & Install Update Button (shown when update is available)
        self.btn_download_update = QPushButton("🚀 Download && Install Update")
        self.btn_download_update.setObjectName("btn_download_update")
        self.btn_download_update.setStyleSheet("""
            QPushButton#btn_download_update {
                background-color: #2e6930;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #3d8b40;
                border-radius: 5px;
                min-height: 22px;
                padding: 4px 12px;
            }
            QPushButton#btn_download_update:hover {
                background-color: #38843a;
            }
            QPushButton#btn_download_update:disabled {
                background-color: #202022;
                color: #636366;
                border: 1px solid #2c2c2e;
            }
        """)
        self.btn_download_update.setVisible(False)
        self.btn_download_update.clicked.connect(self.download_update_clicked)
        lay_upd.addWidget(self.btn_download_update)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #303032; border-radius: 4px; text-align: center; height: 18px; }
            QProgressBar::chunk { background-color: #9146ff; border-radius: 3px; }
        """)
        lay_upd.addWidget(self.progress_bar)

        # Update Channel Selection
        chan_row = QHBoxLayout()
        chan_row.setSpacing(10)
        chan_row.addWidget(QLabel("Update Channel:"))
        self.combo_channel = QComboBox()
        self.combo_channel.addItem("Stable (Recommended)", "stable")
        self.combo_channel.addItem("Beta / Early Access (v3.0 Preview)", "beta")
        cur_chan = getattr(self.main_win.overlay, "update_channel", "stable")
        idx_chan = self.combo_channel.findData(cur_chan)
        if idx_chan >= 0:
            self.combo_channel.setCurrentIndex(idx_chan)
        self.combo_channel.currentIndexChanged.connect(self.on_channel_selection_changed)
        chan_row.addWidget(self.combo_channel)

        self.lbl_channel_note = QLabel()
        self._update_channel_description(cur_chan)
        chan_row.addWidget(self.lbl_channel_note)
        chan_row.addStretch()
        lay_upd.addLayout(chan_row)

        # Checkboxes
        self.chk_check_startup = QCheckBox("Check for updates automatically on startup")
        self.chk_check_startup.setChecked(getattr(self.main_win.overlay, "check_updates_on_startup", True))
        self.chk_check_startup.toggled.connect(self.on_check_startup_toggled)
        lay_upd.addWidget(self.chk_check_startup)

        self.chk_auto_download = QCheckBox("Automatically download and apply updates when available")
        self.chk_auto_download.setChecked(getattr(self.main_win.overlay, "auto_update_enabled", False))
        self.chk_auto_download.toggled.connect(self.on_auto_download_toggled)
        lay_upd.addWidget(self.chk_auto_download)

        self.chk_start_on_boot = QCheckBox("Start application automatically on Windows startup")
        self.chk_start_on_boot.setChecked(getattr(self.main_win.overlay, "start_on_boot", False))
        self.chk_start_on_boot.toggled.connect(self.on_start_on_boot_toggled)
        lay_upd.addWidget(self.chk_start_on_boot)

        layout.addWidget(grp_upd)

        # Group 2: Appearance & Theme
        grp_theme = QGroupBox("Interface Appearance && Theme")
        lay_theme = QVBoxLayout(grp_theme)
        lay_theme.setSpacing(5)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(10)
        theme_row.addWidget(QLabel("Interface Theme:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItem("Auto (Match Windows Theme)", "system")
        self.combo_theme.addItem("Dark Theme", "dark")
        self.combo_theme.addItem("Light Theme", "light")

        cur_pref = getattr(self.main_win.overlay, "theme_preference", "system")
        idx = self.combo_theme.findData(cur_pref)
        if idx >= 0:
            self.combo_theme.setCurrentIndex(idx)
        self.combo_theme.currentIndexChanged.connect(self.on_theme_selection_changed)
        theme_row.addWidget(self.combo_theme)

        self.lbl_theme_info = QLabel()
        theme_row.addWidget(self.lbl_theme_info)
        theme_row.addStretch()
        lay_theme.addLayout(theme_row)
        layout.addWidget(grp_theme)

        # Group 3: Diagnostics & Troubleshooting
        grp_diag = QGroupBox("Diagnostics && Logs")
        lay_diag = QVBoxLayout(grp_diag)
        lay_diag.setSpacing(5)

        self.chk_debug = QCheckBox("Enable Debug Logging")
        self.chk_debug.setChecked(getattr(self.main_win.overlay, "debug_mode", False))
        self.chk_debug.toggled.connect(self.on_debug_toggled)
        lay_diag.addWidget(self.chk_debug)

        diag_btns = QHBoxLayout()
        self.btn_open_debug = QPushButton("Open debug.txt")
        self.btn_open_debug.clicked.connect(self.open_debug_log)
        diag_btns.addWidget(self.btn_open_debug)

        self.btn_open_crash = QPushButton("Open crash_log.txt")
        self.btn_open_crash.clicked.connect(self.open_crash_log)
        diag_btns.addWidget(self.btn_open_crash)

        self.btn_open_appdata = QPushButton("Open App Folder")
        self.btn_open_appdata.clicked.connect(self.open_appdata_folder)
        diag_btns.addWidget(self.btn_open_appdata)
        lay_diag.addLayout(diag_btns)

        self.btn_bug_report = QPushButton("🐞 Submit Bug Report...")
        self.btn_bug_report.setObjectName("btn_bug_report")
        self.btn_bug_report.clicked.connect(self.open_bug_report_dialog)
        lay_diag.addWidget(self.btn_bug_report)

        layout.addWidget(grp_diag)

        # Group 4: About
        grp_about = QGroupBox("About Application")
        lay_about = QVBoxLayout(grp_about)
        lay_about.setSpacing(4)
        self.lbl_about_txt = QLabel()
        self.lbl_about_txt.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_about_txt.setOpenExternalLinks(True)
        lay_about.addWidget(self.lbl_about_txt)
        layout.addWidget(grp_about)

        layout.addStretch()

        self.refresh_theme_labels(theme_manager.get_effective_theme(getattr(self.main_win.overlay, "theme_preference", "system")))

        # Trigger passive update check on tab creation
        self.check_updates_silently()

    def on_theme_selection_changed(self, idx):
        val = self.combo_theme.currentData()
        self.main_win.overlay.theme_preference = val
        self.main_win.overlay.save_settings()
        self.main_win.refresh_theme()

    def on_channel_selection_changed(self, idx):
        val = self.combo_channel.currentData()
        self.main_win.overlay.update_channel = val
        self.main_win.overlay.save_settings()
        self._update_channel_description(val)
        self.main_win.refresh_theme()
        chan_title = "Beta / Early Access" if val == "beta" else "Stable"
        self.lbl_update_status.setText(f"<span style='color: #eab308;'>Switched to <b>{chan_title}</b> • Checking GitHub...</span>")
        self.check_updates_silently()

    def _update_channel_description(self, chan):
        if not hasattr(self, "lbl_channel_note") or not self.lbl_channel_note:
            return
        if chan == "beta":
            self.lbl_channel_note.setText(
                "<span style='color: #eab308; font-size: 11px;'>● Preview builds & v3.0 features</span>"
            )
        else:
            self.lbl_channel_note.setText(
                "<span style='color: #71717a; font-size: 11px;'>● Official milestone releases</span>"
            )

    def open_bug_report_dialog(self):
        dlg = BugReportDialog(self, self.main_win.overlay)
        dlg.exec()

    def refresh_theme_labels(self, effective):
        sec_color = theme_manager.get_secondary_text_color(effective)
        tert_color = theme_manager.get_tertiary_text_color(effective)
        active_os = theme_manager.detect_system_theme().capitalize()
        pref = getattr(self.main_win.overlay, "theme_preference", "system")
        if pref == "system":
            self.lbl_theme_info.setText(f"<span style='color: {sec_color}; font-size: 11px;'>● Matching Windows (<b>{active_os} Mode</b>)</span>")
        elif pref == "dark":
            self.lbl_theme_info.setText(f"<span style='color: {sec_color}; font-size: 11px;'>● <b>Dark Theme</b></span>")
        else:
            self.lbl_theme_info.setText(f"<span style='color: {sec_color}; font-size: 11px;'>● <b>Light Theme</b></span>")

        if hasattr(self, "btn_bug_report"):
            if effective == "light":
                self.btn_bug_report.setStyleSheet("""
                    QPushButton#btn_bug_report {
                        background-color: #f3e8ff;
                        color: #6b21a8;
                        border: 1px solid #c084fc;
                        border-radius: 5px;
                        font-weight: 600;
                        padding: 4px 12px;
                        min-height: 20px;
                    }
                    QPushButton#btn_bug_report:hover {
                        background-color: #e9d5ff;
                    }
                """)
            else:
                self.btn_bug_report.setStyleSheet("""
                    QPushButton#btn_bug_report {
                        background-color: #2b1f40;
                        color: #e9d5ff;
                        border: 1px solid #7c3aed;
                        border-radius: 5px;
                        font-weight: 600;
                        padding: 4px 12px;
                        min-height: 20px;
                    }
                    QPushButton#btn_bug_report:hover {
                        background-color: #3b2d54;
                    }
                """)

        self.lbl_about_txt.setText(
            f"<b>Streamer Calyx</b> – Version {CURRENT_VERSION} <span style='font-weight: normal; color: {tert_color};'>(Commit: <code>{get_build_commit()}</code>)</span><br>"
            "Created by <b>ThaWizanator</b> • <a href='https://twitch.tv/thawizanator' style='color: #9146ff;'>twitch.tv/thawizanator</a><br>"
            f"<span style='color: {tert_color};'>Licensed under the MIT License • Standalone Authenticode Signed</span>"
        )

    def check_updates_silently(self):
        chan = getattr(self.main_win.overlay, "update_channel", "stable")
        self.check_worker = UpdateCheckWorker(CURRENT_VERSION, channel=chan)
        self.check_worker.update_available.connect(self.on_update_found)
        self.check_worker.up_to_date.connect(self.on_up_to_date)
        self.check_worker.check_error.connect(self.on_check_error)
        self.check_worker.start()

    def check_updates_clicked(self):
        self.btn_check_update.setEnabled(False)
        chan = getattr(self.main_win.overlay, "update_channel", "stable")
        chan_title = "Beta / Early Access" if chan == "beta" else "Stable"
        self.lbl_update_status.setText(f"<span style='color: #a1a1aa;'>Checking GitHub releases ({chan_title})...</span>")
        self.check_worker = UpdateCheckWorker(CURRENT_VERSION, channel=chan)
        self.check_worker.update_available.connect(self.on_update_found_interactive)
        self.check_worker.up_to_date.connect(self.on_up_to_date_interactive)
        self.check_worker.check_error.connect(self.on_check_error_interactive)
        self.check_worker.start()

    def on_update_found(self, latest_tag, release_url, download_url, notes):
        self.latest_tag = latest_tag
        self.latest_download_url = download_url
        self.latest_release_url = release_url
        self.lbl_update_status.setText(f"<span style='color: #57F287; font-weight: bold;'>🎉 Update Available: {latest_tag}!</span>")
        if download_url:
            self.btn_download_update.setText(f"🚀 Download && Install Update ({latest_tag})")
            self.btn_download_update.setVisible(True)
            self.btn_download_update.setEnabled(True)

    def on_up_to_date(self, current_ver, latest_tag=""):
        chan = getattr(self.main_win.overlay, "update_channel", "stable")
        cur_v_str = f"v{current_ver}" if not str(current_ver).startswith("v") else str(current_ver)
        latest_str = f"v{latest_tag}" if (latest_tag and not str(latest_tag).startswith("v")) else str(latest_tag)

        if chan == "beta":
            disp = latest_str or cur_v_str
            self.lbl_update_status.setText(f"<span style='color: #eab308; font-weight: bold;'>✔️ Up to date on Beta ({disp})</span>")
        else:
            # Stable channel
            is_preview = any(k in cur_v_str.lower() for k in ["beta", "rc", "alpha", "dev"])
            if is_preview:
                if latest_str:
                    self.lbl_update_status.setText(
                        f"<span style='color: #43b581; font-weight: bold;'>✔️ Latest Stable: {latest_str}</span> "
                        f"<span style='color: #a1a1aa; font-size: 11px;'>(Installed: {cur_v_str})</span>"
                    )
                else:
                    self.lbl_update_status.setText(
                        f"<span style='color: #43b581; font-weight: bold;'>✔️ Up to date on Stable</span> "
                        f"<span style='color: #a1a1aa; font-size: 11px;'>(Installed: {cur_v_str})</span>"
                    )
            else:
                disp = latest_str or cur_v_str
                self.lbl_update_status.setText(f"<span style='color: #43b581; font-weight: bold;'>✔️ Up to date on Stable ({disp})</span>")
        self.btn_download_update.setVisible(False)
        self.btn_download_update.setEnabled(False)

    def on_check_error(self, err_str):
        self.lbl_update_status.setText("<span style='color: #a1a1aa;'>Could not connect to update server</span>")
        self.btn_download_update.setVisible(False)
        self.btn_download_update.setEnabled(False)

    def on_update_found_interactive(self, latest_tag, release_url, download_url, notes):
        self.btn_check_update.setEnabled(True)
        self.on_update_found(latest_tag, release_url, download_url, notes)
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Available")
        msg.setWindowIcon(get_app_icon())
        theme_manager.apply_theme_to_window(msg, getattr(self.main_win.overlay, "theme_preference", "system"))
        msg.setText(
            f"<b>A new version of Streamer Calyx is available!</b><br><br>"
            f"Current version: <b>{get_full_version_string()}</b><br>"
            f"Latest version: <b>{latest_tag}</b><br><br>"
            f"Would you like to download and install this update now?"
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        btn_yes = msg.addButton("Download Now", QMessageBox.ButtonRole.AcceptRole)
        btn_no = msg.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_yes)
        msg.exec()
        if msg.clickedButton() == btn_yes and download_url:
            self.download_update_clicked()

    def on_up_to_date_interactive(self, current_ver, latest_tag=""):
        self.btn_check_update.setEnabled(True)
        self.on_up_to_date(current_ver, latest_tag)
        chan = getattr(self.main_win.overlay, "update_channel", "stable")
        chan_title = "Beta / Early Access" if chan == "beta" else "Stable"
        cur_v_str = f"v{current_ver}" if not str(current_ver).startswith("v") else str(current_ver)
        latest_str = f"v{latest_tag}" if (latest_tag and not str(latest_tag).startswith("v")) else str(latest_tag)

        msg = QMessageBox(self)
        msg.setWindowTitle("Update Check Complete")
        msg.setWindowIcon(get_app_icon())
        theme_manager.apply_theme_to_window(msg, getattr(self.main_win.overlay, "theme_preference", "system"))

        details_html = f"• <b>Active Channel:</b> {chan_title}<br>"
        if latest_str:
            details_html += f"• <b>Latest Release on {chan_title}:</b> <b>{latest_str}</b><br>"
        details_html += f"• <b>Installed Version:</b> {get_clickable_version_html()}<br><br>"

        is_preview = any(k in cur_v_str.lower() for k in ["beta", "rc", "alpha", "dev"])
        if chan != "beta" and is_preview:
            note_html = f"<i>You are currently running a preview build ({cur_v_str}). The latest release on the official stable channel is <b>{latest_str or 'v2.5.2'}</b>. There are no newer stable releases.</i>"
        else:
            note_html = f"<i>Successfully connected to GitHub releases. There are currently no newer releases available on the {chan_title.lower()} channel.</i>"

        msg.setText(
            f"<b>Streamer Calyx is up to date!</b><br><br>"
            f"{details_html}"
            f"{note_html}"
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def on_check_error_interactive(self, err_str):
        self.btn_check_update.setEnabled(True)
        self.on_check_error(err_str)
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Check Error")
        msg.setWindowIcon(get_app_icon())
        theme_manager.apply_theme_to_window(msg, getattr(self.main_win.overlay, "theme_preference", "system"))
        msg.setText(f"<b>Unable to check for updates:</b><br><br>{err_str}")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def download_update_clicked(self):
        if not self.latest_download_url:
            if self.latest_release_url:
                webbrowser.open(self.latest_release_url)
            return

        app_dir = getattr(self.main_win.overlay, "app_dir", None) or os.path.dirname(os.path.abspath(__file__))
        temp_exe = os.path.join(app_dir, f"StreamerCalyx_new_{self.latest_tag}.exe")

        self.btn_download_update.setEnabled(False)
        self.btn_check_update.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        self.download_worker = DownloadWorker(self.latest_download_url, temp_exe)
        self.download_worker.progress.connect(self.progress_bar.setValue)
        self.download_worker.finished.connect(self.on_download_finished)
        self.download_worker.error.connect(self.on_download_error)
        self.download_worker.start()

    def on_download_finished(self, downloaded_path):
        self.progress_bar.setVisible(False)
        self.btn_download_update.setEnabled(True)
        self.btn_check_update.setEnabled(True)

        res = QMessageBox.question(
            self,
            "Update Ready",
            f"<b>Update downloaded successfully!</b><br><br>"
            f"The application needs to restart to apply <b>{self.latest_tag}</b>.<br><br>"
            f"Restart now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            ok, msg = apply_update_and_restart(downloaded_path)
            if ok:
                if hasattr(self.main_win.overlay, "close_application"):
                    self.main_win.overlay.close_application()
                else:
                    QApplication.quit()
            else:
                QMessageBox.information(
                    self, 
                    "Update Note", 
                    f"{msg}\n\nDownloaded update saved to:\n{downloaded_path}"
                )

    def on_download_error(self, err_str):
        self.progress_bar.setVisible(False)
        self.btn_download_update.setEnabled(True)
        self.btn_check_update.setEnabled(True)
        QMessageBox.critical(self, "Download Failed", f"Failed to download update:\n\n{err_str}")

    def on_check_startup_toggled(self, checked):
        if hasattr(self.main_win.overlay, "set_update_settings"):
            self.main_win.overlay.set_update_settings(check_on_startup=checked)

    def on_auto_download_toggled(self, checked):
        if hasattr(self.main_win.overlay, "set_update_settings"):
            self.main_win.overlay.set_update_settings(auto_update=checked)

    def on_start_on_boot_toggled(self, checked):
        if hasattr(self.main_win.overlay, "set_start_on_boot"):
            self.main_win.overlay.set_start_on_boot(checked)

    def on_debug_toggled(self, checked):
        if hasattr(self.main_win.overlay, "set_debug_mode"):
            self.main_win.overlay.set_debug_mode(checked)

    def open_debug_log(self):
        if hasattr(self.main_win.overlay, "open_debug_log"):
            self.main_win.overlay.open_debug_log()

    def open_crash_log(self):
        if hasattr(self.main_win.overlay, "open_crash_log"):
            self.main_win.overlay.open_crash_log()

    def open_appdata_folder(self):
        try:
            from main import APP_DIR
            os.startfile(APP_DIR)
        except Exception:
            try:
                os.startfile(os.path.dirname(os.path.abspath(__file__)))
            except Exception:
                pass


# ==============================================================================
# ==============================================================================
# MAIN SETTINGS CONTAINER (Modern Left Sidebar Layout - v3.0 Architecture)
# ==============================================================================

class TabsAdapter:
    """Compatibility adapter emulating QTabWidget interface for external callers."""
    def __init__(self, win):
        self.win = win

    def setCurrentIndex(self, idx):
        self.win.set_view_index(idx)

    def currentIndex(self):
        return self.win.stacked_pages.currentIndex()

    def count(self):
        return self.win.stacked_pages.count()

    def currentWidget(self):
        return self.win.stacked_pages.currentWidget()

    def widget(self, idx):
        return self.win.stacked_pages.widget(idx)

    def setStyleSheet(self, style):
        pass


PAGE_TITLES = {
    0: "🏠  Main Overlay & Streaming Mode",
    1: "🖥️  Multi-Monitor Configuration",
    2: "🎨  Alert Overlay Styles & Effects",
    3: "🟣  Twitch Channel & Macro Hotkeys",
    4: "⚙️  System, Updates & Diagnostics",
    5: "⏱️  Chronos Live Stream Timers",
    6: "📜  Rotating Text & Trivia Cycler",
    7: "🎬  Stream Director Panel",
    8: "🎮  Unified Hotkeys & Peripherals"
}


class SettingsWindow(QWidget):
    def __init__(self, overlay_app):
        super().__init__()
        self.overlay = overlay_app
        self.setObjectName("SettingsWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(f"Streamer Calyx - Streamer Hub ({get_full_version_string()})")
        self.is_sidebar_collapsed = getattr(self.overlay, "sidebar_collapsed", False)
        init_width = 570 if self.is_sidebar_collapsed else 780
        self.setFixedSize(init_width, 600)
        self.setWindowIcon(get_app_icon())

        # Root Horizontal Layout (Sidebar + Content Area)
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ------------------ LEFT SIDEBAR ------------------
        self.sidebar_widget = QWidget()
        self.sidebar_widget.setObjectName("sidebarContainer")
        self.sidebar_widget.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_layout.setContentsMargins(12, 14, 12, 14)
        sidebar_layout.setSpacing(4)

        # App Brand Header
        lbl_brand = QLabel("<b>Streamer Calyx</b>")
        lbl_brand.setObjectName("sidebarBrand")
        lbl_sub = QLabel("Streamer Control Hub")
        lbl_sub.setObjectName("sidebarSub")
        sidebar_layout.addWidget(lbl_brand)
        sidebar_layout.addWidget(lbl_sub)
        sidebar_layout.addSpacing(6)

        # Exclusive navigation button group
        self.nav_button_group = QButtonGroup(self)
        self.nav_button_group.setExclusive(True)

        # Category 1: DISPLAY & ALERTS
        lbl_cat_display = QLabel("DISPLAY & ALERTS")
        lbl_cat_display.setObjectName("navCatLabel")
        sidebar_layout.addWidget(lbl_cat_display)

        self.btn_nav_main = self._create_nav_btn("🏠  Main Overlay", 0)
        self.btn_nav_monitor = self._create_nav_btn("🖥️  Monitor Setup", 1)
        self.btn_nav_alert = self._create_nav_btn("🎨  Alert Overlay", 2)
        sidebar_layout.addWidget(self.btn_nav_main)
        sidebar_layout.addWidget(self.btn_nav_monitor)
        sidebar_layout.addWidget(self.btn_nav_alert)

        # Category 2: STREAM TOOLS
        lbl_cat_tools = QLabel("STREAM TOOLS")
        lbl_cat_tools.setObjectName("navCatLabel")
        sidebar_layout.addWidget(lbl_cat_tools)

        self.btn_nav_twitch = self._create_nav_btn("🟣  Twitch Macros", 3)
        self.btn_nav_chronos = self._create_nav_btn("⏱️  Chronos Timers", 5)
        self.btn_nav_trivia = self._create_nav_btn("📜  Rotating Text", 6)
        self.btn_nav_director = self._create_nav_btn("🎬  Stream Director", 7)
        sidebar_layout.addWidget(self.btn_nav_twitch)
        sidebar_layout.addWidget(self.btn_nav_chronos)
        sidebar_layout.addWidget(self.btn_nav_trivia)
        sidebar_layout.addWidget(self.btn_nav_director)

        # Category 3: SYSTEM & CONFIG
        lbl_cat_sys = QLabel("APP & CONFIG")
        lbl_cat_sys.setObjectName("navCatLabel")
        sidebar_layout.addWidget(lbl_cat_sys)

        self.btn_nav_hotkeys = self._create_nav_btn("🎮  Hotkeys && Peripherals", 8)
        self.btn_nav_system = self._create_nav_btn("⚙️  System && Logs", 4)
        sidebar_layout.addWidget(self.btn_nav_hotkeys)
        sidebar_layout.addWidget(self.btn_nav_system)

        sidebar_layout.addStretch()

        # Sidebar Footer
        self.lbl_channel_badge = QLabel()
        self.lbl_channel_badge.setStyleSheet("font-size: 11px; font-weight: bold; padding-left: 4px;")
        self.lbl_v = QLabel()
        self.lbl_v.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_v.setOpenExternalLinks(True)
        self.lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.lbl_v.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_v.setStyleSheet("font-size: 10px; padding-left: 4px;")
        sidebar_layout.addWidget(self.lbl_channel_badge)
        sidebar_layout.addWidget(self.lbl_v)

        root_layout.addWidget(self.sidebar_widget)

        # Vertical Divider Frame
        self.divider = QFrame()
        self.divider.setFrameShape(QFrame.Shape.VLine)
        self.divider.setFrameShadow(QFrame.Shadow.Plain)
        self.divider.setObjectName("sidebarDivider")
        root_layout.addWidget(self.divider)

        # ------------------ RIGHT CONTENT AREA ------------------
        self.content_area = QWidget()
        content_layout = QVBoxLayout(self.content_area)
        content_layout.setContentsMargins(16, 14, 16, 12)
        content_layout.setSpacing(8)

        # Section Header Row (Sidebar Toggle + Title / Collapsed Selector)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        self.btn_toggle_sidebar = QPushButton("◀")
        self.btn_toggle_sidebar.setObjectName("btnToggleSidebar")
        self.btn_toggle_sidebar.setToolTip("Toggle sidebar navigation (Ctrl+B)")
        self.btn_toggle_sidebar.setFixedSize(28, 28)
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        header_row.addWidget(self.btn_toggle_sidebar)

        self.lbl_page_title = QLabel("🏠  Main Overlay & Streaming Mode")
        self.lbl_page_title.setObjectName("contentHeaderLabel")
        header_row.addWidget(self.lbl_page_title, 1)

        self.combo_collapsed_nav = QComboBox()
        self.combo_collapsed_nav.setObjectName("comboCollapsedNav")
        self.combo_collapsed_nav.setToolTip("Switch active view")
        for p_idx in sorted(PAGE_TITLES.keys()):
            self.combo_collapsed_nav.addItem(PAGE_TITLES[p_idx], p_idx)
        self.combo_collapsed_nav.currentIndexChanged.connect(self._on_collapsed_nav_changed)
        self.combo_collapsed_nav.setVisible(False)
        header_row.addWidget(self.combo_collapsed_nav)

        content_layout.addLayout(header_row)

        # Stacked Pages
        self.stacked_pages = QStackedWidget()

        # Instantiate 5 core tabs
        self.tab_main = MainTab(self)
        self.tab_monitor = MonitorTab(self)
        self.tab_alert = AlertOverlayTab(self)
        self.tab_twitch = TwitchTab(self)
        self.tab_system = SystemTab(self)

        self.stacked_pages.addWidget(self.tab_main)      # 0
        self.stacked_pages.addWidget(self.tab_monitor)   # 1
        self.stacked_pages.addWidget(self.tab_alert)     # 2
        self.stacked_pages.addWidget(self.tab_twitch)    # 3
        self.stacked_pages.addWidget(self.tab_system)    # 4

        # Initialize Chronos Timing Suite (Phase 2)
        chronos_eng = getattr(self.overlay, "chronos_engine", None)
        if chronos_eng is None:
            from chronos_engine import ChronosEngine
            chronos_eng = ChronosEngine(self)
        self.tab_chronos = ChronosTab(self, chronos_eng)
        self.stacked_pages.addWidget(self.tab_chronos)          # 5

        # Initialize Rotating Text & Trivia Cycler (Phase 3)
        cycler_eng = getattr(self.overlay, "cycler_engine", None)
        if cycler_eng is None:
            from cycler_engine import CyclerEngine
            cycler_eng = CyclerEngine(self)
        self.tab_cycler = CyclerTab(self, cycler_eng)
        self.stacked_pages.addWidget(self.tab_cycler)           # 6

        # Initialize Stream Director (Phase 4)
        self.tab_director = DirectorTab(self)
        self.tab_director.set_streamer_mode(getattr(self.overlay, "streamer_mode", False))
        self.stacked_pages.addWidget(self.tab_director)          # 7

        # Initialize Unified Hotkeys & Peripherals (Phase 5)
        self.tab_hotkeys = HotkeysTab(self)
        self.stacked_pages.addWidget(self.tab_hotkeys)           # 8

        content_layout.addWidget(self.stacked_pages)

        # Bottom Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.setFixedWidth(80)
        self.btn_close.clicked.connect(self.close)
        bottom_bar.addWidget(self.btn_close)
        content_layout.addLayout(bottom_bar)

        root_layout.addWidget(self.content_area)

        # Emulate QTabWidget for external callers
        self.tabs = TabsAdapter(self)

        # Compatibility aliases for other modules
        self.view_visual = self.tab_monitor
        self.view_twitch = self.tab_twitch

        # Connect button group clicks
        self.nav_button_group.buttonClicked.connect(lambda btn: self.set_view_index(self.nav_button_group.id(btn)))

        # Setup shortcut and initial sidebar state
        self.shortcut_sidebar = QShortcut(QKeySequence("Ctrl+B"), self)
        self.shortcut_sidebar.activated.connect(self.toggle_sidebar)
        self._apply_sidebar_state()

        # Apply initial theme
        self.refresh_theme()

    def _create_nav_btn(self, text, idx):
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setProperty("isNav", True)
        btn.setObjectName(f"nav_btn_{idx}")
        self.nav_button_group.addButton(btn, idx)
        return btn

    def _create_preview_page(self, title, description, phase_tag, feature_list):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(12)

        grp = QGroupBox(f"{title} – Preview")
        grp_lay = QVBoxLayout(grp)
        grp_lay.setSpacing(8)

        lbl_badge = QLabel(f"<span style='background-color: #9146ff; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;'>{phase_tag}</span>")
        grp_lay.addWidget(lbl_badge)

        lbl_desc = QLabel(f"<b>{description}</b>")
        lbl_desc.setWordWrap(True)
        grp_lay.addWidget(lbl_desc)

        lbl_feat_hdr = QLabel("<b>Planned Capabilities:</b>")
        grp_lay.addWidget(lbl_feat_hdr)

        for feat in feature_list:
            lbl_f = QLabel(f"  •  {feat}")
            lbl_f.setWordWrap(True)
            grp_lay.addWidget(lbl_f)

        grp_lay.addSpacing(6)
        lbl_tip = QLabel("<i>💡 Want to test this tool before the public release? Switch to the <b>Beta / Early Access</b> channel in System settings to get preview updates as soon as they drop!</i>")
        lbl_tip.setWordWrap(True)
        grp_lay.addWidget(lbl_tip)

        lay.addWidget(grp)
        lay.addStretch()
        return page

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_theme()

    def refresh_theme(self):
        pref = getattr(self.overlay, "theme_preference", "system")
        effective = theme_manager.apply_theme_to_window(self, pref)
        tert = theme_manager.get_tertiary_text_color(effective)
        sec = theme_manager.get_secondary_text_color(effective)
        chan = getattr(self.overlay, "update_channel", "stable")

        v_link = get_clickable_version_html(color=tert, underline=False)
        self.lbl_v.setText(f"{v_link} <span style='color: {tert};'>• ThaWizanator</span>")
        if chan == "beta":
            self.lbl_channel_badge.setText("<span style='color: #eab308; font-size: 11px;'>● Beta Channel</span>")
        else:
            self.lbl_channel_badge.setText("<span style='color: #22c55e; font-size: 11px;'>● Stable Channel</span>")

        if hasattr(self, "divider") and self.divider:
            div_color = "#2d2d30" if effective == "dark" else "#d4d4d8"
            self.divider.setStyleSheet(f"background-color: {div_color}; border: none; width: 1px;")

        if hasattr(self, "tab_main"):
            self.tab_main.refresh_theme_labels(effective)
        if hasattr(self, "tab_monitor"):
            self.tab_monitor.refresh_monitors()
            self.tab_monitor.refresh_theme_labels(effective)
        if hasattr(self, "tab_system"):
            self.tab_system.refresh_theme_labels(effective)
        if hasattr(self, "tab_chronos"):
            self.tab_chronos.refresh_theme_labels(effective)
        if hasattr(self, "tab_cycler"):
            self.tab_cycler.refresh_theme_labels(effective)
        if hasattr(self, "tab_director"):
            self.tab_director.refresh_monitors_list()
            self.tab_director.refresh_theme_labels(effective)

        if hasattr(self, "btn_toggle_sidebar") and self.btn_toggle_sidebar:
            btn_border = "#3f3f46" if effective == "dark" else "#d4d4d8"
            btn_hover = "#27272a" if effective == "dark" else "#e4e4e7"
            btn_fg = "#a1a1aa" if effective == "dark" else "#71717a"
            btn_active_fg = "#ffffff" if effective == "dark" else "#18181b"
            self.btn_toggle_sidebar.setStyleSheet(f"""
                QPushButton#btnToggleSidebar {{
                    background-color: transparent;
                    border: 1px solid {btn_border};
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {btn_fg};
                }}
                QPushButton#btnToggleSidebar:hover {{
                    background-color: {btn_hover};
                    color: {btn_active_fg};
                    border-color: #9146ff;
                }}
            """)

    def set_view_index(self, idx):
        if 0 <= idx < self.stacked_pages.count():
            self.stacked_pages.setCurrentIndex(idx)
            btn = self.nav_button_group.button(idx)
            if btn:
                btn.setChecked(True)
            title = PAGE_TITLES.get(idx, "Streamer Calyx")
            self.lbl_page_title.setText(title)
            if idx == 8 and hasattr(self, "tab_hotkeys"):
                self.tab_hotkeys.populate_table()
            if hasattr(self, "combo_collapsed_nav") and self.combo_collapsed_nav:
                c_idx = self.combo_collapsed_nav.findData(idx)
                if c_idx >= 0 and self.combo_collapsed_nav.currentIndex() != c_idx:
                    self.combo_collapsed_nav.blockSignals(True)
                    self.combo_collapsed_nav.setCurrentIndex(c_idx)
                    self.combo_collapsed_nav.blockSignals(False)

    def toggle_sidebar(self):
        self.is_sidebar_collapsed = not self.is_sidebar_collapsed
        self._apply_sidebar_state()
        if hasattr(self.overlay, "sidebar_collapsed"):
            self.overlay.sidebar_collapsed = self.is_sidebar_collapsed
            if hasattr(self.overlay, "save_settings"):
                self.overlay.save_settings()

    def _apply_sidebar_state(self):
        if self.is_sidebar_collapsed:
            self.sidebar_widget.hide()
            self.divider.hide()
            self.btn_toggle_sidebar.setText("▶")
            self.btn_toggle_sidebar.setToolTip("Expand sidebar navigation (Ctrl+B)")
            self.combo_collapsed_nav.setVisible(True)
            self.lbl_page_title.setVisible(False)
            idx = self.stacked_pages.currentIndex()
            c_idx = self.combo_collapsed_nav.findData(idx)
            if c_idx >= 0 and self.combo_collapsed_nav.currentIndex() != c_idx:
                self.combo_collapsed_nav.blockSignals(True)
                self.combo_collapsed_nav.setCurrentIndex(c_idx)
                self.combo_collapsed_nav.blockSignals(False)
            self.setFixedSize(570, 600)
        else:
            self.sidebar_widget.show()
            self.divider.show()
            self.btn_toggle_sidebar.setText("◀")
            self.btn_toggle_sidebar.setToolTip("Collapse sidebar navigation (Ctrl+B)")
            self.combo_collapsed_nav.setVisible(False)
            self.lbl_page_title.setVisible(True)
            self.setFixedSize(780, 600)

    def _on_collapsed_nav_changed(self, c_idx):
        target_idx = self.combo_collapsed_nav.itemData(c_idx)
        if target_idx is not None and target_idx != self.stacked_pages.currentIndex():
            self.set_view_index(target_idx)

    def refresh_monitors_box(self, box):
        self.tab_monitor.refresh_monitors()

    def setup_row_key_catcher(self, btn):
        btn.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == event.Type.KeyPress:
            if hasattr(obj, "isCheckable") and obj.isCheckable() and obj.isChecked():
                v = event.key()

                # Escape cancels recording
                if v == Qt.Key.Key_Escape:
                    orig = getattr(obj, "_original_text", "set hotkey...")
                    obj.setText(orig)
                    obj.setChecked(False)
                    obj.setStyleSheet("")
                    obj._recorded_keys = []
                    if obj == getattr(self.tab_main, "btn_change_hk", None):
                        self.tab_main.update_activation_hotkey_label()
                    return True

                # Determine key name
                if v == Qt.Key.Key_Control:
                    key_name = "ctrl"
                elif v == Qt.Key.Key_Alt:
                    key_name = "alt"
                elif v == Qt.Key.Key_Shift:
                    key_name = "shift"
                elif v == Qt.Key.Key_Meta:
                    key_name = "windows"
                else:
                    key_name = qt_key_to_keyboard_str(v, event.text())
                    if not key_name:
                        key_name = f"key_{v}"

                # Append to recorded keys list up to 5 keys
                if not hasattr(obj, "_recorded_keys"):
                    obj._recorded_keys = []

                if key_name not in obj._recorded_keys and len(obj._recorded_keys) < 5:
                    obj._recorded_keys.append(key_name)

                # Show recorded sequence and prompt user to click to finish
                if obj._recorded_keys:
                    obj.setText(f"{'+'.join(obj._recorded_keys)} (Click to Finish)")
                else:
                    obj.setText("Press Keys... (Click to Finish)")

                return True

        return super().eventFilter(obj, event)

    def show_about_dialog(self):
        # Switch directly to the System tab where About is prominently displayed
        self.tabs.setCurrentIndex(4)


# ==============================================================================
# RESOURCE & ICON HELPERS
# ==============================================================================
def get_resource_path(relative_path):
    candidates = []
    if hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, relative_path))
    if getattr(sys, 'frozen', False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), relative_path))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path))
    candidates.append(os.getcwd())
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0] if candidates else relative_path

ICON_PATH = get_resource_path("icon.ico")

def get_app_icon():
    ico_path = get_resource_path("icon.ico")
    if os.path.exists(ico_path):
        ic = QIcon(ico_path)
        if not ic.isNull() and ic.availableSizes():
            return ic

    png_path = get_resource_path("icon.png")
    if os.path.exists(png_path):
        ic = QIcon(png_path)
        if not ic.isNull():
            return ic

    # High-resolution procedural fallback (purple alert reticle)
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(145, 70, 255))
    painter.setPen(QColor(255, 255, 255))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    painter.setPen(QPen(QColor(255, 255, 255), 4))
    painter.drawRect(18, 18, 28, 28)
    painter.end()
    return QIcon(pixmap)


def normalize_hotkey(hotkey_str):
    if not hotkey_str:
        return ""
    parts = [p.strip().lower() for p in hotkey_str.split("+") if p.strip()]
    normalized_parts = []
    for p in parts:
        if p in ("multiply", "star"):
            normalized_parts.append("asterisk")
        elif p == "minus":
            normalized_parts.append("subtract")
        elif p == "plus":
            normalized_parts.append("add")
        elif p in ("esc", "escape"):
            normalized_parts.append("esc")
        else:
            normalized_parts.append(p)
    return "+".join(normalized_parts)


def format_hotkey_display(hotkey_str):
    if not hotkey_str:
        return "Not Set"
    parts = [p.strip() for p in hotkey_str.split("+") if p.strip()]
    formatted_parts = []
    for p in parts:
        pl = p.lower()
        if pl == "ctrl": formatted_parts.append("Ctrl")
        elif pl == "alt": formatted_parts.append("Alt")
        elif pl == "shift": formatted_parts.append("Shift")
        elif pl in ("windows", "win"): formatted_parts.append("Win")
        elif pl == "add": formatted_parts.append("Numpad +")
        elif pl == "subtract": formatted_parts.append("Numpad -")
        elif pl == "multiply": formatted_parts.append("Numpad *")
        elif pl == "asterisk": formatted_parts.append("*")
        elif pl == "divide": formatted_parts.append("Numpad /")
        elif pl == "decimal": formatted_parts.append("Numpad .")
        elif pl.startswith("f") and pl[1:].isdigit(): formatted_parts.append(p.upper())
        elif pl == "space": formatted_parts.append("Space")
        elif pl == "esc": formatted_parts.append("Esc")
        else: formatted_parts.append(p.title())
    return " + ".join(formatted_parts)


def qt_key_to_keyboard_str(key, text=""):
    special_map = {
        Qt.Key.Key_Plus: "add",
        Qt.Key.Key_Minus: "subtract",
        Qt.Key.Key_Asterisk: "asterisk",
        Qt.Key.Key_Slash: "divide",
        Qt.Key.Key_Period: "decimal",
        Qt.Key.Key_Comma: "comma",
        Qt.Key.Key_Space: "space",
        Qt.Key.Key_Return: "enter",
        Qt.Key.Key_Enter: "enter",
        Qt.Key.Key_Tab: "tab",
        Qt.Key.Key_Backspace: "backspace",
        Qt.Key.Key_Delete: "delete",
        Qt.Key.Key_Insert: "insert",
        Qt.Key.Key_Home: "home",
        Qt.Key.Key_End: "end",
        Qt.Key.Key_PageUp: "page up",
        Qt.Key.Key_PageDown: "page down",
        Qt.Key.Key_Up: "up",
        Qt.Key.Key_Down: "down",
        Qt.Key.Key_Left: "left",
        Qt.Key.Key_Right: "right",
        Qt.Key.Key_F1: "f1",
        Qt.Key.Key_F2: "f2",
        Qt.Key.Key_F3: "f3",
        Qt.Key.Key_F4: "f4",
        Qt.Key.Key_F5: "f5",
        Qt.Key.Key_F6: "f6",
        Qt.Key.Key_F7: "f7",
        Qt.Key.Key_F8: "f8",
        Qt.Key.Key_F9: "f9",
        Qt.Key.Key_F10: "f10",
        Qt.Key.Key_F11: "f11",
        Qt.Key.Key_F12: "f12",
        Qt.Key.Key_CapsLock: "caps lock",
        Qt.Key.Key_NumLock: "num lock",
        Qt.Key.Key_ScrollLock: "scroll lock",
        Qt.Key.Key_Print: "print screen",
        Qt.Key.Key_Pause: "pause",
    }
    if key in special_map:
        return special_map[key]

    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return chr(key).lower()

    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return chr(key).lower()

    if text and text.strip() and text.isprintable():
        return text.lower()

    return ""