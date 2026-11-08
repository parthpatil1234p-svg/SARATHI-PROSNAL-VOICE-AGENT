"""Supabase Cloud Synchronization Engine for SARATHI (Desktop <-> Mobile)."""

import logging
from typing import Any
import httpx

from config.settings import settings

logger = logging.getLogger("SARATHI.SupabaseSync")


class SupabaseSyncEngine:
    """Lightweight, non-blocking Supabase REST API client for syncing tasks and memory."""

    def __init__(self):
        self.url = settings.SUPABASE_URL.strip().rstrip("/")
        # Prefer service role key for backend tasks if present, else fallback to anon key
        self.key = settings.SUPABASE_SERVICE_ROLE_KEY.strip() or settings.SUPABASE_KEY.strip()
        self.enabled = settings.ENABLE_SUPABASE_SYNC and bool(self.url and self.key)

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.key)

    def _get_headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def push_memory_turn(self, role: str, content: str) -> bool:
        """Uploads a conversation turn to Supabase memory_turns table."""
        if not self.is_configured:
            return False

        endpoint = f"{self.url}/rest/v1/memory_turns"
        payload = {"role": role, "content": content, "synced_desktop": True}
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(endpoint, json=payload, headers=self._get_headers())
                if res.status_code in (200, 201):
                    logger.debug(f"Synced turn to Supabase: role={role}")
                    return True
                logger.warning(f"Failed to push memory to Supabase: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            logger.warning(f"Supabase push_memory_turn network error: {e}")
        return False

    async def fetch_pending_tasks(self) -> list[dict[str, Any]]:
        """Retrieves active/pending tasks from Supabase."""
        if not self.is_configured:
            return []

        endpoint = f"{self.url}/rest/v1/tasks?status=eq.pending&order=created_at.desc"
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(endpoint, headers=self._get_headers())
                if res.status_code == 200:
                    return res.json()
                logger.warning(f"Failed to fetch tasks from Supabase: HTTP {res.status_code}")
        except Exception as e:
            logger.warning(f"Supabase fetch_pending_tasks network error: {e}")
        return []

    async def create_task(self, title: str, category: str = "general", due_at: str | None = None, device_origin: str = "desktop") -> dict[str, Any] | None:
        """Creates a new task in Supabase."""
        if not self.is_configured:
            return None

        endpoint = f"{self.url}/rest/v1/tasks"
        payload = {
            "title": title,
            "category": category,
            "status": "pending",
            "device_origin": device_origin,
        }
        if due_at:
            payload["due_at"] = due_at

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(endpoint, json=payload, headers=self._get_headers())
                if res.status_code in (200, 201):
                    data = res.json()
                    return data[0] if isinstance(data, list) and data else data
                logger.warning(f"Failed to create task in Supabase: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            logger.warning(f"Supabase create_task network error: {e}")
        return None

    async def complete_task(self, task_id: str) -> bool:
        """Marks a task as completed in Supabase."""
        if not self.is_configured:
            return False

        endpoint = f"{self.url}/rest/v1/tasks?id=eq.{task_id}"
        payload = {"status": "completed"}
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.patch(endpoint, json=payload, headers=self._get_headers())
                return res.status_code in (200, 204)
        except Exception as e:
            logger.warning(f"Supabase complete_task network error: {e}")
        return False


# Global singleton instance
supabase_sync = SupabaseSyncEngine()
