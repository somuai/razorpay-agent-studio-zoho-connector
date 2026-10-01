"""Deterministic OAuth endpoint and authorization URL tests (FR-1)."""

import httpx
import pytest

from zoho_inventory_connector.auth.oauth import (
    build_authorization_url,
    exchange_code_for_tokens,
    get_accounts_base_url,
    get_api_base_url,
    refresh_access_token,
)
from zoho_inventory_connector.client.errors import AuthError


def test_datacenter_fallback_overrides_and_custom_scope_encoding() -> None:
    assert get_accounts_base_url("unknown") == "https://accounts.zoho.in"
    assert (
        get_accounts_base_url("eu", "https://accounts.custom.example/")
        == "https://accounts.custom.example"
    )
    assert get_api_base_url("unknown") == "https://www.zohoapis.in/inventory/v1"
    assert get_api_base_url(api_domain="https://api.example/") == "https://api.example/inventory/v1"
    assert get_api_base_url(override="https://inventory.example/") == "https://inventory.example"

    url, state = build_authorization_url(
        "client id",
        redirect_uri="http://localhost/callback?x=1",
        state="fixed-state",
        dc="eu",
        scopes=["scope.one", "scope.two"],
    )
    query = dict(httpx.URL(url).params)
    assert query["client_id"] == "client id"
    assert query["redirect_uri"] == "http://localhost/callback?x=1"
    assert query["scope"] == "scope.one,scope.two"
    assert query["state"] == state == "fixed-state"


@pytest.mark.asyncio
async def test_exchange_and_refresh_token_success_payloads() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"access_token": "access", "refresh_token": "refresh", "expires_in": 3600},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        exchanged = await exchange_code_for_tokens(
            "grant",
            "client",
            "secret",
            "http://localhost/callback",
            "https://accounts.test",
            client,
        )
        refreshed = await refresh_access_token(
            "refresh", "client", "secret", "https://accounts.test", client
        )

    assert exchanged["refresh_token"] == "refresh"
    assert refreshed["access_token"] == "access"
    assert [request.url.path for request in requests] == ["/oauth/v2/token", "/oauth/v2/token"]
    assert "grant_type=authorization_code" in requests[0].content.decode()
    assert "grant_type=refresh_token" in requests[1].content.decode()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "expected_text"),
    [("exchange", "authorization code"), ("refresh", "refresh token")],
)
async def test_oauth_rejected_responses_become_auth_error(
    operation: str, expected_text: str
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "expired"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthError, match=expected_text) as exc_info:
            if operation == "exchange":
                await exchange_code_for_tokens(
                    "bad", "client", "secret", "http://localhost", client=client
                )
            else:
                await refresh_access_token("bad", "client", "secret", client=client)
    assert exc_info.value.http_status == 400
    assert "invalid_grant" in str(exc_info.value)
    assert "expired" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_oauth_non_json_error_does_not_expose_response_body() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="gateway down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthError, match="HTTP 502"):
            await refresh_access_token("refresh", "client", "secret", client=client)
