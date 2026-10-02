"""Offline branch coverage for the live preflight command."""

import hashlib
import json
import os
import time
from pathlib import Path

import httpx
import pytest

from examples.live_preflight import run_preflight


def _http_clients(
    *,
    api_domain: str = "https://www.zohoapis.in",
    wrong_org: bool = False,
    missing_scope: bool = False,
    quota: bool = False,
    expired_grant: bool = False,
) -> tuple[httpx.AsyncClient, httpx.AsyncClient, list[str]]:
    requested: list[str] = []

    async def token_handler(request: httpx.Request) -> httpx.Response:
        if expired_grant:
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(
            200,
            json={
                "access_token": "private-access-token",
                "api_domain": api_domain,
                "expires_in": 3600,
            },
        )

    async def api_handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path.endswith("/organizations"):
            org_id = "account-level-id-not-org-id" if wrong_org else "test-organization-id"
            return httpx.Response(
                200, json={"code": 0, "organizations": [{"organization_id": org_id}]}
            )
        if quota and request.url.path.endswith("/packages"):
            return httpx.Response(429, json={"code": 45})
        if missing_scope and request.url.path.startswith("/inventory/v1/shipmentorders/"):
            return httpx.Response(403, json={"code": 57})
        if request.url.path.startswith("/inventory/v1/shipmentorders/"):
            return httpx.Response(404, json={"code": 1002})
        return httpx.Response(200, json={"code": 0})

    return (
        httpx.AsyncClient(transport=httpx.MockTransport(api_handler)),
        httpx.AsyncClient(transport=httpx.MockTransport(token_handler)),
        requested,
    )


def _environment(tmp_path: Path) -> dict[str, str]:
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"refresh_token": "local-refresh-token"}), encoding="utf-8")
    os.chmod(token_file, 0o600)
    return {
        "ZOHO_CLIENT_ID": "private-client-id",
        "ZOHO_CLIENT_SECRET": "private-client-secret",
        "ZOHO_REFRESH_TOKEN": "private-refresh-token",
        "ZOHO_ORG_ID": "test-organization-id",
        "ZOHO_DC": "in",
        "ZOHO_TOKEN_FILE": str(token_file),
    }


@pytest.mark.asyncio
async def test_missing_credentials_skip_without_network(capsys: pytest.CaptureFixture[str]) -> None:
    assert await run_preflight({}) == 0
    assert "SKIPPED" in capsys.readouterr().out


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key,value",
    [
        ("ZOHO_CLIENT_ID", ""),
        ("ZOHO_CLIENT_SECRET", "your_client_secret_here"),
        ("ZOHO_ORG_ID", "changeme"),
        ("ZOHO_CLIENT_ID", "xxx-client"),
        ("ZOHO_CLIENT_SECRET", "<secret>"),
    ],
)
async def test_placeholder_credentials_fail_without_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str, value: str
) -> None:
    env = _environment(tmp_path)
    env[key] = value
    if not value:
        assert await run_preflight(env) == 1
        assert "empty or look like placeholders" in capsys.readouterr().out
    else:
        assert await run_preflight(env) == 1
        output = capsys.readouterr().out
        assert "look like placeholders" in output
        assert value not in output


@pytest.mark.asyncio
async def test_preflight_success_is_bounded_and_screenshot_safe(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api, token, calls = _http_clients()
    try:
        assert await run_preflight(_environment(tmp_path), api_http=api, token_http=token) == 0
    finally:
        await api.aclose()
        await token.aclose()
    output = capsys.readouterr().out
    assert "PASS: documented read scopes" in output
    assert "API calls used: 8 (budget: <=12)" in output
    assert "private-access-token" not in output
    assert "test-organization-id" not in output
    assert len(calls) == 7  # organizations plus six scope checks


@pytest.mark.asyncio
async def test_preflight_reuses_unexpired_client_bound_access_token(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _environment(tmp_path)
    token_path = Path(env["ZOHO_TOKEN_FILE"])
    token_path.write_text(
        json.dumps(
            {
                "refresh_token": "local-refresh-token",
                "access_token": "cached-access-token",
                "api_domain": "https://www.zohoapis.in",
                "expires_at": time.time() + 3600,
                "client_credentials_fingerprint": hashlib.sha256(
                    b"private-client-id\0private-client-secret"
                ).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    token_path.chmod(0o600)

    def token_handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("preflight should reuse a still-valid access token")

    api, _, calls = _http_clients()
    token = httpx.AsyncClient(transport=httpx.MockTransport(token_handler))
    try:
        assert await run_preflight(env, api_http=api, token_http=token) == 0
    finally:
        await api.aclose()
        await token.aclose()
    output = capsys.readouterr().out
    assert "access token is available (reused from cache)" in output
    assert "API calls used: 7" in output
    assert len(calls) == 7


@pytest.mark.asyncio
async def test_expired_grant_fails_without_secret_leak(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api, token, _ = _http_clients(expired_grant=True)
    try:
        assert await run_preflight(_environment(tmp_path), api_http=api, token_http=token) == 1
    finally:
        await api.aclose()
        await token.aclose()
    output = capsys.readouterr().out
    assert "access-token refresh failed" in output
    assert "invalid_grant" in output
    assert "private-refresh-token" not in output
    assert "API calls used: 1" in output


@pytest.mark.asyncio
async def test_token_connect_timeout_is_not_reported_as_credential_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_connect(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("private connection detail")

    api, _, _ = _http_clients()
    token = httpx.AsyncClient(transport=httpx.MockTransport(fail_connect))
    try:
        assert await run_preflight(_environment(tmp_path), api_http=api, token_http=token) == 1
    finally:
        await api.aclose()
        await token.aclose()
    output = capsys.readouterr().out
    assert "network connection failed (not a credential error)" in output
    assert "sandboxed agent or CI" in output
    assert "check client credentials" not in output
    assert "private connection detail" not in output


@pytest.mark.asyncio
async def test_wrong_data_center_fails_before_inventory_calls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api, token, calls = _http_clients(api_domain="https://www.zohoapis.com")
    try:
        assert await run_preflight(_environment(tmp_path), api_http=api, token_http=token) == 1
    finally:
        await api.aclose()
        await token.aclose()
    assert "data center and token API domain disagree" in capsys.readouterr().out
    assert not calls


@pytest.mark.asyncio
async def test_wrong_org_explains_inventory_organization_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api, token, calls = _http_clients(wrong_org=True)
    try:
        assert await run_preflight(_environment(tmp_path), api_http=api, token_http=token) == 1
    finally:
        await api.aclose()
        await token.aclose()
    output = capsys.readouterr().out
    assert "not an Inventory organization_id" in output
    assert "account ID" in output
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_missing_scope_reports_reconnect_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api, token, _ = _http_clients(missing_scope=True)
    try:
        assert await run_preflight(_environment(tmp_path), api_http=api, token_http=token) == 1
    finally:
        await api.aclose()
        await token.aclose()
    assert "reconnect with the listed documented read scopes" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_quota_error_has_no_retry_guidance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    api, token, calls = _http_clients(quota=True)
    try:
        assert await run_preflight(_environment(tmp_path), api_http=api, token_http=token) == 1
    finally:
        await api.aclose()
        await token.aclose()
    output = capsys.readouterr().out
    assert "daily API quota is exhausted" in output
    assert "do not retry today" in output
    assert len(calls) == 4  # org + items + salesorders + packages


@pytest.mark.asyncio
async def test_token_file_permissions_fail_before_any_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _environment(tmp_path)
    os.chmod(env["ZOHO_TOKEN_FILE"], 0o644)
    api, token, calls = _http_clients()
    try:
        assert await run_preflight(env, api_http=api, token_http=token) == 1
    finally:
        await api.aclose()
        await token.aclose()
    assert "permissions are not 0600" in capsys.readouterr().out
    assert not calls


@pytest.mark.asyncio
async def test_missing_token_file_fails_before_any_network(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _environment(tmp_path)
    Path(env["ZOHO_TOKEN_FILE"]).unlink()
    api, token, calls = _http_clients()
    try:
        assert await run_preflight(env, api_http=api, token_http=token) == 1
    finally:
        await api.aclose()
        await token.aclose()
    assert "private token file is missing" in capsys.readouterr().out
    assert not calls
