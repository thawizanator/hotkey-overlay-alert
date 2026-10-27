# -*- mode: python ; coding: utf-8 -*-
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
] + collect_submodules('aiortc') + collect_submodules('aioice')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='StreamerCalyx',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    icon=['icon.ico'],
)
