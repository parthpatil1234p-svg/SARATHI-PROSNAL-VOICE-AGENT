"""Single Instance Controller for S.A.R.A.T.H.I.

Ensures that strictly ONE instance of SARATHI runs at any given time.
If a second instance is launched (e.g. user double-clicks shortcut multiple times),
the secondary instance signals the active instance to restore and focus the UI, then exits immediately.
"""

import ctypes
import logging
import socket
import sys
import threading
from typing import Callable

logger = logging.getLogger("SARATHI.SingleInstance")

SINGLE_INSTANCE_PORT = 49152
SINGLE_INSTANCE_HOST = "127.0.0.1"
MUTEX_NAME = "Global\\SARATHI_Voice_Agent_Mutex_Parth"
ERROR_ALREADY_EXISTS = 183


class SingleInstanceLock:
    """Manages single-process mutual exclusion via Windows Kernel Mutex & loopback IPC."""

    def __init__(self, port: int = SINGLE_INSTANCE_PORT, host: str = SINGLE_INSTANCE_HOST):
        self.port = port
        self.host = host
        self.server_sock: socket.socket | None = None
        self.mutex_handle = None
        self.is_master = False
        self._listener_thread: threading.Thread | None = None
        self._on_restore_callback: Callable[[], None] | None = None

    def try_acquire(self) -> bool:
        """
        Attempts to acquire the single-instance lock.
        Uses native Windows kernel mutex for zero-latency (<1ms) race protection.
        Returns True if this is the primary instance.
        Returns False if another instance is already running (signals it to focus and exits).
        """
        is_windows = sys.platform == "win32"

        # 1. Native Windows Named Kernel Mutex (Instant atomicity across all threads/processes)
        if is_windows:
            try:
                kernel32 = ctypes.windll.kernel32
                # Use port-specific mutex name so unit tests on different ports don't collide
                mutex_name = f"{MUTEX_NAME}_{self.port}"
                self.mutex_handle = kernel32.CreateMutexW(None, False, mutex_name)
                last_error = kernel32.GetLastError()
                if last_error == ERROR_ALREADY_EXISTS:
                    logger.info("Another SARATHI instance holds the Windows kernel mutex. Signaling existing window...")
                    self._signal_existing_instance()
                    return False
            except Exception as e:
                logger.debug(f"Mutex creation note: {e}")

        # 2. Check if another instance's IPC socket is already listening
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(0.6)
        try:
            test_sock.connect((self.host, self.port))
            try:
                test_sock.sendall(b"RESTORE_DASHBOARD\n")
                test_sock.recv(512)
            except Exception:
                pass
            test_sock.close()
            logger.info("Signaled existing instance via IPC socket. Terminating secondary process.")
            if is_windows:
                self._focus_existing_window()
            return False
        except (ConnectionRefusedError, socket.timeout, OSError):
            test_sock.close()

        # 3. Bind the master server socket (EXCLUSIVE, prevents multiple binds)
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if is_windows and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                try:
                    self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                except Exception:
                    pass
            self.server_sock.bind((self.host, self.port))
            self.server_sock.listen(5)
            self.is_master = True
            logger.info(f"Single instance lock acquired on {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.warning(f"Could not bind single instance port: {e}")
            if self.mutex_handle and is_windows:
                self.is_master = True
                return True
            return False

    def _signal_existing_instance(self):
        """Attempts to signal the primary instance via socket and Win32 focus."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect((self.host, self.port))
            s.sendall(b"RESTORE_DASHBOARD\n")
            s.recv(512)
            s.close()
        except Exception:
            pass
        self._focus_existing_window()

    def _focus_existing_window(self):
        """Brings the existing SARATHI window to the foreground."""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "SARATHI // Autonomous Desktop AI Assistant")
            if not hwnd:
                hwnd = user32.FindWindowW(None, "SARATHI")
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def start_listener(self, on_restore_callback: Callable[[], None]):
        """Starts background thread to listen for restore signals from subsequent launches."""
        if not self.is_master or not self.server_sock:
            return

        self._on_restore_callback = on_restore_callback

        def _listen_loop():
            while self.server_sock:
                try:
                    conn, _ = self.server_sock.accept()
                    data = conn.recv(1024).strip()
                    if b"RESTORE_DASHBOARD" in data:
                        logger.info("Received RESTORE_DASHBOARD signal from secondary launcher.")
                        if self._on_restore_callback:
                            try:
                                self._on_restore_callback()
                            except Exception as cb_err:
                                logger.error(f"Error invoking restore callback: {cb_err}")
                    conn.sendall(b"OK\n")
                    conn.close()
                except Exception:
                    break

        self._listener_thread = threading.Thread(target=_listen_loop, daemon=True)
        self._listener_thread.start()

    def release(self):
        """Closes the server socket and releases Windows mutex handle."""
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None
        if self.mutex_handle and sys.platform == "win32":
            try:
                ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
            except Exception:
                pass
            self.mutex_handle = None
        self.is_master = False
