# -*- mode: python ; coding: utf-8 -*-

import os

# Speed optimizations
EXCLUDES = [
    'tkinter', 'test', 'unittest', 'pdb', 'distutils', 'setuptools',
    'PIL', 'matplotlib', 'numpy', 'scipy', 'pandas'  # Exclude if not used
]

# Get the directory where this spec file is located
SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
ICON_PATH = os.path.join(SPEC_DIR, 'icon.ico')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=True,  # Faster import
    optimize=2,      # Bytecode optimization
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Notepad',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
)
