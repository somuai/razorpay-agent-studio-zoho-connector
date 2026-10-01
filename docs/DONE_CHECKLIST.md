# Definition of Done & Verification Checklist

**Standard:** Every box must be checked ONLY after the verifying command is executed. Pasted output / evidence must be recorded directly below each item.

---

## 1. Quality Gates & Non-Functional Requirements

- [ ] **Linter Quality Gate (`make lint`)**
  - *Command:* `make lint`
  - *Evidence:*
    ```
    (Pending execution)
    ```

- [ ] **Type Checker Quality Gate (`make typecheck`)**
  - *Command:* `make typecheck`
  - *Evidence:*
    ```
    (Pending execution)
    ```

- [ ] **Test Suite & Coverage Gate (`make test`)**
  - *Requirement:* All tests pass, core coverage >= 85%.
  - *Command:* `make test`
  - *Evidence:*
    ```
    (Pending execution)
    ```

- [ ] **Secrets & Privacy Audit (`make check-secrets`)**
  - *Requirement:* No committed tokens, secrets, or raw auth headers across codebase.
  - *Command:* `make check-secrets`
  - *Evidence:*
    ```
    (Pending execution)
    ```

- [ ] **Deterministic Evaluation Gate (`make eval` byte-identical check)**
  - *Requirement:* Run `make eval` twice, diff output JSON files; byte-identical match; all artifacts labeled `SIMULATED`.
  - *Command:* `make eval && cp eval/results/summary.json /tmp/run1.json && make eval && diff -u /tmp/run1.json eval/results/summary.json`
  - *Evidence:*
    ```
    (Pending execution)
    ```

- [ ] **Offline End-to-End Demo Gate (`make demo`)**
  - *Requirement:* Boots mock server, executes cart-nudge decision scenarios, dispute evidence assembly, and throttling burst with metrics summary.
  - *Command:* `make demo`
  - *Evidence:*
    ```
    (Pending execution)
    ```

- [ ] **MCP Specification Sync (`make spec`)**
  - *Requirement:* Tool schema generated from FastMCP server matches committed `mcp/tool_spec.json`.
  - *Command:* `make spec`
  - *Evidence:*
    ```
    (Pending execution)
    ```

---

## 2. Functional Requirements Traceability Matrix

| FR ID | Description | Acceptance Criteria Verification Command | Status |
|---|---|---|---|
| **FR-1.1** | Authorization-code flow with loopback redirect | `pytest tests/test_auth.py -k test_loopback_flow` | Pending |
| **FR-1.2** | Headless refresh token flow (Self-Client) | `pytest tests/test_auth.py -k test_headless_token_flow` | Pending |
| **FR-1.3** | Single-flight TokenManager refresh (asyncio lock) | `pytest tests/test_auth.py -k test_single_flight_refresh` | Pending |
| **FR-1.4** | Refresh token file persistence (0600 mode) | `pytest tests/test_auth.py -k test_token_file_permissions` | Pending |
| **FR-1.5** | Dynamic data-center routing (`api_domain`) | `pytest tests/test_auth.py -k test_api_domain_routing` | Pending |
| **FR-2.1** | Async httpx client with GET-only surface | `pytest tests/test_client.py -k test_strictly_get_only` | Pending |
| **FR-2.2** | Typed upstream error hierarchy | `pytest tests/test_client.py -k test_typed_errors` | Pending |
| **FR-2.3** | On 401: Refresh once, retry once, else AuthError | `pytest tests/test_client.py -k test_401_single_refresh_retry` | Pending |
| **FR-2.4** | Bounded retries for 5xx/network errors | `pytest tests/test_client.py -k test_bounded_5xx_retries` | Pending |
| **FR-3.1** | Client token bucket (80 req/min default) | `pytest tests/test_ratelimit.py -k test_token_bucket_limits` | Pending |
| **FR-3.2** | Concurrency semaphore (5 default) | `pytest tests/test_ratelimit.py -k test_concurrency_semaphore` | Pending |
| **FR-3.3** | HTTP 429 Retry-After & exponential backoff | `pytest tests/test_ratelimit.py -k test_429_backoff` | Pending |
| **FR-3.4** | Code 45 (daily quota exceeded) zero-retry | `pytest tests/test_ratelimit.py -k test_code_45_zero_retry` | Pending |
| **FR-3.5** | Circuit breaker on Code 44 / 1070 | `pytest tests/test_ratelimit.py -k test_circuit_breaker` | Pending |
| **FR-3.6** | Rate limit metrics collection | `pytest tests/test_ratelimit.py -k test_metrics_collection` | Pending |
| **FR-4.1** | In-process TTL cache (stock 60s, items 300s) | `pytest tests/test_cache.py -k test_cache_ttl` | Pending |
| **FR-4.2** | Cache staleness exposure (`as_of`, `cached`) | `pytest tests/test_cache.py -k test_cache_metadata` | Pending |
| **FR-5.1** | FastMCP server & `mcp/tool_spec.json` sync | `make spec` | Pending |
| **FR-5.2** | Reorder level stock status derivation | `pytest tests/test_services.py -k test_stock_availability` | Pending |
| **FR-5.3** | Sales order matching by reference / custom ID | `pytest tests/test_services.py -k test_search_orders_matching` | Pending |
| **FR-5.4** | Dispute evidence composition without guessing | `pytest tests/test_services.py -k test_fulfillment_evidence` | Pending |
| **FR-5.5 / FR-13** | Validated Query Builder & input injection protection | `pytest tests/test_query_builder.py` | Pending |
| **FR-6.1** | Pydantic projection models & normalization | `pytest tests/test_projections.py -k test_normalization` | Pending |
| **FR-6.2** | Response size hard-capping (8 KB limit) | `pytest tests/test_mcp_tools.py -k test_output_capping` | Pending |
| **FR-6.3** | PII masking by default (emails & phones) | `pytest tests/test_projections.py -k test_pii_masking` | Pending |
| **FR-7** | Self-explaining agent errors | `pytest tests/test_mcp_tools.py -k test_agent_error_messages` | Pending |
| **FR-8** | Structured JSON events emission | `pytest tests/test_events.py -k test_structured_events` | Pending |
| **FR-9** | Deterministic mock Zoho server & fixtures | `pytest tests/test_mock_server.py` | Pending |
| **FR-10** | Deterministic simulation eval (E1 & E2) | `make eval` | Pending |
| **FR-11.1** | End-to-end offline demo | `make demo` | Pending |
| **FR-11.2** | Live smoke test harness (safe read-only) | `make live-smoke` (or skipped cleanly if no creds) | Pending |
| **FR-11.3** | Redacted live run transcript & Inspector guide | Check `docs/LIVE_RUN.md` & `docs/INSPECTOR_DEMO.md` | Pending |
| **FR-12** | Complete documentation set | Inspection audit | Pending |
| **FR-14** | Live-trial support seed script (`scripts/seed_zoho.py`) | `python scripts/seed_zoho.py --dry-run` | Pending |
| **FR-15** | Separate audit event per tool call (PII-free) | `pytest tests/test_audit.py` | Pending |
| **NFR-8** | Stdio hygiene (zero stdout pollution on server path) | `pytest tests/test_stdio_hygiene.py` | Pending |
| **NFR-9** | Clean-clone check in temporary directory | `make clean-clone-test` | Pending |

---

## 3. Documentation Set Verification (FR-12)

- [ ] `README.md` (Opens with real merchant problem, metrics baseline, simulated results, quickstart, architecture)
- [ ] `docs/DESIGN.md` (Mermaid diagrams, decisions, what was not built and why, seed script isolation, production path)
- [ ] `docs/API_NOTES.md` (Verified facts with citations, UNVERIFIED flags)
- [ ] `docs/TOOLS.md` (One example call and response per MCP tool)
- [ ] `docs/AGENT_CAPABILITIES.md` (CAN / CANNOT / DEPENDS ON matrix)
- [ ] `docs/MEASUREMENT.md` (Metrics definitions, event schema, real measurement design, kill criteria)
- [ ] `docs/MERCHANT_DISCOVERY.md` (10-12 discovery questions with hypotheses, data requests, pivot triggers, week-1 plan)
- [ ] `docs/MERCHANT_SUMMARY.md` (1-page ops head brief, permissions, privacy, failure handling)
- [ ] `docs/LIMITATIONS.md` (Honest limitations with production remediations)
- [ ] `docs/WALKTHROUGH.md` (3-minute video walkthrough narrative outline)
- [ ] `docs/ASSUMPTIONS.md` (Ambiguity and decision log)
- [ ] `docs/PLAN.md` (Milestone roadmap and risks)
- [ ] `docs/LIVE_RUN.md` (Redacted live execution transcript)
- [ ] `docs/INSPECTOR_DEMO.md` (MCP Inspector guide & screenshot checklist)


