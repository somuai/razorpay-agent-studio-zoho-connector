"""Unit tests for Pydantic projection models, normalization, and privacy masking (FR-6.1, FR-6.3)."""

from zoho_inventory_connector.models.order import (
    SalesOrderProjection,
    mask_email,
    mask_name,
    mask_phone,
)


def test_pii_masking_helpers() -> None:
    """# FR-6.3: Verify customer email, phone, and name masking."""
    assert mask_email("priya.sharma@example.com") == "p***a@example.com"
    assert mask_email("ab@domain.com") == "a***@domain.com"
    assert mask_email(None) is None

    assert mask_phone("+91 98765 43210") == "******3210"
    assert mask_phone("9876543210") == "******3210"
    assert mask_phone(None) is None

    assert mask_name("Priya Sharma") == "Priya S."
    assert mask_name("Ananya") == "Ananya"
    assert mask_name(None) is None


def test_sales_order_projection_masking_default() -> None:
    """# FR-6.1, FR-6.3: Default projection masks customer PII unless include_pii=True."""
    raw_order = {
        "salesorder_id": "so_12345",
        "salesorder_number": "SO-00123",
        "date": "2026-09-15",
        "status": "confirmed",
        "customer_id": "cust_999",
        "customer_name": "Vikram Malhotra",
        "customer_email": "vikram.m@kaveri.in",
        "customer_phone": "+919876543210",
        "reference_number": "order_Rzp_789",
        "total": 2499.00,
        "currency_code": "INR",
        "internal_zoho_secret_db_id": "SECRET_SHOULD_NEVER_LEAK",
        "line_items": [
            {
                "item_id": "item_101",
                "name": "Silk Pillowcase",
                "quantity": 2,
                "rate": 1249.50,
                "item_total": 2499.00,
            }
        ],
    }

    # Masked by default
    proj_masked = SalesOrderProjection.from_raw_zoho(raw_order, include_pii=False)
    d_masked = proj_masked.model_dump()

    assert d_masked["customer_name"] == "Vikram M."
    assert d_masked["customer_email"] == "v***m@kaveri.in"
    assert d_masked["customer_phone"] == "******3210"
    assert d_masked["total_amount"] == 2499.00
    assert "internal_zoho_secret_db_id" not in d_masked

    # Unmasked when include_pii=True
    proj_unmasked = SalesOrderProjection.from_raw_zoho(raw_order, include_pii=True)
    d_unmasked = proj_unmasked.model_dump()
    assert d_unmasked["customer_name"] == "Vikram Malhotra"
    assert d_unmasked["customer_email"] == "vikram.m@kaveri.in"
    assert d_unmasked["customer_phone"] == "+919876543210"
