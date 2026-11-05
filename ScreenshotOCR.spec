# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH)
datas = collect_data_files('rapidocr_onnxruntime')
datas += [(str(root / 'assets' / 'app.ico'), 'assets')]
if (root / 'third_party').exists():
    datas += [(str(root / 'third_party'), 'third_party')]
# Carry DLL dependencies required on a Windows machine without Python installed.
system32 = Path(os.environ['SystemRoot']) / 'System32'
binaries = [(str(system32 / name), '.') for name in ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll') if (system32 / name).exists()]
a = Analysis(
    [str(root / 'app.py')],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pandas', 'IPython', 'pytest', 'PySide6.QtNetwork', 'PySide6.QtOpenGL', 'PySide6.QtQml', 'PySide6.QtQuick'],
    noarchive=False,
    optimize=1,
)
# Qt 6.12 calls the Windows ICU API (unversioned exports). A Poppler ICU
# on the build machine PATH has a colliding name and incompatible exports.
# Resolve this import to the OS, never bundle that unrelated ICU implementation.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='ScreenshotOCR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(root / 'assets' / 'app.ico'),
)
