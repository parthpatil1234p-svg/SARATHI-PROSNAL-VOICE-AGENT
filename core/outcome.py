"""Structured verified outcomes for assistant tools.

Inspired by Mark-LVI's core/outcome.py philosophy:
- `done`: It happened and was verified against actual system state (process table, file system, returncode).
- `unverified`: The command was dispatched, but the resulting state could not yet be confirmed.
- `failed`: It failed, with exact reason and actionable error diagnostic facts.
"""

from __future__ import annotations
from typing import Any

DONE = "done"
UNVERIFIED = "unverified"
FAILED = "failed"
STARTED = "started"


def _render_value(value: Any) -> str:
    """Renders a value cleanly without raw quotes or unescaped newlines."""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).replace('"', "'").replace("\n", " ").strip()
    return f'"{text}"' if (" " in text or not text) else text


def _format_line(status: str, action: str, facts: dict[str, Any]) -> str:
    """Formats structured fact string: status=done action=open_app name=chrome pid=1234"""
    parts = [f"status={status}", f"action={action}"]
    for k, v in facts.items():
        if v is not None:
            parts.append(f"{k}={_render_value(v)}")
    return " ".join(parts)


def done(action: str, /, **facts: Any) -> str:
    """Indicates the action succeeded and was confirmed by observing system state."""
    return _format_line(DONE, action, facts)


def unverified(action: str, /, **facts: Any) -> str:
    """The request went through, but result could not be confirmed immediately."""
    return _format_line(UNVERIFIED, action, facts)


def failed(action: str, reason: str, /, **facts: Any) -> str:
    """The action did not succeed. Reports the exact reason."""
    facts["reason"] = reason
    return _format_line(FAILED, action, facts)


def started(action: str, /, **facts: Any) -> str:
    """A long-running background process has started successfully."""
    return _format_line(STARTED, action, facts)


__all__ = ["DONE", "UNVERIFIED", "FAILED", "STARTED", "done", "unverified", "failed", "started"]
