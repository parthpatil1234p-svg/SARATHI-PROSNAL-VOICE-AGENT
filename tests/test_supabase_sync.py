"""Tests for Supabase Cloud Sync Engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from core.supabase_sync import SupabaseSyncEngine


@pytest.fixture
def mock_supabase():
    with patch("core.supabase_sync.settings") as mock_settings:
        mock_settings.SUPABASE_URL = "https://example.supabase.co"
        mock_settings.SUPABASE_KEY = "anon-key-123"
        mock_settings.SUPABASE_SERVICE_ROLE_KEY = "secret-key-456"
        mock_settings.ENABLE_SUPABASE_SYNC = True
        engine = SupabaseSyncEngine()
        yield engine


def test_supabase_headers(mock_supabase: SupabaseSyncEngine):
    assert mock_supabase.is_configured is True
    headers = mock_supabase._get_headers()
    assert headers["apikey"] == "secret-key-456"
    assert "Bearer secret-key-456" in headers["Authorization"]


@pytest.mark.asyncio
async def test_supabase_push_memory_turn(mock_supabase: SupabaseSyncEngine):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_post.return_value = mock_resp

        success = await mock_supabase.push_memory_turn("user", "Hello from test")
        assert success is True
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["json"]["role"] == "user"
        assert kwargs["json"]["content"] == "Hello from test"


@pytest.mark.asyncio
async def test_supabase_create_and_fetch_tasks(mock_supabase: SupabaseSyncEngine):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = [{"id": "task-uuid-1", "title": "Buy milk", "status": "pending"}]
        mock_post.return_value = mock_resp

        task = await mock_supabase.create_task("Buy milk", category="errand")
        assert task is not None
        assert task["id"] == "task-uuid-1"

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"id": "task-uuid-1", "title": "Buy milk"}]
        mock_get.return_value = mock_resp

        tasks = await mock_supabase.fetch_pending_tasks()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Buy milk"
