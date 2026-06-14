# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['rtt_python_gui.py'],
    datas=[('debug/demo_log.txt', 'debug')],
    hiddenimports=['PIL._tkinter_finder'],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6'],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='rtt_python_gui',
    strip=True,
    upx=True,
    console=False,
)
