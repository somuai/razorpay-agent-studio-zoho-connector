# Merchant summary: technical appendix

This appendix records implementation details behind [the operations summary](MERCHANT_SUMMARY.md).

- Item answers may contain item ID, name, SKU, active status, price/currency, available quantity and its Zoho source field, reorder level, unit, and location-level stock quantities.
- Order answers may contain order ID/number, date, status, customer ID, masked name/email/phone, reference number, total/currency, and line items. Supported order tools accept `include_pii`; it defaults to false. An authorized caller may explicitly enable full email/phone.
- Evidence answers include available invoice/package numbers and dates, shipment status, carrier and tracking number, and explicit missing-field reasons. Delivery time is not inferred.
- Stock TTL defaults to 60 seconds. Stock tools return `as_of` and `cached`; `bypass_cache` is supported.
- Tool results are capped at 8 KB and indicate truncation.
- Free-text notes and addresses are excluded from agent-visible output; the upstream API response may contain fields that are then discarded. Authentication values are not part of tool output or logs.
- Tool-call audit records are written separately as JSONL. The path is configured by `ZOHO_AUDIT_LOG_FILE` and defaults to `.zoho_audit.jsonl`; the file is created with restrictive permissions. PII-minimized parameters are recorded, and a failed audit write prevents the tool request from proceeding.
- Application event logs and the audit stream have separate retention and access-control requirements. Protect and rotate both under the merchant's policy.
