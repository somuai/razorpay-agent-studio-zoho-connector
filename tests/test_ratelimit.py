"""Unit tests for Rate Limiting, Concurrency Limiting, and Circuit Breaker (FR-3)."""

import asyncio

import pytest

from zoho_inventory_connector.client.errors import CircuitOpenError
from zoho_inventory_connector.ratelimit.circuit_breaker import CircuitBreaker, CircuitState
from zoho_inventory_connector.ratelimit.clock import VirtualClock
from zoho_inventory_connector.ratelimit.metrics import RateLimitMetrics
from zoho_inventory_connector.ratelimit.token_bucket import ConcurrencyLimiter, TokenBucket


@pytest.mark.asyncio
async def test_token_bucket_limits_and_burst_300() -> None:
    """# FR-3 AC: Burst of 300 calls against rate limiter never exceeds budget per rolling minute."""
    clock = VirtualClock()
    bucket = TokenBucket(rate_per_minute=80.0, capacity=80.0, clock=clock)

    # First 80 calls are instantaneous (capacity = 80)
    for _ in range(80):
        waited = await bucket.acquire(1.0)
        assert waited == 0.0

    # Next call must wait
    assert bucket.tokens < 1.0

    # Acquire 220 more calls (total 300)
    total_waited = 0.0
    for _ in range(220):
        waited = await bucket.acquire(1.0)
        total_waited += waited

    # 220 tokens at 80/min (1.333 tokens/sec) requires: 220 * (60 / 80) = 165 seconds
    expected_delay = 220 * (60.0 / 80.0)
    assert abs(total_waited - expected_delay) < 1.0
    # Clock was advanced smoothly in virtual time without hanging tests
    assert clock.monotonic() >= 1000.0 + expected_delay


@pytest.mark.asyncio
async def test_concurrency_semaphore_limit() -> None:
    """# FR-3.2: Verify concurrency limiter strictly enforces max concurrent tasks."""
    limiter = ConcurrencyLimiter(max_concurrency=5)
    active_tasks = 0
    max_active_observed = 0

    async def worker() -> None:
        nonlocal active_tasks, max_active_observed
        async with limiter:
            active_tasks += 1
            if active_tasks > max_active_observed:
                max_active_observed = active_tasks
            await asyncio.sleep(0.01)
            active_tasks -= 1

    await asyncio.gather(*(worker() for _ in range(25)))
    assert max_active_observed <= 5


def test_circuit_breaker_tripping_and_recovery() -> None:
    """# FR-3.5 AC: Breaker opens on code 44/1070 and recovers after cool-down (VirtualClock, zero sleep)."""
    clock = VirtualClock()
    breaker = CircuitBreaker(cooldown_seconds=60.0, clock=clock)

    # Initial state is CLOSED
    assert breaker.state == CircuitState.CLOSED
    breaker.check_state()  # Does not raise

    # Trip breaker
    breaker.trip()
    assert breaker.state == CircuitState.OPEN
    with pytest.raises(CircuitOpenError) as exc_info:
        breaker.check_state()
    assert exc_info.value.cooldown_remaining > 0

    # Advance clock by 30s (still within 60s cooldown)
    clock.advance(30.0)
    with pytest.raises(CircuitOpenError):
        breaker.check_state()

    # Advance clock past cooldown (total 61s)
    clock.advance(31.0)
    # Circuit should transition to half-open and permit check
    assert not breaker.is_open()
    breaker.check_state()

    # Record success to close circuit
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_rate_limit_metrics_telemetry() -> None:
    """# FR-3.6: Verify metrics counters, quota tracking, and percentages."""
    metrics = RateLimitMetrics(daily_quota_limit=1000)

    await metrics.record_call(is_upstream=True)
    await metrics.record_call(is_upstream=True)
    await metrics.record_call(is_upstream=False)  # e.g. cache hit
    await metrics.record_throttled()
    await metrics.record_retry()
    await metrics.record_cache_hit()
    await metrics.record_cache_miss()
    await metrics.record_circuit_trip()

    d = metrics.to_dict()
    assert d["calls_made"] == 3
    assert d["daily_quota_consumed"] == 2
    assert d["quota_consumed_pct"] == 0.2  # 2 / 1000 * 100
    assert d["calls_throttled"] == 1
    assert d["calls_retried"] == 1
    assert d["cache_hits"] == 1
    assert d["cache_misses"] == 1
    assert d["cache_hit_rate_pct"] == 50.0
    assert d["circuit_trips"] == 1
