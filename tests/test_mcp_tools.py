"""Integration tests for FastMCP Tools layer (FR-5, FR-6, FR-7)."""

import json

import httpx
import pytest

from mock_zoho.app import app
from mock_zoho.faults import faults
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.mcp_server.server import (
    MAX_OUTPUT_BYTES,
    _enforce_output_cap,
    get_item,
    get_order_fulfillment_evidence,
    get_sales_order,
    get_stock_availability,
    list_items,
    list_sales_orders,
    search_items,
    search_sales_orders,
    set_client,
)
from zoho_inventory_connector.ratelimit.clock import VirtualClock


@pytest.fixture(autouse=True)
def setup_mcp_test_client() -> None:
    faults.reset()
    clock = VirtualClock()
    http_c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    tm = TokenManager("client_id", "secret", "refresh_token", clock=clock, http_client=http_c)
    tm._access_token = "zoho_access_mock_token_12345"
    tm._expires_at_mono = clock.monotonic() + 3600
    client = ZohoClient(
        token_manager=tm,
        org_id="org_kaveri_blr_001",
        clock=clock,
        http_client=http_c,
        base_url_override="http://test/inventory/v1",
    )
    set_client(client)


@pytest.mark.asyncio
async def test_all_8_mcp_tools_execution() -> None:
    """# FR-5: Verify all 8 FastMCP tools execute successfully."""
    # 1. list_items
    r1 = await list_items(page=1, per_page=5)
    assert "items" in r1
    assert len(r1["items"]) == 5

    # 2. get_item
    r2 = await get_item("item_1001")
    assert r2["item_id"] == "item_1001"
    assert "actual_available_stock" in r2

    # 3. search_items
    r3 = await search_items(query="Brass", limit=5)
    assert "items" in r3
    assert len(r3["items"]) >= 1

    # 4. get_stock_availability (Cart primitive)
    r4 = await get_stock_availability(["item_1001", "item_1011", "item_1019"])
    assert "items" in r4
    assert len(r4["items"]) == 3
    statuses = {it["sku"]: it["status"] for it in r4["items"]}
    assert "in_stock" in statuses.values()
    assert "low_stock" in statuses.values()
    assert "out_of_stock" in statuses.values()

    # 5. list_sales_orders
    r5 = await list_sales_orders(page=1, per_page=5)
    assert "sales_orders" in r5
    assert len(r5["sales_orders"]) == 5

    # 6. get_sales_order
    r6 = await get_sales_order("so_2001")
    assert r6["salesorder_id"] == "so_2001"
    assert "customer_name" in r6

    # 7. search_sales_orders
    r7 = await search_sales_orders(reference_number="order_RzpKav1001")
    assert "sales_orders" in r7
    assert len(r7["sales_orders"]) >= 1
    assert r7["match_basis"] == "reference_number_exact"

    # 8. get_order_fulfillment_evidence (Dispute primitive)
    r8 = await get_order_fulfillment_evidence("so_2001")
    assert r8["completeness"] == "complete"
    assert "fulfillment_summary" in r8


def test_output_capping_enforcement() -> None:
    """# FR-6.2: Assert responses exceeding 8 KB are truncated with instructions."""
    huge_list = [{"id": f"item_{i}", "data": "x" * 100} for i in range(200)]
    payload = {"items": huge_list, "count": 200}

    capped = _enforce_output_cap(payload, list_key="items")
    serialized = json.dumps(capped, ensure_ascii=False)

    assert len(serialized.encode("utf-8")) <= MAX_OUTPUT_BYTES
    assert capped["truncated"] is True
    assert "Narrow your query parameters" in capped["truncation_guidance"]


@pytest.mark.asyncio
async def test_agent_error_messages() -> None:
    """# FR-7: Verify tool errors return actionable agent guidance instead of crash or stack trace."""
    # 1. Quota exhausted
    faults.inject_code_45_quota_exhausted = True
    r_quota = await get_stock_availability(["item_1001"])
    assert r_quota["error"] == "QuotaExhaustedError"
    assert "Do not retry today" in r_quota["agent_guidance"]
    assert r_quota["retryable"] is False
    faults.reset()

    # 2. Input validation failure (injection attempt)
    r_inj = await search_items(query="item'; DROP TABLE--")
    assert r_inj["error"] == "InputValidationError"
    assert "prohibited characters" in r_inj["agent_guidance"]
    assert r_inj["retryable"] is False
