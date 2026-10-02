"""Unit and concurrency tests for OAuth and TokenManager (FR-1)."""

import asyncio
import hashlib
import json
import logging
import multiprocessing
import os
import stat
import threading
import time
from pathlib import Path

import pytest

from zoho_inventory_connector.auth.oauth import (
    build_authorization_url,
    get_accounts_base_url,
    get_api_base_url,
)
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.ratelimit.clock import VirtualClock


def _concurrent_token_writer(path: str, barrier: object, index: int) -> None:
    """Child-process helper for atomic token-file write stress coverage."""
    manager = TokenManager("client", "secret", "refresh-stable", token_file=path)
    manager._access_token = f"writer-access-{index}"
    manager._expires_at_mono = manager.clock.monotonic() + 3600
    barrier.wait(timeout=10)  # type: ignore[attr-defined]
    manager.save_tokens_to_file()


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


def test_half_written_token_file_is_ignored_without_losing_env_refresh_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    token_file = tmp_path / "half-written.json"
    token_file.write_text('{"refresh_token":', encoding="utf-8")
    token_file.chmod(0o600)

    manager = TokenManager(
        "client",
        "secret",
        "env-refresh-token",
        token_file=token_file,
    )

    assert manager.refresh_token == "env-refresh-token"
    assert manager._access_token is None
    assert "JSONDecodeError" in caplog.text
    assert "env-refresh-token" not in caplog.text


@pytest.mark.asyncio
async def test_access_token_is_reused_across_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "token.json"
    calls = 0

    async def refresh(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {
            "access_token": "cached-access",
            "expires_in": 3600,
            "api_domain": "https://www.zohoapis.in",
        }

    monkeypatch.setattr("zoho_inventory_connector.auth.token_manager.refresh_access_token", refresh)
    first = TokenManager("id", "secret", "refresh", token_file=token_file)
    assert await first.get_access_token() == "cached-access"
    second = TokenManager("id", "secret", token_file=token_file)
    assert await second.get_access_token() == "cached-access"
    assert calls == 1
    assert stat.S_IMODE(os.stat(token_file).st_mode) == 0o600


@pytest.mark.asyncio
@pytest.mark.parametrize("remaining_seconds", [-30, 120])
async def test_expired_or_near_expiry_cached_access_token_refreshes_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remaining_seconds: float
) -> None:
    token_file = tmp_path / "expired.json"
    token_file.write_text(
        json.dumps(
            {
                "refresh_token": "still-valid-refresh",
                "access_token": "expired-access",
                "expires_at": time.time() + remaining_seconds,
                "api_domain": "https://www.zohoapis.in",
                "client_credentials_fingerprint": hashlib.sha256(b"client-A\0secret").hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    token_file.chmod(0o600)
    refresh_calls = 0

    async def refresh(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal refresh_calls
        refresh_calls += 1
        return {
            "access_token": "fresh-access",
            "refresh_token": "rotated-refresh",
            "expires_in": 3600,
            "api_domain": "https://www.zohoapis.in",
        }

    monkeypatch.setattr("zoho_inventory_connector.auth.token_manager.refresh_access_token", refresh)
    manager = TokenManager("client-A", "secret", token_file=token_file)
    assert await manager.get_access_token() == "fresh-access"
    assert refresh_calls == 1
    saved = json.loads(token_file.read_text(encoding="utf-8"))
    assert saved["refresh_token"] == "rotated-refresh"
    assert saved["access_token"] == "fresh-access"
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


@pytest.mark.asyncio
async def test_cached_access_token_is_bound_to_client_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    refresh_clients: list[str] = []

    async def refresh(*args: object, **kwargs: object) -> dict[str, object]:
        refresh_clients.append(str(kwargs["client_id"]))
        return {
            "access_token": f"access-for-{kwargs['client_id']}",
            "expires_in": 3600,
            "api_domain": "https://www.zohoapis.in",
        }

    monkeypatch.setattr("zoho_inventory_connector.auth.token_manager.refresh_access_token", refresh)
    for index, (second_id, second_secret) in enumerate(
        (("client-B", "secret-A"), ("client-A", "secret-B"))
    ):
        token_file = tmp_path / f"bound-{index}.json"
        first = TokenManager("client-A", "secret-A", "refresh-A", token_file=token_file)
        assert await first.get_access_token() == "access-for-client-A"
        second = TokenManager(second_id, second_secret, token_file=token_file)
        assert not second.is_token_valid()
        assert await second.get_access_token() == f"access-for-{second_id}"
        assert second.refresh_token == "refresh-A"
    assert refresh_clients == ["client-A", "client-B", "client-A", "client-A"]


def test_concurrent_token_file_writers_are_atomic_and_preserve_refresh_token(
    tmp_path: Path,
) -> None:
    token_file = tmp_path / "shared.json"
    initial = TokenManager("client", "secret", "refresh-stable", token_file=token_file)
    initial.save_tokens_to_file()
    stop_reader = threading.Event()
    reader_errors: list[str] = []

    def read_while_writing() -> None:
        while not stop_reader.is_set():
            try:
                value = json.loads(token_file.read_text(encoding="utf-8"))
                assert value["refresh_token"] == "refresh-stable"
            except Exception as exc:  # report only the local exception class
                reader_errors.append(type(exc).__name__)
                return

    reader = threading.Thread(target=read_while_writing)
    reader.start()
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(8)
    writers = [
        context.Process(
            target=_concurrent_token_writer,
            args=(str(token_file), barrier, index),
        )
        for index in range(8)
    ]
    try:
        for process in writers:
            process.start()
        for process in writers:
            process.join(timeout=15)
        assert all(process.exitcode == 0 for process in writers)
    finally:
        for process in writers:
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
        stop_reader.set()
        reader.join(timeout=2)

    saved = json.loads(token_file.read_text(encoding="utf-8"))
    assert not reader_errors
    assert saved["refresh_token"] == "refresh-stable"
    assert saved["access_token"].startswith("writer-access-")
    assert saved["client_credentials_fingerprint"] == hashlib.sha256(b"client\0secret").hexdigest()
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(token_file.with_name("shared.json.lock").stat().st_mode) == 0o600
    assert list(tmp_path.glob(".shared.json.*.tmp")) == []


@pytest.mark.asyncio
async def test_failed_forced_refresh_invalidates_rejected_access_but_keeps_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "rejected.json"

    async def refresh(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("synthetic refresh failure")

    monkeypatch.setattr("zoho_inventory_connector.auth.token_manager.refresh_access_token", refresh)
    manager = TokenManager("client", "secret", "refresh-kept", token_file=token_file)
    manager._access_token = "rejected-access"
    manager._expires_at_mono = manager.clock.monotonic() + 3600
    manager._expires_at_epoch = time.time() + 3600
    manager.save_tokens_to_file()

    with pytest.raises(RuntimeError, match="synthetic refresh failure"):
        await manager.get_access_token(force_refresh=True)
    saved = json.loads(token_file.read_text(encoding="utf-8"))
    assert manager._access_token is None
    assert saved["access_token"] is None
    assert saved["refresh_token"] == "refresh-kept"


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
    assert raw_secret_token[:4] not in repr(tm)
    assert "[REDACTED]" in repr(tm)
