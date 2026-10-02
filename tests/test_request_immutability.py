"""Ensure log redaction never changes requests sent through httpx."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest

from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.events.logging_safety import RedactionFilter
from zoho_inventory_connector.mcp_server import server
from zoho_inventory_connector.ratelimit.clock import VirtualClock

ORG_ID = "999888777666555"
RECORD_ID = "123456789012345"
ACCESS_TOKEN = "mock-access-token-for-request-test"


def _item_payload() -> dict[str, Any]:
    return {
        "code": 0,
        "item": {
            "item_id": RECORD_ID,
            "name": "Fictional test item",
            "sku": "TEST-ITEM-001",
            "status": "active",
            "rate": 10,
            "stock_on_hand": 5,
            "actual_available_stock": 5,
            "reorder_level": 1,
            "unit": "pcs",
        },
    }


def _client(transport: httpx.AsyncBaseTransport) -> tuple[ZohoClient, httpx.AsyncClient]:
    clock = VirtualClock()
    http = httpx.AsyncClient(transport=transport)
    manager = TokenManager(
        "test-client",
        "test-secret",
        "test-refresh-token",
        clock=clock,
        http_client=http,
    )
    manager._access_token = ACCESS_TOKEN
    manager._expires_at_mono = clock.monotonic() + 3600
    return (
        ZohoClient(
            token_manager=manager,
            org_id=ORG_ID,
            clock=clock,
            http_client=http,
            base_url_override="https://www.zohoapis.in/inventory/v1",
        ),
        http,
    )


@pytest.mark.asyncio
async def test_exact_url_and_params_are_not_sanitized_before_httpx() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_item_payload())

    client, http = _client(httpx.MockTransport(handler))
    try:
        await client.get(
            f"/items/{RECORD_ID}",
            params={"page": "3", "organization_id": ORG_ID},
            bypass_cache=True,
        )
    finally:
        await client.aclose()
        await http.aclose()

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert str(request.url) == (
        "https://www.zohoapis.in/inventory/v1/items/123456789012345"
        "?page=3&organization_id=999888777666555"
    )
    assert request.url.params.multi_items() == [
        ("page", "3"),
        ("organization_id", ORG_ID),
    ]
    assert request.headers["Authorization"] == f"Zoho-oauthtoken {ACCESS_TOKEN}"


@pytest.mark.asyncio
async def test_full_tool_request_identical_with_debug_filter_enabled_or_disabled(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    snapshots: list[tuple[str, str, tuple[tuple[str, str], ...], str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        snapshots.append(
            (
                request.method,
                str(request.url),
                tuple(request.url.params.multi_items()),
                request.headers["Authorization"],
            )
        )
        return httpx.Response(200, json=_item_payload())

    # Call the production tool wrapper, not the client helper, in both modes.
    client_a, http_a = _client(httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_client", client_a)
    monkeypatch.setattr(server, "_stock_service", None)
    monkeypatch.setattr(server, "_dispute_service", None)
    try:
        logging.getLogger("zoho_connector.client").debug("debug test call")
        result_enabled = await server.get_item(RECORD_ID)
    finally:
        await client_a.aclose()
        await http_a.aclose()

    client_b, http_b = _client(httpx.MockTransport(handler))
    monkeypatch.setattr(server, "_client", client_b)
    monkeypatch.setattr(server, "_stock_service", None)
    monkeypatch.setattr(server, "_dispute_service", None)
    try:
        # This test validates the HTTP behavior when the filter's text rewrite
        # is inert. No secret-bearing debug message is emitted in that mode.
        monkeypatch.setattr(RedactionFilter, "filter", lambda self, record: True)
        try:
            logging.getLogger("zoho_connector.client").debug("debug test call")
            result_disabled = await server.get_item(RECORD_ID)
        finally:
            monkeypatch.undo()
    finally:
        await client_b.aclose()
        await http_b.aclose()

    assert len(snapshots) == 2
    assert snapshots[0] == snapshots[1]
    assert snapshots[0][1] == (
        "https://www.zohoapis.in/inventory/v1/items/123456789012345?organization_id=999888777666555"
    )
    assert snapshots[0][2] == (("organization_id", ORG_ID),)
    assert snapshots[0][3] == f"Zoho-oauthtoken {ACCESS_TOKEN}"
    assert {key: value for key, value in result_enabled.items() if key != "as_of"} == {
        key: value for key, value in result_disabled.items() if key != "as_of"
    }
