# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('app_icon.ico', '.'),
        ('app_icon.png', '.'),
        ('splash_logo.png', '.'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'pymupdf',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Omit heavy unused AI / ONNX / LLM modules
        'onnxruntime',
        'pymupdf.layout',
        'pymupdf_layout',
        'pymupdf4llm',
        'numpy',
        'networkx',
        'yaml',
        'PyYAML',
        'psutil',
        'tabulate',
        # Omit test frameworks
        'pytest',
        '_pytest',
        'unittest',
        # Omit unused heavy PySide6 components to keep exe small and fast
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineQuick',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.Qt3DCore',
        'PySide6.QtSensors',
        'PySide6.QtPositioning',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtSpatialAudio',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtDesigner',
        'PySide6.QtHelp',
        'PySide6.QtTest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

splash = Splash(
    'splash_logo.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    text_size=12,
    always_on_top=True,
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Ramov',
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
    icon='app_icon.ico',
)
