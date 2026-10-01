"""Tool specification export and drift checks (FR-5.1)."""

import json
from pathlib import Path

import pytest

from zoho_inventory_connector.mcp_server import spec


@pytest.mark.asyncio
async def test_generated_spec_is_sorted_and_describes_registered_tools() -> None:
    result = await spec.generate_spec_dict()
    names = [tool["name"] for tool in result["tools"]]
    assert result["server_name"] == "zoho-inventory-connector"
    assert result["tool_count"] == 8
    assert names == sorted(names)
    assert {"get_stock_availability", "get_order_fulfillment_evidence"}.issubset(names)
    assert all("input_schema" in tool and tool["description"] for tool in result["tools"])


def test_spec_cli_writes_formatted_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "nested" / "tool_spec.json"
    monkeypatch.setattr(spec, "SPEC_PATH", target)
    monkeypatch.setattr("sys.argv", ["spec"])

    spec.main()

    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk["tool_count"] == 8
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_spec_verify_reports_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spec, "SPEC_PATH", tmp_path / "missing.json")
    monkeypatch.setattr("sys.argv", ["spec", "--verify"])
    with pytest.raises(SystemExit) as exc_info:
        spec.main()
    assert exc_info.value.code == 1


def test_spec_verify_rejects_drift_and_accepts_current_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "tool_spec.json"
    monkeypatch.setattr(spec, "SPEC_PATH", target)
    monkeypatch.setattr("sys.argv", ["spec", "--verify"])
    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        spec.main()
    assert exc_info.value.code == 1

    monkeypatch.setattr("sys.argv", ["spec"])
    spec.main()
    monkeypatch.setattr("sys.argv", ["spec", "--verify"])
    with pytest.raises(SystemExit) as exc_info:
        spec.main()
    assert exc_info.value.code == 0
