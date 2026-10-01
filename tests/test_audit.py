"""Unit tests for compliance audit logging and PII stripping (FR-15)."""

import json

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
        "auth_token": "zoho_super_secret_token_abc",
        "client_secret": "my_client_secret_xyz",
        "page": 1,
    }

    sanitized = sanitize_audit_params(params)
    assert sanitized["customer_email"] == "a***o@example.com"
    assert sanitized["customer_phone"] == "******2345"
    assert sanitized["reference_number"] == "order_Rzp_001"
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
