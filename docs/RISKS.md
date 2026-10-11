# Risk register

Likelihood and impact are my judgments for a pilot using this connector, not measured rates. Owners below describe roles in a real engagement; no such merchant engagement is claimed.

| Risk | Likelihood / impact (judgment) | Mitigation in this repo | Trigger to escalate | Real engagement owner |
|---|---|---|---|---|
| Wrong stock field overstates sellable stock | Medium / High | Explicit availability field, `unknown` when unavailable, stock-field audit and planned UI comparison in `make live-stock-fields`. The live API-to-UI mapping remains inconclusive. | Any mismatch with UI, reservations, or checkout eligibility; unknown result on a decision SKU. | Merchant inventory owner, with FDE |
| Wrong shipment attached to a dispute | Medium / High | Exact local sales-order ID filtering and regression test `test_dispute_service_ignores_packages_for_other_orders`. | Any package/order mismatch or evidence tied to a different customer/order. | Dispute operations owner, with FDE |
| Shared Zoho quota exhausted | Medium / High | Rate limiter, bounded retries, circuit/quota handling, call metrics, and simulated warm/cold quota estimates. | Zoho quota errors, sustained throttling, or projected daily usage above the agreed budget. | Merchant Zoho admin / integration owner |
| Cached stock is stale | Medium / Medium | Short stock TTL, `as_of`, `cached`, and `bypass_cache` support. | A stock change after lookup changes an offer or fulfillment decision. | Merchant inventory owner, with FDE |
| PII leaks in logs or tool output | Low / High | Default masking, projections, redaction, audit sanitization, identifier scans, and regression tests. | Any raw contact value, credential, or unintended identifier in output, logs, or captures. | Security/privacy owner and connector owner |
| Zoho schema drifts | Medium / High | Tolerant parsing, explicit unknown/not-available states, response-shape probe, and offline altered-payload tests. | Missing/changed field causes a tool error or changes a decision without an alert. | Connector owner, with merchant Zoho admin |
| Order matching is ambiguous | Medium / High | Bounded search, exact comparison where supported, `match_basis`, and documented unverified email path. | More than one candidate, no unique payment-to-order reference, or unexplained mismatch. | Payments/reconciliation owner |
| Advisory status is treated as a guarantee | Medium / High | Tool descriptions and capability docs call the status advisory; freshness and unknown states are exposed. | An agent sends an offer or promise from stale, unknown, or failed data. | Agent product/policy owner, with merchant operations |

Review this table with the merchant before a pilot. Likelihood and impact should be revised from observed workflows, incidents, and agreed tolerance.
