"""Validated Query Builder for Zoho Inventory API (FR-5.5, FR-13).

Guarantees that untrusted agent inputs are sanitized and validated against
strict allowlists, bounded lengths, and character sets before being sent upstream.
"""

import re
from datetime import datetime
from typing import Any

from zoho_inventory_connector.client.errors import InputValidationError

# Prohibited injection patterns: URL delimiters, SQL/NoSQL operators, shell escapes
PROHIBITED_CHARS_PATTERN = re.compile(
    r"['\";&?=\x00-\x1f\x7f]|--|/\*|\*/|%26|%3f|%3d", re.IGNORECASE
)
ALPHANUMERIC_ID_PATTERN = re.compile(r"^\d{1,25}$")
SAFE_SKU_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.\/]{1,50}$")
SAFE_REF_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.\/#:]{1,64}$")
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SAFE_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+$")


class ValidatedQueryBuilder:
    """Builder and validator for Zoho Inventory API GET query parameters."""

    def __init__(self) -> None:
        self._params: dict[str, str] = {}

    @property
    def params(self) -> dict[str, str]:
        return self._params.copy()

    @staticmethod
    def validate_search_text(
        text: str | None, field_name: str = "query", max_length: int = 100
    ) -> str | None:
        """Validate search text against length limits and injection delimiters."""
        if text is None:
            return None
        text_clean = text.strip()
        if not text_clean:
            return None
        if len(text_clean) > max_length:
            raise InputValidationError(
                field=field_name,
                value=text[:20] + "...",
                reason=f"Query text exceeds maximum allowed length of {max_length} characters.",
            )
        if PROHIBITED_CHARS_PATTERN.search(text_clean):
            raise InputValidationError(
                field=field_name,
                value=text_clean,
                reason="Query contains prohibited characters (quotes, parameter delimiters, or escape sequences).",
            )
        return text_clean

    @staticmethod
    def validate_numeric_id(val: Any, field_name: str) -> str:
        """Validate numeric Zoho resource identifiers (e.g., item_id, salesorder_id)."""
        if val is None:
            raise InputValidationError(
                field=field_name, value="None", reason="Identifier cannot be null."
            )
        str_val = str(val).strip()
        if not ALPHANUMERIC_ID_PATTERN.match(str_val):
            raise InputValidationError(
                field=field_name,
                value=str_val,
                reason="Zoho identifiers must consist only of 1 to 25 numeric digits.",
            )
        return str_val

    @staticmethod
    def validate_sku(sku: str | None, field_name: str = "sku") -> str | None:
        """Validate an inventory SKU string."""
        if sku is None:
            return None
        sku_clean = sku.strip()
        if not sku_clean:
            return None
        if not SAFE_SKU_PATTERN.match(sku_clean):
            raise InputValidationError(
                field=field_name,
                value=sku_clean,
                reason="SKU must be 1-50 characters consisting of letters, digits, '-', '_', '.', or '/'.",
            )
        return sku_clean

    @staticmethod
    def validate_reference_number(
        ref: str | None, field_name: str = "reference_number"
    ) -> str | None:
        """Validate an order reference or Razorpay payment identifier."""
        if ref is None:
            return None
        ref_clean = ref.strip()
        if not ref_clean:
            return None
        if not SAFE_REF_PATTERN.match(ref_clean):
            raise InputValidationError(
                field=field_name,
                value=ref_clean,
                reason="Reference number contains invalid characters or exceeds 64 characters.",
            )
        return ref_clean

    @staticmethod
    def validate_email(email: str | None, field_name: str = "customer_email") -> str | None:
        """Validate customer email filter."""
        if email is None:
            return None
        email_clean = email.strip()
        if not email_clean:
            return None
        if len(email_clean) > 100 or not SAFE_EMAIL_PATTERN.match(email_clean):
            raise InputValidationError(
                field=field_name,
                value=email_clean,
                reason="Invalid email address format.",
            )
        return email_clean

    @staticmethod
    def validate_iso_date(date_str: str | None, field_name: str) -> str | None:
        """Validate ISO 8601 calendar date string (YYYY-MM-DD)."""
        if date_str is None:
            return None
        date_clean = date_str.strip()
        if not date_clean:
            return None
        if not ISO_DATE_PATTERN.match(date_clean):
            raise InputValidationError(
                field=field_name,
                value=date_clean,
                reason="Date must be formatted as YYYY-MM-DD (ISO 8601).",
            )
        try:
            datetime.strptime(date_clean, "%Y-%m-%d")
        except ValueError:
            raise InputValidationError(
                field=field_name,
                value=date_clean,
                reason="Date is not a valid calendar day.",
            ) from None
        return date_clean

    @staticmethod
    def validate_status(
        status: str | None, allowed: set[str], field_name: str = "status"
    ) -> str | None:
        """Validate status against an allowed enum set."""
        if status is None:
            return None
        status_clean = status.strip().lower()
        if not status_clean:
            return None
        if status_clean not in allowed:
            allowed_list = ", ".join(sorted(allowed))
            raise InputValidationError(
                field=field_name,
                value=status,
                reason=f"Status must be one of: [{allowed_list}].",
            )
        return status_clean

    @staticmethod
    def validate_pagination(
        page: int | None, per_page: int | None, max_per_page: int = 50
    ) -> tuple[int, int]:
        """Validate pagination page and per_page limits."""
        p = page if page is not None else 1
        pp = per_page if per_page is not None else max_per_page

        if p < 1 or p > 1000:
            raise InputValidationError(
                field="page",
                value=str(p),
                reason="Page number must be an integer between 1 and 1000.",
            )
        if pp < 1 or pp > max_per_page:
            raise InputValidationError(
                field="per_page",
                value=str(pp),
                reason=f"per_page must be an integer between 1 and {max_per_page}.",
            )
        return p, pp

    def add_param(self, key: str, value: str | None) -> "ValidatedQueryBuilder":
        """Add a validated string parameter."""
        if value is not None and value != "":
            self._params[key] = value
        return self

    def add_int_param(self, key: str, value: int | None) -> "ValidatedQueryBuilder":
        """Add a validated integer parameter."""
        if value is not None:
            self._params[key] = str(value)
        return self
