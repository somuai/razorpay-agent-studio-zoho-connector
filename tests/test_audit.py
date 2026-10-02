"""Unit tests for compliance audit logging and PII stripping (FR-15)."""

import json
import os
import stat

import pytest

from zoho_inventory_connector.client.errors import AuditSinkError
from zoho_inventory_connector.events.audit import (
    AuditEvent,
    AuditLogger,
    sanitize_audit_params,
)


def test_sanitize_audit_params_pii_and_secrets() -> None:
    """# FR-15: Parameters in audit records must have secrets redacted and PII masked."""
    params = {
        "customer_email": "ananya.rao@example.com",
        "customer_phone": "+91 98765 12345",
        "reference_number": "order_Rzp_001",
        "query": "customer name and private free text",
        "auth_token": "zoho_super_secret_token_abc",
        "client_secret": "my_client_secret_xyz",
        "page": 1,
    }

    sanitized = sanitize_audit_params(params)
    assert sanitized["customer_email"] == "a***o@example.com"
    assert sanitized["customer_phone"] == "******2345"
    assert sanitized["reference_number"] == "[MASKED]"
    assert sanitized["query"] == "[OMITTED]"
    assert sanitized["auth_token"] == "[REDACTED_SECRET]"
    assert sanitized["client_secret"] == "[REDACTED_SECRET]"
    assert sanitized["page"] == 1


def test_audit_event_creation_and_recording() -> None:
    """# FR-15: Audit event structure and persistence."""
    logger = AuditLogger()
    event = AuditEvent.create(
        tool="get_sales_order",
        parameters={"salesorder_id": "so_2001", "email": "buyer@test.com"},
        request_id="req_test_123",
    )
    logger.record(event)

    records = logger.get_records()
    assert len(records) == 1
    rec = records[0]
    assert rec.tool == "get_sales_order"
    assert rec.request_id == "req_test_123"
    assert rec.parameters["email"] == "b***r@test.com"
    assert "timestamp" in rec.__dict__

    # JSON serialization
    serialized = json.loads(rec.to_json())
    assert serialized["event"] == "audit_tool_invocation"


def test_audit_jsonl_sink_is_private_and_separate_from_stderr(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """# FR-15: Audit writes to its own private stream, not application stderr."""
    target = tmp_path / "audit" / "events.jsonl"
    target.parent.mkdir()
    target.write_text("", encoding="utf-8")
    os.chmod(target, 0o644)
    logger = AuditLogger(target)
    logger.record(
        AuditEvent.create("search_items", {"query": "private free text"}, "req_audit_test")
    )

    assert capsys.readouterr().err == ""
    record = json.loads(target.read_text(encoding="utf-8"))
    assert record["parameters"]["query"] == "[OMITTED]"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_audit_sink_failure_fails_closed(tmp_path) -> None:
    blocker = tmp_path / "not_a_directory"
    blocker.write_text("", encoding="utf-8")
    logger = AuditLogger(blocker / "events.jsonl")

    with pytest.raises(AuditSinkError, match="audit record could not be saved"):
        logger.record(AuditEvent.create("list_items", {}, "req_sink_failure"))
    assert logger.get_records() == []
