"""Safe and verified file operations with automatic undo backup snapshots.

Inspired by Mark-LVI's actions/file_controller.py:
Every modification or deletion is backed up before touching disk, allowing
instant rollback if an error occurs.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from config.settings import BASE_DIR
from core.outcome import done, failed, unverified
from core.undo import undo_manager
from tools.registry import register_tool

logger = logging.getLogger("SARATHI.FileController")


@register_tool(
    name="write_file_verified",
    description="Safely writes or updates a file on disk with automatic undo backup and Python syntax validation."
)
def write_file_verified(file_path: str, content: str) -> str:
    """Writes content to file with backup snapshot and syntax verification."""
    clean_path = file_path.strip().strip("'\"")
    if not clean_path:
        return failed("write_file", "No file path provided")

    target = Path(clean_path).resolve()

    # Pre-modification backup snapshot for instant rollback
    snap_id = undo_manager.snapshot(target, f"Overwriting {target.name}")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        # Verify on disk
        if not target.exists():
            return failed("write_file", "File does not exist after write operation", path=str(target))

        # If python file, verify AST syntax
        syntax_note = None
        if target.suffix.lower() == ".py":
            try:
                ast.parse(content)
                syntax_note = "Valid Python AST"
            except SyntaxError as e:
                return unverified(
                    "write_file",
                    path=str(target.name),
                    warning=f"File written but has syntax error: {e}",
                    line=e.lineno,
                    backup_id=snap_id
                )

        return done(
            "write_file",
            path=str(target.name),
            bytes=len(content),
            syntax=syntax_note,
            backup_id=snap_id,
            verified=True
        )
    except Exception as e:
        logger.error(f"Error writing file {target}: {e}")
        return failed("write_file", str(e), path=str(target))


@register_tool(
    name="read_file_snippet",
    description="Reads a text or code file with line numbers for inspection."
)
def read_file_snippet(file_path: str, start_line: int = 1, max_lines: int = 60) -> str:
    """Reads a section of a file safely."""
    clean_path = file_path.strip().strip("'\"")
    target = Path(clean_path).resolve()

    if not target.exists():
        return failed("read_file", f"File '{target.name}' not found", path=str(target))

    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        total_lines = len(lines)
        s_idx = max(0, start_line - 1)
        e_idx = min(total_lines, s_idx + max_lines)
        selected = lines[s_idx:e_idx]

        numbered = [f"{i+1:4d}: {line}" for i, line in enumerate(selected, start=s_idx)]
        snippet = "\n".join(numbered)

        return done(
            "read_file",
            file=target.name,
            total_lines=total_lines,
            showing=f"{s_idx+1}-{e_idx}",
            content=snippet
        )
    except Exception as e:
        return failed("read_file", str(e), path=str(target))


@register_tool(
    name="delete_file_safely",
    description="Deletes a file safely after creating a recovery snapshot so it can be restored with undo."
)
def delete_file_safely(file_path: str) -> str:
    """Deletes a file with automatic undo snapshot."""
    clean_path = file_path.strip().strip("'\"")
    target = Path(clean_path).resolve()

    if not target.exists():
        return failed("delete_file", f"File '{target.name}' does not exist")

    # Save backup snapshot
    snap_id = undo_manager.snapshot(target, f"Deleting {target.name}")
    try:
        target.unlink()
        return done("delete_file", file=target.name, backup_id=snap_id, undoable=True)
    except Exception as e:
        return failed("delete_file", str(e), file=target.name)


__all__ = [
    "write_file_verified",
    "read_file_snippet",
    "delete_file_safely"
]
