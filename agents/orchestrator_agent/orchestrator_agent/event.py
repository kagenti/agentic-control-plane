"""Event interface for streaming updates."""

import logging
from abc import ABC, abstractmethod


class Event(ABC):
    """Abstract interface for emitting task events."""

    @abstractmethod
    async def emit_event(self, message: str, final: bool = False) -> None:
        """Emit a task event."""
        pass


class LoggingEvent(Event):
    """Event implementation that logs messages."""

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)

    async def emit_event(self, message: str, final: bool = False) -> None:
        """Log the event message."""
        if final:
            self.logger.info(f"[FINAL] {message}")
        else:
            self.logger.info(message)
