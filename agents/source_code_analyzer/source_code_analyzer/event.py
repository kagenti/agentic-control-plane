import logging
from abc import ABC, abstractmethod


class Event(ABC):
    @abstractmethod
    async def emit_event(self, message: str, final: bool = False) -> None:
        """Emit Event"""
        pass


class LoggingEvent(Event):
    """Event emitter that only logs messages."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    async def emit_event(self, message: str, final: bool = False) -> None:
        status = "final" if final else "update"
        self._logger.info("[%s] %s", status, message)
