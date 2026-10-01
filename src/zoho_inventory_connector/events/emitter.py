"""Structured instrumentation event emitter (FR-8).

Emits structured JSON events (one per tool execution) strictly devoid of PII,
authorization tokens, and customer secrets.
"""

import json
import logging
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

# Logger dedicated to telemetry events; outputs to stderr by default (NFR-8)
_logger = logging.getLogger("zoho_connector.telemetry")


@dataclass
class ToolExecutionEvent:
    """Structured telemetry event schema (FR-8)."""

    ts: str
    event: str
    tool: str
    status: str  # "success" or "error"
    latency_ms: float
    cache_hit: bool
    throttled: bool
    retries: int
    http_status: int | None
    zoho_code: int | None
    stock_status: str | None
    result_count: int
    truncated: bool
    request_id: str

    @classmethod
    def create(
        cls,
        tool: str,
        status: str,
        latency_ms: float,
        cache_hit: bool = False,
        throttled: bool = False,
        retries: int = 0,
        http_status: int | None = 200,
        zoho_code: int | None = 0,
        stock_status: str | None = None,
        result_count: int = 1,
        truncated: bool = False,
        request_id: str | None = None,
    ) -> "ToolExecutionEvent":
        return cls(
            ts=datetime.now(UTC).isoformat(),
            event="tool_execution",
            tool=tool,
            status=status,
            latency_ms=round(latency_ms, 2),
            cache_hit=cache_hit,
            throttled=throttled,
            retries=retries,
            http_status=http_status,
            zoho_code=zoho_code,
            stock_status=stock_status,
            result_count=result_count,
            truncated=truncated,
            request_id=request_id or f"req_{uuid.uuid4().hex[:12]}",
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


class EventEmitter:
    """In-memory event sink and structured log emitter."""

    def __init__(self) -> None:
        self.events: list[ToolExecutionEvent] = []

    def emit(self, event: ToolExecutionEvent) -> None:
        """Record event in memory and write JSON to stderr (NFR-8)."""
        self.events.append(event)
        # Stdio hygiene: Always write logs to stderr, never stdout (NFR-8)
        sys.stderr.write(f"[TELEMETRY] {event.to_json()}\n")
        sys.stderr.flush()

    def get_events(self) -> list[ToolExecutionEvent]:
        return list(self.events)

    def clear(self) -> None:
        self.events.clear()


# Default singleton instance
default_emitter = EventEmitter()
