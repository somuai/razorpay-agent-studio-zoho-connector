"""Token bucket rate limiter and concurrency semaphore (FR-3.1, FR-3.2)."""

import asyncio

from zoho_inventory_connector.ratelimit.clock import Clock, SystemClock


class TokenBucket:
    """Thread-safe / asyncio-safe token bucket rate limiter with injectable clock."""

    def __init__(
        self,
        rate_per_minute: float = 80.0,
        capacity: float | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.rate_per_minute = float(rate_per_minute)
        self.capacity = float(capacity if capacity is not None else rate_per_minute)
        self.fill_rate = self.rate_per_minute / 60.0  # tokens per second
        self.tokens = self.capacity
        self.clock: Clock = clock or SystemClock()
        self.last_update = self.clock.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self.clock.monotonic()
        elapsed = now - self.last_update
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
            self.last_update = now

    async def acquire(self, tokens: float = 1.0) -> float:
        """Acquire tokens, waiting if necessary until available.

        Returns the number of seconds waited (0.0 if tokens were immediately available).
        """
        waited = 0.0
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return waited

                # Calculate required sleep duration to accumulate needed tokens
                needed = tokens - self.tokens
                delay = needed / self.fill_rate

            waited += delay
            await self.clock.sleep(delay)

    async def try_acquire(self, tokens: float = 1.0) -> bool:
        """Attempt to acquire tokens without waiting. Return True if successful."""
        async with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


class ConcurrencyLimiter:
    """Concurrency semaphore with bounded active concurrent in-flight requests (FR-3.2)."""

    def __init__(self, max_concurrency: int = 5) -> None:
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def __aenter__(self) -> "ConcurrencyLimiter":
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._semaphore.release()
