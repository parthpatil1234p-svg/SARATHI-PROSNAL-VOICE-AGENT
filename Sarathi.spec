# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for S.A.R.A.T.H.I. Desktop AI Voice Assistant."""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Base repository root
ROOT_DIR = Path.cwd()

# Locate openwakeword model directory
import openwakeword
oww_dir = Path(openwakeword.__file__).parent
oww_models_dir = oww_dir / "resources" / "models"

# Gather data files
datas = [
    (str(ROOT_DIR / "gui" / "web"), "gui/web"),
    (str(ROOT_DIR / "assets"), "assets"),
    (str(ROOT_DIR / ".env.example"), "."),
]

if (ROOT_DIR / ".env").exists():
    datas.append((str(ROOT_DIR / ".env"), "."))

if oww_models_dir.exists():
    datas.append((str(oww_models_dir), "openwakeword/resources/models"))

# Collect submodules and data
hidden_imports = [
    "webview",
    "webview.platforms.winforms",
    "clr",
    "pythonnet",
    "clr_loader",
    "bottle",
    "comtypes",
    "comtypes.client",
    "pycaw",
    "pycaw.pycaw",
    "pycaw.utils",
    "sounddevice",
    "soundfile",
    "numpy",
    "onnxruntime",
    "openwakeword",
    "openwakeword.model",
    "openwakeword.utils",
    "groq",
    "google.genai",
    "edge_tts",
    "pyttsx3",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "psutil",
    "mss",
    "customtkinter",
    "rich",
    "pydantic",
    "pydantic_settings",
    "httpx",
    "httpcore",
    "h2",
    "asyncio",
    "threading",
    "queue",
    "pythoncom",
    "win32com",
    "win32com.client",
    "faster_whisper",
    "ctranslate2",
]

# Add any additional submodules
hidden_imports += collect_submodules("openwakeword")
hidden_imports += collect_submodules("pydantic")
hidden_imports += collect_submodules("pydantic_settings")
hidden_imports += collect_submodules("httpx")

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest"],
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
    name="Sarathi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Clean windowed desktop app with HUD, no black terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Sarathi",
)
