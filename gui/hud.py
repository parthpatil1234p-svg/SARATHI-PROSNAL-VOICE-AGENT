"""S.A.R.A.T.H.I. Mark VII Tactical Desktop HUD - WebView2 / PyWebView Launcher."""

import asyncio
import json
import logging
import sys
import threading
import time
from pathlib import Path

import webview

from config.settings import BASE_DIR, settings
from core.event_bus import event_bus
from core.orchestrator import AssistantOrchestrator
from gui.web_bridge import SarathiWebBridge

logger = logging.getLogger("SARATHI.HUD")


def bring_sarathi_window_to_front(window_title_keyword: str = "SARATHI"):
    """
    Guarantees bringing the native window to the foreground on Windows 10/11,
    bypassing OS ForegroundLockTimeout restrictions so the full tactical HUD dashboard
    pops to the front when 'Hey Sarathi' wake word is detected.
    """
    if sys.platform != "win32":
        return

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        SW_RESTORE = 9
        SW_SHOW = 5
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_SHOWWINDOW = 0x0040
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2

        hwnds = []

        def enum_windows_callback(hwnd, extra):
            if user32.IsWindow(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    if window_title_keyword.upper() in title.upper():
                        hwnds.append(hwnd)
            return True

        cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(cb_type(enum_windows_callback), 0)

        for hwnd in hwnds:
            # 1. Unminimize if minimized to taskbar
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            else:
                user32.ShowWindow(hwnd, SW_SHOW)

            # 2. Attach thread input to bypass OS foreground lock
            fg_hwnd = user32.GetForegroundWindow()
            fg_thread_id = user32.GetWindowThreadProcessId(fg_hwnd, None)
            curr_thread_id = kernel32.GetCurrentThreadId()

            if fg_thread_id != curr_thread_id and fg_thread_id != 0:
                user32.AttachThreadInput(curr_thread_id, fg_thread_id, True)
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
                user32.AttachThreadInput(curr_thread_id, fg_thread_id, False)
            else:
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)

            # 3. Momentarily set TOPMOST then NOTOPMOST to force window over full-screen apps
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

            # 4. Virtual ALT key tap to force Windows to accept new foreground window
            user32.keybd_event(0x12, 0, 0, 0)
            user32.keybd_event(0x12, 0, 2, 0)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)

    except Exception as e:
        logger.debug(f"Win32 bring to front error: {e}")


def get_sarathi_hwnd(window=None) -> int | None:
    """Finds the native OS HWND for the Sarathi window with 100% precision."""
    if sys.platform != "win32":
        return None
    if window and hasattr(window, "native") and window.native:
        try:
            return window.native.Handle.ToInt32()
        except Exception:
            pass
    import os, ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    pid = os.getpid()
    matched = []

    def enum_cb(h, _):
        if user32.IsWindow(h):
            p = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value == pid:
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(h, cls_buf, 256)
                cls_name = cls_buf.value
                if "WindowsForms" in cls_name:
                    matched.append(h)
        return True

    cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(cb_type(enum_cb), 0)
    return matched[0] if matched else None


# Backward-compatible alias
find_sarathi_hwnd = get_sarathi_hwnd


def apply_window_transparency(window=None, is_transparent: bool = True):
    """
    Applies true WinForms TransparencyKey + DWM desktop composition.
    Guarantees 100% circular floating orb with ZERO square bounding box and ZERO dark corners.
    """
    if sys.platform != "win32":
        return
    if not window or not hasattr(window, "native") or not window.native:
        return
    try:
        import clr
        clr.AddReference('System.Windows.Forms')
        clr.AddReference('System.Drawing')
        from System.Drawing import Color
        from System import Action
        import ctypes

        form = window.native
        hwnd = form.Handle.ToInt32()

        # DWM glass frame extension for hardware desktop composition
        try:
            dwmapi = ctypes.windll.dwmapi
            class MARGINS(ctypes.Structure):
                _fields_ = [
                    ("cxLeftWidth", ctypes.c_int),
                    ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int),
                    ("cyBottomHeight", ctypes.c_int),
                ]
            margins = MARGINS(-1, -1, -1, -1) if is_transparent else MARGINS(0, 0, 0, 0)
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception as dwm_err:
            logger.debug(f"DWM glass frame notice: {dwm_err}")

        def _update_form():
            if is_transparent:
                key = Color.FromArgb(1, 1, 1)
                form.BackColor = key
                form.AllowTransparency = True
                form.TransparencyKey = key
            else:
                form.TransparencyKey = Color.Empty
                form.BackColor = Color.FromArgb(10, 14, 20)

        form.Invoke(Action(_update_form))
        logger.info(f"Applied WinForms window transparency (is_transparent={is_transparent}) on HWND {hwnd}")
    except Exception as e:
        logger.warning(f"Error applying window transparency: {e}")


def set_circular_window_region(is_circular: bool, width: int = 220, height: int = 220, window=None):
    """
    Physically shapes the Windows OS window into a pure circle with ZERO square bounding box or dark corners.
    Applies CreateEllipticRgn to the top-level Form HWND and all child HWNDs.
    When is_circular is False, restores full rectangular region for the cockpit dashboard.
    """
    if sys.platform != "win32":
        return
    hwnd = get_sarathi_hwnd(window)
    if not hwnd:
        return
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    try:
        children = []
        def child_cb(ch, _):
            children.append(ch)
            return True
        cb_child = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(child_cb)
        user32.EnumChildWindows(hwnd, cb_child, 0)
        all_hwnds = [hwnd] + children

        if is_circular:
            # Force exact physical client dimensions
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            user32.SetWindowPos(hwnd, 0, 0, 0, width, height, SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED)

            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w <= 0 or h <= 0:
                w, h = width, height

            for h_w in all_hwnds:
                try:
                    hrgn = gdi32.CreateEllipticRgn(0, 0, w, h)
                    user32.SetWindowRgn(h_w, hrgn, True)
                except Exception:
                    pass
            logger.info(f"Set circular OS window region ({w}x{h}) on HWND {hwnd} and {len(children)} surfaces")
        else:
            for h_w in all_hwnds:
                try:
                    user32.SetWindowRgn(h_w, 0, True)
                except Exception:
                    pass
            logger.info(f"Restored rectangular OS window region on HWND {hwnd} and {len(children)} surfaces")
    except Exception as e:
        logger.warning(f"Error setting window region: {e}")


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

    def _safe_eval_js(self, script: str):
        """Asynchronously executes JavaScript without ever blocking or deadlocking calling threads."""
        if not self.window or not self.is_running:
            return
        def _exec():
            try:
                self.window.evaluate_js(script)
            except Exception as e:
                logger.debug(f"Async evaluate_js error: {e}")
        threading.Thread(target=_exec, daemon=True).start()

    def _run_async_loop(self):
        """Runs the background asyncio event loop for orchestrator tasks."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.bridge.set_loop(self.loop)
        self.orchestrator.loop = self.loop

        # Wire event_bus to push live events to the WebView UI non-blockingly
        def on_event(event_name: str, payload):
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
                    self._safe_eval_js(js_code)
                except Exception as e:
                    logger.debug(f"Event dispatch error for {event_name}: {e}")

        event_bus.subscribe("state_changed", lambda s: on_event("state_changed", s))
        event_bus.subscribe("user_speech", lambda p: on_event("user_speech", p))
        event_bus.subscribe("assistant_speech", lambda p: on_event("assistant_speech", p))
        event_bus.subscribe("tool_executed", lambda p: on_event("tool_executed", p))
        event_bus.subscribe("barge_in", lambda p: on_event("barge_in", p))

        def _handle_wake(payload):
            threading.Thread(target=self._on_wake_detected, daemon=True).start()
            on_event("wake_detected", payload)

        event_bus.subscribe("wake_detected", _handle_wake)
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
        """
        Restores and brings SARATHI to the foreground when 'Hey Sarathi' wake word is detected.
        Pops up the compact floating 3D tactical widget so it never disrupts the user's workflow,
        with an interactive button to expand into the full Mark VII Cockpit Dashboard.
        """
        if not self.is_running:
            return

        try:
            # 1. Pywebview native restore and show
            if self.window:
                try:
                    self.window.show()
                    self.window.restore()
                    if hasattr(self.window, "focus"):
                        self.window.focus()
                except Exception as pw_err:
                    logger.debug(f"Pywebview restore attempt: {pw_err}")

            # 2. Native Win32 foreground activation (unminimizes and pops to front of all apps)
            bring_sarathi_window_to_front("SARATHI")

            # 3. Present as compact floating 3D popup on wake detection
            if hasattr(self.bridge, "collapse_to_compact"):
                self.bridge.collapse_to_compact()

            # 4. Dispatch wake_detected to Web UI non-blockingly
            self._safe_eval_js(
                "if (window.onSarathiEvent) window.onSarathiEvent('wake_detected', {mode: 'compact'});"
            )

            logger.info("SARATHI compact floating 3D HUD restored to foreground on wake detection.")
        except Exception as e:
            logger.debug(f"Window restore error: {e}")

    def _on_window_closing(self):
        """
        Intercepts window close: hides to background resident mode instead of killing the process.
        Returns False so pywebview cancels window destruction, keeping SARATHI's background
        audio stream and wake word listener active 24/7.
        """
        if getattr(self, "_force_quit", False):
            self.is_running = False
            try:
                self.orchestrator.stop()
                logger.info("SARATHI HUD closed cleanly (force quit).")
            except Exception as e:
                logger.debug(f"Shutdown error on closing: {e}")
            return True

        logger.info("Window close intercepted: Hiding to background resident mode. Silently listening for 'Hey Sarathi'.")
        try:
            if self.window:
                self.window.hide()
        except Exception as e:
            logger.debug(f"Window hide error: {e}")
        return False

    def _telemetry_ticker(self):
        """Pushes system diagnostics and real-time audio levels to the HUD non-blockingly."""
        last_telemetry_time = 0.0

        while self.is_running:
            now = time.time()
            if self.window:
                try:
                    # 1. Audio Visualizer Level (~16Hz is smooth and does not congest WebView2 thread)
                    audio_level = getattr(self.orchestrator.audio_stream, "latest_level", 0)
                    if audio_level > 0:
                        js_audio = f"if (window.updateAudioLevel) window.updateAudioLevel({audio_level});"
                        self._safe_eval_js(js_audio)

                    # 2. System Hardware Telemetry (~1Hz)
                    if now - last_telemetry_time >= 1.0:
                        telem = self.bridge.get_telemetry()
                        telem_json = json.dumps(telem)
                        js_telem = f"if (window.updateTelemetry) window.updateTelemetry({telem_json});"
                        self._safe_eval_js(js_telem)
                        last_telemetry_time = now

                except Exception:
                    pass

            time.sleep(0.06)

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

        # Determine initial window dimensions:
        # Defaults to the sleek compact 3D circular voice orb (220x220)
        # positioned at bottom-right above taskbar so it never covers the user's workspace!
        sw, sh = self.bridge.get_screen_resolution()
        init_w, init_h = 220, 220
        init_x = max(10, sw - 260)
        init_y = max(10, sh - 320)

        # Configure pywebview settings: allow direct target drag, prevent button interception
        webview.settings['DRAG_REGION_DIRECT_TARGET_ONLY'] = True

        self.window = webview.create_window(
            title="SARATHI // Autonomous Desktop AI Assistant",
            url=str(html_path.resolve()),
            js_api=self.bridge,
            width=init_w,
            height=init_h,
            x=init_x,
            y=init_y,
            min_size=(180, 180),
            background_color="#0A0E14",
            frameless=True,
            easy_drag=False,
            transparent=True,
            on_top=True,
            minimized=start_in_background,
            hidden=False
        )

        def _apply_initial_shape():
            import time
            for _ in range(40):
                time.sleep(0.15)
                h = get_sarathi_hwnd(self.window)
                if h:
                    apply_window_transparency(self.window, is_transparent=True)
                    set_circular_window_region(True, init_w, init_h, window=self.window)
                    break

        threading.Thread(target=_apply_initial_shape, daemon=True).start()

        def _on_shown():
            apply_window_transparency(self.window, is_transparent=True)
            set_circular_window_region(True, init_w, init_h, window=self.window)

        self.window.events.shown += _on_shown

        self.bridge.set_window(self.window)
        if hasattr(self.bridge, "set_hud_app"):
            self.bridge.set_hud_app(self)
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
