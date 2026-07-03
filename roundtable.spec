# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None
src = Path(SPECPATH)

a = Analysis(
    [str(src / 'launcher.py')],
    pathex=[str(src)],
    binaries=[],
    datas=[
        (str(src / 'web' / 'static'), 'web/static'),
        (str(src / '.env.example'), '.'),
    ],
    hiddenimports=['openai', 'dotenv', 'rich', 'markdown', 'roundtable'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test', 'unittest', 'test'],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Roundtable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 调试用
    icon=None,
    version_info=None,
)
