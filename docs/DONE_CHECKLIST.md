# Completion checklist and evidence

This checklist records commands actually run in this workspace. A green offline gate does not establish live Zoho compatibility or merchant impact. Live verification remains pending until the author runs the smoke path against a real throwaway org and confirms it.

## Quality gates

- [x] `make lint` — `ruff check .`: all checks passed; `ruff format --check .`: 77 files already formatted.
- [x] `make typecheck` — mypy: success, no issues in 28 source files.
- [x] `make test` — 86 passed; total source coverage 89.44% (threshold 85%).
- [x] `make spec` — generated and verified `mcp/tool_spec.json`; 8 registered tools.
- [x] `make eval` twice — all three JSON outputs compared byte-for-byte and were identical. The report is labeled **SIMULATED**. Latest summary: 54/200 baseline out-of-stock nudges (27%) vs 0/200 connector-aware; 18/40 evidence-complete; 0.15 cart calls/decision; 87.85% cache hits.
- [x] `make demo` — started the fictional mock API and separate MCP stdio server; MCP client drove in-stock, low-stock, out-of-stock, evidence, and forced 429/backoff scenarios. Metrics summary: 5 tool events, 3 retries, 1 throttled tool call, 1 tool error.
- [x] `make live-smoke` without credentials — skipped cleanly; required `ZOHO_*` credentials are not configured.
- [x] `python scripts/seed_zoho.py --dry-run` — reported 10 fictional items, 8 orders, 4 packages, up to 2 shipments; no credentials or network used.
- [x] `make check-secrets` — secrets audit clean. Obvious mock/example placeholders are excluded from the secret-like literal match.
- [ ] `make clean-clone-test` — pending final commit; this target clones `HEAD`, so run after committing the candidate.
- [ ] Live Zoho verification and author-captured screenshots — pending external org credentials and author confirmation. Do not substitute mock output.

## Requirement evidence map

| Requirement | Evidence |
|---|---|
| FR-1 OAuth state, offline access, single-flight refresh, private token file, DC routing | `tests/test_auth.py`, `tests/test_oauth_flows.py` |
| FR-2 GET-only Inventory client, typed failures, 401 retry, bounded network/5xx handling | `tests/test_client.py`, `tests/test_read_only_surface.py` |
| FR-3 rate limits, retry bounds, no retry on code 45, breaker, metrics | `tests/test_client.py`, `tests/test_ratelimit.py` |
| FR-4 TTL cache and bypass | `tests/test_cache.py`, `tests/test_mcp_tools.py` |
| FR-5 tools, schema, tool spec, stock/evidence composition | `tests/test_mcp_tools.py`, `tests/test_services.py`, `tests/test_spec.py`, `make spec` |
| FR-6 output cap and PII projections | `tests/test_mcp_tools.py`, `tests/test_projections.py` |
| FR-7 agent-facing errors | `tests/test_mcp_tools.py` |
| FR-8 event schema and emission | `tests/test_events.py` |
| FR-9 fictional mock, OAuth, pagination and fault injection | `tests/test_mock_server.py` |
| FR-10 deterministic simulated evaluation | `tests/test_eval.py`, repeated `make eval` comparison |
| FR-11 offline demo, live smoke skip, Inspector instructions | `make demo`, `make live-smoke`, `docs/INSPECTOR_DEMO.md` |
| FR-12 docs set | inventory below |
| FR-13 validated query/filter construction | `tests/test_query_builder.py`, `tests/test_mcp_tools.py` |
| FR-14 separate, explicit fictional-data seed helper | `scripts/seed_zoho.py --dry-run`; live writes unverified and not run |
| FR-15 separate PII-minimized audit event | `tests/test_audit.py` |
| NFR-8 stdio stdout hygiene | `tests/test_stdio_hygiene.py` |
| NFR-9 clean clone / README quickstart | `make clean-clone-test` pending commit |

## Documentation inventory (FR-12)

- [x] `README.md` — merchant problem, three metrics, simulated headline, live status, quickstart.
- [x] `docs/DESIGN.md` — architecture, trade-offs, exclusions, production extensions tied to M1–M3.
- [x] `docs/API_NOTES.md` — cited Zoho facts and explicit `UNVERIFIED` items.
- [x] `docs/TOOLS.md` — one example call/response for each of eight tools.
- [x] `docs/AGENT_CAPABILITIES.md` — CAN / CANNOT / DEPENDS ON boundaries.
- [x] `docs/MEASUREMENT.md` — definitions, event schema, real measurement design, kill criteria.
- [x] `docs/MERCHANT_DISCOVERY.md` — discovery questions, hypotheses, data requests, pivots, week-one plan.
- [x] `docs/MERCHANT_SUMMARY.md` — plain-language visibility, boundaries, data flow, failures and merchant asks.
- [x] `docs/LIMITATIONS.md` — limits with production fixes.
- [x] `docs/WALKTHROUGH.md` — three-minute narration outline.
- [x] `docs/INSPECTOR_DEMO.md` — mock and live inspection instructions.
- [x] `docs/ASSUMPTIONS.md` — ambiguity decisions.
- [x] `docs/PLAN.md` — milestones, gates, risks and progress.
- [x] `docs/assets/README.md` — author screenshot placeholder; no screenshots fabricated.

## Before claiming complete

1. Commit the candidate, then run `make clean-clone-test` and record its result above.
2. Finish the read-only adversarial review and fix any actionable findings.
3. Keep live status as “not yet verified” until an author-confirmed real-org run exists.
4. Final report must state what was built, three run commands, test/eval results, live-unverified facts, top limitations, and the first merchant discovery questions.
