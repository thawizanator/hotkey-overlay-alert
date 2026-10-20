import sys
import os
import json
import time
import subprocess
import urllib.request
import urllib.error
from PyQt6.QtCore import QThread, pyqtSignal

CURRENT_VERSION = "3.0.0-beta.3"
BUILD_COMMIT = "474dbee"
BUILD_DATE = "2026-10-20"

_cached_build_commit = None

def get_build_commit():
    """Returns short git commit hash, checking live git first with fallback to baked BUILD_COMMIT."""
    global _cached_build_commit
    if _cached_build_commit is not None:
        return _cached_build_commit

    if getattr(sys, "frozen", False):
        _cached_build_commit = BUILD_COMMIT
        return _cached_build_commit

    try:
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cur_dir,
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=flags
        )
        if res.returncode == 0 and res.stdout.strip():
            _cached_build_commit = res.stdout.strip()
            return _cached_build_commit
    except Exception:
        pass
    _cached_build_commit = BUILD_COMMIT
    return _cached_build_commit

def get_full_version_string():
    """Returns formatted version string with commit, e.g. 'v3.0.0-beta.2 (207ecc5)'."""
    commit = get_build_commit()
    if commit:
        return f"v{CURRENT_VERSION} ({commit})"
    return f"v{CURRENT_VERSION}"

GITHUB_REPO = "thawizanator/hotkey-overlay-alert"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

import re

def parse_version(v_str):
    if not v_str:
        return (0, 0, 0, 0, 0)
    cleaned = v_str.strip().lstrip("vV")
    
    pre_tag = ""
    if "-" in cleaned:
        main_part, pre_tag = cleaned.split("-", 1)
    else:
        main_part = cleaned
        
    parts = []
    for p in main_part.split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    major, minor, patch = parts[:3]
    
    if not pre_tag:
        return (major, minor, patch, 999, 0)
        
    pre_lower = pre_tag.lower()
    pre_type = 1
    if "rc" in pre_lower:
        pre_type = 3
    elif "beta" in pre_lower:
        pre_type = 2
    elif "dev" in pre_lower:
        pre_type = 0
    elif "alpha" in pre_lower or "preview" in pre_lower:
        pre_type = 1
        
    pre_nums = re.findall(r'\d+', pre_lower)
    pre_num = int(pre_nums[-1]) if pre_nums else 0
    return (major, minor, patch, pre_type, pre_num)

def is_newer_version(latest_tag, current_ver=CURRENT_VERSION):
    return parse_version(latest_tag) > parse_version(current_ver)

class UpdateCheckWorker(QThread):
    update_available = pyqtSignal(str, str, str, str)  # latest_tag, release_url, download_url, release_notes
    up_to_date = pyqtSignal(str)                       # current_version
    check_error = pyqtSignal(str)                      # error message

    def __init__(self, current_version=CURRENT_VERSION, channel="stable"):
        super().__init__()
        self.current_version = current_version
        self.channel = str(channel or "stable").lower()

    def run(self):
        try:
            if self.channel == "beta":
                api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=50"
                req = urllib.request.Request(api_url, headers={"User-Agent": "HotKeyOverlayAlert"})
                with urllib.request.urlopen(req, timeout=10) as res:
                    releases = json.loads(res.read().decode("utf-8"))
                    if not isinstance(releases, list) or not releases:
                        self.up_to_date.emit(self.current_version)
                        return
                    valid = [r for r in releases if not r.get("draft", False)]
                    if not valid:
                        self.up_to_date.emit(self.current_version)
                        return
                    newest = max(valid, key=lambda r: parse_version(r.get("tag_name", "")))
                    tag_name = newest.get("tag_name", "")
                    release_url = newest.get("html_url", "")
                    notes = newest.get("body", "")
                    download_url = ""
                    for asset in newest.get("assets", []):
                        name = asset.get("name", "").lower()
                        if name.endswith(".exe"):
                            download_url = asset.get("browser_download_url", "")
                            if "hotkeyoverlayalert" in name:
                                break
                    if is_newer_version(tag_name, self.current_version):
                        self.update_available.emit(tag_name, release_url, download_url, notes)
                    else:
                        self.up_to_date.emit(self.current_version)
            else:
                # Stable channel: GitHub's /releases/latest automatically filters out pre-releases
                api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                req = urllib.request.Request(api_url, headers={"User-Agent": "HotKeyOverlayAlert"})
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
    Cleans PyInstaller-specific environment variables (_MEIPASS2, PYTHONPATH, PYTHONHOME)
    to ensure the new executable extracts its own runtime cleanly.
    """
    if not current_exe:
        current_exe = sys.executable

    # If running from python script rather than frozen executable:
    if not getattr(sys, "frozen", False):
        return False, "Application is running from Python source, not a standalone binary."

    updater_ps1 = os.path.join(os.path.dirname(downloaded_exe), "apply_update.ps1")
    parent_pid = os.getpid()

    # Escape single quotes in paths for PowerShell
    safe_downloaded = downloaded_exe.replace("'", "''")
    safe_current = current_exe.replace("'", "''")
    safe_updater_ps1 = updater_ps1.replace("'", "''")

    updater_log = os.path.join(os.path.dirname(downloaded_exe), "updater_log.txt")
    safe_updater_log = updater_log.replace("'", "''")

    script_content = f"""
$logPath = '{safe_updater_log}'
function Log-Update($msg) {{
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    "[$ts] $msg" | Out-File -FilePath $logPath -Append -Encoding utf8
}}

Log-Update "--- Updater Script Started ---"
Log-Update "Target parent PID: {parent_pid}"
Log-Update "Downloaded: '{safe_downloaded}'"
Log-Update "Current: '{safe_current}'"

$parentPid = {parent_pid}
if ($parentPid) {{
    try {{
        $proc = Get-Process -Id $parentPid -ErrorAction SilentlyContinue
        if ($proc) {{
            Log-Update "Waiting for parent PID $parentPid to exit..."
            $proc.WaitForExit(10000)
            Log-Update "Parent PID $parentPid exit wait completed."
        }}
    }} catch {{
        Log-Update "Error waiting for parent PID: $_"
    }}
}}

# Wait for ALL instances of HotKeyOverlayAlert (including parent bootloader) to fully terminate
$maxWait = 10
while ($maxWait -gt 0) {{
    $running = Get-Process -Name "HotKeyOverlayAlert" -ErrorAction SilentlyContinue
    if (-not $running) {{ break }}
    Log-Update "Waiting for running HotKeyOverlayAlert instances to terminate ($maxWait remaining)..."
    Start-Sleep -Milliseconds 500
    $maxWait--
}}

# If any lingering instance (such as an antivirus-suspended bootloader) is still alive, forcefully terminate it
$lingering = Get-Process -Name "HotKeyOverlayAlert" -ErrorAction SilentlyContinue
if ($lingering) {{
    Log-Update "Forcefully terminating lingering HotKeyOverlayAlert instance(s)..."
    $lingering | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}}

# Clean any lingering stale app.lock file
$lockFile = "$env:APPDATA\\ThaWizanator_Overlay\\app.lock"
if (Test-Path -LiteralPath $lockFile) {{
    Log-Update "Removing stale app.lock file..."
    Remove-Item -LiteralPath $lockFile -Force -ErrorAction SilentlyContinue
}}

# Grace period for Windows OS and Defender filesystem release
Start-Sleep -Seconds 2

$replaced = $false
for ($i = 0; $i -lt 15; $i++) {{
    try {{
        Log-Update "Attempting to replace executable (attempt $($i+1))..."
        Move-Item -LiteralPath '{safe_downloaded}' -Destination '{safe_current}' -Force
        $replaced = $true
        Log-Update "Executable replaced successfully!"
        break
    }} catch {{
        Log-Update "Replace attempt failed: $_"
        Start-Sleep -Seconds 1
    }}
}}

# Purge any PyInstaller, Qt, and Python environment leaks
Log-Update "Purging PyInstaller and Qt environment variables..."
Get-ChildItem Env: | Where-Object {{ $_.Name -like '_PYI*' -or $_.Name -like '_MEI*' -or $_.Name -like 'QT_*' -or $_.Name -like 'QML2_*' }} | ForEach-Object {{
    Remove-Item -LiteralPath "Env:\\$($_.Name)" -ErrorAction SilentlyContinue
    [System.Environment]::SetEnvironmentVariable($_.Name, $null, 'Process')
}}

$env:PYTHONPATH = $null
$env:PYTHONHOME = $null
[System.Environment]::SetEnvironmentVariable('PYTHONPATH', $null, 'Process')
[System.Environment]::SetEnvironmentVariable('PYTHONHOME', $null, 'Process')

# Strip old _MEI temporary paths from PATH
$cleanPath = (($env:PATH -split ';') | Where-Object {{ $_ -and ($_ -notmatch '_MEI') }}) -join ';'
$env:PATH = $cleanPath
[System.Environment]::SetEnvironmentVariable('PATH', $cleanPath, 'Process')

# Signal PyInstaller bootloader to treat this as a fresh top-level process
$env:PYINSTALLER_RESET_ENVIRONMENT = '1'
[System.Environment]::SetEnvironmentVariable('PYINSTALLER_RESET_ENVIRONMENT', '1', 'Process')

if ($replaced) {{
    Log-Update "Relaunching updated executable: '{safe_current}'"
    Start-Sleep -Seconds 1
    $workingDir = Split-Path -Parent '{safe_current}'
    $started = Start-Process -FilePath '{safe_current}' -WorkingDirectory $workingDir -PassThru
    Log-Update "Relaunched process PID: $($started.Id)"
}} else {{
    Log-Update "ERROR: Executable was not replaced, aborting relaunch."
}}

Log-Update "Cleaning up updater script..."
Remove-Item -LiteralPath '{safe_updater_ps1}' -Force -ErrorAction SilentlyContinue
Log-Update "--- Updater Script Complete ---"
"""
    with open(updater_ps1, "w", encoding="utf-8") as f:
        f.write(script_content)

    clean_env = os.environ.copy()
    for key in list(clean_env.keys()):
        k_upper = key.upper()
        if k_upper.startswith(("_PYI", "_MEI", "QT_", "QML2_")) or k_upper in ("PYTHONPATH", "PYTHONHOME"):
            clean_env.pop(key, None)
    clean_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

    # Also clean _MEI from PATH in clean_env
    path_dirs = clean_env.get("PATH", "").split(os.pathsep)
    clean_env["PATH"] = os.pathsep.join([d for d in path_dirs if "_MEI" not in d.upper()])

    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-WindowStyle", "Hidden",
        "-ExecutionPolicy", "Bypass",
        "-File", updater_ps1
    ]

    # Windows: run completely hidden in background without a console window.
    # Do NOT pass DETACHED_PROCESS to powershell.exe as it breaks console subsystem initialization.
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        cmd,
        env=clean_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags
    )
    return True, "Update scheduled"

