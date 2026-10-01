"""Audit logging module for tool calls with PII stripping (FR-15).

Maintains an immutable record of tool invocations, sanitized parameters,
and correlation identifiers, separate from application logs.
"""

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zoho_inventory_connector.client.errors import AuditSinkError
from zoho_inventory_connector.models.order import mask_email, mask_phone


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
        elif lower_k in {"query", "search", "search_text", "free_text"}:
            sanitized[key] = "[OMITTED]"
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
    """Private JSONL audit sink, separate from application and telemetry logs."""

    def __init__(self, log_file: Path | str | None = None) -> None:
        self.audit_records: list[AuditEvent] = []
        self.log_file = Path(log_file) if log_file else None

    def record(self, event: AuditEvent) -> None:
        """Store in memory and append a mode-0600 record to the separate audit file."""
        if self.log_file is None:
            self.audit_records.append(event)
            return
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            fd = os.open(self.log_file, flags, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                stream.write(event.to_json() + "\n")
            self.audit_records.append(event)
        except OSError as exc:
            raise AuditSinkError(event.tool, event.request_id) from exc

    def get_records(self) -> list[AuditEvent]:
        return list(self.audit_records)

    def clear(self) -> None:
        self.audit_records.clear()


# Default singleton instance
default_audit_logger = AuditLogger(os.environ.get("ZOHO_AUDIT_LOG_FILE", ".zoho_audit.jsonl"))
