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
from zoho_inventory_connector.events.logging_safety import redact_text
from zoho_inventory_connector.mcp_server import server


def _summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return only low-risk metadata suitable for a screenshot or terminal capture."""
    if "error" in result:
        summary = {
            "status": "error",
            "error": str(result.get("error", "ConnectorError")),
            "phase": "token_or_auth" if result.get("error") == "AuthError" else "inventory_tool",
            "retryable": bool(result.get("retryable", False)),
        }
        message = result.get("message")
        if result.get("error") == "AuthError" and isinstance(message, str) and message:
            summary["diagnostic"] = redact_text(message)[:400]
        diagnostic = result.get("transport_diagnostic")
        if isinstance(diagnostic, Mapping):
            summary["transport_diagnostic"] = dict(diagnostic)
        return summary

    summary: dict[str, Any] = {"status": "ok"}
    for key in ("count", "page", "has_more", "completeness", "as_of", "cached"):
        if key in result:
            summary[key] = result[key]
    for key in ("items", "sales_orders"):
        if isinstance(result.get(key), list):
            summary["result_count"] = len(result[key])
    return summary


async def _run() -> int:
    required = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_ORG_ID")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("SKIPPED: live Zoho smoke requires " + ", ".join(missing))
        return 0

    token_manager = TokenManager(
        client_id=os.environ["ZOHO_CLIENT_ID"],
        client_secret=os.environ["ZOHO_CLIENT_SECRET"],
        refresh_token=os.environ.get("ZOHO_REFRESH_TOKEN"),
        token_file=os.environ.get("ZOHO_TOKEN_FILE", ".zoho_token.json"),
        dc=os.environ.get("ZOHO_DC", "in"),
        accounts_base_url=os.environ.get("ZOHO_ACCOUNTS_BASE_URL"),
    )
    client = ZohoClient(token_manager=token_manager, org_id=os.environ["ZOHO_ORG_ID"])
    server.set_client(client)

    try:
        await token_manager.get_access_token()
    except Exception as exc:
        failure: dict[str, Any] = {
            "phase": "token_acquisition",
            "status": "error",
            "error": type(exc).__name__,
        }
        message = getattr(exc, "message", None)
        if isinstance(message, str) and message:
            failure["diagnostic"] = redact_text(message)[:400]
        transport = getattr(exc, "transport_diagnostic", None)
        if isinstance(transport, Mapping):
            failure["transport_diagnostic"] = dict(transport)
        print(json.dumps(failure, sort_keys=True))
        print(
            "Live smoke stopped during token acquisition; no Inventory tools were called.",
            file=sys.stderr,
        )
        await client.aclose()
        return 1

    async def run_check(tool_name: str, call: Any) -> tuple[str, Mapping[str, Any]]:
        before = client.metrics.to_dict()
        try:
            result = await call
        except Exception as exc:
            # Do not surface arbitrary upstream or library exception text in captures.
            result = {
                "error": type(exc).__name__,
                "message": getattr(exc, "message", ""),
                "retryable": bool(getattr(exc, "retryable", False)),
                "transport_diagnostic": getattr(exc, "transport_diagnostic", None),
            }
        after = client.metrics.to_dict()
        safe = _summary(result)
        safe["upstream_calls"] = after["calls_made"] - before["calls_made"]
        safe["cache_hits"] = after["cache_hits"] - before["cache_hits"]
        safe["cache"] = "hit" if safe["cache_hits"] else "miss_or_uncached"
        print(json.dumps({"tool": tool_name, **safe}, sort_keys=True))
        return tool_name, result

    # Fixed, harmless test terms avoid printing or asking for customer information.
    checks: list[tuple[str, Mapping[str, Any]]] = []
    item_check = await run_check("list_items", server.list_items(page=1, per_page=5))
    checks.append(item_check)
    if item_check[1].get("error") == "AuthError":
        await client.aclose()
        print(
            "Live smoke stopped after token/auth failure; remaining tools were skipped.",
            file=sys.stderr,
        )
        return 1
    items = item_check[1]
    item_rows = items.get("items", []) if "error" not in items else []
    first_item = item_rows[0] if item_rows else {}
    item_id = str(first_item.get("item_id", "0"))
    item_sku = str(first_item.get("sku", "LIVE-SMOKE-NO-MATCH"))
    item_name = str(first_item.get("name", "LIVE-SMOKE-NO-MATCH"))

    order_check = await run_check("list_sales_orders", server.list_sales_orders(page=1, per_page=5))
    checks.append(order_check)
    if order_check[1].get("error") == "AuthError":
        await client.aclose()
        print(
            "Live smoke stopped after token/auth failure; remaining tools were skipped.",
            file=sys.stderr,
        )
        return 1
    orders = order_check[1]
    order_rows = orders.get("sales_orders", []) if "error" not in orders else []
    first_order = order_rows[0] if order_rows else {}
    order_id = str(first_order.get("salesorder_id", "0"))
    reference = str(first_order.get("reference_number", "LIVE-SMOKE-NO-MATCH"))

    remaining_checks = [
        ("get_item", lambda: server.get_item(item_id)),
        ("search_items", lambda: server.search_items(query=item_name[:80], limit=5)),
        ("get_stock_availability", lambda: server.get_stock_availability([item_sku])),
        ("get_sales_order", lambda: server.get_sales_order(order_id)),
        (
            "search_sales_orders",
            lambda: server.search_sales_orders(reference_number=reference, limit=5),
        ),
        (
            "get_order_fulfillment_evidence",
            lambda: server.get_order_fulfillment_evidence(order_id),
        ),
    ]
    for tool_name, call_factory in remaining_checks:
        check = await run_check(tool_name, call_factory())
        checks.append(check)
        if check[1].get("error") == "AuthError":
            await client.aclose()
            print(
                "Live smoke stopped after token/auth failure; remaining tools were skipped.",
                file=sys.stderr,
            )
            return 1

    await client.aclose()
    errors = sum(1 for _, result in checks if "error" in result)
    if errors:
        print(
            f"Live smoke completed with {errors} tool error(s); inspect Zoho setup and documented data limitations.",
            file=sys.stderr,
        )
        return 1
    print(
        f"Live smoke completed with {client.metrics.calls_made} upstream calls "
        f"and {client.metrics.cache_hits} cache hits. This confirms read access only; "
        "it does not establish merchant impact."
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
