"""Integration tests for Mock Zoho Server (FR-9)."""

import httpx
import pytest

from mock_zoho.app import MOCK_ACCESS_TOKEN, app
from mock_zoho.faults import faults


@pytest.fixture(autouse=True)
def reset_mock_faults() -> None:
    faults.reset()


@pytest.mark.asyncio
async def test_mock_oauth_auth_redirect() -> None:
    """# FR-9, FR-1.1: Verify OAuth auth consent redirect with state and code."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/oauth/v2/auth",
            params={
                "client_id": "client_123",
                "redirect_uri": "http://localhost:8080/callback",
                "state": "csrf_token_abc",
                "response_type": "code",
            },
            follow_redirects=False,
        )
        assert res.status_code == 302
        location = res.headers["location"]
        assert "code=mock_auth_grant_code_xyz" in location
        assert "state=csrf_token_abc" in location


@pytest.mark.asyncio
async def test_mock_oauth_token_exchange_and_refresh() -> None:
    """# FR-9, FR-1.1, FR-1.2: Verify token exchange and refresh flows."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Authorization code exchange
        token_res = await client.post(
            "/oauth/v2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": "client_123",
                "client_secret": "secret_456",
                "code": "mock_auth_grant_code_xyz",
                "redirect_uri": "http://localhost:8080/callback",
            },
        )
        assert token_res.status_code == 200
        data = token_res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 3600
        assert "api_domain" in data

        # Refresh token flow
        refresh_res = await client.post(
            "/oauth/v2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": "client_123",
                "client_secret": "secret_456",
                "refresh_token": data["refresh_token"],
            },
        )
        assert refresh_res.status_code == 200
        ref_data = refresh_res.json()
        assert "access_token" in ref_data

        # Invalid grant rejection
        invalid_res = await client.post(
            "/oauth/v2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": "client_123",
                "client_secret": "secret_456",
                "refresh_token": "invalid_token",
            },
        )
        assert invalid_res.status_code == 400
        assert invalid_res.json()["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_mock_items_pagination_and_search() -> None:
    """# FR-9: Verify items listing, pagination, and search."""
    headers = {"Authorization": f"Zoho-oauthtoken {MOCK_ACCESS_TOKEN}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Page 1
        res = await client.get(
            "/inventory/v1/items", params={"page": 1, "per_page": 10}, headers=headers
        )
        assert res.status_code == 200
        data = res.json()
        assert data["code"] == 0
        assert len(data["items"]) == 10
        assert data["page_context"]["has_more_page"] is True

        # Search by SKU
        search_res = await client.get(
            "/inventory/v1/items",
            params={"search_text": "KHG-CUSH-001"},
            headers=headers,
        )
        assert search_res.status_code == 200
        search_data = search_res.json()
        assert len(search_data["items"]) == 1
        assert search_data["items"][0]["sku"] == "KHG-CUSH-001"


@pytest.mark.asyncio
async def test_mock_item_detail_and_404() -> None:
    """# FR-9: Verify item detail retrieval and 404 for missing items."""
    headers = {"Authorization": f"Zoho-oauthtoken {MOCK_ACCESS_TOKEN}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/inventory/v1/items/item_1001", headers=headers)
        assert res.status_code == 200
        assert res.json()["item"]["item_id"] == "item_1001"

        missing_res = await client.get("/inventory/v1/items/item_9999", headers=headers)
        assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_mock_sales_orders_and_sub_resources() -> None:
    """# FR-9: Verify sales orders, packages, shipments, and invoices."""
    headers = {"Authorization": f"Zoho-oauthtoken {MOCK_ACCESS_TOKEN}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get(
            "/inventory/v1/salesorders", params={"page": 1, "per_page": 20}, headers=headers
        )
        assert res.status_code == 200
        orders = res.json()["salesorders"]
        assert len(orders) == 20

        # Detailed order
        so_id = orders[0]["salesorder_id"]
        detail_res = await client.get(f"/inventory/v1/salesorders/{so_id}", headers=headers)
        assert detail_res.status_code == 200
        detail = detail_res.json()["salesorder"]
        assert "packages" in detail
        assert "shipments" in detail
        assert "invoices" in detail


@pytest.mark.asyncio
async def test_mock_fault_injections() -> None:
    """# FR-9: Verify simulated fault modes."""
    headers = {"Authorization": f"Zoho-oauthtoken {MOCK_ACCESS_TOKEN}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Expired token (401)
        faults.inject_401_expired_token = True
        r = await client.get("/inventory/v1/items", headers=headers)
        assert r.status_code == 401
        assert r.json()["code"] == 57
        faults.reset()

        # 2. Rate limit (429 with Retry-After)
        faults.inject_429_rate_limit = True
        faults.retry_after_seconds = 5
        r = await client.get("/inventory/v1/items", headers=headers)
        assert r.status_code == 429
        assert r.headers.get("retry-after") == "5"
        faults.reset()

        # 3. Code 44 Org Block
        faults.inject_code_44_block = True
        r = await client.get("/inventory/v1/items", headers=headers)
        assert r.status_code == 429
        assert r.json()["code"] == 44
        faults.reset()

        # 4. Code 45 Daily Quota Exhausted
        faults.inject_code_45_quota_exhausted = True
        r = await client.get("/inventory/v1/items", headers=headers)
        assert r.status_code == 429
        assert r.json()["code"] == 45
        faults.reset()

        # 5. Code 1070 Concurrency Exceeded
        faults.inject_code_1070_concurrency = True
        r = await client.get("/inventory/v1/items", headers=headers)
        assert r.status_code == 429
        assert r.json()["code"] == 1070
        faults.reset()

        # 6. Server error 500
        faults.inject_500_server_error = True
        r = await client.get("/inventory/v1/items", headers=headers)
        assert r.status_code == 500
        faults.reset()
