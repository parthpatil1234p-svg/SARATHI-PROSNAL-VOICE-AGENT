"""Tool Registry and Function Calling Dispatcher for J.A.R.V.I.S."""

import inspect
import json
import logging
from collections.abc import Callable
from typing import Any, get_type_hints

logger = logging.getLogger("JARVIS.ToolRegistry")

# Global tool registry: name -> (function, openai_schema)
_TOOL_REGISTRY: dict[str, tuple[Callable, dict]] = {}


def register_tool(name: str | None = None, description: str | None = None):
    """
    Decorator to register a Python function as a J.A.R.V.I.S. tool with auto-generated schema.
    """
    def decorator(func: Callable):
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip()

        # Build JSON Schema for parameters
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = type_hints.get(param_name, str)
            json_type = "string"
            if param_type in (int, float):
                json_type = "number" if param_type is float else "integer"
            elif param_type is bool:
                json_type = "boolean"
            elif param_type in (list, tuple):
                json_type = "array"
            elif param_type is dict:
                json_type = "object"

            properties[param_name] = {
                "type": json_type,
                "description": f"Parameter {param_name}"
            }

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_desc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

        _TOOL_REGISTRY[tool_name] = (func, schema)
        logger.debug(f"Registered tool: '{tool_name}'")
        return func

    return decorator


def get_all_tool_schemas() -> list[dict]:
    """Returns OpenAI-compatible tools definitions for all registered tools."""
    return [schema for _, schema in _TOOL_REGISTRY.values()]


async def execute_tool(tool_name: str, arguments: dict | str) -> Any:
    """Executes a registered tool by name with arguments."""
    if tool_name not in _TOOL_REGISTRY:
        raise ValueError(f"Tool '{tool_name}' not found in registry.")

    func, _ = _TOOL_REGISTRY[tool_name]

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON arguments: {e}"

    logger.info(f"Executing tool '{tool_name}' with arguments: {arguments}")
    try:
        if inspect.iscoroutinefunction(func):
            result = await func(**arguments)
        else:
            result = func(**arguments)
        return result
    except Exception as e:
        logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
        return f"Tool execution failed: {e!s}"
