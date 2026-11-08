"""SARATHI Desktop Auto-Update Checker (GitHub Sync)."""

import asyncio
import logging
import subprocess
from typing import Any
import httpx

from config.settings import settings
from core.event_bus import event_bus

logger = logging.getLogger("SARATHI.UpdateChecker")

GITHUB_REPO = "parthpatil1234p-svg/SARATHI-PROSNAL-VOICE-AGENT"
GITHUB_COMMITS_API = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"


class DesktopUpdateChecker:
    """Checks GitHub for new commits/releases and notifies Tactical HUD."""

    def __init__(self):
        self.current_sha = self._get_local_commit_sha()
        self.latest_update_info: dict[str, Any] | None = None

    def _get_local_commit_sha(self) -> str:
        """Determines the current local commit SHA (7 chars)."""
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass
        return "e72d0aa"

    async def check_for_updates(self) -> dict[str, Any] | None:
        """Queries GitHub for new commits on main branch."""
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(
                    GITHUB_COMMITS_API,
                    headers={"User-Agent": "SARATHI-Desktop-Agent"},
                )
                if res.status_code == 200:
                    data = res.json()
                    full_sha = data.get("sha", "")
                    short_sha = full_sha[:7] if len(full_sha) >= 7 else full_sha
                    commit_info = data.get("commit", {})
                    message = commit_info.get("message", "").split("\n")[0]
                    date = commit_info.get("author", {}).get("date", "")

                    if short_sha and short_sha != self.current_sha:
                        self.latest_update_info = {
                            "has_update": True,
                            "current_sha": self.current_sha,
                            "latest_sha": short_sha,
                            "commit_message": message,
                            "date": date,
                            "repo_url": f"https://github.com/{GITHUB_REPO}",
                        }
                        logger.info(f"New update detected on GitHub: {short_sha} - '{message}'")
                        await event_bus.publish("system_update_available", self.latest_update_info)
                        return self.latest_update_info
                    else:
                        logger.debug("SARATHI Desktop is fully up to date.")
                        return {"has_update": False, "current_sha": self.current_sha}
        except Exception as e:
            logger.debug(f"Update check network note: {e}")
        return None

    def start_background_checker(self, interval_seconds: int = 1800):
        """Runs periodic update check in background task (default every 30 mins)."""
        async def _loop():
            # Initial check 5 seconds after startup
            await asyncio.sleep(5)
            while True:
                try:
                    await self.check_for_updates()
                except Exception as loop_err:
                    logger.debug(f"Update loop error: {loop_err}")
                await asyncio.sleep(interval_seconds)

        return asyncio.create_task(_loop())


desktop_update_checker = DesktopUpdateChecker()
