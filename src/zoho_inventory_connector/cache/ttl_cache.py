"""In-process asynchronous TTL cache with staleness metadata (FR-4)."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from zoho_inventory_connector.ratelimit.clock import Clock, SystemClock

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Represents a cached item with timestamps."""

    value: T
    created_at_mono: float
    created_at_iso: str
    ttl_seconds: float


class TTLCache:
    """Thread-safe asynchronous TTL cache with staleness telemetry (FR-4.1, FR-4.2)."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._entries: dict[str, CacheEntry[Any]] = {}
        self._lock = asyncio.Lock()
        self.clock: Clock = clock or SystemClock()

    async def get(
        self, key: str, bypass_cache: bool = False
    ) -> tuple[Any | None, bool, str | None]:
        """Retrieve a value from the cache.

        Returns:
            tuple of (value, is_cached, as_of_iso_timestamp).
            If not found, expired, or bypassed, returns (None, False, None).
        """
        if bypass_cache:
            return None, False, None

        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None, False, None

            now = self.clock.monotonic()
            if (now - entry.created_at_mono) > entry.ttl_seconds:
                # Expired: remove and return miss
                del self._entries[key]
                return None, False, None

            return entry.value, True, entry.created_at_iso

    async def set(self, key: str, value: Any, ttl_seconds: float) -> str:
        """Store a value with a specific TTL. Returns ISO as_of timestamp."""
        now_mono = self.clock.monotonic()
        now_iso = datetime.now(UTC).isoformat()

        async with self._lock:
            self._entries[key] = CacheEntry(
                value=value,
                created_at_mono=now_mono,
                created_at_iso=now_iso,
                ttl_seconds=ttl_seconds,
            )
        return now_iso

    async def invalidate(self, key: str) -> None:
        """Explicitly invalidate a cache key."""
        async with self._lock:
            self._entries.pop(key, None)

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._entries.clear()

    async def size(self) -> int:
        """Return the number of entries currently stored."""
        async with self._lock:
            return len(self._entries)
