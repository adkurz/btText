"""Synchronous application events with isolated listener failures."""

from collections import defaultdict
from collections.abc import Callable
import logging


logger = logging.getLogger(__name__)
EventListener = Callable[..., object]


class EventEmitter:
    """Publish events without letting one listener disrupt other work."""

    def __init__(self) -> None:
        """Create an emitter without registered listeners."""
        self._listeners: dict[str, list[EventListener]] = defaultdict(list)

    def on(self, event: str, listener: EventListener) -> EventListener:
        """Register and return a listener for ``event``."""
        self._listeners[event].append(listener)
        return listener

    def off(self, event: str, listener: EventListener) -> EventListener:
        """Remove and return a previously registered listener."""
        listeners = self._listeners.get(event)
        if listeners is not None:
            self._listeners[event] = [
                candidate
                for candidate in listeners
                if candidate != listener
            ]
        return listener

    def emit(self, event: str, *args, **kwargs) -> None:
        """Call every listener, logging failures and continuing in order."""
        for listener in tuple(self._listeners.get(event, ())):
            try:
                listener(*args, **kwargs)
            except Exception:
                logger.exception(
                    "Event listener %r failed while handling %r",
                    listener,
                    event,
                )
