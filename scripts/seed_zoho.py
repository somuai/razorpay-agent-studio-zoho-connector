"""Seed fictional fixtures into a disposable Zoho org (the repo's only Inventory writer).

This script is deliberately isolated from ``src/``. It requires a separate OAuth
grant, token file, target org, location, and an explicit write acknowledgement.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

DC_ACCOUNTS = {
    "in": "https://accounts.zoho.in",
    "com": "https://accounts.zoho.com",
    "eu": "https://accounts.zoho.eu",
    "com.au": "https://accounts.zoho.com.au",
}
DC_API = {
    "in": "https://www.zohoapis.in",
    "com": "https://www.zohoapis.com",
    "eu": "https://www.zohoapis.eu",
    "com.au": "https://www.zohoapis.com.au",
}
FIXTURE_CONTACT_NAME = "Test Customer - Zoho Connector Demo"
FIXTURE_EMAIL = "zoho-connector-demo@example.invalid"
ITEMS = [
    ("KHG-SEED-CUSHION", "Test Cushion Cover", 699.0, 20),
    ("KHG-SEED-LAMP", "Test Brass Table Lamp", 1499.0, 0),
    ("KHG-SEED-VASE", "Test Ceramic Vase", 2199.0, 2),
    ("KHG-SEED-RUNNER", "Test Linen Table Runner", 899.0, 0),
    ("KHG-SEED-TRAY", "Test Wooden Serving Tray", 1299.0, 1),
    ("KHG-SEED-MUG", "Test Ceramic Mug Set", 799.0, 18),
    ("KHG-SEED-THROW", "Test Cotton Throw", 2499.0, 22),
    ("KHG-SEED-PLANTER", "Test Terracotta Planter", 650.0, 7),
    ("KHG-SEED-BASKET", "Test Woven Basket", 1100.0, 12),
    ("KHG-SEED-CANDLE", "Test Brass Candle Holder", 950.0, 9),
]


class SeedError(RuntimeError):
    """Safe, user-facing seed failure that never includes a secret-bearing response body."""


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
        os.replace(tmp_path, path)
        os.chmod(path, 0o600)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _read_state(path: Path, org_id: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "organization_id": org_id,
            "items": {},
            "orders": {},
            "packages": {},
            "shipments": {},
        }
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SeedError(
            "Seed state file is unreadable; preserve it and inspect it before continuing."
        ) from None
    if state.get("organization_id") != org_id:
        raise SeedError("Seed state belongs to another organization; refusing to reuse it.")
    return state


async def _run_seed() -> int:
    org_id = os.environ["ZOHO_SEED_ORG_ID"]
    dc = os.environ.get("ZOHO_DC", "in").lower()
    accounts_url = os.environ.get(
        "ZOHO_SEED_ACCOUNTS_BASE_URL", DC_ACCOUNTS.get(dc, DC_ACCOUNTS["in"])
    )
    api_domain = os.environ.get("ZOHO_SEED_API_DOMAIN", DC_API.get(dc, DC_API["in"]))
    api_url = f"{api_domain.rstrip('/')}/inventory/v1"
    location_id = os.environ["ZOHO_SEED_LOCATION_ID"]
    token_path = Path(os.environ.get("ZOHO_SEED_TOKEN_FILE", ".zoho_seed_token.json"))
    state_path = Path(os.environ.get("ZOHO_SEED_STATE_FILE", ".zoho_seed_state.json"))
    state = _read_state(state_path, org_id)

    client_id = os.environ["ZOHO_SEED_CLIENT_ID"]
    client_secret = os.environ["ZOHO_SEED_CLIENT_SECRET"]
    refresh_token = os.environ["ZOHO_SEED_REFRESH_TOKEN"]

    async with httpx.AsyncClient(timeout=20.0) as http:
        try:
            token_response = await http.post(
                f"{accounts_url.rstrip('/')}/oauth/v2/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                },
            )
        except httpx.HTTPError:
            raise SeedError(
                "Could not reach Zoho Accounts while refreshing the seed token."
            ) from None
        if token_response.status_code != 200:
            raise SeedError(
                f"Zoho rejected the seed OAuth grant (HTTP {token_response.status_code})."
            )
        token_payload = token_response.json()
        access_token = token_payload.get("access_token")
        if not access_token:
            raise SeedError("Zoho token response did not include an access token.")
        if token_payload.get("api_domain"):
            api_url = f"{str(token_payload['api_domain']).rstrip('/')}/inventory/v1"
        _write_private_json(
            token_path,
            {"refresh_token": refresh_token, "api_domain": token_payload.get("api_domain")},
        )
        headers = {"Authorization": f"Zoho-oauthtoken {access_token}", "Accept": "application/json"}

        async def request(
            method: str,
            endpoint: str,
            *,
            params: dict[str, str] | None = None,
            body: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            query = {"organization_id": org_id, **(params or {})}
            try:
                response = await http.request(
                    method,
                    f"{api_url}/{endpoint.lstrip('/')}",
                    params=query,
                    headers=headers,
                    json=body,
                )
            except httpx.HTTPError:
                raise SeedError(
                    f"Zoho request failed for {endpoint}; no write retry was attempted."
                ) from None
            if response.status_code not in {200, 201}:
                raise SeedError(
                    f"Zoho returned HTTP {response.status_code} for {endpoint}; no write retry was attempted."
                )
            try:
                data = response.json()
            except ValueError:
                raise SeedError(f"Zoho returned invalid JSON for {endpoint}.") from None
            if isinstance(data, dict) and data.get("code") not in {None, 0}:
                raise SeedError(
                    f"Zoho returned application error code {data['code']} for {endpoint}."
                )
            return data

        # Complete all reads that could prevent safe deduplication before writing.
        items_page = await request("GET", "/items", params={"page": "1", "per_page": "200"})
        contacts_page = await request(
            "GET", "/contacts", params={"contact_name": FIXTURE_CONTACT_NAME, "per_page": "200"}
        )
        orders_page = await request("GET", "/salesorders", params={"page": "1", "per_page": "200"})
        # Verify package read access before any writes; package lookup is required
        # later for idempotent creation and shipment checks.
        await request("GET", "/packages", params={"page": "1", "per_page": "1"})
        existing_items = {str(row.get("sku")): row for row in items_page.get("items", [])}
        existing_contacts = [
            row
            for row in contacts_page.get("contacts", [])
            if row.get("contact_name") == FIXTURE_CONTACT_NAME
        ]
        existing_orders = {
            str(row.get("salesorder_number")): row for row in orders_page.get("salesorders", [])
        }

        contact = existing_contacts[0] if existing_contacts else None
        if len(existing_contacts) > 1:
            raise SeedError(
                "Multiple fixture contacts with the exact deterministic name exist; refusing to guess."
            )

        for sku, name, rate, quantity in ITEMS:
            item = existing_items.get(sku)
            if item:
                state.setdefault("items", {})[sku] = str(item.get("item_id", ""))
                continue
            body = {
                "name": name,
                "sku": sku,
                "unit": "pcs",
                "item_type": "inventory",
                "product_type": "goods",
                "track_inventory": True,
                "rate": rate,
                "reorder_level": 5,
                "locations": [
                    {
                        "location_id": location_id,
                        "initial_stock": quantity,
                        "initial_stock_rate": rate,
                    }
                ],
            }
            result = await request("POST", "/items", body=body)
            item = result.get("item", {})
            item_id = str(item.get("item_id", ""))
            if not item_id:
                raise SeedError(
                    f"Zoho accepted {sku} without returning an item ID; preserve partial results and inspect the org."
                )
            state.setdefault("items", {})[sku] = item_id
            _write_private_json(state_path, state)
            existing_items[sku] = item

        if contact is None:
            result = await request(
                "POST",
                "/contacts",
                body={
                    "contact_name": FIXTURE_CONTACT_NAME,
                    "contact_type": "customer",
                    "email": FIXTURE_EMAIL,
                },
            )
            contact = result.get("contact", {})
            if not contact.get("contact_id"):
                raise SeedError("Zoho accepted the fixture contact without returning a contact ID.")
            _write_private_json(state_path, {**state, "contact_id": str(contact["contact_id"])})

        contact_id = str(contact.get("contact_id", state.get("contact_id", "")))
        created_orders: list[dict[str, Any]] = []
        for index, (sku, name, rate, _) in enumerate(ITEMS[:8], start=1):
            order_number = f"KHG-SEED-SO-{index:03d}"
            reference = f"order_RzpKavSeed{index:03d}"
            order = existing_orders.get(order_number)
            if not order:
                item_id = str(
                    state.get("items", {}).get(sku)
                    or existing_items.get(sku, {}).get("item_id", "")
                )
                item_data = await request("GET", f"/items/{item_id}")
                item = item_data.get("item", {})
                lines = item.get("item_id") and [
                    {
                        "item_id": item_id,
                        "name": name,
                        "rate": rate,
                        "quantity": 1,
                        "unit": str(item.get("unit", "pcs")),
                    }
                ]
                if not lines:
                    raise SeedError(
                        f"Fixture item {sku} could not be read; refusing to create its order."
                    )
                result = await request(
                    "POST",
                    "/salesorders",
                    body={
                        "customer_id": contact_id,
                        "salesorder_number": order_number,
                        "reference_number": reference,
                        "date": "2026-09-15",
                        "line_items": lines,
                    },
                )
                order = result.get("salesorder", {})
                if not order.get("salesorder_id"):
                    raise SeedError(f"Zoho accepted {order_number} without returning an order ID.")
                state.setdefault("orders", {})[order_number] = str(order["salesorder_id"])
                _write_private_json(state_path, state)
            created_orders.append(order)

        # Four orders get a package. Two get a shipment/tracking reference; two
        # deliberately remain packaged without tracking for partial evidence.
        for index, order in enumerate(created_orders[:4], start=1):
            salesorder_id = str(order["salesorder_id"])
            existing_package = state.get("packages", {}).get(salesorder_id)
            package_id = str(existing_package or "")
            if not package_id:
                package_list = await request(
                    "GET", "/packages", params={"salesorder_id": salesorder_id, "per_page": "50"}
                )
                package_rows = package_list.get("packages", [])
                if package_rows:
                    package_id = str(package_rows[0].get("package_id", ""))
            if not package_id:
                order_detail = await request("GET", f"/salesorders/{salesorder_id}")
                order_full = order_detail.get("salesorder", {})
                so_lines = order_full.get("line_items", [])
                if not so_lines:
                    raise SeedError(f"{salesorder_id} has no line item IDs for package creation.")
                line = so_lines[0]
                package_result = await request(
                    "POST",
                    "/packages",
                    params={"salesorder_id": salesorder_id},
                    body={
                        "package_number": f"KHG-SEED-PKG-{index:03d}",
                        "date": "2026-09-16",
                        "line_items": [
                            {"so_line_item_id": str(line.get("line_item_id", "")), "quantity": 1}
                        ],
                    },
                )
                package_id = str(package_result.get("package", {}).get("package_id", ""))
                if not package_id:
                    raise SeedError(
                        "Zoho accepted a fixture package without returning a package ID."
                    )
                state.setdefault("packages", {})[salesorder_id] = package_id
                _write_private_json(state_path, state)

            if index <= 2 and not state.get("shipments", {}).get(package_id):
                package_detail = await request("GET", f"/packages/{package_id}")
                package = package_detail.get("package", {})
                if not package.get("shipment_order"):
                    result = await request(
                        "POST",
                        "/shipmentorders",
                        params={"salesorder_id": salesorder_id, "package_ids": package_id},
                        body={
                            "shipment_number": f"KHG-SEED-SHP-{index:03d}",
                            "date": "2026-09-17",
                            "delivery_method": "Test Carrier",
                            "tracking_number": f"TEST-TRACK-{index:06d}",
                            "reference_number": f"KHG-SEED-TRACK-{index:03d}",
                        },
                    )
                    shipment = result.get("shipmentorder", result.get("shipment_order", {}))
                    shipment_id = str(
                        shipment.get("shipmentorder_id", shipment.get("shipment_order_id", ""))
                    )
                    if not shipment_id:
                        raise SeedError(
                            "Zoho accepted a fixture shipment without returning its shipment ID."
                        )
                    state.setdefault("shipments", {})[package_id] = shipment_id
                    _write_private_json(state_path, state)

    print(
        "Seed finished. Created or reused fictional fixture records; no real customer data was used."
    )
    print(f"Private token file: {token_path}; private state file: {state_path}.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the fictional seed plan; make no network calls.",
    )
    mode.add_argument(
        "--i-understand-this-writes",
        action="store_true",
        help="Acknowledge writes to the disposable Zoho organization named by ZOHO_SEED_ORG_ID.",
    )
    args = parser.parse_args()
    if args.dry_run:
        print("DRY RUN: no credentials read and no network calls made.")
        print(
            f"Would seed {len(ITEMS)} fictional items, 8 sales orders, 4 packages, and up to 2 shipments."
        )
        print("Out-of-stock/low-stock starting quantities are fictional; no delivery is claimed.")
        return

    required = (
        "ZOHO_SEED_CLIENT_ID",
        "ZOHO_SEED_CLIENT_SECRET",
        "ZOHO_SEED_REFRESH_TOKEN",
        "ZOHO_SEED_ORG_ID",
        "ZOHO_SEED_LOCATION_ID",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("Missing separate seed settings: " + ", ".join(missing), file=sys.stderr)
        raise SystemExit(2)
    print("Write acknowledgement accepted for disposable Zoho organization (ID hidden).")
    try:
        raise SystemExit(asyncio.run(_run_seed()))
    except SeedError as exc:
        print(f"Seed stopped safely: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
