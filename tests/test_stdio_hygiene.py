"""Tests for Stdio Hygiene on the FastMCP server path (NFR-8).

The MCP stdio server must never write unformatted or debug logs to stdout,
as doing so corrupts the JSON-RPC protocol stream. All logging routes to stderr.
"""

import httpx
import pytest

from mock_zoho.app import app
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.mcp_server.server import (
    get_stock_availability,
    list_items,
    set_client,
)
from zoho_inventory_connector.ratelimit.clock import VirtualClock


@pytest.fixture(autouse=True)
def setup_stdio_client() -> None:
    clock = VirtualClock()
    http_c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    tm = TokenManager("client_id", "secret", "refresh_token", clock=clock, http_client=http_c)
    tm._access_token = "zoho_access_mock_token_12345"
    tm._expires_at_mono = clock.monotonic() + 3600
    client = ZohoClient(
        token_manager=tm,
        org_id="org_kaveri_blr_001",
        clock=clock,
        http_client=http_c,
        base_url_override="http://test/inventory/v1",
    )
    set_client(client)


@pytest.mark.asyncio
async def test_zero_stdout_pollution_on_server_path(capsys: pytest.CaptureFixture[str]) -> None:
    """# NFR-8 AC: Zero output to stdout during tool execution; all logs route to stderr."""
    # Execute tools
    await list_items(page=1, per_page=5)
    await get_stock_availability(["item_1001", "item_1011"])

    captured = capsys.readouterr()

    # stdout MUST be completely empty
    assert captured.out == "", f"Stdout pollution detected: {captured.out!r}"

    # stderr SHOULD contain telemetry and audit logs
    assert "[TELEMETRY]" in captured.err
    assert "[AUDIT]" in captured.err
