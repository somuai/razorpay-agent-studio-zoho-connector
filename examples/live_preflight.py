"""Read-only credential and endpoint preflight; output is safe to screenshot."""

from __future__ import annotations

import asyncio
import os
import re
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from zoho_inventory_connector.auth.oauth import DC_API_MAP
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.errors import AuthError
from zoho_inventory_connector.client.transport_diagnostics import transport_diagnostic
from zoho_inventory_connector.events.logging_safety import redact_text

REQUIRED_ENV = (
    "ZOHO_CLIENT_ID",
    "ZOHO_CLIENT_SECRET",
    "ZOHO_ORG_ID",
)
PLACEHOLDER_MARKERS = ("your_", "changeme", "xxx", "<", ">")
SCOPE_ENDPOINTS = (
    ("ZohoInventory.items.READ", "items?page=1&per_page=1"),
    ("ZohoInventory.salesorders.READ", "salesorders?page=1&per_page=1"),
    ("ZohoInventory.packages.READ", "packages?page=1&per_page=1"),
    # Zoho documents shipment retrieval by ID but not a list endpoint. A synthetic
    # missing ID distinguishes a permitted route (404/code 1002) from denied scope.
    ("ZohoInventory.shipmentorders.READ", "shipmentorders/999999999999999999999999999999"),
    ("ZohoInventory.invoices.READ", "invoices?page=1&per_page=1"),
    ("ZohoInventory.contacts.READ", "contacts?page=1&per_page=1"),
)
READ_ENDPOINTS = ("items", "salesorders", "packages", "invoices")


def _say(status: str, label: str, fix: str = "") -> None:
    suffix = f" — {fix}" if fix else ""
    print(f"{status}: {label}{suffix}")


def _api_dc_matches(api_domain: str, dc: str) -> bool:
    expected_host = urlparse(DC_API_MAP.get(dc.lower(), DC_API_MAP["in"])).hostname or ""
    observed_host = urlparse(api_domain).hostname or ""
    # Zoho sometimes returns a regional API host variant. Compare the DC suffix.
    suffixes = {
        "in": ".zohoapis.in",
        "com": ".zohoapis.com",
        "eu": ".zohoapis.eu",
        "com.au": ".zohoapis.com.au",
        "jp": ".zohoapis.jp",
        "ca": ".zohoapis.ca",
    }
    expected_suffix = suffixes.get(dc.lower())
    if expected_suffix:
        return observed_host.endswith(expected_suffix)
    return observed_host == expected_host


def _safe_error(response: httpx.Response) -> str:
    """Map upstream responses to a short non-sensitive diagnosis."""
    try:
        data = response.json()
    except ValueError:
        data = {}
    code = data.get("code") if isinstance(data, Mapping) else None
    if code == 45:
        return "Zoho daily quota exhausted; do not retry today."
    if response.status_code == 401 or code in (57, 59):
        return "Zoho rejected authentication; regenerate the grant and refresh token."
    if response.status_code == 403 or code in (6, 57):
        return "Read scope may be missing; reconnect with the documented read scopes."
    if response.status_code == 404:
        return "Zoho endpoint was not found; check API version and resource path."
    if response.status_code == 429:
        return "Zoho rate limited the preflight; wait, then retry once."
    return f"Zoho returned HTTP {response.status_code}; inspect API_NOTES.md and retry within the time-box."


def _diagnostic(response: httpx.Response, path: str, host: str) -> str:
    try:
        data = response.json()
    except ValueError:
        data = {}
    code = data.get("code") if isinstance(data, Mapping) else None
    message = data.get("message") if isinstance(data, Mapping) else None
    safe_message = re.sub(
        r"(?:token|secret|password|authorization)\S*", "[redacted]", str(message or ""), flags=re.I
    )
    safe_message = re.sub(r"\b\d{6,}\b", "[id]", safe_message)[:200]
    if response.status_code in (401, 403) or code in (6, 57, 59):
        fix = "check scopes and regenerate the token"
    elif response.status_code == 404:
        fix = "check the API root and path"
    elif response.status_code == 400 or code in (1001, 1002):
        fix = "check ZOHO_ORG_ID"
    elif response.status_code == 429 or code in (44, 45, 1070):
        fix = "check quota or rate limits"
    else:
        fix = "inspect API_NOTES.md and check connectivity"
    return redact_text(
        f"endpoint {path}; HTTP {response.status_code}; Zoho code {code!r}; "
        f"message {safe_message!r}; host {host}; fix: {fix}"
    )


async def run_preflight(
    environ: Mapping[str, str] | None = None,
    *,
    api_http: httpx.AsyncClient | None = None,
    token_http: httpx.AsyncClient | None = None,
) -> int:
    """Run preflight checks. Injection points exist only to test offline branches."""
    env = environ if environ is not None else os.environ
    missing = [key for key in REQUIRED_ENV if key not in env]
    empty = [key for key in REQUIRED_ENV if key in env and not env.get(key, "").strip()]
    placeholders = [
        key
        for key in REQUIRED_ENV
        if env.get(key)
        and (
            env[key].strip().lower()
            in {"your_client_id_here", "your_client_secret_here", "your_organization_id_here"}
            or any(marker in env[key].strip().lower() for marker in PLACEHOLDER_MARKERS)
        )
    ]
    if empty or placeholders:
        invalid = empty + placeholders
        if invalid:
            _say(
                "FAIL",
                "credential settings are empty or look like placeholders: " + ", ".join(invalid),
                "replace these values in the ignored .env before live checks",
            )
            return 1
    if missing:
        print(
            "SKIPPED: required settings are not exported in this shell: "
            + ", ".join(missing)
            + ". Export these names from the local .env before live checks."
        )
        return 0

    _say("PASS", "required credential variables are present (values hidden)")
    token_path = Path(env.get("ZOHO_TOKEN_FILE", ".zoho_token.json"))
    try:
        info = token_path.stat()
    except OSError:
        _say(
            "FAIL",
            "private token file is missing",
            "run make zoho-token and confirm the file was written",
        )
        return 1
    if stat.S_IMODE(info.st_mode) != 0o600:
        _say("FAIL", "token file permissions are not 0600", "chmod 600 the configured token file")
        return 1
    _say("PASS", "private token file exists with 0600 permissions")

    owns_token_http = token_http is None
    token_client = token_http or httpx.AsyncClient(timeout=15.0)
    owns_api_http = api_http is None
    api_client = api_http or httpx.AsyncClient(timeout=15.0)
    calls = 0
    try:
        token_manager = TokenManager(
            client_id=env["ZOHO_CLIENT_ID"],
            client_secret=env["ZOHO_CLIENT_SECRET"],
            refresh_token=env.get("ZOHO_REFRESH_TOKEN"),
            token_file=token_path,
            dc=env.get("ZOHO_DC", "in"),
            accounts_base_url=env.get("ZOHO_ACCOUNTS_BASE_URL"),
            http_client=token_client,
        )
        if not token_manager.refresh_token:
            _say(
                "FAIL",
                "no refresh token found in environment or private token file",
                "run make zoho-token and keep the token file at the configured path",
            )
            print(f"API calls used: {calls}")
            return 1
        cached_access_token = token_manager.is_token_valid()
        if not cached_access_token:
            calls += 1  # Count the token endpoint attempt, including rejected grants.
        try:
            access_token = await token_manager.get_access_token()
        except Exception as exc:
            safe_message = str(getattr(exc, "message", ""))
            if "invalid_grant" in safe_message:
                fix = "refresh token is expired or revoked; generate a new read-only grant with make zoho-token"
            elif "invalid_client" in safe_message:
                fix = "check the client ID/secret pair and API Console data center"
            elif any(
                marker in safe_message.lower()
                for marker in ("access_denied", "too many requests", "http 429", "rate limit")
            ):
                fix = "Zoho may be throttling token generation; wait 10 minutes before retrying"
            else:
                fix = "check client credentials and regenerate the refresh token"
            _say(
                "FAIL",
                "access-token refresh failed"
                + (
                    "; " + redact_text(safe_message)[:300]
                    if isinstance(exc, AuthError) and safe_message
                    else ""
                ),
                fix,
            )
            diagnostic = getattr(exc, "transport_diagnostic", None)
            if diagnostic:
                print("TRANSPORT: " + str(diagnostic))
            print(f"API calls used: {calls}")
            return 1
        _say(
            "PASS",
            "access token is available (reused from cache)"
            if cached_access_token
            else "access-token refresh works",
        )
        if getattr(token_manager, "_scope", None):
            _say(
                "INFO",
                "token scopes recorded: "
                + re.sub(r"[^A-Za-z0-9_., ]", "", token_manager._scope)[:300],
            )

        api_domain = token_manager._api_domain
        dc = env.get("ZOHO_DC", "in")
        if not api_domain or not _api_dc_matches(api_domain, dc):
            observed_dc = next(
                (
                    key
                    for key in ("in", "com", "eu", "com.au", "jp", "ca")
                    if api_domain and _api_dc_matches(api_domain, key)
                ),
                "unknown",
            )
            _say(
                "FAIL",
                f"configured data center and token API domain disagree (configured {dc}, token domain {observed_dc})",
                "use credentials and ZOHO_DC from the same Zoho data center",
            )
            print(f"API calls used: {calls}")
            return 1
        _say("PASS", "configured data center agrees with token API domain")

        base = api_domain.rstrip("/") + "/inventory/v1"
        headers = {"Authorization": f"Zoho-oauthtoken {access_token}", "Accept": "application/json"}

        async def get_json(
            path: str, *, org_required: bool = True
        ) -> tuple[httpx.Response, dict[str, Any]]:
            nonlocal calls
            params = {"organization_id": env["ZOHO_ORG_ID"]} if org_required else None
            calls += 1
            try:
                response = await api_client.get(f"{base}/{path}", params=params, headers=headers)
            except httpx.HTTPError as exc:
                diagnostic = transport_diagnostic(exc, f"{base}/{path}", attempt=1)
                _say(
                    "FAIL",
                    f"endpoint {path}; transport {diagnostic}",
                    "check connectivity",
                )
                raise
            try:
                data = response.json()
            except ValueError:
                data = {}
            return response, data if isinstance(data, dict) else {}

        response, org_data = await get_json("organizations", org_required=False)
        if not response.is_success or org_data.get("code", 0) not in (0, None):
            _say(
                "FAIL",
                "cannot list organizations",
                _diagnostic(response, "/organizations", urlparse(base).hostname or "[unknown]"),
            )
            print(f"API calls used: {calls}")
            return 1
        orgs = org_data.get("organizations", [])
        org_ids = {str(row.get("organization_id")) for row in orgs if isinstance(row, Mapping)}
        if env["ZOHO_ORG_ID"] not in org_ids:
            _say(
                "FAIL",
                "configured ID is not an Inventory organization_id returned by Zoho",
                "copy the ID from Inventory Settings → Organization Profile, not the Zoho account ID",
            )
            print(f"API calls used: {calls}")
            return 1
        _say("PASS", "configured ID matches an Inventory organization")

        scope_failures: list[str] = []
        scope_diagnostics: list[str] = []
        for scope, path in SCOPE_ENDPOINTS:
            probe, data = await get_json(path)
            if data.get("code") == 45:
                _say(
                    "FAIL",
                    "Zoho daily API quota is exhausted",
                    "do not retry today; wait for the documented quota reset",
                )
                print(f"API calls used: {calls}")
                return 1
            if scope == "ZohoInventory.shipmentorders.READ" and (
                probe.status_code == 404 or data.get("code") in (1002, 1003)
            ):
                # Expected record-not-found proves the scoped detail route was reached.
                continue
            if not probe.is_success or data.get("code", 0) not in (0, None):
                scope_failures.append(scope)
                scope_diagnostics.append(
                    _diagnostic(
                        probe, "/" + path.split("?", 1)[0], urlparse(base).hostname or "[unknown]"
                    )
                )
        if scope_failures:
            _say(
                "FAIL",
                "read-scope endpoint checks failed for: " + ", ".join(scope_failures),
                "reconnect with the listed documented read scopes; if salesorders is HTTP 400, inspect the list-all limitation and verified-ID fallback",
            )
            for detail in scope_diagnostics:
                print("DIAGNOSTIC: " + detail)
            print(f"API calls used: {calls}")
            return 1
        _say(
            "PASS",
            "documented read scopes are effective on all six resource routes (shipment route reached expected not-found)",
        )

        _say("PASS", "cheap reads succeeded for items, salesorders, packages, and invoices")
        print(f"API calls used: {calls} (budget: <=12)")
        return 0
    except Exception:
        _say(
            "FAIL",
            "Zoho preflight request failed",
            "check network, data center, scopes, and docs/API_NOTES.md",
        )
        print(f"API calls used: {calls}")
        return 1
    finally:
        if owns_api_http:
            await api_client.aclose()
        if owns_token_http:
            await token_client.aclose()


def main() -> None:
    try:
        raise SystemExit(asyncio.run(run_preflight()))
    except KeyboardInterrupt:
        print("Preflight interrupted.", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
