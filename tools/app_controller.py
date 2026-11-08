"""Verified Application Controller with Windows Process Table Tracking.

Inspired by Mark-LVI's actions/open_app.py:
Verifies every app launch or termination against psutil's live process table
rather than blindly assuming success from subprocess.Popen.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import Any

import psutil

from core.outcome import done, failed, unverified
from tools.registry import register_tool

logger = logging.getLogger("SARATHI.AppController")

# Common Windows App Aliases & Executable Names
APP_ALIASES: dict[str, list[str]] = {
    "notepad": ["notepad.exe", "notepad"],
    "calculator": ["calc.exe", "calculator", "calc"],
    "calc": ["calc.exe"],
    "chrome": ["chrome.exe", "google chrome"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe", "microsoft edge"],
    "msedge": ["msedge.exe"],
    "code": ["code.cmd", "code.exe", "visual studio code"],
    "vscode": ["code.cmd", "code.exe"],
    "spotify": ["spotify.exe"],
    "explorer": ["explorer.exe"],
    "file explorer": ["explorer.exe"],
    "terminal": ["wt.exe", "powershell.exe", "cmd.exe"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "task manager": ["taskmgr.exe"],
    "settings": ["ms-settings:"],
}


def _find_running_process(target_names: list[str]) -> psutil.Process | None:
    """Scans active process table for any process matching target names."""
    target_lowers = [t.lower().replace(".exe", "") for t in target_names]
    for p in psutil.process_iter(["pid", "name"]):
        try:
            p_name = p.info["name"].lower().replace(".exe", "")
            if p_name in target_lowers or any(t in p_name for t in target_lowers):
                return p
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


@register_tool(
    name="open_application_verified",
    description="Launches a desktop application on Windows and verifies via the process table that it is actually running."
)
def open_application_verified(app_name: str) -> str:
    """Launches an application and verifies its process started."""
    clean = app_name.strip().lower()
    if not clean:
        return failed("open_app", "No application name provided")

    candidates = APP_ALIASES.get(clean, [clean, f"{clean}.exe"])

    # Check if already running
    existing = _find_running_process(candidates)
    if existing:
        return done("open_app", app=clean, pid=existing.pid, note="Already running")

    # Try launching executable
    launched = False
    exec_target = clean

    # Check standard PATH
    for cand in candidates:
        found = shutil.which(cand)
        if found:
            exec_target = found
            break

    try:
        if clean in ("settings", "ms-settings"):
            os.system("start ms-settings:")
            launched = True
        else:
            subprocess.Popen(exec_target, shell=True)
            launched = True
    except Exception as e:
        return failed("open_app", f"Launch command failed: {e}", app=clean)

    # Verification: Poll process table for up to 3.0s
    start_wait = time.time()
    while time.time() - start_wait < 3.0:
        time.sleep(0.3)
        proc = _find_running_process(candidates)
        if proc:
            return done("open_app", app=clean, pid=proc.pid, verified=True)

    return unverified("open_app", app=clean, note="Dispatched launch command, but process not confirmed in table yet")


@register_tool(
    name="close_application_verified",
    description="Closes a running desktop application by name and verifies its removal from the process table."
)
def close_application_verified(app_name: str, force: bool = False) -> str:
    """Terminates an application and verifies it stopped running."""
    clean = app_name.strip().lower()
    candidates = APP_ALIASES.get(clean, [clean, f"{clean}.exe"])
    target_lowers = [t.lower().replace(".exe", "") for t in candidates]

    matched_procs: list[psutil.Process] = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            p_name = p.info["name"].lower().replace(".exe", "")
            if p_name in target_lowers or any(t == p_name for t in target_lowers):
                matched_procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not matched_procs:
        return failed("close_app", f"No running process found for '{clean}'", app=clean)

    closed_count = 0
    for p in matched_procs:
        try:
            if force:
                p.kill()
            else:
                p.terminate()
            closed_count += 1
        except Exception:
            pass

    # Wait for process exit verification
    time.sleep(0.5)
    still_running = _find_running_process(candidates)
    if not still_running:
        return done("close_app", app=clean, closed_instances=closed_count, verified=True)
    elif force:
        try:
            still_running.kill()
            return done("close_app", app=clean, forced=True, verified=True)
        except Exception as e:
            return failed("close_app", str(e), app=clean)

    return unverified("close_app", app=clean, note="Termination signal sent; app may be waiting on user confirmation dialog")


@register_tool(
    name="list_running_applications",
    description="Returns a list of currently running user applications with process IDs and memory utilization."
)
def list_running_applications(limit: int = 15) -> str:
    """Lists prominent user desktop processes."""
    apps = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            name = p.info["name"]
            # Filter out system low-level background threads
            if name.lower().endswith(".exe") and not name.lower().startswith(("svchost", "system", "smss", "csrss")):
                mem_mb = round(p.info["memory_info"].rss / (1024 * 1024), 1)
                apps.append({"pid": p.info["pid"], "name": name, "mem_mb": mem_mb})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    apps.sort(key=lambda x: x["mem_mb"], reverse=True)
    top_apps = apps[:limit]
    return done("list_apps", count=len(top_apps), processes=top_apps)


__all__ = [
    "open_application_verified",
    "close_application_verified",
    "list_running_applications"
]
