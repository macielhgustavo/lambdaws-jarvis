"""Small synchronous event bus.

This is intentionally tiny in v11. It establishes the contract that future
voice, scheduler, daemon, desktop and automation services can communicate
without importing one another.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event: str, handler: EventHandler) -> Callable[[], None]:
        self._subscribers[event].append(handler)

        def unsubscribe() -> None:
            handlers = self._subscribers.get(event, [])
            if handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    def publish(self, event: str, **payload: Any) -> None:
        for handler in tuple(self._subscribers.get(event, ())):
            handler(dict(payload))
