"""Offline tests for the read-only live assertion harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from examples import live_assert
from mock_zoho.app import app
from mock_zoho.faults import faults
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.ratelimit.clock import VirtualClock


@pytest.fixture(autouse=True)
def reset_faults() -> None:
    faults.reset()


def test_expected_config_loads_json_yaml_subset(tmp_path: Path) -> None:
    path = tmp_path / "expected.yaml"
    path.write_text(json.dumps({"items": [], "orders": []}), encoding="utf-8")
    assert live_assert.load_expected(path) == {"items": [], "orders": []}


def test_missing_expected_config_has_copy_instructions(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="copy live_expected.example.yaml"):
        live_assert.load_expected(tmp_path / "live_expected.yaml")


def test_compare_expected_reports_only_declared_fields() -> None:
    assert live_assert.compare_expected(
        {"status": "low_stock", "irrelevant": "private"}, {"status": "in_stock"}
    ) == ["status: expected 'in_stock', got 'low_stock'"]
    assert (
        live_assert.compare_expected(
            {"missing_fields": ["tracking_number", "invoice"]},
            {"missing_fields": ["invoice", "tracking_number"]},
        )
        == []
    )


@pytest.mark.asyncio
async def test_assertion_calls_tools_only_through_read_only_surface(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clock = VirtualClock()
    http_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    token_manager = TokenManager(
        "client_id", "secret", "refresh_token", clock=clock, http_client=http_client
    )
    token_manager._access_token = "zoho_access_mock_token_12345"
    token_manager._expires_at_mono = clock.monotonic() + 3600
    client = ZohoClient(
        token_manager=token_manager,
        org_id="org_kaveri_blr_001",
        clock=clock,
        http_client=http_client,
        base_url_override="http://test/inventory/v1",
    )
    monkeypatch.setattr(live_assert, "_configured_client", lambda: client)

    async def forbid_mutation(method: str, *args: Any, **kwargs: Any) -> Any:
        if method.upper() != "GET":
            raise AssertionError("live assertion harness attempted a non-GET request")
        return await original_request(method, *args, **kwargs)

    original_request = client._http_client.request
    monkeypatch.setattr(client._http_client, "request", forbid_mutation)
    config = {
        "items": [{"sku": "KHG-CUSH-001", "expect": {"status": "in_stock"}}],
        "orders": [
            {
                "reference_number": "order_RzpKav1001",
                "expect": {"found": True, "completeness": "complete", "delivery_proof": "present"},
            }
        ],
    }
    assert await live_assert.run(config) == 0
    output = capsys.readouterr().out
    assert "PASS item 001" in output
    assert "PASS order 001" in output
