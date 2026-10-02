"""Regression tests for identifier and credential redaction in all log paths.

These tests use the deterministic in-process Zoho mock only. No live target or
credential file is consulted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from examples import live_assert, live_preflight, live_probe, live_smoke
from mock_zoho.app import MOCK_ACCESS_TOKEN, app
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.client.errors import NotFoundError
from zoho_inventory_connector.events.audit import AuditEvent, AuditLogger
from zoho_inventory_connector.events.logging_safety import configure_secure_logging
from zoho_inventory_connector.mcp_server import server
from zoho_inventory_connector.ratelimit.clock import VirtualClock

ORG_ID = "999888777666555"
RECORD_ID = "123456789012345"
ACCESS_TOKEN = MOCK_ACCESS_TOKEN
AUTH_VALUE = f"Zoho-oauthtoken {ACCESS_TOKEN}"
CLIENT_SECRET = "client-secret-value-should-never-log"
ALL_SECRETS = (ORG_ID, RECORD_ID, ACCESS_TOKEN, AUTH_VALUE, CLIENT_SECRET)


@pytest.fixture(autouse=True)
def secure_logging(caplog: pytest.LogCaptureFixture) -> None:
    configure_secure_logging()
    caplog.set_level(logging.DEBUG)


def _assert_no_secrets(value: str, *, allow_masked_suffix: bool = True) -> None:
    for secret in ALL_SECRETS:
        assert secret not in value
    if allow_masked_suffix:
        assert "***555" in value or ORG_ID not in value
        assert "***345" in value or RECORD_ID not in value


def _mock_client() -> tuple[ZohoClient, httpx.AsyncClient]:
    clock = VirtualClock()
    transport = httpx.ASGITransport(app=app)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://test")
    manager = TokenManager(
        "test-client-id",
        CLIENT_SECRET,
        "test-refresh-token",
        clock=clock,
        http_client=http_client,
    )
    manager._access_token = ACCESS_TOKEN
    manager._expires_at_mono = clock.monotonic() + 3600
    client = ZohoClient(
        token_manager=manager,
        org_id=ORG_ID,
        clock=clock,
        http_client=http_client,
        base_url_override="http://test/inventory/v1",
    )
    return client, http_client


def test_filter_covers_new_loggers_urls_headers_and_exception_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A logger created after configuration must inherit the same protection.
    logger = logging.getLogger("third_party.future_transport")
    logger.setLevel(logging.DEBUG)
    logger.warning(
        "GET https://www.zohoapis.in/inventory/v1/items/%s?organization_id=%s headers=%r error=%s",
        RECORD_ID,
        ORG_ID,
        {"Authorization": AUTH_VALUE},
        f"request failed for {RECORD_ID} with client_secret={CLIENT_SECRET}",
    )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    _assert_no_secrets(rendered)
    assert "***555" in rendered
    assert "***345" in rendered

    try:
        raise RuntimeError(
            f"refresh_token={ACCESS_TOKEN}; request organization_id={ORG_ID}; record {RECORD_ID}"
        )
    except RuntimeError:
        logger.exception("upstream transport failure")
    _assert_no_secrets(caplog.text)


def test_http_library_debug_loggers_are_quiet_by_default() -> None:
    for name in ("httpx", "httpcore", "urllib3"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING


@pytest.mark.asyncio
async def test_representative_tool_call_has_no_identifier_or_auth_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, http = _mock_client()
    try:
        # Exercise the real GET transport and logger configuration against mock_zoho.
        response, _, _ = await client.get(
            "/items/item_1001", params={"organization_id": ORG_ID}, bypass_cache=True
        )
        assert isinstance(response, dict)
        logging.getLogger("zoho_connector.client").debug(
            "request URL=%s params=%r headers=%r",
            f"/items/{RECORD_ID}?organization_id={ORG_ID}",
            {"organization_id": ORG_ID},
            {"Authorization": AUTH_VALUE},
        )
    finally:
        await client.aclose()
        await http.aclose()

    output = caplog.text
    _assert_no_secrets(output)


@pytest.mark.asyncio
async def test_not_found_error_does_not_include_org_or_record_ids() -> None:
    client, http = _mock_client()
    try:
        with pytest.raises(NotFoundError) as caught:
            await client.get(
                f"items/{RECORD_ID}",
                params={"organization_id": ORG_ID},
                bypass_cache=True,
            )
    finally:
        await client.aclose()
        await http.aclose()
    _assert_no_secrets(str(caught.value))


def _preflight_env(tmp_path: Path) -> dict[str, str]:
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"refresh_token": "test-refresh-token"}), encoding="utf-8")
    token_file.chmod(0o600)
    return {
        "ZOHO_CLIENT_ID": "test-client-id",
        "ZOHO_CLIENT_SECRET": CLIENT_SECRET,
        "ZOHO_REFRESH_TOKEN": "test-refresh-token",
        "ZOHO_ORG_ID": ORG_ID,
        "ZOHO_DC": "in",
        "ZOHO_TOKEN_FILE": str(token_file),
    }


def _preflight_http_clients() -> tuple[httpx.AsyncClient, httpx.AsyncClient]:
    async def token_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": ACCESS_TOKEN,
                "api_domain": "https://www.zohoapis.in",
                "expires_in": 3600,
                "scope": "ZohoInventory.items.READ",
            },
        )

    async def api_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/organizations"):
            return httpx.Response(
                200, json={"code": 0, "organizations": [{"organization_id": ORG_ID}]}
            )
        if "/shipmentorders/" in request.url.path:
            return httpx.Response(404, json={"code": 1002, "message": "record not found"})
        return httpx.Response(200, json={"code": 0})

    return (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)),
        httpx.AsyncClient(transport=httpx.MockTransport(token_handler)),
    )


@pytest.mark.asyncio
async def test_live_preflight_mock_logs_and_output_are_redacted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    api, token = _preflight_http_clients()
    try:
        result = await live_preflight.run_preflight(
            _preflight_env(tmp_path), api_http=api, token_http=token
        )
    finally:
        await api.aclose()
        await token.aclose()
    assert result == 0
    _assert_no_secrets(caplog.text + capsys.readouterr().out)


@pytest.mark.asyncio
async def test_live_probe_mock_logs_and_report_are_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, http = _mock_client()
    try:
        report = await live_probe.run_probe(client)
    finally:
        await client.aclose()
        await http.aclose()
    _assert_no_secrets(live_probe.render_report(report) + caplog.text)


@pytest.mark.asyncio
async def test_live_assert_mock_logs_and_output_are_redacted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client, http = _mock_client()
    monkeypatch.setattr(live_assert, "_configured_client", lambda: client)
    config: dict[str, Any] = {
        "items": [{"sku": "KHG-CUSH-001", "expect": {"status": "in_stock"}}],
        "orders": [
            {
                "reference_number": "order_RzpKav1001",
                "expect": {"found": True},
            }
        ],
    }
    try:
        await live_assert.run(config)
    finally:
        await http.aclose()
    _assert_no_secrets(caplog.text + capsys.readouterr().out)


@pytest.mark.asyncio
async def test_live_smoke_mock_logs_and_output_are_redacted(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    previous_client = server._client
    client, http = _mock_client()
    monkeypatch.setenv("ZOHO_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("ZOHO_ORG_ID", ORG_ID)
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "test-refresh-token")
    monkeypatch.setenv("ZOHO_API_BASE_URL", "http://test/inventory/v1")

    class CachedTokenManager:
        async def get_access_token(self) -> str:
            return ACCESS_TOKEN

    monkeypatch.setattr(live_smoke, "TokenManager", lambda **_: CachedTokenManager())
    monkeypatch.setattr(live_smoke, "ZohoClient", lambda **_: client)
    try:
        result = await live_smoke._run()
    finally:
        await http.aclose()
        server._client = previous_client
        server._stock_service = None
        server._dispute_service = None
    assert result == 0
    _assert_no_secrets(caplog.text + capsys.readouterr().out)


def test_audit_sink_masks_record_identifiers_and_credentials(tmp_path: Path) -> None:
    target = tmp_path / "audit.jsonl"
    sink = AuditLogger(target)
    sink.record(
        AuditEvent.create(
            "get_item",
            {
                "item_id": RECORD_ID,
                "organization_id": ORG_ID,
                "Authorization": AUTH_VALUE,
                "client_secret": CLIENT_SECRET,
            },
            "request-id-safe",
        )
    )
    contents = target.read_text(encoding="utf-8")
    assert RECORD_ID not in contents
    assert ORG_ID not in contents
    assert ACCESS_TOKEN not in contents
    assert AUTH_VALUE not in contents
    assert CLIENT_SECRET not in contents
