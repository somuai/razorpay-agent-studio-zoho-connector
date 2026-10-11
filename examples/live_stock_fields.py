"""Compare Zoho stock-related fields with the connector decision and UI values.

Live mode is deliberately read-only. ``--mock`` uses the in-process fictional
Zoho API and never opens a network connection.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from typing import Any

import httpx

from mock_zoho.app import app
from mock_zoho.fixtures import PRODUCT_CATALOG
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.mcp_server import server

EXPECTED_SKUS = tuple(f"KHG-{index:03d}" for index in range(1, 11))
MOCK_SKUS = tuple(row[1] for row in PRODUCT_CATALOG[:10])
UI_VALUES_PATH = Path(os.environ.get("ZOHO_LIVE_UI_VALUES_PATH", "live_ui_values.yaml"))
UI_EXAMPLE_PATH = Path("live_ui_values.example.yaml")
STOCK_KEY = re.compile(r"stock|available", re.IGNORECASE)
LONG_DIGITS = re.compile(r"\d{8,}")
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


def _mock_client() -> ZohoClient:
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


def _live_client() -> ZohoClient:
    required = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_ORG_ID")
    missing = [name for name in required if not os.environ.get(name)]
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


def load_ui_values(path: Path = UI_VALUES_PATH) -> dict[str, dict[str, float | None]]:
    """Load the optional JSON-compatible YAML UI observation file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as error:
        raise ValueError(
            "live_ui_values.yaml must use the JSON-compatible YAML syntax in "
            "live_ui_values.example.yaml"
        ) from error
    rows = data.get("items") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("UI values file must contain an 'items' list.")
    result: dict[str, dict[str, float | None]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("sku"), str):
            continue
        parsed: dict[str, float | None] = {}
        for key in ("on_hand", "available_for_sale"):
            value = row.get(key)
            parsed[key] = float(value) if isinstance(value, (int, float)) else None
        result[row["sku"]] = parsed
    return result


def stock_fields(value: Any, prefix: str = "") -> dict[str, Any]:
    """Collect every stock/availability leaf while preserving its response path."""
    found: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if STOCK_KEY.search(str(key)) and not isinstance(child, (dict, list)):
                found[path] = child
            else:
                found.update(stock_fields(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.update(stock_fields(child, f"{prefix}[{index}]"))
    return found


def _field_matching(fields: dict[str, Any], value: float | None) -> list[str]:
    if value is None:
        return []
    matches: list[str] = []
    for key, raw in fields.items():
        try:
            if raw is not None and float(raw) == value:
                matches.append(key)
        except (TypeError, ValueError):
            continue
    return matches


def _display_value(value: Any) -> str:
    """Render only scalar stock values, masking any unexpected identifier text."""
    rendered = str(value)
    rendered = EMAIL.sub("[MASKED_EMAIL]", rendered)
    return LONG_DIGITS.sub("[MASKED_DIGITS]", rendered)


async def collect(client: ZohoClient, skus: tuple[str, ...]) -> list[dict[str, Any]]:
    """Fetch catalog once, then each matching item detail exactly once."""
    server.set_client(client)
    catalog, _, _ = await client.get(
        "/items", params={"page": "1", "per_page": "50"}, bypass_cache=True
    )
    by_sku = {
        str(row.get("sku", "")).upper(): row
        for row in catalog.get("items", [])
        if isinstance(row, dict) and row.get("sku")
    }
    rows: list[dict[str, Any]] = []
    for sku in skus:
        summary = by_sku.get(sku.upper())
        if not summary:
            rows.append(
                {"sku": sku, "missing": True, "fields": {}, "source": "none", "status": "unknown"}
            )
            continue
        item_id = str(summary.get("item_id", ""))
        detail, _, _ = await client.get(f"/items/{item_id}", bypass_cache=True)
        item = detail.get("item") if isinstance(detail, dict) else None
        if not isinstance(item, dict):
            rows.append(
                {"sku": sku, "missing": True, "fields": {}, "source": "none", "status": "unknown"}
            )
            continue
        # Use the actual MCP tool path, backed by the already-fetched detail response.
        # ZohoClient constructs its cache key before adding organization_id to
        # the outgoing request parameters; a direct item lookup has no params.
        cache_key = f"{client._resolve_base_url()}/items/{item_id}?[]"
        await client.cache.set(cache_key, {"item": item}, 60.0)
        with redirect_stderr(StringIO()):
            decision = await server.get_stock_availability([item_id])
        availability = (decision.get("items") or [{}])[0] if "error" not in decision else {}
        rows.append(
            {
                "sku": sku,
                "fields": stock_fields(item),
                "source": availability.get("source_stock_field", "none"),
                "quantity": availability.get("quantity_sellable"),
                "status": availability.get("status", "unknown"),
                "on_hand": item.get("stock_on_hand"),
                "available_for_sale": item.get("available_for_sale"),
            }
        )
    return rows


def _scan(rendered: str) -> list[str]:
    findings: list[str] = []
    for number, line in enumerate(rendered.splitlines(), start=1):
        safe_line = EMAIL.sub("[MASKED_EMAIL]", line)
        if LONG_DIGITS.search(line):
            findings.append(f"line {number}: {LONG_DIGITS.sub('[MASKED_DIGITS]', safe_line)}")
        if EMAIL.search(line):
            findings.append(f"line {number}: [email-shaped text masked]")
    return findings


def render(rows: list[dict[str, Any]], ui: dict[str, dict[str, float | None]], mode: str) -> str:
    """Render a compact table and explicit cross-source summary."""
    lines = [
        f"Mode: {mode}",
        "SKU | API stock/availability fields | connector source | status | UI on-hand match | UI available match | source equals UI available",
    ]
    on_hand_keys: dict[str, int] = {}
    available_keys: dict[str, int] = {}
    complete = 0
    source_matches = 0
    for row in rows:
        sku = row["sku"]
        fields = row.get("fields", {})
        values = (
            ", ".join(f"{key}={_display_value(value)}" for key, value in sorted(fields.items()))
            or "none"
        )
        observed = ui.get(sku, {})
        on_matches = _field_matching(fields, observed.get("on_hand"))
        available_matches = _field_matching(fields, observed.get("available_for_sale"))
        for key in on_matches:
            on_hand_keys[key] = on_hand_keys.get(key, 0) + 1
        for key in available_matches:
            available_keys[key] = available_keys.get(key, 0) + 1
        on_verdict = (
            "NOT RECORDED"
            if observed.get("on_hand") is None
            else ("MATCH: " + ",".join(on_matches) if on_matches else "NO MATCH")
        )
        av_verdict = (
            "NOT RECORDED"
            if observed.get("available_for_sale") is None
            else ("MATCH: " + ",".join(available_matches) if available_matches else "NO MATCH")
        )
        if observed.get("available_for_sale") is not None:
            complete += 1
            if row.get("source") and row.get("quantity") == observed.get("available_for_sale"):
                source_matches += 1
        lines.append(
            f"{sku} | {values} | {row.get('source', 'none')} | {row.get('status', 'unknown')} | {on_verdict} | {av_verdict} | "
            + (
                "MATCH"
                if observed.get("available_for_sale") is not None
                and row.get("quantity") == observed.get("available_for_sale")
                else "NO MATCH"
                if observed.get("available_for_sale") is not None
                else "NOT RECORDED"
            )
        )
    lines.append("Summary:")
    lines.append(
        "API key matching UI on-hand: "
        + (
            ", ".join(sorted(on_hand_keys))
            if on_hand_keys
            else "INCONCLUSIVE (UI values not recorded or no field matched)"
        )
    )
    lines.append(
        "API key matching UI available-for-sale: "
        + (
            ", ".join(sorted(available_keys))
            if available_keys
            else "INCONCLUSIVE (UI values not recorded or no field matched)"
        )
    )
    lines.append(
        "Connector-selected field equals UI available-for-sale for every recorded SKU: "
        + (
            f"{'YES' if source_matches == complete else 'NO'} ({source_matches}/{complete}; {len(rows) - complete} UI values not recorded)"
            if complete
            else "INCONCLUSIVE (UI values not recorded)"
        )
    )
    return "\n".join(lines)


async def run(mock: bool, ui_path: Path = UI_VALUES_PATH) -> int:
    client = _mock_client() if mock else _live_client()
    skus = MOCK_SKUS if mock else EXPECTED_SKUS
    try:
        with redirect_stderr(StringIO()):
            rows = await collect(client, skus)
        ui = load_ui_values(ui_path)
        output = render(rows, ui, "MOCK / SIMULATED (offline)" if mock else "LIVE / READ-ONLY")
        print(output)
        findings = _scan(output)
        if findings:
            print("Identifier scan: UNSAFE; offending lines (digits masked):")
            print("\n".join(findings))
            return 1
        print("Identifier scan: SAFE")
        if not mock and not ui:
            print(
                f"UI comparison: INCONCLUSIVE; record UI values in {ui_path} (template: {UI_EXAMPLE_PATH})."
            )
        return 0
    finally:
        await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mock", action="store_true", help="use local fictional API; no network")
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(run(args.mock)))
    except KeyboardInterrupt:
        print("Stock field check interrupted.", file=sys.stderr)
        raise SystemExit(130) from None
    except Exception as error:
        print(f"FAIL: stock field check raised {type(error).__name__}; details omitted.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
