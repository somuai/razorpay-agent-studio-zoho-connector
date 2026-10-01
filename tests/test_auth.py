"""Unit and concurrency tests for OAuth and TokenManager (FR-1)."""

import asyncio
import logging
import os
import stat
from pathlib import Path

import pytest

from zoho_inventory_connector.auth.oauth import (
    build_authorization_url,
    get_accounts_base_url,
    get_api_base_url,
)
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.ratelimit.clock import VirtualClock


def test_build_authorization_url_contains_state_and_offline() -> None:
    """# FR-1.1: Verify auth URL contains state for CSRF and access_type=offline."""
    url, state = build_authorization_url(
        client_id="test_client_id",
        redirect_uri="http://localhost:8080/callback",
        dc="in",
    )
    assert f"state={state}" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "accounts.zoho.in" in url
    assert "ZohoInventory.items.READ" in url


def test_datacenter_routing_fallback_and_dynamic() -> None:
    """# FR-1.5: Derive api_domain from token response or fallback to ZOHO_DC."""
    assert get_accounts_base_url("in") == "https://accounts.zoho.in"
    assert get_accounts_base_url("com") == "https://accounts.zoho.com"
    assert get_api_base_url("in") == "https://www.zohoapis.in/inventory/v1"

    # Dynamic domain routing
    assert (
        get_api_base_url("in", api_domain="https://www.zohoapis.com")
        == "https://www.zohoapis.com/inventory/v1"
    )


@pytest.mark.asyncio
async def test_single_flight_refresh_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    """# FR-1.3 Acceptance Criterion: 50 concurrent calls with expired token produce exactly 1 refresh call."""
    virtual_clock = VirtualClock()
    refresh_invocations = 0

    async def mock_refresh(*args, **kwargs) -> dict[str, object]:
        nonlocal refresh_invocations
        refresh_invocations += 1
        # Virtual delay
        await asyncio.sleep(0.01)
        return {
            "access_token": f"mock_token_v{refresh_invocations}",
            "expires_in": 3600,
            "api_domain": "https://www.zohoapis.in",
        }

    monkeypatch.setattr(
        "zoho_inventory_connector.auth.token_manager.refresh_access_token",
        mock_refresh,
    )

    tm = TokenManager(
        client_id="client_xyz",
        client_secret="secret_abc",
        refresh_token="ref_token_123",
        clock=virtual_clock,
    )

    # Launch 50 concurrent calls simultaneously
    tokens = await asyncio.gather(*(tm.get_access_token() for _ in range(50)))

    # Assert exactly 1 refresh call was made
    assert refresh_invocations == 1
    assert len(tokens) == 50
    # All 50 received the same token
    assert all(t == "mock_token_v1" for t in tokens)

    # Advance virtual clock beyond expiration buffer
    virtual_clock.advance(3400)  # past 3600 - 300 buffer
    # Next call should trigger a second refresh
    tok2 = await tm.get_access_token()
    assert refresh_invocations == 2
    assert tok2 == "mock_token_v2"


def test_token_file_persistence_mode_0600(tmp_path: Path) -> None:
    """# FR-1.4 Acceptance Criterion: Refresh token persisted to file with mode 0600."""
    token_file = tmp_path / "subdir" / ".zoho_token.json"
    tm = TokenManager(
        client_id="client_xyz",
        client_secret="secret_abc",
        refresh_token="secret_refresh_token_to_save",
        token_file=token_file,
    )
    tm.save_tokens_to_file()

    assert token_file.exists()
    mode = stat.S_IMODE(os.stat(token_file).st_mode)
    assert mode == 0o600

    # Test loading
    tm2 = TokenManager(
        client_id="client_xyz",
        client_secret="secret_abc",
        token_file=token_file,
    )
    assert tm2.refresh_token == "secret_refresh_token_to_save"


def test_tokens_never_logged_or_printed(caplog: pytest.LogCaptureFixture) -> None:
    """# FR-1.4 Acceptance Criterion: Token strings never appear in captured logs."""
    raw_secret_token = "SUPER_SECRET_TOKEN_XYZ_12345"
    tm = TokenManager(
        client_id="client_xyz",
        client_secret="secret_abc",
        refresh_token=raw_secret_token,
    )

    with caplog.at_level(logging.DEBUG):
        logger = logging.getLogger("test_auth")
        logger.info("Manager created: %r", tm)

    log_output = caplog.text
    assert raw_secret_token not in log_output
    assert "[REDACTED]" in repr(tm)
