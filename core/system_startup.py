"""Windows 11 Automatic Startup and Background Runner Configuration for S.A.R.A.T.H.I.

Configures SARATHI to start automatically on Windows boot in the background,
silently listening for 'Hey Sarathi' and waking up instantly when summoned.
"""

import logging
import os
import sys
import winreg
from pathlib import Path

from config.settings import EXE_DIR

logger = logging.getLogger("SARATHI.Startup")

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_APP_NAME = "SARATHI_AI_ASSISTANT"


def get_startup_shortcut_path() -> Path:
    """Returns the user's Windows Startup folder shortcut path."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "SARATHI.lnk"


def get_vbs_launcher_path() -> Path:
    """Returns the path to the silent VBS launcher."""
    return EXE_DIR / "Launch_Sarathi_Background.vbs"


def get_target_executable_command() -> str:
    """Determines the target command to run on startup in the background."""
    # If compiled exe exists, prefer it
    exe_candidate = EXE_DIR / "dist" / "Sarathi" / "Sarathi.exe"
    if not exe_candidate.exists():
        exe_candidate = EXE_DIR / "Sarathi.exe"

    if exe_candidate.exists():
        return f'"{exe_candidate}" --background'

    # Fallback to python in current venv
    venv_python = EXE_DIR / ".venv" / "Scripts" / "pythonw.exe"
    if not venv_python.exists():
        venv_python = EXE_DIR / ".venv" / "Scripts" / "python.exe"

    main_py = EXE_DIR / "main.py"
    return f'"{venv_python}" "{main_py}" --background'


def enable_auto_startup(start_in_background: bool = True) -> dict:
    """
    Enables SARATHI to start automatically on Windows boot.
    Configures both the Windows Startup folder shortcut and Windows Registry Run key.
    """
    results = {"shortcut": False, "registry": False, "target": ""}
    shortcut_path = get_startup_shortcut_path()
    vbs_path = get_vbs_launcher_path()

    # 1. Ensure silent VBS launcher exists
    exe_cmd = get_target_executable_command()
    results["target"] = exe_cmd

    # 2. Configure Windows Registry Run Key
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            # If VBS launcher exists, run via wscript.exe silently, else run target command
            if vbs_path.exists():
                reg_cmd = f'wscript.exe "{vbs_path}"'
            else:
                reg_cmd = exe_cmd
            winreg.SetValueEx(key, REG_APP_NAME, 0, winreg.REG_SZ, reg_cmd)
            results["registry"] = True
            logger.info(f"Registry Run key set: {REG_APP_NAME} -> {reg_cmd}")
    except Exception as e:
        logger.warning(f"Failed to set Windows Registry Run key: {e}")

    # 3. Create Windows Startup folder shortcut
    try:
        import base64
        import subprocess
        target_file = str(vbs_path if vbs_path.exists() else (EXE_DIR / "Launch_Sarathi.bat"))
        ps_script = (
            f"$ws = New-Object -ComObject WScript.Shell\n"
            f"$s = $ws.CreateShortcut('{shortcut_path}')\n"
            f"$s.TargetPath = '{target_file}'\n"
            f"$s.WorkingDirectory = '{EXE_DIR}'\n"
            f"$s.WindowStyle = 7\n"
            f"$s.Save()\n"
        )
        encoded_cmd = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")
        subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded_cmd], check=True, capture_output=True)
        results["shortcut"] = shortcut_path.exists()
        logger.info(f"Startup shortcut created at: {shortcut_path}")
    except Exception as e:
        logger.warning(f"Failed to create startup shortcut: {e}")

    return results


def disable_auto_startup() -> dict:
    """Disables auto-startup by removing shortcut and registry entry."""
    results = {"shortcut_removed": False, "registry_removed": False}
    shortcut_path = get_startup_shortcut_path()

    try:
        if shortcut_path.exists():
            shortcut_path.unlink()
            results["shortcut_removed"] = True
    except Exception as e:
        logger.warning(f"Error removing shortcut: {e}")

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, REG_APP_NAME)
                results["registry_removed"] = True
            except FileNotFoundError:
                results["registry_removed"] = True
    except Exception as e:
        logger.warning(f"Error removing registry key: {e}")

    return results


def is_auto_startup_enabled() -> bool:
    """Checks if auto-startup is configured in Registry or Startup folder."""
    shortcut_path = get_startup_shortcut_path()
    if shortcut_path.exists():
        return True

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, REG_APP_NAME)
            return bool(val)
    except Exception:
        return False
