# -*- mode: python ; coding: utf-8 -*-

# Speed optimizations
EXCLUDES = [
    'tkinter', 'test', 'unittest', 'pdb', 'distutils', 'setuptools',
    'PIL', 'matplotlib', 'numpy', 'scipy', 'pandas'  # Exclude if not used
]

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
    [],
    exclude_binaries=True,
    name='Notepad',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Notepad',
)
