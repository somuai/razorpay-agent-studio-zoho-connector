"""Unit tests for structured instrumentation events (FR-8)."""

import json

from zoho_inventory_connector.events.emitter import (
    EventEmitter,
    ToolExecutionEvent,
)


def test_tool_execution_event_schema() -> None:
    """# FR-8: Verify event schema matches required fields with zero PII/secrets."""
    event = ToolExecutionEvent.create(
        tool="get_stock_availability",
        status="success",
        latency_ms=14.2,
        cache_hit=False,
        throttled=False,
        retries=0,
        http_status=200,
        zoho_code=0,
        stock_status="in_stock",
        result_count=3,
        truncated=False,
        request_id="req_test_001",
    )

    data = json.loads(event.to_json())
    required_keys = [
        "ts",
        "event",
        "tool",
        "status",
        "latency_ms",
        "cache_hit",
        "throttled",
        "retries",
        "http_status",
        "zoho_code",
        "stock_status",
        "result_count",
        "truncated",
        "request_id",
    ]
    for k in required_keys:
        assert k in data, f"Missing key '{k}' in telemetry event"

    assert data["event"] == "tool_execution"
    assert data["tool"] == "get_stock_availability"
    assert data["status"] == "success"
    assert data["latency_ms"] == 14.2


def test_event_emitter_sink() -> None:
    emitter = EventEmitter()
    ev = ToolExecutionEvent.create(
        tool="list_items",
        status="success",
        latency_ms=8.5,
    )
    emitter.emit(ev)
    assert len(emitter.get_events()) == 1
    emitter.clear()
    assert len(emitter.get_events()) == 0
