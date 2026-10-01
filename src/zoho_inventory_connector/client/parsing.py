"""Strict parsers for values received from Zoho response payloads."""

import math
from typing import Any

from zoho_inventory_connector.client.errors import InvalidResponseError


def parse_upstream_float(value: Any, field: str, default: float = 0.0) -> float:
    """Parse a finite numeric field or raise a safe typed upstream-data error."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise InvalidResponseError(field)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise InvalidResponseError(field) from None
    if not math.isfinite(number):
        raise InvalidResponseError(field)
    return number
