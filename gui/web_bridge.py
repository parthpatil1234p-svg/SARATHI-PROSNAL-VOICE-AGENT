"""Python <-> JavaScript bridge for S.A.R.A.T.H.I. Mark VII Tactical HUD."""

import asyncio
import logging
import os
import threading
import time
from typing import Any

import psutil

from config.settings import BASE_DIR, EXE_DIR, settings
from core.orchestrator import AssistantOrchestrator
from tools.os_tools import mute_system, set_system_volume
from tools.system_tools import get_system_diagnostics, purge_system_cache
from tools.vision_tools import analyze_screen
from voice.audio_stream import AudioInputStream
from voice.player import player
from voice.tts.voice_cloner import voice_cloner

logger = logging.getLogger("SARATHI.WebBridge")


class SarathiWebBridge:
    """
    Exposes Python backend methods to the JavaScript front-end via pywebview.
    Methods are callable from JS as `window.pywebview.api.<method_name>(...)`.
    """

    def __init__(self, orchestrator: AssistantOrchestrator, window=None):
        self._orchestrator = orchestrator
        self._window = window
        self._loop: asyncio.AbstractEventLoop | None = None
        self._voice_task: asyncio.Task | None = None
        self._is_voice_active = False
        self._is_mic_muted = False
        self._action_in_progress = False
        self._is_quitting = False

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Sets the active asyncio event loop."""
        self._loop = loop

    def set_window(self, window):
        """Sets the pywebview window instance."""
        self._window = window

    def get_conversation_history(self) -> list[dict[str, Any]]:
        """Returns chronological conversation history from persistent SQLite memory."""
        try:
            from core.persistent_memory import memory_db
            return memory_db.get_recent_history(limit=50)
        except Exception as e:
            logger.debug(f"Fallback to memory buffer history: {e}")
            res: list[dict[str, Any]] = []
            if hasattr(self._orchestrator, "memory") and self._orchestrator.memory:
                for m in self._orchestrator.memory.get_messages():
                    role = m.get("role", "")
                    if role != "system":
                        res.append({
                            "role": role,
                            "content": m.get("content", ""),
                            "time": time.strftime("%H:%M:%S")
                        })
            return res

    # -------------------------------------------------------------
    # Window Controls (Minimize, Maximize, Hide to Background, Power Off)
    # -------------------------------------------------------------
    def minimize_window(self):
        """Minimizes the native application window."""
        if self._window:
            try:
                self._window.minimize()
            except Exception as e:
                logger.warning(f"Window minimize error: {e}")

    def hide_to_background(self):
        """Hides the HUD window to run silently in the background while keeping voice listener active."""
        if self._window:
            try:
                self._window.hide()
                logger.info("SARATHI HUD hidden to background. Listening for 'Hey Sarathi'.")
            except Exception as e:
                logger.warning(f"Window hide error: {e}")

    def maximize_window(self):
        """Toggles maximize/restore state."""
        if self._window:
            try:
                if getattr(self, "_is_maximized", False):
                    self._window.restore()
                    self._is_maximized = False
                else:
                    self._window.maximize()
                    self._is_maximized = True
            except Exception as e:
                logger.warning(f"Window maximize/restore error: {e}")

    def close_window(self):
        """Closes the HUD window cleanly."""
        self.power_off()

    def power_off(self):
        """Fully terminates the application and background listener."""
        self._is_quitting = True
        logger.info("Powering down SARATHI completely.")
        if self._window:
            try:
                self._orchestrator.stop()
                self._window.destroy()
            except Exception as e:
                logger.warning(f"Window destroy error: {e}")
        import os
        os._exit(0)

    # -------------------------------------------------------------
    # Conversational Commands
    # -------------------------------------------------------------
    def send_prompt(self, prompt: str) -> dict[str, Any]:
        """Receives prompt text from HUD and executes turn in background."""
        cleaned = prompt.strip()
        if not cleaned:
            return {"status": "empty"}

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._orchestrator.process_text_turn(cleaned),
                self._loop
            )
            return {"status": "ok", "prompt": cleaned}
        return {"status": "loop_inactive"}

    def toggle_voice_mode(self) -> dict[str, Any]:
        """Toggles continuous background listening mode."""
        if self._is_voice_active:
            self._is_voice_active = False
            self._orchestrator.stop()
            logger.info("Voice mode disabled via HUD.")
            return {"status": "stopped", "active": False}
        else:
            self._is_voice_active = True
            if self._loop and self._loop.is_running():
                self._voice_task = asyncio.run_coroutine_threadsafe(
                    self._orchestrator.start_voice_loop(),
                    self._loop
                )
            logger.info("Voice mode enabled via HUD.")
            return {"status": "started", "active": True}

    def barge_in(self) -> dict[str, Any]:
        """Instant speech barge-in interruption (<10ms)."""
        player.interrupt()
        if self._loop and self._loop.is_running():
            from core.state_machine import AssistantState

            async def _barge_coro():
                self._orchestrator.state_machine.transition_to(AssistantState.INTERRUPTED)
                await event_bus.publish("barge_in", {})
                await asyncio.sleep(0.1)
                self._orchestrator.vad.reset()
                self._orchestrator.idle_vad.reset()
                self._orchestrator.active_conversation_timeout = time.time() + 10.0
                self._orchestrator.state_machine.transition_to(AssistantState.LISTENING)

            asyncio.run_coroutine_threadsafe(_barge_coro(), self._loop)
        logger.info("Barge-in triggered via HUD.")
        return {"status": "interrupted"}

    def trigger_wake(self) -> dict[str, Any]:
        """Manually forces wake detection as if user clicked push-to-talk mic."""
        if self._loop and self._loop.is_running():
            from core.state_machine import AssistantState

            async def _wake_coro():
                self._orchestrator.active_conversation_timeout = time.time() + 15.0
                self._orchestrator.state_machine.transition_to(AssistantState.WAKE_DETECTED)
                await self._orchestrator._play_wake_chime()
                # Ensure microphone buffer is drained so wake cue is not recorded as speech
                await asyncio.sleep(0.3)
                while not self._orchestrator.audio_stream.audio_queue.empty():
                    try:
                        self._orchestrator.audio_stream.audio_queue.get_nowait()
                    except Exception:
                        break
                self._orchestrator.vad.reset()
                self._orchestrator.state_machine.transition_to(AssistantState.LISTENING)

            asyncio.run_coroutine_threadsafe(_wake_coro(), self._loop)
            logger.info("Manual wake pulse triggered via HUD mic.")
            return {"status": "listening"}
        return {"status": "error"}

    # -------------------------------------------------------------
    # Quick Trigger Actions
    # -------------------------------------------------------------
    def execute_quick_action(self, action_id: str) -> dict[str, Any]:
        """Handles HUD quick action chips with instant local execution and direct voice feedback."""
        logger.info(f"Quick action triggered: {action_id}")

        if self._action_in_progress and action_id != "mute_mic":
            logger.warning(f"Action {action_id} ignored - another action is in progress.")
            return {"status": "busy", "message": "SARATHI is processing previous action."}

        if action_id == "mute_mic":
            self._is_mic_muted = not self._is_mic_muted
            if self._is_mic_muted:
                self._orchestrator.audio_stream.stop()
                msg = "Microphone muted."
            else:
                self._orchestrator.audio_stream.start()
                msg = "Microphone unmuted."
            return {"status": "ok", "muted": self._is_mic_muted, "message": msg}

        if not self._loop or not self._loop.is_running():
            # Fallback for headless testing when no async loop is active
            if action_id == "volume_50":
                res = set_system_volume(50)
                return {"status": "ok", "message": res}
            elif action_id == "purge_cache":
                res = purge_system_cache()
                return {"status": "ok", "message": res}
            elif action_id == "diagnostics":
                diag = get_system_diagnostics()
                return {"status": "ok", "diagnostics": diag}
            return {"status": "ok"}

        self._action_in_progress = True

        async def _run_action():
            try:
                if action_id == "diagnostics":
                    diag = get_system_diagnostics()
                    spoken = (
                        f"Diagnostics nominal, sir. CPU utilization is at {diag['cpu_usage_percent']}, "
                        f"and memory is at {diag['ram_usage']}."
                    )
                    await self._orchestrator.speak_direct(
                        text=spoken,
                        tool_name="get_system_diagnostics",
                        tool_result=diag
                    )

                elif action_id == "volume_50":
                    res = set_system_volume(50)
                    spoken = "Master audio output adjusted to fifty percent, sir."
                    await self._orchestrator.speak_direct(
                        text=spoken,
                        tool_name="set_system_volume",
                        tool_result=res
                    )

                elif action_id == "purge_cache":
                    res = purge_system_cache()
                    spoken = f"System cache purged successfully, sir. {res}"
                    await self._orchestrator.speak_direct(
                        text=spoken,
                        tool_name="purge_system_cache",
                        tool_result=res
                    )

                elif action_id == "screenshot":
                    res = await analyze_screen(prompt="Analyze the current display and provide an executive summary.")
                    await self._orchestrator.speak_direct(
                        text=res,
                        tool_name="analyze_screen",
                        tool_result="Visual scan completed."
                    )
            except Exception as e:
                logger.error(f"Error executing quick action {action_id}: {e}")
            finally:
                self._action_in_progress = False

        asyncio.run_coroutine_threadsafe(_run_action(), self._loop)
        return {"status": "ok", "action": action_id}

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
            audio_level = getattr(self._orchestrator.audio_stream, "latest_level", 0)

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
                "groq_api_key": settings.GROQ_API_KEY or "",
                "gemini_api_key": settings.GEMINI_API_KEY or "",
                "elevenlabs_api_key": settings.ELEVENLABS_API_KEY or "",
                "cloned_voice_id": settings.ELEVENLABS_VOICE_ID or "",
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
                self._orchestrator.tts = voice_cloner.get_cloned_tts()
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
            env_vars: dict[str, str] = {}

            # Read existing values from available .env sources to preserve unedited keys
            source_candidates = [
                EXE_DIR / ".env",
                BASE_DIR / ".env",
                BASE_DIR / ".env.example",
            ]
            for candidate in source_candidates:
                if candidate.exists():
                    try:
                        with open(candidate, encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith("#") and "=" in line:
                                    k, v = line.split("=", 1)
                                    k_clean = k.strip()
                                    if k_clean not in env_vars:
                                        env_vars[k_clean] = v.strip().strip('"').strip("'")
                    except Exception as read_err:
                        logger.warning(f"Failed reading .env from {candidate}: {read_err}")

            # Update from received cfg
            if "groq_key" in cfg:
                key_val = (cfg["groq_key"] or "").strip()
                env_vars["GROQ_API_KEY"] = key_val
                settings.GROQ_API_KEY = key_val

            if "gemini_key" in cfg:
                key_val = (cfg["gemini_key"] or "").strip()
                env_vars["GEMINI_API_KEY"] = key_val
                settings.GEMINI_API_KEY = key_val

            if "llm_provider" in cfg and cfg["llm_provider"]:
                provider_val = cfg["llm_provider"].strip().lower()
                env_vars["DEFAULT_LLM_PROVIDER"] = provider_val
                settings.DEFAULT_LLM_PROVIDER = provider_val

            if "tts_provider" in cfg and cfg["tts_provider"]:
                tts_val = cfg["tts_provider"].strip().lower()
                env_vars["TTS_PROVIDER"] = tts_val
                settings.TTS_PROVIDER = tts_val

            if "elevenlabs_key" in cfg:
                key_val = (cfg["elevenlabs_key"] or "").strip()
                env_vars["ELEVENLABS_API_KEY"] = key_val
                settings.ELEVENLABS_API_KEY = key_val

            if "elevenlabs_voice_id" in cfg and cfg["elevenlabs_voice_id"]:
                voice_id_val = cfg["elevenlabs_voice_id"].strip()
                env_vars["ELEVENLABS_VOICE_ID"] = voice_id_val
                settings.ELEVENLABS_VOICE_ID = voice_id_val

            # Target paths to save: always save to EXE_DIR (next to Sarathi.exe or project)
            # and also to BASE_DIR if different
            target_paths = {EXE_DIR / ".env"}
            import sys
            if not getattr(sys, "frozen", False):
                target_paths.add(BASE_DIR / ".env")

            for target in target_paths:
                try:
                    with open(target, "w", encoding="utf-8") as f:
                        for k, v in env_vars.items():
                            f.write(f'{k}="{v}"\n')
                    logger.info(f"Persisted updated .env to {target}")
                except Exception as write_err:
                    logger.warning(f"Failed writing .env to {target}: {write_err}")

            # Also maintain mirror .env.example with dummy values if BASE_DIR/.env.example exists
            try:
                example_path = BASE_DIR / ".env.example"
                if example_path.exists():
                    example_vars: dict[str, str] = {}
                    with open(example_path, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                example_vars[k.strip()] = v.strip().strip('"').strip("'")
                    for k in env_vars:
                        if k not in example_vars:
                            example_vars[k] = "your-value-here"
                    with open(example_path, "w", encoding="utf-8") as f:
                        for k, v in example_vars.items():
                            f.write(f'{k}="{v}"\n')
            except Exception as ex_err:
                logger.debug(f"Non-critical .env.example sync error: {ex_err}")

            # Reset HTTP connection pools so new credentials take effect immediately
            from core.http_client import reset_shared_clients
            reset_shared_clients()

            # Re-initialize clients in orchestrator
            if hasattr(self._orchestrator, "llm") and self._orchestrator.llm:
                self._orchestrator.llm._init_client()

            if hasattr(self._orchestrator, "stt") and hasattr(self._orchestrator.stt, "_init_groq_client"):
                self._orchestrator.stt._init_groq_client()

            from voice.tts import get_tts_engine
            self._orchestrator.tts = get_tts_engine()

            logger.info("Settings and API keys successfully saved and applied to runtime.")
            return {"status": "success", "message": "Configuration saved and applied."}
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return {"status": "error", "message": str(e)}


# Backward compatibility alias
JarvisWebBridge = SarathiWebBridge
