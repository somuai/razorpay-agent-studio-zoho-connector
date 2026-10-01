# Execution Plan: Zoho Inventory Connector for Razorpay Agent Studio

**Document Version:** 1.0.0  
**Status:** In Progress (M1 Active)  
**Target:** Milestones M1 through M9 (M10 Optional Stretch)  
**Standard:** Strict compliance with `AGENTS.md` PRD and Honesty Rules.

---

## 1. Executive Summary & Verification Sequencing

Before any client or business logic code is authored, critical upstream platform assumptions (Zoho Inventory API & OAuth mechanics) must be verified and cited in `docs/API_NOTES.md`.

### Order of Zoho Fact Verification:
1. **Authentication & DC Base URLs:** India Data Center endpoints (`https://accounts.zoho.in/oauth/v2/auth`, `https://accounts.zoho.in/oauth/v2/token`, `https://www.zohoapis.in/inventory/v1`), token lifetime (3600s), header format (`Authorization: Zoho-oauthtoken <token>`), and dynamic routing via `api_domain`.
2. **Minimal Read-Only Scopes:** Exact scope identifiers (`ZohoInventory.items.READ`, `ZohoInventory.salesorders.READ`, `ZohoInventory.packages.READ`, `ZohoInventory.shipmentorders.READ`, `ZohoInventory.invoices.READ`, `ZohoInventory.organizations.READ`).
3. **Item Stock Availability Semantics:** Distinction between `stock_on_hand` (physical), `available_stock` (unshipped), and `actual_available_stock` (sellable = accounting stock minus open/committed sales orders). For cart abandonment nudges, `actual_available_stock` is the determinative metric.
4. **Order & Dispute Evidence Paths:** Location of package tracking numbers, carrier details, shipment status, and delivery date across `/salesorders/{id}`, `/packages`, and `/shipmentorders`.
5. **Rate Limiting & Error Codes:** HTTP 429 semantics, Zoho error code 44 (per-minute block), code 45 (daily quota exceeded — no retry), and code 1070 (concurrency limit reached).

---

## 2. Milestone Roadmap (M1 – M10)

### Milestone M1: Scaffolding, Makefile, Environment & Core Documentation
- **Files to Create:**
  - `pyproject.toml`, `requirements.lock`
  - `Makefile` (targets: `setup`, `lint`, `typecheck`, `test`, `mock-server`, `spec`, `eval`, `demo`, `live-smoke`, `check-secrets`)
  - `.gitignore`, `.env.example`
  - `docs/API_NOTES.md`
  - `docs/PLAN.md`
  - `docs/ASSUMPTIONS.md`
  - `docs/DONE_CHECKLIST.md`
- **FR IDs Covered:** Scaffold foundational structure for FR-1 through FR-12; NFR-1, NFR-5, NFR-6.
- **Verification Command:** `make lint` passes; `docs/API_NOTES.md` contains valid citations and clear `UNVERIFIED` tags where necessary.
- **Subagent Delegation:** `docs-verifier` verifies docs/API facts; main thread handles build config and repo layout.
- **Main Risk:** Tooling configuration drift between uv/pip/ruff/mypy. Resolved by pinning exact compatible tool versions and paths.

---

### Milestone M2: Deterministic Mock Zoho Server & Seeded Fixtures
- **Files to Create:**
  - `mock_zoho/app.py`: FastAPI server emulating Zoho Inventory v1 and Zoho Accounts OAuth endpoints.
  - `mock_zoho/fixtures.py`: Deterministic data generator seeded with `seed=42` containing:
    - 30 items (in-stock, low-stock, out-of-stock, multi-warehouse).
    - 40 sales orders across statuses (`draft`, `confirmed`, `fulfilled`, `closed`, `void`).
    - Packages, shipments with/without tracking, invoices.
  - `mock_zoho/faults.py`: Configurable fault injection (401 expired token, 429 with/without `Retry-After`, code 44 block, code 45 quota exhausted, 500 internal error, simulated network delays).
  - `tests/test_mock_server.py`: Validates mock behavior, OAuth flow emulation, and pagination against Zoho specs.
- **FR IDs Covered:** FR-9, NFR-2, NFR-4.
- **Verification Command:** `make mock-server` serves; `pytest tests/test_mock_server.py` passes.
- **Subagent Delegation:** `mock-builder` implements fixture generators; main thread integrates FastAPI router.
- **Main Risk:** Divergence between mock response shapes and real Zoho API shapes. Resolved by exact fixture schema replication from verified API documentation.

---

### Milestone M3: Authentication & Token Management
- **Files to Create:**
  - `src/zoho_inventory_connector/auth/oauth.py`: OAuth authorization-code flow, loopback server for redirect (`http://localhost:8080/callback`), state verification for CSRF, headless refresh-token extraction.
  - `src/zoho_inventory_connector/auth/token_manager.py`: `TokenManager` with single-flight concurrency lock (`asyncio.Lock`), proactive refresh buffer (5 mins before expiry), disk persistence (`mode 0600`), and strict secret redaction.
  - `tests/test_auth.py`: 50 concurrent calls verify exactly 1 refresh call; tests ensuring token strings never appear in captured logs; auth URL state parameter checks.
- **FR IDs Covered:** FR-1 (FR-1.1 – FR-1.5), NFR-1.
- **Verification Command:** `pytest tests/test_auth.py` passes with zero secret leakage.
- **Main Risk:** Concurrency race conditions in single-flight token refresh under async loads. Resolved with robust `asyncio.Lock` and double-checked token expiry validation.

---

### Milestone M4: HTTP Client, Resilient Rate Limiting & Multi-Tier Cache
- **Files to Create:**
  - `src/zoho_inventory_connector/client/client.py`: Async `httpx` client strictly restricted to `GET` requests; automated header injection (`Authorization: Zoho-oauthtoken ...`, `organization_id`).
  - `src/zoho_inventory_connector/client/errors.py`: Typed error hierarchy (`AuthError`, `RateLimitError`, `NotFoundError`, `UpstreamError`, `QuotaExhaustedError`, `CircuitOpenError`).
  - `src/zoho_inventory_connector/ratelimit/token_bucket.py`: Leaky/token bucket rate limiter (80 req/min default), concurrency semaphore (default 5).
  - `src/zoho_inventory_connector/ratelimit/circuit_breaker.py`: Circuit breaker for error codes 44 and 1070 with configurable cooldown.
  - `src/zoho_inventory_connector/ratelimit/metrics.py`: Metrics tracking (calls made, throttled, retried, cache hits, estimated quota).
  - `src/zoho_inventory_connector/cache/ttl_cache.py`: In-memory TTL cache with fine-grained TTLs (items: 300s, stock: 60s), `as_of` metadata, and `bypass_cache` override.
  - `tests/test_client.py`, `tests/test_ratelimit.py`, `tests/test_cache.py`: Unit and burst tests with injectable virtual clock (no real sleeps).
- **FR IDs Covered:** FR-2, FR-3, FR-4, NFR-2, NFR-3.
- **Verification Command:** `pytest tests/test_client.py tests/test_ratelimit.py tests/test_cache.py` passes (asserting no non-GET calls, burst rate enforcement, zero retries on code 45).
- **Main Risk:** Flaky unit tests if real time sleeps are used. Resolved by implementing an injectable abstract clock interface `Clock` supporting simulated virtual advancement.

---

### Milestone M5: Pydantic Projections, Domain Services, FastMCP Server, Query Builder & Spec Generation
- **Files to Create:**
  - `src/zoho_inventory_connector/client/query_builder.py`: Validated query builder (FR-5.5, FR-13). Strict per-field validation (regex, length limits, enums for status, ISO dates, numeric IDs, escaping). Sanitizes or rejects injection-style inputs (quote operators, control chars, param tampering) with agent-readable error messages.
  - `src/zoho_inventory_connector/models/item.py`: Item projection, warehouse inventory breakdown, stock availability status enum (`in_stock`, `low_stock`, `out_of_stock`, `unknown`).
  - `src/zoho_inventory_connector/models/order.py`: Sales order projection, status normalization, payment match metadata (`match_basis`).
  - `src/zoho_inventory_connector/models/evidence.py`: Fulfillment evidence composition (`complete`, `partial`, `none`), missing fields enumeration.
  - `src/zoho_inventory_connector/services/stock_service.py`: Stock calculation logic against reorder levels and warehouse thresholds.
  - `src/zoho_inventory_connector/services/dispute_service.py`: Cross-object synthesis of orders, packages, shipments, tracking, and invoices.
  - `src/zoho_inventory_connector/mcp_server/server.py`: FastMCP server registering the 8 read-only tools with explicit descriptions, parameter bounds, output byte-capping (8 KB), and PII masking. Adheres strictly to NFR-8: never writes to stdout except protocol frames; all logs route to stderr.
  - `src/zoho_inventory_connector/mcp_server/spec.py`: Tool spec exporter writing to `mcp/tool_spec.json`.
  - `mcp/tool_spec.json`: Committed JSON schema of MCP tools.
  - `tests/test_query_builder.py`: Injection tests verifying parameter tampering, quotes, and malicious strings are rejected/neutralized (FR-13).
  - `tests/test_stdio_hygiene.py`: Verifies zero stdout pollution on the server path (NFR-8).
  - `tests/test_mcp_tools.py`, `tests/test_projections.py`, `tests/test_spec.py`: Verifies tool contracts, size caps, masking, and schema drift.
- **FR IDs Covered:** FR-5 (including FR-5.5, FR-13), FR-6, FR-7, NFR-8.
- **Verification Command:** `make spec` succeeds without git diff; `pytest tests/test_query_builder.py tests/test_stdio_hygiene.py tests/test_mcp_tools.py tests/test_projections.py tests/test_spec.py` passes.
- **Main Risk:** Oversized JSON responses exceeding LLM context windows or leaking sensitive customer PII. Resolved by hard capping response length (8 KB limit with `truncated: true`) and applying regex masking to emails/phones by default.

---

### Milestone M6: Structured Instrumentation, Audit Trail & Evaluation Harness
- **Files to Create:**
  - `src/zoho_inventory_connector/events/emitter.py`: Structured JSON logger emitting metrics (`ts`, `event`, `tool`, `status`, `latency_ms`, `cache_hit`, `throttled`, `retries`, `stock_status`, etc.) with zero PII (FR-8).
  - `src/zoho_inventory_connector/events/audit.py`: Audit log emitter recording one audit event per tool call (`tool`, sanitized parameters with PII removed, timestamp, `request_id`) separate from application logs (FR-15).
  - `eval/seed_data.py`: Seeded generator for 200 abandoned-cart events and 40 payment dispute cases (`seed=42`).
  - `eval/nudge_sim.py`: Simulation comparing baseline naive nudging vs. connector-aware stock-aware nudging (M1 metrics, discount budget saved).
  - `eval/dispute_eval.py`: Evaluation of dispute fulfillment evidence assembly across seeded disputes (M2 metrics, completeness rates).
  - `eval/run_eval.py`: Unified harness producing markdown tables and deterministic JSON output under `eval/results/`.
  - `eval/results/summary.json`: Committed evaluation output labeled `SIMULATED`.
  - `docs/MEASUREMENT.md`: Complete metrics definitions, event schema, audit schema, real-world measurement plan, and kill criteria.
- **FR IDs Covered:** FR-8, FR-10, FR-15.
- **Verification Command:** `make eval` generates deterministic results; consecutive runs produce byte-identical JSON; all outputs labeled `SIMULATED`.
- **Subagent Delegation:** `eval-analyst` builds the simulation scenarios and analytics formulas.
- **Main Risk:** Non-deterministic evaluation outcomes causing CI flakiness. Resolved by seeding random generators, freezing timestamps in synthetic data, and sorting JSON keys.

---

### Milestone M7: Offline Demo, Seed Script & Live-Smoke Evidence Harness
- **Files to Create:**
  - `examples/demo.py`: Executable demonstration script that boots mock server, initializes MCP client, and walks through:
    1. Cart-nudge decisions for in-stock, low-stock, and out-of-stock items.
    2. Dispute evidence compilation for complete and partial fulfillment cases.
    3. Throttling and circuit breaker demonstration under burst load.
  - `scripts/seed_zoho.py`: Isolated dev tooling to seed trial org with ~10 fictional items (2 out-of-stock, 2 low-stock) and ~8 fictional sales orders with tracking (FR-14). Requires separate write scopes, `--i-understand-this-writes` flag, never imported by `src/`.
  - `examples/live_smoke.py`: Safe, read-only live verification script activated only when `ZOHO_*` credentials are provided. Exercises every MCP tool against real Zoho instance, prints masked screenshot-friendly summaries (FR-14), and writes a REDACTED transcript to `docs/LIVE_RUN.md` (FR-11.3).
  - `docs/LIVE_RUN.md`: Sanitized live execution record.
  - `docs/INSPECTOR_DEMO.md`: Step-by-step instructions for running MCP Inspector (`npx @modelcontextprotocol/inspector ...`) with screenshot checklist for `docs/assets/`.
  - `tests/test_demo.py`: E2E integration test ensuring the demo runs cleanly in headless environments.
  - `tests/test_read_only_surface.py`: Asserts no non-GET calls anywhere in `src/` or `mcp_server`.
- **FR IDs Covered:** FR-11 (FR-11.1, FR-11.2, FR-11.3), FR-14, NFR-9.
- **Verification Command:** `make demo` runs end-to-end completely offline; `make clean-clone-test` succeeds.
- **Main Risk:** Process contention or port collision during background server execution. Resolved by selecting dynamic or isolated local ports and clean shutdown handlers.

---

### Milestone M8: Comprehensive Documentation Suite
- **Files to Create / Finalize:**
  - `README.md`: Framing merchant problem (P1, P2), metrics baseline, headline simulated results, quickstart guide, architecture overview.
  - `docs/DESIGN.md`: Architecture diagrams (Mermaid), key trade-offs, non-goals ("What I chose not to build and why"), production roadmap.
  - `docs/TOOLS.md`: Concrete example invocations and responses for all 8 MCP tools.
  - `docs/AGENT_CAPABILITIES.md`: Explicit CAN / CANNOT / DEPENDS ON matrices for LLM agent builders.
  - `docs/MERCHANT_DISCOVERY.md`: 10-12 deep-dive merchant discovery questions with underlying hypotheses, data requests, and design pivot triggers; week-one onboarding plan.
  - `docs/MERCHANT_SUMMARY.md`: 1-page plain-language ops brief explaining permissions, privacy boundaries, failure modes, and operational commitments.
  - `docs/LIMITATIONS.md`: Honest technical limitations paired with production remediation architectures.
  - `docs/WALKTHROUGH.md`: 3-minute executive video walkthrough script and narrative flow.
  - `docs/DONE_CHECKLIST.md`: Verification audit with exact reproduction commands and status checkboxes.
- **FR IDs Covered:** FR-12.
- **Verification Command:** Documentation completeness audit; verify compliance with Honesty Rules (no invented quotes or unsimulated metrics).
- **Subagent Delegation:** `docs-writer` assists in formatting user-facing summaries.
- **Main Risk:** Over-claiming agent autonomy or omitting critical boundary conditions. Resolved by strict adherence to Section 10 Honesty Rules.

---

### Milestone M9: Adversarial Review, Hardening & Final Gate Audit
- **Activities:**
  - Invoke `reviewer` subagent to conduct an adversarial code, security, and documentation audit:
    - Verify every FR acceptance criterion.
    - Check for secret leaks or PII exposures (`check-secrets` target).
    - Audit codebase to prove zero non-GET requests exist.
    - Verify all evaluation tables and doc summaries explicitly carry `SIMULATED` markers.
  - Fix any identified issues, ensure >= 85% core module test coverage, re-run full test suite and evaluations.
  - Populate `docs/DONE_CHECKLIST.md` with command execution proof.
- **Verification Command:** `make lint && make typecheck && make test && make eval && make demo` all succeed cleanly.

---

### Milestone M10 (Optional Stretch): Claude Agent SDK Demo
- **Files to Create:**
  - `examples/agent_demo.py`: Implementation using Anthropic's Claude Agent SDK attaching our FastMCP tools.
  - Handles missing `ANTHROPIC_API_KEY` gracefully without erroring or breaking default targets.
- **Verification Command:** `python -m examples.agent_demo --dry-run` or live if key present.

---

## 3. Ambiguities & Design Decisions

1. **Reorder Level Default (FR-5.2):** In Zoho Inventory, `reorder_level` is optional on items.  
   *Decision:* When `reorder_level` is null or zero, the connector defaults the `low_stock` threshold to 5 units, fully configurable via `DEFAULT_LOW_STOCK_THRESHOLD`.
2. **Sales Order Matching for Disputes (FR-5.3):** Razorpay payment IDs or order IDs are not standard native fields in Zoho Inventory.  
   *Decision:* The connector searches `reference_number` and standard custom fields for `razorpay_order_id` or `razorpay_payment_id`, returning `match_basis` (e.g. `reference_number_exact`, `custom_field_razorpay_order_id`) so the calling agent has transparency into the matching confidence.
3. **Fulfillment Status Hierarchy (FR-5.4):** A sales order might be marked `fulfilled` while carrier tracking is not yet generated.  
   *Decision:* `get_order_fulfillment_evidence` cross-references the sales order status, package status, and shipment order records. If tracking number or courier delivery date is missing, it is reported as `not_available` with `completeness: "partial"`, never guessed.
