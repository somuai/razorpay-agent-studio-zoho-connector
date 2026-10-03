"""Offline coverage for the order-tool PII masking command."""

import asyncio

from examples import live_pii_check


def test_mock_pii_check_calls_order_tools_with_pii_disabled_and_scans_output(
    capsys, monkeypatch
) -> None:
    calls: list[tuple[str, bool]] = []
    search = live_pii_check.server.search_sales_orders
    detail = live_pii_check.server.get_sales_order

    async def checked_search(*args, **kwargs):
        calls.append(("search_sales_orders", kwargs["include_pii"]))
        return await search(*args, **kwargs)

    async def checked_detail(*args, **kwargs):
        calls.append(("get_sales_order", kwargs["include_pii"]))
        return await detail(*args, **kwargs)

    monkeypatch.setattr(live_pii_check.server, "search_sales_orders", checked_search)
    monkeypatch.setattr(live_pii_check.server, "get_sales_order", checked_detail)

    assert asyncio.run(live_pii_check._run(mock=True)) == 0
    output = capsys.readouterr().out
    assert calls == [("search_sales_orders", False), ("get_sales_order", False)]
    assert live_pii_check.MOCK_EMAIL not in output
    assert live_pii_check.MOCK_PHONE not in output
    assert 'customer_email": "[MASKED]' in output
    assert 'customer_phone": "[MASKED]' in output
    assert "no raw test email" in output


def test_output_scanner_reports_only_safe_finding_labels() -> None:
    raw = "customer_001@example.com +91987651001"
    findings = live_pii_check._scan_output(
        raw, live_pii_check.MOCK_EMAIL, live_pii_check.MOCK_PHONE
    )
    assert findings == [
        "raw test email appeared in output",
        "raw test phone appeared in output",
        "email-shaped text appeared in output",
        "8+ digit sequence appeared in output",
    ]
    assert live_pii_check.MOCK_EMAIL not in "; ".join(findings)
    assert live_pii_check.MOCK_PHONE not in "; ".join(findings)
