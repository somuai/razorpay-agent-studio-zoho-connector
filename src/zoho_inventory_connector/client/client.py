"""GET-only resilient Zoho Inventory HTTP client (FR-2, FR-3, FR-4).

Enforces strictly read-only operations, token bucket rate limits, concurrency semaphores,
exponential backoff, circuit breaking, proactive token refresh, and caching.
"""

import random
from datetime import UTC, datetime
from typing import Any

import httpx

from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.cache.ttl_cache import TTLCache
from zoho_inventory_connector.client.errors import (
    AuthError,
    CircuitOpenError,
    NotFoundError,
    QuotaExhaustedError,
    RateLimitError,
    UpstreamError,
)
from zoho_inventory_connector.client.transport_diagnostics import (
    is_connect_phase_failure,
    request_with_connect_retries,
    transport_diagnostic,
    zoho_connect_attempts,
    zoho_http_timeout,
)
from zoho_inventory_connector.ratelimit.circuit_breaker import CircuitBreaker
from zoho_inventory_connector.ratelimit.clock import Clock, SystemClock
from zoho_inventory_connector.ratelimit.metrics import RateLimitMetrics
from zoho_inventory_connector.ratelimit.token_bucket import ConcurrencyLimiter, TokenBucket


class ZohoClient:
    """Resilient, GET-only HTTP client for Zoho Inventory."""

    def __init__(
        self,
        token_manager: TokenManager,
        org_id: str,
        rate_limiter: TokenBucket | None = None,
        concurrency_limiter: ConcurrencyLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        cache: TTLCache | None = None,
        metrics: RateLimitMetrics | None = None,
        clock: Clock | None = None,
        http_client: httpx.AsyncClient | None = None,
        max_retries: int = 3,
        base_url_override: str | None = None,
    ) -> None:
        self.token_manager = token_manager
        self.org_id = org_id
        self.clock: Clock = clock or SystemClock()
        self.rate_limiter: TokenBucket = rate_limiter or TokenBucket(
            rate_per_minute=80.0, clock=self.clock
        )
        self.concurrency_limiter: ConcurrencyLimiter = concurrency_limiter or ConcurrencyLimiter(
            max_concurrency=5
        )
        self.circuit_breaker: CircuitBreaker = circuit_breaker or CircuitBreaker(
            cooldown_seconds=60.0, clock=self.clock
        )
        self.cache: TTLCache = cache or TTLCache(clock=self.clock)
        self.metrics: RateLimitMetrics = metrics or RateLimitMetrics()
        self.max_retries = max_retries
        self.max_connect_attempts = zoho_connect_attempts()
        self.base_url_override = base_url_override
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=zoho_http_timeout())

    def _resolve_base_url(self) -> str:
        if self.base_url_override:
            return self.base_url_override.rstrip("/")
        return self.token_manager.get_api_base_url()

    async def aclose(self) -> None:
        """Close the HTTP client only when this client created it."""
        if self._owns_http_client:
            await self._http_client.aclose()

    async def get(
        self,
        endpoint: str,
        params: dict[str, str] | None = None,
        cache_ttl: float = 0.0,
        bypass_cache: bool = False,
    ) -> tuple[dict[str, Any], bool, str]:
        """Execute a resilient GET request against Zoho Inventory (FR-2.1).

        Returns:
            tuple of (data_dict, is_cached, as_of_iso_timestamp)
        """
        clean_endpoint = endpoint.lstrip("/")
        base_url = self._resolve_base_url()
        full_url = f"{base_url}/{clean_endpoint}"

        # 1. Check Cache (FR-4)
        cache_key = f"{full_url}?{sorted((params or {}).items())}"
        if cache_ttl > 0 and not bypass_cache:
            cached_val, is_cached, as_of = await self.cache.get(cache_key, bypass_cache=False)
            if is_cached and cached_val is not None:
                await self.metrics.record_cache_hit()
                return cached_val, True, as_of or datetime.now(UTC).isoformat()
            await self.metrics.record_cache_miss()

        # 2. Check Circuit Breaker (FR-3.5)
        self.circuit_breaker.check_state()

        # Build request parameters
        req_params = dict(params or {})
        req_params["organization_id"] = self.org_id

        attempt = 0
        refreshed_auth_on_401 = False

        while attempt <= self.max_retries:
            attempt += 1

            # 4. Concurrency Limit (FR-3.2)
            async with self.concurrency_limiter:
                access_token = await self.token_manager.get_access_token()
                headers = {
                    "Authorization": f"Zoho-oauthtoken {access_token}",
                    "Accept": "application/json",
                }

                async def before_connect_attempt() -> None:
                    waited = await self.rate_limiter.acquire(1.0)
                    if waited > 0:
                        await self.metrics.record_throttled()
                    await self.metrics.record_call(is_upstream=True)

                async def record_connect_retry() -> None:
                    await self.metrics.record_retry()

                async def send_get(
                    request_url: str = full_url,
                    request_params: dict[str, str] = req_params,
                    request_headers: dict[str, str] = headers,
                ) -> httpx.Response:
                    return await self._http_client.get(
                        request_url, params=request_params, headers=request_headers
                    )

                try:
                    res = await request_with_connect_retries(
                        send_get,
                        full_url,
                        attempts=self.max_connect_attempts,
                        before_attempt=before_connect_attempt,
                        on_retry=record_connect_retry,
                    )
                except (httpx.TransportError, httpx.TimeoutException) as err:
                    diagnostic = transport_diagnostic(err, full_url, attempt)
                    phase = str(diagnostic["phase"])
                    count = diagnostic.get("attempt_count", 1)
                    if not is_connect_phase_failure(err) and attempt <= self.max_retries:
                        await self.metrics.record_retry()
                        delay = random.uniform(0.0, min(8.0, (2 ** (attempt - 1)) * 0.5))
                        await self.clock.sleep(delay)
                        continue
                    raise UpstreamError(
                        f"Network error (transport failure) contacting Zoho Inventory after "
                        f"{count} attempt(s), phase={phase}; not a credential error.",
                        http_status=None,
                        transport_diagnostic=diagnostic,
                    ) from err

            # 5. Evaluate HTTP & Body Responses
            # A) 401 Unauthorized (FR-2.3)
            if res.status_code == 401:
                if not refreshed_auth_on_401:
                    refreshed_auth_on_401 = True
                    await self.token_manager.get_access_token(force_refresh=True)
                    continue
                raise AuthError(
                    message="Zoho authentication failed after token refresh retry.",
                    http_status=401,
                )

            # Parse JSON body if present
            content_type = res.headers.get("content-type", "")
            body: dict[str, Any] = {}
            if "application/json" in content_type:
                try:
                    body = res.json()
                except Exception:
                    body = {}

            zoho_code = body.get("code")

            # B) Daily Quota Exceeded - Code 45 (FR-3.4) -> ZERO RETRIES
            if zoho_code == 45:
                raise QuotaExhaustedError()

            # C) Org Blocked - Code 44 (FR-3.5) -> Trip Breaker
            if zoho_code == 44:
                self.circuit_breaker.trip(cooldown_seconds=60.0)
                await self.metrics.record_circuit_trip()
                raise CircuitOpenError(cooldown_remaining=60.0, zoho_code=44)

            # D) Concurrency Limit - Code 1070 (FR-3.5)
            if zoho_code == 1070:
                self.circuit_breaker.trip(cooldown_seconds=15.0)
                await self.metrics.record_circuit_trip()
                raise RateLimitError(kind="concurrency", retry_after=15.0, zoho_code=1070)

            # E) HTTP 429 Rate Limit (FR-3.3)
            if res.status_code == 429:
                await self.metrics.record_throttled()
                if attempt > self.max_retries:
                    raise RateLimitError(
                        kind="per_minute",
                        retry_after=min(60.0, float(res.headers.get("Retry-After", "2")))
                        if res.headers.get("Retry-After", "2").replace(".", "", 1).isdigit()
                        else 2.0,
                    )
                retry_header = res.headers.get("Retry-After")
                if retry_header and retry_header.replace(".", "", 1).isdigit():
                    delay = min(60.0, max(0.0, float(retry_header)))
                else:
                    delay = random.uniform(0.0, min(10.0, 2 ** (attempt - 1)))

                await self.metrics.record_retry()
                await self.clock.sleep(delay)
                continue

            # F) 404 Not Found (FR-2.2)
            if res.status_code == 404 or zoho_code in (1002, 1003):
                # Do not include query parameters: they contain the organization ID.
                raise NotFoundError(resource=clean_endpoint.split("/", 1)[0], identifier="[masked]")

            # G) 5xx Server Error (FR-2.4)
            if res.status_code >= 500:
                if attempt > self.max_retries:
                    raise UpstreamError(
                        f"Zoho Inventory returned server error {res.status_code}.",
                        http_status=res.status_code,
                    )
                await self.metrics.record_retry()
                delay = random.uniform(0.0, min(8.0, 2 ** (attempt - 1)))
                await self.clock.sleep(delay)
                continue

            # H) Success (200 OK)
            if res.status_code == 200:
                self.circuit_breaker.record_success()
                now_iso = datetime.now(UTC).isoformat()
                if cache_ttl > 0:
                    as_of_saved = await self.cache.set(cache_key, body, ttl_seconds=cache_ttl)
                    return body, False, as_of_saved
                return body, False, now_iso

            # Unhandled status
            raise UpstreamError(
                message=f"Zoho Inventory returned unexpected HTTP status {res.status_code}.",
                http_status=res.status_code,
            )

        raise UpstreamError("Maximum retries exhausted contacting Zoho Inventory.")
