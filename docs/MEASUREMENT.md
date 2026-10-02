# Measurement plan (FR-8, FR-10, FR-15)

> **SIMULATED:** Every result in `eval/results/` and every number printed by `make eval` comes from fictional, deterministic fixtures (`seed=42`) for the fictional Kaveri Home Goods merchant. These results show policy behavior on seeded cases. They do not establish real merchant impact, conversion uplift, dispute win rate, or production latency.

## Questions and metrics

The project tests two workflow hypotheses: stock checks can avoid sending recovery nudges for unavailable cart items, and a composed evidence lookup can make existing Zoho fulfillment evidence easier for dispute ops to assemble. It does not test whether customers convert more often or whether a submitted dispute is won.

| Metric | Definition in the simulation | Reported evidence |
|---|---|---|
| **M1: unavailable nudges** | For each policy, number of nudge actions sent for carts containing at least one seeded out-of-stock item divided by all 200 cart events. The connector-aware policy suppresses the whole cart if any item is out of stock; partial-cart recovery is out of scope. | Baseline and connector-aware counts and percentages; fictional INR discount given to unavailable carts. |
| **M1: discount budget** | Baseline discount amount minus connector-aware discount amount. Also report baseline discount on unavailable carts separately. | The first is discount avoided, including discounts withheld for low-stock scarcity carts; it is **not** all waste. Only the second is discount directed to zero-stock carts in this fixture. |
| **M2a: Zoho-documented evidence completeness** | Share of 40 fictional mock cases with order, invoice, package, shipment status, carrier, and tracking number present. Delivery proof is excluded from this measure. | Count and percentage of cases with all six fields. The count is simulated from mock records and is not live Zoho coverage. |
| **M2b: delivery proof completeness** | Share of cases with carrier-confirmed delivered-at timestamp or equivalent. The reviewed Zoho Shipment Orders schema does not document this field, so the schema-faithful estimate is 0/40. | The mock fixture separately reports whether its undocumented `delivery_date` field is present; this is not accepted as carrier proof. A carrier-tracking integration is needed to establish this measure. |
| **M2c: mock checklist completeness** | Legacy mock-only measure requiring every field in the current evidence projection, including the mock-only `delivery_date`. | Retained to show the earlier fixture result, clearly separated from Zoho-documented completeness and delivery proof. It does not establish live evidence coverage. |
| **M3: connector cost** | Upstream GET calls divided by cart decisions or dispute cases, plus cache lookup hit rate and upstream calls divided by the assumed free-plan daily limit of 1,000. | Nudge phase, dispute phase, and combined two-phase call/quota estimates. The 1,000-call cap is an assumption from the project brief and must be verified for a live org and plan. |
| **Latency** | `make eval` records p50/p95 elapsed time from the injected virtual clock. The virtual clock does not advance for ordinary mock requests. | The reported 0 ms percentiles confirm deterministic virtual-clock elapsed time only; they are **not runtime latency benchmarks**. Use production `latency_ms` events for latency. |

Reproduce the simulation with `make eval`. The command writes `eval/results/nudge_results.json`, `eval/results/dispute_results.json`, and `eval/results/summary.json`. Each JSON result has `simulation_mode: SIMULATED`; the stdout report also labels the run SIMULATED. The eval deliberately keeps deterministic JSON separate from host-dependent wall-clock timings.

## Reading the seeded result

The baseline fixture's 27% out-of-stock share is an explicit fixture assumption, not an estimate of any merchant's rate. The connector-aware result of zero unavailable nudges is true by construction because the policy suppresses every cart labeled out of stock. Treat the comparison as a mechanism check only. `make eval` also emits a deterministic SIMULATED sensitivity sweep at 2%, 5%, 10% and 27%, using the same fictional discount offers and a seed-42 assignment of out-of-stock labels. The first merchant measurement should be the actual share of eligible carts containing unavailable items, using the merchant's agreed sellability definition.

The warm fixture uses 0.15 upstream calls per decision because the same 30-item catalog serves 200 carts and the cache stays warm. At the assumed 1,000-call daily cap, that supports 6,666 decisions/day at 100% allocation, 3,333 at 50%, and 1,666 at 25%. In the cold-cache scenario, each distinct SKU lookup costs one upstream call; the fixture averages 1.235 distinct SKUs per cart, supporting 809, 404, and 202 decisions at those same allocations. Both are **SIMULATED** feasibility bounds, not promises. Real cache hit rate depends on catalog size and traffic skew and must be measured; other Zoho users and integrations consume the shared organization quota.

In the seeded run, a cart containing any out-of-stock item is suppressed as a whole, a cart with low-stock items receives a scarcity message and no discount, and a cart whose items are all in stock can receive its normal discount. Baseline sends a discount nudge for every cart. All generated cart events run at the same virtual-clock instant, so the cache hit rate is an optimistic within-TTL fixture result; it does not model event spacing or changing stock. These rules produce a policy comparison, not a forecast: the fixtures do not model buyer response, inventory movement during delivery, discount elasticity, or operational handling.

For disputes, the output separates Zoho-documented evidence completeness, delivery proof, and the mock-only all-fields checklist. The fixture's fictional `delivery_date` does not appear in the reviewed Zoho schema and cannot be treated as carrier confirmation. None of these measures says the evidence is admissible, persuasive, or sufficient under a payment network's rules. Missing-field counts can overlap because one case may lack several fields.

## Instrumentation contract

The production event stream has one `tool_execution` JSON event per tool call. The application event contains no customer PII, access tokens, authorization headers, or secret-bearing URLs:

```json
{
  "ts": "2026-10-01T12:00:00.000000+00:00",
  "event": "tool_execution",
  "tool": "get_stock_availability",
  "status": "success",
  "latency_ms": 12.5,
  "cache_hit": false,
  "throttled": false,
  "retries": 0,
  "http_status": 200,
  "zoho_code": 0,
  "stock_status": "in_stock",
  "result_count": 1,
  "truncated": false,
  "request_id": "req_example_only"
}
```

Fields: `ts` is ISO 8601; `event` is the discriminator; `tool` and `status` identify the operation and outcome; `latency_ms` is tool wall time; `cache_hit`, `throttled`, and `retries` describe connector behavior; `http_status` and `zoho_code` identify upstream outcomes when available; `stock_status` is normalized and optional for non-stock tools; `result_count` and `truncated` describe the projection; `request_id` correlates records. Tool event logging is separate from the audit stream.

The separate `audit_tool_invocation` JSONL file (configured by `ZOHO_AUDIT_LOG_FILE`, default `.zoho_audit.jsonl`) records the tool name, timestamp, request ID, and a PII-minimized parameter summary. It omits credentials and free-text search terms and masks contact details and order/reference identifiers. Protect and rotate the file under the merchant's retention policy. If persistence fails, the tool call fails closed and emits an agent-safe error. Example:

```json
{
  "timestamp": "2026-10-01T12:00:00.000000+00:00",
  "event": "audit_tool_invocation",
  "tool": "search_sales_orders",
  "parameters": {"reference_number": "[MASKED]", "customer_email": "[MASKED]"},
  "request_id": "req_example_only"
}
```

For production analysis, compute tool latency percentiles from `latency_ms`; cache hit rate as cache-hit stock tool calls divided by eligible stock tool calls; retry and throttle rates from their event fields; and quota use by reconciling connector upstream calls with the merchant's Zoho organization-level usage. Do not infer organization-wide quota use from this connector's logs alone.

## Real merchant measurement plan

### Before a pilot

1. Validate with the merchant where stock-on-hand, sellable quantity, reservations, and warehouse availability are represented. Confirm the sellability rule and the cost of suppressing a cart that contains both unavailable and available items.
2. Validate that the Zoho order records link to the relevant Razorpay order/payment, and which package, shipment, tracking, and invoice fields ops actually uses for disputes.
3. Capture an agreed baseline and define the primary business outcome with the merchant. For nudges, use recovered contribution margin or conversion with discount cost included, not nudge count alone. For disputes, use evidence assembly time/completeness; measure case outcomes only if sample size and dispute rules allow a meaningful comparison.
4. Estimate sample size from the merchant's baseline rate, selected minimum effect, variance, and acceptable false-positive/false-negative rates. The simulation does not supply these inputs, so it does not claim a powered sample size.
5. Confirm Zoho plan quota, other integrations' consumption, data retention, access scopes, consent, and who can stop the pilot.

### Controlled rollout

- **Control:** the merchant's current approved abandoned-cart process. Do not deliberately send known out-of-stock nudges as a control. If the existing process already suppresses unavailable items, compare with that policy and evaluate the incremental value of this connector.
- **Treatment:** connector-aware decisioning, with the same channel, timing, and eligibility rules as control. Randomize eligible cart events where operationally and legally acceptable; otherwise use a pre-agreed matched or stepped rollout and document its limits.
- **Window:** agree before launch. Include full weekday/weekend cycles and enough time to observe the conversion attribution window and inventory restocks. Avoid stopping early based on noisy intermediate outcomes.
- **Disputes:** use a staged before/after or matched-case study of assembly time and missing-evidence rates. Keep case submission and dispute strategy under human control. Do not attribute win-rate changes to this connector without accounting for case mix and representativeness.

### Minimum event fields

Use pseudonymous IDs and retain only approved fields: assignment group; event timestamp; cart or dispute cohort ID; SKU identifiers or approved category; stock result and `as_of`; cache age; tool outcome and latency; nudge eligibility/action/discount; delivery timestamp; purchase/conversion and net contribution margin in the attribution window; inventory restock/adjustment time; dispute reason/category; evidence fields present/missing; human assembly time; and final outcome when available. Keep identity mapping in the merchant's systems. Never put full customer details, tokens, or payment credentials in this evaluation dataset.

### Confounders to track

- Seasonality, campaigns, traffic source, and weekday/weekend mix.
- Restock timing, reservations, stock synchronization delay, and inventory churn after the check.
- Discount elasticity, competing promotions, price changes, and multi-item-cart composition.
- Nudge delivery failures, channel reachability, attribution-window choice, and customers who purchase without a nudge.
- For disputes: reason-code mix, issuer rules, evidence retention, shipping partner behavior, case value, and ops handling changes.
- Zoho quota consumption shared with other org users and integrations, API throttles, and connector cache behavior.

## Kill criteria

Pause treatment and review with the merchant if any of these pre-agreed stop conditions occurs:

1. **Incorrect stock decision:** any confirmed case where stale or incorrect data causes a nudge to be sent for an item the agreed sellability rule says is unavailable, or a material number of available carts to be suppressed. Investigate the source field, timestamp, cache age, and threshold before resuming.
2. **Quota or reliability harm:** any code 45 daily-quota exhaustion attributable to the connector, repeated code 44 organization blocks, or connector usage above the merchant-approved daily budget. The 15% of quota value can be an initial ceiling only if the merchant explicitly approves it; lower shared headroom takes precedence.
3. **Customer or margin harm:** after the pre-agreed minimum sample and attribution window, treatment contribution margin or conversion is below control by the merchant's pre-agreed unacceptable amount, or the treatment creates a material complaint/opt-out increase. Define the margin and harm thresholds before looking at treatment results.
4. **No operational value:** after a representative pilot, there is no meaningful reduction in unavailable-item nudges or evidence assembly time/completeness relative to the current process, and measured connector cost or maintenance is not justified by the merchant.
5. **Evidence integrity:** any guessed or misattributed fulfillment evidence, or any systematic gap that makes the evidence bundle misleading. Disable automated use until corrected; missing data must stay explicitly missing.

These are stop rules, not claims that a particular outcome has happened. The merchant and Razorpay owner must set numeric thresholds and sample requirements before a live experiment. A result that is inconclusive is not a success; extend only with an agreed rationale or stop.
