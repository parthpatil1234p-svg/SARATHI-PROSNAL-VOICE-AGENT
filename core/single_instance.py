"""Single Instance Controller for S.A.R.A.T.H.I.

Ensures that only ONE instance of SARATHI runs at any given time.
If a second instance is launched (e.g. user clicks shortcut while background instance is running),
the second instance signals the active instance to restore and focus the dashboard, then exits immediately.
"""

import logging
import socket
import sys
import threading
from typing import Callable

logger = logging.getLogger("SARATHI.SingleInstance")

SINGLE_INSTANCE_PORT = 49152
SINGLE_INSTANCE_HOST = "127.0.0.1"


class SingleInstanceLock:
    """Manages single-process mutual exclusion via loopback IPC."""

    def __init__(self, port: int = SINGLE_INSTANCE_PORT, host: str = SINGLE_INSTANCE_HOST):
        self.port = port
        self.host = host
        self.server_sock: socket.socket | None = None
        self.is_master = False
        self._listener_thread: threading.Thread | None = None
        self._on_restore_callback: Callable[[], None] | None = None

    def try_acquire(self) -> bool:
        """
        Attempts to acquire the single-instance lock.
        Returns True if this is the primary instance.
        Returns False if another instance is already running (after signaling it to restore).
        """
        # Test if another instance is listening
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(1.0)
        try:
            test_sock.connect((self.host, self.port))
            # Another instance exists! Send signal to bring its dashboard to front
            try:
                test_sock.sendall(b"RESTORE_DASHBOARD\n")
                test_sock.recv(1024)
            except Exception:
                pass
            test_sock.close()
            logger.info("Another SARATHI instance is already running. Signaled existing dashboard to focus.")
            return False
        except (ConnectionRefusedError, socket.timeout, OSError):
            # Port is free; we are the primary instance
            test_sock.close()

        # Bind the master server socket
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind((self.host, self.port))
            self.server_sock.listen(5)
            self.is_master = True
            logger.info(f"Single instance lock acquired on {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.warning(f"Could not bind single instance port: {e}")
            return True  # Fallback to allow launch if port binding fails

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
                                logger.error(f"Error invoking restore callback: cb_err")
                    conn.sendall(b"OK\n")
                    conn.close()
                except Exception:
                    break

        self._listener_thread = threading.Thread(target=_listen_loop, daemon=True)
        self._listener_thread.start()

    def release(self):
        """Closes the server socket."""
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None
