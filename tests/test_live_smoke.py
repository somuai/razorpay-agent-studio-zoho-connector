"""Masking checks for live-smoke's screenshot-safe projection."""

import asyncio

from examples import live_smoke
from examples.live_smoke import _summary
from zoho_inventory_connector.client.errors import AuthError


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


def test_smoke_fails_fast_after_one_token_acquisition_failure(monkeypatch, capsys) -> None:
    token_attempts = 0
    tool_calls = 0

    class FailedTokenManager:
        async def get_access_token(self) -> str:
            nonlocal token_attempts
            token_attempts += 1
            raise AuthError(message="Zoho Accounts refresh rejected: invalid_grant")

    class MinimalClient:
        async def aclose(self) -> None:
            return None

    def unexpected_tool(*args, **kwargs):
        nonlocal tool_calls
        tool_calls += 1
        raise AssertionError("tool should not run after token acquisition fails")

    monkeypatch.setenv("ZOHO_CLIENT_ID", "test-client")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("ZOHO_ORG_ID", "999888777666555")
    monkeypatch.setattr(live_smoke, "TokenManager", lambda **_: FailedTokenManager())
    monkeypatch.setattr(live_smoke, "ZohoClient", lambda **_: MinimalClient())
    monkeypatch.setattr(live_smoke.server, "list_items", unexpected_tool)

    assert asyncio.run(live_smoke._run()) == 1
    output = capsys.readouterr().out
    assert '"phase": "token_acquisition"' in output
    assert "invalid_grant" in output
    assert token_attempts == 1
    assert tool_calls == 0
