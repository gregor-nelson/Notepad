# main.spec - Production PyInstaller spec file (no console)
# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# Analysis configuration
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include icon and essential data files
        ('icon.ico', '.'),
        ('syntax_highlighter.py', '.'),
    ],
    hiddenimports=[
        # Essential PyQt6 modules - these made it work
        'PyQt6.QtCore',
        'PyQt6.QtGui', 
        'PyQt6.QtWidgets',
        'PyQt6.QtSvg',
        'PyQt6.QtPrintSupport',
        # Additional imports that might be needed
        'PyQt6.sip',
        'sip',
        'codecs',
        'logging',
        'datetime',
        'pathlib',
        'platform',
        'time',
        'os',
        'sys',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Safe to exclude - these don't break the app
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PIL',
        'Pillow',
        'unittest',
        'pydoc',
        'doctest',
        'pdb',
        'profile',
        'cProfile',
        'turtle',
        'email',
        'http',
        'ftplib',
        'xml.etree',
        'sqlite3',
        'multiprocessing',
        'asyncio',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Optimize by removing debug info
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Production version - single file, no console, optimized
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='main',
    debug=False,              # No debug info
    bootloader_ignore_signals=False,
    strip=False,              # DISABLED: Windows doesn't have strip utility
    upx=False,                # UPX can sometimes cause issues
    console=False,            # NO CONSOLE WINDOW
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',          # Your icon
)

# Alternative: Onedir version for faster startup (uncomment to use)
# This creates a folder with multiple files but starts faster
"""
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,              # DISABLED: Windows doesn't have strip utility
    upx=False,
    console=False,            # NO CONSOLE WINDOW
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,              # DISABLED: Windows doesn't have strip utility
    upx=False,
    upx_exclude=[],
    name='main',
)
"""

# BUILD INSTRUCTIONS:
# 1. Save this as "main.spec"
# 2. Run: pyinstaller.exe --clean main.spec
# 3. Your executable will be: dist/main.exe (single file, no console)
#
# NOTE: strip=False is used because Windows doesn't have the 'strip' utility by default
# This means slightly larger file size but prevents build errors
#
# For faster startup, uncomment the onedir version above and comment out the onefile version
# Then the executable will be: dist/main/main.exe (folder with files, faster startup)