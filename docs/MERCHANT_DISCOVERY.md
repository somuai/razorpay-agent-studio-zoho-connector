# Merchant discovery plan

**Scenario:** Kaveri Home Goods is fictional. These are questions for a future discovery session; no interview has taken place. Each question tests a hypothesis, identifies data to request, and names an answer that could change the design.

| # | Ask the merchant | Hypothesis tested | Data to request (sample only, with approval) | What answer would change the design? |
|---|---|---|---|---|
| 1 | What happens today from cart abandonment to nudge, and who sets discount rules? | Some offers are sent without stock awareness. | Workflow diagram and anonymized event timestamps. | If offers are already inventory-gated, focus on freshness or measurement rather than suppression. |
| 2 | What does “sellable” mean for your warehouses and channels? | `actual_available_stock` approximates stock safe to advertise. | Zoho field definitions, reservations, safety stock, and warehouse rules. | If reserved stock or channel allocation is excluded, change the stock source/rule before any pilot. |
| 3 | How quickly does stock change, and what stale-data window is acceptable? | A 60-second cache is operationally safe. | Stock update frequency and stockout/cancellation history. | If inventory changes within the cache window often, lower TTL or add event-driven invalidation. |
| 4 | What should happen to a multi-item cart when just one SKU is unavailable? | Suppressing the entire nudge is acceptable for the first simulation. | Anonymized cart line-item and conversion outcomes. | If partial-cart recovery is preferred, design line-level eligibility and message composition. |
| 5 | Which stock states should change discount or message policy? | Low stock should prompt scarcity language without discount. | Current promotion rules, margin constraints, and approved wording. | If scarcity messages are prohibited or discounts remain required, redesign policy and test economics. |
| 6 | How do operations assemble chargeback evidence today, and what causes delay? | Orders and shipment evidence are split across systems or records. | Redacted case checklist, source systems, and handling timestamps. | If Zoho does not participate in the workflow, connect the actual system of record. |
| 7 | Where are invoice, package, carrier, tracking, dispatch, and delivery confirmation recorded? | Zoho contains all fields the composed evidence tool seeks. | Anonymized sample records and field mappings. | If delivery facts live in a courier system, add a separately scoped integration; never infer them. |
| 8 | How do you link a Razorpay order/payment/dispute to a Zoho sales order? | The Razorpay order ID is stored in `reference_number`. | Redacted IDs from paired records; custom-field configuration. | If linkage is absent or non-unique, implement a merchant-approved mapping key and ambiguity handling. |
| 9 | Which Zoho organization, region, OAuth owner, and scopes can support a read-only trial? | India DC and a single org are appropriate for the first setup. | Org/DC identifiers and consented read-only app configuration; no secrets in notes. | Different DC, org model, or OAuth policy changes routing and onboarding steps. |
| 10 | What other integrations consume the Zoho API quota, and what capacity can this agent use? | A conservative local request budget is enough. | Plan limits, daily usage pattern, and peak periods. | Shared quota pressure may require a smaller budget, scheduling, or a shared limiter. |
| 11 | What would count as success, and what would make you stop the pilot? | Fewer wasteful discounts and faster evidence assembly are valuable outcomes. | Baseline events, event definitions, cost/GMV constraints, support incidents. | Set thresholds from the merchant's economics and baseline; do not adopt simulated thresholds as facts. |
| 12 | What data may be exposed to the agent, and how long may it be retained? | Minimal projections and masking meet the merchant's privacy needs. | Data classification, retention, role/access requirements. | Restrict fields further, remove email matching, or change deployment/log retention controls. |

## Week-one plan (proposed)

| Day | Work | Exit evidence |
|---|---|---|
| 1 | Map cart and dispute workflows with operations and confirm success/stop measures. | Approved workflow map, owners, baseline definitions. |
| 2 | Inspect field semantics, data ownership, OAuth constraints, quota, and identifier linkage using a throwaway or read-only test org. | Verified mapping sheet; unresolved facts explicitly marked. |
| 3 | Validate sample stock decisions and dispute evidence against operations' expected answer. | Small, approved fixture set and mismatch log. |
| 4 | Run a shadow-mode evaluation with no customer-facing actions; inspect freshness, missing fields, latency, and quota. | Event-level report with access controls and no unnecessary PII. |
| 5 | Review errors and kill criteria with merchant; decide whether to proceed, revise, or stop. | Signed-off pilot plan or explicit no-go decision. |

All data requests are conditional on merchant approval and should use redacted/minimized records. This plan does not imply that a merchant has agreed to participate.
