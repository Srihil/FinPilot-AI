# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for FinPilot Tally Connector.
Produces a single .exe that customers can download and run on Windows.

Build command:
    pyinstaller finpilot_connector.spec
Output:
    dist/finpilot-tally-connector.exe
"""

block_cipher = None

a = Analysis(
    ['connector.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('.env.example', '.'),   # bundled so user has a reference
    ],
    hiddenimports=[
        'httpx',
        'httpcore',
        'anyio',
        'dotenv',
        'defusedxml',
        'defusedxml.ElementTree',
        'tally_client',
        'config',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='finpilot-tally-connector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # keep console window — user needs to see output
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
