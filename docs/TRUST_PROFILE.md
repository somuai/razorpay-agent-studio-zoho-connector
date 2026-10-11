# Proposed trust profile

**Proposal only:** Kaveri Home Goods is fictional. No merchant has approved these controls, and the document is not a data-processing agreement or production security review.

## Data boundary

The agent can receive normalized item names, SKUs, prices, stock quantities and source fields; sales-order summaries and line items; and recorded invoice, package, shipment, carrier, tracking, and missing-field information. Customer email and phone are masked by default in supported order projections. Addresses and free-text notes are excluded from agent output. An explicit `include_pii` option can expose fuller contact details, so a pilot should leave it disabled unless a documented use case and approval require it.

The connector sends the selected projection and tool result from Zoho to the MCP caller. The local audit stream records tool name, time, request identifier, and sanitized parameters; application telemetry records operational fields. The audit file is created with restrictive permissions and is separate from application logs. The repository sets no retention period or automatic deletion schedule; retention, access, rotation, and deletion must be agreed before deployment.

The connector cannot create or edit records, adjust stock, issue refunds, send offers, or submit a dispute. It cannot reserve inventory, guarantee current sellability, infer missing evidence, or independently prove delivery from a Zoho-entered date.

## Approvals to require before a pilot

- Written approval for the data fields, read scopes, organization, named users, and isolated test environment.
- Agreement on whether contact data is needed; default to no full email or phone in model context.
- Approval of the agent host, model/data handling, logs, audit access, retention period, deletion method, and incident contact.
- Merchant confirmation of sellable-stock rules, stale-data tolerance, order matching key, and authoritative carrier evidence.
- A quota budget, shadow-mode plan, success measures, human handoff rules, stop conditions, and named operational owners.

These are proposed safeguards to validate with the merchant and the platform owner before any real data is connected.
