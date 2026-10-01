"""Tests for ZohoClient GET-only surface and error handling (FR-2)."""

import httpx
import pytest

from mock_zoho.app import app
from mock_zoho.faults import faults
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.client.errors import (
    AuthError,
    NotFoundError,
    QuotaExhaustedError,
    UpstreamError,
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
