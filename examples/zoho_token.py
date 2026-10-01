"""Interactive, local-only Zoho OAuth setup that persists a refresh token securely."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
import webbrowser
from pathlib import Path

from zoho_inventory_connector.auth.oauth import (
    build_authorization_url,
    exchange_code_for_tokens,
    get_accounts_base_url,
    listen_for_loopback_callback,
)


def _persist_tokens(path: Path, refresh_token: str, api_domain: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"refresh_token": refresh_token, "api_domain": api_domain}, stream)
            stream.write("\n")
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


async def _run() -> int:
    client_id = os.environ.get("ZOHO_CLIENT_ID")
    client_secret = os.environ.get("ZOHO_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("SKIPPED: set ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET to start OAuth setup.")
        return 0

    redirect_uri = os.environ.get("ZOHO_REDIRECT_URI", "http://localhost:8080/callback")
    parsed_redirect = urllib.parse.urlparse(redirect_uri)
    if parsed_redirect.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("The OAuth redirect must use localhost or 127.0.0.1.")
    if parsed_redirect.path != "/callback":
        raise ValueError("The OAuth redirect path must be /callback.")

    dc = os.environ.get("ZOHO_DC", "in")
    auth_url, state = build_authorization_url(client_id, redirect_uri=redirect_uri, dc=dc)
    callback = asyncio.create_task(
        listen_for_loopback_callback(
            expected_state=state,
            host="127.0.0.1",
            port=parsed_redirect.port or 80,
        )
    )
    await asyncio.sleep(0)
    print("Opening Zoho consent in your browser. The local callback checks OAuth state.")
    if not webbrowser.open(auth_url):
        print("Open this authorization URL in a browser:\n" + auth_url)
    code = await callback
    tokens = await exchange_code_for_tokens(
        code=code,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        accounts_base_url=get_accounts_base_url(dc, os.environ.get("ZOHO_ACCOUNTS_BASE_URL")),
    )
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError(
            "Zoho did not return a refresh token. Revoke prior grants and retry with consent."
        )
    token_path = Path(os.environ.get("ZOHO_TOKEN_FILE", ".zoho_token.json"))
    _persist_tokens(token_path, str(refresh_token), tokens.get("api_domain"))
    print(f"Refresh token saved with mode 0600 to {token_path}; token value was not displayed.")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_run()))
    except KeyboardInterrupt:
        print("OAuth setup interrupted.")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
