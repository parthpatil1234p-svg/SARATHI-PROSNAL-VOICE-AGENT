"""S.A.R.A.T.H.I. Mark VII Tactical Desktop HUD - WebView2 / PyWebView Launcher."""

import asyncio
import json
import logging
import threading
import time
from pathlib import Path

import webview

from config.settings import BASE_DIR, settings
from core.event_bus import event_bus
from core.orchestrator import AssistantOrchestrator
from gui.web_bridge import SarathiWebBridge

logger = logging.getLogger("SARATHI.HUD")


class SarathiHUDApp:
    """
    Main Desktop HUD Application runner.
    Hosts the Stitch-designed Mark VII Tactical Interface via Microsoft Edge WebView2,
    bridged seamlessly to the Python assistant orchestrator.
    """

    def __init__(self):
        self.orchestrator = AssistantOrchestrator()
        self.bridge = SarathiWebBridge(self.orchestrator)
        self.window = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.bg_thread: threading.Thread | None = None
        self.telemetry_thread: threading.Thread | None = None
        self.is_running = True

    def _run_async_loop(self):
        """Runs the background asyncio event loop for orchestrator tasks."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.bridge.set_loop(self.loop)
        self.orchestrator.loop = self.loop

        # Wire event_bus to push live events to the WebView UI
        async def on_event(event_name: str, payload):
            if self.window and self.is_running:
                try:
                    payload_raw_json = json.dumps(payload, default=str)
                    encoded_arg = json.dumps(payload_raw_json)
                    js_code = (
                        f"try {{ "
                        f"  var data = JSON.parse({encoded_arg}); "
                        f"  if (window.onSarathiEvent) window.onSarathiEvent('{event_name}', data); "
                        f"  else if (window.onJarvisEvent) window.onJarvisEvent('{event_name}', data); "
                        f"}} catch(e) {{ console.error('dispatch error for {event_name}:', e); }}"
                    )
                    self.window.evaluate_js(js_code)
                except Exception as e:
                    logger.debug(f"Event dispatch error for {event_name}: {e}")

        event_bus.subscribe("state_changed", lambda s: on_event("state_changed", s))
        event_bus.subscribe("user_speech", lambda p: on_event("user_speech", p))
        event_bus.subscribe("assistant_speech", lambda p: on_event("assistant_speech", p))
        event_bus.subscribe("tool_executed", lambda p: on_event("tool_executed", p))
        event_bus.subscribe("barge_in", lambda p: on_event("barge_in", p))
        event_bus.subscribe("wake_detected", lambda p: self._on_wake_detected())
        event_bus.subscribe("mic_mute_changed", lambda p: on_event("mic_mute_changed", p))
        event_bus.subscribe("system_update_available", lambda p: on_event("system_update_available", p))

        # Start continuous voice loop by default
        self.bridge._is_voice_active = True
        self.loop.create_task(self.orchestrator.start_voice_loop())

        # Start background GitHub auto-update checker
        try:
            from core.update_checker import desktop_update_checker
            desktop_update_checker.start_background_checker()
        except Exception as upd_err:
            logger.debug(f"Update checker start note: {upd_err}")

        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def _on_wake_detected(self):
        """Restores and shows the tactical HUD window if hidden when Sarathi wakes up."""
        if self.window and self.is_running:
            try:
                self.window.show()
                self.window.restore()
                logger.info("Tactical HUD window restored on wake detection.")
            except Exception as e:
                logger.debug(f"Window restore error: {e}")

    def _on_window_closing(self):
        """Handles clean application shutdown when the window close button is pressed."""
        self.is_running = False
        try:
            self.orchestrator.stop()
            logger.info("SARATHI HUD closed cleanly.")
        except Exception as e:
            logger.debug(f"Shutdown error on closing: {e}")
        return True

    def _telemetry_ticker(self):
        """Pushes system diagnostics and real-time audio levels to the HUD."""
        last_telemetry_time = 0.0

        while self.is_running:
            now = time.time()
            if self.window:
                try:
                    # 1. Audio Visualizer Level (~33Hz for silky-smooth HUD responsiveness)
                    audio_level = getattr(self.orchestrator.audio_stream, "latest_level", 0)
                    if audio_level > 0:
                        js_audio = f"if (window.updateAudioLevel) window.updateAudioLevel({audio_level});"
                        self.window.evaluate_js(js_audio)

                    # 2. System Hardware Telemetry (~1Hz)
                    if now - last_telemetry_time >= 1.0:
                        telem = self.bridge.get_telemetry()
                        telem_json = json.dumps(telem)
                        js_telem = f"if (window.updateTelemetry) window.updateTelemetry({telem_json});"
                        self.window.evaluate_js(js_telem)
                        last_telemetry_time = now

                except Exception:
                    pass

            time.sleep(0.03)

    def launch(self, start_in_background: bool = False, lock=None):
        """Launches the Mark VII Tactical HUD Window."""
        html_path = BASE_DIR / "gui" / "web" / "index.html"
        if not html_path.exists():
            raise FileNotFoundError(f"HUD HTML template not found at {html_path}")

        # Start background threads
        self.bg_thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self.bg_thread.start()

        self.telemetry_thread = threading.Thread(target=self._telemetry_ticker, daemon=True)
        self.telemetry_thread.start()

        # Listen for secondary instance restore signals if single-instance lock is active
        if lock and hasattr(lock, "start_listener"):
            lock.start_listener(on_restore_callback=lambda: self._on_wake_detected())

        # Create Native Windows 11 Desktop Window (1440x900 as per Mark VII specs)
        # In background mode, starts minimized to the taskbar so the application icon is always visible
        self.window = webview.create_window(
            title="SARATHI // Autonomous Desktop AI Assistant",
            url=str(html_path.resolve()),
            js_api=self.bridge,
            width=1440,
            height=900,
            min_size=(1024, 700),
            background_color="#0A0E14",
            frameless=False,
            easy_drag=True,
            minimized=start_in_background,
            hidden=False
        )
        self.bridge.set_window(self.window)
        self.window.events.closing += self._on_window_closing

        if start_in_background:
            logger.info("SARATHI started in background mode (minimized to taskbar). Silently listening for 'Hey Sarathi'.")

        # Starts the native WebView2 message loop on the main thread (blocking until closed)
        webview.start(debug=False)
        self.is_running = False
        self.orchestrator.stop()


# Backward compatibility alias
JarvisHUDApp = SarathiHUDApp


def run_tactical_hud(background: bool = False, lock=None):
    """Entry point to launch the tactical desktop HUD."""
    app = SarathiHUDApp()
    app.launch(start_in_background=background, lock=lock)


if __name__ == "__main__":
    run_tactical_hud()
