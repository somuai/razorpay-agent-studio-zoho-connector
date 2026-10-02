"""Deterministic OAuth endpoint and authorization URL tests (FR-1)."""

import ssl

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
    assert "error_description=expired" in str(exc_info.value)
    assert "body_json=true" in str(exc_info.value)
    assert "accounts.zoho.in" in str(exc_info.value)


@pytest.mark.asyncio
async def test_oauth_non_json_error_does_not_expose_response_body() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="gateway down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthError, match="HTTP 502") as exc_info:
            await refresh_access_token("refresh", "client", "secret", client=client)
    assert "body_json=false" in str(exc_info.value)
    assert "gateway down" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_oauth_http_429_is_an_http_response_not_a_transport_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="<html>throttled</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthError) as exc_info:
            await refresh_access_token("refresh", "client", "secret", client=client)
    assert exc_info.value.http_status == 429
    assert exc_info.value.transport_diagnostic is None
    assert "operation=refresh" in str(exc_info.value)
    assert "HTTP 429" in str(exc_info.value)
    assert "body_json=false" in str(exc_info.value)
    assert "throttled" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "transport_error", "expected_phase"),
    [
        ("refresh", httpx.ReadTimeout("private timeout"), "read"),
        ("exchange", httpx.ConnectError("private TLS failure"), "connect"),
    ],
)
async def test_oauth_transport_errors_report_only_safe_classes_and_phase(
    operation: str, transport_error: httpx.HTTPError, expected_phase: str
) -> None:
    if operation == "exchange":
        transport_error.__cause__ = ssl.SSLError("private certificate detail")

    def handler(_: httpx.Request) -> httpx.Response:
        raise transport_error

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AuthError) as exc_info:
            if operation == "refresh":
                await refresh_access_token("refresh", "client", "secret", client=client)
            else:
                await exchange_code_for_tokens(
                    "grant", "client", "secret", "http://localhost", client=client
                )

    diagnostic = exc_info.value.transport_diagnostic
    assert diagnostic is not None
    assert diagnostic["operation"] == operation
    expected = expected_phase if operation == "refresh" else "TLS"
    assert diagnostic["phase"] == expected
    assert diagnostic["host"] == "accounts.zoho.in"
    rendered = str(diagnostic) + str(exc_info.value)
    assert "private timeout" not in rendered
    assert "private TLS failure" not in rendered
    assert "private certificate detail" not in rendered
    assert "Network connection failed (not a credential error)" in str(exc_info.value)
    assert "sandboxed agent or CI" in str(diagnostic["network_context_hint"])
