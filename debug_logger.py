import sys
import os
import time
import traceback
import platform
import faulthandler

DEBUG_MODE = False
DEBUG_LOG_FILE = None
CRASH_LOG_FILE = None
CRASH_HANDLER_INSTALLED = False

def init_debug_logger(log_file_path, enabled=False):
    global DEBUG_LOG_FILE, DEBUG_MODE, CRASH_LOG_FILE
    DEBUG_LOG_FILE = log_file_path
    DEBUG_MODE = enabled
    if log_file_path:
        CRASH_LOG_FILE = os.path.join(os.path.dirname(log_file_path), "crash_log.txt")

def set_debug_mode(enabled):
    global DEBUG_MODE
    DEBUG_MODE = enabled

def is_debug_mode():
    return DEBUG_MODE

def get_debug_log_path():
    return DEBUG_LOG_FILE

def get_crash_log_path():
    return CRASH_LOG_FILE

def log_debug(category, message):
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{category.upper()}] {message}\n"
        print(log_line.strip())
        if DEBUG_LOG_FILE:
            if DEBUG_MODE or category.upper() in ("SYSTEM", "DIRECTOR", "CRASH", "UPDATER", "HOTKEY"):
                with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(log_line)
    except Exception:
        pass

def write_crash_report(exctype, value, tb, thread_name=None):
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        crash_text = "".join(traceback.format_exception(exctype, value, tb))
        header = f"""
================================================================================
CRASH REPORT - HOTKEY OVERLAY ALERT
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
                
        # Show error dialog if possible
        try:
            from PyQt6.QtWidgets import QMessageBox, QApplication
            if QApplication.instance():
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setWindowTitle("HotKey Overlay Alert - Crash Detected")
                msg.setText(
                    f"<b>An unexpected error occurred in HotKey Overlay Alert:</b><br><br>"
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
                        "HotKey Overlay Alert Crash",
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
