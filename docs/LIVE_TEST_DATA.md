# Live test data checklist

Create these fictional records by hand in the separate throwaway India-data-center Zoho Inventory organization. Do not use the institutional organization. Keep all names, references, and tracking values obviously synthetic.

## Items

Create ten inventory-tracked items with unique SKUs `KHG-001` through `KHG-010`. Set a reorder level on every item so the connector's status rule can be checked. Use distinct fake names such as `KHG Test Item 001`.

| SKU | Set opening stock | Reorder level | Expected status |
|---|---:|---:|---|
| KHG-001 | 0 | 5 | out_of_stock |
| KHG-002 | 30 | 5 | in_stock |
| KHG-003 | 18 | 4 | in_stock |
| KHG-004 | 12 | 3 | in_stock |
| KHG-005 | 9 | 2 | in_stock |
| KHG-006 | 15 | 5 | in_stock |
| KHG-007 | 8 | 2 | in_stock |
| KHG-008 | 3 | 5 | low_stock |
| KHG-009 | 2 | 2 | low_stock |
| KHG-010 | 0 | 5 | out_of_stock |

This creates six ordinary in-stock items, two at or below their reorder level, and two out of stock. If locations are enabled, split `KHG-006` over two locations and note that in the local expected file. With multiple locations and no merchant allocation rule, this connector intentionally reports `unknown` rather than summing locations; set `KHG-006` to `unknown` in `live_expected.yaml` for that variant.

## Sales orders and fulfillment records

Create five sales orders with unique references exactly `RZP-TEST-001` through `RZP-TEST-005`, each containing at least one of the test items.

| Reference | Expected setup | Evidence expectation |
|---|---|---|
| RZP-TEST-001 | Invoice, package, shipment; fake carrier and tracking number | Partial; `shipment_date` and `delivery_date` unavailable unless those exact fields are exposed; delivery proof `not_available` |
| RZP-TEST-002 | Invoice, package, shipment; fake carrier and tracking number | Partial; `shipment_date` and `delivery_date` unavailable unless those exact fields are exposed; delivery proof `not_available` |
| RZP-TEST-003 | Invoice, package, shipment; fake carrier and tracking number | Partial; `shipment_date` and `delivery_date` unavailable unless those exact fields are exposed; delivery proof `not_available` |
| RZP-TEST-004 | Invoice and package, no shipment | Partial; shipment status/carrier/tracking/dates missing |
| RZP-TEST-005 | Invoice, no package or shipment | Partial; package/shipment status/carrier/tracking/dates missing |

Zoho's documented shipment fields in this project do not include a carrier-confirmed delivered-at timestamp. The connector's current completeness field also counts shipment and delivery dates, so a data-backed record may show `partial` even when its basic Zoho evidence exists. Do not mark a test order complete based on your expectation alone: inspect the actual output and use it to update the expected file if your organization exposes different fields. `delivery_proof` in the expected file means the connector's `delivery_date.status`; expect `not_available` for all five.

## Expected connector results

Copy [`live_expected.example.yaml`](../live_expected.example.yaml) to `live_expected.yaml` at the repository root, then change the expected item statuses to match the exact stock values you entered. The assertion command checks each SKU's status and, for each order, whether it was found, the connector completeness label, missing field names when specified, and delivery-date availability. It reports only row identifiers' final three characters, not tracking numbers or record identifiers.

If an assertion fails, first compare the value in Zoho with the item reorder level and verify each sales order's reference number. Then inspect the masked failure and `docs/LIVE_FINDINGS.md`; do not paste credentials, customer data, or real tracking information into chat.
