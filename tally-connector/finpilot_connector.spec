# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for FinPilot Tally Connector GUI (system tray app).
Target: smallest possible .exe size.
"""

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pystray._win32',
        'PIL._tkinter_finder',
        'defusedxml',
        'defusedxml.ElementTree',
        'tally_client',
        'config',
        'connector',
        'tkinter',
        'tkinter.font',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'pytest', 'unittest', 'setuptools',
        'cryptography', 'ssl', '_ssl',
        'multiprocessing', 'concurrent',
        'xmlrpc', 'ftplib', 'imaplib', 'poplib', 'smtplib',
        'doctest', 'pdb', 'profile', 'pstats',
        'curses', 'readline',
    ],
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
    strip=True,           # strip debug symbols
    upx=True,             # compress with UPX
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # no console window — pure GUI tray app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
