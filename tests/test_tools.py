"""Unit tests for the OS and System Tools."""

import pytest

from tools.code_runner import execute_python_code
from tools.registry import execute_tool, get_all_tool_schemas
from tools.system_tools import get_system_diagnostics


def test_registered_tools_schemas():
    schemas = get_all_tool_schemas()
    assert len(schemas) >= 8

    tool_names = [s["function"]["name"] for s in schemas]
    assert "get_system_diagnostics" in tool_names
    assert "set_system_volume" in tool_names
    assert "open_application" in tool_names
    assert "execute_python_code" in tool_names


def test_system_diagnostics():
    data = get_system_diagnostics()
    assert "cpu_usage_percent" in data
    assert "ram_usage" in data
    assert "battery_status" in data


def test_code_runner_safe():
    output = execute_python_code("print('Hello Jarvis')")
    assert output == "Hello Jarvis"


def test_code_runner_blocks_destructive_commands():
    output = execute_python_code("import shutil; shutil.rmtree('C:/')")
    assert "Execution blocked" in output


@pytest.mark.asyncio
async def test_tool_dispatcher():
    result = await execute_tool("execute_python_code", {"code": "print(2 + 2)"})
    assert result.strip() == "4"
