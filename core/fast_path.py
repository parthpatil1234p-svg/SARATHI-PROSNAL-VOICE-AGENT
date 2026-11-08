"""Rule-based intent fast-path router.

Bypasses cloud LLM inference completely for deterministic local commands:
- Master volume & mute
- System date & time
- Application launching
- Real-time hardware diagnostics & battery status
- Timers and countdowns
"""

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Any

from config.settings import settings
from tools.os_tools import mute_system, open_application, set_system_volume
from tools.system_tools import get_system_diagnostics

logger = logging.getLogger("SARATHI.FastPath")

# Active background timers
_active_timers: list[asyncio.Task] = []


class FastPathResult:
    def __init__(self, matched: bool, spoken_text: str = "", tool_name: str = "", tool_result: Any = None):
        self.matched = matched
        self.spoken_text = spoken_text
        self.tool_name = tool_name
        self.tool_result = tool_result


def check_fast_path(user_text: str) -> FastPathResult:
    """
    Checks if a user transcript matches a deterministic command rule.
    Returns FastPathResult(matched=True, spoken_text=..., tool_name=..., tool_result=...).
    """
    cleaned = user_text.strip().lower().rstrip(".,!?")

    # 1. System Time & Date
    if any(q in cleaned for q in ("what time is it", "what's the time", "current time", "tell me the time", "what is the time")):
        now = datetime.now()
        time_str = now.strftime("%I:%M %p").lstrip("0")
        spoken = f"It is currently {time_str}, sir."
        return FastPathResult(True, spoken, "get_time", time_str)

    if any(q in cleaned for q in ("what is today's date", "what's today's date", "today's date", "what is the date", "what's the date", "what day is it")):
        now = datetime.now()
        day_str = now.strftime("%A, %B %d, %Y")
        spoken = f"Today is {day_str}, sir."
        return FastPathResult(True, spoken, "get_date", day_str)

    # 2. Master System Volume Control
    vol_match = re.search(r'(?:set\s+)?volume\s+(?:to\s+)?(\d{1,3})(?:\s*%)?', cleaned)
    if vol_match:
        val = int(vol_match.group(1))
        res = set_system_volume(val)
        spoken = f"Master audio volume adjusted to {val} percent, sir."
        return FastPathResult(True, spoken, "set_system_volume", res)

    if cleaned in ("mute", "mute audio", "mute system", "mute sound"):
        res = mute_system(True)
        return FastPathResult(True, "System audio muted, sir.", "mute_system", res)

    if cleaned in ("unmute", "unmute audio", "unmute system", "unmute sound"):
        res = mute_system(False)
        return FastPathResult(True, "System audio unmuted, sir.", "mute_system", res)

    # 3. Application Launcher
    app_match = re.match(r'(?:open|launch|start)\s+([a-zA-Z0-9\s]+)', cleaned)
    if app_match:
        app_name = app_match.group(1).strip()
        common_apps = {
            "notepad", "calc", "calculator", "chrome", "google chrome", "browser",
            "edge", "microsoft edge", "spotify", "code", "vs code", "vscode",
            "cmd", "terminal", "powershell", "task manager", "settings", "explorer"
        }
        if app_name in common_apps:
            res = open_application(app_name)
            spoken = f"Launching {app_name}, sir."
            return FastPathResult(True, spoken, "open_application", res)

    # 4. System Diagnostics & Hardware
    if any(q in cleaned for q in ("cpu usage", "battery level", "battery status", "how much ram", "system diagnostics", "hardware status")):
        diag = get_system_diagnostics()
        cpu = diag.get("cpu_usage_percent", "unknown")
        ram = diag.get("ram_usage", "unknown")
        spoken = f"Diagnostics nominal, sir. CPU is at {cpu}, with RAM usage at {ram}."
        return FastPathResult(True, spoken, "get_system_diagnostics", diag)

    # 5. Timers
    timer_match = re.search(r'set\s+(?:a\s+)?timer\s+(?:for\s+)?(\d+)\s*(second|minute|sec|min)s?', cleaned)
    if timer_match:
        amount = int(timer_match.group(1))
        unit = timer_match.group(2)
        total_seconds = amount * 60 if unit.startswith("min") else amount
        spoken = f"Timer set for {amount} {unit}{'s' if amount > 1 else ''}, sir."

        # Schedule background chime when complete
        async def _timer_worker():
            await asyncio.sleep(total_seconds)
            from voice.player import player
            logger.info(f"Timer for {amount} {unit} expired!")
            from core.orchestrator import AssistantOrchestrator
            # Play notification
            await player.play_chime("wake")

        try:
            loop = asyncio.get_running_loop()
            t = loop.create_task(_timer_worker())
            _active_timers.append(t)
        except Exception:
            pass

        return FastPathResult(True, spoken, "set_timer", {"seconds": total_seconds})

    # 6. Greetings & Instant Pleasantries (<5ms response)
    if cleaned in ("hi", "hello", "hey", "hii", "heyy", "namaste", "hey sarathi", "hi sarathi", "hello sarathi"):
        user_name = getattr(settings, "USER_NAME", "Sir")
        asst_name = getattr(settings, "ASSISTANT_NAME", "SARATHI")
        spoken = f"Hello {user_name}! {asst_name} is online and operational. How can I assist you today?"
        return FastPathResult(True, spoken, "greeting", {"status": "ready"})

    if any(q in cleaned for q in ("good morning", "shubh prabhat")):
        user_name = getattr(settings, "USER_NAME", "Sir")
        spoken = f"Good morning, {user_name}. All systems are nominal. Standing by for your command."
        return FastPathResult(True, spoken, "greeting_morning", {})

    if any(q in cleaned for q in ("good evening", "good afternoon")):
        user_name = getattr(settings, "USER_NAME", "Sir")
        spoken = f"Good day, {user_name}. How can I assist you?"
        return FastPathResult(True, spoken, "greeting_day", {})

    # 7. Identity & Personal Questions (Instant <10ms response)
    if any(q in cleaned for q in ("what is my name", "what's my name", "who am i", "do you know my name", "tell me my name", "mera naam kya hai")):
        user_name = getattr(settings, "USER_NAME", "Sir")
        spoken = f"Your name is set as {user_name}, sir."
        return FastPathResult(True, spoken, "user_identity", {"user_name": user_name})

    if any(q in cleaned for q in ("what is your name", "what's your name", "who are you", "what should i call you", "tell me your name", "tum kaun ho")):
        asst_name = getattr(settings, "ASSISTANT_NAME", "SARATHI")
        spoken = f"I am {asst_name}, your personal desktop AI voice assistant, sir."
        return FastPathResult(True, spoken, "assistant_identity", {"assistant_name": asst_name})

    if any(q in cleaned for q in ("how are you", "how are you doing", "how r u", "kaisa hai", "kaise ho")):
        asst_name = getattr(settings, "ASSISTANT_NAME", "SARATHI")
        spoken = f"All systems are operational and running at peak performance, sir. How can I assist you?"
        return FastPathResult(True, spoken, "assistant_status", {"status": "nominal"})

    if any(q in cleaned for q in ("kiske api", "which api", "whose api", "what api", "konse api", "kaunse api", "what model are you")):
        spoken = "Main Groq Cloud API pe run kar raha hoon, powered by Groq's high-speed LPU inference engine."
        return FastPathResult(True, spoken, "api_identity", {"provider": "groq", "api": "Groq Cloud API"})

    return FastPathResult(False)
