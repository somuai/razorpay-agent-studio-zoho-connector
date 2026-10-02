# Completion checklist and evidence

This checklist records commands actually run in this workspace. A green offline gate does not establish live Zoho compatibility or merchant impact. Live verification remains pending until the author runs the smoke path against a real throwaway org and confirms it.

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
- [x] OAuth refresh diagnostics and cross-process access-token cache — Accounts failures now expose only safe status/error/description/host or exception class; the private `0600` token file persists access-token expiry and is reused for five minutes of validity. Offline gates: `make test` 119 passed / 90.26% coverage, lint/typecheck/spec/secrets clean. No live call made during this change.
- [x] `make zoho-token` hardening — hidden grant-code prompt; invalid/expired grant guidance; API-domain/DC validation; `0600` token-file persistence; code/token non-disclosure verified in `tests/test_zoho_token.py`.
- [x] `make live-probe` and `make live-assert` — shape-only report and expected-data assertions are implemented and covered offline. Neither has been run against Zoho; `docs/LIVE_FINDINGS.md` remains an INCONCLUSIVE template.
- [x] `python scripts/seed_zoho.py --dry-run` — reported 10 fictional items, 8 orders, 4 packages, up to 2 shipments; no credentials or network used.
- [x] `make check-secrets` — secrets audit clean. Obvious mock/example placeholders are excluded from the secret-like literal match.
- [x] `make live-smoke` — skipped cleanly with credential variables unset; refresh token may be read from the private token file.
- [x] `make clean-clone-test` — passed against commit `a63b8de`; README placeholder check passed, fresh clone installed 47 locked packages, deterministic SIMULATED eval printed updated 1.65 calls/dispute and 9.6% combined quota, offline demo completed (5 events / 3 retries / 1 throttled call), and MCP spec generated and verified.
- [ ] Live Zoho verification and author-captured screenshots — pending external org credentials and author confirmation. Do not substitute mock output.

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
