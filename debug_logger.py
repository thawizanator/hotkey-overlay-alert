import sys
import os
import time
import datetime
import traceback
import platform
import faulthandler

def is_beta_build() -> bool:
    try:
        from updater import CURRENT_VERSION
        return "beta" in CURRENT_VERSION.lower()
    except Exception:
        return False

DEBUG_MODE = is_beta_build()
DEBUG_LOG_FILE = None
CRASH_LOG_FILE = None
MIRROR_LOG_FILE = None
LOGS_DIR = None
CRASH_HANDLER_INSTALLED = False
_current_log_date = None

def get_logs_dir():
    global LOGS_DIR
    if not LOGS_DIR:
        app_data = os.getenv("APPDATA") or os.path.expanduser("~")
        LOGS_DIR = os.path.join(app_data, "StreamerCalyx", "logs")
        try:
            os.makedirs(LOGS_DIR, exist_ok=True)
        except Exception:
            pass
    return LOGS_DIR

def prune_old_logs(max_days=7):
    """Deletes daily debug log files older than max_days (7-day rolling retention)."""
    logs_dir = get_logs_dir()
    if not logs_dir or not os.path.exists(logs_dir):
        return
    try:
        now = time.time()
        cutoff_sec = max_days * 86400
        today_date = datetime.date.today()
        for fname in os.listdir(logs_dir):
            if fname.startswith("debug_") and fname.endswith(".txt"):
                fpath = os.path.join(logs_dir, fname)
                try:
                    should_prune = False
                    date_part = fname[6:14]
                    if len(date_part) == 8 and date_part.isdigit():
                        try:
                            f_year = int(date_part[0:4])
                            f_month = int(date_part[4:6])
                            f_day = int(date_part[6:8])
                            f_date = datetime.date(f_year, f_month, f_day)
                            if (today_date - f_date).days > max_days:
                                should_prune = True
                        except Exception:
                            pass
                    
                    if not should_prune:
                        f_mtime = os.path.getmtime(fpath)
                        if (now - f_mtime) > cutoff_sec:
                            should_prune = True

                    if should_prune:
                        os.remove(fpath)
                        print(f"[SYSTEM] Pruned expired debug log (>7 days): {fname}")
                except Exception as ex:
                    print(f"[SYSTEM] Error pruning log file {fname}: {ex}")
    except Exception as e:
        print(f"[SYSTEM] Error during log retention sweep: {e}")

def init_debug_logger(log_file_path, enabled=False):
    global DEBUG_LOG_FILE, DEBUG_MODE, CRASH_LOG_FILE, LOGS_DIR, MIRROR_LOG_FILE, _current_log_date
    if log_file_path:
        app_dir = os.path.dirname(os.path.abspath(log_file_path))
        LOGS_DIR = os.path.join(app_dir, "logs")
        os.makedirs(LOGS_DIR, exist_ok=True)
        MIRROR_LOG_FILE = log_file_path
        CRASH_LOG_FILE = os.path.join(app_dir, "crash_log.txt")

        _current_log_date = time.strftime("%Y%m%d")
        DEBUG_LOG_FILE = os.path.join(LOGS_DIR, f"debug_{_current_log_date}.txt")
    else:
        DEBUG_LOG_FILE = None
        MIRROR_LOG_FILE = None

    if is_beta_build():
        DEBUG_MODE = True
    else:
        DEBUG_MODE = enabled

    # Sweep and prune logs older than 7 days
    prune_old_logs(max_days=7)

def set_debug_mode(enabled):
    global DEBUG_MODE
    if is_beta_build():
        # Debugging mode cannot be turned off in Beta builds
        DEBUG_MODE = True
    else:
        DEBUG_MODE = bool(enabled)

def is_debug_mode():
    if is_beta_build():
        return True
    return DEBUG_MODE

def get_debug_log_path():
    return DEBUG_LOG_FILE

def get_mirror_log_path():
    return MIRROR_LOG_FILE

def get_crash_log_path():
    return CRASH_LOG_FILE

def get_all_log_files():
    """Returns sorted list of absolute paths to daily log files in LOGS_DIR."""
    logs_dir = get_logs_dir()
    if not logs_dir or not os.path.exists(logs_dir):
        return []
    try:
        files = []
        for f in os.listdir(logs_dir):
            if f.startswith("debug_") and f.endswith(".txt"):
                files.append(os.path.join(logs_dir, f))
        return sorted(files, reverse=True)
    except Exception:
        return []

def log_debug(category, message):
    global DEBUG_LOG_FILE, _current_log_date, LOGS_DIR, MIRROR_LOG_FILE
    try:
        logs_dir = get_logs_dir()
        today = time.strftime("%Y%m%d")
        if _current_log_date != today or not DEBUG_LOG_FILE:
            _current_log_date = today
            if logs_dir:
                DEBUG_LOG_FILE = os.path.join(logs_dir, f"debug_{today}.txt")
                prune_old_logs(max_days=7)

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{category.upper()}] {message}\n"
        print(log_line.strip())

        should_log = (DEBUG_MODE or is_beta_build() or category.upper() in (
            "SYSTEM", "DIRECTOR", "CRASH", "UPDATER", "HOTKEY", "LAN_SOUND_SERVER",
            "LAN_SOUND_CLIENT", "SOUNDBOARD", "WEBRTC", "HOST_BOUNCER", "BOUNCER",
            "AUTOCLIP", "UI_ACTION"
        ))

        if should_log:
            if DEBUG_LOG_FILE:
                with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(log_line)
            if MIRROR_LOG_FILE:
                with open(MIRROR_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(log_line)
    except Exception:
        pass

def write_crash_report(exctype, value, tb, thread_name=None):
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        crash_text = "".join(traceback.format_exception(exctype, value, tb))
        header = f"""
================================================================================
CRASH REPORT - STREAMER CALYX
Timestamp: {timestamp}
Python: {platform.python_version()} ({platform.architecture()[0]})
Platform: {platform.platform()}
Thread: {thread_name or 'MainThread'}
================================================================================
{crash_text}
"""
        print(header, file=sys.stderr)
        
        # Write to crash_log.txt
        if CRASH_LOG_FILE:
            with open(CRASH_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(header)
                
        # Also log to debug.txt if enabled
        log_debug("CRASH", f"Unhandled exception: {exctype.__name__}: {value}")
        if DEBUG_LOG_FILE:
            with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(header)
                
        # Show error dialog if possible (skipped during automated testing)
        if os.environ.get("STREAMER_CALYX_HEADLESS") == "1" or os.environ.get("STREAMER_CALYX_TEST") == "1":
            return

        try:
            from PyQt6.QtWidgets import QMessageBox, QApplication
            if QApplication.instance():
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setWindowTitle("Streamer Calyx - Crash Detected")
                msg.setText(
                    f"<b>An unexpected error occurred in Streamer Calyx:</b><br><br>"
                    f"<code>{exctype.__name__}: {value}</code><br><br>"
                    f"A detailed crash report has been saved to:<br>"
                    f"<b>{CRASH_LOG_FILE}</b>"
                )
                msg.setDetailedText(crash_text)
                msg.exec()
        except Exception:
            # Fallback to win32 ctypes MessageBox if Qt fails
            if sys.platform == "win32":
                try:
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(
                        0,
                        f"An unexpected error occurred:\n{exctype.__name__}: {value}\n\nCrash log saved to:\n{CRASH_LOG_FILE}",
                        "Streamer Calyx Crash",
                        0x10 # MB_ICONERROR
                    )
                except Exception:
                    pass
    except Exception as e:
        print(f"Error recording crash report: {e}")

def install_crash_handler():
    global CRASH_HANDLER_INSTALLED
    if CRASH_HANDLER_INSTALLED:
        return
    CRASH_HANDLER_INSTALLED = True

    # 1. Main thread sys.excepthook
    def global_excepthook(exctype, value, tb):
        if issubclass(exctype, KeyboardInterrupt):
            sys.__excepthook__(exctype, value, tb)
            return
        write_crash_report(exctype, value, tb, "MainThread")
        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = global_excepthook

    # 2. Worker threads threading.excepthook
    try:
        import threading
        def thread_excepthook(args):
            if issubclass(args.exc_type, KeyboardInterrupt):
                return
            tname = args.thread.name if args.thread else "WorkerThread"
            write_crash_report(args.exc_type, args.exc_value, args.exc_traceback, tname)
        threading.excepthook = thread_excepthook
    except Exception:
        pass

    # 3. Low-level faulthandler for fatal crashes
    try:
        if CRASH_LOG_FILE:
            fh = open(CRASH_LOG_FILE, "a", encoding="utf-8")
            faulthandler.enable(fh)
    except Exception:
        pass
