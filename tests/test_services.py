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

    # A substring search result is not an exact SKU match; never borrow its stock.
    res_partial_match = await service.get_stock_availability(["KHG-CUSH-00"])
    assert res_partial_match.items[0].status == StockStatus.UNKNOWN
    assert res_partial_match.items[0].item_id == "unknown"


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


@pytest.mark.asyncio
async def test_stock_schema_drift_preserves_unknown_and_accepts_numeric_strings(
    mock_client: ZohoClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing/null/malformed stock does not become a false out-of-stock decision."""
    payloads = {
        "item_1": {"item_id": "item_1", "sku": "KHG-001", "actual_available_stock": "7"},
        "item_2": {"item_id": "item_2", "sku": "KHG-002", "actual_available_stock": None},
        "item_3": {"item_id": "item_3", "sku": "KHG-003", "stock_on_hand": "bad"},
        "item_4": {
            "item_id": "item_4",
            "sku": "KHG-004",
            "locations": [{"location_actual_available_stock": "2"}],
        },
    }

    async def changed_schema_get(
        endpoint: str, **kwargs: object
    ) -> tuple[dict[str, object], bool, str]:
        item_id = endpoint.rsplit("/", 1)[-1]
        return (
            {"item": payloads[item_id], "unexpected_extra": "ignored"},
            False,
            "2026-10-02T00:00:00+00:00",
        )

    monkeypatch.setattr(mock_client, "get", changed_schema_get)
    service = StockService(mock_client)

    in_stock = (await service.get_stock_availability(["item_1"])).items[0]
    null_stock = (await service.get_stock_availability(["item_2"])).items[0]
    malformed = (await service.get_stock_availability(["item_3"])).items[0]
    one_location = (await service.get_stock_availability(["item_4"])).items[0]

    assert in_stock.status == StockStatus.IN_STOCK
    assert in_stock.quantity_sellable == 7.0
    assert null_stock.status == StockStatus.UNKNOWN
    assert "usable available-stock" in (null_stock.availability_note or "")
    assert malformed.status == StockStatus.UNKNOWN
    assert one_location.status == StockStatus.LOW_STOCK
    assert one_location.quantity_sellable == 2.0


@pytest.mark.asyncio
async def test_dispute_service_reads_nested_package_shipment_not_undocumented_list(
    mock_client: ZohoClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def package_detail_get(
        endpoint: str, **_kwargs: object
    ) -> tuple[dict[str, object], bool, str]:
        calls.append(endpoint)
        if endpoint == "/salesorders/12345":
            return (
                {
                    "salesorder": {
                        "salesorder_id": "12345",
                        "salesorder_number": "SO-TEST-12345",
                        "status": "fulfilled",
                        "date": "2026-10-02",
                        "invoices": [{"invoice_number": "INV-TEST"}],
                        "packages": [{"package_id": "98765", "package_number": "PKG-TEST"}],
                    }
                },
                False,
                "2026-10-02T00:00:00+00:00",
            )
        if endpoint == "/packages/98765":
            return (
                {
                    "package": {
                        "package_id": "98765",
                        "shipment_order": {
                            "status": "shipped",
                            "carrier": "Synthetic Carrier",
                            "tracking_number": "FAKE-TRACKING",
                        },
                    }
                },
                False,
                "2026-10-02T00:00:00+00:00",
            )
        raise AssertionError(f"Unexpected endpoint {endpoint}")

    monkeypatch.setattr(mock_client, "get", package_detail_get)
    result = await DisputeService(mock_client).get_order_fulfillment_evidence("12345")
    assert result.carrier.status == "present"
    assert result.tracking_number.status == "present"
    assert result.delivery_date.status == "not_available"
    assert "/shipmentorders" not in calls
    assert "/packages/98765" in calls


@pytest.mark.asyncio
async def test_dispute_service_ignores_packages_for_other_orders(
    mock_client: ZohoClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A package-list filter may return a global page; unrelated rows are not evidence."""
    calls: list[str] = []

    async def cross_order_package_page(
        endpoint: str, **kwargs: object
    ) -> tuple[dict[str, object], bool, str]:
        calls.append(endpoint)
        if endpoint == "/salesorders/12345":
            return (
                {"salesorder": {"salesorder_id": "12345", "salesorder_number": "SO-TARGET"}},
                False,
                "2026-10-03T00:00:00+00:00",
            )
        if endpoint == "/invoices":
            return ({"invoices": []}, False, "2026-10-03T00:00:00+00:00")
        if endpoint == "/packages":
            assert kwargs.get("params") == {"salesorder_id": "12345"}
            return (
                {
                    "packages": [
                        {"package_id": "99999", "salesorder_id": "54321"},
                        {"package_id": "98765", "salesorder_id": "12345"},
                    ]
                },
                False,
                "2026-10-03T00:00:00+00:00",
            )
        if endpoint == "/packages/98765":
            return (
                {
                    "package": {
                        "package_id": "98765",
                        "shipment_order": {
                            "status": "shipped",
                            "carrier": "Synthetic Carrier",
                            "tracking_number": "FAKE-TRACKING",
                        },
                    }
                },
                False,
                "2026-10-03T00:00:00+00:00",
            )
        raise AssertionError(f"Unexpected endpoint {endpoint}")

    monkeypatch.setattr(mock_client, "get", cross_order_package_page)
    result = await DisputeService(mock_client).get_order_fulfillment_evidence("12345")

    assert result.package.status == "present"
    assert result.carrier.status == "present"
    assert result.tracking_number.status == "present"
    assert "/packages/99999" not in calls
    assert "/packages/98765" in calls


@pytest.mark.asyncio
async def test_dispute_service_reads_live_shipment_field_aliases(
    mock_client: ZohoClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sparse nested shipment triggers detail lookup and Zoho field aliases are normalized."""

    async def sparse_embedded_shipment(
        endpoint: str, **_kwargs: object
    ) -> tuple[dict[str, object], bool, str]:
        stamp = "2026-10-03T00:00:00+00:00"
        if endpoint == "/salesorders/12345":
            return (
                {
                    "salesorder": {
                        "salesorder_id": "12345",
                        "salesorder_number": "SO-TARGET",
                        "packages": [{"package_id": "98765", "shipment_order": {}}],
                    }
                },
                False,
                stamp,
            )
        if endpoint == "/invoices":
            return ({"invoices": []}, False, stamp)
        if endpoint == "/packages/98765":
            return (
                {
                    "package": {
                        "shipment_order": {
                            "status": "shipped",
                            "carrier": "Synthetic Carrier",
                            "tracking_number": "FAKE-TRACKING",
                            "shipping_date": "2026-10-02",
                            "shipment_delivered_date": "2026-10-03",
                        }
                    }
                },
                False,
                stamp,
            )
        raise AssertionError(f"Unexpected endpoint {endpoint}")

    monkeypatch.setattr(mock_client, "get", sparse_embedded_shipment)
    result = await DisputeService(mock_client).get_order_fulfillment_evidence("12345")

    assert result.shipment_date.status == "present"
    assert result.shipment_date.value == "2026-10-02"
    assert result.delivery_date.status == "present"
    assert result.delivery_date.value == "2026-10-03"
    assert result.delivery_status.value == "shipped"
