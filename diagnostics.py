import sys
import os
import platform
import datetime
import re
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import PYQT_VERSION_STR

from updater import CURRENT_VERSION, get_full_version_string, get_build_commit

APP_DIR = os.path.join(os.environ.get("APPDATA", ""), "ThaWizanator_Overlay")

def check_vcredist():
    """Checks for presence of Microsoft Visual C++ 2015-2022 Redistributable (msvcp140.dll)."""
    sys_root = os.environ.get("SystemRoot", r"C:\Windows")
    sys32 = os.path.join(sys_root, "System32", "msvcp140.dll")
    sys_wow64 = os.path.join(sys_root, "SysWOW64", "msvcp140.dll")
    
    found_paths = []
    if os.path.exists(sys32):
        found_paths.append("System32/msvcp140.dll (64-bit)")
    if os.path.exists(sys_wow64):
        found_paths.append("SysWOW64/msvcp140.dll (32-bit)")
        
    if found_paths:
        return f"Installed ({', '.join(found_paths)})"
    return "Not Detected in System folders"

def get_system_info(overlay_app=None) -> dict:
    """Collects clean, non-sensitive system and environment diagnostics."""
    now = datetime.datetime.now()
    
    # Screens / Monitors
    screen_info = []
    try:
        screens = QApplication.screens()
        for i, s in enumerate(screens):
            geom = s.geometry()
            is_pri = (s == QApplication.primaryScreen())
            screen_info.append(f"Monitor #{i+1}: {geom.width()}x{geom.height()} @ ({geom.x()},{geom.y()}){' [Primary]' if is_pri else ''} [DPR: {s.devicePixelRatio():.2f}]")
    except Exception:
        screen_info.append("Unable to detect display geometry")

    theme_pref = "system"
    streamer_mode = False
    update_chan = "stable"
    dpi_mode = "system"
    if overlay_app:
        theme_pref = getattr(overlay_app, "theme_preference", "system")
        streamer_mode = getattr(overlay_app, "streamer_mode", False)
        update_chan = getattr(overlay_app, "update_channel", "stable")
        dpi_mode = getattr(overlay_app, "dpi_mode", "system")

    info = {
        "Application Version": get_full_version_string(),
        "Git Build Commit": get_build_commit(),
        "Operating System": f"{platform.system()} {platform.release()} (Build {platform.version()}) - {platform.machine()}",
        "Date & Time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "Python Runtime": f"{platform.python_implementation()} {platform.python_version()} ({platform.architecture()[0]})",
        "PyQt6 Version": PYQT_VERSION_STR,
        "C++ Runtime (VC++ 2015-2022)": check_vcredist(),
        "Packaging": "PyInstaller Standalone Executable" if getattr(sys, "frozen", False) else "Python Source",
        "Update Channel": update_chan.capitalize(),
        "Theme Preference": theme_pref.capitalize(),
        "DPI Scaling Mode": dpi_mode.capitalize(),
        "Streamer Mode": "Enabled (Transparent HUDs)" if streamer_mode else "Disabled (Standard Modals)",
        "Monitors": screen_info
    }
    return info

def sanitize_text(text: str) -> str:
    """Removes sensitive tokens, passwords, and private user folder names from text."""
    if not text:
        return ""
    user_prof = os.environ.get("USERPROFILE", "")
    if user_prof:
        text = text.replace(user_prof, r"C:\Users\<User>")
    
    text = re.sub(r'oauth:[a-zA-Z0-9]{20,}', 'oauth:<REDACTED>', text)
    text = re.sub(r'token[\'"]?\s*[:=]\s*[\'"][a-zA-Z0-9]{20,}[\'"]', 'token: "<REDACTED>"', text)
    return text

def bundle_logs(overlay_app=None, target_dir=None) -> tuple:
    """
    Combines debug.txt, crash_log.txt, updater_log.txt with system diagnostics.
    Returns (bundle_filepath, sanitized_full_text).
    """
    if not target_dir:
        target_dir = APP_DIR
    os.makedirs(target_dir, exist_ok=True)
    bundle_file = os.path.join(target_dir, "bug_report_bundle.txt")

    sys_info = get_system_info(overlay_app)
    
    lines = []
    lines.append("=" * 80)
    lines.append("HOTKEY OVERLAY ALERT - BUG REPORT DIAGNOSTICS BUNDLE")
    lines.append("=" * 80)
    for k, v in sys_info.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("=" * 80)
    lines.append("")

    log_files = [
        ("CRASH LOG (crash_log.txt)", os.path.join(APP_DIR, "crash_log.txt")),
        ("DEBUG LOG (debug.txt)", os.path.join(APP_DIR, "debug.txt")),
        ("UPDATER LOG (updater_log.txt)", os.path.join(APP_DIR, "updater_log.txt")),
    ]

    for title, log_path in log_files:
        lines.append("-" * 80)
        lines.append(title)
        lines.append("-" * 80)
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read().strip()
                if content:
                    log_lines = content.splitlines()
                    if len(log_lines) > 200:
                        log_lines = [f"[... truncated, showing last 200 of {len(log_lines)} lines ...]"] + log_lines[-200:]
                    lines.append("\n".join(log_lines))
                else:
                    lines.append("(File is empty)")
            except Exception as e:
                lines.append(f"(Error reading log file: {e})")
        else:
            lines.append("(File does not exist)")
        lines.append("")

    full_text = sanitize_text("\n".join(lines))
    try:
        with open(bundle_file, "w", encoding="utf-8") as f:
            f.write(full_text)
    except Exception as e:
        print(f"Error saving bug report bundle: {e}")

    return bundle_file, full_text
