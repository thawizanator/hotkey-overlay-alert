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
                             QMessageBox, QLineEdit, QStackedWidget)
from PyQt6.QtGui import QIcon
from http.server import BaseHTTPRequestHandler, HTTPServer

SPEED_MAPPING = {"Snail": 0.01, "Turtle": 0.02, "Squirrel": 0.04, "Cheetah": 0.08, "Lightning": 0.15, "Always On": 0.00}
TWITCH_COMMANDS = ["/marker [description]", "/marker", "/announce [description]", "/announceblue [description]", "/announcegreen [description]", "/announceorange [description]", "/announcepurple [description]", "/shoutout [username]"]

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
        print(f"Error validating Twitch token: {e}")
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
                        <h2>Authorization Complete!</h2>
                        <p>Your Twitch account has been linked successfully.</p>
                        <p>You can safely close this browser window and return to <b>HotKey Overlay Alert</b>.</p>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html_response.encode("utf-8"))
            else:
                if worker is not None:
                    worker.auth_error.emit(error_msg or "Failed to capture access token.")

                html_err = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset='utf-8'>
                    <title>Authorization Failed - HotKey Overlay Alert</title>
                    <style>
                        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0e0e10; color: #efeff1; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
                        .card {{ background: #18181b; border: 1px solid #303032; border-radius: 8px; padding: 32px 40px; text-align: center; max-width: 480px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }}
                        h2 {{ color: #ED4245; margin-top: 0; }}
                        p {{ color: #adadb8; line-height: 1.5; }}
                    </style>
                </head>
                <body>
                    <div class='card'>
                        <h2>Authorization Failed</h2>
                        <p>{error_msg or 'Access was denied or token was missing.'}</p>
                        <p>You can close this window and try again from the app.</p>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(html_err.encode("utf-8"))
            return

        # Initial landing page: extract URL hash fragment (which browsers don't send over HTTP) and redirect
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        html_redirect = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset='utf-8'>
            <title>Processing Twitch Token - HotKey Overlay Alert</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0e0e10; color: #efeff1; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
                .card { background: #18181b; border: 1px solid #303032; border-radius: 8px; padding: 32px 40px; text-align: center; max-width: 480px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
                h2 { color: #9146ff; margin-top: 0; }
                p { color: #adadb8; line-height: 1.5; }
                .spinner { border: 4px solid #303032; border-top: 4px solid #9146ff; border-radius: 50%; width: 36px; height: 36px; animation: spin 1s linear infinite; margin: 20px auto; }
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            </style>
        </head>
        <body>
            <div class='card'>
                <h2>Connecting to HotKey Overlay Alert...</h2>
                <div class='spinner' id='spinner'></div>
                <p id='msg'>Processing authorization token, please wait...</p>
            </div>
            <script>
                (function() {
                    var hash = window.location.hash ? window.location.hash.substring(1) : '';
                    var search = window.location.search ? window.location.search.substring(1) : '';
                    var params = new URLSearchParams(hash || search);
                    var token = params.get('access_token');
                    var error = params.get('error_description') || params.get('error');

                    if (token) {
                        window.location.href = '/callback?access_token=' + encodeURIComponent(token);
                    } else if (error) {
                        window.location.href = '/callback?error=' + encodeURIComponent(error);
                    } else {
                        document.getElementById('spinner').style.display = 'none';
                        document.getElementById('msg').innerText = 'No authorization token detected. Please return to the app and retry.';
                    }
                })();
            </script>
        </body>
        </html>
        """
        self.wfile.write(html_redirect.encode("utf-8"))

    def log_message(self, format, *args):
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
            # Bind to all interfaces so both localhost and 127.0.0.1 work
            server = ReusableHTTPServer(("", self.port), TwitchAuthHandler)
            server.worker = self
            server.timeout = 0.5

            scopes = "channel:manage:broadcast+moderator:manage:announcements+moderator:manage:shoutouts+user:write:chat+user:read:chat"
            encoded_redirect = urllib.parse.quote(self.redirect_uri, safe="")
            auth_url = f"https://id.twitch.tv/oauth2/authorize?client_id={self.client_id}&redirect_uri={encoded_redirect}&response_type=token&scope={scopes}&force_verify=true"

            webbrowser.open(auth_url)

            start_time = time.time()
            # Wait up to 120 seconds for the user to complete authorization
            while self.running and not self.token_captured:
                server.handle_request()
                if time.time() - start_time > 120:
                    self.auth_error.emit("Twitch authorization timed out after 2 minutes.")
                    break

            if self.token_captured:
                time.sleep(0.5)
        except Exception as e:
            print(f"TwitchAuthWorker Error: {e}")
            self.auth_error.emit(str(e))
        finally:
            if server:
                try:
                    server.server_close()
                except Exception:
                    pass

    def stop(self):
        self.running = False


class TwitchSettingsView(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_win = main_window
        self.auth_worker = None
        layout = QVBoxLayout()
        layout.setSpacing(8)

        layout.addWidget(QLabel("<h2>Twitch Integration Console</h2>"))

        # Account Status Section
        layout.addWidget(QLabel("<b>Twitch Integration Account:</b>"))

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("font-size: 13px; padding: 4px;")
        layout.addWidget(self.lbl_status)

        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Broadcaster Channel Name:"))
        self.txt_channel = QLineEdit()
        self.txt_channel.setFixedWidth(200)
        self.txt_channel.setText(self.main_win.overlay.twitch_channel)
        channel_layout.addWidget(self.txt_channel)
        channel_layout.addStretch()
        layout.addLayout(channel_layout)

        # Login / Link / Unlink Buttons
        btn_box = QHBoxLayout()
        self.btn_login = QPushButton("🔑 Login / Link with Twitch Account")
        self.btn_login.setStyleSheet("background-color: #6441a5; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_login.clicked.connect(self.start_twitch_oauth)
        btn_box.addWidget(self.btn_login)

        self.btn_unlink = QPushButton("Disconnect Account")
        self.btn_unlink.setStyleSheet("background-color: #555; color: white; padding: 6px; border-radius: 4px;")
        self.btn_unlink.clicked.connect(self.unlink_twitch_account)
        btn_box.addWidget(self.btn_unlink)

        layout.addLayout(btn_box)

        layout.addSpacing(10)
        layout.addWidget(QLabel("<b>Configure Macro Hotkeys (Max 4 Commands):</b>"))

        self.entries_layout = QVBoxLayout()
        self.rows = []
        layout.addLayout(self.entries_layout)

        macro_actions_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Hotkey Entry")
        self.btn_add.clicked.connect(self.add_entry_row)
        macro_actions_layout.addWidget(self.btn_add)
        layout.addLayout(macro_actions_layout)

        layout.addStretch()

        nav_layout = QHBoxLayout()
        self.btn_save = QPushButton("Save & Return")
        self.btn_save.clicked.connect(self.save_and_close)
        nav_layout.addWidget(self.btn_save)
        layout.addLayout(nav_layout)

        self.setLayout(layout)
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
            self.btn_login.setText("🔄 Re-link / Switch Twitch Account")
            self.btn_login.setStyleSheet("background-color: #2e6930; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")
            self.btn_unlink.setVisible(True)
        else:
            self.lbl_status.setText("⚪ Status: <b>Not Connected</b> (Click below to link Twitch)")
            self.btn_login.setText("🔑 Login / Link with Twitch Account")
            self.btn_login.setStyleSheet("background-color: #6441a5; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")
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
        if "redirect_mismatch" in str(err_msg).lower():
            redirect_uri = getattr(self.main_win.overlay, "twitch_redirect_uri", "http://localhost:17563")
            QMessageBox.warning(
                self,
                "Redirect URI Mismatch",
                f"Twitch rejected the authorization request because the redirect URI does not match:\n\n"
                f"App sent: {redirect_uri}\n\n"
                f"Please ensure that '{redirect_uri}' is added to 'OAuth Redirect URLs' in your Twitch Developer Console "
                f"at dev.twitch.tv/console/apps, or adjust the OAuth Redirect URI field in this menu to match exactly."
            )
        else:
            QMessageBox.warning(self, "Authorization Error", f"Twitch linking was not completed:\n\n{err_msg}")

    def handle_incoming_token(self, token):
        self.btn_login.setEnabled(True)
        client_id_str = str(self.main_win.overlay.twitch_client_id).strip()

        # Validate token and auto-fetch channel profile
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

        # Immediately persist the received token and credentials
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
        self.create_row_ui("/marker", "set hotkey...")

    def create_row_ui(self, saved_command, saved_hotkey):
        row_widget = QWidget()
        row_lay = QHBoxLayout()
        combo = QComboBox()
        for cmd in TWITCH_COMMANDS:
            combo.addItem(cmd)
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

    def remove_entry_row(self, r_data):
        r_data["widget"].deleteLater()
        self.entries_layout.removeWidget(r_data["widget"])
        self.rows.remove(r_data)

    def save_and_close(self):
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
        self.main_win.set_view_index(0)


class VisualSettingsView(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_win = main_window
        layout = QVBoxLayout()
        layout.setSpacing(8)

        layout.addWidget(QLabel("<b>Select Monitor:</b>"))
        self.monitor_combo = QComboBox()
        self.main_win.refresh_monitors_box(self.monitor_combo)
        self.monitor_combo.setCurrentIndex(self.main_win.overlay.target_monitor_index)
        layout.addWidget(self.monitor_combo)

        self.btn_identify = QPushButton("Identify Monitors")
        self.btn_identify.clicked.connect(self.main_win.overlay.identify_monitors)
        layout.addWidget(self.btn_identify)

        layout.addSpacing(10)
        layout.addWidget(QLabel("<b>Activation Hotkey:</b>"))
        self.lbl_hotkey = QLabel()
        layout.addWidget(self.lbl_hotkey)

        hk_btn_layout = QHBoxLayout()
        self.btn_change_hk = QPushButton("Change Hotkey")
        self.btn_change_hk.setCheckable(True)
        self.main_win.setup_row_key_catcher(self.btn_change_hk)
        self.btn_change_hk.clicked.connect(self.on_activation_hotkey_btn_clicked)

        self.btn_reset_hk = QPushButton("Reset Default")
        self.btn_reset_hk.clicked.connect(self.reset_activation_hotkey)

        hk_btn_layout.addWidget(self.btn_change_hk)
        hk_btn_layout.addWidget(self.btn_reset_hk)
        layout.addLayout(hk_btn_layout)
        self.update_activation_hotkey_label()

        layout.addSpacing(10)
        layout.addWidget(QLabel("Border Customization:"))

        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Highlight Color:"))
        self.btn_color = QPushButton()
        self.btn_color.setFixedSize(40, 22)
        self.btn_color.setStyleSheet(f"background-color: {self.main_win.overlay.border_color.name()}; border: 1px solid black;")
        self.btn_color.clicked.connect(self.pick_color)
        color_layout.addWidget(self.btn_color)
        color_layout.addStretch()
        layout.addLayout(color_layout)

        layout.addWidget(QLabel("Thickness (px):"))
        self.slider_thickness = QSlider(Qt.Orientation.Horizontal)
        self.slider_thickness.setRange(2, 30)
        self.slider_thickness.setValue(self.main_win.overlay.border_thickness)
        self.slider_thickness.valueChanged.connect(self.adjust_thickness)
        layout.addWidget(self.slider_thickness)

        layout.addWidget(QLabel("Opacity/Transparency:"))
        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(10, 100)
        self.slider_opacity.setValue(int(self.main_win.overlay.border_opacity * 100))
        self.slider_opacity.valueChanged.connect(self.adjust_opacity)
        layout.addWidget(self.slider_opacity)

        layout.addSpacing(10)
        layout.addWidget(QLabel("Effects & Animation Speed:"))
        flash_state = "ON" if self.main_win.overlay.is_flashing else "OFF"
        self.btn_flash = QPushButton(f"Toggle Breathing/Flashing Effect: {flash_state}")
        self.btn_flash.clicked.connect(self.toggle_flash)
        layout.addWidget(self.btn_flash)

        self.speed_combo = QComboBox()
        for s in SPEED_MAPPING.keys():
            self.speed_combo.addItem(s)
        self.speed_combo.setCurrentText(self.main_win.overlay.flash_speed_name)
        layout.addWidget(self.speed_combo)

        layout.addSpacing(10)
        self.btn_goto_twitch = QPushButton("Open Twitch Hotkey Integration Menu →")
        self.btn_goto_twitch.setStyleSheet("background-color: #6441a5; color: white; font-weight: bold; padding: 6px;")
        self.btn_goto_twitch.clicked.connect(lambda: self.main_win.set_view_index(1))
        layout.addWidget(self.btn_goto_twitch)

        layout.addStretch()

        nav_btn_layout = QHBoxLayout()
        self.btn_about = QPushButton("About Application")
        self.btn_about.clicked.connect(self.main_win.show_about_dialog)
        self.btn_close = QPushButton("Close Settings")
        self.btn_close.clicked.connect(self.main_win.close)
        nav_btn_layout.addWidget(self.btn_about)
        nav_btn_layout.addWidget(self.btn_close)
        layout.addLayout(nav_btn_layout)

        self.setLayout(layout)
        self.monitor_combo.currentIndexChanged.connect(self.change_monitor)
        self.speed_combo.currentIndexChanged.connect(self.change_speed)

    def change_monitor(self, idx):
        if idx >= 0:
            self.main_win.overlay.target_monitor_index = idx
            self.main_win.overlay.update_monitor_geometry(idx)
            self.main_win.overlay.save_settings()

    def change_speed(self, idx):
        if idx >= 0:
            self.main_win.overlay.update_flash_speed(self.speed_combo.currentText())

    def pick_color(self):
        color = QColorDialog.getColor(self.main_win.overlay.border_color, self, "Select Color")
        if color.isValid():
            self.main_win.overlay.border_color = color
            self.btn_color.setStyleSheet(f"background-color: {color.name()}; border: 1px solid black;")
            self.main_win.overlay.update()
            self.main_win.overlay.save_settings()

    def adjust_thickness(self, val):
        self.main_win.overlay.border_thickness = val
        self.main_win.overlay.update()
        self.main_win.overlay.save_settings()

    def adjust_opacity(self, val):
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

    def update_activation_hotkey_label(self):
        current = getattr(self.main_win.overlay, "activation_hotkey", "ctrl+add")
        formatted = format_hotkey_display(current)
        self.lbl_hotkey.setText(f"Current Hotkey: <b>{formatted}</b>")

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


def get_resource_path(relative_path):
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

ICON_PATH = get_resource_path("icon.ico")


def normalize_hotkey(hk_str):
    if not hk_str:
        return ""
    replacements = {
        "multiply": "asterisk",
        "minus": "subtract",
        "star": "asterisk",
    }
    clean = hk_str.replace("(Click to Finish)", "").strip()
    parts = [p.strip() for p in clean.split("+") if p.strip()]
    normalized = [replacements.get(p.lower(), p.lower()) for p in parts]
    return "+".join(normalized)


def format_hotkey_display(hk):
    if not hk:
        return "None (Disabled)"
    display_map = {
        "ctrl": "Ctrl",
        "left ctrl": "Ctrl",
        "right ctrl": "Right Ctrl",
        "alt": "Alt",
        "shift": "Shift",
        "windows": "Win",
        "add": "Numpad +",
        "subtract": "Numpad -",
        "multiply": "Numpad *",
        "asterisk": "Asterisk (*)",
        "divide": "Numpad /",
        "space": "Space",
        "tab": "Tab",
        "enter": "Enter",
        "backspace": "Backspace",
        "delete": "Delete",
        "insert": "Insert",
        "home": "Home",
        "end": "End",
        "page up": "Page Up",
        "page down": "Page Down",
        "caps lock": "Caps Lock",
        "num lock": "Num Lock",
        "scroll lock": "Scroll Lock",
        "print screen": "Print Screen",
        "pause": "Pause",
    }
    parts = []
    for p in hk.split("+"):
        p_clean = p.strip().lower()
        if p_clean in display_map:
            parts.append(display_map[p_clean])
        elif p_clean.startswith("f") and p_clean[1:].isdigit():
            parts.append(p_clean.upper())
        elif len(p_clean) <= 3:
            parts.append(p_clean.upper())
        else:
            parts.append(p_clean.title())
    return " + ".join(parts)


def qt_key_to_keyboard_str(key, text=""):
    # Function keys F1-F24
    if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        return f"f{key - Qt.Key.Key_F1 + 1}"

    # Numpad & Math keys
    numpad_map = {
        Qt.Key.Key_Plus: "add",
        Qt.Key.Key_Asterisk: "asterisk",
        Qt.Key.Key_Minus: "subtract",
        Qt.Key.Key_Slash: "/",
        Qt.Key.Key_Period: ".",
    }
    if key in numpad_map:
        return numpad_map[key]

    # Special / Navigation keys
    special_map = {
        Qt.Key.Key_Space: "space",
        Qt.Key.Key_Tab: "tab",
        Qt.Key.Key_Return: "enter",
        Qt.Key.Key_Enter: "enter",
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
        Qt.Key.Key_CapsLock: "caps lock",
        Qt.Key.Key_NumLock: "num lock",
        Qt.Key.Key_ScrollLock: "scroll lock",
        Qt.Key.Key_Print: "print screen",
        Qt.Key.Key_Pause: "pause",
    }
    if key in special_map:
        return special_map[key]

    # Standard ASCII numbers 0-9
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return chr(key).lower()

    # Standard ASCII letters A-Z
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return chr(key).lower()

    # Printable text fallback
    if text and text.strip() and text.isprintable():
        return text.lower()

    return ""


class SettingsWindow(QWidget):
    def __init__(self, overlay_app):
        super().__init__()
        self.overlay = overlay_app
        self.setWindowTitle("HotKey Overlay Alert Settings")
        self.setFixedSize(400, 620)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.stack = QStackedWidget(self)
        self.view_visual = VisualSettingsView(self)
        self.view_twitch = TwitchSettingsView(self)
        self.stack.addWidget(self.view_visual)
        self.stack.addWidget(self.view_twitch)

        layout = QVBoxLayout()
        layout.addWidget(self.stack)
        self.setLayout(layout)

    def set_view_index(self, idx):
        self.stack.setCurrentIndex(idx)

    def refresh_monitors_box(self, box):
        box.clear()
        for i, s in enumerate(QApplication.screens()):
            box.addItem(f"Monitor #{i + 1} ({s.size().width()}x{s.size().height()})")

    def setup_row_key_catcher(self, btn):
        btn.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj.isCheckable() and obj.isChecked():
            if event.type() == event.Type.KeyPress:
                v = event.key()

                # Escape cancels recording
                if v == Qt.Key.Key_Escape:
                    orig = getattr(obj, "_original_text", "set hotkey...")
                    obj.setText(orig)
                    obj.setChecked(False)
                    obj.setStyleSheet("")
                    obj._recorded_keys = []
                    if hasattr(self, "view_visual") and obj == getattr(self.view_visual, "btn_change_hk", None):
                        self.view_visual.update_activation_hotkey_label()
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
        msg = QMessageBox(self)
        if os.path.exists(ICON_PATH):
            msg.setWindowIcon(QIcon(ICON_PATH))
        msg.setWindowTitle("About Monitor Border Overlay")
        about_text = ( 
            "<b>About This App</b><br><br>" 
            "This visual hotkey alert was created to help prevent one of the most common " 
            "streaming mistakes: muting your microphone and forgetting to unmute it. " 
            "(Trust me, I've done it plenty of times!)<br><br>" 
            "However, this app isn't limited to microphone muting. You can use it to " 
            "monitor any hotkey or toggle you want a visual reminder for. Simply configure " 
            "the hotkey in this app to match the hotkey you want to monitor.<br><br>" 
            "<b>How It Works</b><br>" 
            "• This app provides visual alerts only. There are no audio notifications.<br>" 
            "• The app runs in the system tray, where you'll find its wizanator icon. " 
            "Yes, that one!<br>" 
            "• When triggered, the highlighted overlay is designed to stay on top of " 
            "other application windows so you can see your alert while streaming.<br><br>" 
            "<b>Troubleshooting</b><br>" 
            "If the overlay doesn't stay on top of other applications as expected, try " 
            "closing the app and restarting it with administrator privileges. To do this, " 
            "right-click the app and select <b>Run as administrator</b>.<br><br>" 
            "<b>Created by ThaWizanator</b><br>" 
            "<a href='https://twitch.tv'>twitch.tv/thawizanator</a><br><br>" 
            "Version 2.1.0 | October 2026" 
        )
        msg.setText(about_text)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.exec()