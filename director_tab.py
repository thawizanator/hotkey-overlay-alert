import os
import sys
import subprocess
import webbrowser
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QGroupBox, QListWidget, QListWidgetItem,
    QMessageBox, QDialog, QInputDialog, QColorDialog, QFormLayout, QScrollArea, QFrame,
    QCheckBox
)
from PyQt6.QtGui import QColor, QIcon

from director_panel import DirectorPanelWindow
import theme_manager
from debug_logger import log_debug

def obfuscate_str(data_str: str, key: int = 140) -> str:
    if not data_str:
        return ""
    return "".join(chr(ord(c) ^ key) for c in data_str)

class SceneEditDialog(QDialog):
    """Dialog to add or modify a scene card."""
    def __init__(self, name="New Scene", color_hex="#22c55e", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Scene Card")
        self.setFixedSize(320, 160)
        self.chosen_color = color_hex

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        self.edit_name = QLineEdit(name)
        form.addRow("Scene Name:", self.edit_name)

        btn_row = QHBoxLayout()
        self.lbl_color_preview = QLabel("   ")
        self.lbl_color_preview.setFixedSize(30, 24)
        self._update_color_preview()

        self.btn_pick_color = QPushButton("Choose Color...")
        self.btn_pick_color.clicked.connect(self._pick_color)
        btn_row.addWidget(self.lbl_color_preview)
        btn_row.addWidget(self.btn_pick_color)
        btn_row.addStretch()
        form.addRow("Border Color:", btn_row)
        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def _pick_color(self):
        col = QColorDialog.getColor(QColor(self.chosen_color), self, "Select Scene Border Color")
        if col.isValid():
            self.chosen_color = col.name()
            self._update_color_preview()

    def _update_color_preview(self):
        self.lbl_color_preview.setStyleSheet(f"background-color: {self.chosen_color}; border: 1px solid #ffffff; border-radius: 4px;")

    def get_data(self):
        return self.edit_name.text().strip() or "Untitled Scene", self.chosen_color


class DirectorTab(QWidget):
    """Stream Director Settings Configuration Tab with Master Launch Button."""
    def __init__(self, main_win):
        super().__init__()
        self.main_win = main_win
        self.panel_window = None

        # Data defaults
        self.api_key = ""
        self.stream_url = "https://twitch.tv/thawizanator"
        self.target_monitor_idx = 0
        self.app_mode = True
        self.scenes = [
            {"name": "Scene 1", "color": "#22c55e"},
            {"name": "Scene 2", "color": "#0284c7"},
            {"name": "Scene 3", "color": "#ea580c"},
            {"name": "Scene 4", "color": "#a855f7"},
            {"name": "Scene 5", "color": "#ef4444"},
        ]
        self.audio_toggles = [
            {"name": "Mic", "muted": False},
            {"name": "Game", "muted": False},
            {"name": "Music", "muted": False},
            {"name": "Discord", "muted": False},
            {"name": "Alerts", "muted": False},
            {"name": "SFX", "muted": False},
        ]
        self.faders = [
            {"name": "Mic", "volume": 80},
            {"name": "Game", "volume": 75},
            {"name": "Music", "volume": 60},
        ]

        self._build_ui()
        self.load_from_settings()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # Scroll area for compact height
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(8)

        # ------------------ GROUP 1: REMOTE AUTH & MONITOR ------------------
        grp_conn = QGroupBox("Stream Director Connection & Target Display")
        lay_conn = QVBoxLayout(grp_conn)
        lay_conn.setSpacing(6)

        row_api = QHBoxLayout()
        row_api.addWidget(QLabel("Director API Key:"))
        self.edit_api_key = QLineEdit()
        self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_api_key.setPlaceholderText("Enter streamer's secret token...")
        self.edit_api_key.textChanged.connect(self._on_settings_changed)
        row_api.addWidget(self.edit_api_key, 1)

        self.btn_toggle_key = QPushButton("👁️")
        self.btn_toggle_key.setFixedSize(28, 24)
        self.btn_toggle_key.setToolTip("Show/Hide Key")
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
        row_api.addWidget(self.btn_toggle_key)
        lay_conn.addLayout(row_api)

        row_url = QHBoxLayout()
        row_url.addWidget(QLabel("Stream Live URL:"))
        self.edit_stream_url = QLineEdit(self.stream_url)
        self.edit_stream_url.setPlaceholderText("https://twitch.tv/username")
        self.edit_stream_url.textChanged.connect(self._on_settings_changed)
        row_url.addWidget(self.edit_stream_url, 1)
        lay_conn.addLayout(row_url)

        row_mon = QHBoxLayout()
        row_mon.addWidget(QLabel("Open Panel On Display:"))
        self.combo_monitor = QComboBox()
        self.refresh_monitors_list()
        self.combo_monitor.currentIndexChanged.connect(self._on_settings_changed)
        row_mon.addWidget(self.combo_monitor, 1)
        lay_conn.addLayout(row_mon)

        self.chk_app_mode = QCheckBox("Open stream in dedicated studio window (Chromium App Mode)")
        self.chk_app_mode.setChecked(self.app_mode)
        self.chk_app_mode.setToolTip("Launches Chrome or Edge maximized in clean borderless app mode without address or tab bars.")
        self.chk_app_mode.setStyleSheet("font-size: 11px; color: #e4e4e7; margin-top: 2px;")
        self.chk_app_mode.toggled.connect(self._on_settings_changed)
        lay_conn.addWidget(self.chk_app_mode)

        scroll_layout.addWidget(grp_conn)

        # ------------------ GROUP 2: SCENE TOGGLES (MAX 5) ------------------
        grp_scenes = QGroupBox("Scene Toggles (Limit: 5)")
        lay_sc = QVBoxLayout(grp_scenes)
        lay_sc.setSpacing(4)

        sc_btn_row = QHBoxLayout()
        self.lbl_scene_count = QLabel("Active Scenes: (5 / 5)")
        self.lbl_scene_count.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        sc_btn_row.addWidget(self.lbl_scene_count)
        sc_btn_row.addStretch()

        self.btn_add_scene = QPushButton("➕ Add Scene")
        self.btn_add_scene.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_add_scene.clicked.connect(self._add_scene)
        sc_btn_row.addWidget(self.btn_add_scene)

        self.btn_edit_scene = QPushButton("✏️ Edit")
        self.btn_edit_scene.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_edit_scene.clicked.connect(self._edit_scene)
        sc_btn_row.addWidget(self.btn_edit_scene)

        self.btn_rem_scene = QPushButton("🗑️ Remove")
        self.btn_rem_scene.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_rem_scene.clicked.connect(self._remove_scene)
        sc_btn_row.addWidget(self.btn_rem_scene)
        lay_sc.addLayout(sc_btn_row)

        self.list_scenes = QListWidget()
        self.list_scenes.setFixedHeight(75)
        self.list_scenes.setStyleSheet("font-size: 11px; padding: 2px;")
        lay_sc.addWidget(self.list_scenes)
        scroll_layout.addWidget(grp_scenes)

        # ------------------ GROUP 3: AUDIO MUTE TOGGLES ------------------
        grp_audio = QGroupBox("Audio Mute / Unmute Toggles (Up to 6)")
        lay_au = QVBoxLayout(grp_audio)
        lay_au.setSpacing(4)

        au_btn_row = QHBoxLayout()
        self.lbl_audio_count = QLabel("Active Audio Toggles: (6 / 6)")
        self.lbl_audio_count.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        au_btn_row.addWidget(self.lbl_audio_count)
        au_btn_row.addStretch()

        self.btn_add_audio = QPushButton("➕ Add Source")
        self.btn_add_audio.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_add_audio.clicked.connect(self._add_audio)
        au_btn_row.addWidget(self.btn_add_audio)

        self.btn_edit_audio = QPushButton("✏️ Edit")
        self.btn_edit_audio.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_edit_audio.clicked.connect(self._edit_audio)
        au_btn_row.addWidget(self.btn_edit_audio)

        self.btn_rem_audio = QPushButton("🗑️ Remove")
        self.btn_rem_audio.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.btn_rem_audio.clicked.connect(self._remove_audio)
        au_btn_row.addWidget(self.btn_rem_audio)
        lay_au.addLayout(au_btn_row)

        self.list_audio = QListWidget()
        self.list_audio.setFixedHeight(70)
        self.list_audio.setStyleSheet("font-size: 11px; padding: 2px;")
        lay_au.addWidget(self.list_audio)
        scroll_layout.addWidget(grp_audio)

        # ------------------ GROUP 4: VOLUME FADERS (3 SLIDERS) ------------------
        grp_faders = QGroupBox("Volume Sliders (3 Channels)")
        lay_fd = QHBoxLayout(grp_faders)
        lay_fd.setSpacing(10)

        lay_fd.addWidget(QLabel("Slider 1:"))
        self.edit_fader1 = QLineEdit("Mic")
        self.edit_fader1.textChanged.connect(self._on_settings_changed)
        lay_fd.addWidget(self.edit_fader1)

        lay_fd.addWidget(QLabel("Slider 2:"))
        self.edit_fader2 = QLineEdit("Game")
        self.edit_fader2.textChanged.connect(self._on_settings_changed)
        lay_fd.addWidget(self.edit_fader2)

        lay_fd.addWidget(QLabel("Slider 3:"))
        self.edit_fader3 = QLineEdit("Music")
        self.edit_fader3.textChanged.connect(self._on_settings_changed)
        lay_fd.addWidget(self.edit_fader3)
        scroll_layout.addWidget(grp_faders)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # ------------------ MASTER LAUNCH / CLOSE BUTTON ------------------
        self.btn_launch_panel = QPushButton("🚀 Launch Director Panel")
        self.btn_launch_panel.setObjectName("btnLaunchDirector")
        self.btn_launch_panel.setFixedHeight(36)
        self.btn_launch_panel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_launch_button_state(is_open=False)
        self.btn_launch_panel.clicked.connect(self.toggle_director_panel)
        main_layout.addWidget(self.btn_launch_panel)

    def refresh_monitors_list(self):
        self.combo_monitor.blockSignals(True)
        self.combo_monitor.clear()
        screens = QApplication.screens()
        for i, s in enumerate(screens):
            g = s.geometry()
            name = s.name() or f"Display #{i+1}"
            self.combo_monitor.addItem(f"Monitor #{i+1}: {g.width()}x{g.height()} ({name})", i)
        if 0 <= self.target_monitor_idx < len(screens):
            self.combo_monitor.setCurrentIndex(self.target_monitor_idx)
        self.combo_monitor.blockSignals(False)

    def _toggle_key_visibility(self):
        if self.edit_api_key.echoMode() == QLineEdit.EchoMode.Password:
            self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_key.setText("🔒")
        else:
            self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_key.setText("👁️")

    def _refresh_scene_list_ui(self):
        self.list_scenes.clear()
        for i, s in enumerate(self.scenes):
            it = QListWidgetItem(f"[{i+1}] {s['name']}  (Border: {s['color']})")
            self.list_scenes.addItem(it)
        count = len(self.scenes)
        self.lbl_scene_count.setText(f"Active Scenes: ({count} / 5)")
        self.btn_add_scene.setEnabled(count < 5)

    def _refresh_audio_list_ui(self):
        self.list_audio.clear()
        for i, a in enumerate(self.audio_toggles):
            it = QListWidgetItem(f"[{i+1}] {a['name']}")
            self.list_audio.addItem(it)
        count = len(self.audio_toggles)
        self.lbl_audio_count.setText(f"Active Audio Toggles: ({count} / 6)")
        self.btn_add_audio.setEnabled(count < 6)

    def _add_scene(self):
        if len(self.scenes) >= 5:
            QMessageBox.information(self, "Limit Reached", "A maximum of 5 scenes can be configured on the panel.")
            return
        dlg = SceneEditDialog(f"Scene {len(self.scenes)+1}", "#22c55e", self)
        if dlg.exec():
            n, c = dlg.get_data()
            self.scenes.append({"name": n, "color": c})
            self._refresh_scene_list_ui()
            self._on_settings_changed()

    def _edit_scene(self):
        row = self.list_scenes.currentRow()
        if 0 <= row < len(self.scenes):
            sc = self.scenes[row]
            dlg = SceneEditDialog(sc["name"], sc["color"], self)
            if dlg.exec():
                n, c = dlg.get_data()
                self.scenes[row] = {"name": n, "color": c}
                self._refresh_scene_list_ui()
                self._on_settings_changed()

    def _remove_scene(self):
        row = self.list_scenes.currentRow()
        if 0 <= row < len(self.scenes):
            self.scenes.pop(row)
            self._refresh_scene_list_ui()
            self._on_settings_changed()

    def _add_audio(self):
        if len(self.audio_toggles) >= 6:
            QMessageBox.information(self, "Limit Reached", "A maximum of 6 audio mute toggles can be configured.")
            return
        name = f"Audio {len(self.audio_toggles)+1}"
        self.audio_toggles.append({"name": name, "muted": False})
        self._refresh_audio_list_ui()
        self._on_settings_changed()

    def _edit_audio(self):
        row = self.list_audio.currentRow()
        if 0 <= row < len(self.audio_toggles):
            cur = self.audio_toggles[row]["name"]
            # Simple rename
            from PyQt6.QtWidgets import QInputDialog
            new_name, ok = QInputDialog.getText(self, "Edit Audio Source", "Source Name:", text=cur)
            if ok and new_name.strip():
                self.audio_toggles[row]["name"] = new_name.strip()
                self._refresh_audio_list_ui()
                self._on_settings_changed()

    def _remove_audio(self):
        row = self.list_audio.currentRow()
        if 0 <= row < len(self.audio_toggles):
            self.audio_toggles.pop(row)
            self._refresh_audio_list_ui()
            self._on_settings_changed()

    def _set_launch_button_state(self, is_open: bool):
        if is_open:
            self.btn_launch_panel.setText("🟢 Close Director Panel")
            self.btn_launch_panel.setStyleSheet("""
                QPushButton#btnLaunchDirector {
                    background-color: #b91c1c;
                    color: #ffffff;
                    font-size: 13px;
                    font-weight: bold;
                    border: 1px solid #dc2626;
                    border-radius: 6px;
                }
                QPushButton#btnLaunchDirector:hover {
                    background-color: #dc2626;
                }
            """)
        else:
            self.btn_launch_panel.setText("🔴 Launch Director Panel")
            self.btn_launch_panel.setStyleSheet("""
                QPushButton#btnLaunchDirector {
                    background-color: #15803d;
                    color: #ffffff;
                    font-size: 13px;
                    font-weight: bold;
                    border: 1px solid #16a34a;
                    border-radius: 6px;
                }
                QPushButton#btnLaunchDirector:hover {
                    background-color: #16a34a;
                }
            """)

    def toggle_director_panel(self):
        if self.panel_window and self.panel_window.isVisible():
            log_debug("DIRECTOR", "Closing Director Panel via toggle")
            self.panel_window.close()
        else:
            self.launch_director_panel()

    def launch_director_panel(self):
        log_debug("DIRECTOR", "User clicked Launch Director Panel")

        # 1. Instantiate or show panel first so we know exact geometry above taskbar
        if not self.panel_window:
            self.panel_window = DirectorPanelWindow()
            self.panel_window.panel_closed.connect(self._on_panel_closed)
            self.panel_window.settings_requested.connect(self._open_settings_from_panel)

        fader_data = [
            {"name": self.edit_fader1.text().strip() or "Audio 1", "volume": self.faders[0].get("volume", 80)},
            {"name": self.edit_fader2.text().strip() or "Audio 2", "volume": self.faders[1].get("volume", 75)},
            {"name": self.edit_fader3.text().strip() or "Audio 3", "volume": self.faders[2].get("volume", 60)},
        ]
        self.panel_window.load_configuration(self.scenes, self.audio_toggles, fader_data)
        
        target_mon = self.combo_monitor.currentData()
        if target_mon is None:
            target_mon = self.combo_monitor.currentIndex()
        if target_mon is None or target_mon < 0:
            target_mon = 0

        log_debug("DIRECTOR", f"Target monitor index: {target_mon}")
        self.panel_window.reposition_above_taskbar(target_mon)
        self.panel_window.showNormal()
        self.panel_window.raise_()
        self.panel_window.activateWindow()
        self.panel_window.force_topmost()
        geom = self.panel_window.geometry()
        log_debug("DIRECTOR", f"Director Panel shown at: ({geom.x()}, {geom.y()}, {geom.width()}x{geom.height()}) - IsVisible: {self.panel_window.isVisible()}")
        self._set_launch_button_state(is_open=True)

        # 2. Open the streamer's livestream in browser (Chromium App Mode fitted above dock, or standard browser)
        url = self.edit_stream_url.text().strip()
        if url:
            self._launch_stream_browser(url, target_mon, geom.y())

        # Automatically hide Settings window so the user gets clean separate dock view
        if self.main_win:
            self.main_win.hide()

        # Re-assert topmost after browser completes launch
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(400, self.panel_window.force_topmost)
        QTimer.singleShot(1000, self.panel_window.force_topmost)

    def _find_chromium_browser(self) -> str | None:
        if sys.platform != "win32":
            return None
        import winreg
        # 1. Check registry App Paths
        for app in ["chrome.exe", "msedge.exe", "brave.exe"]:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app}") as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    if val and os.path.exists(val):
                        return val
            except Exception:
                pass
        # 2. Check well-known filesystem paths
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _launch_stream_browser(self, url: str, target_mon: int, dock_top_y: int):
        screens = QApplication.screens()
        idx = target_mon if 0 <= target_mon < len(screens) else 0
        screen = screens[idx] if screens else None

        if screen:
            geo = screen.geometry()
            pos_x = geo.x()
            pos_y = geo.y()
            win_w = geo.width()
            win_h = max(300, dock_top_y - pos_y)
        else:
            pos_x, pos_y, win_w, win_h = 0, 0, 1360, 546

        if hasattr(self, "chk_app_mode") and self.chk_app_mode.isChecked():
            browser_exe = self._find_chromium_browser()
            if browser_exe:
                try:
                    cmd = [
                        browser_exe,
                        f"--app={url}",
                        "--start-maximized",
                    ]
                    log_debug("DIRECTOR", f"Launching studio app window maximized ({os.path.basename(browser_exe)}): {url}")
                    subprocess.Popen(cmd)
                    return
                except Exception as e:
                    log_debug("DIRECTOR", f"Failed to launch Chromium app mode: {e}")

        # Fallback to default browser
        try:
            log_debug("DIRECTOR", f"Opening livestream URL in default browser: {url}")
            webbrowser.open(url)
        except Exception as e:
            log_debug("DIRECTOR", f"Browser launch error: {e}")

    def _open_settings_from_panel(self):
        log_debug("DIRECTOR", "Settings button clicked on Director Dock")
        if self.main_win:
            self.main_win.show()
            self.main_win.raise_()
            self.main_win.activateWindow()
            self.main_win.set_view_index(7)

    def _on_panel_closed(self):
        log_debug("DIRECTOR", "Director Panel closed event received")
        self._set_launch_button_state(is_open=False)

    def _on_settings_changed(self):
        self.api_key = self.edit_api_key.text()
        self.stream_url = self.edit_stream_url.text().strip()
        self.target_monitor_idx = self.combo_monitor.currentData() or 0
        if hasattr(self, "chk_app_mode"):
            self.app_mode = self.chk_app_mode.isChecked()
        self.faders[0]["name"] = self.edit_fader1.text().strip()
        self.faders[1]["name"] = self.edit_fader2.text().strip()
        self.faders[2]["name"] = self.edit_fader3.text().strip()
        self.save_to_settings()

    def export_settings(self) -> dict:
        return {
            "api_key_obf": obfuscate_str(self.edit_api_key.text()),
            "stream_url": self.edit_stream_url.text().strip(),
            "target_monitor": self.combo_monitor.currentData() or 0,
            "app_mode": self.chk_app_mode.isChecked() if hasattr(self, "chk_app_mode") else True,
            "scenes": self.scenes,
            "audio_toggles": self.audio_toggles,
            "faders": [
                {"name": self.edit_fader1.text().strip() or "Mic", "volume": self.faders[0].get("volume", 80)},
                {"name": self.edit_fader2.text().strip() or "Game", "volume": self.faders[1].get("volume", 75)},
                {"name": self.edit_fader3.text().strip() or "Music", "volume": self.faders[2].get("volume", 60)},
            ]
        }

    def load_from_settings(self):
        d = getattr(self.main_win.overlay, "director_settings", {})
        if d:
            self.api_key = obfuscate_str(d.get("api_key_obf", ""))
            self.edit_api_key.setText(self.api_key)
            self.stream_url = d.get("stream_url", self.stream_url)
            self.edit_stream_url.setText(self.stream_url)
            self.target_monitor_idx = d.get("target_monitor", 0)
            self.app_mode = d.get("app_mode", True)
            if hasattr(self, "chk_app_mode"):
                self.chk_app_mode.setChecked(self.app_mode)
            self.scenes = d.get("scenes", self.scenes)
            self.audio_toggles = d.get("audio_toggles", self.audio_toggles)
            self.faders = d.get("faders", self.faders)
            if len(self.faders) >= 3:
                self.edit_fader1.setText(self.faders[0].get("name", "Mic"))
                self.edit_fader2.setText(self.faders[1].get("name", "Game"))
                self.edit_fader3.setText(self.faders[2].get("name", "Music"))

        self.refresh_monitors_list()
        self._refresh_scene_list_ui()
        self._refresh_audio_list_ui()

    def save_to_settings(self):
        if hasattr(self.main_win, "overlay") and self.main_win.overlay:
            self.main_win.overlay.director_settings = self.export_settings()
            self.main_win.overlay.save_settings()

    def refresh_theme_labels(self, effective):
        is_dark = (effective == "dark")
        sub_fg = "#a1a1aa" if is_dark else "#71717a"
        if hasattr(self, "lbl_scene_count"):
            self.lbl_scene_count.setStyleSheet(f"font-size: 11px; color: {sub_fg};")
        if hasattr(self, "lbl_audio_count"):
            self.lbl_audio_count.setStyleSheet(f"font-size: 11px; color: {sub_fg};")
