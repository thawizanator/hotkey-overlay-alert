import os
import time

DEBUG_MODE = False
DEBUG_LOG_FILE = None

def init_debug_logger(log_file_path, enabled=False):
    global DEBUG_LOG_FILE, DEBUG_MODE
    DEBUG_LOG_FILE = log_file_path
    DEBUG_MODE = enabled

def set_debug_mode(enabled):
    global DEBUG_MODE
    DEBUG_MODE = enabled

def is_debug_mode():
    return DEBUG_MODE

def get_debug_log_path():
    return DEBUG_LOG_FILE

def log_debug(category, message):
    try:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{category.upper()}] {message}\n"
        print(log_line.strip())
        if DEBUG_MODE and DEBUG_LOG_FILE:
            with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_line)
    except Exception:
        pass
