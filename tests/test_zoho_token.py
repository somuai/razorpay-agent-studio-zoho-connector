"""Offline tests for hidden-code exchange and private token persistence."""

import asyncio
import hashlib
import json
import os
from pathlib import Path

import pytest

from examples import zoho_token
from zoho_inventory_connector.client.errors import AuthError


def _env(monkeypatch: pytest.MonkeyPatch, token_path: Path) -> None:
    monkeypatch.setenv("ZOHO_CLIENT_ID", "client-id-secret")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "client-secret-value")
    monkeypatch.setenv("ZOHO_DC", "in")
    monkeypatch.setenv("ZOHO_TOKEN_FILE", str(token_path))


def test_dc_matches_returned_api_domain() -> None:
    assert zoho_token._api_domain_matches_dc("https://www.zohoapis.in", "in")
    assert not zoho_token._api_domain_matches_dc("https://www.zohoapis.com", "in")
    assert not zoho_token._api_domain_matches_dc(None, "in")


def test_grant_code_is_not_echoed_and_token_file_is_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    token_path = tmp_path / "private" / "token.json"
    _env(monkeypatch, token_path)
    monkeypatch.setattr(zoho_token.getpass, "getpass", lambda _prompt: "sensitive-grant-code")

    async def fake_exchange(**_kwargs: object) -> dict[str, object]:
        return {
            "refresh_token": "sensitive-refresh-token",
            "api_domain": "https://www.zohoapis.in",
        }

    monkeypatch.setattr(zoho_token, "exchange_code_for_tokens", fake_exchange)
    assert asyncio.run(zoho_token._run()) == 0
    captured = capsys.readouterr().out
    assert "sensitive-grant-code" not in captured
    assert "sensitive-refresh-token" not in captured
    assert json.loads(token_path.read_text()) == {
        "refresh_token": "sensitive-refresh-token",
        "api_domain": "https://www.zohoapis.in",
        "client_credentials_fingerprint": hashlib.sha256(
            b"client-id-secret\0client-secret-value"
        ).hexdigest(),
    }
    assert os.stat(token_path).st_mode & 0o777 == 0o600


def test_dc_mismatch_does_not_persist_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    token_path = tmp_path / "token.json"
    _env(monkeypatch, token_path)
    monkeypatch.setattr(zoho_token.getpass, "getpass", lambda _prompt: "grant")

    async def fake_exchange(**_kwargs: object) -> dict[str, object]:
        return {"refresh_token": "refresh", "api_domain": "https://www.zohoapis.com"}

    monkeypatch.setattr(zoho_token, "exchange_code_for_tokens", fake_exchange)
    assert asyncio.run(zoho_token._run()) == 1
    assert "does not match ZOHO_DC" in capsys.readouterr().out
    assert not token_path.exists()


def test_expired_grant_message_does_not_leak_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, tmp_path / "token.json")
    monkeypatch.setattr(zoho_token.getpass, "getpass", lambda _prompt: "sensitive-grant-code")

    async def fake_exchange(**_kwargs: object) -> dict[str, object]:
        raise AuthError("Zoho rejected authorization code (invalid_grant)")

    monkeypatch.setattr(zoho_token, "exchange_code_for_tokens", fake_exchange)
    assert asyncio.run(zoho_token._run()) == 1
    output = capsys.readouterr().out
    assert "Codes expire in" in output
    assert "sensitive-grant-code" not in output
