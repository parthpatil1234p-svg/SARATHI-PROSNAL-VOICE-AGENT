"""Conversational memory and context management for J.A.R.V.I.S."""

from typing import Any

from config.persona import JARVIS_SYSTEM_PROMPT
from config.settings import settings


class ConversationMemory:
    """
    Maintains a sliding token window of conversational turns.
    Always anchors the J.A.R.V.I.S. system prompt at position 0.
    """

    def __init__(self, max_turns: int = 12):
        self.max_turns = max_turns
        self.messages: list[dict[str, Any]] = []
        self.reset()

    def reset(self):
        """Initializes memory with the persona system prompt."""
        formatted_prompt = JARVIS_SYSTEM_PROMPT.format(user_name=settings.USER_NAME)
        self.messages = [
            {"role": "system", "content": formatted_prompt}
        ]

    def add_user_message(self, content: str):
        """Appends user voice transcription."""
        self.messages.append({"role": "user", "content": content})
        self._trim_history()

    def add_assistant_message(self, content: str):
        """Appends assistant's spoken response."""
        self.messages.append({"role": "assistant", "content": content})
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
        self._trim_history()

    def get_messages(self) -> list[dict[str, Any]]:
        """Returns the full message list for the API request."""
        return self.messages

    def _trim_history(self):
        """Keeps system prompt at index 0 and limits conversational history."""
        # System prompt + at most max_turns * 2 messages
        max_allowed = 1 + (self.max_turns * 2)
        if len(self.messages) > max_allowed:
            # Keep system prompt, discard oldest messages
            self.messages = [self.messages[0]] + self.messages[-(max_allowed - 1):]
