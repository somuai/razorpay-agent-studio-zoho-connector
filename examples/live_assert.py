"""Compare hand-entered live Zoho data with expected connector outputs (read-only)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.mcp_server import server

EXPECTED_PATH = Path("live_expected.yaml")


def load_expected(path: Path = EXPECTED_PATH) -> dict[str, Any]:
    """Load JSON-compatible YAML to avoid a runtime YAML dependency."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(
            f"{path} is missing; copy live_expected.example.yaml to live_expected.yaml and edit it."
        ) from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{path} must use the JSON-compatible YAML syntax shown in live_expected.example.yaml."
        ) from error
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("items"), list)
        or not isinstance(data.get("orders"), list)
    ):
        raise ValueError("Expected config must contain 'items' and 'orders' lists.")
    return data


def _configured_client() -> ZohoClient:
    required = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_ORG_ID")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise ValueError("Missing required Zoho environment settings: " + ", ".join(missing))
    manager = TokenManager(
        client_id=os.environ["ZOHO_CLIENT_ID"],
        client_secret=os.environ["ZOHO_CLIENT_SECRET"],
        refresh_token=os.environ.get("ZOHO_REFRESH_TOKEN"),
        token_file=os.environ.get("ZOHO_TOKEN_FILE", ".zoho_token.json"),
        dc=os.environ.get("ZOHO_DC", "in"),
        accounts_base_url=os.environ.get("ZOHO_ACCOUNTS_BASE_URL"),
    )
    return ZohoClient(
        token_manager=manager,
        org_id=os.environ["ZOHO_ORG_ID"],
        base_url_override=os.environ.get("ZOHO_API_BASE_URL"),
    )


def compare_expected(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Compare only declared checks and return readable mismatch descriptions."""
    diffs: list[str] = []
    for key, wanted in expected.items():
        got = actual.get(key)
        if key == "missing_fields":
            got, wanted = sorted(got or []), sorted(wanted or [])
        if got != wanted:
            diffs.append(f"{key}: expected {wanted!r}, got {got!r}")
    return diffs


async def run(expected: dict[str, Any]) -> int:
    client = _configured_client()
    server.set_client(client)
    failed = 0
    try:
        for row in expected["items"]:
            sku = str(row["sku"])
            result = await server.get_stock_availability([sku], bypass_cache=True)
            actual = {}
            if "error" not in result and result.get("items"):
                actual = {"status": result["items"][0].get("status")}
            diffs = compare_expected(actual, row.get("expect", {}))
            print(
                f"{'FAIL' if diffs else 'PASS'} item {sku[-3:]}"
                + (": " + "; ".join(diffs) if diffs else "")
            )
            failed += bool(diffs)

        for row in expected["orders"]:
            ref = str(row["reference_number"])
            search = await server.search_sales_orders(reference_number=ref, limit=5)
            orders = search.get("sales_orders", []) if "error" not in search else []
            if len(orders) != 1:
                actual = {"found": False}
            else:
                order_id = str(orders[0].get("salesorder_id", ""))
                evidence = await server.get_order_fulfillment_evidence(order_id)
                actual = {
                    "found": "error" not in evidence,
                    "completeness": evidence.get("completeness"),
                    "missing_fields": evidence.get("missing_fields", []),
                    "delivery_proof": evidence.get("delivery_date", {}).get("status", "unknown"),
                }
            diffs = compare_expected(actual, row.get("expect", {}))
            print(
                f"{'FAIL' if diffs else 'PASS'} order {ref[-3:]}"
                + (": " + "; ".join(diffs) if diffs else "")
            )
            failed += bool(diffs)
    finally:
        await client.aclose()
    print(
        f"Live assertions: {failed} failed row(s) across {len(expected['items']) + len(expected['orders'])} rows."
    )
    return 1 if failed else 0


def main() -> None:
    required = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_ORG_ID")
    if any(not os.environ.get(key) for key in required):
        print(
            "SKIPPED: live assertions require client credentials and an Inventory organization; no network calls were made."
        )
        raise SystemExit(0)
    try:
        config = load_expected()
        raise SystemExit(asyncio.run(run(config)))
    except (ValueError, KeyError) as error:
        print(f"FAIL live-assert: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        print("Live assertions interrupted.", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
