# Design and trade-offs

## Workflow before endpoints

Kaveri Home Goods is a fictional example, not an interviewed merchant. The design hypothesis is that stock-blind cart recovery can waste discounts and that dispute operations may have to gather order, invoice, package, and shipment facts from separate records. The two composed primitives are `get_stock_availability` and `get_order_fulfillment_evidence`; raw list/get/search tools support discovery and reconciliation around them.

```mermaid
flowchart LR
  A[Agent Studio agent] -->|MCP over stdio| T[FastMCP tool layer]
  T --> V[Validated inputs and projections]
  V --> S[Stock service / dispute service]
  S --> C[Zoho client]
  C --> R[Token manager, rate controls, TTL cache]
  R -->|HTTPS GET| Z[Zoho Inventory API]
  R -->|local HTTP| F[Deterministic fictional mock]
```

## Decisions

| Decision | Why | Cost or boundary |
|---|---|---|
| Read-only connector surface | Inventory context should inform an agent without letting it mutate merchant records. | Corrections and order actions stay in Zoho or an explicitly authorized workflow. |
| Composed decision tools | A sellability result and a missing-evidence list are closer to agent decisions than raw endpoint payloads. | The stock rule and evidence fields must be validated against an actual merchant workflow. |
| Bounded projections and 8 KB cap | Keep irrelevant Zoho fields and oversized records out of the model context. | Large responses must be narrowed; cap behavior should be checked against all output shapes. |
| Default PII masking | Reduce customer data exposed to agent context. | The sales-order tool has an explicit `include_pii` option; deployments should keep it false unless needed. |
| In-process TTL cache and local limiter | Simple controls fit a single connector process and reduce repeat reads. | Cache is per-process and may be stale; it does not coordinate multiple replicas. |
| Deterministic mock and fixed seed | Permit offline development and reproducible policy simulations. | Mock success does not prove Zoho compatibility or live performance. |

The stock service uses an explicit `actual_available_stock` value or a single-location `location_actual_available_stock` value; it never substitutes physical `stock_on_hand`. If the available quantity is ambiguous across several locations, it returns `unknown`. Low stock uses `reorder_level` or a configurable default. These are code-level rules, not a verified definition of sellability for a merchant. The evidence service marks absent fields unavailable and preserves typed upstream errors rather than presenting them as empty evidence; delivery time and merchant-specific linkage still require live validation. See [Limitations](LIMITATIONS.md).

**Delivery-proof gap:** live package responses included `shipment_delivered_date`, but it was blank on the three matching shipped records checked. Its source and meaning are not established as carrier-confirmed; a date entered in Zoho is not independent carrier evidence. Ask who or what sets the field and how soon, then add a carrier-tracking integration if independent proof is required.

The app-facing server is FastMCP over stdio. Tool telemetry goes to stderr; PII-minimized audit events go to a separate mode-0600 JSONL file selected by `ZOHO_AUDIT_LOG_FILE`. These local sinks still need deployment-level access and retention controls. The checked-in `mcp/tool_spec.json` is generated from the server's registered tool schemas.

## What I chose not to build and why

- **Write tools:** explicitly outside the connector's read-only job; order creation, stock adjustment, refunds, or dispute submission require separate authorization and controls.
- **Webhooks:** useful for lower-latency invalidation, but would add public ingress and lifecycle complexity before the polling and freshness need is measured.
- **Multi-tenant OAuth:** a single-organization local connector is enough to validate the interface; production tenancy needs tenant isolation and credential lifecycle design.
- **UI or database:** neither is needed for a small MCP read path; the audit sink is a local append-only JSONL file for this single-process prototype, not a multi-tenant audit database.
- **Distributed limiter:** the current deployment target is one process. A multi-replica deployment would need shared quota coordination.
- **Real merchant/customer data:** all fixtures remain fictional. No interview, data access, or uplift claim is implied.
- **Production Agent Studio runtime wiring:** this repo demonstrates an MCP integration shape only. It does not claim access to Razorpay internal interfaces.
- **Automated dispute filing or discount delivery:** evidence and stock context support human or agent decisions; taking external action needs a separately governed workflow.

## Production extensions tied to M1–M3

- **M1, wasted nudges:** validate which Zoho stock quantity means sellable for the merchant; measure stock freshness at decision time; add cache invalidation if 60-second staleness changes suppression decisions. Pilot against a control group before changing discount policy.
- **M2, evidence completeness:** map the merchant's package and carrier process, find who or what records the Zoho delivered-date field, measure update lag, and count missing fields by source. A Zoho status/date alone is not carrier-confirmed delivery proof; add a verified carrier-tracking integration if the evidence gap is material. Never infer delivery.
- **M3, cost and quota:** compare agent request volume with all Zoho consumers, export call/cache/retry metrics, and use a shared limiter if running multiple replicas. Agree on a quota budget and stop conditions with operations.

## Current project readiness

The repository contains the MCP server, service layer, client, mock API, evaluation outputs, tool specification, offline demo, OAuth helper, live-smoke helper, and an isolated seeded-data helper. The read-only Zoho preflight, smoke, probe, and assertions passed against the throwaway organization on 2026-10-03. Agent Studio runtime loading and credential storage remain untested.
### OAuth token reuse across commands

The private `0600` token file stores the current access token and absolute expiry alongside the refresh token. New CLI processes reuse that access token while it has more than five minutes remaining, only when the cached client-credentials fingerprint matches the configured client. Writes use a sidecar file lock, a unique `0600` temporary file, and an atomic replace so concurrent writers cannot share a temporary path or expose a partial JSON file. The in-process lock provides single-flight refreshes within one process; separate processes can still refresh concurrently if no valid cache entry exists. Preflight uses the same cache instead of forcing a token request. A 401 invalidates the rejected cached access token before refresh, while preserving the refresh token if refresh fails.
