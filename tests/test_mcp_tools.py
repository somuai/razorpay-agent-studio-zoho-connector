"""Integration tests for FastMCP Tools layer (FR-5, FR-6, FR-7)."""

import json

import httpx
import pytest

from mock_zoho.app import app
from mock_zoho.faults import faults
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.client.errors import AuditSinkError, InvalidResponseError
from zoho_inventory_connector.events.audit import AuditEvent, default_audit_logger
from zoho_inventory_connector.events.emitter import default_emitter
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


@pytest.mark.asyncio
async def test_customer_email_resolves_through_contacts() -> None:
    """Email searches resolve an exact contact before fetching that customer's orders."""
    result = await search_sales_orders(customer_email="customer_001@example.com", limit=5)

    assert result["match_basis"] == "contact_email_exact"
    assert result["count"] == 1
    assert result["sales_orders"][0]["customer_email"] == "c***1@example.com"


@pytest.mark.asyncio
async def test_tool_argument_validation_errors_are_actionable() -> None:
    """# FR-5/7/13: Tool-level bounds and required inputs fail without upstream calls."""
    bad_page = await list_items(page=0)
    assert bad_page["error"] == "InputValidationError"
    assert "page" in bad_page["message"]

    too_many_skus = await get_stock_availability([f"SKU{i}" for i in range(21)])
    assert too_many_skus["error"] == "InputValidationError"
    assert "20 items" in too_many_skus["message"]

    missing_order_match = await search_sales_orders()
    assert missing_order_match["error"] == "InputValidationError"
    assert "At least one" in missing_order_match["message"]


@pytest.mark.asyncio
async def test_malformed_upstream_numeric_field_returns_typed_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed stock values become safe tool errors instead of escaping as ValueError."""
    from zoho_inventory_connector.mcp_server import server

    client = server.get_client()

    async def malformed_get(*args: object, **kwargs: object) -> tuple[dict[str, object], bool, str]:
        return (
            {"items": [{"item_id": "item_1", "sku": "SKU-1", "actual_available_stock": "many"}]},
            False,
            "2026-10-01T00:00:00+00:00",
        )

    monkeypatch.setattr(client, "get", malformed_get)
    result = await get_stock_availability(["SKU-1"], bypass_cache=True)
    assert result["error"] == InvalidResponseError.__name__
    assert "actual_available_stock" in result["message"]


@pytest.mark.asyncio
async def test_tool_event_captures_request_local_throttle_and_retries() -> None:
    """# FR-8: Per-tool telemetry includes actual retry and throttle behavior."""
    faults.inject_429_rate_limit = True
    faults.retry_after_seconds = 0.01
    previous_count = len(default_emitter.get_events())

    result = await get_stock_availability(["item_1001"], bypass_cache=True)

    event = default_emitter.get_events()[previous_count]
    assert result["error"] == "RateLimitError"
    assert event.tool == "get_stock_availability"
    assert event.throttled is True
    assert event.retries == 3


@pytest.mark.asyncio
async def test_tool_call_fails_closed_when_audit_sink_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zoho_inventory_connector.mcp_server import server

    client = server.get_client()

    def fail_audit(event: AuditEvent) -> None:
        raise AuditSinkError(event.tool, event.request_id)

    monkeypatch.setattr(default_audit_logger, "record", fail_audit)
    result = await list_items(page=1, per_page=5)

    assert result["error"] == "AuditSinkError"
    assert client.metrics.calls_made == 0
