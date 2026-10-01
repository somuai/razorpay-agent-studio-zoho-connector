# Zoho Inventory agent connection: operations summary

**For discussion with a merchant.** Kaveri Home Goods is fictional; no interview or production setup has occurred. This describes the intended connector behavior and current limits.

## What the agent can see

The connector can read a limited projection of product and sales-order records. It can check an explicitly available stock quantity and return an `in_stock`, `low_stock`, `out_of_stock`, or `unknown` status with the time of retrieval. It can gather order, invoice, package, and shipment details that Zoho returns, then list fields it could not find.

For those answers, data sent from Zoho into the agent context can include product/item ID, name, SKU, active status, price and currency, the selected stock quantity and source field, reorder level, unit and location stock breakdown. Order answers can include sales-order ID/number, date, status, customer ID and a masked customer name/email/phone, reference number, total and currency, and projected line items. Evidence answers can include invoice/package numbers and dates, shipment status, carrier and tracking number, plus explicit missing-field reasons. Free-text notes and addresses are excluded. Full email/phone are included only if an authorized caller explicitly sets `include_pii=true` on supported order tools.

Customer phone and email are masked in sales-order results by default. The order detail and search tools have an `include_pii` option; keep it off unless there is a clear business need and the agent is authorized. The connector sends the projection fields needed for the specific answer into the agent context. Authentication data must stay in local secret configuration and must never be included in prompts or logs. Tool-call audit metadata is written separately to a private JSONL file (`ZOHO_AUDIT_LOG_FILE`, default `.zoho_audit.jsonl`); free-text queries are omitted and contact details are masked. The deployment owner must protect and rotate that file under the merchant's retention policy. If the audit sink cannot accept a record, the tool request fails closed and asks the operator to restore the sink.

## What it can never do

This connector cannot create or change orders, adjust stock, issue refunds, send discounts, or submit dispute responses. It cannot reserve stock, promise an item will still be available at checkout, invent a delivery event, or guarantee that evidence will win a dispute. A successful evidence result means the fields in this connector's checklist were found; it is not a legal or network-rule decision.

## When information is missing or unavailable

Stock data may be cached (60-second default in the code path) and can change after it is read. A stale timestamp, `unknown` status, authentication problem, quota exhaustion, or upstream error means the agent should not guess. Some errors should be retried only when the error guidance says so. If an invoice, package, tracking number, or delivery date is absent, the result should identify that gap for an operations person.

Confirmed empty results are listed as missing fields. Authentication, quota, rate-limit, and upstream failures remain errors with retry guidance; they must not be interpreted as proof that a record is absent. This behavior is covered by the client and service error mapping; live response shapes still need verification in a throwaway Zoho org.

## How we would know whether this helps

First, check in a fictional-data simulation whether stock-aware policy avoids discounting out-of-stock items and what data is missing from seeded disputes. These outputs are labeled **SIMULATED**; they do not show real savings or dispute outcomes. For a real pilot, agree a baseline and control group, record data freshness and tool failures, measure cart and dispute outcomes, and include all shared Zoho API usage. See [Measurement](MEASUREMENT.md).

## What we need from you before a pilot

- Confirm which Zoho quantity means sellable stock, including reservations and warehouse rules.
- Show where tracking and delivery confirmation are recorded, and how the Razorpay order/payment ID maps to a Zoho order.
- Identify an isolated test organization, approve minimum read-only scopes, and confirm shared API quota constraints.
- Approve the fields the agent may see and the retention/access policy.
- Agree the success measures, control design, and stop conditions before any customer-facing action.

**Live status:** no real Zoho org has been verified for this workspace. Treat this as a design proposal until the live read-only smoke check has been run and confirmed.
