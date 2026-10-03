"""Live helpers share the retrying Inventory client and expose actual HTTP attempts."""

from __future__ import annotations

import json
from collections import Counter

import httpx
import pytest

from examples import live_assert, live_probe, live_smoke
from mock_zoho.app import app
from mock_zoho.faults import faults
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.ratelimit.clock import VirtualClock


class FlakyASGITransport(httpx.AsyncBaseTransport):
    """Raise a configured number of connect errors, then call the local mock app."""

    def __init__(self, fail_path: str, failures: int) -> None:
        self.fail_path = fail_path
        self.failures = failures
        self.seen: Counter[str] = Counter()
        self.delegate = httpx.ASGITransport(app=app)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.seen[path] += 1
        if path == self.fail_path and self.seen[path] <= self.failures:
            raise httpx.ConnectTimeout("private mock transport text", request=request)
        return await self.delegate.handle_async_request(request)

    async def aclose(self) -> None:
        await self.delegate.aclose()


class CachedTokenManager:
    async def get_access_token(self, force_refresh: bool = False) -> str:
        return "zoho_access_mock_token_12345"

    def get_api_base_url(self) -> str:
        return "http://test"


def _make_client(
    path: str, failures: int
) -> tuple[ZohoClient, httpx.AsyncClient, FlakyASGITransport]:
    transport = FlakyASGITransport(path, failures)
    http = httpx.AsyncClient(transport=transport, base_url="http://test")
    client = ZohoClient(
        token_manager=CachedTokenManager(),  # type: ignore[arg-type]
        org_id="org_kaveri_blr_001",
        http_client=http,
        base_url_override="http://test/inventory/v1",
        clock=VirtualClock(),
    )
    return client, http, transport


@pytest.fixture(autouse=True)
def _offline_retry_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    faults.reset()
    monkeypatch.setenv("ZOHO_CONNECT_RETRIES", "4")

    async def no_wait(_: int) -> None:
        return None

    monkeypatch.setattr(
        "zoho_inventory_connector.client.transport_diagnostics.connect_backoff", no_wait
    )


@pytest.mark.asyncio
async def test_smoke_uses_retrying_client_and_reports_actual_attempt_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client, http, transport = _make_client("/inventory/v1/items", 3)
    monkeypatch.setenv("ZOHO_CLIENT_ID", "mock-client")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "mock-secret")
    monkeypatch.setenv("ZOHO_ORG_ID", "org_kaveri_blr_001")
    monkeypatch.setattr(live_smoke, "TokenManager", lambda **_: CachedTokenManager())
    monkeypatch.setattr(live_smoke, "ZohoClient", lambda **_: client)
    try:
        assert await live_smoke._run() == 0
    finally:
        await http.aclose()
    output = capsys.readouterr().out
    first_tool = json.loads(
        next(line for line in output.splitlines() if '"tool": "list_items"' in line)
    )
    assert first_tool["upstream_calls"] == 4
    assert transport.seen["/inventory/v1/items"] >= 4
    assert "Live smoke completed" in output


@pytest.mark.asyncio
async def test_probe_uses_retrying_client_and_reports_actual_attempt_count() -> None:
    client, http, transport = _make_client("/inventory/v1/salesorders", 2)
    try:
        report = await live_probe.run_probe(client)
    finally:
        await http.aclose()
    assert transport.seen["/inventory/v1/salesorders"] >= 4
    assert report["upstream_attempt_count"] == client.metrics.calls_made
    assert report["upstream_attempt_count"] >= 4
    rendered = live_probe.render_report(report)
    assert f"upstream HTTP attempts: {report['upstream_attempt_count']}" in rendered


@pytest.mark.asyncio
async def test_probe_reports_each_failed_connect_phase() -> None:
    client, http, _ = _make_client("/inventory/v1/salesorders", 4)
    try:
        report = await live_probe.run_probe(client)
    finally:
        await http.aclose()
    rendered = live_probe.render_report(report)
    assert "transport attempts 4 (connect, connect, connect, connect)" in rendered


@pytest.mark.asyncio
async def test_assert_uses_retrying_client_and_reports_actual_attempt_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client, http, transport = _make_client("/inventory/v1/items", 3)
    monkeypatch.setattr(live_assert, "_configured_client", lambda: client)
    try:
        assert (
            await live_assert.run(
                {"items": [{"sku": "KHG-CUSH-001", "expect": {"status": "in_stock"}}], "orders": []}
            )
            == 0
        )
    finally:
        await http.aclose()
    output = capsys.readouterr().out
    assert transport.seen["/inventory/v1/items"] == 4
    assert "upstream HTTP attempts: 4" in output


@pytest.mark.asyncio
async def test_assert_reports_failed_connect_attempt_count_and_phases(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client, http, _ = _make_client("/inventory/v1/items", 4)
    monkeypatch.setattr(live_assert, "_configured_client", lambda: client)
    try:
        assert (
            await live_assert.run(
                {"items": [{"sku": "KHG-CUSH-001", "expect": {"status": "in_stock"}}], "orders": []}
            )
            == 1
        )
    finally:
        await http.aclose()
    output = capsys.readouterr().out
    assert "transport attempts: 4 (connect, connect, connect, connect)" in output
    assert "upstream HTTP attempts: 4" in output
