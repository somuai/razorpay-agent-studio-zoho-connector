"""Circuit breaker pattern for Zoho rate-limit locks and block codes (FR-3.5)."""

import asyncio
from enum import StrEnum

from zoho_inventory_connector.client.errors import CircuitOpenError
from zoho_inventory_connector.ratelimit.clock import Clock, SystemClock


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker that trips on severe upstream signals (e.g. Zoho code 44/1070).

    When open, immediately fails fast with CircuitOpenError without making upstream HTTP calls.
    """

    def __init__(
        self,
        cooldown_seconds: float = 60.0,
        clock: Clock | None = None,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.clock: Clock = clock or SystemClock()
        self.state = CircuitState.CLOSED
        self.opened_at: float | None = None
        self._lock = asyncio.Lock()

    def is_open(self) -> bool:
        """Check if circuit is currently open without acquiring lock."""
        if self.state == CircuitState.CLOSED:
            return False
        now = self.clock.monotonic()
        if self.opened_at is not None and (now - self.opened_at) >= self.cooldown_seconds:
            self.state = CircuitState.HALF_OPEN
            return False
        return True

    def check_state(self) -> None:
        """Raise CircuitOpenError if breaker is currently open."""
        if self.is_open():
            cooldown_left = 0.0
            if self.opened_at is not None:
                cooldown_left = max(
                    0.0, self.cooldown_seconds - (self.clock.monotonic() - self.opened_at)
                )
            raise CircuitOpenError(cooldown_remaining=cooldown_left)

    def trip(self, custom_cooldown: float | None = None) -> None:
        """Trip circuit breaker into OPEN state."""
        self.state = CircuitState.OPEN
        self.opened_at = self.clock.monotonic()
        if custom_cooldown is not None and custom_cooldown > 0:
            self.cooldown_seconds = custom_cooldown

    def record_success(self) -> None:
        """Record a successful response, resetting circuit to CLOSED."""
        self.state = CircuitState.CLOSED
        self.opened_at = None
