"""Tests for ZohoClient GET-only surface and error handling (FR-2)."""

import httpx
import pytest

from mock_zoho.app import app
from mock_zoho.faults import faults
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.client.errors import (
    AuthError,
    CircuitOpenError,
    NotFoundError,
    QuotaExhaustedError,
    RateLimitError,
    UpstreamError,
)
from zoho_inventory_connector.client.transport_diagnostics import (
    transport_diagnostic,
    zoho_connect_attempts,
    zoho_http_timeout,
)
from zoho_inventory_connector.ratelimit.clock import VirtualClock


@pytest.fixture(autouse=True)
def reset_faults() -> None:
    faults.reset()


def test_strictly_get_only_interface() -> None:
    """# FR-2 AC: Assert no HTTP method other than GET is ever exposed on ZohoClient."""
    clock = VirtualClock()
    tm = TokenManager("client_id", "secret", "refresh_token", clock=clock)
    client = ZohoClient(token_manager=tm, org_id="org_123", clock=clock)

    assert hasattr(client, "get")
    assert not hasattr(client, "post")
    assert not hasattr(client, "put")
    assert not hasattr(client, "delete")
    assert not hasattr(client, "patch")


@pytest.mark.asyncio
async def test_401_refresh_and_retry_once() -> None:
    """# FR-2.3: On 401, client refreshes token once and retries once."""
    clock = VirtualClock()
    refresh_count = 0

    async def mock_refresh(*args, **kwargs) -> dict[str, object]:
        nonlocal refresh_count
        refresh_count += 1
        return {
            "access_token": "zoho_access_mock_token_12345",
            "expires_in": 3600,
            "api_domain": "http://test",
        }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_c:
        tm = TokenManager(
            client_id="client_id",
            client_secret="secret",
            refresh_token="ref_token",
            clock=clock,
            http_client=http_c,
        )
        tm._access_token = "invalid_old_token"
        tm._expires_at_mono = clock.monotonic() + 3600

        # Replace refresh method on tm
        from zoho_inventory_connector.auth import token_manager

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(token_manager, "refresh_access_token", mock_refresh)

        client = ZohoClient(
            token_manager=tm,
            org_id="org_kaveri_blr_001",
            clock=clock,
            http_client=http_c,
            base_url_override="http://test/inventory/v1",
        )

        data, is_cached, as_of = await client.get("/items")
        assert data["code"] == 0
        assert refresh_count == 1
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_401_fails_after_retry() -> None:
    """# FR-2.3: If token refresh still yields 401, raises AuthError."""
    clock = VirtualClock()
    faults.inject_401_expired_token = True

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_c:
        tm = TokenManager(
            client_id="client_id",
            client_secret="secret",
            refresh_token="ref_token",
            clock=clock,
            http_client=http_c,
        )
        client = ZohoClient(
            token_manager=tm,
            org_id="org_kaveri_blr_001",
            clock=clock,
            http_client=http_c,
            base_url_override="http://test/inventory/v1",
        )

        with pytest.raises(AuthError):
            await client.get("/items")


@pytest.mark.asyncio
async def test_code_45_quota_exhausted_zero_retry() -> None:
    """# FR-3.4: Zoho code 45 raises QuotaExhaustedError without retry."""
    clock = VirtualClock()
    faults.inject_code_45_quota_exhausted = True

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_c:
        tm = TokenManager(
            client_id="client_id",
            client_secret="secret",
            refresh_token="ref_token",
            clock=clock,
            http_client=http_c,
        )
        tm._access_token = "zoho_access_mock_token_12345"
        tm._expires_at_mono = clock.monotonic() + 3600

        client = ZohoClient(
            token_manager=tm,
            org_id="org_kaveri_blr_001",
            clock=clock,
            http_client=http_c,
            base_url_override="http://test/inventory/v1",
        )

        with pytest.raises(QuotaExhaustedError):
            await client.get("/items")

        # Zero retries must be recorded
        assert client.metrics.calls_retried == 0


@pytest.mark.asyncio
async def test_404_not_found() -> None:
    """# FR-2.2: 404 raises NotFoundError."""
    clock = VirtualClock()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_c:
        tm = TokenManager(
            client_id="client_id",
            client_secret="secret",
            refresh_token="ref_token",
            clock=clock,
            http_client=http_c,
        )
        tm._access_token = "zoho_access_mock_token_12345"
        tm._expires_at_mono = clock.monotonic() + 3600

        client = ZohoClient(
            token_manager=tm,
            org_id="org_kaveri_blr_001",
            clock=clock,
            http_client=http_c,
            base_url_override="http://test/inventory/v1",
        )

        with pytest.raises(NotFoundError):
            await client.get("/items/item_nonexistent_9999")


@pytest.mark.asyncio
async def test_5xx_bounded_retries() -> None:
    """# FR-2.4: 5xx server errors retry up to max_retries with exponential backoff then raise UpstreamError."""
    clock = VirtualClock()
    faults.inject_500_server_error = True

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_c:
        tm = TokenManager(
            client_id="client_id",
            client_secret="secret",
            refresh_token="ref_token",
            clock=clock,
            http_client=http_c,
        )
        tm._access_token = "zoho_access_mock_token_12345"
        tm._expires_at_mono = clock.monotonic() + 3600

        client = ZohoClient(
            token_manager=tm,
            org_id="org_kaveri_blr_001",
            clock=clock,
            http_client=http_c,
            max_retries=2,
            base_url_override="http://test/inventory/v1",
        )

        with pytest.raises(UpstreamError):
            await client.get("/items")

        # Retried max_retries times
        assert client.metrics.calls_retried == 2


def test_zoho_timeout_uses_five_second_connect_budget() -> None:
    timeout = zoho_http_timeout()
    assert timeout.connect == 5.0
    assert timeout.read == 15.0
    assert timeout.write == 15.0
    assert timeout.pool == 5.0


@pytest.mark.asyncio
async def test_inventory_connect_retries_replay_identical_request() -> None:
    """Only connect failures retry, with the organization and auth request unchanged."""
    clock = VirtualClock()
    requests: list[tuple[str, str, tuple[tuple[str, str], ...], str]] = []
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        requests.append(
            (
                request.method,
                str(request.url),
                tuple(request.url.params.multi_items()),
                request.headers.get("authorization", ""),
            )
        )
        if attempts < 4:
            raise httpx.ConnectTimeout("offline test failure", request=request)
        return httpx.Response(200, json={"code": 0, "items": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        token_manager = TokenManager("mock-client", "mock-secret", "mock-refresh", clock=clock)
        token_manager._access_token = "mock-access"
        token_manager._expires_at_mono = clock.monotonic() + 3600
        client = ZohoClient(
            token_manager=token_manager,
            org_id="mock-org-12345678",
            clock=clock,
            http_client=http_client,
            base_url_override="https://inventory.example/inventory/v1",
        )
        body, cached, _as_of = await client.get("items", params={"page": "1"})

    assert body["code"] == 0
    assert cached is False
    assert attempts == 4
    assert len(set(requests)) == 1
    method, url, params, authorization = requests[0]
    assert method == "GET"
    assert (
        url
        == "https://inventory.example/inventory/v1/items?page=1&organization_id=mock-org-12345678"
    )
    assert params == (("page", "1"), ("organization_id", "mock-org-12345678"))
    assert authorization == "Zoho-oauthtoken mock-access"
    assert client.metrics.calls_retried == 3


@pytest.mark.asyncio
async def test_inventory_connect_failures_stop_after_four_attempts() -> None:
    clock = VirtualClock()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectTimeout("private transport text", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        token_manager = TokenManager("mock-client", "mock-secret", "mock-refresh", clock=clock)
        token_manager._access_token = "mock-access"
        token_manager._expires_at_mono = clock.monotonic() + 3600
        client = ZohoClient(
            token_manager=token_manager,
            org_id="mock-org",
            clock=clock,
            http_client=http_client,
            max_retries=9,
            base_url_override="https://inventory.example/inventory/v1",
        )
        with pytest.raises(UpstreamError) as exc_info:
            await client.get("items", params={"page": "1"})

    diagnostic = exc_info.value.transport_diagnostic
    assert attempts == 4
    assert diagnostic is not None
    assert diagnostic["attempt_count"] == 4
    assert diagnostic["max_attempts"] == 4
    assert diagnostic["phase"] == "connect"
    assert "after 4 attempt(s)" in str(exc_info.value)
    assert "private transport text" not in str(exc_info.value)


def test_connect_attempt_setting_has_four_attempt_default_and_validated_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZOHO_CONNECT_RETRIES", raising=False)
    assert zoho_connect_attempts() == 4
    monkeypatch.setenv("ZOHO_CONNECT_RETRIES", "2")
    assert zoho_connect_attempts() == 2
    monkeypatch.setenv("ZOHO_CONNECT_RETRIES", "0")
    with pytest.raises(ValueError, match="ZOHO_CONNECT_RETRIES"):
        zoho_connect_attempts()


@pytest.mark.asyncio
async def test_429_honors_retry_after_and_stops_after_bound() -> None:
    """# FR-3.3: Respect Retry-After without real sleeping and bound retries."""
    clock = VirtualClock()
    started_at = clock.monotonic()
    faults.inject_429_rate_limit = True
    faults.retry_after_seconds = 4

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_c:
        tm = TokenManager("client_id", "secret", "refresh", clock=clock, http_client=http_c)
        tm._access_token = "zoho_access_mock_token_12345"
        tm._expires_at_mono = clock.monotonic() + 3600
        client = ZohoClient(
            token_manager=tm,
            org_id="org_kaveri_blr_001",
            clock=clock,
            http_client=http_c,
            max_retries=1,
            base_url_override="http://test/inventory/v1",
        )
        with pytest.raises(RateLimitError) as exc_info:
            await client.get("/items")

    assert exc_info.value.kind == "per_minute"
    assert clock.monotonic() - started_at == 4
    assert client.metrics.calls_retried == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fault_name", "error_type"),
    [("inject_code_44_block", CircuitOpenError), ("inject_code_1070_concurrency", RateLimitError)],
)
async def test_org_block_and_concurrency_codes_fail_fast(
    fault_name: str, error_type: type[Exception]
) -> None:
    """# FR-3.5: Org blocks trip the breaker and concurrency faults request lower parallelism."""
    clock = VirtualClock()
    setattr(faults, fault_name, True)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_c:
        tm = TokenManager("client_id", "secret", "refresh", clock=clock, http_client=http_c)
        tm._access_token = "zoho_access_mock_token_12345"
        tm._expires_at_mono = clock.monotonic() + 3600
        client = ZohoClient(
            token_manager=tm,
            org_id="org_kaveri_blr_001",
            clock=clock,
            http_client=http_c,
            base_url_override="http://test/inventory/v1",
        )
        with pytest.raises(error_type):
            await client.get("/items")
        if fault_name == "inject_code_44_block":
            with pytest.raises(CircuitOpenError):
                await client.get("/items")


@pytest.mark.asyncio
async def test_transport_error_retries_then_maps_to_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """# FR-2.4: Network failures use bounded retry and become a typed error."""
    monkeypatch.setenv("ZOHO_CONNECT_RETRIES", "2")
    clock = VirtualClock()
    attempts = 0

    def fail_request(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail_request)) as http_c:
        tm = TokenManager("client_id", "secret", "refresh", clock=clock, http_client=http_c)
        tm._access_token = "access"
        tm._expires_at_mono = clock.monotonic() + 3600
        client = ZohoClient(
            token_manager=tm,
            org_id="org",
            clock=clock,
            http_client=http_c,
            max_retries=1,
            base_url_override="https://inventory.invalid",
        )
        with pytest.raises(UpstreamError, match="Network error") as exc_info:
            await client.get("/items")

    assert attempts == 2
    assert client.metrics.calls_retried == 1
    assert exc_info.value.transport_diagnostic == {
        "exception_class": "ConnectError",
        "cause_classes": [],
        "phase": "connect",
        "host": "inventory.invalid",
        "attempt": 2,
        "attempt_count": 2,
        "max_attempts": 2,
        "attempts": [
            {"attempt": 1, "phase": "connect"},
            {"attempt": 2, "phase": "connect"},
        ],
        "proxy_env_names": [],
        "network_context_hint": (
            "Network connection failed (not a credential error). If this is running inside a "
            "sandboxed agent or CI, outbound network may be blocked; run the command from a normal terminal."
        ),
    }


def test_transport_diagnostic_reports_safe_cause_phase_host_attempt_and_proxy_names() -> None:
    request = httpx.Request("GET", "https://api.example.invalid/items/123456789012345")
    cause = OSError("private socket detail")
    error = httpx.ConnectError("private URL and identifier", request=request)
    error.__cause__ = cause
    diagnostic = transport_diagnostic(
        error,
        str(request.url),
        attempt=3,
        environ={"HTTPS_PROXY": "secret-proxy-value", "NO_PROXY": "private-value"},
    )
    assert diagnostic == {
        "exception_class": "ConnectError",
        "cause_classes": ["OSError"],
        "phase": "connect",
        "host": "api.example.invalid",
        "attempt": 3,
        "attempt_count": 3,
        "attempts": [{"attempt": 3, "phase": "connect"}],
        "proxy_env_names": ["HTTPS_PROXY", "NO_PROXY"],
        "network_context_hint": (
            "Network connection failed (not a credential error). If this is running inside a "
            "sandboxed agent or CI, outbound network may be blocked; run the command from a normal terminal."
        ),
    }
    assert "secret-proxy-value" not in str(diagnostic)
    assert "123456789012345" not in str(diagnostic)


@pytest.mark.asyncio
async def test_unexpected_http_status_maps_to_upstream_error() -> None:
    clock = VirtualClock()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(418, text="unexpected")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_c:
        tm = TokenManager("client_id", "secret", "refresh", clock=clock, http_client=http_c)
        tm._access_token = "access"
        tm._expires_at_mono = clock.monotonic() + 3600
        client = ZohoClient(
            token_manager=tm,
            org_id="org",
            clock=clock,
            http_client=http_c,
            base_url_override="https://inventory.invalid",
        )
        with pytest.raises(UpstreamError) as exc_info:
            await client.get("/items")
    assert exc_info.value.http_status == 418
