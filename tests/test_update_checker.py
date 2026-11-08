"""Tests for Desktop Update Checker."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.update_checker import DesktopUpdateChecker


@pytest.fixture
def checker():
    c = DesktopUpdateChecker()
    c.current_sha = "1111111"
    return c


@pytest.mark.asyncio
async def test_update_checker_detects_new_commit(checker: DesktopUpdateChecker):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sha": "2222222abcdef",
            "commit": {
                "message": "feat: amazing new voice feature",
                "author": {"date": "2026-11-08T19:00:00Z"},
            },
        }
        mock_get.return_value = mock_resp

        result = await checker.check_for_updates()
        assert result is not None
        assert result["has_update"] is True
        assert result["latest_sha"] == "2222222"
        assert result["commit_message"] == "feat: amazing new voice feature"


@pytest.mark.asyncio
async def test_update_checker_up_to_date(checker: DesktopUpdateChecker):
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sha": "1111111abcdef",
            "commit": {"message": "old commit"},
        }
        mock_get.return_value = mock_resp

        result = await checker.check_for_updates()
        assert result is not None
        assert result["has_update"] is False
