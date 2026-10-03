"""Interactive, local-only Zoho OAuth setup that persists a refresh token securely."""

from __future__ import annotations

import asyncio
import getpass
import hashlib
import json
import os
import time
import urllib.parse
from pathlib import Path

from zoho_inventory_connector.auth.oauth import (
    exchange_code_for_tokens,
    get_accounts_base_url,
)
from zoho_inventory_connector.client.errors import AuthError
from zoho_inventory_connector.events.logging_safety import redact_text


def _persist_tokens(
    path: Path,
    refresh_token: str,
    api_domain: str | None,
    client_id: str,
    client_secret: str,
    access_token: str,
    expires_in: int | float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            payload = {
                "refresh_token": refresh_token,
                "api_domain": api_domain,
                "access_token": access_token,
                "expires_at": time.time() + float(expires_in),
                "client_credentials_fingerprint": hashlib.sha256(
                    f"{client_id}\0{client_secret}".encode()
                ).hexdigest(),
            }
            json.dump(payload, stream)
            stream.write("\n")
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _api_domain_matches_dc(api_domain: str | None, dc: str) -> bool:
    """Reject a token response routed to a different Zoho data center."""
    if not api_domain:
        return False
    expected = {
        "in": "zohoapis.in",
        "com": "zohoapis.com",
        "eu": "zohoapis.eu",
        "com.au": "zohoapis.com.au",
        "jp": "zohoapis.jp",
        "ca": "zohoapis.ca",
    }.get(dc.lower())
    host = urllib.parse.urlparse(api_domain).hostname or ""
    return expected is not None and (host == expected or host.endswith("." + expected))


async def _run() -> int:
    client_id = os.environ.get("ZOHO_CLIENT_ID")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("SKIPPED: set ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET to start OAuth setup.")
        return 0

    dc = os.environ.get("ZOHO_DC", "in")
    redirect_uri = os.environ.get("ZOHO_REDIRECT_URI", "http://localhost:8080/callback")
    print(
        f"Generate a read-only grant code in the Zoho {dc.upper()} API Console, then exchange it immediately."
    )
    code = getpass.getpass("Grant code (input hidden; expires in about 1–2 minutes): ").strip()
    if not code:
        print("No grant code entered; no token request was made.")
        return 1
    try:
        tokens = await exchange_code_for_tokens(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            accounts_base_url=get_accounts_base_url(dc, os.environ.get("ZOHO_ACCOUNTS_BASE_URL")),
        )
    except Exception as exc:
        # AuthError messages from the OAuth layer contain only redacted response
        # metadata or safe transport diagnostics. Never print arbitrary exception text.
        detail = getattr(exc, "message", None)
        safe_detail = redact_text(detail)[:1000] if isinstance(detail, str) else ""
        if isinstance(exc, AuthError) and (
            "oauth_error=invalid_grant" in safe_detail or "oauth_error=invalid_code" in safe_detail
        ):
            print(
                "Zoho rejected the grant code. Generate a new code for the same Self Client and rerun make zoho-token. "
                + safe_detail
            )
        elif isinstance(exc, AuthError) and "oauth_error=invalid_client" in safe_detail:
            print(
                "Zoho rejected the client credentials. Check that ZOHO_CLIENT_ID and "
                "ZOHO_CLIENT_SECRET match the Self Client that generated the code. " + safe_detail
            )
        elif isinstance(exc, AuthError) and (
            exc.http_status == 429 or "too many requests" in safe_detail.lower()
        ):
            print(
                "Zoho throttled token generation; wait 10 minutes before trying again. "
                + safe_detail
            )
        elif isinstance(exc, AuthError) and exc.transport_diagnostic is not None:
            print(f"Zoho token exchange transport failure: {safe_detail}")
        elif isinstance(exc, AuthError) and safe_detail:
            print(f"Zoho token exchange rejected: {safe_detail}")
        else:
            print(
                f"Zoho token exchange failed ({type(exc).__name__}); check the data center, client settings, redirect URI, and scopes."
            )
        return 1
    if not _api_domain_matches_dc(tokens.get("api_domain"), dc):
        print(
            "Zoho token response api_domain does not match ZOHO_DC (or is missing); token was not saved. Check the account/API Console data center."
        )
        return 1
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print(
            "Zoho did not return a refresh token; recreate the read-only grant with offline access."
        )
        return 1
    token_path = Path(os.environ.get("ZOHO_TOKEN_FILE", ".zoho_token.json"))
    _persist_tokens(
        token_path,
        str(refresh_token),
        tokens.get("api_domain"),
        client_id,
        client_secret,
        str(tokens["access_token"]),
        float(tokens.get("expires_in", 3600)),
    )
    print(
        "Refresh token saved to the private token file with mode 0600; value hidden. DC check passed."
    )
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_run()))
    except KeyboardInterrupt:
        print("OAuth setup interrupted.")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
