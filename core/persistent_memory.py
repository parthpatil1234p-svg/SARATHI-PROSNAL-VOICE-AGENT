"""Persistent SQLite Memory and Behavioral Retention Engine for S.A.R.A.T.H.I.

Ensures that all user conversations, personal facts, preferences, and behavioral
rules are permanently retained across application restarts, system reboots,
and file cleanups.

Features:
- Dual-layer storage: Primary in application directory, secondary backup in user profile (%APPDATA% / ~/.sarathi)
- Auto-restoration if primary database is ever deleted or missing
- SQLite WAL mode for fast concurrent reads and writes
- Long-term user profile and fact extraction
- Seamless conversation turn history
"""

import json
import logging
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import EXE_DIR, settings

logger = logging.getLogger("SARATHI.Memory")


class PersistentMemoryManager:
    """Manages persistent SQLite memory, conversation history, and user profile retention."""

    _instance = None

    @classmethod
    def get_instance(cls) -> "PersistentMemoryManager":
        if cls._instance is None:
            cls._instance = PersistentMemoryManager()
        return cls._instance

    def __init__(self, db_path: Path | None = None, backup_db_path: Path | None = None):
        # 1. Determine primary and backup paths
        self.primary_db_path = db_path or (EXE_DIR / "sarathi_memory.db")

        if backup_db_path is not None:
            self.backup_db_path = backup_db_path
        elif db_path is not None:
            # Custom db path (e.g. in tests) - isolate backup to same directory
            self.backup_db_path = db_path.parent / f"{db_path.stem}_backup.db"
        else:
            # Backup directory in user's home/AppData directory (immune to repo cleanups)
            appdata = os.environ.get("APPDATA")
            if appdata:
                self.backup_dir = Path(appdata) / "SARATHI"
            else:
                self.backup_dir = Path.home() / ".sarathi"
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            self.backup_db_path = self.backup_dir / "sarathi_memory.db"

        # 2. Auto-recover from backup if primary is missing or empty
        self._ensure_database_integrity()

        # 3. Initialize SQLite schema
        self._init_db()

        # 4. Seed default core identity facts if not present
        self._seed_default_facts()

    def _ensure_database_integrity(self):
        """Restores database from backup if primary is missing or corrupted."""
        try:
            if (not self.primary_db_path.exists() or self.primary_db_path.stat().st_size == 0):
                if self.backup_db_path.exists() and self.backup_db_path.stat().st_size > 0:
                    logger.info(f"Restoring persistent memory from backup: {self.backup_db_path}")
                    shutil.copy2(self.backup_db_path, self.primary_db_path)
            elif self.primary_db_path.exists() and (not self.backup_db_path.exists() or self.backup_db_path.stat().st_size == 0):
                # Sync primary to backup
                shutil.copy2(self.primary_db_path, self.backup_db_path)
        except Exception as e:
            logger.warning(f"Memory integrity sync warning: {e}")

    def _get_connection(self) -> sqlite3.Connection:
        """Opens a connection to the primary SQLite database with WAL mode."""
        conn = sqlite3.connect(str(self.primary_db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        """Creates the required tables for long-term memory."""
        with self._get_connection() as conn:
            # 1. Conversations table (All historical turns)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    session_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT,
                    metadata TEXT
                );
            """)

            # 2. User Facts & Profile table (Long-term persistent user knowledge)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_facts (
                    key TEXT PRIMARY KEY,
                    category TEXT DEFAULT 'general',
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    updated_at TEXT NOT NULL
                );
            """)

            # 3. Behavioral Rules & Instructions table (Learned guidelines)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS behavioral_rules (
                    rule_key TEXT PRIMARY KEY,
                    rule_text TEXT NOT NULL,
                    active INTEGER DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
            """)

            # Indexes for fast lookup
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_time ON conversations(timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_facts_cat ON user_facts(category);")
            conn.commit()

        # Sync schema to backup
        self._sync_to_backup()

    def _sync_to_backup(self):
        """Asynchronously or safely mirrors the primary DB to the user profile backup."""
        try:
            if self.primary_db_path.exists():
                shutil.copy2(self.primary_db_path, self.backup_db_path)
        except Exception as e:
            logger.debug(f"Backup sync notice: {e}")

    def _seed_default_facts(self):
        """Seeds initial identity and user facts if missing."""
        user_name = getattr(settings, "USER_NAME", "Parth")
        default_facts = {
            "user_name": (user_name, "identity"),
            "assistant_name": ("SARATHI", "identity"),
            "relationship": ("Fiercely loyal right-hand partner, companion, and friend inspired by Iron Man's JARVIS", "persona"),
            "tone_style": ("Warm, conversational, charismatic, friendly. Never lectures like a teacher.", "persona"),
            "api_infrastructure": ("Groq Cloud API (high-speed LPU inference)", "system"),
            "os_environment": ("Windows 11 Desktop", "environment"),
        }
        for k, (v, cat) in default_facts.items():
            if self.get_user_fact(k) is None:
                self.set_user_fact(k, v, category=cat)

        default_rules = {
            "anti_teacher_rule": "Speak like a warm, supportive friend and wingman. Never lecture, preach, or talk down like a school teacher.",
            "identity_sarathi": "Strictly identify as SARATHI, never Jarvis.",
            "concise_spoken": "Keep voice answers to 1-2 crisp spoken sentences without markdown or bullet points.",
            "user_loyalty": f"Prioritize {user_name}'s instructions with highest loyalty and friendliness."
        }
        for rk, rtext in default_rules.items():
            self.add_behavioral_rule(rk, rtext)

    # -------------------------------------------------------------
    # Conversation History
    # -------------------------------------------------------------

    def save_turn(self, role: str, content: str, session_id: str = "", metadata: dict | None = None):
        """Saves a conversational turn (user, assistant, tool) to permanent storage."""
        if not content and not metadata:
            return

        now = time.time()
        iso = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        meta_json = json.dumps(metadata) if metadata else None

        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO conversations (timestamp, created_at, session_id, role, content, metadata) VALUES (?, ?, ?, ?, ?, ?);",
                    (now, iso, session_id, role, content, meta_json)
                )
                conn.commit()
            self._sync_to_backup()
        except Exception as e:
            logger.error(f"Failed to save conversation turn: {e}")

    def get_recent_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Returns the most recent N conversational turns."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT role, content, created_at, metadata FROM conversations WHERE role IN ('user', 'assistant') ORDER BY id DESC LIMIT ?;",
                    (limit,)
                )
                rows = cursor.fetchall()
                # Reverse to chronological order (oldest to newest)
                results = []
                for r in reversed(rows):
                    results.append({
                        "role": r["role"],
                        "content": r["content"] or "",
                        "time": r["created_at"].split()[-1] if r["created_at"] else ""
                    })
                return results
        except Exception as e:
            logger.error(f"Failed to fetch recent history: {e}")
            return []

    def get_all_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Returns full historical conversation logs for the HUD viewer."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, created_at, role, content, metadata FROM conversations ORDER BY id DESC LIMIT ?;",
                    (limit,)
                )
                rows = cursor.fetchall()
                results = []
                for r in reversed(rows):
                    meta = {}
                    if r["metadata"]:
                        try:
                            meta = json.loads(r["metadata"])
                        except Exception:
                            pass
                    results.append({
                        "id": r["id"],
                        "time": r["created_at"],
                        "role": r["role"],
                        "content": r["content"] or "",
                        "metadata": meta
                    })
                return results
        except Exception as e:
            logger.error(f"Failed to fetch all history: {e}")
            return []

    # -------------------------------------------------------------
    # User Facts & Long-term Profile
    # -------------------------------------------------------------

    def set_user_fact(self, key: str, value: str, category: str = "general", confidence: float = 1.0):
        """Sets or updates a permanent fact about the user or system."""
        clean_key = key.strip().lower().replace(" ", "_")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO user_facts (key, category, value, confidence, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        category = excluded.category,
                        value = excluded.value,
                        confidence = excluded.confidence,
                        updated_at = excluded.updated_at;
                    """,
                    (clean_key, category, value.strip(), confidence, now_str)
                )
                conn.commit()
            self._sync_to_backup()
            logger.info(f"Learned persistent fact: [{clean_key}] = '{value}'")
        except Exception as e:
            logger.error(f"Failed to set user fact '{key}': {e}")

    def get_user_fact(self, key: str) -> str | None:
        """Retrieves a specific permanent user fact."""
        clean_key = key.strip().lower().replace(" ", "_")
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT value FROM user_facts WHERE key = ?;", (clean_key,))
                row = cursor.fetchone()
                return row["value"] if row else None
        except Exception as e:
            logger.error(f"Failed to get user fact '{key}': {e}")
            return None

    def get_all_facts(self) -> dict[str, str]:
        """Returns all stored user facts as a key-value mapping."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT key, value FROM user_facts ORDER BY key ASC;")
                return {row["key"]: row["value"] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Failed to get all facts: {e}")
            return {}

    # -------------------------------------------------------------
    # Behavioral Rules
    # -------------------------------------------------------------

    def add_behavioral_rule(self, rule_key: str, rule_text: str):
        """Adds or updates a persistent behavioral guideline."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO behavioral_rules (rule_key, rule_text, active, updated_at)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(rule_key) DO UPDATE SET
                        rule_text = excluded.rule_text,
                        active = 1,
                        updated_at = excluded.updated_at;
                    """,
                    (rule_key.strip(), rule_text.strip(), now_str)
                )
                conn.commit()
            self._sync_to_backup()
        except Exception as e:
            logger.error(f"Failed to add behavioral rule '{rule_key}': {e}")

    def get_active_rules(self) -> list[str]:
        """Returns all currently active behavioral rules."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT rule_text FROM behavioral_rules WHERE active = 1 ORDER BY rule_key ASC;")
                return [row["rule_text"] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get active rules: {e}")
            return []

    # -------------------------------------------------------------
    # Context Formatting & Auto-Extraction
    # -------------------------------------------------------------

    def get_memory_context_prompt(self) -> str:
        """Builds a concise context block of known facts and rules for the LLM system prompt."""
        facts = self.get_all_facts()
        rules = self.get_active_rules()

        lines = ["\n[PERMANENT LONG-TERM MEMORY (CROSS-SESSION)]:"]
        if facts:
            lines.append("Known User Facts & Context:")
            for k, v in facts.items():
                readable_k = k.replace("_", " ").title()
                lines.append(f"- {readable_k}: {v}")

        if rules:
            lines.append("Permanent Behavioral Guidelines:")
            for r in rules:
                lines.append(f"- {r}")

        return "\n".join(lines)

    def auto_extract_facts(self, user_text: str):
        """Heuristically extracts user statements and saves them to persistent memory."""
        cleaned = user_text.strip()

        # 1. "Remember that X" / "Please remember X" / "Yaad rakhna ki X"
        rem_match = re.search(r'(?:please\s+)?remember\s+(?:that\s+)?(.+)', cleaned, re.IGNORECASE)
        if rem_match:
            fact = rem_match.group(1).strip().rstrip(".,!?")
            self.set_user_fact(f"custom_{int(time.time())}", fact, category="instruction")
            return

        # 2. "My name is X" / "Mera naam X hai"
        name_match = re.search(r'(?:my\s+name\s+is|mera\s+naam)\s+([a-zA-Z]+)', cleaned, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).capitalize()
            self.set_user_fact("user_name", name, category="identity")
            return

        # 3. "I like X" / "I prefer X"
        pref_match = re.search(r'i\s+(?:like|prefer|love)\s+(.+)', cleaned, re.IGNORECASE)
        if pref_match:
            pref = pref_match.group(1).strip().rstrip(".,!?")
            self.set_user_fact(f"preference_{int(time.time())}", f"User likes/prefers {pref}", category="preference")
            return


# Singleton instance
memory_db = PersistentMemoryManager.get_instance()
