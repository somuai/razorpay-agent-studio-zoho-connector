"""Unit tests for TTL Cache and staleness telemetry (FR-4)."""

import pytest

from zoho_inventory_connector.cache.ttl_cache import TTLCache
from zoho_inventory_connector.ratelimit.clock import VirtualClock


@pytest.mark.asyncio
async def test_cache_hit_and_expiration() -> None:
    """# FR-4.1, FR-4.2: Verify TTL cache storage, retrieval, and expiration."""
    clock = VirtualClock()
    cache = TTLCache(clock=clock)

    # Store entry with 60s TTL
    as_of = await cache.set("item_101", {"sku": "KHG-001", "stock": 10}, ttl_seconds=60.0)
    assert as_of is not None
    assert await cache.size() == 1

    # Immediate retrieval -> Cache hit
    val, is_cached, entry_as_of = await cache.get("item_101")
    assert is_cached is True
    assert val == {"sku": "KHG-001", "stock": 10}
    assert entry_as_of == as_of

    # Advance clock by 30s (still within 60s TTL)
    clock.advance(30.0)
    val2, is_cached2, _ = await cache.get("item_101")
    assert is_cached2 is True

    # Advance clock past 60s TTL
    clock.advance(31.0)
    val3, is_cached3, _ = await cache.get("item_101")
    assert is_cached3 is False
    assert val3 is None


@pytest.mark.asyncio
async def test_bypass_cache_flag() -> None:
    """# FR-4.1: bypass_cache flag forces fresh fetch even when entry is within TTL."""
    clock = VirtualClock()
    cache = TTLCache(clock=clock)

    await cache.set("stock_KHG", {"qty": 5}, ttl_seconds=60.0)

    # Retrieval with bypass_cache=True returns miss
    val, is_cached, _ = await cache.get("stock_KHG", bypass_cache=True)
    assert is_cached is False
    assert val is None

    # Retrieval with bypass_cache=False returns cached
    val2, is_cached2, _ = await cache.get("stock_KHG", bypass_cache=False)
    assert is_cached2 is True
    assert val2 == {"qty": 5}


@pytest.mark.asyncio
async def test_cache_invalidation_and_clear() -> None:
    clock = VirtualClock()
    cache = TTLCache(clock=clock)

    await cache.set("k1", "v1", ttl_seconds=60.0)
    await cache.set("k2", "v2", ttl_seconds=60.0)
    assert await cache.size() == 2

    await cache.invalidate("k1")
    assert await cache.size() == 1
    val, is_cached, _ = await cache.get("k1")
    assert is_cached is False

    await cache.clear()
    assert await cache.size() == 0
