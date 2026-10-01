# MCP tool guide

The examples below show the normalized contract with fictional values; use IDs returned by `list_items` or `list_sales_orders` in the connected organization. The query builder accepts Zoho numeric IDs and the mock's bounded `item_` / `so_` fixture IDs.

All successful tools return normalized data with `as_of` and cache metadata where implemented. Errors are returned as typed, agent-readable objects. Responses are subject to an 8 KB cap. Inputs used in upstream filters are validated. Sales-order PII is masked by default, except current projections may include a partially masked name/email/phone.

## `list_items`

Browse the catalog; do not use for a current cart stock decision. Inputs: `page` (default 1), `per_page` (default 50, maximum 50), optional `status` (`active`, `inactive`, `all`).

```json
{"page":1,"per_page":20,"status":"active"}
```
```json
{"items":[{"item_id":"item_1001","name":"Handwoven Ikat Cushion Cover","sku":"KHG-CUSH-001","status":"active","rate":699.0,"stock_on_hand":32.0,"actual_available_stock":30.0,"reorder_level":10.0}],"page":1,"per_page":20,"has_more":false,"next_page":null,"as_of":"2026-10-02T00:00:00+00:00","cached":false,"truncated":false}
```

## `get_item`

Retrieve one item's projection by its returned `item_id`; use the stock tool when deciding whether to nudge.

```json
{"item_id":"item_1001"}
```
```json
{"item_id":"item_1001","name":"Handwoven Ikat Cushion Cover","sku":"KHG-CUSH-001","status":"active","rate":699.0,"currency_code":"INR","stock_on_hand":32.0,"actual_available_stock":30.0,"reorder_level":10.0,"unit":"pcs","description":"Fictional catalog item","as_of":"2026-10-02T00:00:00+00:00","cached":false}
```

## `search_items`

Find by validated name or SKU substring; `only_low_stock` limits results at or below reorder level (including out-of-stock). It returns `items`, `count`, freshness, and cache status.

```json
{"query":"Ikat","only_low_stock":false,"limit":10}
```
```json
{"items":[{"item_id":"item_1001","name":"Handwoven Ikat Cushion Cover","sku":"KHG-CUSH-001","rate":699.0,"actual_available_stock":30.0,"reorder_level":10.0,"is_low_stock":false,"is_out_of_stock":false}],"count":1,"as_of":"2026-10-02T00:00:00+00:00","cached":false,"truncated":false}
```

## `get_stock_availability`

Primary cart-nudge context tool. Check before deciding whether to offer a discount. The connector returns `in_stock`, `low_stock`, `out_of_stock`, or `unknown`; this is advisory and reflects the selected Zoho quantity at `as_of`, not a reservation or real-time guarantee. Physical `stock_on_hand` is never used as a sellable fallback. If only a multi-location quantity exists, the tool returns `unknown` until allocation policy is validated. `skus_or_ids` accepts up to 20 values; `bypass_cache` defaults false.

```json
{"skus_or_ids":["KHG-CUSH-001","KHG-SILK-019"],"bypass_cache":false}
```
```json
{"items":[{"item_id":"item_1001","sku":"KHG-CUSH-001","name":"Handwoven Ikat Cushion Cover","status":"in_stock","quantity_sellable":30.0,"source_stock_field":"actual_available_stock","reorder_level":10.0,"unit":"pcs","warehouses":[],"as_of":"2026-10-02T00:00:00+00:00","cached":false},{"item_id":"item_1019","sku":"KHG-SILK-019","name":"Pure Silk Brocade Tablecloth","status":"out_of_stock","quantity_sellable":0.0,"source_stock_field":"actual_available_stock","reorder_level":5.0,"unit":"pcs","warehouses":[],"as_of":"2026-10-02T00:00:00+00:00","cached":false}],"as_of":"2026-10-02T00:00:00+00:00","cached":false,"truncated":false}
```

## `list_sales_orders`

Browse orders, optionally by status, customer ID, and ISO dates. Use only when the caller is authorized to inspect order information.

```json
{"status":"fulfilled","date_from":"2026-09-01","date_to":"2026-09-30","page":1,"per_page":10}
```
```json
{"sales_orders":[{"salesorder_id":"so_2001","salesorder_number":"SO-10001","date":"2026-09-02","status":"fulfilled","customer_id":"301","customer_name":"Test Customer 1.","customer_email":"c***1@example.com","customer_phone":"******1001","reference_number":"order_RzpKav1001","total_amount":1398.0,"currency_code":"INR","line_items_count":1,"line_items":[],"match_basis":null}],"page":1,"per_page":10,"has_more":false,"next_page":null,"as_of":"2026-10-02T00:00:00+00:00","cached":false,"truncated":false}
```

## `get_sales_order`

Retrieve one order's normalized projection by its returned `salesorder_id`. `include_pii` defaults false; enable only when needed and authorized.

```json
{"salesorder_id":"so_2001","include_pii":false}
```
```json
{"salesorder_id":"so_2001","salesorder_number":"SO-10001","date":"2026-09-02","status":"fulfilled","customer_id":"301","customer_name":"Test Customer 1.","customer_email":"c***1@example.com","customer_phone":"******1001","reference_number":"order_RzpKav1001","total_amount":1398.0,"currency_code":"INR","line_items_count":1,"line_items":[{"item_id":"item_1001","sku":"KHG-CUSH-001","name":"Handwoven Ikat Cushion Cover","quantity":2.0,"rate":699.0,"item_total":1398.0}],"match_basis":null,"as_of":"2026-10-02T00:00:00+00:00","cached":false}
```

## `search_sales_orders`

Match by exact stored reference, Razorpay order ID (searched as reference text, then exact-compared locally), or customer email (resolve an exact contact email, then list that contact's orders). Email matching may be ambiguous. The response includes `match_basis`; inspect the result before associating a dispute.

```json
{"razorpay_order_id":"order_RzpKav1001","limit":5,"include_pii":false}
```
```json
{"sales_orders":[{"salesorder_id":"so_2001","salesorder_number":"SO-10001","date":"2026-09-02","status":"fulfilled","customer_id":"301","customer_name":"Test Customer 1.","customer_email":"c***1@example.com","customer_phone":"******1001","reference_number":"order_RzpKav1001","total_amount":1398.0,"currency_code":"INR","line_items_count":1,"line_items":[],"match_basis":"reference_number_exact"}],"count":1,"match_basis":"reference_number_exact","as_of":"2026-10-02T00:00:00+00:00","cached":false,"truncated":false}
```

## `get_order_fulfillment_evidence`

Primary evidence-assembly tool for an order already matched to a dispute. It reports fields found and missing; it does not submit a rebuttal or establish that the evidence is sufficient under a payment network's rules.

```json
{"salesorder_id":"so_2001","bypass_cache":false}
```
```json
{"salesorder_id":"so_2001","completeness":"partial","missing_fields":["delivery_date"],"sales_order":{"status":"present","value":"SO-10001","source_resource":"salesorders","details":{"status":"fulfilled","date":"2026-09-02","total":1398.0,"currency":"INR"}},"invoice":{"status":"present","value":"INV-20001","source_resource":"invoices","details":{}},"package":{"status":"present","value":"PKG-30001","source_resource":"packages","details":{}},"carrier":{"status":"present","value":"BlueDart","source_resource":"shipmentorders","details":null},"tracking_number":{"status":"present","value":"fictional-tracking","source_resource":"shipmentorders","details":null},"shipment_date":{"status":"present","value":"2026-09-03","source_resource":"shipmentorders","details":null},"delivery_date":{"status":"not_available","value":null,"source_resource":"shipmentorders","details":{"reason":"Delivery date confirmation missing"}},"delivery_status":{"status":"present","value":"in_transit","source_resource":"shipmentorders","details":null},"order_date":"2026-09-02","fulfillment_summary":"Order SO-10001 has partial fulfillment proof in Zoho. Missing critical evidence: [delivery_date].","as_of":"2026-10-02T00:00:00+00:00","cached":false}
```

Examples illustrate response shape, not observed live payloads. Exact fields and Zoho semantics remain subject to [API verification notes](API_NOTES.md) and a real-org smoke test.
