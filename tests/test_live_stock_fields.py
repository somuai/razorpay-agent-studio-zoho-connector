"""Offline coverage for live stock-field comparison and privacy scans."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from examples import live_stock_fields as command


def test_mock_run_fetches_each_item_detail_once_and_emits_scanned_table(
    monkeypatch, capsys
) -> None:
    original = command._mock_client
    client = original()
    calls: list[str] = []
    original_get = client._http_client.get

    async def counted_get(url, *args, **kwargs):
        if "/items/" in str(url):
            calls.append(str(url))
        return await original_get(url, *args, **kwargs)

    monkeypatch.setattr(client._http_client, "get", counted_get)
    monkeypatch.setattr(command, "_mock_client", lambda: client)

    assert asyncio.run(command.run(mock=True, ui_path=Path("/missing/live_ui_values.yaml"))) == 0
    output = capsys.readouterr().out
    assert len(calls) == 10
    assert "MOCK / SIMULATED (offline)" in output
    assert "connector source" in output
    assert "Identifier scan: SAFE" in output
    assert "zoho_access_mock_token" not in output
    assert command.LONG_DIGITS.search(output) is None


def test_load_ui_values_accepts_json_yaml_and_nulls(tmp_path: Path) -> None:
    path = tmp_path / "values.yaml"
    path.write_text(
        json.dumps({"items": [{"sku": "KHG-001", "on_hand": 12, "available_for_sale": None}]}),
        encoding="utf-8",
    )
    assert command.load_ui_values(path) == {
        "KHG-001": {"on_hand": 12.0, "available_for_sale": None}
    }


def test_render_reports_api_key_match_and_incomplete_ui_values() -> None:
    rows = [
        {
            "sku": "KHG-001",
            "fields": {
                "stock_on_hand": 20,
                "available_for_sale": 17,
                "actual_available_stock": 17,
            },
            "source": "actual_available_stock",
            "quantity": 17,
            "status": "in_stock",
        }
    ]
    ui = {"KHG-001": {"on_hand": 20, "available_for_sale": 17}}
    output = command.render(rows, ui, "MOCK")
    assert "UI on-hand match" in output
    assert "MATCH: stock_on_hand" in output
    assert "MATCH: available_for_sale,actual_available_stock" in output
    assert "YES (1/1; 0 UI values not recorded)" in output

    incomplete = command.render(rows, {}, "MOCK")
    assert "INCONCLUSIVE (UI values not recorded)" in incomplete


def test_identifier_scanner_masks_digits_and_labels_email() -> None:
    findings = command._scan("KHG-001 | stock_on_hand=123456789 | person@example.com")
    assert findings == [
        "line 1: KHG-001 | stock_on_hand=[MASKED_DIGITS] | [MASKED_EMAIL]",
        "line 1: [email-shaped text masked]",
    ]
    assert "123456789" not in " ".join(findings)
    assert "person@example.com" not in " ".join(findings)
