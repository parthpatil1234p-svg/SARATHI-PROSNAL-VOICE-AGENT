"""Asynchronous Event Bus for decoupled internal communication."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger("JARVIS.EventBus")


class EventBus:
    """Async pub-sub event dispatcher."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable[[Any], Coroutine[Any, Any, None]]]] = {}

    def subscribe(self, event_name: str, handler: Callable[[Any], Coroutine[Any, Any, None]]):
        """Subscribes an async handler to a specific event."""
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(handler)

    async def publish(self, event_name: str, payload: Any = None):
        """Publishes an event to all registered async handlers."""
        if event_name not in self._subscribers:
            return

        handlers = self._subscribers[event_name]
        tasks = [asyncio.create_task(self._safe_call(h, payload, event_name)) for h in handlers]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_call(
        self,
        handler: Callable[[Any], Coroutine[Any, Any, None]],
        payload: Any,
        event_name: str
    ):
        try:
            await handler(payload)
        except Exception as e:
            logger.error(f"Handler error for event '{event_name}': {e}", exc_info=True)


# Global event bus singleton
event_bus = EventBus()
