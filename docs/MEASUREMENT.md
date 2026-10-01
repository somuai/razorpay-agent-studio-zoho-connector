# Measurement Framework & Impact Evaluation (FR-8, FR-10)

> **Notice:** All benchmark numbers, uplift percentages, and financial values presented in this document are **SIMULATED on fictional data** (`seed=42`) representing *Kaveri Home Goods*, a Bangalore D2C home decor merchant. Never construe these as production metrics.

---

## 1. Executive Summary & Success Metrics

The Zoho Inventory Connector enables Razorpay Agent Studio agents to query merchant inventory and order data safely. We evaluate impact against two core merchant problems:
1. **P1 (Abandoned Cart Conversion):** Blind cart nudges disburse discount codes for out-of-stock items, burning discount budget and alienating buyers.
2. **P2 (Dispute Responder):** Chargeback rebuttals require manual assembly of shipping/delivery proof across multiple screens, resulting in missed dispute deadlines and lost revenue.

### Success Metrics Taxonomy

| Metric | Name | Business Rationale | Simulation Target | Simulated Result (`seed=42`) |
|---|---|---|---|---|
| **M1** | **Wasted Nudges & Discount Liability** | % of cart recovery nudges sent for unavailable SKUs, and fictional INR discount budget wasted on zero-stock items. | Reduce out-of-stock waste to 0% | **0.0%** (vs 24.0% baseline); **₹13,536.80** zero-stock waste eliminated; **₹23,849.10** total budget saved |
| **M2** | **Dispute Evidence Completeness** | % of chargebacks with complete fulfillment proof from a single tool call; strict enumeration of missing fields for partials. | > 40% complete; 0 unverified guesses | **45.0%** complete; **55.0%** partial with exact missing fields flagged; **0** guesses |
| **M3** | **Agent Efficiency & Upstream Quota Cost** | API calls per decision, cache hit rate, and daily Zoho quota consumed (% of free-tier 1,000 req/day limit). | < 0.5 calls/decision; < 10% daily quota | **0.15** calls/cart decision; **85.0%** cache hit rate; **3.0%** of daily quota |

---

## 2. Simulated Results Table

The simulation was executed using `make eval` over 200 seeded cart events and 40 dispute cases.

### Metric 1: Abandoned Cart Nudge Optimization (N = 200 Carts)

| Metric / Attribute | Baseline Policy (Unaware) | Connector-Aware Agent | Delta / Merchant Impact |
|---|:---:|:---:|:---:|
| **Nudges Sent** | 200 | 152 | 48 out-of-stock carts safely suppressed |
| **Wasted Nudges (Sent for 0 Stock)** | 48 (24.0%) | **0 (0.0%)** | **-24.0% (Eliminated completely)** |
| **Scarcity Nudges (No Discount Offered)** | 0 | 52 | Urgency driven by stock scarcity; 0% margin loss |
| **Total Discount Disbursed** | ₹57,282.10 | ₹33,433.00 | **₹23,849.10 saved** |
| **Wasted Discount on Zero Stock** | ₹13,536.80 | **₹0.00** | **100% budget liability eliminated** |

### Metric 2: Chargeback Dispute Evidence Completeness (N = 40 Cases)

| Evidence Classification | Cases | Pct (%) | Automated Ops Workflow Action |
|---|:---:|:---:|---|
| **Complete Evidence** (Order + Invoice + Tracking + Delivery) | 18 | **45.0%** | Instant 1-click gateway rebuttal submission |
| **Partial Evidence** (Missing tracking or delivery timestamp) | 22 | **55.0%** | Flagged for manual merchant ops triage with exact missing fields |
| **Unsupported / Not Found** | 0 | 0.0% | Auto-flagged to prevent hopeless dispute penalties |

#### Missing Fields Breakdown in Partial Disputes:
- `package`: Missing in 18 cases (Order confirmed but packaging slip not generated in Zoho).
- `carrier`: Missing in 18 cases (Shipment order not assigned to courier partner).
- `tracking_number`: Missing in 22 cases (Courier assigned or pending tracking number upload).
- `shipment_date`: Missing in 18 cases.
- `delivery_date`: Missing in 22 cases (In-transit or courier delivery sync pending).
- `delivery_status`: Missing in 18 cases.
- `invoice`: Missing in 8 cases (Draft or un-invoiced orders).

### Metric 3: Agent Cost & Quota Efficiency

- **Total Upstream API Calls (Nudge Sim):** 30 (for 200 cart evaluations)
- **Cache Hits (TTL 60s):** 170 (**85.0% hit rate**)
- **API Calls per Decision:** **0.15** calls/cart decision
- **API Calls per Dispute Case:** **2.1** calls/case
- **Daily Zoho Free-Tier Quota Consumed:** **3.0%** of 1,000 requests/day cap

---

## 3. Event Instrumentation Schema (FR-8, FR-15)

Every tool invocation emits structured JSON events to `stderr` (preserving `stdout` for clean MCP JSON-RPC protocol frames). The eval harness computes the exact metrics above by parsing these logs.

### A. Tool Execution Event Schema (`tool_execution`)

```json
{
  "ts": "2026-10-01T12:00:00.000000+00:00",
  "event": "tool_execution",
  "tool": "get_stock_availability",
  "status": "success",
  "latency_ms": 1.25,
  "cache_hit": true,
  "throttled": false,
  "retries": 0,
  "http_status": 200,
  "zoho_code": 0,
  "stock_status": "in_stock",
  "result_count": 1,
  "truncated": false,
  "request_id": "req_8a9f20bc12d4"
}
```

#### Fields Description:
- `ts`: ISO 8601 UTC timestamp.
- `event`: Event discriminator (`tool_execution`).
- `tool`: Invoked MCP tool name.
- `status`: Execution outcome (`success` or `error`).
- `latency_ms`: Duration of the tool execution in milliseconds.
- `cache_hit`: Boolean indicating if response was served from in-memory TTL cache.
- `throttled`: Boolean indicating if token bucket throttled the call.
- `retries`: Number of upstream HTTP retries attempted.
- `http_status`: HTTP status code returned by Zoho API.
- `zoho_code`: Zoho internal error code (e.g. 0 for success, 44 for block, 45 for quota).
- `stock_status`: Normalized stock outcome (`in_stock`, `low_stock`, `out_of_stock`, `unknown`).
- `result_count`: Number of entities returned.
- `truncated`: Boolean indicating if output hit the 8 KB safety cap.
- `request_id`: Correlation UUID for distributed tracing across logs.

### B. Compliance Audit Event Schema (`audit_tool_invocation` - FR-15)

Audit logs are emitted separately and guarantee that customer PII and upstream authentication secrets are never written:

```json
{
  "timestamp": "2026-10-01T12:00:00.000000+00:00",
  "event": "audit_tool_invocation",
  "tool": "search_sales_orders",
  "parameters": {
    "customer_email": "p***a@example.com",
    "customer_phone": "******3210",
    "reference_number": "order_Rzp_101",
    "auth_token": "[REDACTED_SECRET]"
  },
  "request_id": "req_8a9f20bc12d4"
}
```

---

## 4. Real-World Measurement Design (Production Experimentation Plan)

To transition from fictional simulation to a live merchant rollout (e.g. at Kaveri Home Goods), the following rigorous experimentation plan must be followed:

### 1. Randomized Controlled Trial (A/B Test Design)
- **Unit of Randomization:** User checkout session / cart abandonment event. Random assignment occurs when the checkout is abandoned on Razorpay Checkout.
- **Control Group (50%):** Standard Abandoned Cart agent with stock-blind policy (sends standard 10% coupon nudge to all abandoned carts regardless of inventory).
- **Treatment Group (50%):** Connector-aware agent with Zoho inventory awareness (suppresses out-of-stock items; sends stock scarcity message with 0% discount on low-stock items; sends standard 10% coupon on in-stock items).

### 2. Sample Size & Measurement Window
- **Minimum Detectable Effect (MDE):** 1.5% absolute lift in recovered GMV and 15% reduction in discount spend.
- **Sample Size:** 2,400 cart abandonments per group (4,800 total sessions), providing 80% statistical power at $\alpha = 0.05$.
- **Window:** 14 consecutive days to account for day-of-week purchase cycles (weekend vs weekday decor shopping).
- **Attribution Window:** 24 hours from cart nudge delivery.

### 3. Confounders & Controls
1. **Catalog Restock Timing:** If an item is restocked within 2 hours after suppression, did we lose a sale? *Mitigation:* Log suppressed carts and observe if user returned organically.
2. **Discount Elasticity on Low Stock:** Does sending a scarcity message without a discount depress conversion compared to a 10% discount? *Mitigation:* Track conversion rates specifically for low-stock SKUs between Control and Treatment.
3. **Multi-Item Carts:** If 1 item is out of stock but 2 items are in stock, should the agent nudge for the available items? *Mitigation:* Recommend partial cart nudges in v2.
4. **Shared Upstream Quota:** If merchant's ERP or warehouse scanner consumes 800 Zoho API calls in the morning, the agent must not exhaust the remaining 200 calls.

---

## 5. Explicit Kill Criteria

We define strict, falsifiable kill criteria. If any of the following occur during a production pilot, **we pause or shut down the agent integration immediately**:

1. **Quota Contention:** If the agent consumes more than **15% of the merchant's total daily Zoho API quota** (150 calls on Free plan) during any 24-hour period, or triggers a Zoho Code 44 / Code 45 error in production.
2. **Negative Conversion Delta:** If the 24-hour conversion rate in the Treatment group drops by more than **2.0% relative to Control** ($p < 0.05$), indicating that scarcity messaging without discount harms merchant brand or buyer intent.
3. **Cache Inefficiency:** If production cache hit rate drops below **50%** over a 48-hour window, indicating high inventory churn or un-cacheable SKU dispersion.
4. **Dispute Inefficacy:** If the dispute rebuttal win rate for the merchant fails to improve by at least **5.0 percentage points** after 30 days of automated evidence submission, or if evidence completeness is under **25%** due to poor warehouse ops data hygiene.
