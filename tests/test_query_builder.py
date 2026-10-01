"""Unit tests for Validated Query Builder (FR-5.5, FR-13)."""

import pytest

from zoho_inventory_connector.client.errors import InputValidationError
from zoho_inventory_connector.client.query_builder import ValidatedQueryBuilder


def test_valid_search_text() -> None:
    text = ValidatedQueryBuilder.validate_search_text("Silk Pillowcase", field_name="query")
    assert text == "Silk Pillowcase"


@pytest.mark.parametrize(
    "malicious_input",
    [
        "item' OR '1'='1",
        'item" OR "1"="1',
        "item; DROP TABLE items; --",
        "item&organization_id=99999",
        "item?hack=1",
        "item%26admin=true",
        "item%3Fextra=1",
        "item/*comment*/name",
        "item--test",
        "item\nSELECT *",
        "item\x00hidden",
    ],
)
def test_search_text_injection_rejection(malicious_input: str) -> None:
    """# FR-13: Assert operator injection, quote escaping, and delimiters are rejected."""
    with pytest.raises(InputValidationError) as exc_info:
        ValidatedQueryBuilder.validate_search_text(malicious_input, field_name="query")
    assert "prohibited characters" in exc_info.value.reason.lower()
    assert exc_info.value.http_status == 400


def test_search_text_length_limit() -> None:
    """# FR-13: Assert excessive length queries are rejected."""
    long_input = "a" * 101
    with pytest.raises(InputValidationError) as exc_info:
        ValidatedQueryBuilder.validate_search_text(long_input, max_length=100)
    assert "maximum allowed length" in exc_info.value.reason.lower()


def test_valid_numeric_id() -> None:
    val = ValidatedQueryBuilder.validate_numeric_id("982341209384", field_name="item_id")
    assert val == "982341209384"


@pytest.mark.parametrize(
    "invalid_id",
    [
        "item_123",
        "-123",
        "123; DROP",
        "123 456",
        "abc",
        "",
        "123456789012345678901234567",  # > 25 digits
    ],
)
def test_numeric_id_validation_failures(invalid_id: str) -> None:
    with pytest.raises(InputValidationError) as exc_info:
        ValidatedQueryBuilder.validate_numeric_id(invalid_id, field_name="item_id")
    assert (
        "numeric digits" in exc_info.value.reason.lower()
        or "cannot be null" in exc_info.value.reason.lower()
    )


def test_sku_validation() -> None:
    assert ValidatedQueryBuilder.validate_sku("SKU-BED-001_A.1/B") == "SKU-BED-001_A.1/B"

    with pytest.raises(InputValidationError):
        ValidatedQueryBuilder.validate_sku("SKU' OR 1=1")

    with pytest.raises(InputValidationError):
        ValidatedQueryBuilder.validate_sku("SKU with spaces")

    with pytest.raises(InputValidationError):
        ValidatedQueryBuilder.validate_sku("a" * 51)


def test_reference_number_validation() -> None:
    assert ValidatedQueryBuilder.validate_reference_number("order_Kav123#01") == "order_Kav123#01"

    with pytest.raises(InputValidationError):
        ValidatedQueryBuilder.validate_reference_number("order;DROP")


def test_iso_date_validation() -> None:
    assert (
        ValidatedQueryBuilder.validate_iso_date("2026-10-01", field_name="date_from")
        == "2026-10-01"
    )

    with pytest.raises(InputValidationError):
        ValidatedQueryBuilder.validate_iso_date("01-10-2026", field_name="date_from")

    with pytest.raises(InputValidationError):
        ValidatedQueryBuilder.validate_iso_date("2026-02-31", field_name="date_from")  # Invalid day


def test_status_validation() -> None:
    allowed = {"active", "inactive"}
    assert ValidatedQueryBuilder.validate_status("ACTIVE", allowed=allowed) == "active"

    with pytest.raises(InputValidationError) as exc_info:
        ValidatedQueryBuilder.validate_status("pending", allowed=allowed)
    assert "must be one of" in exc_info.value.reason.lower()


def test_pagination_bounds() -> None:
    p, pp = ValidatedQueryBuilder.validate_pagination(page=2, per_page=25, max_per_page=50)
    assert p == 2
    assert pp == 25

    with pytest.raises(InputValidationError):
        ValidatedQueryBuilder.validate_pagination(page=0, per_page=25)

    with pytest.raises(InputValidationError):
        ValidatedQueryBuilder.validate_pagination(page=1, per_page=100, max_per_page=50)


def test_query_builder_params_assembly() -> None:
    builder = ValidatedQueryBuilder()
    builder.add_param("search_text", "Pillow")
    builder.add_int_param("page", 1)
    builder.add_int_param("per_page", 20)

    params = builder.params
    assert params == {"search_text": "Pillow", "page": "1", "per_page": "20"}
