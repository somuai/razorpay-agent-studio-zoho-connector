"""Masking checks for live-smoke's screenshot-safe projection."""

from examples.live_smoke import _summary


def test_summary_never_includes_identifier_contact_or_tracking_values() -> None:
    result = {
        "items": [
            {
                "organization_id": "organization-private-123",
                "email": "private@example.com",
                "phone": "+91 9999999999",
                "tracking_number": "TRACKING-PRIVATE-123",
            }
        ],
        "organization_id": "organization-private-123",
        "as_of": "2026-10-02T00:00:00+00:00",
        "cached": False,
    }
    rendered = str(_summary(result))
    for secret in (
        "organization-private-123",
        "private@example.com",
        "+91 9999999999",
        "TRACKING-PRIVATE-123",
    ):
        assert secret not in rendered
    assert "result_count" in rendered


def test_error_summary_drops_upstream_exception_text() -> None:
    rendered = str(
        _summary(
            {
                "error": "UpstreamError",
                "message": "token-private email@example.com tracking-private-123",
                "retryable": True,
            }
        )
    )
    assert "token-private" not in rendered
    assert "email@example.com" not in rendered
    assert "tracking-private-123" not in rendered


def test_transport_error_summary_keeps_only_safe_transport_metadata() -> None:
    rendered = str(
        _summary(
            {
                "error": "UpstreamError",
                "message": "private exception text",
                "retryable": True,
                "transport_diagnostic": {
                    "exception_class": "ConnectError",
                    "cause_classes": ["OSError"],
                    "phase": "connect",
                    "host": "www.zohoapis.in",
                    "attempt": 4,
                    "proxy_env_names": ["HTTPS_PROXY"],
                },
            }
        )
    )
    assert "ConnectError" in rendered
    assert "www.zohoapis.in" in rendered
    assert "private exception text" not in rendered
