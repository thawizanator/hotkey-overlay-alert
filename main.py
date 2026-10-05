import sys
import os
import json
import keyboard

# Ensure Windows Taskbar displays the application icon instead of Python's default icon
if sys.platform == "win32":
    try:
        import ctypes
        app_user_model_id = "thawizanator.hotkeyoverlayalert.app.2.1"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_user_model_id)
    except Exception:
        pass

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QSystemTrayIcon, QMenu, QWidget, QVBoxLayout, QLabel, QLineEdit, QMessageBox
from PyQt6.QtGui import QPainter, QPen, QColor, QIcon, QAction, QPixmap

# Import components from our other local workspace files
from twitch_worker import TwitchCommandWorker
from settings_ui import SettingsWindow, SPEED_MAPPING, normalize_hotkey, format_hotkey_display, ICON_PATH, get_app_icon

def get_app_directory():
    appdata_root = os.environ.get("APPDATA") or os.path.expanduser("~")
    app_folder = os.path.join(appdata_root, "ThaWizanator_Overlay")
    if not os.path.exists(app_folder): 
        os.makedirs(app_folder)
    return app_folder

APP_DIR = get_app_directory()
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
LOCK_FILE = os.path.join(APP_DIR, "app.lock")
lock_file_handle = None

def obfuscate(data_str, key=140):
    if not data_str: return ""
    return "".join(chr(ord(c) ^ key) for c in data_str)

def check_single_instance():
    global lock_file_handle
    try:
        if os.path.exists(LOCK_FILE):
            try: os.remove(LOCK_FILE)
            except Exception: return False
        lock_file_handle = open(LOCK_FILE, 'w')
        lock_file_handle.write(str(os.getpid()))
        lock_file_handle.flush()
        return True
    except Exception: return False

class HotkeySignaler(QObject):
    trigger = pyqtSignal(int)

class TextInputOverlay(QMainWindow):
    def __init__(self, command, parent_overlay):
        super().__init__()
        self.cmd = command
        self.overlay = parent_overlay
        self.setGeometry(self.overlay.geometry())
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
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
        self.input_field.setPlaceholderText("Enter optional description...")
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
        self.activateWindow()
        self.raise_()
        self.input_field.setFocus()
        QTimer.singleShot(30, self.input_field.setFocus)

    def submit(self):
        self.overlay.dispatch_twitch_call(self.cmd, self.input_field.text().strip())
        self.close()

    def mousePressEvent(self, event):
        # Click outside the card closes the overlay
        if hasattr(self, "card") and not self.card.geometry().contains(event.pos()):
            self.close()
        else:
            super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if obj == self.input_field and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            self.submit()
        else:
            super().keyPressEvent(event)

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
        
        # Check first run status before loading settings or writing files
        self.is_first_run = not os.path.exists(CONFIG_FILE)
        
        self.load_settings()
        self.is_visible = False
        self.id_windows = []
        
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

    def load_settings(self):
        self.target_monitor_index = 0
        self.border_thickness = 10
        self.border_color = QColor(255, 0, 0)
        self.border_opacity = 1.0
        self.is_flashing = False
        self.flash_speed_name = "Squirrel"
        self.activation_hotkey = "ctrl+add"
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
                        if isinstance(m, dict) and "hotkey" in m:
                            m["hotkey"] = normalize_hotkey(m["hotkey"])
            except Exception as e:
                print(f"Error loading configuration: {e}")

    def save_settings(self):
        for m in self.twitch_macros:
            if isinstance(m, dict) and "hotkey" in m:
                m["hotkey"] = normalize_hotkey(m["hotkey"])

        d = {
            "monitor_index": self.target_monitor_index,
            "thickness": self.border_thickness,
            "color": self.border_color.name(),
            "opacity": self.border_opacity,
            "is_flashing": self.is_flashing,
            "flash_speed_name": self.flash_speed_name,
            "activation_hotkey": normalize_hotkey(self.activation_hotkey),
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

    def rebind_activation_hotkey(self, new_hotkey=None):
        if new_hotkey is not None:
            self.activation_hotkey = normalize_hotkey(new_hotkey)

        if hasattr(self, "_bound_activation_hotkey") and self._bound_activation_hotkey:
            try:
                keyboard.remove_hotkey(self._bound_activation_hotkey)
            except Exception:
                pass

        if self.activation_hotkey:
            try:
                keyboard.add_hotkey(self.activation_hotkey, lambda: self.signaler.trigger.emit(0))
                self._bound_activation_hotkey = self.activation_hotkey
            except Exception as e:
                print(f"Warning: Could not bind activation hotkey '{self.activation_hotkey}': {e}")
                self._bound_activation_hotkey = ""
        else:
            self._bound_activation_hotkey = ""

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
        if "[description]" in cmd or "[username]" in cmd:
            self.input_ui = TextInputOverlay(cmd, self)
            self.input_ui.show()
        else: self.dispatch_twitch_call(cmd, "")

    def dispatch_twitch_call(self, command, argument):
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

    def on_twitch_worker_result(self, message, is_success):
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
        else:
            self.setWindowOpacity(self.border_opacity)
            self.show()
            self.raise_()
            if self.is_flashing and self.flash_speed_name != "Always On":
                self.flash_timer.start(30)
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
        self.settings_window.view_visual.monitor_combo.setCurrentIndex(self.target_monitor_index)
        self.settings_window.show()

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
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("thawizanator.hotkeyoverlayalert.app.2.1")
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