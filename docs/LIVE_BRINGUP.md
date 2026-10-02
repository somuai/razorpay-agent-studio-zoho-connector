# Live bring-up runbook

Live mode remains **not verified** until the author confirms the final read-only smoke run against a personal throwaway Zoho Inventory organization in the India data center. Never use the institutional organization. Keep `.env`, grant codes, refresh tokens, account identifiers, and screenshots with personal data out of Git and chat.

## One-time manual setup

Create the throwaway organization and fictional records using [LIVE_TEST_DATA.md](LIVE_TEST_DATA.md). Create a Zoho Self Client with only the read scopes listed in [API_NOTES.md](API_NOTES.md). Put the client ID, client secret, `ZOHO_ORG_ID`, and `ZOHO_DC=in` in the local ignored `.env` file. The shell must export these values because Make does not load `.env` automatically. `ZOHO_REFRESH_TOKEN` may be blank; `make zoho-token` stores it in the private token file. Do not paste credentials or grant codes into chat.

In zsh, load the local file into the command environment with `set -a; source .env; set +a` (do not enable shell tracing). The refresh-token line may remain blank because the token helper stores its value in the ignored token file.

## Command sequence

Run these in order from the repository root:

1. `make live-token-status`
   - Makes no network request. It prints token-file presence, mode, key names, access-token presence and expiry, plus whether the cache is bound to the currently configured client credentials. It never prints values.
2. `make live-preflight`
   - Without client ID, client secret, and Inventory organization ID, it prints `SKIPPED` and exits 0 without contacting Zoho.
   - With credentials, it validates local configuration, token-file permissions, cached or refreshed access-token availability, organization membership, scopes, and one inexpensive read on each required resource. It reports a call budget and masked identifiers. It reuses a valid client-bound cached token instead of forcing a refresh.
   - A failed check prints one actionable fix. Do not continue until preflight passes.
3. `make zoho-token`
   - Enter the newly generated grant code at the hidden prompt immediately after generating it; it expires in roughly 1–2 minutes.
   - Success writes the refresh token only to the local token file with mode `0600`, after checking that Zoho's returned API domain matches `ZOHO_DC`. The live commands read the refresh token from that file unless `ZOHO_REFRESH_TOKEN` is explicitly set.
   - `invalid_grant` means the code expired, was already used, or does not match the client/DC. Generate a fresh code and rerun this step.
4. `make live-preflight`
   - Repeats the checks using the newly saved token. A DC mismatch, wrong Inventory organization ID, missing scope, or exhausted quota is called out separately.
5. `make live-smoke`
   - Calls the eight MCP tools and prints a concise masked JSON summary per tool, including upstream-call count and cache status. A tool error returns nonzero; use its generic category and the local debug logs, never share credentials.
   - Token acquisition happens once before tool calls; if it fails, smoke prints the token-phase diagnostic and stops without repeating the failed token request eight times. Authentication failure during a tool call also stops the remaining tools.
6. `make live-probe`
   - Performs read-only endpoint probes and writes field-name/type findings to `docs/LIVE_FINDINGS.md`. A result is `INCONCLUSIVE` when the org lacks suitable records. No response values are recorded.
7. `make live-assert`
   - Reads the private local `live_expected.yaml` copied from `live_expected.example.yaml`, calls the connector tools, and prints a pass/fail diff for each expected item/order. Delivery proof should be `not_available`; Zoho's documented shipment schema has no delivered-at timestamp.

Inventory resource operations in preflight, smoke, probe, and assertion are GET-only. OAuth token exchange/refresh uses Zoho Accounts POST endpoints; it does not write Inventory records. Keep the debugging loop to one focused pass: copy the exact masked failure category, inspect `docs/API_NOTES.md` and `docs/LIVE_FINDINGS.md`, fix only what the observed response supports, then rerun the failing command and offline gates. Do not turn a failed or inconclusive probe into a confirmed API claim.

## Failure guide

| Failure | Meaning | Next action |
|---|---|---|
| Required variables missing | Local environment is incomplete | Set the credential names listed by preflight in the shell; never print values. |
| Token file missing or permissions too broad | No private refresh token is available or its file is unsafe | Run `make zoho-token`; it writes with mode `0600`. |
| Cached token does not match client credentials | Access-token cache belongs to a different client configuration or predates credential binding | Confirm the Self Client credentials, then run preflight once; a successful refresh binds the new cache. |
| Python `httpx` connect timeout | Python could not open the Zoho connection; curl may use a different resolver or TLS path | Check the network/VPN and retry after connectivity recovers; avoid repeated token attempts. |
| OAuth `invalid_grant` | Refresh grant is expired, revoked, or belongs to another client | Generate a fresh read-only code and exchange it immediately. |
| OAuth `invalid_client` | Current client ID/secret do not match the token's client | Verify the Self Client credentials; do not retry token minting repeatedly. |
| Token endpoint HTTP 429 or throttle text | Zoho rejected token generation as too frequent | Wait at least 10 minutes before another token request. |
| Token endpoint transport failure | No HTTP response was received from the Accounts host | Check the printed transport phase and network path; do not treat it as a Zoho OAuth error response. |
| API domain/DC mismatch | The OAuth grant came from a different Zoho data center | Recreate the client/grant in India and set `ZOHO_DC=in`. |
| Organization not listed | Wrong ID, wrong account, or missing settings scope | Copy the Inventory `organization_id` from that personal account's Organization Profile; do not use the Zoho account-level ID. |
| Missing scope | Consent did not include a required read scope | Revoke/recreate the Self Client grant with only the documented read scopes. |
| Daily quota exceeded | The org's shared daily API budget is exhausted | Stop live calls until reset; do not retry repeatedly. |
| Empty data or assertion mismatch | Manual fixtures differ from the expected file, or the schema differs | Check the named row/field; update only local expectations for intentional fixture choices. |
| `INCONCLUSIVE` probe | The org does not contain data needed to exercise that API shape | Add the specified fictional fixture by hand or leave the claim unresolved. |
