"""Injectable clock interface for deterministic time-based testing (NFR-2)."""

import asyncio
import time
from abc import ABC, abstractmethod


class Clock(ABC):
    """Abstract clock interface providing monotonic and wall time."""

    @abstractmethod
    def monotonic(self) -> float:
        """Return the current monotonic time in seconds."""
        pass

    @abstractmethod
    def time(self) -> float:
        """Return the current wall-clock time in seconds."""
        pass

    @abstractmethod
    async def sleep(self, seconds: float) -> None:
        """Asynchronously sleep for the given number of seconds."""
        pass


class SystemClock(Clock):
    """Standard system clock relying on OS time and asyncio sleep."""

    def monotonic(self) -> float:
        return time.monotonic()

    def time(self) -> float:
        return time.time()

    async def sleep(self, seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)


class VirtualClock(Clock):
    """Virtual clock for deterministic, zero-sleep unit testing (NFR-2)."""

    def __init__(
        self, initial_monotonic: float = 1000.0, initial_wall: float = 1700000000.0
    ) -> None:
        self._monotonic: float = initial_monotonic
        self._wall: float = initial_wall

    def monotonic(self) -> float:
        return self._monotonic

    def time(self) -> float:
        return self._wall

    def advance(self, seconds: float) -> None:
        """Advance the virtual clock by the given number of seconds."""
        if seconds < 0:
            raise ValueError("VirtualClock cannot move backwards.")
        self._monotonic += seconds
        self._wall += seconds

    async def sleep(self, seconds: float) -> None:
        """In virtual mode, sleep instantly advances time without wall-clock delay."""
        if seconds > 0:
            self.advance(seconds)
        # Yield control briefly to allow cooperative event loop scheduling
        await asyncio.sleep(0)
