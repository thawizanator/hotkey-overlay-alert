# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

datas = [
    ('icon.ico', '.'),
    ('icon.png', '.'),
    ('splash-image.png', '.')
] + collect_data_files('aiortc')

hidden_imports = [
    'PyQt6.QtGui',
    'PyQt6.QtWebSockets',
    'splash_screen',
    'director_tab',
    'director_panel',
    'streamlabs_client',
    'director_security',
    'webrtc_p2p',
    'cryptography',
    'pylibsrtp',
    'input_manager',
    'hotkey_tab',
    'PyQt6.QtMultimedia',
    'soundboard_engine',
    'soundboard_tab',
    'soundboard_spam_guard',
    'soundboard_lan_bridge',
    'auto_clip_engine',
    'autoclip_tab',
    'audio_diagnostics',
    'about_tab',
    'stream_launch_tab',
    'logs_tab',
    'beta_telemetry_dialog',
    'debug_logger',
] + collect_submodules('aiortc') + collect_submodules('aioice')

excluded_modules = [
    'PyQt6.QtQml',
    'PyQt6.QtQuick',
    'PyQt6.QtQuickWidgets',
    'PyQt6.QtQuick3D',
    'PyQt6.QtQuick3DRuntimeRender',
    'PyQt6.QtDesigner',
    'PyQt6.QtPdf',
    'PyQt6.QtPdfWidgets',
    'PyQt6.QtVirtualKeyboard',
    'PyQt6.QtBluetooth',
    'PyQt6.QtNfc',
    'PyQt6.QtPositioning',
    'PyQt6.QtSensors',
    'PyQt6.QtSerialPort',
    'PyQt6.QtWebChannel',
    'PyQt6.QtSql',
    'PyQt6.QtTest',
    'numpy',
    'scipy',
    'matplotlib',
    'pandas',
    'setuptools',
    'pkg_resources',
    'tkinter',
    'unittest',
    'distutils',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
)

# Debloat: Filter heavy unused dynamic libraries
EXCLUDED_DLLS = {
    'opengl32sw.dll',
    'qt6qml.dll',
    'qt6qmlmodels.dll',
    'qt6quick.dll',
    'qt6quickwidgets.dll',
    'qt6quick3d.dll',
    'qt6quick3druntimerender.dll',
    'qt6designer.dll',
    'qt6pdf.dll',
    'qt6pdfwidgets.dll',
    'qt6virtualkeyboard.dll',
    'qt6bluetooth.dll',
    'qt6nfc.dll',
    'qt6positioning.dll',
    'qt6sensors.dll',
    'qt6serialport.dll',
    'qt6webchannel.dll',
    'qt6sql.dll',
    'qt6test.dll',
}

def is_excluded_binary(bin_tuple):
    name = os.path.basename(bin_tuple[0]).lower()
    return name in EXCLUDED_DLLS

a.binaries = [b for b in a.binaries if not is_excluded_binary(b)]

pyz = PYZ(a.pure)

# 1. Onedir target for NSIS Installer (sub-second launch from unpacked directory)
exe_app = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StreamerCalyx',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    version='version_info.txt',
    icon=['icon.ico'],
)

coll = COLLECT(
    exe_app,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='StreamerCalyx_app',
)

# 2. Onefile target for Standalone Portable (.exe)
exe_portable = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='StreamerCalyx_Portable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    version='version_info.txt',
    icon=['icon.ico'],
)
