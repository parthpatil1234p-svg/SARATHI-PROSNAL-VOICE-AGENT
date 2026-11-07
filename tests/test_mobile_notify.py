from tools.mobile_notify import send_mobile_notification
from tools.registry import execute_tool, get_all_tool_schemas
import pytest

def test_send_mobile_notification():
    res = send_mobile_notification("Unit test alert from Sarathi", title="Test Alert", topic="sarathi_unit_test")
    assert res.get("status") == "success"
    assert "url" in res

@pytest.mark.asyncio
async def test_tool_registry_has_mobile_notification():
    schemas = get_all_tool_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "send_mobile_notification" in names
