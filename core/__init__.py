"""Core package exports."""

from core.event_bus import EventBus, event_bus
from core.state_machine import AssistantState, StateMachine

__all__ = [
    "AssistantOrchestrator",
    "AssistantState",
    "EventBus",
    "StateMachine",
    "event_bus",
]


def __getattr__(name: str):
    if name == "AssistantOrchestrator":
        from core.orchestrator import AssistantOrchestrator
        return AssistantOrchestrator
    raise AttributeError(f"module 'core' has no attribute '{name}'")
