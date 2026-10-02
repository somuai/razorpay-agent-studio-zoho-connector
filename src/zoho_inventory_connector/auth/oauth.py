"""OAuth 2.0 flow and loopback redirect server (FR-1.1, FR-1.2, FR-1.5)."""

import asyncio
import re
import secrets
import urllib.parse
from typing import Any
from urllib.parse import urlparse

import httpx

from zoho_inventory_connector.client.errors import AuthError
from zoho_inventory_connector.client.transport_diagnostics import transport_diagnostic
from zoho_inventory_connector.events.logging_safety import redact_text

DC_ACCOUNTS_MAP: dict[str, str] = {
    "in": "https://accounts.zoho.in",
    "com": "https://accounts.zoho.com",
    "eu": "https://accounts.zoho.eu",
    "com.au": "https://accounts.zoho.com.au",
    "jp": "https://accounts.zoho.jp",
    "ca": "https://accounts.zoho.ca",
}

DC_API_MAP: dict[str, str] = {
    "in": "https://www.zohoapis.in/inventory/v1",
    "com": "https://www.zohoapis.com/inventory/v1",
    "eu": "https://www.zohoapis.eu/inventory/v1",
    "com.au": "https://www.zohoapis.com.au/inventory/v1",
    "jp": "https://www.zohoapis.jp/inventory/v1",
    "ca": "https://www.zohoapis.ca/inventory/v1",
}

READ_ONLY_SCOPES: list[str] = [
    "ZohoInventory.items.READ",
    "ZohoInventory.salesorders.READ",
    "ZohoInventory.packages.READ",
    "ZohoInventory.shipmentorders.READ",
    "ZohoInventory.invoices.READ",
    "ZohoInventory.contacts.READ",
    "ZohoInventory.settings.READ",
]


def _safe_oauth_detail(response: httpx.Response, operation: str) -> tuple[str, dict[str, Any]]:
    """Describe token endpoint response metadata without logging its body or values."""
    try:
        decoded = response.json()
        body_is_json = True
    except ValueError:
        decoded = None
        body_is_json = False
    data = decoded if isinstance(decoded, dict) else {}
    host = urlparse(str(response.request.url)).hostname or "[unknown]"

    def field(name: str) -> str:
        value = data.get(name)
        if value is None:
            return "absent"
        safe = re.sub(r"[\r\n\t]+", " ", str(value))
        return redact_text(safe)[:200]

    detail = (
        f"operation={operation}; host={host}; HTTP {response.status_code}; "
        f"body_json={str(body_is_json).lower()}; oauth_error={field('error')}; "
        f"error_description={field('error_description')}"
    )
    return detail, data


def _parse_token_response(response: httpx.Response, operation: str) -> dict[str, Any]:
    detail, data = _safe_oauth_detail(response, operation)
    label = "authorization code exchange" if operation == "exchange" else "refresh token request"
    if response.status_code != 200 or data.get("error"):
        raise AuthError(
            message=f"Zoho Accounts {label} rejected: {detail}",
            http_status=response.status_code,
        )
    if not isinstance(data, dict):
        raise AuthError(
            message=f"Zoho Accounts {label} returned a non-object response: {detail}",
            http_status=response.status_code,
        )
    if not data.get("access_token"):
        raise AuthError(
            message=f"Zoho Accounts {label} response is missing an access token: {detail}",
            http_status=response.status_code,
        )
    return data


def get_accounts_base_url(dc: str = "in", override: str | None = None) -> str:
    """Resolve accounts endpoint for given data center."""
    if override:
        return override.rstrip("/")
    return DC_ACCOUNTS_MAP.get(dc.lower(), DC_ACCOUNTS_MAP["in"])


def get_api_base_url(
    dc: str = "in", api_domain: str | None = None, override: str | None = None
) -> str:
    """Resolve API base endpoint (FR-1.5: derive from api_domain or fallback to DC)."""
    if override:
        return override.rstrip("/")
    if api_domain:
        return f"{api_domain.rstrip('/')}/inventory/v1"
    return DC_API_MAP.get(dc.lower(), DC_API_MAP["in"])


def build_authorization_url(
    client_id: str,
    redirect_uri: str = "http://localhost:8080/callback",
    state: str | None = None,
    dc: str = "in",
    accounts_base_url: str | None = None,
    scopes: list[str] | None = None,
) -> tuple[str, str]:
    """Construct Zoho OAuth authorization URL (FR-1.1).

    Returns:
        tuple of (authorization_url, state)
    """
    base_url = get_accounts_base_url(dc, accounts_base_url)
    state_token = state or secrets.token_urlsafe(32)
    requested_scopes = ",".join(scopes or READ_ONLY_SCOPES)

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": requested_scopes,
        "access_type": "offline",
        "prompt": "consent",
        "state": state_token,
    }
    query_str = urllib.parse.urlencode(params)
    auth_url = f"{base_url}/oauth/v2/auth?{query_str}"
    return auth_url, state_token


async def exchange_code_for_tokens(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    accounts_base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Exchange authorization code for access and refresh tokens (FR-1.1)."""
    base_url = get_accounts_base_url(override=accounts_base_url)
    token_url = f"{base_url}/oauth/v2/token"

    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }

    local_client = client or httpx.AsyncClient(timeout=15.0)
    try:
        try:
            res = await local_client.post(token_url, data=data)
        except httpx.HTTPError as exc:
            diagnostic = transport_diagnostic(exc, token_url, attempt=1)
            diagnostic["operation"] = "exchange"
            raise AuthError(
                message="Zoho Accounts authorization-code exchange transport failure.",
                http_status=None,
                transport_diagnostic=diagnostic,
            ) from None
        return _parse_token_response(res, "exchange")
    finally:
        if client is None:
            await local_client.aclose()


async def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    accounts_base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Exchange refresh token for a fresh access token (FR-1.2, FR-1.3)."""
    base_url = get_accounts_base_url(override=accounts_base_url)
    token_url = f"{base_url}/oauth/v2/token"

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    local_client = client or httpx.AsyncClient(timeout=15.0)
    try:
        try:
            res = await local_client.post(token_url, data=data)
        except httpx.HTTPError as exc:
            diagnostic = transport_diagnostic(exc, token_url, attempt=1)
            diagnostic["operation"] = "refresh"
            raise AuthError(
                message="Zoho Accounts refresh transport failure.",
                http_status=None,
                transport_diagnostic=diagnostic,
            ) from None
        return _parse_token_response(res, "refresh")
    finally:
        if client is None:
            await local_client.aclose()


async def listen_for_loopback_callback(
    expected_state: str,
    host: str = "127.0.0.1",
    port: int = 8080,
    timeout_seconds: float = 120.0,
) -> str:
    """Run an ephemeral TCP server to capture the loopback OAuth callback (FR-1.1).

    Validates the state parameter against CSRF attacks.
    """
    code_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await reader.readline()
            request_line = line.decode("utf-8", errors="replace")
            # Parse GET /callback?code=...&state=... HTTP/1.1
            parts = request_line.split()
            if len(parts) >= 2 and parts[0] == "GET":
                path = parts[1]
                parsed = urllib.parse.urlparse(path)
                qs = urllib.parse.parse_qs(parsed.query)

                received_code = qs.get("code", [None])[0]
                received_state = qs.get("state", [None])[0]

                if not received_code:
                    body = "<h3>Authentication failed: Missing code</h3>"
                    status = "400 Bad Request"
                elif received_state != expected_state:
                    body = "<h3>Authentication failed: CSRF state mismatch</h3>"
                    status = "403 Forbidden"
                    if not code_future.done():
                        code_future.set_exception(
                            AuthError("CSRF state mismatch in OAuth loopback callback.")
                        )
                else:
                    body = (
                        "<h3>Zoho Authentication Successful!</h3>"
                        "<p>You can close this tab and return to your terminal.</p>"
                    )
                    status = "200 OK"
                    if not code_future.done():
                        code_future.set_result(received_code)

                response_content = (
                    f"HTTP/1.1 {status}\r\n"
                    f"Content-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(body.encode('utf-8'))}\r\n"
                    f"Connection: close\r\n\r\n"
                    f"{body}"
                )
                writer.write(response_content.encode("utf-8"))
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, host, port)
    try:
        async with asyncio.timeout(timeout_seconds):
            return await code_future
    except TimeoutError:
        raise AuthError(
            f"OAuth loopback callback timed out after {timeout_seconds} seconds."
        ) from None
    finally:
        server.close()
        await server.wait_closed()
