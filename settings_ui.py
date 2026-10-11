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
                             QGroupBox, QProgressBar, QDialog)
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen
from http.server import BaseHTTPRequestHandler, HTTPServer

from updater import (UpdateCheckWorker, DownloadWorker, apply_update_and_restart, 
                     CURRENT_VERSION, is_newer_version, GITHUB_REPO)
from debug_logger import log_debug, get_crash_log_path, get_debug_log_path

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
                    <title>Twitch Linked! - HotKey Overlay Alert</title>
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
                        <p>Your Twitch account has been authenticated with HotKey Overlay Alert.</p>
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
                <head><meta charset='utf-8'><title>Error - HotKey Overlay Alert</title>
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
        grp_mode = QGroupBox("Display & Overlay Mode")
        lay_mode = QVBoxLayout(grp_mode)
        lay_mode.setSpacing(6)

        self.chk_streamer = QCheckBox("Streamer Mode (In-Game Transparent HUD Overlays)")
        self.chk_streamer.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.chk_streamer.setChecked(getattr(self.main_win.overlay, "streamer_mode", True))
        self.chk_streamer.toggled.connect(self.on_streamer_toggled)
        lay_mode.addWidget(self.chk_streamer)

        lbl_mode_desc = QLabel(
            "<span style='color: #a1a1aa; font-size: 12px;'>"
            "• <b>Checked (Streamer Mode):</b> Uses non-intrusive transparent in-game HUD alerts "
            "and auto-fading toasts so game captures and full-screen games are never interrupted.<br>"
            "• <b>Unchecked (Desktop Mode):</b> Uses standard modal window dialogs with title bars "
            "and persistent confirmation popups, designed for channel moderators and desktop users."
            "</span>"
        )
        lbl_mode_desc.setWordWrap(True)
        lbl_mode_desc.setTextFormat(Qt.TextFormat.RichText)
        lay_mode.addWidget(lbl_mode_desc)
        layout.addWidget(grp_mode)

        # Group 2: Primary Activation Hotkey
        grp_hk = QGroupBox("Primary Monitor Highlight Hotkey")
        lay_hk = QVBoxLayout(grp_hk)
        lay_hk.setSpacing(8)

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

        lbl_hint = QLabel(
            "<span style='color: #71717a; font-size: 11px;'>"
            "💡 Tip: HotKey Overlay Alert runs quietly in your Windows system tray. "
            "Right-click the <b>wizanator icon</b> anytime to reopen settings or exit."
            "</span>"
        )
        lbl_hint.setWordWrap(True)
        lbl_hint.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(lbl_hint)

        self.update_activation_hotkey_label()

    def on_streamer_toggled(self, checked):
        if hasattr(self.main_win.overlay, "set_streamer_mode"):
            self.main_win.overlay.set_streamer_mode(checked)

    def update_activation_hotkey_label(self):
        current = getattr(self.main_win.overlay, "activation_hotkey", "ctrl+add")
        formatted = format_hotkey_display(current)
        self.lbl_hotkey.setText(f"Active Highlight Hotkey: <b>{formatted}</b>")

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
        self.btn_identify.setStyleSheet("padding: 6px; font-weight: bold;")
        self.btn_identify.clicked.connect(self.main_win.overlay.identify_monitors)
        lay_mon.addWidget(self.btn_identify)

        layout.addWidget(grp_mon)

        self.lbl_info = QLabel()
        self.lbl_info.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        self.update_monitor_info()
        layout.addWidget(self.lbl_info)

        layout.addStretch()

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

    def update_monitor_info(self):
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
        grp_fx = QGroupBox("Breathing & Flashing Effects")
        lay_fx = QVBoxLayout(grp_fx)
        lay_fx.setSpacing(8)

        flash_state = "ON" if self.main_win.overlay.is_flashing else "OFF"
        self.btn_flash = QPushButton(f"Toggle Breathing/Flashing Effect: {flash_state}")
        self.btn_flash.setStyleSheet("font-weight: bold; padding: 5px;")
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
        self.txt_channel.setText(self.main_win.overlay.twitch_channel)
        channel_layout.addWidget(self.txt_channel)
        channel_layout.addStretch()
        lay_acc.addLayout(channel_layout)

        btn_box = QHBoxLayout()
        self.btn_login = QPushButton("🔑 Login / Link with Twitch Account")
        self.btn_login.setStyleSheet("background-color: #6441a5; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")
        self.btn_login.clicked.connect(self.start_twitch_oauth)
        btn_box.addWidget(self.btn_login)

        self.btn_unlink = QPushButton("Disconnect")
        self.btn_unlink.setStyleSheet("background-color: #4b4b4e; color: white; padding: 5px 10px; border-radius: 4px;")
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
        self.btn_save.setStyleSheet("background-color: #2e6930; color: white; font-weight: bold; padding: 4px 12px;")
        self.btn_save.clicked.connect(self.save_macros)
        macro_actions_layout.addWidget(self.btn_save)
        macro_actions_layout.addStretch()
        lay_mac.addLayout(macro_actions_layout)

        layout.addWidget(grp_mac)
        layout.addStretch()

        for m in self.main_win.overlay.twitch_macros:
            self.create_row_ui(m["command"], m["hotkey"])

        self.update_connection_ui()

    def update_connection_ui(self):
        token = getattr(self.main_win.overlay, "twitch_token", "")
        channel = getattr(self.main_win.overlay, "twitch_channel", "")
        display = getattr(self.main_win.overlay, "twitch_display_name", "") or channel
        user_id = getattr(self.main_win.overlay, "twitch_user_id", "")

        if token:
            info_text = f"🟢 Connected as: <b>{display}</b>"
            if channel and channel.lower() != display.lower():
                info_text += f" (@{channel})"
            if user_id:
                info_text += f" <span style='color: gray;'>(ID: {user_id})</span>"
            self.lbl_status.setText(info_text)
            self.btn_login.setText("🔄 Re-link Account")
            self.btn_login.setStyleSheet("background-color: #2e6930; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")
            self.btn_unlink.setVisible(True)
        else:
            self.lbl_status.setText("⚪ Status: <b>Not Connected</b> (Click below to link Twitch)")
            self.btn_login.setText("🔑 Login / Link with Twitch Account")
            self.btn_login.setStyleSheet("background-color: #6441a5; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px;")
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
            login = self.txt_channel.text().strip() or self.main_win.overlay.twitch_channel
            display_name = login

        self.main_win.overlay.twitch_token = token
        self.main_win.overlay.twitch_channel = login
        if user_id:
            self.main_win.overlay.twitch_user_id = str(user_id)
        if display_name:
            self.main_win.overlay.twitch_display_name = display_name

        self.txt_channel.setText(login)
        self.update_connection_ui()
        self.main_win.overlay.save_settings()

        QMessageBox.information(
            self,
            "Success",
            f"Your Twitch account has been linked successfully!\n\n"
            f"Broadcaster: {display_name} ({login})\n"
            f"User ID: {self.main_win.overlay.twitch_user_id or 'Auto-detected'}\n\n"
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
            self.main_win.overlay.twitch_user_id = ""
            self.main_win.overlay.twitch_display_name = ""
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
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # Group 1: Software Updates
        grp_upd = QGroupBox("Application Updates")
        lay_upd = QVBoxLayout(grp_upd)
        lay_upd.setSpacing(8)

        status_box = QHBoxLayout()
        self.lbl_cur_ver = QLabel(f"Installed Version: <b>v{CURRENT_VERSION}</b>")
        self.lbl_update_status = QLabel("<span style='color: #a1a1aa;'>Status: Checking...</span>")
        self.lbl_update_status.setTextFormat(Qt.TextFormat.RichText)
        status_box.addWidget(self.lbl_cur_ver)
        status_box.addSpacing(16)
        status_box.addWidget(self.lbl_update_status)
        status_box.addStretch()
        lay_upd.addLayout(status_box)

        btn_upd_box = QHBoxLayout()
        self.btn_check_update = QPushButton("🔄 Check for Updates Now")
        self.btn_check_update.clicked.connect(self.check_updates_clicked)
        btn_upd_box.addWidget(self.btn_check_update)

        self.btn_download_update = QPushButton("🚀 Download & Install Update")
        self.btn_download_update.setStyleSheet("background-color: #2e6930; color: white; font-weight: bold; padding: 5px;")
        self.btn_download_update.setEnabled(False)
        self.btn_download_update.clicked.connect(self.download_update_clicked)
        btn_upd_box.addWidget(self.btn_download_update)

        self.btn_view_release = QPushButton("View on GitHub")
        self.btn_view_release.clicked.connect(lambda: webbrowser.open(self.latest_release_url or f"https://github.com/{GITHUB_REPO}/releases"))
        btn_upd_box.addWidget(self.btn_view_release)
        lay_upd.addLayout(btn_upd_box)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #303032; border-radius: 4px; text-align: center; height: 18px; }
            QProgressBar::chunk { background-color: #9146ff; border-radius: 3px; }
        """)
        lay_upd.addWidget(self.progress_bar)

        # Checkboxes
        self.chk_check_startup = QCheckBox("Check for updates automatically on startup")
        self.chk_check_startup.setChecked(getattr(self.main_win.overlay, "check_updates_on_startup", True))
        self.chk_check_startup.toggled.connect(self.on_check_startup_toggled)
        lay_upd.addWidget(self.chk_check_startup)

        self.chk_auto_download = QCheckBox("Automatically download and apply updates when available")
        self.chk_auto_download.setChecked(getattr(self.main_win.overlay, "auto_update_enabled", False))
        self.chk_auto_download.toggled.connect(self.on_auto_download_toggled)
        lay_upd.addWidget(self.chk_auto_download)

        layout.addWidget(grp_upd)

        # Group 2: Diagnostics & Troubleshooting
        grp_diag = QGroupBox("Diagnostics & Logs")
        lay_diag = QVBoxLayout(grp_diag)
        lay_diag.setSpacing(8)

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

        layout.addWidget(grp_diag)

        # Group 3: About
        grp_about = QGroupBox("About Application")
        lay_about = QVBoxLayout(grp_about)
        lay_about.setSpacing(4)
        lbl_about_txt = QLabel(
            f"<b>HotKey Overlay Alert</b> – Version {CURRENT_VERSION}<br>"
            "Created by <b>ThaWizanator</b> • <a href='https://twitch.tv/thawizanator' style='color: #9146ff;'>twitch.tv/thawizanator</a><br>"
            "<span style='color: #71717a;'>Licensed under the MIT License • Standalone Authenticode Signed</span>"
        )
        lbl_about_txt.setTextFormat(Qt.TextFormat.RichText)
        lbl_about_txt.setOpenExternalLinks(True)
        lay_about.addWidget(lbl_about_txt)
        layout.addWidget(grp_about)

        layout.addStretch()

        # Trigger passive update check on tab creation
        self.check_updates_silently()

    def check_updates_silently(self):
        self.check_worker = UpdateCheckWorker(CURRENT_VERSION)
        self.check_worker.update_available.connect(self.on_update_found)
        self.check_worker.up_to_date.connect(self.on_up_to_date)
        self.check_worker.check_error.connect(self.on_check_error)
        self.check_worker.start()

    def check_updates_clicked(self):
        self.btn_check_update.setEnabled(False)
        self.lbl_update_status.setText("<span style='color: #a1a1aa;'>Checking GitHub releases...</span>")
        self.check_worker = UpdateCheckWorker(CURRENT_VERSION)
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
            self.btn_download_update.setEnabled(True)

    def on_up_to_date(self, current_ver):
        self.lbl_update_status.setText(f"<span style='color: #43b581;'>✔️ Up to date (v{current_ver})</span>")
        self.btn_download_update.setEnabled(False)

    def on_check_error(self, err_str):
        self.lbl_update_status.setText("<span style='color: #a1a1aa;'>Could not connect to update server</span>")

    def on_update_found_interactive(self, latest_tag, release_url, download_url, notes):
        self.btn_check_update.setEnabled(True)
        self.on_update_found(latest_tag, release_url, download_url, notes)
        res = QMessageBox.question(
            self,
            "Update Available",
            f"<b>A new version of HotKey Overlay Alert is available!</b><br><br>"
            f"Current version: <b>v{CURRENT_VERSION}</b><br>"
            f"Latest version: <b>{latest_tag}</b><br><br>"
            f"Would you like to download and install this update now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes and download_url:
            self.download_update_clicked()

    def on_up_to_date_interactive(self, current_ver):
        self.btn_check_update.setEnabled(True)
        self.on_up_to_date(current_ver)
        QMessageBox.information(self, "Up to Date", f"HotKey Overlay Alert is up to date (version {current_ver}).")

    def on_check_error_interactive(self, err_str):
        self.btn_check_update.setEnabled(True)
        self.on_check_error(err_str)
        QMessageBox.warning(self, "Update Check Error", f"Unable to check for updates:\n\n{err_str}")

    def download_update_clicked(self):
        if not self.latest_download_url:
            if self.latest_release_url:
                webbrowser.open(self.latest_release_url)
            return

        app_dir = getattr(self.main_win.overlay, "app_dir", None) or os.path.dirname(os.path.abspath(__file__))
        temp_exe = os.path.join(app_dir, f"HotKeyOverlayAlert_new_{self.latest_tag}.exe")

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
# MAIN SETTINGS CONTAINER (5-Tab Modern Layout)
# ==============================================================================
class SettingsWindow(QWidget):
    def __init__(self, overlay_app):
        super().__init__()
        self.overlay = overlay_app
        self.setWindowTitle(f"HotKey Overlay Alert Settings (v{CURRENT_VERSION})")
        self.setFixedSize(510, 460)
        self.setWindowIcon(get_app_icon())

        # Main Layout
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        # Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #303032;
                background-color: #18181b;
                border-radius: 6px;
                padding: 4px;
            }
            QTabBar::tab {
                background: #27272a;
                color: #a1a1aa;
                padding: 7px 14px;
                margin-right: 3px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-weight: 600;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: #9146ff;
                color: #ffffff;
            }
            QTabBar::tab:hover:!selected {
                background: #3f3f46;
                color: #efeff1;
            }
            QGroupBox {
                border: 1px solid #303032;
                border-radius: 6px;
                margin-top: 8px;
                font-weight: bold;
                font-size: 12px;
                color: #efeff1;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """)

        # Add the 5 requested tabs
        self.tab_main = MainTab(self)
        self.tab_monitor = MonitorTab(self)
        self.tab_alert = AlertOverlayTab(self)
        self.tab_twitch = TwitchTab(self)
        self.tab_system = SystemTab(self)

        self.tabs.addTab(self.tab_main, "🏠 Main")
        self.tabs.addTab(self.tab_monitor, "🖥️ Monitor")
        self.tabs.addTab(self.tab_alert, "🎨 Alert Overlay")
        self.tabs.addTab(self.tab_twitch, "🟣 Twitch")
        self.tabs.addTab(self.tab_system, "⚙️ System")

        root_layout.addWidget(self.tabs)

        # Bottom Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(4, 0, 4, 0)
        lbl_v = QLabel(f"<span style='color: #71717a; font-size: 11px;'>v{CURRENT_VERSION} • ThaWizanator</span>")
        lbl_v.setTextFormat(Qt.TextFormat.RichText)
        bottom_bar.addWidget(lbl_v)
        bottom_bar.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.setFixedWidth(80)
        self.btn_close.setStyleSheet("padding: 5px 12px;")
        self.btn_close.clicked.connect(self.close)
        bottom_bar.addWidget(self.btn_close)
        root_layout.addLayout(bottom_bar)

        # Compatibility aliases for other modules
        self.view_visual = self.tab_monitor
        self.view_twitch = self.tab_twitch

    def set_view_index(self, idx):
        if idx < self.tabs.count():
            self.tabs.setCurrentIndex(idx)

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
    icon = QIcon()
    ico_path = get_resource_path("icon.ico")
    png_path = get_resource_path("icon.png")

    if os.path.exists(ico_path):
        icon.addFile(ico_path)
    if os.path.exists(png_path):
        icon.addFile(png_path)

    if not icon.isNull() and icon.availableSizes():
        return icon

    for p in [ico_path, png_path]:
        if os.path.exists(p):
            ic = QIcon(p)
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