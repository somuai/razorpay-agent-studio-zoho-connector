# Execution Plan — Zoho Inventory connector for Razorpay Agent Studio

**Status:** M1–M10 implementation and live Zoho API verification complete; author screenshots and final commit review remain.
**Scope:** M1–M10. M11 (optional Gemini example) is explicitly deferred until M1–M10 are green.
**Merchant:** Kaveri Home Goods is fictional. No merchant interview is claimed. The read-only Zoho path passed preflight, smoke, probe, and assertions on 2026-10-03; Agent Studio runtime integration is not claimed.

## Verification order and constraints

1. Verify OAuth endpoints, India data-center routing and token behavior from current Zoho docs.
2. Verify exact read-only scopes, organization ID placement, endpoint paths and pagination.
3. Verify stock fields and package/shipment/invoice evidence paths before making product claims.
4. Verify rate limits and error codes; mark non-public/unclear limits `UNVERIFIED` and configurable.
5. Then run the mock, client, tools, simulations, demo, documentation and final gates.

The docs-verifier owns only `docs/API_NOTES.md`. Live credentials are optional for M5 readiness; without them `make live-smoke` must skip cleanly. Only the author can confirm live proof. No screenshots or live transcripts will be fabricated.

## Milestones

| Milestone | Work and paths | Requirements | Gate / evidence | Main risk and response |
|---|---|---|---|---|
| M1 — plan and scaffold | `docs/PLAN.md`, `docs/API_NOTES.md`, `docs/ASSUMPTIONS.md`, `docs/DONE_CHECKLIST.md`, Makefile/config | NFR-1, 5, 6; FR-12 | `make lint`; API fact has a doc URL or `UNVERIFIED` | Baseline had prior implementation files deleted in the checkout; recover tracked versions first, then inspect them against v2. |
| M2 — mock | `mock_zoho/`, `tests/test_mock_server.py` | FR-9; NFR-2, 4 | `make mock-server`; mock OAuth, pagination and injected faults | Mock drift; align to verified API notes and preserve fictional deterministic fixtures. |
| M3 — OAuth | `auth/oauth.py`, `auth/token_manager.py`, `tests/test_auth.py` | FR-1; NFR-1 | `pytest tests/test_auth.py` | Refresh races or secret leakage; lock refresh and capture logs in tests. |
| M4 — client resilience | `client/`, `ratelimit/`, `cache/`, related tests | FR-2, 3, 4, 13; NFR-2, 3 | client/rate/cache/query tests; source scan for non-GET methods | Retry amplification and query injection; bounded GET retries, code-45 no-retry, strict validated builders. |
| M5 — live readiness | `scripts/seed_zoho.py`, `examples/live_preflight.py`, `examples/zoho_token.py`, `examples/live_smoke.py`, `examples/live_probe.py`, `examples/live_assert.py`, Makefile, live runbook/data docs | FR-11, 14; NFR-9 | Live preflight/smoke/probe/assert passed against throwaway India org on 2026-10-03; first assertion exposed cross-order packages, fixed and verified 15/15; screenshot captures remain pending | Connectivity is intermittent; bounded retries and one-command burst preserve safe diagnostics. |
| M6 — tools and projections | `models/`, `services/`, `mcp_server/`, `mcp/tool_spec.json`, tests | FR-5, 6, 7; NFR-8 | `make spec`; tool/projection/stdout tests | Zoho schema uncertainty; project only verified fields and say `not_available` where absent. |
| M7 — observability and evaluation | `events/`, `eval/`, `docs/MEASUREMENT.md` | FR-8, 10, 15 | `make eval` twice; JSON byte comparison | Results could look real; label every table and artifact `SIMULATED`, seed all data and timestamps. |
| M8 — offline demo | `examples/demo.py` or current equivalent | FR-11.1 | `make demo` with no network or Zoho credentials | Demo cannot start children reliably; use bounded subprocess lifecycle and clear cleanup. |
| M9 — documentation | `README.md`, all FR-12 docs | FR-12; NFR-9 | doc inventory, first-screen review, `make clean-clone-test` | Overclaiming; distinguish simulated results, assumptions and unverified live behavior. |
| M10 — adversarial review and audit | reviewer findings, fixes, `docs/DONE_CHECKLIST.md` | All FR/NFR and acceptance criteria | all final commands, secret scan, source GET-only scan, docs checklist with pasted output | A green unit suite can miss integration gaps; review claims, error paths, data exposure and instructions separately. |

## Parallel work boundaries

- **Zoho docs verifier:** `docs/API_NOTES.md` only.
- **Merchant docs writer:** `README.md` and its assigned audience docs only; document observed behavior and gaps.
- **Evaluation analyst:** `eval/` and `docs/MEASUREMENT.md` only.
- **Reviewer:** read-only review after M9; main thread fixes findings.
- Main thread owns `src/`, mock integration, scripts, Makefile, plan, assumptions and final checklist. No simultaneous writers share a file.

## Cut order

If constrained, defer M11 first, then streamable HTTP, extra edge-case tests beyond gates, optional `list_sales_orders` filters, and Mermaid polish. Do not drop OAuth, rate limiting, stock and dispute decision tools, the evaluation harness, merchant summary, README problem framing, honesty requirements or live-smoke readiness.

## Current progress

- [x] Read `AGENTS.md` and `CODEX_RUNSHEET.md`.
- [x] Restore the tracked project baseline after finding 66 tracked paths deleted from the working tree.
- [x] Create the long-running completion goal and start bounded documentation/evaluation work.
- [x] Reconcile the implementation, scripts, docs and tests to AGENTS.md v2; update API notes and regenerate the MCP spec.
- [x] Complete the offline M1–M9 implementation and documentation work; lint, typecheck, tests, simulated eval, demo, live-smoke skip, seed dry-run and secret scan have run. Record detailed outputs in `docs/DONE_CHECKLIST.md`.
- [x] Finish M10 read-only review and fixes, commit the candidate, and pass `make clean-clone-test` against the live-bring-up prep commit.
- [x] Prepare a safe live bring-up path offline: preflight, hidden grant-code exchange, masked smoke output, read-only response-shape probe, hand-entered expected-data assertions, and schema-drift fallback; no Zoho requests made.
- [x] Obtain author-run live verification for token exchange, preflight, eight-tool smoke, probe and 15/15 assertions. Author-captured screenshots remain pending; do not imply Agent Studio runtime verification.
