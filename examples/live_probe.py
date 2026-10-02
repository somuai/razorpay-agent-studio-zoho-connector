"""Read-only, shape-only probes for Zoho API facts currently marked UNVERIFIED.

This module is inert without credentials. It never issues POST/PUT/PATCH/DELETE
requests and its report deliberately contains field names and JSON types only.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.client.errors import ConnectorError

OUTPUT = Path("docs/LIVE_FINDINGS.md")

READ_ONLY_UNRESOLVED = (
    (
        "OAuth grant lifetime discrepancy",
        "No timed 60-second/2-minute expiry experiment is performed; the code is exchanged promptly.",
    ),
    (
        "PKCE support and Self Client equivalence to the loopback app",
        "The GET-only API probe does not test authorization request parameters or alternate OAuth app types.",
    ),
    (
        "Whether the merchant integration stores a Razorpay payment ID in reference_number",
        "Synthetic reference filtering tests Zoho search behavior only; it cannot prove the merchant's upstream field mapping.",
    ),
    (
        "Customer-email-to-sales-order matching",
        "No deliberately created, unique test contact email is supplied to this probe; inspect only after adding one to the throwaway org.",
    ),
    (
        "Package-number and sales-order-number package filter semantics",
        "This probe reads package pages/details to inspect shipment embedding but does not test the ambiguous package search filters.",
    ),
    (
        "Which availability field is truly sellable for the merchant",
        "Field names and types can be observed, but sellability depends on reservations, channel policy, and location allocation.",
    ),
    (
        "Daily quota reset timing and guaranteed Retry-After behavior",
        "The probe does not exhaust quota or deliberately induce throttling; a naturally observed header is reported separately.",
    ),
    (
        "Free-plan availability for this account",
        "A Premium-trial dashboard observation does not test free-plan eligibility for the separate personal throwaway account.",
    ),
    (
        "Item create route and minimum accepted item payload",
        "Requires an Inventory item write; intentionally not tested because this probe is GET-only.",
    ),
    (
        "Contact-person requirement for sales-order creation",
        "Requires a controlled sales-order write; intentionally not tested because this probe is GET-only.",
    ),
    (
        "Minimum accepted sales-order line-item payload",
        "Requires a controlled sales-order write; intentionally not tested because this probe is GET-only.",
    ),
    (
        "Whether shipment creation automatically sets shipped status",
        "Requires a shipment write/state transition; intentionally not tested because this probe is GET-only.",
    ),
    (
        "Seeder idempotency under repeated writes",
        "Requires repeated Inventory writes; intentionally not tested because this probe is GET-only.",
    ),
)


def shape(value: Any, prefix: str = "") -> dict[str, str]:
    """Describe nested JSON structure without including any payload values."""
    result: dict[str, str] = {}
    if isinstance(value, Mapping):
        if prefix:
            result[prefix] = "object"
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            result.update(shape(child, path))
    elif isinstance(value, list):
        result[prefix] = "array"
        if value:
            result.update(shape(value[0], prefix + "[]"))
    else:
        result[prefix] = _json_type(value)
    return result


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "unknown"


def _safe_route(endpoint: str) -> str:
    """Keep resource path shape while removing record IDs and query values."""
    parts = endpoint.split("?", 1)[0].strip("/").split("/")
    if not parts or not parts[0]:
        return "/"
    return f"/{parts[0]}/{{record_id}}" if len(parts) > 1 else f"/{parts[0]}"


class ProbeRunner:
    """Collect response shapes and status metadata through the read-only client."""

    def __init__(self, client: Any, response_meta: list[dict[str, Any]] | None = None) -> None:
        self.client = client
        self.response_meta = response_meta if response_meta is not None else []
        self.calls = 0
        self.rows: list[dict[str, Any]] = []

    async def get(
        self, label: str, endpoint: str, params: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        self.calls += 1
        before = len(self.response_meta)
        try:
            body, _cached, _as_of = await self.client.get(
                endpoint, params=params, bypass_cache=True
            )
        except ConnectorError as exc:
            meta = self.response_meta[before:]
            row = {
                "test": label,
                "status": "error",
                "result": "CONFIRMED" if meta else "INCONCLUSIVE",
                "tested": f"GET {_safe_route(endpoint)} with bounded query parameters; response values omitted.",
                "http_status": meta[-1].get("status") if meta else exc.http_status,
                "zoho_code": exc.zoho_code,
                "retry_after_seen": any(item.get("retry_after") for item in meta),
                "shape": {},
            }
            self.rows.append(row)
            return None
        meta = self.response_meta[before:]
        row = {
            "test": label,
            "status": "ok",
            "result": "CONFIRMED",
            "tested": f"GET {_safe_route(endpoint)} with bounded query parameters; response values omitted.",
            "http_status": meta[-1].get("status") if meta else 200,
            "zoho_code": body.get("code") if isinstance(body, dict) else None,
            "retry_after_seen": any(item.get("retry_after") for item in meta),
            "shape": shape(body),
        }
        self.rows.append(row)
        return body


def _first_resource(body: dict[str, Any] | None, *keys: str) -> dict[str, Any] | None:
    if not body:
        return None
    for key in keys:
        value = body.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    return None


def _accepted(body: dict[str, Any] | None) -> bool:
    """Zoho often returns API failures inside an HTTP 200 response body."""
    return body is not None and body.get("code", 0) in (0, "0", None)


def _resource_rows(body: dict[str, Any] | None, *keys: str) -> list[dict[str, Any]]:
    if body:
        for key in keys:
            rows = body.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _record_result(
    runner: ProbeRunner,
    test: str,
    observed: str,
    result: str,
    doc: str,
    tested: str = "Read-only GET; see the named probe and shape row above.",
) -> None:
    runner.rows.append(
        {
            "finding": test,
            "result": result,
            "tested": tested,
            "observed": observed,
            "update": doc,
        }
    )


async def run_probe(
    client: Any, response_meta: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Probe documented uncertainty; output only response shapes and enum labels."""
    runner = ProbeRunner(client, response_meta)

    # Test the disputed list-all behavior first, then a bounded page for shape data.
    page_orders = await runner.get(
        "salesorders_first_page", "/salesorders", {"page": "1", "per_page": "1"}
    )
    _record_result(
        runner,
        "GET /salesorders without salesorder_ids",
        "request accepted" if _accepted(page_orders) else "request rejected or unavailable",
        "CONFIRMED"
        if _accepted(page_orders)
        else ("CONTRADICTED" if page_orders is not None else "INCONCLUSIVE"),
        "docs/API_NOTES.md",
    )
    # Filter probes run independently of list-all support, so they still test the
    # recovery path if GET /salesorders without IDs is rejected.
    reference = await runner.get(
        "salesorders_reference_number_filter",
        "/salesorders",
        {"reference_number": "RZP-TEST-001", "page": "1", "per_page": "1"},
    )
    reference_match = any(
        row.get("reference_number") == "RZP-TEST-001"
        for row in _resource_rows(reference, "salesorders", "sales_orders")
    )
    search_text = await runner.get(
        "salesorders_search_text_filter",
        "/salesorders",
        {"search_text": "RZP-TEST-001", "page": "1", "per_page": "1"},
    )
    search_match = any(
        row.get("reference_number") == "RZP-TEST-001"
        for row in _resource_rows(search_text, "salesorders", "sales_orders")
    )
    status_filter = await runner.get(
        "salesorders_status_filter",
        "/salesorders",
        {"status": "confirmed", "page": "1", "per_page": "1"},
    )
    for label, body, matched in (
        ("sales-order reference_number filter", reference, reference_match),
        ("sales-order search_text for reference", search_text, search_match),
    ):
        _record_result(
            runner,
            label,
            "matching test reference returned"
            if matched
            else "request accepted but no matching test reference returned",
            "CONFIRMED" if matched else ("INCONCLUSIVE" if _accepted(body) else "CONTRADICTED"),
            "docs/API_NOTES.md",
        )
    _record_result(
        runner,
        "sales-order status filter",
        "request accepted" if _accepted(status_filter) else "request rejected or unavailable",
        "CONFIRMED"
        if _accepted(status_filter)
        else ("CONTRADICTED" if status_filter is not None else "INCONCLUSIVE"),
        "docs/API_NOTES.md",
    )

    # Item list filter probes use synthetic terms and do not print submitted values.
    item_list = await runner.get("items_first_page", "/items", {"page": "1", "per_page": "1"})
    item = _first_resource(item_list, "items")
    for label, params in (
        ("items_search_text", {"search_text": "KHG-001", "page": "1", "per_page": "1"}),
        ("items_filter_by", {"filter_by": "Status.Active", "page": "1", "per_page": "1"}),
        ("items_sku", {"sku": "KHG-001", "page": "1", "per_page": "1"}),
    ):
        body = await runner.get(label, "/items", params)
        test_sku = params.get("sku") or params.get("search_text")
        rows = _resource_rows(body, "items")
        semantic_match = any(row.get("sku") == test_sku for row in rows) if test_sku else bool(rows)
        observed = (
            "matching test item returned"
            if semantic_match
            else (
                "request accepted; no matching test item returned"
                if _accepted(body)
                else "request rejected or unavailable"
            )
        )
        status = (
            "CONFIRMED"
            if semantic_match
            else (
                "INCONCLUSIVE"
                if _accepted(body)
                else ("CONTRADICTED" if body is not None else "INCONCLUSIVE")
            )
        )
        _record_result(runner, label, observed, status, "docs/API_NOTES.md")

    if item and item.get("item_id") is not None:
        detail = await runner.get("item_detail", f"/items/{item['item_id']}")
        detail_item = detail.get("item") if isinstance(detail, dict) else None
        if isinstance(detail_item, dict):
            stock_fields = [
                key
                for key in (
                    "stock_on_hand",
                    "location_available_stock",
                    "location_actual_available_stock",
                )
                if key in detail_item
            ]
            locations = detail_item.get("locations")
            if isinstance(locations, list) and locations and isinstance(locations[0], dict):
                stock_fields.extend(
                    key
                    for key in (
                        "location_stock_on_hand",
                        "location_available_stock",
                        "location_actual_available_stock",
                    )
                    if key in locations[0] and key not in stock_fields
                )
            observed = (
                "stock fields: "
                + (", ".join(f"`{key}`" for key in stock_fields) or "none present")
                + "; locations array: "
                + ("present" if isinstance(locations, list) else "absent")
            )
            _record_result(
                runner, "stock fields and locations", observed, "CONFIRMED", "docs/API_NOTES.md"
            )
        else:
            _record_result(
                runner,
                "stock fields and locations",
                "item detail unavailable",
                "INCONCLUSIVE",
                "docs/API_NOTES.md",
            )
    else:
        _record_result(
            runner,
            "stock fields and locations",
            "no item record available for detail probe",
            "INCONCLUSIVE",
            "docs/API_NOTES.md",
        )

    page_context = page_orders.get("page_context") if isinstance(page_orders, dict) else None
    max_page = await runner.get(
        "salesorders_per_page_limit", "/salesorders", {"page": "1", "per_page": "200"}
    )
    over_limit_page = await runner.get(
        "salesorders_per_page_over_limit", "/salesorders", {"page": "1", "per_page": "201"}
    )
    page_two = await runner.get(
        "salesorders_second_page", "/salesorders", {"page": "2", "per_page": "1"}
    )
    _record_result(
        runner,
        "sales-order pagination and per_page limit",
        (
            (
                "page_context shape observed; per_page=200 accepted; page 2 request "
                + ("accepted" if _accepted(page_two) else "rejected or unavailable")
                + "; per_page=201 "
                + ("accepted" if _accepted(over_limit_page) else "rejected")
            )
            if _accepted(max_page)
            else "per_page=200 rejected; page 2 was also probed"
        )
        if isinstance(page_context, dict)
        else "no page_context in available response",
        "CONFIRMED"
        if isinstance(page_context, dict) and _accepted(max_page) and _accepted(page_two)
        else (
            "CONTRADICTED" if max_page is not None and not _accepted(max_page) else "INCONCLUSIVE"
        ),
        "docs/API_NOTES.md",
    )

    packages = await runner.get("packages_first_page", "/packages", {"page": "1", "per_page": "10"})
    package_rows = _resource_rows(packages, "packages")
    embedded: dict[str, Any] | None = None
    for package in package_rows[:10]:
        package_id = package.get("package_id")
        if package_id is None:
            continue
        package_detail = await runner.get("package_detail", f"/packages/{package_id}")
        value = (
            package_detail.get("package", {}).get("shipment_order")
            if isinstance(package_detail, dict)
            else None
        )
        if isinstance(value, dict):
            embedded = value
            break
    if package_rows:
        _record_result(
            runner,
            "package detail embeds shipment_order",
            "shipment_order object present"
            if isinstance(embedded, dict)
            else "shipment_order object absent",
            "CONFIRMED" if embedded is not None else "INCONCLUSIVE",
            "docs/API_NOTES.md",
        )
        shipment_fields = (
            [
                key
                for key in (
                    "status",
                    "carrier",
                    "tracking_number",
                    "delivered_at",
                    "delivered_date",
                    "delivery_date",
                )
                if key in embedded
            ]
            if embedded is not None
            else []
        )
        observed_fields = (
            ", ".join(f"`{key}`" for key in shipment_fields) or "none of the named fields present"
        )
        delivered = (
            any(key in embedded for key in ("delivered_at", "delivered_date", "delivery_date"))
            if embedded is not None
            else False
        )
        core_fields = ("status", "carrier", "tracking_number")
        missing_core = [key for key in core_fields if embedded is None or key not in embedded]
        _record_result(
            runner,
            "shipment status/carrier/tracking_number fields",
            f"fields observed in this record: {observed_fields}; missing core fields: "
            f"{', '.join(missing_core) if missing_core else 'none'}",
            "CONFIRMED"
            if embedded is not None and not missing_core
            else ("CONTRADICTED" if embedded is not None else "INCONCLUSIVE"),
            "docs/API_NOTES.md",
        )
        _record_result(
            runner,
            "delivered-at timestamp on observed shipment",
            "delivered-at equivalent present in this record"
            if delivered
            else "no delivered-at equivalent in this record; this does not prove schema-wide absence",
            "CONTRADICTED" if delivered else "INCONCLUSIVE",
            "docs/API_NOTES.md",
        )
    else:
        _record_result(
            runner,
            "package/shipment relationship and shipment fields",
            "no package record available for detail probe",
            "INCONCLUSIVE",
            "docs/API_NOTES.md",
        )

    await runner.get("invoices_first_page", "/invoices", {"page": "1", "per_page": "1"})
    # A deliberately impossible identifier tests observed missing-record behavior.
    await runner.get("missing_item_record", "/items/999999999999999999999999999999")
    missing_probe = next(
        (row for row in reversed(runner.rows) if row.get("test") == "missing_item_record"), {}
    )
    _record_result(
        runner,
        "missing-record response code",
        f"HTTP {missing_probe.get('http_status') or 'unknown'}; Zoho code {missing_probe.get('zoho_code') or 'not returned'}",
        "CONFIRMED"
        if missing_probe.get("http_status") is not None
        or missing_probe.get("zoho_code") is not None
        else "INCONCLUSIVE",
        "docs/API_NOTES.md",
    )
    saw_retry_after = any(item.get("retry_after") for item in runner.response_meta)
    _record_result(
        runner,
        "Retry-After response header",
        "header observed"
        if saw_retry_after
        else "not observed on these requests; no throttling was induced",
        "CONFIRMED" if saw_retry_after else "INCONCLUSIVE",
        "docs/API_NOTES.md",
    )
    for claim, limitation in READ_ONLY_UNRESOLVED:
        _record_result(
            runner,
            claim,
            limitation,
            "INCONCLUSIVE",
            "docs/API_NOTES.md",
            tested="Not testable by this bounded GET-only probe; no unsupported behavior is inferred.",
        )

    metrics = getattr(client, "metrics", None)
    if metrics is not None and hasattr(metrics, "to_dict"):
        observed_calls = int(metrics.to_dict().get("calls_made", 0))
    else:
        observed_calls = len(runner.response_meta) or runner.calls
    return {"call_count": observed_calls, "rows": runner.rows}


def render_report(report: dict[str, Any]) -> str:
    """Render findings without any record values, IDs, or response bodies."""
    lines = [
        "# Zoho live API findings",
        "",
        "> Generated by `make live-probe`. This file is evidence only when generated against the authorized throwaway org. Values, identifiers, and record contents are intentionally excluded; shapes contain field paths and JSON types only.",
        "",
        f"Calls issued: {int(report.get('call_count', 0))} (GET only).",
        "",
        "| Claim / probe | Result | How tested | Observed response shape / note | Update |",
        "|---|---|---|---|---|",
    ]
    for row in report.get("rows", []):
        label = row.get("finding", row.get("test", "probe"))
        result = row.get("result", row.get("status", "INCONCLUSIVE"))
        if "shape" in row:
            fields = (
                ", ".join(f"`{key}`: {value}" for key, value in row["shape"].items())
                or "no fields observed"
            )
            note = f"HTTP {row.get('http_status') or 'unknown'}; {fields}; Retry-After: {'yes' if row.get('retry_after_seen') else 'not observed'}"
            if row.get("zoho_code") is not None:
                note += f"; Zoho code {row['zoho_code']}"
        else:
            note = str(row.get("observed", "no observation"))
        tested = row.get("tested", "Read-only GET; response values are omitted.")
        update = row.get("update", "docs/API_NOTES.md")
        lines.append(f"| {label} | {result} | {tested} | {note} | {update} |")
    if not report.get("rows"):
        lines.extend(["", "No live findings are populated until a credentialed run completes.", ""])
    return "\n".join(lines)


async def _run() -> int:
    required = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_ORG_ID")
    if any(not os.environ.get(key) for key in required):
        print("SKIPPED: live probe requires Zoho credentials; no network calls were made.")
        return 0
    meta: list[dict[str, Any]] = []

    async def capture(response: httpx.Response) -> None:
        meta.append(
            {"status": response.status_code, "retry_after": "Retry-After" in response.headers}
        )

    http = httpx.AsyncClient(timeout=15.0, event_hooks={"response": [capture]})
    manager = TokenManager(
        client_id=os.environ["ZOHO_CLIENT_ID"],
        client_secret=os.environ["ZOHO_CLIENT_SECRET"],
        refresh_token=os.environ.get("ZOHO_REFRESH_TOKEN"),
        token_file=os.environ.get("ZOHO_TOKEN_FILE", ".zoho_token.json"),
        dc=os.environ.get("ZOHO_DC", "in"),
    )
    client = ZohoClient(manager, os.environ["ZOHO_ORG_ID"], http_client=http)
    try:
        report = await run_probe(client, meta)
        OUTPUT.write_text(render_report(report), encoding="utf-8")
        print(
            f"Live probe finished: {report['call_count']} GET calls. Findings written to {OUTPUT}."
        )
        print("Response values and identifiers were not written.")
        return 0
    finally:
        await client.aclose()
        await http.aclose()


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_run()))
    except KeyboardInterrupt:
        print("Live probe interrupted.")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
