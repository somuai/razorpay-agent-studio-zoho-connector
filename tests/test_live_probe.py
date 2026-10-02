from __future__ import annotations

import asyncio
from typing import Any

from examples.live_probe import ProbeRunner, render_report, run_probe, shape
from zoho_inventory_connector.client.errors import NotFoundError


class FakeZoho:
    """In-memory GET-only fake; any attempted mutation is impossible by design."""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    async def get(self, endpoint: str, params: dict[str, str] | None = None, **_: Any):
        self.calls.append((endpoint, params))
        key = endpoint
        if key not in self.responses:
            raise NotFoundError(endpoint, "synthetic")
        return self.responses[key], False, "test-time"


def test_shape_reports_only_field_paths_and_json_types() -> None:
    payload = {"item": {"sku": "SECRET-SKU", "stock": None, "locations": [{"name": "SECRET"}]}}
    result = shape(payload)
    assert result == {
        "item": "object",
        "item.sku": "string",
        "item.stock": "null",
        "item.locations": "array",
        "item.locations[]": "object",
        "item.locations[].name": "string",
    }
    assert "SECRET" not in str(result)


def test_probe_is_get_only_and_marks_empty_org_probes_inconclusive() -> None:
    fake = FakeZoho()
    report = asyncio.run(run_probe(fake))
    assert report["call_count"] == len(fake.calls)
    assert fake.calls and all(endpoint.startswith("/") for endpoint, _ in fake.calls)
    assert not any(
        row.get("result") == "CONFIRMED"
        and row.get("finding") not in {"missing-record response code"}
        for row in report["rows"]
    )
    assert any(row.get("result") == "INCONCLUSIVE" for row in report["rows"])
    rendered = render_report(report)
    assert "GET only" in rendered
    assert "synthetic-secret-value" not in rendered


def test_probe_describes_item_and_package_response_shapes_without_values() -> None:
    fake = FakeZoho(
        {
            "/salesorders": {
                "code": 0,
                "salesorders": [
                    {"salesorder_id": "private-order-id", "reference_number": "private-ref"}
                ],
                "page_context": {"has_more_page": False},
            },
            "/items": {
                "code": 0,
                "items": [{"item_id": "private-item-id", "sku": "private-sku"}],
                "page_context": {"has_more_page": False},
            },
            "/items/private-item-id": {
                "code": 0,
                "item": {"locations": [{"location_available_stock": 2}], "stock_on_hand": 3},
            },
            "/packages": {
                "code": 0,
                "packages": [{"package_id": "private-package-id"}],
                "page_context": {"has_more_page": False},
            },
            "/packages/private-package-id": {
                "code": 0,
                "package": {
                    "shipment_order": {
                        "status": "private-status-value",
                        "tracking_number": "private-tracking",
                    }
                },
            },
            "/invoices": {"code": 0, "invoices": []},
        }
    )
    report = asyncio.run(run_probe(fake))
    rendered = render_report(report)
    for secret in (
        "private-order-id",
        "private-ref",
        "private-item-id",
        "private-sku",
        "private-package-id",
        "private-tracking",
        "private-status-value",
    ):
        assert secret not in rendered
    assert "`item.locations[].location_available_stock`: number" in rendered
    assert "`package.shipment_order.status`: string" in rendered
    assert report["call_count"] == len(fake.calls)


def test_probe_error_row_exposes_only_codes_and_status_metadata() -> None:
    runner = ProbeRunner(FakeZoho(), response_meta=[{"status": 404, "retry_after": False}])
    result = asyncio.run(runner.get("missing", "/items/999999999999999999999999999999"))
    assert result is None
    assert runner.rows[0]["http_status"] == 404
    assert runner.rows[0]["shape"] == {}
    assert "999999999999999999999999999999" not in render_report(
        {"call_count": 1, "rows": runner.rows}
    )
