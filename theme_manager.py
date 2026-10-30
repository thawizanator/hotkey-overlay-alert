import os
import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QPalette, QColor, QPixmap, QPainter, QPen, QPainterPath
from PyQt6.QtCore import Qt

def get_checkmark_icon_path() -> str:
    """Returns absolute path with forward slashes to the checkmark icon, creating it if needed."""
    app_data = os.environ.get("APPDATA", "")
    target_dir = os.path.join(app_data, "StreamerCalyx") if app_data else os.path.dirname(__file__)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        pass
    icon_path = os.path.join(target_dir, "checkmark_white.png")
    if not os.path.exists(icon_path):
        try:
            pix = QPixmap(32, 32)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor(255, 255, 255), 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(7, 16)
            path.lineTo(13, 22)
            path.lineTo(25, 10)
            painter.drawPath(path)
            painter.end()
            pix.save(icon_path)
        except Exception:
            pass
    return icon_path.replace("\\", "/")

def get_dropdown_arrow_path(theme: str = "dark", disabled: bool = False) -> str:
    """Returns absolute path with forward slashes to the dropdown chevron icon, creating it if needed."""
    app_data = os.environ.get("APPDATA", "")
    target_dir = os.path.join(app_data, "StreamerCalyx") if app_data else os.path.dirname(__file__)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        pass

    if disabled:
        filename = f"dropdown_arrow_{theme}_disabled.png"
        color_hex = "#52525b" if theme == "dark" else "#a1a1aa"
    else:
        filename = f"dropdown_arrow_{theme}.png"
        color_hex = "#efeff1" if theme == "dark" else "#52525b"

    icon_path = os.path.join(target_dir, filename)
    if not os.path.exists(icon_path):
        try:
            pix = QPixmap(32, 32)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen = QPen(QColor(color_hex), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(8, 12)
            path.lineTo(16, 20)
            path.lineTo(24, 12)
            painter.drawPath(path)
            painter.end()
            pix.save(icon_path)
        except Exception:
            pass
    return icon_path.replace("\\", "/")

def detect_system_theme() -> str:
    """
    Detects whether the Windows host OS is currently using Light or Dark theme.
    Returns 'dark' or 'light'.
    """
    # 1. Check Qt styleHints (PyQt 6.5+)
    app = QApplication.instance()
    if app and hasattr(app, "styleHints"):
        try:
            scheme = app.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Light:
                return "light"
            elif scheme == Qt.ColorScheme.Dark:
                return "dark"
        except Exception:
            pass

    # 2. Check Windows Registry fallback
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if val == 1 else "dark"
        except Exception:
            pass

    return "dark"

def get_effective_theme(preference: str = "system") -> str:
    """
    Resolves the active theme ('dark' or 'light') based on user preference ('system', 'dark', 'light').
    """
    pref = str(preference or "system").lower()
    if pref in ("dark", "light"):
        return pref
    return detect_system_theme()

def get_secondary_text_color(theme: str) -> str:
    """Returns the hex color code for secondary / hint text for the given theme."""
    return "#52525b" if theme == "light" else "#a1a1aa"

def get_tertiary_text_color(theme: str) -> str:
    """Returns the hex color code for small tip / footer text for the given theme."""
    return "#71717a" if theme == "light" else "#71717a"

def get_theme_palette(theme: str) -> QPalette:
    """Generates a QPalette matching the given theme ('dark' or 'light')."""
    pal = QPalette()
    if theme == "light":
        pal.setColor(QPalette.ColorRole.Window, QColor("#f4f4f6"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#18181b"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#f4f4f5"))
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#18181b"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#18181b"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#f4f4f5"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#18181b"))
        pal.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#9146ff"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    else:
        pal.setColor(QPalette.ColorRole.Window, QColor("#121214"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#efeff1"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#0e0e10"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#18181b"))
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#18181b"))
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#efeff1"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#efeff1"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#27272a"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#efeff1"))
        pal.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#9146ff"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return pal

LIGHT_STYLESHEET = """
    QWidget#SettingsWindow, QDialog#SettingsWindow, QDialog, QMessageBox {
        background-color: #f4f4f6;
        color: #18181b;
    }
    QMessageBox QLabel {
        color: #18181b;
        font-size: 13px;
    }
    QMessageBox QPushButton {
        min-width: 70px;
        min-height: 24px;
        padding: 4px 14px;
        font-weight: 600;
    }
    QWidget {
        color: #18181b;
        font-family: 'Segoe UI', -apple-system, sans-serif;
    }
    QTabWidget::pane {
        border: 1px solid #d4d4d8;
        background-color: #ffffff;
        border-radius: 6px;
        padding: 4px;
    }
    QTabBar::tab {
        background: #e4e4e7;
        color: #52525b;
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
        background: #d4d4d8;
        color: #18181b;
    }
    QGroupBox {
        border: 1px solid #e4e4e7;
        background-color: #ffffff;
        border-radius: 6px;
        margin-top: 10px;
        font-weight: bold;
        font-size: 12px;
        color: #18181b;
        padding-top: 12px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: #18181b;
    }
    QToolTip {
        background-color: #f4f4f5;
        color: #18181b;
        border: 1px solid #d4d4d8;
        border-radius: 4px;
        padding: 5px 8px;
        font-size: 11px;
    }
    QPushButton {
        background-color: #f4f4f5;
        color: #18181b;
        border: 1px solid #d4d4d8;
        border-radius: 5px;
        padding: 3px 10px;
        font-size: 12px;
        min-height: 18px;
    }
    QPushButton:hover {
        background-color: #e4e4e7;
        border-color: #a1a1aa;
    }
    QPushButton:pressed {
        background-color: #d4d4d8;
    }
    QPushButton:disabled {
        background-color: #f4f4f5;
        color: #a1a1aa;
        border-color: #e4e4e7;
    }
    QCheckBox {
        color: #18181b;
        font-size: 12px;
        spacing: 6px;
    }
    QCheckBox::indicator {
        width: 15px;
        height: 15px;
        border: 1px solid #a1a1aa;
        border-radius: 3px;
        background-color: #ffffff;
    }
    QCheckBox::indicator:hover {
        border-color: #9146ff;
    }
    QCheckBox::indicator:checked {
        background-color: #9146ff;
        border-color: #9146ff;
        image: url("__CHECKMARK_URL__");
    }
    QComboBox, QSpinBox, QDateTimeEdit {
        background-color: #ffffff;
        color: #18181b;
        border: 1px solid #d4d4d8;
        border-radius: 4px;
        padding: 2px 6px;
        min-height: 18px;
        max-height: 22px;
    }
    QComboBox {
        padding-right: 22px;
    }
    QComboBox:hover, QSpinBox:hover, QDateTimeEdit:hover {
        border-color: #a1a1aa;
    }
    QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus {
        border: 1px solid #9146ff;
    }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 20px;
        border: none;
    }
    QComboBox::down-arrow {
        image: url("__DROPDOWN_ARROW_URL__");
        width: 12px;
        height: 12px;
    }
    QComboBox::down-arrow:disabled {
        image: url("__DROPDOWN_ARROW_DISABLED_URL__");
    }
    QComboBox QAbstractItemView {
        background-color: #ffffff;
        color: #18181b;
        border: 1px solid #d4d4d8;
        selection-background-color: #9146ff;
        selection-color: #ffffff;
        outline: none;
    }
    QLineEdit, QTextEdit, QListWidget {
        background-color: #ffffff;
        color: #18181b;
        border: 1px solid #d4d4d8;
        border-radius: 4px;
        padding: 4px 8px;
    }
    QLineEdit:focus, QTextEdit:focus, QListWidget:focus {
        border: 1px solid #9146ff;
    }
    QListWidget::item {
        padding: 4px 6px;
        border-radius: 3px;
    }
    QListWidget::item:selected {
        background-color: #9146ff;
        color: #ffffff;
    }
    QListWidget::item:hover:!selected {
        background-color: #e4e4e7;
    }
    QSlider::groove:horizontal {
        height: 6px;
        background: #e4e4e7;
        border-radius: 3px;
    }
    QSlider::sub-page:horizontal {
        background: #9146ff;
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #ffffff;
        border: 1px solid #a1a1aa;
        width: 14px;
        margin-top: -4px;
        margin-bottom: -4px;
        border-radius: 7px;
    }
    QSlider::handle:horizontal:hover {
        border-color: #9146ff;
    }
    QProgressBar {
        border: 1px solid #d4d4d8;
        border-radius: 4px;
        text-align: center;
        height: 18px;
        background-color: #f4f4f5;
        color: #18181b;
    }
    QProgressBar::chunk {
        background-color: #9146ff;
        border-radius: 3px;
    }
    QLabel {
        color: #18181b;
    }
    QMenu {
        background-color: #ffffff;
        color: #18181b;
        border: 1px solid #d4d4d8;
        border-radius: 6px;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 20px 6px 12px;
        border-radius: 4px;
    }
    QMenu::item:selected {
        background-color: #9146ff;
        color: #ffffff;
    }
    QMenu::separator {
        height: 1px;
        background-color: #e4e4e7;
        margin: 4px 6px;
    }
    /* Modern Left Sidebar Styles (Light) */
    QWidget#sidebarContainer {
        background-color: #f0f0f3;
        border-right: 1px solid #d4d4d8;
    }
    QLabel#sidebarBrand {
        color: #18181b;
        font-size: 14px;
        font-weight: bold;
    }
    QLabel#sidebarSub {
        color: #71717a;
        font-size: 11px;
    }
    QLabel#navCatLabel {
        color: #71717a;
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 1px;
        padding-top: 8px;
        padding-bottom: 2px;
        padding-left: 6px;
    }
    QPushButton[isNav="true"] {
        text-align: left;
        background-color: transparent;
        color: #52525b;
        border: none;
        border-left: 3px solid transparent;
        border-radius: 4px;
        padding: 7px 12px;
        font-size: 12px;
        font-weight: 600;
        min-height: 20px;
    }
    QPushButton[isNav="true"]:hover:!checked {
        background-color: #e4e4e7;
        color: #18181b;
    }
    QPushButton[isNav="true"]:checked {
        background-color: #ffffff;
        color: #18181b;
        border-left: 3px solid #9146ff;
    }
    QPushButton[isNav="true"]:disabled {
        color: #a1a1aa;
        background-color: transparent;
        border-left: 3px solid transparent;
    }
    QLabel#contentHeaderLabel {
        color: #18181b;
        font-size: 15px;
        font-weight: bold;
        padding-bottom: 4px;
    }
"""

DARK_STYLESHEET = """
    QWidget#SettingsWindow, QDialog#SettingsWindow, QDialog, QMessageBox {
        background-color: #121214;
        color: #efeff1;
    }
    QMessageBox QLabel {
        color: #efeff1;
        font-size: 13px;
    }
    QMessageBox QPushButton {
        min-width: 70px;
        min-height: 24px;
        padding: 4px 14px;
        font-weight: 600;
    }
    QToolTip {
        background-color: #18181b;
        color: #efeff1;
        border: 1px solid #3f3f46;
        border-radius: 4px;
        padding: 5px 8px;
        font-size: 11px;
    }
    QWidget {
        color: #efeff1;
        font-family: 'Segoe UI', -apple-system, sans-serif;
    }
    QTabWidget::pane {
        border: 1px solid #2d2d30;
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
        border: 1px solid #2d2d30;
        background-color: #18181b;
        border-radius: 6px;
        margin-top: 10px;
        font-weight: bold;
        font-size: 12px;
        color: #efeff1;
        padding-top: 12px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: #ffffff;
    }
    QToolTip {
        background-color: #18181b;
        color: #efeff1;
        border: 1px solid #3f3f46;
        border-radius: 4px;
        padding: 5px 8px;
        font-size: 11px;
    }
    QPushButton {

        background-color: #27272a;
        color: #efeff1;
        border: 1px solid #3f3f46;
        border-radius: 5px;
        padding: 3px 10px;
        font-size: 12px;
        min-height: 18px;
    }
    QPushButton:hover {
        background-color: #3f3f46;
        border-color: #52525b;
    }
    QPushButton:pressed {
        background-color: #18181b;
    }
    QPushButton:disabled {
        background-color: #202022;
        color: #636366;
        border-color: #2c2c2e;
    }
    QCheckBox {
        color: #efeff1;
        font-size: 12px;
        spacing: 6px;
    }
    QCheckBox::indicator {
        width: 15px;
        height: 15px;
        border: 1px solid #52525b;
        border-radius: 3px;
        background-color: #27272a;
    }
    QCheckBox::indicator:hover {
        border-color: #9146ff;
    }
    QCheckBox::indicator:checked {
        background-color: #9146ff;
        border-color: #9146ff;
        image: url("__CHECKMARK_URL__");
    }
    QComboBox, QSpinBox, QDateTimeEdit {
        background-color: #27272a;
        color: #efeff1;
        border: 1px solid #3f3f46;
        border-radius: 4px;
        padding: 2px 6px;
        min-height: 18px;
        max-height: 22px;
    }
    QComboBox {
        padding-right: 22px;
    }
    QComboBox:hover, QSpinBox:hover, QDateTimeEdit:hover {
        border-color: #52525b;
    }
    QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus {
        border: 1px solid #9146ff;
    }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 20px;
        border: none;
    }
    QComboBox::down-arrow {
        image: url("__DROPDOWN_ARROW_URL__");
        width: 12px;
        height: 12px;
    }
    QComboBox::down-arrow:disabled {
        image: url("__DROPDOWN_ARROW_DISABLED_URL__");
    }
    QComboBox QAbstractItemView {
        background-color: #18181b;
        color: #efeff1;
        border: 1px solid #3f3f46;
        selection-background-color: #9146ff;
        selection-color: #ffffff;
        outline: none;
    }
    QLineEdit, QTextEdit, QListWidget {
        background-color: #0e0e10;
        color: #efeff1;
        border: 1px solid #3f3f46;
        border-radius: 4px;
        padding: 4px 8px;
    }
    QLineEdit:focus, QTextEdit:focus, QListWidget:focus {
        border: 1px solid #9146ff;
    }
    QListWidget::item {
        padding: 4px 6px;
        border-radius: 3px;
    }
    QListWidget::item:selected {
        background-color: #9146ff;
        color: #ffffff;
    }
    QListWidget::item:hover:!selected {
        background-color: #27272a;
    }
    QSlider::groove:horizontal {
        height: 6px;
        background: #27272a;
        border-radius: 3px;
    }
    QSlider::sub-page:horizontal {
        background: #9146ff;
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #efeff1;
        border: 1px solid #3f3f46;
        width: 14px;
        margin-top: -4px;
        margin-bottom: -4px;
        border-radius: 7px;
    }
    QSlider::handle:horizontal:hover {
        border-color: #9146ff;
    }
    QProgressBar {
        border: 1px solid #303032;
        border-radius: 4px;
        text-align: center;
        height: 18px;
        background-color: #18181b;
        color: #efeff1;
    }
    QProgressBar::chunk {
        background-color: #9146ff;
        border-radius: 3px;
    }
    QLabel {
        color: #efeff1;
    }
    QMenu {
        background-color: #18181b;
        color: #efeff1;
        border: 1px solid #3f3f46;
        border-radius: 6px;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 20px 6px 12px;
        border-radius: 4px;
    }
    QMenu::item:selected {
        background-color: #9146ff;
        color: #ffffff;
    }
    QMenu::separator {
        height: 1px;
        background-color: #3f3f46;
        margin: 4px 6px;
    }
    /* Modern Left Sidebar Styles (Dark) */
    QWidget#sidebarContainer {
        background-color: #18181b;
        border-right: 1px solid #2d2d30;
    }
    QLabel#sidebarBrand {
        color: #efeff1;
        font-size: 14px;
        font-weight: bold;
    }
    QLabel#sidebarSub {
        color: #a1a1aa;
        font-size: 11px;
    }
    QLabel#navCatLabel {
        color: #a1a1aa;
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 1px;
        padding-top: 8px;
        padding-bottom: 2px;
        padding-left: 6px;
    }
    QPushButton[isNav="true"] {
        text-align: left;
        background-color: transparent;
        color: #a1a1aa;
        border: none;
        border-left: 3px solid transparent;
        border-radius: 4px;
        padding: 7px 12px;
        font-size: 12px;
        font-weight: 600;
        min-height: 20px;
    }
    QPushButton[isNav="true"]:hover:!checked {
        background-color: #27272a;
        color: #efeff1;
    }
    QPushButton[isNav="true"]:checked {
        background-color: #27272a;
        color: #ffffff;
        border-left: 3px solid #9146ff;
    }
    QPushButton[isNav="true"]:disabled {
        color: #52525b;
        background-color: transparent;
        border-left: 3px solid transparent;
    }
    QLabel#contentHeaderLabel {
        color: #efeff1;
        font-size: 15px;
        font-weight: bold;
        padding-bottom: 4px;
    }
"""

def get_theme_stylesheet(theme: str) -> str:
    """Returns the CSS stylesheet matching the given theme ('dark' or 'light')."""
    chk_icon = get_checkmark_icon_path()
    arrow_icon = get_dropdown_arrow_path(theme, disabled=False)
    arrow_disabled = get_dropdown_arrow_path(theme, disabled=True)
    raw = LIGHT_STYLESHEET if theme == "light" else DARK_STYLESHEET
    return (raw
            .replace("__CHECKMARK_URL__", chk_icon)
            .replace("__DROPDOWN_ARROW_URL__", arrow_icon)
            .replace("__DROPDOWN_ARROW_DISABLED_URL__", arrow_disabled))

def set_window_immersive_dark_mode(hwnd, is_dark: bool):
    """
    Sets Windows 10/11 title bar immersive dark mode attribute via DwmSetWindowAttribute.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # Windows 10 build 19041 (20H1)+ and Windows 11 use attribute 20
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        val = ctypes.c_int(1 if is_dark else 0)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(hwnd),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(val),
            ctypes.sizeof(val)
        )
        if res != 0:
            # Fallback for Windows 10 1809 - 1909
            DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY = 19
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(hwnd),
                DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY,
                ctypes.byref(val),
                ctypes.sizeof(val)
            )
    except Exception:
        pass

def apply_theme_to_window(window: QWidget, preference: str = "system") -> str:
    """
    Applies the appropriate theme to the specified window and the global application.
    Returns the resolved effective theme ('dark' or 'light').
    """
    effective = get_effective_theme(preference)
    palette = get_theme_palette(effective)
    stylesheet = get_theme_stylesheet(effective)

    app = QApplication.instance()
    if app:
        app.setPalette(palette)

    if window:
        window.setPalette(palette)
        window.setStyleSheet(stylesheet)
        if hasattr(window, "tabs") and window.tabs and hasattr(window.tabs, "setStyleSheet"):
            try:
                window.tabs.setStyleSheet(stylesheet)
            except Exception:
                pass
        if hasattr(window, "stacked_pages") and window.stacked_pages:
            window.stacked_pages.setStyleSheet(stylesheet)
        if hasattr(window, "sidebar_widget") and window.sidebar_widget:
            window.sidebar_widget.setStyleSheet(stylesheet)
        
        # Apply Windows 10/11 title bar dark mode
        try:
            hwnd = window.winId()
            if hwnd:
                set_window_immersive_dark_mode(hwnd, is_dark=(effective == "dark"))
        except Exception:
            pass

    return effective
