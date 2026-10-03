# Completion checklist and evidence

This checklist records commands actually run in this workspace. A green offline gate does not establish live Zoho compatibility or merchant impact. The author has confirmed a live preflight and smoke run; full live probe/assert and author-captured evidence remain pending, so the README continues to say live verification is not yet complete.

## Quality gates

- [x] `make lint` — `ruff check .`: all checks passed; `ruff format --check .`: 90 files already formatted.
- [x] `make typecheck` — mypy: success, no issues in 29 source files.
- [x] `make test` — 113 passed; total source coverage 90.23% (threshold 85%). Includes offline tests for live command skip/masking, token exchange handling, schema drift, and nested package shipment fallback.
- [x] `make spec` — generated and verified `mcp/tool_spec.json`; 8 registered tools.
- [x] `make eval` twice — all three result JSON files compared byte-for-byte and identical. Results are **SIMULATED**, M1 is a mechanism check, and the sensitivity sweep is deterministic. Quota table: warm fixture 0.15 calls/decision → 6,666 / 3,333 / 1,666 decisions at 100/50/25% allocation; cold-cache fixture mix 1.235 calls/decision → 809 / 404 / 202. M2 separates Zoho-documented evidence fields (18/40 in the fixture), schema-faithful delivery proof (0/40; requires carrier integration), and mock-only `delivery_date` presence (18/40).
- [x] `make demo` — started the fictional mock API and separate MCP stdio server; MCP client drove in-stock, low-stock, out-of-stock, evidence, and forced 429/backoff scenarios. Metrics summary: 5 tool events, 3 retries, 1 throttled tool call, 1 tool error.
- [x] Read-only adversarial review — findings fixed: clarified upstream response vs agent-visible fields; changed delivery wording to recorded date (not carrier-confirmed); renamed mock complete-case metric; masked reference/order IDs in audit records and aligned example/docs. Re-review found no remaining actionable findings.
- [x] Zoho dashboard check — signed-in Zoho Inventory dashboard observed in the India data center; Premium trial showed 14 days remaining and setup at 0%. The earlier dashboard was excluded from testing; the current personal throwaway target is still not live-verified. No live API evidence is claimed here.
- [x] `make live-smoke` without credentials — skipped cleanly; required `ZOHO_*` credentials are not configured.
- [x] Live bring-up prep — `live-preflight`, `live-smoke`, `live-probe`, `live-assert`, and `zoho-token` all skipped cleanly when their required environment variables were explicitly unset; no Zoho requests were made. Preflight's offline branch tests cover wrong DC/org, rejected refresh grant, missing scope, quota exhaustion, and unsafe/missing token setup. Probe/assert tests use only the mock or an in-memory fake.
- [x] Preflight placeholder guard — `make test` covers absent, empty, template, and obvious placeholder credential values; `make lint` passes. `live-preflight` now fails with variable names only when a configured credential is empty or placeholder-like, while still skipping cleanly when settings are absent from the environment.
- [x] Preflight diagnostics — added masked endpoint path, HTTP status, Zoho code/message, host, token-scope display, exception class and one-line fixes; offline gates pass (`make lint`, `make test` 118 passed / 90.18% coverage, `make typecheck`, `make spec`, `make check-secrets`). No live call was made during this code change.
- [x] Live logging identifier leak — the 2026-10-02 smoke exposed full request URLs in HTTPX logs. Added process-wide record redaction, quiet HTTP library defaults, safe not-found errors, recursive audit parameter masking, and ignored `.log`/`.jsonl` artifacts. Mock regression tests cover new loggers, exceptions, tool calls and each live helper. Offline gates: `make lint`, `make typecheck`, `make test` (128 passed, 90.34% coverage), `make spec`, two deterministic `make eval` runs, `make demo`, `make check-secrets`, and `make clean-clone-test` all passed. The ignored audit file scan found no raw identifier fields or credential markers. No live request was made for this fix; post-fix live screenshot safety still needs confirmation.
- [x] OAuth refresh diagnostics and cross-process access-token cache — Accounts failures now expose only safe status/error/description/host or exception class; the private `0600` token file persists access-token expiry and is reused for five minutes of validity. Offline gates: `make test` 119 passed / 90.26% coverage, lint/typecheck/spec/secrets clean. No live call made during this change.
- [x] `make zoho-token` hardening — hidden grant-code prompt; invalid/expired grant guidance; API-domain/DC validation; `0600` token-file persistence; code/token non-disclosure verified in `tests/test_zoho_token.py`.
- [x] `make live-probe` and `make live-assert` — shape-only report and expected-data assertions are implemented and covered offline. Neither has been run against Zoho; `docs/LIVE_FINDINGS.md` remains an INCONCLUSIVE template.
- [x] `python scripts/seed_zoho.py --dry-run` — reported 10 fictional items, 8 orders, 4 packages, up to 2 shipments; no credentials or network used.
- [x] `make check-secrets` — secrets audit clean. Obvious mock/example placeholders are excluded from the secret-like literal match.
- [x] `make live-smoke` — skipped cleanly with credential variables unset; refresh token may be read from the private token file.
- [x] `make clean-clone-test` — passed against commit `2cc5ba4` after the log-redaction change; README placeholder check passed, a fresh clone installed 47 locked packages, deterministic SIMULATED eval completed, offline demo completed, and the 8-tool MCP spec generated and verified.
- [ ] Full live verification and author-captured screenshots — the 2026-10-02 post-fix smoke returned transport errors for all eight tools, then the single preflight discriminator failed at token refresh before Inventory calls. `live-probe` and `live-assert` were not run after that failure. Direct unauthenticated curl checks returned Accounts HTTP 200 and Inventory HTTP 401; no proxy variables were set. Live status remains unverified; do not substitute mock output.

## 2026-10-02 live connectivity and request-path investigation

- Direct connectivity check: `https://accounts.zoho.in/` returned HTTP 200; the unauthenticated Inventory organizations route returned HTTP 401; no proxy environment variables were present.
- One `make live-preflight` run exited at access-token refresh after one token endpoint attempt. Inventory calls were not reached. The output gave a generic refresh failure; offline changes now expose safe OAuth error fields and transport metadata for future diagnosis. Do not retry without the author’s credential/throttle check.
- The earlier captured `make live-smoke` exited with errors for all eight tools after four attempts each, with no HTTP status or Zoho code. Its scan matched a long digit run in an internal request ID, not a Zoho identifier; generated request IDs now use letters only.
- Request-path audit of `2cc5ba4`: the only `ZohoClient` change alters `NotFoundError` presentation after a response. The process-wide logging setup changes `LogRecord` text and HTTP logger levels; it does not modify URLs, params, headers, token handling, transports, proxies or retry behavior. Offline regression tests now compare exact mock-transport URL, query params, and Authorization header through the client and full `get_item` tool path with DEBUG logging and the redaction transformation enabled/disabled.
- Current offline verification: `make test` — 133 passed, 89.86% coverage; `make lint`, `make typecheck`, `make spec`, two deterministic `make eval` runs, `make demo`, and `make check-secrets` passed. `make clean-clone-test` passed against committed HEAD; it does not include this uncommitted patch, so rerun after a reviewed commit.

## 2026-10-02 token-cache and transport follow-up

- Unauthenticated Python `httpx.get` to the Accounts homepage failed after 15 seconds with the safe exception chain `ConnectTimeout -> ConnectTimeout -> TimeoutError`; an earlier curl check reached Accounts with HTTP 200 and the unauthenticated Inventory route with HTTP 401. This points to a Python HTTP connect-path/network problem; no credentials or Zoho API token were sent by the Python check.
- Local token status at inspection: file present, mode `0600`, keys `access_token`, `api_domain`, `expires_at`, `refresh_token`; cached access token was present with about 26 minutes remaining. The pre-existing cache has no credential fingerprint, so the new code will deliberately not reuse it until one successful refresh binds it to the configured client credentials.
- Cache audit found `live-preflight` called `get_access_token(force_refresh=True)`, bypassing a valid cached access token on every run. It now reuses a valid client-bound cache and counts a token endpoint call only when a refresh is actually attempted.
- Cache writes previously shared a fixed `.tmp` path and did not associate access tokens with current client credentials. Writes now use a local `flock`, unique mode-0600 temporary file, fsync, and atomic replacement; token loading checks a SHA-256 client-credentials fingerprint, while preserving refresh-token rotation. A failed forced refresh invalidates the rejected access token without deleting the refresh token.
- OAuth diagnostics distinguish token-endpoint HTTP responses from transport failures, report JSON/error metadata safely, and include exception/cause classes, phase, Accounts host and operation only for transport failures. `live-smoke` attempts token acquisition once before tool calls and stops after a token/auth error. `make live-token-status` inspects local metadata only and makes no network request.
- A read-only review found a client-binding bug: token-file refresh tokens were loaded even when the stored client-credentials fingerprint was missing or did not match. Loading now requires a matching fingerprint; an explicitly configured `ZOHO_REFRESH_TOKEN` still takes precedence. `make zoho-token` writes the binding for newly exchanged grants. Regression tests cover changed client ID, changed secret, explicit refresh-token precedence, and token-helper persistence.
- Fresh offline verification for this follow-up: `make lint` passed (96 files formatted); `make typecheck` passed (31 source files); `make test` passed (147 tests, 90.56% coverage); `make spec` generated and verified 8 tools; `make eval` ran successfully with SIMULATED output; `make demo` completed offline; `make check-secrets` reported clean; `make clean-clone-test` passed against committed HEAD. `git diff --check` passed. The working changes are uncommitted.
- `make live-token-status` is local-only: token file present, mode `0600`, key names `access_token`, `api_domain`, `expires_at`, `refresh_token`, cached access token present with about 10.6 minutes left; client credential binding unavailable because this pre-existing file lacks a fingerprint. After the helper is used with the intended Self Client, a fresh token-file fingerprint will be recorded.
- No Zoho API calls were made during this follow-up. A previous no-credential Python HTTPX connectivity check timed out while curl had reached the same Zoho hosts, so the root cause of the earlier live transport failures remains unconfirmed. Do not change live-verification status based on these offline checks.
- Network discrimination check (unauthenticated): `curl -4` returned HTTP 200 in 0.25 s; `curl -6` returned HTTP 200 in 0.19 s. Python HTTPX default and an IPv4-bound `local_address="0.0.0.0"` transport both raised `ConnectTimeout` at 10 s. DNS returned one IPv4 answer and no IPv6 answer for each tested Zoho hostname; no proxy environment variable names were present. This rules against an IPv6-only failure in this check, but does not identify why Python's connect path differs from curl. No authenticated calls were made.
- Transport diagnostics now clearly label Accounts transport failures as network failures, include the sandbox/CI network hint in Accounts and Inventory diagnostics, and do not classify a timeout as a credential failure. A mock preflight regression test verifies the wording and redaction. Live command guidance in `docs/LIVE_BRINGUP.md` now directs runs to the author's normal terminal. No live commands were run for this change.

## 2026-10-02 documentation handoff and fresh offline evidence

- [x] `make test` — 147 passed; total coverage 90.56%. Raw command output saved without editing under `docs/evidence/make-test.txt`, with MOCK / SIMULATED label, date and base commit.
- [x] `make lint` — all checks passed; 99 files already formatted.
- [x] `make typecheck` — mypy success, no issues in 31 source files.
- [x] `make spec` — generated and verified `mcp/tool_spec.json`; 8 tools registered.
- [x] `make eval` twice — stdout and all generated result JSON files compared byte-for-byte and identical. Raw output saved under `docs/evidence/make-eval.txt`; all metrics are SIMULATED.
- [x] `make demo` — completed offline against the local fictional mock; 6 tool events, 3 retries and 1 throttled tool call. Raw output saved under `docs/evidence/make-demo.txt` and labeled MOCK / SIMULATED.
- [x] Evidence identifier scan — `rg -n '[0-9]{8,}' docs/evidence` returned no matches. The captured output values were not edited.
- [x] `make check-secrets` — secrets audit clean.
- [x] `UV_OFFLINE=1 make clean-clone-test` — passed; cloned locally, installed 47 cached locked packages without network, ran eval/demo/spec, and verified README placeholders.
- [x] `make screenshots-check` — reports all nine expected screenshot files missing. No screenshot was generated, edited, or claimed.
- [x] `git diff --check` — passed.
- [x] Documentation handoff — README is 221 lines; `find docs -type f | wc -l` reports 24 files. Added assignment mapping, auth flow, API limit table, public Agent Studio boundary, current quality results, hidden screenshot slots, `FIELD_NOTES.md`, evidence outputs, capture guide, written ten-minute tour and submission note.
- [ ] Full live verification remains pending: earlier preflight (8 calls) and all-tools smoke (14 calls) are historical successes, but live probe and assertion were not run and no screenshots exist. Later connection failures and token-cache correction are documented. No live Zoho calls or network calls were made for this documentation update.

## README forward-deployed handoff rewrite

- Rewrote README in the requested order, keeping live status **not yet verified** and distinguishing previously reported preflight/smoke activity from incomplete probe/assert/screenshots. Numerical claims are traced to `make eval`, `eval/results/summary.json`, `docs/LIVE_FINDINGS.md`, or this checklist.
- Added the three named author screenshot slots only inside an HTML comment, so no broken image/link renders before genuine files exist. Added `docs/assets/CAPTURE_GUIDE.md` with terminal and Inspector capture steps, masking checklist, and digit scan. No screenshots were created or edited.
- `make clean-clone-test` applies the tracked worktree diff and copies the new screenshot capture guide into its fresh clone before running the quickstart, so it tests the revision under review.
- `make clean-clone-test` passed on the README revision: the placeholder scan passed, 47 locked packages installed, the simulated eval and demo ran, and the 8-tool spec was generated and verified.
- Final gates for this README revision: `make lint` passed (97 files formatted), `make typecheck` passed (31 source files), `make test` passed (147 tests, 90.56% coverage), `make spec` generated and verified 8 tools, `make eval` and `make demo` completed, `make check-secrets` was clean, and `git diff --check` passed. No Zoho calls, screenshots or commits were made for the README rewrite.
- Reviewer follow-up: added the five-item manual UI stock comparison (explicitly not an API result), the fictional cart failure scenario, and actual mock output excerpts for unavailable stock and partial evidence. The demo now exercises a partial evidence order (`so_2035`) in addition to the complete case; its observed summary reports 6 tool events and 3 retries. Customer-email order lookup is marked unverified across README, tool docs, capabilities and generated spec; implementation resolves exact contacts and then lists by `customer_id`. No live/network calls were made.
- Reviewer follow-up gate results: `make lint` passed (97 files formatted); `make typecheck` passed (31 source files); `make test` passed (147 tests, 90.56% coverage); `make spec` generated and verified 8 tools; `make eval` and `make demo` completed; `make check-secrets`, `make clean-clone-test`, and `git diff --check` passed. The clean clone applied the current tracked diff and included the new capture guide. No live Zoho calls or commit made.

## Requirement evidence map

| Requirement | Evidence |
|---|---|
| FR-1 OAuth state, offline access, single-flight refresh, private token file, DC routing | `tests/test_auth.py`, `tests/test_oauth_flows.py` |
| FR-2 GET-only Inventory client, typed failures, 401 retry, bounded network/5xx handling | `tests/test_client.py`, `tests/test_read_only_surface.py` |
| FR-3 rate limits, retry bounds, no retry on code 45, breaker, metrics | `tests/test_client.py`, `tests/test_ratelimit.py` |
| FR-4 TTL cache and bypass | `tests/test_cache.py`, `tests/test_mcp_tools.py` |
| FR-5 tools, schema, tool spec, stock/evidence composition | `tests/test_mcp_tools.py`, `tests/test_services.py`, `tests/test_spec.py`, `make spec` |
| Schema-drift tolerant stock/order projections; list-sales-order 400 recovery | `tests/test_services.py`, `tests/test_mcp_tools.py` |
| FR-6 output cap and PII projections | `tests/test_mcp_tools.py`, `tests/test_projections.py` |
| FR-7 agent-facing errors | `tests/test_mcp_tools.py` |
| FR-8 event schema and emission | `tests/test_events.py` |
| FR-9 fictional mock, OAuth, pagination and fault injection | `tests/test_mock_server.py` |
| FR-10 deterministic simulated evaluation | `tests/test_eval.py`, repeated `make eval` comparison |
| FR-11 offline demo, live smoke skip, Inspector instructions | `make demo`, `make live-smoke`, `docs/INSPECTOR_DEMO.md` |
| Live bring-up commands, masked output, and test-data assertions | `examples/live_preflight.py`, `examples/live_smoke.py`, `examples/live_probe.py`, `examples/live_assert.py`; offline tests under `tests/test_live_*.py` and `tests/test_zoho_token.py` |
| FR-12 docs set | inventory below |
| FR-13 validated query/filter construction | `tests/test_query_builder.py`, `tests/test_mcp_tools.py` |
| FR-14 separate, explicit fictional-data seed helper | `scripts/seed_zoho.py --dry-run`; live writes unverified and not run |
| FR-15 separate PII-minimized audit event | `tests/test_audit.py` |
| NFR-8 stdio stdout hygiene | `tests/test_stdio_hygiene.py` |
| NFR-9 clean clone / README quickstart | `make clean-clone-test` passed against committed HEAD |

## Documentation inventory (FR-12)

- [x] `README.md` — merchant problem, three metrics, simulated headline, live status, quickstart.
- [x] `docs/DESIGN.md` — architecture, trade-offs, exclusions, production extensions tied to M1–M3.
- [x] `docs/API_NOTES.md` — cited Zoho facts and explicit `UNVERIFIED` items.
- [x] `docs/TOOLS.md` — one example call/response for each of eight tools.
- [x] `docs/AGENT_CAPABILITIES.md` — CAN / CANNOT / DEPENDS ON boundaries.
- [x] `docs/MEASUREMENT.md` — definitions, event schema, real measurement design, kill criteria.
- [x] `docs/MERCHANT_DISCOVERY.md` — discovery questions, hypotheses, data requests, pivots, week-one plan.
- [x] `docs/MERCHANT_SUMMARY.md` and `docs/MERCHANT_SUMMARY_TECHNICAL.md` — one-page operations summary with can-see/masked/never-do table; implementation settings and fields moved to the linked appendix.
- [x] `docs/LIMITATIONS.md` — limits with production fixes.
- [x] `docs/WALKTHROUGH.md` — three-minute narration outline.
- [x] `docs/INSPECTOR_DEMO.md` — mock and live inspection instructions.
- [x] `docs/LIVE_BRINGUP.md`, `docs/LIVE_TEST_DATA.md`, `docs/LIVE_FINDINGS.md`, and `live_expected.example.yaml` — ordered runbook, fictional test fixture checklist, inconclusive findings template, and expected output example.
- [x] `docs/ASSUMPTIONS.md` — ambiguity decisions.
- [x] `docs/PLAN.md` — milestones, gates, risks and progress.
- [x] `docs/assets/README.md` — author screenshot placeholder; no screenshots fabricated.

## Before claiming complete

1. Keep live status as “not yet verified” until an author-confirmed real-org run exists.
2. Final report must state what was built, three run commands, test/eval results, live-unverified facts, top limitations, and the first merchant discovery questions.

## 2026-10-03: bounded connect retries and one-command live bring-up

- [x] Accounts token exchange and refresh retry only connect/TLS transport failures, at most four attempts with jitter; any HTTP response returns directly to OAuth parsing and is never retried. Owned HTTP clients use a five-second connect timeout. Inventory calls use the same connect timeout and bounded connect-only retries, capped at four; non-connect transport failures keep the existing bounded retry behavior. Request replay tests compare method, URL, form/query data and headers where applicable.
- [x] `make net-watch ARGS=--mock` — local unauthenticated Accounts and Inventory endpoints returned HTTP responses; no Zoho host was contacted.
- [x] `make live-burst ARGS=--mock` — all stages completed: environment validation, host watch, token status, preflight, smoke, probe and assert. The final scan reported `SAFE TO SCREENSHOT`. Outputs were written below `.live_out/`, and `git check-ignore -v` confirmed that path is ignored.
- [x] Orchestration regression tests — mock burst completes all stages, stops at the first failure, redacts a deliberately supplied secret from terminal output, and leaves the real live findings file unchanged.
- [x] Reused the five-second connect timeout for preflight and shape-probe HTTP clients as well as the core token and Inventory clients. Updated the historical organization note in `API_NOTES.md` and `LIVE_FINDINGS.md` to reflect the author's correction; plan eligibility remains unverified.
- [x] `make lint` — passed; Ruff reports 101 files already formatted.
- [x] `make typecheck` — passed; mypy checked 31 source files.
- [x] `make test` — 157 passed; source coverage 90.61% (threshold 85%).
- [x] `make spec` — generated and verified the MCP specification with 8 tools.
- [x] `make eval` twice — stdout and generated JSON files were byte-identical; stdout SHA-256 `93deaf90746ed9afb980f744eebcf04cc29d6a15ca112b88e582e1c3d08e2d1b`. All results are SIMULATED.
- [x] `make demo` — completed offline against the local fictional mock.
- [x] `make check-secrets` — secrets audit clean.
- [x] `UV_OFFLINE=1 make clean-clone-test` — passed; local clone installed from cache and completed eval, demo and spec checks.
- [x] `make screenshots-check` — lists all nine author-capture files as missing. No screenshot was generated or edited.
- [x] `python scripts/scan_live_outputs.py ...` — all captured mock burst step outputs scanned clean. The ignored output directory contains only fake mock credentials and mock data.
- [x] Read-only public GitHub browser review — main page latest commit matched local committed HEAD `3be32e8`; README tables and Mermaid rendered; docs tree exposed all expected docs; evidence files and findings/field notes were reviewed; ten README-linked docs opened successfully. The browser session already displayed a GitHub account avatar, so this was not performed in a private/logged-out window as requested. No GitHub controls were used to modify the repository.
- [ ] Live Zoho preflight/smoke/probe/assert remain unverified in this task. No Zoho host, authenticated API, Zoho Console, credentials, grant codes, token file values, or `.env` contents were accessed. Do not change README live status.
- [ ] No commit or push was made; the changes remain local for review.

## 2026-10-03: preflight retry-path correction

- [x] Investigation: `examples/live_preflight.py` sent Inventory GETs directly through its `httpx.AsyncClient` and passed literal `attempt=1` into transport diagnostics, bypassing `ZohoClient` retries. `live-smoke`, `live-probe`, and `live-assert` construct/use `ZohoClient`; its connection retry logic was active but the attempt budget was not shared with the documented `ZOHO_CONNECT_RETRIES` setting.
- [x] Implemented shared `ZOHO_CONNECT_RETRIES` budget (default four, configurable 1–10), five-second connect timeout, jittered connect-only retries, accurate attempt totals and per-attempt phase diagnostics. HTTP responses are returned directly and never retried by this policy.
- [x] Added offline MockTransport regressions for preflight, smoke, probe and assert. Preflight exhaustion reports four Inventory attempts and a phase entry for each; smoke, probe and assert report actual upstream attempts after transient connect failures, while probe/assert also show each exhausted attempt phase.
- [x] `make lint` — passed; Ruff checks passed, 102 files formatted.
- [x] `make typecheck` — passed; mypy checked 31 source files.
- [x] `make test` — 164 passed; total source coverage 90.60% (threshold 85%).
- [x] `make spec` — generated and verified the 8-tool MCP specification.
- [x] `make eval` twice — stdout and all three `eval/results/*.json` files were byte-identical; stdout SHA-256 `93deaf90746ed9afb980f744eebcf04cc29d6a15ca112b88e582e1c3d08e2d1b`.
- [x] `make demo` — completed offline against the fictional local mock.
- [x] `make check-secrets` — secrets audit clean.
- [x] `UV_OFFLINE=1 make clean-clone-test` — passed with locally cached dependencies; eval, demo and spec completed in the clone.
- [x] `git diff --check` — passed.
- [x] No Zoho or other external network calls were made for this investigation. No commit was made.
- [ ] Live preflight, smoke, probe and assert remain unverified; do not update the README live-verification claim from these mock tests.
