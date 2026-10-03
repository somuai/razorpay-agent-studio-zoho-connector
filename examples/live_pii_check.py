"""Check that order tools keep customer email and phone masked by default."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import redirect_stderr
from io import StringIO
from typing import Any

import httpx

from mock_zoho.app import app
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.mcp_server import server

EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
LONG_DIGIT_PATTERN = re.compile(r"\d{8,}")
MOCK_REFERENCE = "order_RzpKav1001"
MOCK_EMAIL = "customer_001@example.com"
MOCK_PHONE = "+91987651001"


def _make_mock_client() -> ZohoClient:
    """Use the in-process fictional API fixture; this path makes no network call."""
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://mock")
    manager = TokenManager("mock-client", "mock-secret", "mock-refresh-token", http_client=http)
    manager._access_token = "mock-access-token"
    manager._expires_at_mono = manager.clock.monotonic() + 3600
    return ZohoClient(
        manager,
        "mock-org",
        http_client=http,
        base_url_override="http://mock/inventory/v1",
    )


def _make_live_client() -> ZohoClient:
    """Build the configured live client without printing any credential values."""
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
        manager,
        os.environ["ZOHO_ORG_ID"],
        base_url_override=os.environ.get("ZOHO_API_BASE_URL"),
    )


def _scan_output(rendered: str, raw_email: str, raw_phone: str) -> list[str]:
    """Return safe finding labels only; never echo the value that triggered a scan."""
    findings: list[str] = []
    if raw_email and raw_email.casefold() in rendered.casefold():
        findings.append("raw test email appeared in output")
    if raw_phone and raw_phone in rendered:
        findings.append("raw test phone appeared in output")
    if EMAIL_PATTERN.search(rendered):
        findings.append("email-shaped text appeared in output")
    if LONG_DIGIT_PATTERN.search(rendered):
        findings.append("8+ digit sequence appeared in output")
    return findings


def _terminal_projection(value: Any) -> Any:
    """Mask contacts and IDs so terminal output passes strict privacy scans."""
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"customer_email", "customer_phone"} or key.endswith("_id"):
                safe[key] = "[MASKED]" if item else item
            else:
                safe[key] = _terminal_projection(item)
        return safe
    if isinstance(value, list):
        return [_terminal_projection(item) for item in value]
    return value


async def _run(*, mock: bool) -> int:
    if mock:
        reference, raw_email, raw_phone = MOCK_REFERENCE, MOCK_EMAIL, MOCK_PHONE
        client = _make_mock_client()
    else:
        reference = os.environ.get("ZOHO_PII_TEST_ORDER_REFERENCE", "")
        raw_email = os.environ.get("ZOHO_PII_TEST_EMAIL", "")
        raw_phone = os.environ.get("ZOHO_PII_TEST_PHONE", "")
        if not (reference and raw_email and raw_phone):
            print(
                "FAIL: set ZOHO_PII_TEST_ORDER_REFERENCE, ZOHO_PII_TEST_EMAIL, and "
                "ZOHO_PII_TEST_PHONE to values for one fictional Zoho test customer; values are hidden."
            )
            return 2
        client = _make_live_client()

    server.set_client(client)
    try:
        tool_stderr = StringIO()
        with redirect_stderr(tool_stderr):
            found = await server.search_sales_orders(
                reference_number=reference, limit=5, include_pii=False
            )
            orders = found.get("sales_orders", []) if "error" not in found else []
            if len(orders) != 1:
                print("FAIL: expected exactly one order for the configured fictional reference.")
                return 1
            salesorder_id = str(orders[0].get("salesorder_id", ""))
            if not salesorder_id:
                print("FAIL: matching order did not include a usable order identifier.")
                return 1
            detail = await server.get_sales_order(salesorder_id, include_pii=False)
        if "error" in detail:
            print("FAIL: get_sales_order returned an error; output omitted for privacy.")
            return 1
        if not detail.get("customer_email") or not detail.get("customer_phone"):
            print(
                "FAIL: order detail did not return both configured fake contact fields; "
                "masking could not be confirmed."
            )
            return 1

        safe = {
            "search_sales_orders": _terminal_projection(orders[0]),
            "get_sales_order": _terminal_projection(detail),
        }
        rendered = json.dumps(safe, sort_keys=True, ensure_ascii=False)
        findings = _scan_output(rendered + tool_stderr.getvalue(), raw_email, raw_phone)
        if findings:
            print("FAIL: " + "; ".join(findings))
            return 1
        print(
            "PASS: search_sales_orders and get_sales_order returned masked customer fields (include_pii=false)."
        )
        print(rendered)
        print(
            "PASS: output contains no raw test email, raw test phone, email-shaped text, or 8+ digit sequence."
        )
        return 0
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mock", action="store_true", help="use the local fictional mock; no network"
    )
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(_run(mock=args.mock)))
    except KeyboardInterrupt:
        print("PII check interrupted.", file=sys.stderr)
        raise SystemExit(130) from None
    except Exception as error:  # Keep exception values out of output; they may include inputs.
        print(f"FAIL: PII masking check raised {type(error).__name__}; details omitted.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
