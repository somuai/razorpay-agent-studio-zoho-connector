"""Rate limiting and client telemetry metrics (FR-3.6)."""

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RateLimitMetrics:
    """Metrics tracking rate limiting, retries, and quota consumption."""

    calls_made: int = 0
    calls_throttled: int = 0
    calls_retried: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    daily_quota_consumed: int = 0
    daily_quota_limit: int = 1000
    circuit_trips: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def record_call(self, is_upstream: bool = True) -> None:
        async with self._lock:
            self.calls_made += 1
            if is_upstream:
                self.daily_quota_consumed += 1

    async def record_throttled(self) -> None:
        async with self._lock:
            self.calls_throttled += 1

    async def record_retry(self) -> None:
        async with self._lock:
            self.calls_retried += 1

    async def record_cache_hit(self) -> None:
        async with self._lock:
            self.cache_hits += 1

    async def record_cache_miss(self) -> None:
        async with self._lock:
            self.cache_misses += 1

    async def record_circuit_trip(self) -> None:
        async with self._lock:
            self.circuit_trips += 1

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as dictionary."""
        quota_pct = (
            (self.daily_quota_consumed / self.daily_quota_limit) * 100.0
            if self.daily_quota_limit > 0
            else 0.0
        )
        total_lookups = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_lookups * 100.0) if total_lookups > 0 else 0.0

        return {
            "calls_made": self.calls_made,
            "calls_throttled": self.calls_throttled,
            "calls_retried": self.calls_retried,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate_pct": round(hit_rate, 2),
            "daily_quota_consumed": self.daily_quota_consumed,
            "daily_quota_limit": self.daily_quota_limit,
            "quota_consumed_pct": round(quota_pct, 2),
            "circuit_trips": self.circuit_trips,
        }
