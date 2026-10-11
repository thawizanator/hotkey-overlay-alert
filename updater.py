import sys
import os
import json
import time
import subprocess
import urllib.request
import urllib.error
from PyQt6.QtCore import QThread, pyqtSignal

CURRENT_VERSION = "2.3.0"
GITHUB_REPO = "thawizanator/hotkey-overlay-alert"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

def parse_version(v_str):
    if not v_str:
        return (0, 0, 0)
    cleaned = v_str.strip().lstrip("vV")
    parts = []
    for p in cleaned.split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])

def is_newer_version(latest_tag, current_ver=CURRENT_VERSION):
    return parse_version(latest_tag) > parse_version(current_ver)

class UpdateCheckWorker(QThread):
    update_available = pyqtSignal(str, str, str, str)  # latest_tag, release_url, download_url, release_notes
    up_to_date = pyqtSignal(str)                       # current_version
    check_error = pyqtSignal(str)                      # error message

    def __init__(self, current_version=CURRENT_VERSION):
        super().__init__()
        self.current_version = current_version

    def run(self):
        try:
            req = urllib.request.Request(API_URL, headers={"User-Agent": "HotKeyOverlayAlert"})
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode("utf-8"))
                tag_name = data.get("tag_name", "")
                release_url = data.get("html_url", "")
                notes = data.get("body", "")

                download_url = ""
                for asset in data.get("assets", []):
                    name = asset.get("name", "").lower()
                    if name.endswith(".exe"):
                        download_url = asset.get("browser_download_url", "")
                        if "hotkeyoverlayalert" in name:
                            break

                if is_newer_version(tag_name, self.current_version):
                    self.update_available.emit(tag_name, release_url, download_url, notes)
                else:
                    self.up_to_date.emit(self.current_version)
        except Exception as e:
            self.check_error.emit(str(e))

class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, download_url, target_path):
        super().__init__()
        self.download_url = download_url
        self.target_path = target_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            req = urllib.request.Request(self.download_url, headers={"User-Agent": "HotKeyOverlayAlert"})
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0
                block_size = 65536

                with open(self.target_path, "wb") as f:
                    while not self._is_cancelled:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        downloaded += len(buffer)
                        f.write(buffer)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress.emit(percent)

                if self._is_cancelled:
                    try: 
                        os.remove(self.target_path)
                    except Exception: 
                        pass
                    return

                self.progress.emit(100)
                self.finished.emit(self.target_path)
        except Exception as e:
            self.error.emit(str(e))

def apply_update_and_restart(downloaded_exe, current_exe=None):
    """
    Spawns a detached background process to replace the running executable
    and relaunch the new version, then signals the application to exit.
    """
    if not current_exe:
        current_exe = sys.executable

    # If running from python script rather than frozen executable:
    if not getattr(sys, "frozen", False):
        return False, "Application is running from Python source, not a standalone binary."

    updater_ps1 = os.path.join(os.path.dirname(downloaded_exe), "apply_update.ps1")
    script_content = f"""
Start-Sleep -Seconds 2
try {{
    Move-Item -LiteralPath '{downloaded_exe}' -Destination '{current_exe}' -Force
    Start-Process -FilePath '{current_exe}'
}} catch {{
    Start-Sleep -Seconds 2
    Move-Item -LiteralPath '{downloaded_exe}' -Destination '{current_exe}' -Force
    Start-Process -FilePath '{current_exe}'
}}
Remove-Item -LiteralPath '{updater_ps1}' -Force -ErrorAction SilentlyContinue
"""
    with open(updater_ps1, "w", encoding="utf-8") as f:
        f.write(script_content)

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-WindowStyle", "Hidden",
        "-ExecutionPolicy", "Bypass",
        "-File", updater_ps1
    ]
    subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    return True, "Update scheduled"
