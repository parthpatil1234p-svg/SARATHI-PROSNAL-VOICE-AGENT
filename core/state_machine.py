"""Finite State Machine for J.A.R.V.I.S. operational lifecycle."""

import logging
import threading
from collections.abc import Callable
from enum import Enum, auto

logger = logging.getLogger("SARATHI.StateMachine")


class AssistantState(Enum):
    IDLE = auto()               # Sleeping / listening for wake word ("Hey Sarathi")
    WAKE_DETECTED = auto()      # Wake word triggered, playing chime
    LISTENING = auto()          # Streaming user speech via microphone & VAD
    PROCESSING = auto()         # LLM thinking / generating tokens
    EXECUTING_TOOL = auto()     # Running OS/Python actions
    SPEAKING = auto()           # TTS audio actively playing through speaker
    INTERRUPTED = auto()        # User spoke mid-speech; halting output immediately


class StateMachine:
    """Thread-safe state manager for the assistant."""

    def __init__(self, initial_state: AssistantState = AssistantState.IDLE):
        self._state = initial_state
        self._lock = threading.Lock()
        self._listeners: list[Callable[[AssistantState, AssistantState], None]] = []

    @property
    def current_state(self) -> AssistantState:
        with self._lock:
            return self._state

    def add_listener(self, callback: Callable[[AssistantState, AssistantState], None]):
        """Register a callback for state transition notifications."""
        self._listeners.append(callback)

    def transition_to(self, new_state: AssistantState) -> bool:
        """Transitions state if valid, notifying listeners."""
        with self._lock:
            old_state = self._state
            if old_state == new_state:
                return False

            self._state = new_state
            logger.info(f"State Transition: [{old_state.name}] -> [{new_state.name}]")

        # Notify listeners outside the lock to avoid deadlocks
        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state transition listener: {e}")

        return True

    def is_idle(self) -> bool:
        return self.current_state == AssistantState.IDLE

    def is_speaking(self) -> bool:
        return self.current_state == AssistantState.SPEAKING

    def is_listening(self) -> bool:
        return self.current_state == AssistantState.LISTENING
