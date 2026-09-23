# -*- coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# ========================================================
# 🔧 CONFIGURATION SECTION
# ========================================================
APP_NAME = "FastClip"
MAIN_SCRIPT = "fastclip.pyw"
ICON_FILE = "logo.ico"

# List of hidden imports (modules that PyInstaller cannot detect)
HIDDEN_IMPORTS = []

# List of extra data files to include INSIDE the exe (src, dst)
ADDED_FILES = []
# ========================================================

spec_path = os.path.abspath(sys.argv[0])
spec_dir = os.path.dirname(spec_path)
project_root = os.path.abspath(os.path.join(spec_dir, ".."))

# Resolve paths
script_path = os.path.join(project_root, MAIN_SCRIPT)
icon_path = os.path.join(project_root, ICON_FILE) if ICON_FILE else None

# Collect resources for specific libraries if needed
# Example: tmp_ret = collect_all('some_lib')
# datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

added_files = ADDED_FILES + [
    (os.path.join(project_root, "VERSION"), "."),
]

a = Analysis(
    [script_path],
    pathex=[project_root],
    binaries=[],
    datas=added_files,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

