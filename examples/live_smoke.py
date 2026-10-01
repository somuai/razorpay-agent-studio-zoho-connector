"""Masked read-only smoke check against a configured Zoho Inventory organization."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from typing import Any

from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.mcp_server import server


def _summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return only low-risk metadata suitable for a screenshot or terminal capture."""
    if "error" in result:
        return {
            "status": "error",
            "error": str(result.get("error", "ConnectorError")),
            "retryable": bool(result.get("retryable", False)),
        }

    summary: dict[str, Any] = {"status": "ok"}
    for key in ("count", "page", "has_more", "completeness", "match_basis", "as_of", "cached"):
        if key in result:
            summary[key] = result[key]
    for key in ("items", "sales_orders"):
        if isinstance(result.get(key), list):
            summary["result_count"] = len(result[key])
    return summary


async def _run() -> int:
    required = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN", "ZOHO_ORG_ID")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("SKIPPED: live Zoho smoke requires " + ", ".join(missing))
        return 0

    token_manager = TokenManager(
        client_id=os.environ["ZOHO_CLIENT_ID"],
        client_secret=os.environ["ZOHO_CLIENT_SECRET"],
        refresh_token=os.environ["ZOHO_REFRESH_TOKEN"],
        token_file=os.environ.get("ZOHO_TOKEN_FILE", ".zoho_token.json"),
        dc=os.environ.get("ZOHO_DC", "in"),
        accounts_base_url=os.environ.get("ZOHO_ACCOUNTS_BASE_URL"),
    )
    client = ZohoClient(token_manager=token_manager, org_id=os.environ["ZOHO_ORG_ID"])
    server.set_client(client)

    # Fixed, harmless test terms avoid printing or asking for customer information.
    items = await server.list_items(page=1, per_page=5)
    item_rows = items.get("items", []) if "error" not in items else []
    first_item = item_rows[0] if item_rows else {}
    item_id = str(first_item.get("item_id", "0"))
    item_sku = str(first_item.get("sku", "LIVE-SMOKE-NO-MATCH"))
    item_name = str(first_item.get("name", "LIVE-SMOKE-NO-MATCH"))

    orders = await server.list_sales_orders(page=1, per_page=5)
    order_rows = orders.get("sales_orders", []) if "error" not in orders else []
    first_order = order_rows[0] if order_rows else {}
    order_id = str(first_order.get("salesorder_id", "0"))
    reference = str(first_order.get("reference_number", "LIVE-SMOKE-NO-MATCH"))

    checks: list[tuple[str, Mapping[str, Any]]] = [
        ("list_items", items),
        ("get_item", await server.get_item(item_id)),
        ("search_items", await server.search_items(query=item_name[:80], limit=5)),
        ("get_stock_availability", await server.get_stock_availability([item_sku])),
        ("list_sales_orders", orders),
        ("get_sales_order", await server.get_sales_order(order_id)),
        (
            "search_sales_orders",
            await server.search_sales_orders(reference_number=reference, limit=5),
        ),
        ("get_order_fulfillment_evidence", await server.get_order_fulfillment_evidence(order_id)),
    ]

    for tool_name, result in checks:
        print(json.dumps({"tool": tool_name, **_summary(result)}, sort_keys=True))

    await client.aclose()
    errors = sum(1 for _, result in checks if "error" in result)
    if errors:
        print(
            f"Live smoke completed with {errors} tool error(s); inspect Zoho setup and documented data limitations.",
            file=sys.stderr,
        )
        return 1
    print(
        "Live smoke completed. This confirms read access only; it does not establish merchant impact."
    )
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_run()))
    except KeyboardInterrupt:
        print("Live smoke interrupted.", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
