#!/usr/bin/env python3
"""
Streamer Calyx Master Release Automation Pipeline
Compiles debloated binaries (onedir + onefile), builds the NSIS installer,
digitally signs all executables with DigiCert EV hardware token, and verifies signatures.
"""

import os
import sys
import shutil
import subprocess
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(REPO_ROOT, "dist")
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
MAKENSIS_EXE = os.path.join(TOOLS_DIR, "nsis", "makensis.exe")
SIGNTOOL_EXE = r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"
EV_THUMBPRINT = "4F0585B9717223435582D1F916E17759F2B51496"
TIMESTAMP_URL = "http://timestamp.digicert.com"

def run_step(cmd, desc, cwd=REPO_ROOT):
    print(f"\n[STEP] {desc}...")
    start = time.time()
    res = subprocess.run(cmd, cwd=cwd, shell=True)
    if res.returncode != 0:
        print(f"[ERROR] Failed during: {desc} (code {res.returncode})")
        sys.exit(res.returncode)
    elapsed = time.time() - start
    print(f"[OK] {desc} completed in {elapsed:.1f}s")

def main():
    print("=" * 60)
    print("STREAMER CALYX MASTER RELEASE BUILD PIPELINE")
    print("=" * 60)

    # 1. PyInstaller Build
    py_exe = sys.executable
    run_step(f'"{py_exe}" -m PyInstaller --noconfirm main.spec', "Compiling debloated onedir & portable binaries")

    # 2. Duplicate portable to backward-compatible names
    portable_exe = os.path.join(DIST_DIR, "StreamerCalyx_Portable.exe")
    std_exe = os.path.join(DIST_DIR, "StreamerCalyx.exe")
    legacy_exe = os.path.join(DIST_DIR, "HotKeyOverlayAlert.exe")

    if os.path.exists(portable_exe):
        shutil.copy2(portable_exe, std_exe)
        shutil.copy2(portable_exe, legacy_exe)
        print("[OK] Replicated portable executable to StreamerCalyx.exe and HotKeyOverlayAlert.exe")

    # Copy root icon files into StreamerCalyx_app
    app_dir = os.path.join(DIST_DIR, "StreamerCalyx_app")
    if os.path.exists(app_dir):
        for icon_file in ["icon.ico", "icon.png"]:
            src_icon = os.path.join(REPO_ROOT, icon_file)
            if os.path.exists(src_icon):
                shutil.copy2(src_icon, os.path.join(app_dir, icon_file))

    # 3. Build NSIS Modern Installer
    if os.path.exists(MAKENSIS_EXE):
        nsi_script = os.path.join(REPO_ROOT, "installer", "StreamerCalyx_Installer.nsi")
        run_step(f'"{MAKENSIS_EXE}" "{nsi_script}"', "Compiling NSIS Modern Installer (StreamerCalyx_Setup.exe)")
    else:
        print(f"[WARN] makensis.exe not found at {MAKENSIS_EXE}, skipping installer compilation.")

    # 4. Authenticode EV Digital Signing
    if os.path.exists(SIGNTOOL_EXE):
        targets = [
            os.path.join(DIST_DIR, "StreamerCalyx_app", "StreamerCalyx.exe"),
            portable_exe,
            std_exe,
            legacy_exe,
            os.path.join(DIST_DIR, "StreamerCalyx_Setup.exe"),
        ]
        valid_targets = [f'"{t}"' for t in targets if os.path.exists(t)]
        if valid_targets:
            targets_str = " ".join(valid_targets)
            sign_cmd = f'"{SIGNTOOL_EXE}" sign /sha1 {EV_THUMBPRINT} /tr {TIMESTAMP_URL} /td sha256 /fd sha256 {targets_str}'
            run_step(sign_cmd, "Signing binaries with DigiCert EV hardware token")

            verify_cmd = f'"{SIGNTOOL_EXE}" verify /pa {targets_str}'
            run_step(verify_cmd, "Verifying Authenticode EV digital signatures")
    else:
        print("[WARN] signtool.exe not found, skipping EV code signing.")

    # 5. Deploy to Streamer's Desktop
    desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.exists(desktop_dir):
        if os.path.exists(portable_exe):
            try:
                shutil.copy2(portable_exe, os.path.join(desktop_dir, "StreamerCalyx_Portable.exe"))
                print(f"[OK] Deployed StreamerCalyx_Portable.exe to Desktop")
            except Exception as e:
                print(f"[WARN] Could not update Desktop StreamerCalyx_Portable.exe: {e}")
        if os.path.exists(std_exe):
            try:
                shutil.copy2(std_exe, os.path.join(desktop_dir, "StreamerCalyx.exe"))
                print(f"[OK] Deployed StreamerCalyx.exe to Desktop")
            except Exception as e:
                print(f"[WARN] Could not update Desktop StreamerCalyx.exe (process running): {e}")
        setup_exe = os.path.join(DIST_DIR, "StreamerCalyx_Setup.exe")
        if os.path.exists(setup_exe):
            try:
                shutil.copy2(setup_exe, os.path.join(desktop_dir, "StreamerCalyx_Setup.exe"))
                print(f"[OK] Deployed StreamerCalyx_Setup.exe to Desktop")
            except Exception as e:
                print(f"[WARN] Could not update Desktop StreamerCalyx_Setup.exe: {e}")

    print("\n" + "=" * 60)
    print("[SUCCESS] ALL RELEASE ARTIFACTS BUILT, SIGNED & DEPLOYED!")
    print("=" * 60)

if __name__ == "__main__":
    main()
