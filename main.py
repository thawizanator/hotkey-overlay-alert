import sys
import os
import json
import keyboard

# Ensure Windows Taskbar displays the application icon instead of Python's default icon
if sys.platform == "win32":
    try:
        import ctypes
        app_user_model_id = "thawizanator.hotkeyoverlayalert.app.2.3.9"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_user_model_id)
    except Exception:
        pass

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import (QApplication, QMainWindow, QSystemTrayIcon, QMenu, 
                             QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QMessageBox, QDialog, QPushButton)
from PyQt6.QtGui import QPainter, QPen, QColor, QIcon, QAction, QPixmap

# Import components from our other local workspace files
from twitch_worker import TwitchCommandWorker
from settings_ui import SettingsWindow, SPEED_MAPPING, normalize_hotkey, format_hotkey_display, ICON_PATH, get_app_icon
from updater import CURRENT_VERSION, UpdateCheckWorker, DownloadWorker, apply_update_and_restart

def get_app_directory():
    appdata_root = os.environ.get("APPDATA") or os.path.expanduser("~")
    app_folder = os.path.join(appdata_root, "ThaWizanator_Overlay")
    if not os.path.exists(app_folder): 
        os.makedirs(app_folder)
    return app_folder

APP_DIR = get_app_directory()
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
DEBUG_LOG_FILE = os.path.join(APP_DIR, "debug.txt")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
LOCK_FILE = os.path.join(APP_DIR, "app.lock")
lock_file_handle = None
from debug_logger import init_debug_logger, set_debug_mode, is_debug_mode, get_debug_log_path, log_debug, install_crash_handler
init_debug_logger(DEBUG_LOG_FILE, False)
install_crash_handler()

def obfuscate(data_str, key=140):
    if not data_str: return ""
    return "".join(chr(ord(c) ^ key) for c in data_str)

def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        is_running = False
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            STILL_ACTIVE = 259
            is_running = (exit_code.value == STILL_ACTIVE)
        kernel32.CloseHandle(handle)
        return is_running
    except Exception:
        return False

def check_single_instance():
    global lock_file_handle
    try:
        if os.path.exists(LOCK_FILE):
            # Check if previous PID recorded in lock file is still running
            try:
                with open(LOCK_FILE, 'r') as f:
                    old_pid = int(f.read().strip())
                if is_pid_running(old_pid):
                    return False
            except Exception:
                pass
            # Old PID is no longer running; safe to remove stale lock file
            try:
                os.remove(LOCK_FILE)
            except Exception:
                return False
        lock_file_handle = open(LOCK_FILE, 'w')
        lock_file_handle.write(str(os.getpid()))
        lock_file_handle.flush()
        return True
    except Exception:
        return False

def set_autostart_registry(enable: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        )
        app_name = "HotKeyOverlayAlert"
        if enable:
            if getattr(sys, "frozen", False):
                exe_path = f'"{sys.executable}"'
            else:
                exe_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
            log_debug("SYSTEM", f"Set Windows startup registry key to: {exe_path}")
        else:
            try:
                winreg.DeleteValue(key, app_name)
                log_debug("SYSTEM", "Removed Windows startup registry key")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        log_debug("SYSTEM", f"Error updating Windows autostart registry: {e}")
        return False

def is_autostart_registry_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_QUERY_VALUE
        )
        val, _ = winreg.QueryValueEx(key, "HotKeyOverlayAlert")
        winreg.CloseKey(key)
        return bool(val)
    except Exception:
        return False

class HotkeySignaler(QObject):
    trigger = pyqtSignal(int)

class HUDToastNotification(QMainWindow):
    def __init__(self, message, is_success=True, target_screen=None):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool | 
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowIcon(get_app_icon())

        container = QWidget(self)
        container.setObjectName("ToastContainer")

        border_color = "#9146ff" if is_success else "#ff5555"
        icon_symbol = "🟣" if is_success else "⚠️"
        header_text = "TWITCH ACTION SUCCESS" if is_success else "TWITCH ALERT"
        msg_lower = message.lower()
        if "marker" in msg_lower:
            header_text = "STREAM MARKER CREATED" if is_success else "STREAM MARKER (OFFLINE)"
        elif "announcement" in msg_lower:
            header_text = "CHAT ANNOUNCEMENT SENT" if is_success else "ANNOUNCEMENT NOTICE"
        elif "shoutout" in msg_lower:
            header_text = "SHOUTOUT CARD SENT" if is_success else "SHOUTOUT NOTICE"
        elif "cooldown" in msg_lower or "429" in msg_lower:
            header_text = "TWITCH COOLDOWN NOTICE"
            border_color = "#ffaa00"
            icon_symbol = "⏳"

        container.setStyleSheet(f"""
            QWidget#ToastContainer {{
                background-color: rgba(24, 24, 27, 240);
                border: 2px solid {border_color};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(4)

        lbl_hdr = QLabel(f"{icon_symbol} {header_text}")
        lbl_hdr.setStyleSheet(f"color: {border_color}; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        layout.addWidget(lbl_hdr)

        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: 500;")
        layout.addWidget(lbl_msg)

        self.setCentralWidget(container)
        self.adjustSize()
        self.setFixedWidth(max(380, min(520, self.sizeHint().width() + 40)))

        screens = QApplication.screens()
        screen = target_screen if target_screen in screens else QApplication.primaryScreen()
        if screen:
            geom = screen.geometry()
            x = geom.x() + (geom.width() - self.width()) // 2
            y = geom.y() + 45
            self.move(x, y)

        self.fade_timer = QTimer(self)
        self.opacity = 1.0
        QTimer.singleShot(4000, self.start_fade_out)

    def start_fade_out(self):
        self.fade_timer.timeout.connect(self._fade_step)
        self.fade_timer.start(30)

    def _fade_step(self):
        self.opacity -= 0.08
        if self.opacity <= 0.05:
            self.fade_timer.stop()
            self.close()
        else:
            self.setWindowOpacity(self.opacity)

class TextInputOverlay(QMainWindow):
    def __init__(self, command, parent_overlay):
        super().__init__()
        self.cmd = command
        self.overlay = parent_overlay
        self.setGeometry(self.overlay.geometry())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowIcon(get_app_icon())

        # Translucent backdrop covering entire target monitor
        backdrop = QWidget(self)
        backdrop.setStyleSheet("background-color: rgba(0, 0, 0, 160);")
        backdrop_layout = QVBoxLayout(backdrop)
        backdrop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        backdrop_layout.setContentsMargins(0, 0, 0, 0)

        # Centered Modal Card
        self.card = QWidget(backdrop)
        self.card.setObjectName("ActionCard")
        self.card.setFixedWidth(500)
        self.card.setStyleSheet("""
            QWidget#ActionCard {
                background-color: #18181b;
                border: 2px solid #9146ff;
                border-radius: 12px;
            }
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(14)

        lbl_header = QLabel("EXECUTE TWITCH ACTION")
        lbl_header.setStyleSheet("color: #adadb8; font-size: 13px; font-weight: bold; letter-spacing: 1px;")
        card_layout.addWidget(lbl_header)

        lbl_cmd = QLabel(self.cmd)
        lbl_cmd.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: bold;")
        lbl_cmd.setWordWrap(True)
        card_layout.addWidget(lbl_cmd)

        self.input_field = QLineEdit()
        self.input_field.setMaxLength(140)
        placeholder = "Enter target username..." if "[username]" in self.cmd else "Enter optional description..."
        self.input_field.setPlaceholderText(placeholder)
        self.input_field.setStyleSheet("""
            QLineEdit {
                font-size: 16px;
                padding: 10px 14px;
                color: #efeff1;
                background-color: #0e0e10;
                border: 1px solid #464649;
                border-radius: 6px;
            }
            QLineEdit:focus {
                border: 2px solid #9146ff;
            }
        """)
        self.input_field.installEventFilter(self)
        self.input_field.returnPressed.connect(self.submit)
        card_layout.addWidget(self.input_field)

        lbl_hint = QLabel("Press <b>Enter</b> to submit &nbsp;•&nbsp; Press <b>Esc</b> to close")
        lbl_hint.setTextFormat(Qt.TextFormat.RichText)
        lbl_hint.setStyleSheet("color: #adadb8; font-size: 12px;")
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(lbl_hint)

        backdrop_layout.addWidget(self.card)
        self.setCentralWidget(backdrop)

    def showEvent(self, event):
        super().showEvent(event)
        self._force_field_focus()
        QTimer.singleShot(40, self._force_field_focus)
        QTimer.singleShot(120, self._force_field_focus)

    def _force_field_focus(self):
        self.activateWindow()
        self.raise_()
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.SetActiveWindow(hwnd)
            except Exception:
                pass
        self.input_field.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.input_field.selectAll()

    def submit(self):
        val = self.input_field.text().strip()
        if not val and "marker" in self.cmd.lower():
            val = self.overlay.twitch_channel
        log_debug("INPUT", f"Text input prompt submitted: cmd='{self.cmd}', value='{val}'")
        self.overlay.dispatch_twitch_call(self.cmd, val)
        self.close()

    def mousePressEvent(self, event):
        # Click outside the card closes the overlay
        if hasattr(self, "card") and not self.card.geometry().contains(event.pos()):
            log_debug("INPUT", f"Text input prompt clicked outside/closed for '{self.cmd}'")
            self.close()
        else:
            super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if obj == self.input_field and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                log_debug("INPUT", f"Text input prompt dismissed with Escape for '{self.cmd}'")
                self.close()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            log_debug("INPUT", f"Text input prompt dismissed with Escape for '{self.cmd}'")
            self.close()
        elif event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            self.submit()
        else:
            super().keyPressEvent(event)

class StandardInputModal(QDialog):
    def __init__(self, command, parent_overlay):
        super().__init__()
        self.cmd = command
        self.overlay = parent_overlay
        self.setWindowTitle("Twitch Action - Input Required")
        self.setWindowIcon(get_app_icon())
        self.setFixedSize(450, 200)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        prompt_title = "<b>Execute Twitch Action</b>"
        placeholder = "Enter text..."
        if "[username]" in self.cmd.lower() or "shoutout" in self.cmd.lower():
            prompt_title = f"<b>Enter Target Twitch Username:</b><br><span style='color: gray; font-size: 12px;'>Action: {self.cmd}</span>"
            placeholder = "e.g. streamer_name"
        elif "announce" in self.cmd.lower():
            prompt_title = f"<b>Enter Chat Announcement Message:</b><br><span style='color: gray; font-size: 12px;'>Action: {self.cmd}</span>"
            placeholder = "e.g. Stream starting soon!"
        elif "marker" in self.cmd.lower():
            prompt_title = f"<b>Enter Stream Marker Description:</b><br><span style='color: gray; font-size: 12px;'>Action: {self.cmd}</span>"
            placeholder = "e.g. Epic boss victory"

        lbl = QLabel(prompt_title)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setStyleSheet("font-size: 14px;")
        layout.addWidget(lbl)

        self.input_field = QLineEdit()
        self.input_field.setMaxLength(140)
        self.input_field.setPlaceholderText(placeholder)
        self.input_field.setStyleSheet("font-size: 15px; padding: 6px 10px;")
        self.input_field.returnPressed.connect(self.submit)
        layout.addWidget(self.input_field)

        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_submit = QPushButton("Submit Action")
        self.btn_submit.setStyleSheet("background-color: #9146ff; color: white; font-weight: bold; padding: 6px 16px; border-radius: 4px;")
        self.btn_submit.clicked.connect(self.submit)
        
        btn_box.addStretch()
        btn_box.addWidget(self.btn_cancel)
        btn_box.addWidget(self.btn_submit)
        layout.addLayout(btn_box)

    def showEvent(self, event):
        super().showEvent(event)
        self.input_field.setFocus()
        self.input_field.selectAll()

    def submit(self):
        val = self.input_field.text().strip()
        if not val and "marker" in self.cmd.lower():
            val = self.overlay.twitch_channel
        log_debug("INPUT", f"Standard desktop modal submitted: cmd='{self.cmd}', value='{val}'")
        self.overlay.dispatch_twitch_call(self.cmd, val)
        self.accept()

class IdentificationOverlay(QMainWindow):
    def __init__(self, number, geometry):
        super().__init__()
        self.setGeometry(geometry)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        lbl = QLabel(f"MONITOR #{number}", self)
        lbl.setStyleSheet("font-size: 72px; color: white; background: rgba(0,0,0,180); padding: 20px;")
        self.setCentralWidget(lbl)
        QTimer.singleShot(3000, self.close)

class RedBorderOverlay(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.app_dir = APP_DIR
        
        # Check first run status before loading settings or writing files
        self.is_first_run = not os.path.exists(CONFIG_FILE)
        
        self.load_settings()
        self.is_visible = False
        self.id_windows = []
        self.current_toast = None
        
        self.update_monitor_geometry(self.target_monitor_index)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowIcon(get_app_icon())
        
        self.signaler = HotkeySignaler()
        self.signaler.trigger.connect(lambda: self.toggle_visibility())
        self._bound_activation_hotkey = ""
        self.rebind_activation_hotkey()
        
        self.macro_signaler = HotkeySignaler()
        self.macro_signaler.trigger.connect(self.evaluate_macro_trigger)
        
        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self.process_flash_step)
        self.flash_direction = -1
        self.init_system_tray()
        self.settings_window = SettingsWindow(self)
        self.rebind_twitch_macros()
        
        if self.is_first_run:
            QTimer.singleShot(200, self.show_welcome_message)

        if getattr(self, "check_updates_on_startup", True):
            QTimer.singleShot(4000, self.run_startup_update_check)

        if getattr(self, "start_on_boot", False):
            set_autostart_registry(True)

    def load_settings(self):
        self.target_monitor_index = 0
        self.border_thickness = 10
        self.border_color = QColor(255, 0, 0)
        self.border_opacity = 1.0
        self.is_flashing = False
        self.flash_speed_name = "Squirrel"
        self.activation_hotkey = "ctrl+add"
        self.primary_hotkey_enabled = True
        self.start_on_boot = False
        self.streamer_mode = True
        self.debug_mode = False
        self.check_updates_on_startup = True
        self.auto_update_enabled = False
        self.twitch_channel = "thawizanator"
        self.twitch_client_id = "09inz20qnc8wbc7qemz9jl6kqf8iad"
        self.twitch_redirect_uri = "http://localhost:17563"
        self.twitch_user_id = ""
        self.twitch_display_name = ""
        self.twitch_token = ""
        self.twitch_macros = []

        cfg_to_read = None
        if os.path.exists(CONFIG_FILE):
            cfg_to_read = CONFIG_FILE
        elif os.path.exists(LOCAL_CONFIG_FILE):
            cfg_to_read = LOCAL_CONFIG_FILE

        if cfg_to_read:
            try:
                with open(cfg_to_read, 'r') as f:
                    d = json.load(f)
                    self.target_monitor_index = d.get("monitor_index", 0)
                    self.border_thickness = d.get("thickness", 10)
                    self.border_color = QColor(d.get("color", "#ff0000"))
                    self.border_opacity = d.get("opacity", 1.0)
                    self.is_flashing = d.get("is_flashing", False)
                    self.flash_speed_name = d.get("flash_speed_name", "Squirrel")
                    self.activation_hotkey = normalize_hotkey(d.get("activation_hotkey", "ctrl+add"))
                    self.primary_hotkey_enabled = d.get("primary_hotkey_enabled", True)
                    self.start_on_boot = d.get("start_on_boot", False)
                    self.streamer_mode = d.get("streamer_mode", True)
                    self.debug_mode = d.get("debug_mode", False)
                    self.check_updates_on_startup = d.get("check_updates_on_startup", True)
                    self.auto_update_enabled = d.get("auto_update_enabled", False)
                    set_debug_mode(self.debug_mode)
                    loaded_client_id = d.get("twitch_client_id", self.twitch_client_id)
                    if loaded_client_id and loaded_client_id != "testclientid":
                        self.twitch_client_id = loaded_client_id
                    else:
                        self.twitch_client_id = "09inz20qnc8wbc7qemz9jl6kqf8iad"
                    self.twitch_redirect_uri = d.get("twitch_redirect_uri", "http://localhost:17563")
                    self.twitch_user_id = str(d.get("twitch_user_id", ""))
                    self.twitch_display_name = d.get("twitch_display_name", "")
                    self.twitch_token = obfuscate(d.get("twitch_token_obf", ""))
                    self.twitch_macros = d.get("twitch_macros", [])
                    for m in self.twitch_macros:
                        if isinstance(m, dict):
                            if "hotkey" in m:
                                m["hotkey"] = normalize_hotkey(m["hotkey"])
                            if m.get("command") == "/marker":
                                m["command"] = "/marker [username]"
            except Exception as e:
                print(f"Error loading configuration: {e}")

    def save_settings(self):
        for m in self.twitch_macros:
            if isinstance(m, dict):
                if "hotkey" in m:
                    m["hotkey"] = normalize_hotkey(m["hotkey"])
                if m.get("command") == "/marker":
                    m["command"] = "/marker [username]"

        d = {
            "monitor_index": self.target_monitor_index,
            "thickness": self.border_thickness,
            "color": self.border_color.name(),
            "opacity": self.border_opacity,
            "is_flashing": self.is_flashing,
            "flash_speed_name": self.flash_speed_name,
            "activation_hotkey": normalize_hotkey(self.activation_hotkey),
            "primary_hotkey_enabled": self.primary_hotkey_enabled,
            "start_on_boot": self.start_on_boot,
            "streamer_mode": self.streamer_mode,
            "debug_mode": self.debug_mode,
            "check_updates_on_startup": self.check_updates_on_startup,
            "auto_update_enabled": self.auto_update_enabled,
            "twitch_channel": self.twitch_channel,
            "twitch_client_id": self.twitch_client_id,
            "twitch_redirect_uri": self.twitch_redirect_uri,
            "twitch_user_id": self.twitch_user_id,
            "twitch_display_name": self.twitch_display_name,
            "twitch_token_obf": obfuscate(self.twitch_token),
            "twitch_macros": self.twitch_macros
        }
        # Save to primary APPDATA location
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(d, f, indent=4)
        except Exception as e:
            print(f"Error saving APPDATA config: {e}")

        # Also keep local directory config.json synchronized if writable
        try:
            with open(LOCAL_CONFIG_FILE, 'w') as f:
                json.dump(d, f, indent=4)
        except Exception:
            pass

    def set_streamer_mode(self, enabled):
        self.streamer_mode = bool(enabled)
        self.save_settings()
        log_debug("SYSTEM", f"Streamer mode toggled: {'ENABLED' if self.streamer_mode else 'DISABLED'}")

    def set_debug_mode(self, enabled):
        self.debug_mode = bool(enabled)
        set_debug_mode(self.debug_mode)
        self.save_settings()
        log_debug("SYSTEM", f"Debug logging toggled: {'ENABLED' if self.debug_mode else 'DISABLED'}")

    def set_update_settings(self, check_on_startup=None, auto_update=None):
        if check_on_startup is not None:
            self.check_updates_on_startup = bool(check_on_startup)
        if auto_update is not None:
            self.auto_update_enabled = bool(auto_update)
        self.save_settings()
        log_debug("SYSTEM", f"Update settings saved: check_on_startup={self.check_updates_on_startup}, auto_update={self.auto_update_enabled}")

    def run_startup_update_check(self):
        log_debug("UPDATER", "Running startup update check...")
        self.startup_check_worker = UpdateCheckWorker(CURRENT_VERSION)
        self.startup_check_worker.update_available.connect(self.on_startup_update_found)
        self.startup_check_worker.start()

    def on_startup_update_found(self, latest_tag, release_url, download_url, notes):
        log_debug("UPDATER", f"Startup check found update: {latest_tag}")
        if self.auto_update_enabled and download_url:
            log_debug("UPDATER", f"Auto-update enabled. Starting background download for {latest_tag}...")
            temp_exe = os.path.join(APP_DIR, f"HotKeyOverlayAlert_new_{latest_tag}.exe")
            self.bg_download_worker = DownloadWorker(download_url, temp_exe)
            self.bg_download_worker.finished.connect(lambda p: self.on_bg_download_finished(p, latest_tag))
            self.bg_download_worker.start()
        else:
            msg_box = QMessageBox()
            msg_box.setWindowTitle("Application Update Available")
            msg_box.setWindowIcon(get_app_icon())
            msg_box.setText(
                f"<b>A new version of HotKey Overlay Alert is available!</b><br><br>"
                f"Installed Version: <b>v{CURRENT_VERSION}</b><br>"
                f"Latest Version: <b>{latest_tag}</b><br><br>"
                f"Would you like to download and install this update now?"
            )
            msg_box.setTextFormat(Qt.TextFormat.RichText)
            btn_now = msg_box.addButton("Download Now", QMessageBox.ButtonRole.AcceptRole)
            btn_later = msg_box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(btn_now)
            msg_box.exec()

            if msg_box.clickedButton() == btn_now:
                self.open_settings()
                if hasattr(self.settings_window, "tabs"):
                    self.settings_window.tabs.setCurrentIndex(4)  # System tab
                if hasattr(self.settings_window, "tab_system"):
                    self.settings_window.tab_system.latest_tag = latest_tag
                    self.settings_window.tab_system.latest_download_url = download_url
                    self.settings_window.tab_system.latest_release_url = release_url
                    self.settings_window.tab_system.lbl_update_status.setText(f"<span style='color: #57F287; font-weight: bold;'>🎉 Update Available: {latest_tag}!</span>")
                    if download_url:
                        self.settings_window.tab_system.btn_download_update.setText(f"🚀 Download && Install Update ({latest_tag})")
                        self.settings_window.tab_system.btn_download_update.setVisible(True)
                        self.settings_window.tab_system.btn_download_update.setEnabled(True)
                        self.settings_window.tab_system.download_update_clicked()

    def on_bg_download_finished(self, downloaded_path, tag):
        log_debug("UPDATER", f"Background download completed: {downloaded_path}")
        msg_box = QMessageBox()
        msg_box.setWindowTitle("Update Ready to Install")
        msg_box.setWindowIcon(get_app_icon())
        msg_box.setText(
            f"<b>Update {tag} has been downloaded automatically!</b><br><br>"
            f"The application needs to restart to apply the new version.<br><br>"
            f"Restart now?"
        )
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        btn_restart = msg_box.addButton("Restart Now", QMessageBox.ButtonRole.AcceptRole)
        btn_later = msg_box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(btn_restart)
        msg_box.exec()

        if msg_box.clickedButton() == btn_restart:
            ok, msg = apply_update_and_restart(downloaded_path)
            if ok:
                self.close_application()
            else:
                QMessageBox.information(None, "Update Note", f"{msg}\n\nDownloaded update saved to:\n{downloaded_path}")

    def open_debug_log(self):
        try:
            if not os.path.exists(DEBUG_LOG_FILE):
                with open(DEBUG_LOG_FILE, "w", encoding="utf-8") as f:
                    f.write(f"=== HotKey Overlay Alert Debug Log (v{CURRENT_VERSION}) ===\n")
            os.startfile(DEBUG_LOG_FILE)
            log_debug("SYSTEM", "Opened debug.txt in default viewer")
        except Exception as e:
            print(f"Error opening debug log: {e}")

    def open_crash_log(self):
        try:
            from debug_logger import get_crash_log_path
            p = get_crash_log_path()
            if p:
                if not os.path.exists(p):
                    with open(p, "w", encoding="utf-8") as f:
                        f.write("=== HotKey Overlay Alert Crash Log ===\nNo crashes recorded.\n")
                os.startfile(p)
                log_debug("SYSTEM", "Opened crash_log.txt in default viewer")
        except Exception as e:
            print(f"Error opening crash log: {e}")

    def set_primary_hotkey_enabled(self, enabled):
        self.primary_hotkey_enabled = bool(enabled)
        self.rebind_activation_hotkey()
        self.save_settings()
        log_debug("SYSTEM", f"Primary highlight hotkey toggled: {'ENABLED' if self.primary_hotkey_enabled else 'DISABLED'}")

    def set_start_on_boot(self, enabled):
        self.start_on_boot = bool(enabled)
        set_autostart_registry(self.start_on_boot)
        self.save_settings()
        log_debug("SYSTEM", f"Windows startup auto-launch toggled: {'ENABLED' if self.start_on_boot else 'DISABLED'}")

    def rebind_activation_hotkey(self, new_hotkey=None):
        if new_hotkey is not None:
            self.activation_hotkey = normalize_hotkey(new_hotkey)

        if hasattr(self, "_bound_activation_hotkey") and self._bound_activation_hotkey:
            try:
                keyboard.remove_hotkey(self._bound_activation_hotkey)
            except Exception:
                pass
            self._bound_activation_hotkey = ""

        if self.primary_hotkey_enabled and self.activation_hotkey:
            try:
                keyboard.add_hotkey(self.activation_hotkey, lambda: self.signaler.trigger.emit(0))
                self._bound_activation_hotkey = self.activation_hotkey
                log_debug("HOTKEY", f"Primary activation hotkey bound: '{self.activation_hotkey}'")
            except Exception as e:
                print(f"Warning: Could not bind activation hotkey '{self.activation_hotkey}': {e}")
                self._bound_activation_hotkey = ""
        else:
            self._bound_activation_hotkey = ""
            log_debug("HOTKEY", "Primary activation hotkey is disabled or empty")

    def rebind_twitch_macros(self):
        for m in self.twitch_macros:
            try:
                raw_hk = m.get("hotkey", "")
                if raw_hk:
                    keyboard.remove_hotkey(raw_hk)
            except Exception:
                pass

        for i, m in enumerate(self.twitch_macros):
            hk = m.get("hotkey", "")
            if hk and hk not in ["set hotkey...", "Press Key...", "Press key(s)..."]:
                norm_hk = normalize_hotkey(hk)
                m["hotkey"] = norm_hk
                try:
                    keyboard.add_hotkey(norm_hk, lambda idx=i: self.macro_signaler.trigger.emit(idx))
                except Exception as e:
                    print(f"Warning: Could not bind macro hotkey '{norm_hk}': {e}")

    def evaluate_macro_trigger(self, slot_index):
        if slot_index >= len(self.twitch_macros): return
        cmd = self.twitch_macros[slot_index]["command"]
        log_debug("MACRO", f"Triggered macro slot {slot_index}: command='{cmd}'")
        if cmd in ["/marker [username]", "/marker"]:
            # Drop marker using streamer's username as description without interrupting gameplay
            self.dispatch_twitch_call(cmd, self.twitch_channel)
        elif "[description]" in cmd or "[username]" in cmd:
            if self.streamer_mode:
                log_debug("INPUT", f"Showing transparent in-game HUD overlay for command='{cmd}'")
                self.input_ui = TextInputOverlay(cmd, self)
                self.input_ui.show()
            else:
                log_debug("INPUT", f"Showing standard desktop modal dialog for command='{cmd}'")
                self.modal_ui = StandardInputModal(cmd, self)
                self.modal_ui.exec()
        else:
            self.dispatch_twitch_call(cmd, "")

    def dispatch_twitch_call(self, command, argument):
        log_debug("TWITCH", f"Dispatching command='{command}', argument='{argument}' (channel='{self.twitch_channel}', user_id='{self.twitch_user_id}')")
        self.worker = TwitchCommandWorker(
            command=command,
            argument=argument,
            token=self.twitch_token,
            client_id=self.twitch_client_id,
            channel_name=self.twitch_channel,
            user_id=self.twitch_user_id
        )
        self.worker.result_signal.connect(self.on_twitch_worker_result)
        self.worker.start()

    def show_hud_toast(self, message, is_success):
        try:
            if hasattr(self, "current_toast") and self.current_toast:
                try:
                    self.current_toast.close()
                except Exception:
                    pass
            screens = QApplication.screens()
            target_screen = screens[self.target_monitor_index] if self.target_monitor_index < len(screens) else QApplication.primaryScreen()
            self.current_toast = HUDToastNotification(message, is_success, target_screen)
            self.current_toast.show()
        except Exception as e:
            print(f"Toast display notice: {e}")

    def on_twitch_worker_result(self, message, is_success):
        log_debug("TWITCH_RESPONSE", f"Success={is_success} | message='{message}'")
        if self.streamer_mode:
            self.show_hud_toast(message, is_success)
        else:
            icon = QMessageBox.Icon.Information if is_success else QMessageBox.Icon.Warning
            title = "Twitch Action Complete" if is_success else "Twitch Action Notice"
            msg_box = QMessageBox(icon, title, message)
            msg_box.setWindowIcon(get_app_icon())
            msg_box.setText(f"<b>{title}</b><br><br>{message}")
            msg_box.setTextFormat(Qt.TextFormat.RichText)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

        icon = QSystemTrayIcon.MessageIcon.Information if is_success else QSystemTrayIcon.MessageIcon.Warning
        if hasattr(self, "tray_icon") and self.tray_icon.isVisible():
            self.tray_icon.showMessage("HotKey Overlay Alert - Twitch", message, icon, 4000)

    def show_welcome_message(self):
        msg = QMessageBox()
        msg.setWindowTitle("HotKey Overlay Alert Loaded")
        msg.setWindowIcon(get_app_icon())
        formatted_hk = format_hotkey_display(self.activation_hotkey)
        msg.setText(
            "<b>Thanks for using the Hotkey Overlay Alert!</b><br><br>"
            "The program is now active and running quietly in your background. You can "
            "find it anytime down in your taskbar's hidden system tray drawer (click the little "
            "<b>^</b> arrow near your system clock).<br><br>"
            "Right-clicking the **wizanator icon** will allow you to access the setup menu, change "
            "your active monitor layout, or adjust animation parameters.<br><br>"
            f"Activation Hotkey: <b>{formatted_hk}</b>"
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.exec()
        self.save_settings()

    def update_flash_speed(self, name):
        self.flash_speed_name = name
        self.save_settings()
        if self.is_visible:
            if name == "Always On": self.flash_timer.stop(); self.setWindowOpacity(self.border_opacity)
            elif self.is_flashing: self.flash_timer.start(30)

    def init_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_app_icon())
        self.tray_menu = QMenu()
        self.settings_action = QAction("Settings", self)
        self.settings_action.triggered.connect(self.open_settings)
        self.tray_menu.addAction(self.settings_action)
        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.close_application)
        self.tray_menu.addAction(self.exit_action)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

    def update_monitor_geometry(self, idx):
        screens = QApplication.screens()
        if idx < len(screens):
            self.setGeometry(screens[idx].geometry())
            self.update()

    def identify_monitors(self):
        self.id_windows.clear()
        for i, s in enumerate(QApplication.screens()):
            win = IdentificationOverlay(i + 1, s.geometry())
            win.show()
            self.id_windows.append(win)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(self.border_color, self.border_thickness))
        offset = self.border_thickness // 2
        painter.drawRect(offset, offset, self.width() - self.border_thickness, self.height() - self.border_thickness)

    def toggle_visibility(self):
        if self.is_visible:
            self.hide()
            self.flash_timer.stop()
            log_debug("OVERLAY", "Overlay hidden")
        else:
            self.setWindowOpacity(self.border_opacity)
            self.show()
            self.raise_()
            if self.is_flashing and self.flash_speed_name != "Always On":
                self.flash_timer.start(30)
            log_debug("OVERLAY", f"Overlay displayed on monitor #{self.target_monitor_index + 1} (thickness={self.border_thickness}, opacity={self.border_opacity}, flashing={self.is_flashing})")
        self.is_visible = not self.is_visible

    def start_flash(self):
        self.is_flashing = True
        if self.is_visible and self.flash_speed_name != "Always On":
            self.flash_timer.start(30)

    def stop_flash(self):
        self.is_flashing = False
        self.flash_timer.stop()
        if self.is_visible:
            self.setWindowOpacity(self.border_opacity)

    def process_flash_step(self):
        if self.flash_speed_name == "Always On":
            return
        cur = self.windowOpacity()
        new_op = cur + (self.flash_direction * SPEED_MAPPING.get(self.flash_speed_name, 0.04))
        if new_op <= 0.15:
            new_op = 0.15
            self.flash_direction = 1
        elif new_op >= self.border_opacity:
            new_op = self.border_opacity
            self.flash_direction = -1
        self.setWindowOpacity(new_op)

    def open_settings(self):
        if hasattr(self.settings_window, "tab_monitor"):
            self.settings_window.tab_monitor.refresh_monitors()
            self.settings_window.tab_monitor.monitor_combo.setCurrentIndex(self.target_monitor_index)
        elif hasattr(self.settings_window, "view_visual"):
            self.settings_window.view_visual.monitor_combo.setCurrentIndex(self.target_monitor_index)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def close_application(self):
        global lock_file_handle
        keyboard.unhook_all()
        self.tray_icon.hide()
        self.settings_window.close()
        if lock_file_handle:
            lock_file_handle.close()
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass
        self.app.quit()

if __name__ == '__main__':
    # Ensure Windows Taskbar displays the application icon instead of Python's default icon
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("thawizanator.hotkeyoverlayalert.app.2.3.9")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setWindowIcon(get_app_icon())

    if not check_single_instance():
        msg = QMessageBox()
        msg.setWindowIcon(get_app_icon())
        msg.setText("Application is already running! Check hidden system tray icons.")
        msg.exec()
        sys.exit(0)
    app.setQuitOnLastWindowClosed(False)
    overlay = RedBorderOverlay(app)
    sys.exit(app.exec())