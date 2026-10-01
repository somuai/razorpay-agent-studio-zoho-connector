"""Unit tests for StockService and DisputeService (FR-5.2, FR-5.3, FR-5.4)."""

import httpx
import pytest

from mock_zoho.app import app
from mock_zoho.faults import faults
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.models.evidence import EvidenceCompleteness
from zoho_inventory_connector.models.item import StockStatus
from zoho_inventory_connector.ratelimit.clock import VirtualClock
from zoho_inventory_connector.services.dispute_service import DisputeService
from zoho_inventory_connector.services.stock_service import StockService


@pytest.fixture(autouse=True)
def reset_faults() -> None:
    faults.reset()


@pytest.fixture
def mock_client() -> ZohoClient:
    clock = VirtualClock()
    http_c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    tm = TokenManager("client_id", "secret", "refresh_token", clock=clock, http_client=http_c)
    tm._access_token = "zoho_access_mock_token_12345"
    tm._expires_at_mono = clock.monotonic() + 3600
    return ZohoClient(
        token_manager=tm,
        org_id="org_kaveri_blr_001",
        clock=clock,
        http_client=http_c,
        base_url_override="http://test/inventory/v1",
    )


@pytest.mark.asyncio
async def test_stock_availability_derivation(mock_client: ZohoClient) -> None:
    """# FR-5.2: Verify stock status derivation across in-stock, low-stock, and out-of-stock items."""
    service = StockService(mock_client, default_low_stock_threshold=5.0)

    # 1. In-stock item (item_1001)
    res_in = await service.get_stock_availability(["item_1001"])
    assert len(res_in.items) == 1
    assert res_in.items[0].status == StockStatus.IN_STOCK
    assert res_in.items[0].quantity_sellable > 5.0
    assert res_in.items[0].source_stock_field == "actual_available_stock"
    assert res_in.items[0].as_of is not None
    assert len(res_in.items[0].warehouses) >= 1

    # 2. Low-stock item (item_1011)
    res_low = await service.get_stock_availability(["item_1011"])
    assert len(res_low.items) == 1
    assert res_low.items[0].status == StockStatus.LOW_STOCK
    assert 0 < res_low.items[0].quantity_sellable <= 5.0

    # 3. Out-of-stock item (item_1019)
    res_out = await service.get_stock_availability(["item_1019"])
    assert len(res_out.items) == 1
    assert res_out.items[0].status == StockStatus.OUT_OF_STOCK
    assert res_out.items[0].quantity_sellable == 0.0

    # 4. Unknown SKU
    res_unknown = await service.get_stock_availability(["UNKNOWN-NONEXISTENT-SKU"])
    assert len(res_unknown.items) == 1
    assert res_unknown.items[0].status == StockStatus.UNKNOWN


@pytest.mark.asyncio
async def test_fulfillment_evidence_composition(mock_client: ZohoClient) -> None:
    """# FR-5.4: Verify complete vs partial dispute fulfillment evidence without guessing."""
    dispute_service = DisputeService(mock_client)

    # 1. Complete evidence order (so_2001 is fulfilled with tracking & delivery)
    ev_complete = await dispute_service.get_order_fulfillment_evidence("so_2001")
    assert ev_complete.completeness == EvidenceCompleteness.COMPLETE
    assert ev_complete.missing_fields == []
    assert ev_complete.sales_order.status == "present"
    assert ev_complete.invoice.status == "present"
    assert ev_complete.package.status == "present"
    assert ev_complete.carrier.status == "present"
    assert ev_complete.tracking_number.status == "present"
    assert ev_complete.delivery_date.status == "present"
    assert "fulfilled successfully" in ev_complete.fulfillment_summary

    # 2. Partial fulfillment order (so_2035 is partial without tracking / delivery date)
    ev_partial = await dispute_service.get_order_fulfillment_evidence("so_2035")
    assert ev_partial.completeness == EvidenceCompleteness.PARTIAL
    assert "tracking_number" in ev_partial.missing_fields
    assert "delivery_date" in ev_partial.missing_fields
    assert ev_partial.tracking_number.status == "not_available"
    assert ev_partial.delivery_date.status == "not_available"
    assert "partial fulfillment proof" in ev_partial.fulfillment_summary

    # 3. Nonexistent order
    ev_none = await dispute_service.get_order_fulfillment_evidence("so_9999")
    assert ev_none.completeness == EvidenceCompleteness.NONE
    assert "does not exist" in ev_none.fulfillment_summary
