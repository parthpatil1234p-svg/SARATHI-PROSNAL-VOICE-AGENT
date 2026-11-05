"""Windows 11 OS Control Tools: Volume (PyCAW), App Launcher, and Media Keys."""

import logging
import subprocess

from tools.registry import register_tool

logger = logging.getLogger("JARVIS.OSTools")


@register_tool(
    name="set_system_volume",
    description="Sets the master Windows system audio volume to a specific percentage between 0 and 100."
)
def set_system_volume(level: int) -> str:
    """Sets master volume percentage (0-100)."""
    try:
        from pycaw.pycaw import AudioUtilities

        spk = AudioUtilities.GetSpeakers()
        clamped = max(0, min(100, int(level)))
        scalar = clamped / 100.0
        spk.EndpointVolume.SetMasterVolumeLevelScalar(scalar, None)
        return f"Master audio volume successfully adjusted to {clamped}%."
    except Exception as e:
        return f"Unable to adjust volume: {e}"


@register_tool(
    name="mute_system",
    description="Toggles or sets the system audio mute state."
)
def mute_system(mute: bool = True) -> str:
    """Mutes or unmutes system sound."""
    try:
        from pycaw.pycaw import AudioUtilities

        spk = AudioUtilities.GetSpeakers()
        spk.EndpointVolume.SetMute(int(mute), None)
        return "Audio muted, sir." if mute else "Audio unmuted, sir."
    except Exception as e:
        return f"Failed to toggle mute: {e}"


@register_tool(
    name="open_application",
    description="Opens or launches a desktop application on Windows (e.g., 'notepad', 'calc', 'chrome', 'spotify', 'code', 'cmd')."
)
def open_application(app_name: str) -> str:
    """Launches an application by common name or executable."""
    cleaned = app_name.strip().lower()

    app_aliases = {
        "calculator": "calc",
        "chrome": "start chrome",
        "browser": "start chrome",
        "edge": "start msedge",
        "notepad": "notepad",
        "code": "code",
        "vs code": "code",
        "vscode": "code",
        "cmd": "start cmd",
        "terminal": "start wt",
        "explorer": "explorer",
        "files": "explorer",
        "task manager": "taskmgr",
        "settings": "start ms-settings:",
        "spotify": "start spotify:",
    }

    cmd = app_aliases.get(cleaned, cleaned)
    try:
        # Use shell execution or os.startfile if exists
        subprocess.Popen(cmd, shell=True)
        return f"Opening {app_name}, sir."
    except Exception as e:
        return f"Could not launch application '{app_name}': {e}"


@register_tool(
    name="media_control",
    description="Controls media playback on Windows: 'play_pause', 'next', 'previous', 'stop'."
)
def media_control(action: str) -> str:
    """Simulates Windows multimedia key events."""
    import ctypes

    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PREV_TRACK = 0xB1
    VK_MEDIA_STOP = 0xB2
    VK_MEDIA_PLAY_PAUSE = 0xB3
    KEYEVENTF_KEYUP = 0x0002

    key_map = {
        "play": VK_MEDIA_PLAY_PAUSE,
        "pause": VK_MEDIA_PLAY_PAUSE,
        "play_pause": VK_MEDIA_PLAY_PAUSE,
        "toggle": VK_MEDIA_PLAY_PAUSE,
        "next": VK_MEDIA_NEXT_TRACK,
        "previous": VK_MEDIA_PREV_TRACK,
        "prev": VK_MEDIA_PREV_TRACK,
        "stop": VK_MEDIA_STOP,
    }

    vk = key_map.get(action.lower().strip())
    if not vk:
        return f"Unknown media action: '{action}'. Available: play_pause, next, previous, stop."

    try:
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        return f"Media {action} command executed."
    except Exception as e:
        return f"Failed to execute media key: {e}"
