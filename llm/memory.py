"""Conversational memory and context management for S.A.R.A.T.H.I.

Integrates persistent cross-session SQLite memory so user facts, guidelines,
and previous conversation turns are retained permanently across restarts.
"""

from typing import Any

from config.persona import SARATHI_CONCISE_PROMPT, SARATHI_SYSTEM_PROMPT
from config.settings import settings
from core.persistent_memory import PersistentMemoryManager, memory_db


class ConversationMemory:
    """
    Maintains active conversational turns backed by persistent SQLite storage.
    Always anchors the S.A.R.A.T.H.I. persona prompt with injected permanent memories at position 0.
    """

    def __init__(self, max_turns: int | None = None, db: PersistentMemoryManager | None = None):
        if max_turns is not None:
            self.max_turns = max_turns
        else:
            self.max_turns = 6 if settings.ENABLE_LLM_LOW_LATENCY else 12
        self.db = db or memory_db
        self.messages: list[dict[str, Any]] = []
        self.reset()

    def reset(self):
        """Initializes memory with persona prompt, active learned rules, and recent turn history."""
        prompt_tmpl = SARATHI_CONCISE_PROMPT if settings.ENABLE_LLM_LOW_LATENCY else SARATHI_SYSTEM_PROMPT
        formatted_prompt = prompt_tmpl.format(user_name=settings.USER_NAME)

        # Inject persistent cross-session memories and behavioral rules
        memory_block = self.db.get_memory_context_prompt()
        full_system_content = f"{formatted_prompt}\n{memory_block}"

        self.messages = [
            {"role": "system", "content": full_system_content}
        ]

        # Seamlessly load recent turns from persistent DB
        recent_history = self.db.get_recent_history(limit=self.max_turns)
        for turn in recent_history:
            self.messages.append({
                "role": turn["role"],
                "content": turn["content"]
            })

    def add_user_message(self, content: str):
        """Appends user voice transcription and persists to SQLite."""
        self.messages.append({"role": "user", "content": content})
        # Auto-extract and save any facts stated by the user
        self.db.auto_extract_facts(content)
        # Save to persistent SQLite database
        self.db.save_turn(role="user", content=content)
        self._trim_history()

    def add_assistant_message(self, content: str):
        """Appends assistant's spoken response and persists to SQLite."""
        self.messages.append({"role": "assistant", "content": content})
        self.db.save_turn(role="assistant", content=content)
        self._trim_history()

    def add_tool_call_turn(self, tool_call_id: str, tool_name: str, arguments: str, result: str):
        """Records an executed tool invocation and its observation."""
        self.messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                }
            ]
        })
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": str(result)
        })
        # Save to persistent storage
        self.db.save_turn(
            role="tool",
            content=str(result),
            metadata={"tool_name": tool_name, "args": arguments, "tool_call_id": tool_call_id}
        )
        self._trim_history()

    def get_messages(self) -> list[dict[str, Any]]:
        """Returns the full message list for the API request."""
        return self.messages

    def _trim_history(self):
        """Keeps system prompt at index 0 and limits conversational history."""
        # System prompt + at most max_turns * 2 messages
        max_allowed = 1 + (self.max_turns * 2)
        if len(self.messages) > max_allowed:
            # Keep system prompt, discard oldest in-memory messages (they are still in SQLite)
            self.messages = [self.messages[0]] + self.messages[-(max_allowed - 1):]
