"""Pydantic projection models for Sales Orders and customer privacy masking (FR-6.1, FR-6.3)."""

import re

from pydantic import BaseModel, ConfigDict, Field

from zoho_inventory_connector.client.parsing import parse_optional_upstream_float


def mask_email(email: str | None) -> str | None:
    """Mask email address for privacy (e.g. 'priya.sharma@example.com' -> 'p***a@example.com')."""
    if not email or "@" not in email:
        return email
    local_part, domain = email.split("@", 1)
    if len(local_part) <= 2:
        masked_local = local_part[0] + "***"
    else:
        masked_local = local_part[0] + "***" + local_part[-1]
    return f"{masked_local}@{domain}"


def mask_phone(phone: str | None) -> str | None:
    """Mask phone number, keeping only last 4 digits (e.g. '+91 9876543210' -> '******3210')."""
    if not phone:
        return phone
    digits_only = re.sub(r"\D", "", phone)
    if len(digits_only) <= 4:
        return "****"
    last_four = digits_only[-4:]
    return f"******{last_four}"


def mask_name(name: str | None) -> str | None:
    """Partially mask customer name (e.g. 'Priya Sharma' -> 'Priya S.')."""
    if not name:
        return name
    parts = name.strip().split()
    if len(parts) <= 1:
        return name
    return f"{parts[0]} {parts[-1][0]}."


class SalesOrderLineItem(BaseModel):
    """Projection of sales order line item."""

    model_config = ConfigDict(extra="ignore")

    item_id: str
    sku: str | None = None
    name: str
    quantity: float | None = None
    rate: float | None = None
    item_total: float | None = None


class SalesOrderProjection(BaseModel):
    """Normalized projection of a Zoho Sales Order record (FR-6.1)."""

    model_config = ConfigDict(extra="ignore")

    salesorder_id: str
    salesorder_number: str
    date: str = Field(description="Order date in ISO 8601 format (YYYY-MM-DD)")
    status: str
    customer_id: str
    customer_name: str
    customer_email: str | None = None
    customer_phone: str | None = None
    reference_number: str | None = None
    total_amount: float | None = None
    currency_code: str = "INR"
    line_items_count: int = 0
    line_items: list[SalesOrderLineItem] = Field(default_factory=list)
    match_basis: str | None = Field(
        default=None,
        description="Explains how the order was matched (e.g. reference_number_exact, customer_email) (FR-5.3)",
    )

    @classmethod
    def from_raw_zoho(
        cls,
        raw: dict[str, object],
        include_pii: bool = False,
        match_basis: str | None = None,
    ) -> "SalesOrderProjection":
        """Construct normalized projection with default PII redaction (FR-6.3)."""
        raw_name = str(raw.get("customer_name") or "")
        raw_email = str(raw.get("email") or raw.get("customer_email") or "")
        raw_phone = str(raw.get("phone") or raw.get("customer_phone") or "")

        name = raw_name if include_pii else mask_name(raw_name) or "Customer"
        email = raw_email if include_pii else mask_email(raw_email)
        phone = raw_phone if include_pii else mask_phone(raw_phone)

        line_items_raw = raw.get("line_items") or []
        items_list: list[SalesOrderLineItem] = []
        if isinstance(line_items_raw, list):
            for li in line_items_raw:
                if isinstance(li, dict):
                    items_list.append(
                        SalesOrderLineItem(
                            item_id=str(li.get("item_id") or ""),
                            sku=str(li.get("sku") or "") or None,
                            name=str(li.get("name") or "Item"),
                            quantity=parse_optional_upstream_float(
                                li.get("quantity"), "line_items.quantity"
                            ),
                            rate=parse_optional_upstream_float(li.get("rate"), "line_items.rate"),
                            item_total=parse_optional_upstream_float(
                                li.get("item_total"), "line_items.item_total"
                            ),
                        )
                    )

        return cls(
            salesorder_id=str(raw.get("salesorder_id") or ""),
            salesorder_number=str(raw.get("salesorder_number") or ""),
            date=str(raw.get("date") or ""),
            status=str(raw.get("status") or ""),
            customer_id=str(raw.get("customer_id") or ""),
            customer_name=name,
            customer_email=email,
            customer_phone=phone,
            reference_number=str(raw.get("reference_number") or "") or None,
            total_amount=parse_optional_upstream_float(raw.get("total"), "total"),
            currency_code=str(raw.get("currency_code") or "INR"),
            line_items_count=len(items_list),
            line_items=items_list,
            match_basis=match_basis,
        )
