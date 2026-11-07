"""S.A.R.A.T.H.I. GUI package."""

from gui.app import JarvisDesktopApp, run_gui
from gui.hud import JarvisHUDApp, SarathiHUDApp, run_tactical_hud
from gui.web_bridge import JarvisWebBridge, SarathiWebBridge

SarathiDesktopApp = JarvisDesktopApp

__all__ = [
    "SarathiHUDApp",
    "JarvisHUDApp",
    "SarathiDesktopApp",
    "JarvisDesktopApp",
    "SarathiWebBridge",
    "JarvisWebBridge",
    "run_tactical_hud",
    "run_gui",
]
