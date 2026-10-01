# AGENTS.md — Zoho Inventory Connector for Razorpay Agent Studio (Technical PRD, v2)

> Codex reads this file at the start of every task. It is the product spec and the working agreement.
> This file may be visible to reviewers if the repo is public: keep it professional, and never put secrets in it.
> If a chat prompt conflicts with this file, ask nothing: follow this file, record the conflict in `docs/ASSUMPTIONS.md`, continue.

---

## 0. Mission and evaluation criteria

This repo is a take-home submission for a **Forward-Deployed Engineer, Agent Studio** role at Razorpay (Bangalore, on-site). That role is the technical owner of the merchant relationship: sit with the merchant, find the real problem behind the ask, design the fix, build the first working version, and prove whether it moved the metric. It is engineer, consultant and builder in one, and it is explicitly "not a demo or ticket-closing role."

**Assignment (Option 3):** Build a private connector for **Zoho Inventory** that lets an Agent Studio agent read inventory and orders. Required: a working OAuth or API-key flow, list/get/search primitives, rate-limit handling, an MCP tool specification (or equivalent), and a short document describing what the agent can and cannot do. Include setup/run instructions, assumptions and limitations. No real customer data, passwords, API keys or credentials.

**How the work will be judged (design to all five):**
1. **Complete** — every item above is present and works.
2. **Live-proven** — it runs against a real Zoho Inventory org, not only a mock. Evidence is captured. This is table stakes.
3. **Problem-led** — a specific merchant problem drives tool design; the README opens with the problem, not the stack.
4. **Measured honestly** — impact is quantified in simulation with explicit labels, plus a plan for real measurement and kill criteria.
5. **Merchant-ready writing** — a non-engineer ops head can read the merchant summary and understand what the agent sees and can never do.

Rule of thumb: never ship code without its doc, and never ship a claim without a command that reproduces it.

### What Agent Studio is (public information only)

Razorpay Agent Studio launched on 12 March 2026 (FTX 2026). Publicly it is a B2B agent marketplace and builder for payments and business banking: merchants deploy prebuilt agents with one click, or create their own from a natural-language prompt ("Build Your Agent"). It is built on Anthropic's Claude Agent SDK, and its agents work inside Razorpay on payments and post-payment operations. Launch agents include:
- **Abandoned Cart Conversion** — finds abandoned carts and re-engages customers by WhatsApp or email with nudges and offers.
- **Dispute Responder** — fetches dispute details, compiles evidence and prepares rebuttals.
- **Subscription Recovery** — retries failed recurring payments at better times.
- **Cashflow Forecaster**.
Razorpay has described an open ecosystem for developers and fintech partners; its launch announcement names Nugget by Zomato and SuperU as build partners for the cart agent. MediaNama raised questions about the *possibility* of price discrimination and dark patterns from personalized offers; that is a public concern, not evidence that any agent used aggressive or discriminatory discounts. Razorpay's public response says offers remain within merchant-configured coupon rules. This connector only supplies inventory facts and never chooses or sends offers. Sources: [Razorpay launch announcement](https://razorpay.com/newsroom/?p=4704), [Razorpay Agent Studio overview](https://razorpay.com/blog/agent-studio-ai-agents-by-razorpay/), [MediaNama coverage and Razorpay response](https://www.medianama.com/2026/03/223-razorpay-chief-product-officer-ai-agent-studio-pricing-compliance-concerns/).

**Where this connector sits.** Agents on these merchants' workflows are autonomous LLM agents (Claude-based). They need merchant data that lives outside Razorpay, such as stock and fulfillment records in Zoho Inventory. The connector is that bridge:

    Agent Studio agent (Claude)  ──MCP tool calls──▶  this MCP server  ──read-only, OAuth2──▶  Zoho Inventory
      Abandoned Cart Conversion → get_stock_availability
      Dispute Responder         → search_sales_orders, get_order_fulfillment_evidence

This connector serves the first two agents above.

**What is NOT public (treat as assumptions; log each in `docs/ASSUMPTIONS.md`).** How Agent Studio registers or loads a private connector; how it stores per-merchant credentials; whether it expects MCP specifically. The assignment asks for "an MCP tool specification or equivalent", so we assume an MCP-compatible tool interface and describe the integration shape only. Never claim Razorpay-internal knowledge or imply this was tested inside Agent Studio.

**Design consequences of the agent being the user.** Agents run unattended, so: tool descriptions are effectively prompts (be explicit about when to use and not use each tool); outputs are small and bounded; errors tell the agent how to recover; the connector is read-only so a misbehaving or prompt-injected agent cannot change a merchant's data; and in production credentials would be per merchant, which is out of scope here and documented as the long-term fix.

### FDE operating mindset (apply to every design decision)
- Start from the merchant's workflow and cost of being wrong, not from the API surface.
- Treat the agent as the user: tool descriptions, output size and error messages are product surface.
- Prefer a composed tool that answers a decision ("is this sellable?") over exposing raw endpoints.
- Say what you don't know. Mark assumptions. Show how you'd learn the truth from a real merchant.
- Ship the smallest thing that is real, then measure it.

---

## 1. Problem statement

**Fictional merchant:** *Kaveri Home Goods*, a D2C home-decor brand in Bangalore. Razorpay Checkout on its own site; Zoho Inventory for stock and sales orders. This merchant is fictional. Never imply a real interview or real customer data exists.

| # | Stated ask | Real problem (hypothesis to validate) | Agent affected |
|---|---|---|---|
| P1 | "Recover more abandoned carts." | Nudges and discounts go out for SKUs that are out of stock or nearly so. Discount budget is wasted and customers are disappointed. The agent has no stock awareness. | Abandoned Cart Conversion |
| P2 | "Win more chargebacks." | Rebuttals need fulfillment evidence (order, invoice, packed/shipped/delivered status and dates, tracking). Ops assembles it by hand across tools; it is slow and often incomplete. | Dispute Responder |

**Metrics (defined in `docs/MEASUREMENT.md`, computed in `eval/`):**
- **M1 Wasted nudges:** % of nudges sent for unavailable SKUs, and fictional-INR discount budget wasted.
- **M2 Dispute evidence completeness:** % of seeded disputes with complete evidence from one tool call; missing fields enumerated for partials.
- **M3 Agent cost:** API calls per decision/case and % of Zoho free-plan daily quota (1,000/day) consumed.

All evaluation outputs are **SIMULATED on fictional data** and must say so wherever shown.

---

## 2. Goals and non-goals

**Goals:** read-only Zoho connector with correct OAuth2 (India data center first); MCP server with agent-friendly tools; quota-aware limiting and caching; deterministic mock for offline testing; **live verification against a real Zoho org**; measurement harness and instrumentation; plain-language merchant and discovery docs.

**Non-goals (explain each in `docs/DESIGN.md` → "What I chose not to build and why"):** write tools in the connector; webhooks; multi-tenant OAuth; a UI; a database; a distributed limiter; real merchant/customer data; invented quotes or uplift; wiring into Razorpay's real Agent Studio runtime (describe the integration shape only).

---

## 3. Users and stories

- **Agent:** "Before I nudge for SKU X, is it sellable now?" "Give me everything needed to rebut the dispute on order SO-123 and tell me exactly what's missing."
- **Merchant ops head:** "Show me what the agent can see and never do. Tell me when data is stale or missing instead of guessing."
- **FDE (author):** "Prove the impact, state the limits, show what I'd ask the merchant next."

---

## 4. Functional requirements

IDs are referenced from tests (`# FR-3.4`) and docs. Acceptance criteria (AC) are binary.

### FR-1 Authentication (OAuth2)
- 1.1 Authorization-code flow with loopback redirect server; `state` for CSRF; PKCE if Zoho supports it; `access_type=offline`; minimal read-only scopes.
- 1.2 Headless path: refresh token from env or token file (Zoho Self Client) for CI and demos.
- 1.3 `TokenManager`: caches access token, refreshes before expiry, **single-flight** refresh (asyncio lock). Never mint a token per request.
- 1.4 Refresh token persisted to a gitignored file, mode `0600`, never logged. Optional OS keyring.
- 1.5 Data-center routing from the token response's `api_domain`; fallback `ZOHO_DC` (default `in`).
- AC: 50 concurrent calls with an expired token trigger exactly 1 refresh; token strings never appear in captured logs; auth URL contains `state`.

### FR-2 HTTP client
- 2.1 Async `httpx`; **GET-only** surface; injects `Authorization: Zoho-oauthtoken <token>` and `organization_id`.
- 2.2 Typed errors: `AuthError`, `RateLimitError(kind, retry_after)`, `NotFoundError`, `UpstreamError`, `QuotaExhaustedError`, `CircuitOpenError`.
- 2.3 On 401: refresh once, retry once, else `AuthError`.
- 2.4 Timeouts; bounded retries for 5xx/network on idempotent GETs.
- AC: a test fails CI if any code path in `src/` issues a non-GET request.

### FR-3 Rate limiting
- 3.1 Client-side token bucket, default 80 req/min (under Zoho's 100/min/org), configurable.
- 3.2 Concurrency semaphore, default 5 (Zoho soft limit ≈ 10).
- 3.3 HTTP 429: honor `Retry-After` (capped), else exponential backoff with full jitter, bounded attempts.
- 3.4 Daily quota exceeded (Zoho code 45): **no retry**; raise `QuotaExhaustedError` with an agent-readable message.
- 3.5 Org block (code 44) or concurrency error (1070): circuit breaker with cool-down; fail fast with `CircuitOpenError`.
- 3.6 Metrics: calls made, throttled, retried, cache hits, quota estimate.
- AC: 300-call burst against the mock never exceeds the per-minute budget; code 45 triggers zero retries; breaker opens on code 44 and recovers after cool-down (injectable clock, no real sleeps in unit tests).

### FR-4 Cache
- 4.1 In-process TTL cache; stock availability TTL default 60 s; all TTLs configurable and documented; `bypass_cache` on stock tools.
- 4.2 Every stock response carries `as_of` (ISO timestamp) and `cached`.
- AC: repeated stock check within TTL makes 0 extra upstream calls; `as_of` always present.

### FR-5 MCP server and tools
FastMCP; stdio default, streamable HTTP optional. **Read-only.** Descriptions state when to use and when not to use each tool. Inputs have JSON-schema bounds.

| Tool | Purpose | Key inputs | Key outputs |
|---|---|---|---|
| `list_items` | Browse catalog | `page`, `per_page<=50`, `status`, `fields?` | items[], `has_more`, `next_page`, `truncated` |
| `get_item` | One item | `item_id` | item projection |
| `search_items` | Find by name/SKU | `query`, `sku?`, `only_low_stock?`, `limit<=25` | items[], `truncated` |
| `get_stock_availability` | **Cart-nudge decision primitive** | `skus_or_ids[]<=20` | per-SKU `status` (`in_stock`/`low_stock`/`out_of_stock`/`unknown`), `quantity`, `warehouses[]`, `as_of`, `cached` |
| `list_sales_orders` | Browse orders | `status?`, `customer_id?`, `date_from?`, `date_to?`, `page` | orders[], paging |
| `get_sales_order` | One order | `salesorder_id` | order projection |
| `search_sales_orders` | Match a payment to an order | `reference_number?` or `customer_email?` or `razorpay_order_id?` | orders[], `match_basis` |
| `get_order_fulfillment_evidence` | **Dispute-evidence primitive** | `salesorder_id` | per-field `present`/`not_available`, `completeness` (`complete`/`partial`/`none`), `missing[]` |

- 5.1 `mcp/tool_spec.json` generated from the server; a test fails on drift.
- 5.2 `low_stock` derives from the item's reorder level if present, else a configurable default; documented.
- 5.3 `razorpay_order_id` matching relies on the merchant storing it in `reference_number` or a custom field. Document as an assumption; always return `match_basis`.
- 5.4 Evidence never guesses: absent data is `not_available`, never inferred.

### FR-6 Output safety
- 6.1 Pydantic **projection** models expose only needed fields; normalize money (`amount`, `currency`), dates (ISO 8601), stock (name the Zoho field used).
- 6.2 Serialized output hard-capped (default 8 KB) with `truncated: true` and guidance to narrow the query.
- 6.3 PII masked by default (partial email/phone); `include_pii` defaults false and is off in demos.
- AC: tests for cap, masking, and that raw Zoho fields outside the projection never leak.

### FR-7 Agent-facing errors
Every tool error says what happened, whether to retry, and what to do instead. No stack traces, tokens, or secret-bearing URLs.
Example: *"Zoho daily API quota is exhausted for this organization. Do not retry today. Tell the user inventory data is temporarily unavailable; use cached data only if as_of is within the allowed window."*

### FR-8 Instrumentation
One structured JSON event per tool call, **no PII, no tokens**: `ts`, `event`, `tool`, `status`, `latency_ms`, `cache_hit`, `throttled`, `retries`, `http_status`, `zoho_code`, `stock_status`, `result_count`, `truncated`, `request_id`. Schema in `docs/MEASUREMENT.md`. The eval harness computes metrics from these events, showing the same computation works on production logs.

### FR-9 Mock Zoho server (`mock_zoho/`)
FastAPI emulation of OAuth (auth, token, refresh, expiry, `invalid_grant`) and Inventory endpoints. **Fictional** seeded fixtures (`seed=42`): 30 items (several out-of-stock, several low-stock, some multi-warehouse), 40 sales orders across statuses, packages/shipments with and without tracking, invoices. Zoho-shaped pagination and filters. Fault injection: 401 expired token, 429 with/without `Retry-After`, code 44, code 45, 5xx, slow responses.

### FR-10 Evaluation harness (`eval/`)
- E1 Nudge policy over 200 seeded abandoned-cart events. Baseline: nudge + discount every cart. Connector-aware: `get_stock_availability` first; `out_of_stock` suppress; `low_stock` scarcity message, no discount; `in_stock` normal discount. Report: nudges sent, nudges to unavailable SKUs, wasted discount (fictional INR), correctly nudged, API calls per decision, p50/p95 tool latency, cache hit rate, quota % used.
- E2 Dispute evidence over 40 seeded disputes: complete / partial (which fields missing) / none; API calls per case.
- Output: Markdown table to stdout and `eval/results/*.json`, every artifact labeled `SIMULATED`.
- `docs/MEASUREMENT.md` must include: what real measurement needs (control group, time window, event fields, confounders: seasonality, restock timing, discount elasticity) and explicit **kill criteria** ("what would make me conclude this did NOT work").
- AC: `make eval` is deterministic; two runs produce byte-identical JSON.

### FR-11 Demo, live proof and inspector path
- 11.1 `make demo`: starts the mock and MCP server and drives (1) nudge decisions for an in-stock, low-stock and out-of-stock SKU, (2) dispute evidence assembly, (3) a burst showing throttling/backoff with a metrics summary. Fully offline.
- 11.2 `make live-smoke`: skipped unless `ZOHO_*` env vars exist; read-only calls only; prints a **masked, screenshot-friendly** summary per tool; never prints tokens or customer data.
- 11.3 `docs/INSPECTOR_DEMO.md`: exact steps to explore the server with the MCP Inspector (no LLM needed) in mock mode and live mode.
- 11.4 `docs/assets/`: placeholder README section "Live verification" with a slot for the author's screenshots; Codex must not fabricate screenshots or claim live verification. The claim is added only after the author confirms a real run.
- 11.5 **Optional (last):** `examples/agent_demo.py` using a free-tier Gemini model through the Google Gen AI SDK with this MCP server attached. Verify the SDK's current API from its docs first. Read `GEMINI_API_KEY` from env, exit gracefully if missing, keep out of default make targets, cap model calls, back off on 429. README states Agent Studio is built on Claude's Agent SDK and this demo only shows the server is model-agnostic.

### FR-12 Documentation set
Short, specific, no filler.

| File | Audience | Must contain |
|---|---|---|
| `README.md` | Everyone | **First screen:** stated ask vs. real problem, the three metrics, the headline simulated result, live-verification status. Then quickstart (mock first, then live), then architecture. |
| `docs/DESIGN.md` | Engineers | Mermaid architecture; decisions and trade-offs; "What I chose not to build and why"; "How I would extend this in production" tied to M1–M3 |
| `docs/API_NOTES.md` | Engineers | Verified Zoho facts, each with a doc URL; `UNVERIFIED` where not confirmable |
| `docs/TOOLS.md` | Agent builders | One example call/response per tool |
| `docs/AGENT_CAPABILITIES.md` | Agent builders, Razorpay | CAN / CANNOT / DEPENDS-ON table |
| `docs/MEASUREMENT.md` | Analysts | Metric definitions, event schema, real-measurement design, kill criteria |
| `docs/MERCHANT_DISCOVERY.md` | FDE reviewer | 10–12 discovery questions, each with the hypothesis tested, data to request, and "what answer would change the design"; day-by-day week-one plan; assumptions clearly labeled |
| `docs/MERCHANT_SUMMARY.md` | Merchant ops head | One page, plain language: what the agent sees, can never do, what data leaves Zoho, failure modes and handling, how we'd know it works, "what I need from you" |
| `docs/LIMITATIONS.md` | Everyone | Honest limits, each with a production-grade fix |
| `docs/WALKTHROUGH.md` | Author | 3-minute narration outline: problem → assumptions → live demo → eval table → limits → next steps |
| `docs/INSPECTOR_DEMO.md` | Anyone | Inspector steps |
| `docs/ASSUMPTIONS.md` | Everyone | Every ambiguity and the decision taken |
| `docs/DONE_CHECKLIST.md` | Codex, author | Gates, each with the command and pasted evidence |

`AGENT_CAPABILITIES.md` minimum. **Cannot:** write, adjust stock, create orders or refunds; guarantee real-time stock; produce evidence Zoho doesn't hold. **Depends on:** how the merchant records packages/tracking; whether the Razorpay order/payment ID is stored on the Zoho order; Zoho's daily quota being shared across all consumers of the org.

### FR-13 Input safety
Every tool input that feeds an upstream filter or query string goes through a validated builder with explicit allowlists, length limits and escaping. The agent never passes raw query text. Tests attempt operator injection and quote-escaping and assert rejection.

### FR-14 Live-trial seeding (isolated from the connector)
`scripts/seed_zoho.py` idempotently creates ~10 fictional items and ~8 fictional sales orders (some out-of-stock, low-stock, with packages with and without tracking) in a **throwaway** Zoho org. It is the **only** place write scopes are used; it uses a separate token file and separate documented scopes; it is never imported by `src/`. The no-non-GET test covers `src/` only and must pass.

### FR-15 Audit events
Per tool call: tool, parameters with PII removed, timestamp, `request_id`, written to a separate audit stream from application logs.

---

## 5. Non-functional requirements

- NFR-1 **Security:** no secrets in repo or history; `.env.example` only; redact `Authorization`/tokens in logs; a test greps the repo for secret-like strings; fictional data only.
- NFR-2 **Determinism:** seeded data and injectable clock; no network and no real sleeps in unit tests.
- NFR-3 **Reliability:** all upstream failures map to typed errors; no unhandled exception escapes a tool.
- NFR-4 **Performance (mock):** tool p95 < 150 ms excluding injected delays; output cap enforced.
- NFR-5 **Quality gates:** `ruff` clean; `mypy` or `pyright` clean on `src/`; core coverage ≥ 85%.
- NFR-6 **Portability:** Python 3.11+, macOS/Linux; `make setup` is one command.
- NFR-7 **Readability:** boring code; docstrings explain why; no speculative abstractions.
- NFR-8 **Stdio hygiene:** the stdio MCP server writes only protocol frames to stdout; all logs go to stderr. A test fails on any stdout `print()` in the server path.
- NFR-9 **Clean-clone check:** `make clean-clone-test` clones the repo into a temp dir, follows the README quickstart in mock mode, and fails on placeholders such as `<you>` or `<your-repo>`.

---

## 6. Architecture and layout

```
.
├── AGENTS.md  README.md  Makefile  pyproject.toml  requirements.lock  .env.example  .gitignore
├── src/zoho_inventory_connector/
│   ├── auth/        # oauth flow, loopback server, TokenManager
│   ├── client/      # ZohoClient (GET-only), typed errors, query builder
│   ├── ratelimit/   # token bucket, semaphore, backoff, circuit breaker, metrics
│   ├── cache/       # TTL cache
│   ├── models/      # pydantic projections
│   ├── services/    # stock availability, fulfillment evidence composition
│   ├── events/      # JSON event + audit emitters
│   └── mcp_server/  # FastMCP tools, spec generation
├── mock_zoho/       # FastAPI mock, seeded fixtures, fault injection
├── eval/            # nudge sim, dispute eval, results/
├── scripts/         # seed_zoho.py (write scopes, isolated), live helpers
├── examples/        # agent_demo.py (optional)
├── tests/           # names reference FR IDs
└── docs/            # incl. assets/ for author screenshots
```

Layering: `mcp_server` → `services` → `client` → (`auth`, `ratelimit`, `cache`). No upward imports. Only `client` and `auth` touch HTTP. `scripts/` is never imported by `src/`.

Makefile targets: `setup`, `lint`, `typecheck`, `test`, `mock-server`, `demo`, `eval`, `spec`, `live-smoke`, `zoho-token`, `clean-clone-test`.

---

## 7. Zoho facts to verify before coding (record in `docs/API_NOTES.md`)

Do **not** trust memory. Read current docs, cite a URL per fact, mark `UNVERIFIED` and make it configurable if unreachable.

- India DC: `accounts.zoho.in`; API base `https://www.zohoapis.in/inventory/v1`; `api_domain` in the token response.
- Auth-code params, token endpoint, refresh flow, access-token lifetime, limits on refresh-token and access-token generation.
- Header `Zoho-oauthtoken <token>`; `organization_id` requirement (query param vs header).
- Exact **read-only scope names** for items, sales orders, packages/shipments, invoices, contacts, organizations; and the separate write scopes needed only by the seeding script.
- Pagination (`page`, `per_page` max, `page_context.has_more_page`); search/filter params per endpoint.
- Item stock fields (stock on hand vs. available vs. actual available; per-warehouse) and which counts as "sellable".
- Packages/shipments: where tracking number, carrier, shipped and delivered dates live.
- Limits (as seen in current docs, re-verify): 100 req/min per org; daily caps by plan (free: 1,000/day); concurrency soft limit ≈ 10; HTTP 429; codes 44 (per-minute block), 45 (daily exceeded), 1070 (concurrency).
- Whether Zoho's free plan or only a trial is available for a throwaway org.

---

## 8. Error taxonomy

| Condition | Typed error | Retry? | Agent guidance |
|---|---|---|---|
| 401 expired | refresh, then `AuthError` | once | "Authentication with Zoho failed; ask the user to reconnect." |
| 429 per-minute | `RateLimitError(per_minute)` | yes, backoff | "Rate limited; retrying shortly." |
| Code 45 daily | `QuotaExhaustedError` | **no** | "Daily quota exhausted; do not retry today." |
| Code 44 org block | `CircuitOpenError` | after cool-down | "Zoho temporarily blocked requests; try later." |
| Code 1070 concurrency | `RateLimitError(concurrency)` | yes, lower parallelism | "Too many parallel calls; slowing down." |
| 404 | `NotFoundError` | no | "No such item/order; verify the ID." |
| 5xx / network | `UpstreamError` | bounded | "Zoho is unavailable; do not guess data." |

---

## 9. Privacy and security

- Default projection excludes phone, full email, addresses, free-text notes. `include_pii` is opt-in and documented.
- Data leaving Zoho is limited to the projection fields; state this in `MERCHANT_SUMMARY.md`.
- Logs and events carry no tokens, no `Authorization`, no PII.
- Token file path from env, `0600`, gitignored, never printed.
- Fixtures are obviously fictional ("Test Customer 014").

---

## 10. Honesty rules (non-negotiable)

1. Never invent a merchant interview, customer quote, real uplift, or production metric.
2. Every evaluation output, table and chart is labeled **SIMULATED**.
3. Claim **live verification only after the author confirms a real `make live-smoke` run.** Until then the README says "Live mode: not yet verified."
4. Never fabricate screenshots, logs or terminal output.
5. Do not claim Razorpay-internal knowledge; describe Agent Studio only from public information.
6. If a requirement can't be met, say so in `docs/LIMITATIONS.md`.

---

## 11. Workflow: planning, goals, subagents

**Planning.** Use `/plan` for the initial project plan; persist it to `docs/PLAN.md`; update as milestones complete.

**Goals.** Long-running work runs under `/goal` with verifiable completion criteria (section 12). Do not declare done on circumstantial evidence: run the commands in `docs/DONE_CHECKLIST.md` and paste key output lines into it.

**Subagents** (if unavailable, do the same work sequentially). Keep the main thread on integration; delegate bounded, non-overlapping work.

| Role | Scope | Access | Output |
|---|---|---|---|
| `docs-verifier` | Read Zoho API/OAuth docs; extract verified facts | read-only (web); writes `docs/API_NOTES.md` only | Cited facts, `UNVERIFIED` flags |
| `mock-builder` | `mock_zoho/` and fixtures, fault injection | writes `mock_zoho/`, `tests/fixtures` | Seeded deterministic mock |
| `test-writer` | Tests mapped to FR IDs | writes `tests/` only | Failing-first tests |
| `eval-analyst` | `eval/`, `docs/MEASUREMENT.md` | writes those only | Deterministic tables |
| `reviewer` | Adversarial review: security, FR coverage, honesty rules, hiring-manager read | **read-only** | Findings with file:line |
| `docs-writer` | Merchant-facing docs, README opening, walkthrough | writes `docs/`, `README.md` | Plain-language docs |

Never run two agents writing the same files at once. The main thread owns `src/` integration and commits.

**Git.** Commit per milestone with clear messages. Never commit `.env`, tokens, or real data. Don't rewrite history.

**Autonomy.** Don't ask questions: assume, log in `docs/ASSUMPTIONS.md`, continue. Stop only for a missing external credential; then continue in mock mode.

**Style.** Python 3.11, type hints, pydantic v2, `ruff`, small modules, no dead code.

---

## 12. Milestones, time budget and definition of done

Time budget (wall-clock target ≈ 8–10 h of mostly unattended runtime; the author needs the final 2 h for live proof, recording and the form).

| M | Deliverable | Gate |
|---|---|---|
| M1 | Scaffold, Makefile, `API_NOTES.md`, `PLAN.md`, `ASSUMPTIONS.md` | `make lint`; every API fact has a URL or `UNVERIFIED` |
| M2 | Mock Zoho + fixtures + fault injection | mock serves; OAuth and pagination tests pass |
| M3 | Auth + TokenManager | FR-1 tests pass |
| M4 | Client + query builder + rate limiting + cache | FR-2/3/4/13 tests pass incl. burst and breaker |
| M5 | **Live-proof readiness:** `zoho-token` helper, `seed_zoho.py`, `live-smoke`, Inspector doc | scripts run in mock mode; skip cleanly without creds. **Author runs live now (human gate); Codex does not block on it.** |
| M6 | Models, services, MCP tools, spec, stdio hygiene | FR-5/6/7 + NFR-8 tests pass; `make spec` in sync |
| M7 | Instrumentation, audit, eval harness | `make eval` deterministic, labeled SIMULATED |
| M8 | Demo (offline) | `make demo` runs end to end |
| M9 | Docs set (FR-12) + clean-clone test | `make clean-clone-test` passes; README first screen meets FR-12 |
| M10 | Adversarial review → fixes → final audit | `docs/DONE_CHECKLIST.md` fully ticked with evidence |
| M11 (optional) | Gemini agent demo | only if M1–M10 are green |

**Cut order if time runs short (cut first → last):** M11, `streamable HTTP` transport, extra edge-case tests beyond the gates, `list_sales_orders` filters, mermaid polish. **Never cut:** OAuth, rate limiting, the two decision tools, eval harness, merchant summary, README first screen, honesty rules, live-smoke readiness.

**Done =** `make lint`, `make typecheck`, `make test` (core coverage ≥ 85%), `make eval` byte-identical on rerun, `make demo` offline, `make clean-clone-test`, secrets scan clean, all FR-12 docs present and specific, README first screen compliant, honesty rules respected, and the final report printed.

**Final report (print at the end):** what was built; how to run it in three commands; test and eval results; what is unverified against live Zoho; top 3 limitations; what to ask a real merchant first.
