# AGENTS.md — Zoho Inventory Connector for Razorpay Agent Studio (Technical PRD)

> Codex reads this file at the start of every task. It is both the product spec and the working agreement.
> If anything here conflicts with a chat prompt, ask nothing: follow this file, record the conflict in `docs/ASSUMPTIONS.md`, and continue.

---

## 0. Why this repo exists (read first)

This is a take-home assignment for a **Forward-Deployed Engineer, Agent Studio** role at Razorpay (Bangalore, on-site). The role owns the merchant relationship end to end: sit with the merchant, find the real problem behind the ask, design and build the first working version, and prove whether it moved the metric. It is "not a demo or ticket-closing role."

The assignment (Option 3): *Build a private connector for a merchant tool (we chose **Zoho Inventory**) that lets an Agent Studio agent read inventory/orders. Include a working OAuth or API-key flow, list/get/search primitives, rate-limit handling, an MCP tool specification, and a short document of what the agent can and cannot do. No real customer data, passwords, API keys, or credentials.*

**Reviewer's lens.** The checklist above is table stakes. The submission is judged on: (1) did the author find a real merchant problem, (2) is the connector designed for an LLM agent as its user, (3) is impact *measured honestly*, (4) is the writing clear enough to hand to a merchant's ops head. Engineering and framing carry equal weight. Never ship code without the matching doc, and never ship a claim without a command that reproduces it.

Context: Agent Studio is Razorpay's agent marketplace/builder, built on Anthropic's Claude Agent SDK. Launch agents include Abandoned Cart Conversion, Dispute Responder, Subscription Recovery, and Cashflow Forecaster. Our connector serves the first two.

---

## 1. Problem statement

**Fictional merchant:** *Kaveri Home Goods*, a D2C home-decor brand in Bangalore. Razorpay Checkout on its own site; Zoho Inventory for stock and sales orders. (Fictional. Never imply a real interview happened.)

| # | Stated ask | Real problem (our hypothesis) | Agent affected |
|---|---|---|---|
| P1 | "Recover more abandoned carts." | Nudges and discounts are sent for SKUs that are out of stock or nearly so. Discount budget is wasted and customers are disappointed. The agent has no stock awareness. | Abandoned Cart Conversion |
| P2 | "Win more chargebacks." | Rebuttals need fulfillment evidence (order, invoice, packed/shipped/delivered status and dates, tracking). Ops assembles it by hand across tools; it is slow and often incomplete. | Dispute Responder |

**Success metrics (must be defined in `docs/MEASUREMENT.md`, computed in `eval/`):**

- **M1 — Wasted nudges:** % of nudges sent for unavailable SKUs, and fictional-INR discount budget wasted. Target in simulation: reduce to 0 for out-of-stock SKUs.
- **M2 — Dispute evidence completeness:** % of seeded disputes with complete fulfillment evidence from one tool call, with missing fields enumerated for partials.
- **M3 — Agent cost:** API calls per decision / per case, and Zoho daily quota consumed (% of free-plan cap of 1,000/day).

All results are **SIMULATED on fictional data** and must say so wherever shown.

---

## 2. Goals and non-goals

**Goals**
1. Read-only Zoho Inventory connector with correct OAuth2 (India data center first).
2. MCP server exposing agent-friendly tools: bounded, PII-masked, self-explaining errors.
3. Quota-aware rate limiting and caching that keeps an agent inside Zoho's limits.
4. Deterministic mock Zoho server so everything is demonstrable and testable offline.
5. Measurement harness and event instrumentation so impact could be measured in production.
6. Merchant-facing and discovery documentation written in plain language.

**Non-goals (document each in `docs/DESIGN.md` under "What I chose not to build and why")**
- Any write operation (stock adjustments, order creation, refunds). Read-only by construction.
- Webhooks, multi-tenant OAuth, a UI, a database, or a distributed limiter (describe as the production path).
- Real merchant data, real customer data, or invented customer quotes or uplift numbers.
- Wiring into Razorpay's real Agent Studio runtime (not publicly specified; describe the integration shape only).

---

## 3. Users and stories

- **Agent (primary user):** "Before I nudge for SKU X, tell me if it's sellable now." "Give me everything needed to rebut dispute on order SO-123, and tell me exactly what's missing."
- **Merchant ops head (secondary):** "Show me what the agent can see and never do." "Tell me when data is stale or missing instead of guessing."
- **FDE (me):** "Prove the impact, state the limits, and show what I'd ask the merchant next."

---

## 4. Functional requirements

Each requirement has an ID. Tests and docs must reference IDs (e.g. `# FR-3.4` in test names or docstrings). Acceptance criteria (AC) are binary.

### FR-1 Authentication (OAuth2)
- FR-1.1 Authorization-code flow with a loopback redirect server. `state` for CSRF; PKCE if Zoho supports it. Request `access_type=offline` and the minimal read-only scopes.
- FR-1.2 Headless path: refresh token supplied by env (Zoho "Self Client" flow) for CI and demos.
- FR-1.3 `TokenManager`: caches the access token, refreshes before expiry, **single-flight** refresh (asyncio lock) so N concurrent calls trigger exactly one refresh. Never mint a token per request (Zoho limits token generation).
- FR-1.4 Refresh token persisted to a gitignored file, mode `0600`. Never logged. Optional OS keyring.
- FR-1.5 Data-center routing: derive `api_domain` from the token response; fall back to `ZOHO_DC` (default `in`).
- AC: 50 concurrent calls with an expired token produce exactly 1 refresh call; token strings never appear in captured logs; auth URL contains `state`.

### FR-2 HTTP client
- FR-2.1 Async `httpx` client; **GET-only** surface; injects `Authorization: Zoho-oauthtoken <token>` and `organization_id`.
- FR-2.2 Typed errors: `AuthError`, `RateLimitError(kind, retry_after)`, `NotFoundError`, `UpstreamError`, `QuotaExhaustedError`, `CircuitOpenError`.
- FR-2.3 On 401: refresh once, retry once, else `AuthError`.
- FR-2.4 Timeouts and bounded retries for 5xx/network errors (idempotent GETs only).
- AC: a test asserts no HTTP method other than GET is ever issued by any code path or tool; failing it fails CI.

### FR-3 Rate limiting
- FR-3.1 Client-side token bucket, default 80 req/min (below Zoho's 100/min/org). Configurable.
- FR-3.2 Concurrency semaphore, default 5 (Zoho soft limit is about 10).
- FR-3.3 HTTP 429: honor `Retry-After` if present, else exponential backoff with full jitter, bounded attempts.
- FR-3.4 Daily quota exceeded (Zoho code 45): **do not retry**. Raise `QuotaExhaustedError` with an agent-readable message and reset guidance.
- FR-3.5 Org block (code 44) or concurrency error (1070): open a circuit breaker with a cool-down; calls fail fast with `CircuitOpenError`.
- FR-3.6 Metrics object: calls made, throttled, retried, cache hits, quota estimate.
- AC: burst of 300 calls against the mock never exceeds the budget per rolling minute; code 45 triggers zero retries; breaker opens on code 44 and recovers after the cool-down (use an injectable clock; no real sleeps in unit tests).

### FR-4 Cache
- FR-4.1 In-process TTL cache for read lookups (items, org info). Stock availability has a short TTL (default 60s). All TTLs configurable and documented. `bypass_cache` flag on stock tools.
- FR-4.2 Responses expose `as_of` (ISO timestamp) and `cached` so the agent can judge staleness.
- AC: repeated stock check within TTL consumes 0 additional upstream calls; `as_of` is present on every stock response.

### FR-5 MCP server and tools
FastMCP server; stdio by default, streamable HTTP optional. **Read-only.** Tool descriptions must say when to use the tool and when not to. All inputs have JSON-schema constraints (max lengths, enums, bounded `limit`).

| Tool | Purpose | Key inputs | Key outputs |
|---|---|---|---|
| `list_items` | Browse catalog | `page`, `per_page<=50`, `status`, `fields?` | items[], `has_more`, `next_page`, `truncated` |
| `get_item` | One item detail | `item_id` | item projection |
| `search_items` | Find by name/SKU | `query`, `sku?`, `only_low_stock?`, `limit<=25` | items[], `truncated` |
| `get_stock_availability` | **Cart-nudge decision primitive** | `skus_or_ids[]<=20` | per-SKU `status` (`in_stock`/`low_stock`/`out_of_stock`/`unknown`), `quantity`, `warehouses[]`, `as_of`, `cached` |
| `list_sales_orders` | Browse orders | `status?`, `customer_id?`, `date_from?`, `date_to?`, `page` | orders[], paging |
| `get_sales_order` | One order | `salesorder_id` | order projection |
| `search_sales_orders` | Match payment to order | `reference_number?` or `customer_email?` or `razorpay_order_id?` | orders[], `match_basis` |
| `get_order_fulfillment_evidence` | **Dispute-evidence primitive** | `salesorder_id` | composed evidence with per-field `present`/`not_available`, `completeness` (`complete`/`partial`/`none`), `missing[]` |

- FR-5.1 `mcp/tool_spec.json` generated from the server; a test fails if it drifts.
- FR-5.2 `low_stock` threshold derives from the item's reorder level if present, else a configurable default; document it.
- FR-5.3 `search_sales_orders` by `razorpay_order_id` relies on the merchant storing it in `reference_number` or a custom field. Document as an assumption and surface `match_basis` so the agent knows how the match was made.
- FR-5.4 `get_order_fulfillment_evidence` never guesses. Absent data is `not_available`, never inferred.

### FR-6 Output safety
- FR-6.1 Pydantic **projection** models: expose only fields needed; normalize money (`amount`, `currency`), dates (ISO 8601), stock fields (name the Zoho field used).
- FR-6.2 Serialized tool output hard-capped (default 8 KB) with `truncated: true` and guidance to narrow the query.
- FR-6.3 PII masked by default (partial email and phone). `include_pii` defaults to false; opt-in documented and off in demos.
- AC: tests for cap enforcement, masking, and that raw Zoho payload fields not in the projection never leak.

### FR-7 Agent-facing errors
Every error returned by a tool says: what happened, whether to retry, and what to do instead. No stack traces, tokens, or URLs with secrets.
Example: *"Zoho daily API quota is exhausted for this organization. Do not retry today. Tell the user inventory data is temporarily unavailable; use cached data only if as_of is within the allowed window."*

### FR-8 Instrumentation
Structured JSON events (one per tool call) with **no PII, no tokens**: `ts`, `event`, `tool`, `status`, `latency_ms`, `cache_hit`, `throttled`, `retries`, `http_status`, `zoho_code`, `stock_status`, `result_count`, `truncated`, `request_id`. Schema documented in `docs/MEASUREMENT.md`. Eval harness computes metrics from these events, proving the same computation works on production logs.

### FR-9 Mock Zoho server (`mock_zoho/`)
FastAPI app emulating OAuth (auth, token, refresh, expiry, `invalid_grant`) and Inventory endpoints with **fictional** fixtures: 30 items (several out-of-stock, several low-stock, some multi-warehouse), 40 sales orders across statuses, packages/shipments with and without tracking, invoices. Pagination and filters behave like Zoho's documented shape. Fault injection via a control endpoint or env: 401 expired token, 429 with/without `Retry-After`, code 44, code 45, 5xx, slow responses. Fixture generation is seeded and deterministic (`seed=42`).

### FR-10 Evaluation harness (`eval/`)
- E1 Nudge policy comparison over 200 seeded abandoned-cart events:
  - Baseline: nudge + discount every cart.
  - Connector-aware: `get_stock_availability` first; `out_of_stock` suppress; `low_stock` send scarcity message with no discount; `in_stock` normal discount.
  - Report: nudges sent, nudges sent to unavailable SKUs, wasted discount (fictional INR), correctly nudged, API calls per decision, p50/p95 tool latency, cache hit rate, quota % used.
- E2 Dispute evidence over 40 seeded fictional disputes: complete / partial (with which fields missing) / none; API calls per case.
- Output: Markdown table to stdout and `eval/results/*.json`, every artifact labeled `SIMULATED`.
- `docs/MEASUREMENT.md` must include: what a real measurement needs (control group, window, event fields, confounders such as seasonality, restock timing, discount elasticity) and **explicit kill criteria** ("what would make me conclude this did NOT work").
- AC: `make eval` is deterministic; two runs produce byte-identical JSON.

### FR-11 Demo and live smoke
- `make demo`: starts the mock, runs the MCP server, and drives (1) cart-nudge decisions for an in-stock, a low-stock, and an out-of-stock SKU, (2) dispute evidence assembly, (3) a burst showing throttling/backoff with a metrics summary.
- `make live-smoke`: skipped unless `ZOHO_*` env vars are present; read-only endpoints only; never prints tokens or customer data.
- **Optional stretch (only after all gates are green):** `examples/agent_demo.py` using the Claude Agent SDK with this MCP server attached, answering the two scenarios. Reads `ANTHROPIC_API_KEY` from env, exits gracefully with a message if missing, never commits keys. Verify the SDK's current API from its docs before coding.

### FR-12 Documentation set
Short, specific, no filler. Each doc has an owner section below.

| File | Audience | Must contain |
|---|---|---|
| `README.md` | Everyone | Opens with the stated ask vs. real problem, metrics + baseline, headline simulated result, then quickstart (mock first, then live), then architecture |
| `docs/DESIGN.md` | Engineers | Mermaid architecture; decisions and trade-offs; "What I chose not to build and why"; "How I would extend this in production" tied to M1-M3 |
| `docs/API_NOTES.md` | Engineers | Verified Zoho facts, each with a doc URL; `UNVERIFIED` where not confirmable |
| `docs/TOOLS.md` | Agent builders | One example call/response per tool |
| `docs/AGENT_CAPABILITIES.md` | Agent builders and Razorpay | CAN / CANNOT table (see below) |
| `docs/MEASUREMENT.md` | Analysts | Metrics definitions, event schema, real-measurement design, kill criteria |
| `docs/MERCHANT_DISCOVERY.md` | FDE reviewer | 10-12 discovery questions, each with the hypothesis it tests, data to request, and "what answer would change the design"; day-by-day week-one plan; clearly labeled assumptions |
| `docs/MERCHANT_SUMMARY.md` | Merchant ops head | One page, plain language: what the agent sees, can never do, what data leaves Zoho, failure modes and handling, how we'd know it works, "what I need from you" |
| `docs/LIMITATIONS.md` | Everyone | Honest limits + production-grade fix for each |
| `docs/WALKTHROUGH.md` | Me | 3-minute narration outline: problem, assumptions, live demo, eval table, limits, next steps |
| `docs/ASSUMPTIONS.md` | Everyone | Every ambiguity and the decision taken |
| `docs/DONE_CHECKLIST.md` | Codex and me | Gate checklist with the command that proves each item |

`AGENT_CAPABILITIES.md` CAN/CANNOT must include at minimum. **Cannot:** write, adjust stock, create orders or refunds; guarantee real-time stock; produce evidence Zoho does not hold. **Depends on:** how the merchant records packages/tracking; whether the Razorpay order/payment ID is stored on the Zoho order; Zoho daily quota shared across all consumers of the org.

---

## 5. Non-functional requirements

- NFR-1 **Security:** no secrets in repo or history; `.env.example` only; redact `Authorization` and tokens in all logs; a test greps the repo for secret-like strings; fictional data only.
- NFR-2 **Determinism:** tests and eval use seeded data and an injectable clock; no network and no real sleeps in unit tests.
- NFR-3 **Reliability:** all upstream failure modes map to typed errors; no unhandled exceptions escape a tool.
- NFR-4 **Performance (mock):** tool p95 < 150 ms excluding injected delays; response size cap enforced.
- NFR-5 **Quality gates:** `ruff` clean; `mypy` (or pyright) clean on `src/`; core-module coverage >= 85%.
- NFR-6 **Portability:** Python 3.11+, macOS/Linux; one-command setup (`make setup`).
- NFR-7 **Readability:** boring code, docstrings explain *why*, no speculative abstractions.

---

## 6. Architecture and repo layout

```
.
├── AGENTS.md
├── README.md
├── Makefile                      # setup, test, lint, typecheck, mock-server, demo, eval, live-smoke, spec
├── pyproject.toml / requirements.lock
├── .env.example  .gitignore
├── src/zoho_inventory_connector/
│   ├── auth/        # oauth flow, loopback server, TokenManager
│   ├── client/      # ZohoClient (GET-only), typed errors
│   ├── ratelimit/   # token bucket, semaphore, backoff, circuit breaker, metrics
│   ├── cache/       # TTL cache
│   ├── models/      # pydantic projections
│   ├── services/    # stock availability, fulfillment evidence composition
│   ├── events/      # structured JSON event emitter
│   └── mcp_server/  # FastMCP tools, spec generation
├── mock_zoho/       # FastAPI mock + seeded fixtures + fault injection
├── eval/            # nudge policy sim, dispute evidence eval, results/
├── examples/        # agent_demo.py (optional stretch)
├── tests/           # unit, integration, e2e (names reference FR IDs)
└── docs/
```

Layering rule: `mcp_server` -> `services` -> `client` -> (`auth`, `ratelimit`, `cache`). No layer imports upward. `models` is shared. Only `client` talks HTTP.

---

## 7. Zoho facts to verify before coding (write results in `docs/API_NOTES.md`)

Do **not** trust memory. Read current docs; cite URL per fact; mark `UNVERIFIED` and make configurable if unreachable.

- India DC: `accounts.zoho.in`, API base `https://www.zohoapis.in/inventory/v1`. Confirm `api_domain` behavior in the token response.
- Auth-code params (`access_type=offline`, `prompt=consent`), token endpoint, refresh flow, access-token lifetime, limits on refresh-token and access-token generation.
- Header format `Zoho-oauthtoken <token>`; `organization_id` requirement (query param vs header).
- Exact **read-only scope names** for items, sales orders, packages/shipments, invoices, contacts, organizations. Request the minimum.
- Pagination (`page`, `per_page` max, `page_context.has_more_page`) and search/filter params per endpoint (items by name/SKU/status; sales orders by status, reference number, date range, customer).
- Item stock fields (e.g. stock on hand vs. available vs. actual available; per-warehouse breakdown) and which to treat as "sellable".
- Packages/shipments: where tracking number, carrier, shipped and delivered dates live.
- Limits seen in current docs: 100 req/min per org; daily caps per plan (free: 1,000/day); concurrency soft limit (~10); HTTP 429; error codes 44 (per-minute block), 45 (daily exceeded), 1070 (concurrency).

---

## 8. Error taxonomy

| Condition | Typed error | Retry? | Agent guidance |
|---|---|---|---|
| 401 expired token | (internal refresh, then `AuthError` if still failing) | once | "Authentication with Zoho failed; ask the user to reconnect." |
| 429 per-minute | `RateLimitError(per_minute)` | yes, backoff | "Rate limited; retrying shortly." |
| Code 45 daily | `QuotaExhaustedError` | **no** | "Daily quota exhausted; do not retry today." |
| Code 44 org block | `CircuitOpenError` | after cool-down | "Zoho temporarily blocked requests; try later." |
| Code 1070 concurrency | `RateLimitError(concurrency)` | yes, reduce parallelism | "Too many parallel calls; slowing down." |
| 404 | `NotFoundError` | no | "No such item/order; verify the ID." |
| 5xx / network | `UpstreamError` | bounded | "Zoho is unavailable; do not guess data." |

---

## 9. Privacy and security rules

- Default projection excludes phone, full email, addresses, and free-text notes. `include_pii` is opt-in and documented.
- Data that leaves Zoho is limited to the projection fields; document this in `MERCHANT_SUMMARY.md`.
- Logs and events: no tokens, no `Authorization`, no PII.
- Token file path from env, `0600`, gitignored; never printed.
- Fixture data is fictional and obviously so (e.g. names like "Test Customer 014").

---

## 10. Honesty rules (non-negotiable)

1. Never invent a merchant interview, customer quote, real uplift, or production metric.
2. Every evaluation output, table, and chart is labeled **SIMULATED**.
3. Say what is **UNVERIFIED** against live Zoho. Live-mode behavior is claimed only if `make live-smoke` was actually run.
4. Do not claim Razorpay-internal knowledge. Agent Studio's runtime is described only from public information.
5. If a requirement cannot be met, say so in `docs/LIMITATIONS.md` instead of faking it.

---

## 11. Workflow, planning, goals, and subagents

**Planning.** Start every non-trivial milestone with a short plan (use `/plan` for the initial project plan). Keep the plan in `docs/PLAN.md` and update it as milestones complete.

**Goals.** Long-running work runs under a `/goal` with *verifiable* completion criteria (see section 12). Do not declare the goal achieved on circumstantial evidence; run the commands in `docs/DONE_CHECKLIST.md` and paste the outputs' key lines into it.

**Subagents.** Delegate bounded, parallelizable work and keep the main thread on integration. If subagents are unavailable in this Codex version, do the same work sequentially in the main thread.

| Role | Scope | Read/write | Output |
|---|---|---|---|
| `docs-verifier` | Read Zoho API/OAuth docs; extract verified facts | read-only (web), writes `docs/API_NOTES.md` only | Cited facts, `UNVERIFIED` flags |
| `mock-builder` | `mock_zoho/` and fixtures, fault injection | writes `mock_zoho/`, `tests/fixtures` | Seeded deterministic mock |
| `test-writer` | Tests mapped to FR IDs | writes `tests/` only | Tests that fail first, then pass |
| `eval-analyst` | `eval/` harness and `MEASUREMENT.md` | writes `eval/`, `docs/MEASUREMENT.md` | Deterministic tables |
| `reviewer` | Adversarial review: security, FR coverage, honesty rules, hiring-manager read | **read-only** | Findings list with file:line |
| `docs-writer` | Merchant-facing docs, README opening, walkthrough | writes `docs/` and README | Plain-language docs |

Never run two agents that write the same files at once. The main thread owns `src/` integration and commits.

**Git.** Commit per milestone with a clear message. Never commit `.env`, tokens, or `eval/results` that contain anything but fictional data. Do not rewrite history.

**Autonomy.** Do not ask questions. Make the reasonable assumption, log it in `docs/ASSUMPTIONS.md`, continue. Stop only for a missing external credential and then continue in mock mode.

**Style.** Python 3.11, type hints, pydantic v2, `ruff` format/lint, small modules, no dead code, docstrings explain why.

---

## 12. Milestones and definition of done

| M | Deliverable | Gate (command) |
|---|---|---|
| M1 | Scaffold, Makefile, `API_NOTES.md`, `PLAN.md`, `ASSUMPTIONS.md` | `make lint` passes; `API_NOTES.md` has a URL per fact |
| M2 | Mock Zoho + fixtures + fault injection | `make mock-server` serves; tests for OAuth and pagination pass |
| M3 | Auth + TokenManager | FR-1 tests pass (single-flight, no token in logs) |
| M4 | Client + rate limiting + cache | FR-2/3/4 tests pass incl. burst and breaker tests |
| M5 | Models + services + MCP tools + spec | FR-5/6/7 tests pass; `make spec` is in sync |
| M6 | Instrumentation + eval harness | `make eval` deterministic; results labeled SIMULATED |
| M7 | Demo + live-smoke wiring | `make demo` runs end to end offline |
| M8 | Docs set (all of FR-12) | Reviewer subagent finds no honesty-rule violations |
| M9 | Adversarial review + fixes + final audit | `docs/DONE_CHECKLIST.md` fully ticked with evidence |
| M10 (optional) | Claude Agent SDK demo | Only if M1-M9 are green |

**Done =** all of: `make lint`, `make typecheck`, `make test` (coverage >= 85% core), `make eval` (byte-identical on rerun), `make demo` (offline), secrets scan clean, every FR-12 doc present and specific, README opens with the merchant problem, and the final report below is printed.

**Final report (print at the end):** what was built; how to run it (3 commands); test and eval results; what is unverified against live Zoho; top 3 limitations; what to ask a real merchant first.

---

## 13. Addendum (Applied Immediately)

Competitive context: another candidate shipped a clean read-only MCP server with live-API screenshots, MCP Inspector evidence, a seed script, a validated query builder, and PII masking. Our differentiators are the merchant framing, simulated evaluation, quota-aware design, and decision tools. We must also match the baseline of live proof and input hardening.

1. **VALIDATED QUERY BUILDER (FR-5.5):** Search tools must never pass agent-supplied text into Zoho query parameters unvalidated. Define per-field validators (allowed characters, max length, enums for status, ISO dates, numeric IDs). Reject anything else with a clear agent-readable error. Tests must include injection-style inputs (extra parameters, URL-encoded separators, quote and operator characters) and assert they are rejected or neutralized.
2. **LIVE EVIDENCE (FR-11.3):** `make live-smoke` must exercise every tool against a real Zoho org and write a REDACTED transcript to `docs/LIVE_RUN.md` (no tokens, no org IDs, no real personal data). Add `docs/INSPECTOR_DEMO.md` with exact steps to run the MCP Inspector against the server (`npx @modelcontextprotocol/inspector ...`) and a list of the screenshots I should capture (to be added manually under `docs/assets/`).
3. **SEED SCRIPT (Dev Tooling, NOT part of the connector):** `scripts/seed_zoho.py` creates about 10 fictional items (2 out of stock, 2 low stock) and 6-8 fictional sales orders (some with packages and tracking) in MY trial org so live tests have something to read. It requires separate write scopes and separate credentials from the connector, is never imported by `src/`, has a dry-run flag, refuses to run unless an explicit `--i-understand-this-writes` flag is passed, and uses obviously fake names. Update the read-only test to scan `src/` and the MCP server only, and document in `docs/DESIGN.md` why the seed script exists and why it is isolated.
4. **SCOPE PROTECTION:** If time is short, cut in this order: M10 demo, extra docs polish, extra evaluation detail. Never cut: the live smoke test, the README's merchant-problem opening, the honesty rules, the read-only guarantee, quota-aware rate limiting, or the tests for FR-1 to FR-7.
5. **ORIGINALITY:** Do not copy code or text from any other repository. Implement everything from the Zoho documentation and this PRD.
6. **FR-13 Input Safety:** Every tool input that feeds an upstream filter or query string must go through a validated query builder with explicit allowlists, length limits and escaping. The agent never passes raw query text. Add tests that try operator injection and quote-escaping and assert rejection.
7. **NFR-8 Stdio Hygiene:** The MCP stdio server must never write to stdout except protocol frames. All logging goes to stderr. Add a test that fails if any print() to stdout occurs on the server path.
8. **FR-14 Live-Trial Support:** Add `scripts/seed_zoho.py` that creates ~10 fictional items and ~8 fictional sales orders (with some out-of-stock, low-stock, packages with and without tracking) in a throwaway Zoho org, idempotently, using write scopes ONLY in this script and never in the connector. Document the extra scopes needed and that they are for seeding only. Add `make live-smoke` output that prints a masked, screenshot-friendly summary of each tool call.
9. **FR-15 Audit:** Add an audit event per tool call (tool, parameters with PII removed, timestamp, request_id) separate from application logs, in line with the instrumentation schema.
10. **NFR-9 Clean-Clone Check:** Add a `make clean-clone-test` target that clones the repo to a temp dir, follows the README quickstart exactly in mock mode, and fails on any placeholder like `<you>` or `<your-repo>` in the README.


