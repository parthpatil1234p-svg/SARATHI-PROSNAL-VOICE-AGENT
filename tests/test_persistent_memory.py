"""Tests for Persistent SQLite Memory and Long-Term Retention."""

import tempfile
from pathlib import Path
import pytest

from core.persistent_memory import PersistentMemoryManager
from llm.memory import ConversationMemory


@pytest.fixture
def temp_memory_mgr(tmp_path: Path):
    db_file = tmp_path / "test_memory.db"
    mgr = PersistentMemoryManager(db_path=db_file)
    return mgr


def test_persistent_memory_init(temp_memory_mgr: PersistentMemoryManager):
    """Verifies that database schema initializes with default facts."""
    facts = temp_memory_mgr.get_all_facts()
    assert "user_name" in facts
    assert facts["user_name"] == "Parth"
    assert "assistant_name" in facts
    assert facts["assistant_name"] == "SARATHI"


def test_persistent_memory_save_and_retrieve_turn(temp_memory_mgr: PersistentMemoryManager):
    """Verifies storing and retrieving conversation turns across sessions."""
    temp_memory_mgr.save_turn(role="user", content="Hello Sarathi, remember my startup!")
    temp_memory_mgr.save_turn(role="assistant", content="Always got your back, Parth!")

    history = temp_memory_mgr.get_recent_history(limit=5)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert "remember my startup" in history[0]["content"]
    assert history[1]["role"] == "assistant"
    assert "Always got your back" in history[1]["content"]


def test_user_fact_retention_and_auto_extract(temp_memory_mgr: PersistentMemoryManager):
    """Verifies storing and auto-extracting facts from user speech."""
    temp_memory_mgr.set_user_fact("favorite_editor", "VS Code", category="preference")
    assert temp_memory_mgr.get_user_fact("favorite_editor") == "VS Code"

    # Auto extract test
    temp_memory_mgr.auto_extract_facts("Remember that my main server runs on port 8000")
    facts = temp_memory_mgr.get_all_facts()
    found = any("port 8000" in v for v in facts.values())
    assert found is True


def test_behavioral_rules_retention(temp_memory_mgr: PersistentMemoryManager):
    """Verifies behavioral guidelines persist in memory."""
    temp_memory_mgr.add_behavioral_rule("custom_rule", "Always respond with enthusiasm.")
    rules = temp_memory_mgr.get_active_rules()
    assert any("Always respond with enthusiasm." in r for r in rules)


def test_conversation_memory_integration(temp_memory_mgr: PersistentMemoryManager):
    """Verifies ConversationMemory loads past history and context prompt."""
    temp_memory_mgr.save_turn("user", "What's our goal?")
    temp_memory_mgr.save_turn("assistant", "To build the best voice agent, Parth!")

    # Instantiate ConversationMemory using the test DB
    conv_mem = ConversationMemory(max_turns=5, db=temp_memory_mgr)
    messages = conv_mem.get_messages()

    # Position 0 should be system prompt with injected persistent memory
    assert messages[0]["role"] == "system"
    assert "PERMANENT LONG-TERM MEMORY" in messages[0]["content"]

    # Subsequent positions should be restored conversation turns
    assert any("What's our goal?" in m.get("content", "") for m in messages)
    assert any("To build the best voice agent" in m.get("content", "") for m in messages)
