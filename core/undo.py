"""Transactional file undo manager for safe desktop modifications.

Keeps timestamped snapshots in `.sarathi_backup/` so any file created, modified,
or deleted by the assistant can be rolled back immediately.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any

from config.settings import BASE_DIR

logger = logging.getLogger("SARATHI.Undo")

BACKUP_DIR = BASE_DIR / ".sarathi_backup"


class UndoManager:
    """Tracks and reverses file modifications performed by Sarathi."""

    def __init__(self, backup_dir: Path | None = None):
        self.backup_dir = backup_dir or BACKUP_DIR
        self.history: list[dict[str, Any]] = []

    def _ensure_dir(self):
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def snapshot(self, target_path: Path | str, description: str = "") -> str | None:
        """Takes a pre-modification snapshot of the file. Returns backup ID or None."""
        self._ensure_dir()
        p = Path(target_path).resolve()
        timestamp = int(time.time() * 1000)
        snap_id = f"snap_{timestamp}_{p.name}"

        if not p.exists():
            # File is about to be created: record that undoing means deleting it
            entry = {
                "id": snap_id,
                "target": str(p),
                "action": "created",
                "backup_path": None,
                "timestamp": timestamp,
                "description": description or f"Created {p.name}"
            }
            self.history.append(entry)
            logger.info(f"Recorded creation intent for {p} (backup ID: {snap_id})")
            return snap_id

        backup_file = self.backup_dir / snap_id
        try:
            shutil.copy2(p, backup_file)
            entry = {
                "id": snap_id,
                "target": str(p),
                "action": "modified",
                "backup_path": str(backup_file),
                "timestamp": timestamp,
                "description": description or f"Modified {p.name}"
            }
            self.history.append(entry)
            logger.info(f"Snapshot saved for {p} -> {backup_file}")
            return snap_id
        except Exception as e:
            logger.error(f"Failed to snapshot {p}: {e}")
            return None

    def undo_last(self) -> tuple[bool, str]:
        """Rolls back the most recent file action. Returns (success, message)."""
        if not self.history:
            return False, "No file operations recorded in undo history."

        entry = self.history.pop()
        target = Path(entry["target"])
        action = entry["action"]
        backup_path = entry.get("backup_path")

        try:
            if action == "created":
                if target.exists():
                    target.unlink()
                    return True, f"Undid creation of {target.name} (file removed)."
                return True, f"File {target.name} was already deleted."

            if action == "modified" and backup_path:
                bp = Path(backup_path)
                if bp.exists():
                    shutil.copy2(bp, target)
                    bp.unlink(missing_ok=True)
                    return True, f"Restored {target.name} to version prior to {entry['description']}."
                return False, f"Backup file {bp.name} not found."

            return False, f"Unknown action '{action}' in undo history."
        except Exception as e:
            logger.error(f"Failed to undo action: {e}")
            return False, f"Undo failed: {e}"


# Global undo manager singleton
undo_manager = UndoManager()

__all__ = ["UndoManager", "undo_manager", "BACKUP_DIR"]
