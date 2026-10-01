"""Audit logging module for tool calls with PII stripping (FR-15).

Maintains an immutable record of tool invocations, sanitized parameters,
and correlation identifiers, separate from application logs.
"""

import json
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from zoho_inventory_connector.models.order import mask_email, mask_phone

SENSITIVE_PARAM_KEYS = {
    "customer_email",
    "email",
    "phone",
    "customer_phone",
    "authorization",
    "token",
}


def sanitize_audit_params(params: dict[str, Any]) -> dict[str, Any]:
    """Sanitize parameters dictionary for audit recording by stripping/masking PII (FR-15)."""
    sanitized: dict[str, Any] = {}
    for key, val in params.items():
        lower_k = key.lower()
        if "token" in lower_k or "secret" in lower_k or "auth" in lower_k:
            sanitized[key] = "[REDACTED_SECRET]"
        elif "email" in lower_k and isinstance(val, str):
            sanitized[key] = mask_email(val)
        elif "phone" in lower_k and isinstance(val, str):
            sanitized[key] = mask_phone(val)
        else:
            sanitized[key] = val
    return sanitized


@dataclass
class AuditEvent:
    """Audit event recording an authorized tool invocation (FR-15)."""

    timestamp: str
    event: str
    tool: str
    parameters: dict[str, Any]
    request_id: str

    @classmethod
    def create(
        cls,
        tool: str,
        parameters: dict[str, Any],
        request_id: str | None = None,
    ) -> "AuditEvent":
        return cls(
            timestamp=datetime.now(UTC).isoformat(),
            event="audit_tool_invocation",
            tool=tool,
            parameters=sanitize_audit_params(parameters),
            request_id=request_id or f"req_{uuid.uuid4().hex[:12]}",
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


class AuditLogger:
    """Sink for compliance and audit trail records."""

    def __init__(self) -> None:
        self.audit_records: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        """Store audit record and output to stderr (NFR-8)."""
        self.audit_records.append(event)
        sys.stderr.write(f"[AUDIT] {event.to_json()}\n")
        sys.stderr.flush()

    def get_records(self) -> list[AuditEvent]:
        return list(self.audit_records)

    def clear(self) -> None:
        self.audit_records.clear()


# Default singleton instance
default_audit_logger = AuditLogger()
