"""Python <-> JavaScript bridge for J.A.R.V.I.S. Mark VII Tactical HUD."""

import asyncio
import logging
import os
import threading
import time
from typing import Any

import psutil

from config.settings import BASE_DIR, settings
from core.orchestrator import AssistantOrchestrator
from tools.os_tools import mute_system, set_system_volume
from tools.system_tools import get_system_diagnostics, purge_system_cache
from tools.vision_tools import analyze_screen
from voice.audio_stream import AudioInputStream
from voice.player import player
from voice.tts.voice_cloner import voice_cloner

logger = logging.getLogger("JARVIS.WebBridge")


class JarvisWebBridge:
    """
    Exposes Python backend methods to the JavaScript front-end via pywebview.
    Methods are callable from JS as `window.pywebview.api.<method_name>(...)`.
    """

    def __init__(self, orchestrator: AssistantOrchestrator, window=None):
        self.orchestrator = orchestrator
        self.window = window
        self.loop: asyncio.AbstractEventLoop | None = None
        self.voice_task: asyncio.Task | None = None
        self.is_voice_active = False
        self.is_mic_muted = False

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Sets the active asyncio event loop."""
        self.loop = loop

    def set_window(self, window):
        """Sets the pywebview window instance."""
        self.window = window

    # -------------------------------------------------------------
    # Window Controls (Minimize, Maximize, Close)
    # -------------------------------------------------------------
    def minimize_window(self):
        """Minimizes the native application window."""
        if self.window:
            try:
                self.window.minimize()
            except Exception as e:
                logger.warning(f"Window minimize error: {e}")

    def maximize_window(self):
        """Toggles maximize/restore state."""
        if self.window:
            try:
                self.window.toggle_fullscreen()
            except Exception as e:
                logger.warning(f"Window toggle fullscreen error: {e}")

    def close_window(self):
        """Closes the desktop application cleanly."""
        if self.window:
            try:
                self.orchestrator.stop()
                self.window.destroy()
            except Exception as e:
                logger.warning(f"Window close error: {e}")

    # -------------------------------------------------------------
    # Conversational Commands
    # -------------------------------------------------------------
    def send_prompt(self, prompt: str) -> dict[str, Any]:
        """Receives prompt text from HUD and executes turn in background."""
        cleaned = prompt.strip()
        if not cleaned:
            return {"status": "empty"}

        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.orchestrator.process_text_turn(cleaned),
                self.loop
            )
            return {"status": "ok", "prompt": cleaned}
        return {"status": "loop_inactive"}

    def toggle_voice_mode(self) -> dict[str, Any]:
        """Toggles continuous background listening mode."""
        if self.is_voice_active:
            self.is_voice_active = False
            self.orchestrator.stop()
            logger.info("Voice mode disabled via HUD.")
            return {"status": "stopped", "active": False}
        else:
            self.is_voice_active = True
            if self.loop and self.loop.is_running():
                self.voice_task = asyncio.run_coroutine_threadsafe(
                    self.orchestrator.start_voice_loop(),
                    self.loop
                )
            logger.info("Voice mode enabled via HUD.")
            return {"status": "started", "active": True}

    def barge_in(self) -> dict[str, Any]:
        """Instant speech barge-in interruption (<10ms)."""
        player.interrupt()
        logger.info("Barge-in triggered via HUD.")
        return {"status": "interrupted"}

    # -------------------------------------------------------------
    # Quick Trigger Actions
    # -------------------------------------------------------------
    def execute_quick_action(self, action_id: str) -> dict[str, Any]:
        """Handles HUD quick action chips."""
        logger.info(f"Quick action triggered: {action_id}")

        if action_id == "diagnostics":
            return self.send_prompt("Check system diagnostics and give me a quick status report.")

        elif action_id == "volume_50":
            res = set_system_volume(50)
            return {"status": "ok", "message": res}

        elif action_id == "screenshot":
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.orchestrator.process_text_turn("Look at my screen and describe what you see."),
                    self.loop
                )
                return {"status": "ok", "message": "Analyzing screen..."}

        elif action_id == "mute_mic":
            self.is_mic_muted = not self.is_mic_muted
            if self.is_mic_muted:
                self.orchestrator.audio_stream.stop()
                msg = "Microphone muted."
            else:
                self.orchestrator.audio_stream.start()
                msg = "Microphone unmuted."
            return {"status": "ok", "muted": self.is_mic_muted, "message": msg}

        elif action_id == "purge_cache":
            res = purge_system_cache()
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.orchestrator.process_text_turn(f"Report: {res}"),
                    self.loop
                )
            return {"status": "ok", "message": res}

        return {"status": "unknown_action"}

    # -------------------------------------------------------------
    # System Telemetry & Audio Devices
    # -------------------------------------------------------------
    def get_telemetry(self) -> dict[str, Any]:
        """Gathers real-time hardware telemetry."""
        try:
            overall_cpu = psutil.cpu_percent(interval=None)
            per_core = psutil.cpu_percent(percpu=True)
            # Pad or truncate to 12 cores for visualizer
            if len(per_core) < 12:
                per_core = per_core + [per_core[-1]] * (12 - len(per_core))
            else:
                per_core = per_core[:12]

            mem = psutil.virtual_memory()
            ram_used_gb = round(mem.used / (1024 ** 3), 1)
            ram_total_gb = round(mem.total / (1024 ** 3), 1)
            ram_pct = mem.percent

            # Disk C:
            try:
                disk = psutil.disk_usage("C:\\")
                disk_free_gb = round(disk.free / (1024 ** 3), 1)
                disk_total_gb = round(disk.total / (1024 ** 3), 1)
                disk_pct = disk.percent
            except Exception:
                disk_free_gb, disk_total_gb, disk_pct = 20.0, 512.0, 75.0

            # Battery
            battery = psutil.sensors_battery()
            battery_pct = battery.percent if battery else 100
            battery_ac = battery.power_plugged if battery else True

            # Uptime
            uptime_hours = round((time.time() - psutil.boot_time()) / 3600, 1)

            # Audio level
            audio_level = getattr(self.orchestrator.audio_stream, "latest_level", 0)

            return {
                "cpu_pct": overall_cpu,
                "cores": per_core,
                "ram_pct": ram_pct,
                "ram_used_gb": ram_used_gb,
                "ram_total_gb": ram_total_gb,
                "disk_free_gb": disk_free_gb,
                "disk_total_gb": disk_total_gb,
                "disk_pct": disk_pct,
                "battery_pct": battery_pct,
                "battery_ac": battery_ac,
                "uptime_hours": uptime_hours,
                "audio_level": audio_level
            }
        except Exception as e:
            logger.error(f"Error gathering telemetry: {e}")
            return {"cpu_pct": 25.0, "cores": [25] * 12, "ram_pct": 50.0, "audio_level": 0}

    def get_initial_data(self) -> dict[str, Any]:
        """Provides initial configuration, audio devices, and telemetry to front-end."""
        devices = AudioInputStream.list_audio_devices()
        input_devs = [d for d in devices if d["max_inputs"] > 0]
        output_devs = [d for d in devices if d["max_outputs"] > 0]

        return {
            "settings": {
                "assistant_name": settings.ASSISTANT_NAME,
                "llm_provider": settings.DEFAULT_LLM_PROVIDER,
                "llm_model": settings.DEFAULT_LLM_MODEL,
                "gemini_model": settings.DEFAULT_GEMINI_MODEL,
                "tts_provider": settings.TTS_PROVIDER,
                "groq_key_set": bool(settings.GROQ_API_KEY),
                "gemini_key_set": bool(settings.GEMINI_API_KEY),
                "elevenlabs_key_set": bool(settings.ELEVENLABS_API_KEY),
                "cloned_voice_id": settings.ELEVENLABS_VOICE_ID or "v_personal_mk7",
            },
            "audio_devices": {
                "inputs": input_devs,
                "outputs": output_devs
            },
            "telemetry": self.get_telemetry()
        }

    # -------------------------------------------------------------
    # Voice Studio & Cloning
    # -------------------------------------------------------------
    def browse_voice_file(self) -> dict[str, Any]:
        """Opens native Windows file picker to select an audio sample for voice cloning."""
        selected_file = None

        def _open_dialog():
            nonlocal selected_file
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                selected_file = filedialog.askopenfilename(
                    title="Select Voice Sample for J.A.R.V.I.S. Cloning",
                    filetypes=[
                        ("Audio Files", "*.wav;*.mp3;*.m4a;*.flac;*.ogg"),
                        ("WAV Audio", "*.wav"),
                        ("MP3 Audio", "*.mp3"),
                        ("All Files", "*.*")
                    ]
                )
                root.destroy()
            except Exception as e:
                logger.warning(f"File picker warning: {e}")

        # Run in separate thread to prevent blocking WebView
        thread = threading.Thread(target=_open_dialog)
        thread.start()
        thread.join(timeout=30)

        if selected_file and os.path.exists(selected_file):
            size_mb = round(os.path.getsize(selected_file) / (1024 * 1024), 2)
            return {
                "status": "selected",
                "file_path": selected_file,
                "file_name": os.path.basename(selected_file),
                "size_mb": size_mb
            }
        return {"status": "cancelled"}

    def clone_voice(self, file_path: str, voice_name: str = "Personal Voice") -> dict[str, Any]:
        """Clones voice using ElevenLabs or saves to local cloned asset directory."""
        if not file_path or not os.path.exists(file_path):
            return {"status": "error", "message": "Voice file path does not exist."}

        try:
            res = voice_cloner.clone_voice(sample_path=file_path, voice_name=voice_name)
            if res.get("status") == "success":
                # Update runtime TTS provider
                settings.TTS_PROVIDER = "elevenlabs"
                settings.ELEVENLABS_VOICE_ID = res.get("voice_id", "")
                self.orchestrator.tts = voice_cloner.get_cloned_tts()
                return {"status": "success", "voice_id": res.get("voice_id"), "message": res.get("message")}
            else:
                return {"status": "error", "message": res.get("message", "Cloning failed.")}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # -------------------------------------------------------------
    # Configuration Management
    # -------------------------------------------------------------
    def save_settings(self, cfg: dict[str, Any]) -> dict[str, Any]:
        """Saves configuration changes to .env and updates active runtime."""
        try:
            env_path = BASE_DIR / ".env"
            env_vars: dict[str, str] = {}
            if env_path.exists():
                with open(env_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            env_vars[k.strip()] = v.strip().strip('"').strip("'")

            # Update from received cfg
            if "groq_key" in cfg and cfg["groq_key"]:
                env_vars["GROQ_API_KEY"] = cfg["groq_key"]
                settings.GROQ_API_KEY = cfg["groq_key"]

            if "gemini_key" in cfg and cfg["gemini_key"]:
                env_vars["GEMINI_API_KEY"] = cfg["gemini_key"]
                settings.GEMINI_API_KEY = cfg["gemini_key"]

            if "llm_provider" in cfg and cfg["llm_provider"]:
                env_vars["DEFAULT_LLM_PROVIDER"] = cfg["llm_provider"]
                settings.DEFAULT_LLM_PROVIDER = cfg["llm_provider"]

            if "tts_provider" in cfg and cfg["tts_provider"]:
                env_vars["TTS_PROVIDER"] = cfg["tts_provider"]
                settings.TTS_PROVIDER = cfg["tts_provider"]

            # Write updated .env
            with open(env_path, "w", encoding="utf-8") as f:
                for k, v in env_vars.items():
                    f.write(f'{k}="{v}"\n')

            # Re-initialize clients in orchestrator
            self.orchestrator.llm._init_client()
            from voice.tts import get_tts_engine
            self.orchestrator.tts = get_tts_engine()

            logger.info("Settings successfully applied to runtime.")
            return {"status": "success", "message": "Configuration saved and applied."}
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return {"status": "error", "message": str(e)}
