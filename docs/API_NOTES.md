# Zoho Inventory API notes

**Checked:** 2026-10-02 against the official Zoho pages linked below. This is documentation research only; no Zoho account or live API call was used. `UNVERIFIED` means the cited official documentation does not settle the point, not that the behavior is necessarily unsupported.

## Data center and API routing

- Zoho lists India Accounts at `https://accounts.zoho.in/` and the India Inventory API host as `https://www.zohoapis.in`. The v1 API root for this connector is therefore `https://www.zohoapis.in/inventory/v1`. Source: [Zoho Inventory OAuth](https://www.zoho.com/inventory/api/v1/oauth/) and [Zoho Inventory Introduction, data centers](https://www.zoho.com/inventory/api/v1/introduction/).
- Zoho's OAuth token examples include an `api_domain` field and explain that API calls use that returned host. Build the Inventory root as `{api_domain}/inventory/v1`; use configured `ZOHO_DC` only if the token response lacks it. Source: [Zoho Self Client authorization-code flow](https://www.zoho.com/developer/oauth/self-client/authorization-code-flow.html).
- The organization ID is required as the `organization_id` query parameter for Inventory resource requests. The Organizations list endpoint is an exception that lists the user's organizations without an organization ID. Sources: [Zoho Inventory Introduction](https://www.zoho.com/inventory/api/v1/introduction/) and [Organizations API](https://www.zoho.com/inventory/api/v1/organizations/).

## OAuth facts

- Zoho Inventory documents an OAuth 2.0 authorization-code flow. The authorization request uses `/oauth/v2/auth`, `response_type=code`, a registered `redirect_uri`, `scope`, `state`, and `access_type=offline` to request a refresh token. It describes `state` as round-tripped and the authorization code as short-lived. Source: [Zoho Inventory OAuth](https://www.zoho.com/inventory/api/v1/oauth/).
- The Inventory OAuth page says access tokens normally expire in one hour; use the refresh-token grant at the DC-specific Accounts host. The refreshed token response contains `expires_in` and `api_domain`. Sources: [Zoho Inventory OAuth](https://www.zoho.com/inventory/api/v1/oauth/) and [Zoho Self Client authorization-code flow](https://www.zoho.com/developer/oauth/self-client/authorization-code-flow.html).
- Inventory's API-specific auth page uses `Authorization: Zoho-oauthtoken <access_token>`. Use this exact format for Inventory calls. Source: [Zoho Inventory OAuth](https://www.zoho.com/inventory/api/v1/oauth/). Zoho's generic OAuth overview describes a Bearer scheme, so the Inventory-specific instructions take precedence for this connector.
- Zoho currently documents token-generation throttles: at most 10 access-token requests in 10 minutes, at most 10 active access tokens per refresh token, at most 20 active refresh tokens per user/client, and at most 10 authorization codes per user in 10 minutes. Reuse access tokens and single-flight refreshes. Source: [Zoho OAuth token limits](https://www.zoho.com/developer/oauth/token-limits.html).
- The connector persists the current access token and expiry in the private `0600` token file and reuses it across CLI processes while more than five minutes remain and the client-credentials fingerprint matches. Writes are serialized with a local sidecar lock and committed by unique-temp-file atomic replacement. This reduces avoidable token-generation calls; it does not change Zoho's quota or refresh-token rules. Cross-process token refresh itself is not single-flight.
- **Authorization-code lifetime discrepancy — `UNVERIFIED`:** the Inventory-specific OAuth page says 60 seconds; the general token-limits page says two minutes. Treat codes as ephemeral and exchange immediately; confirm observed behavior for the registered app/DC. Sources: [Zoho Inventory OAuth](https://www.zoho.com/inventory/api/v1/oauth/) and [Zoho OAuth token limits](https://www.zoho.com/developer/oauth/token-limits.html).
- **PKCE — `UNVERIFIED`:** the Inventory OAuth authorization parameter list does not document `code_challenge` or `code_verifier`. Do not claim PKCE support or send those parameters unless confirmed in current Zoho documentation for this app type/DC. Source: [Zoho Inventory OAuth](https://www.zoho.com/inventory/api/v1/oauth/).
- **Self Client suitability — `UNVERIFIED` for this loopback app:** Zoho has a Self Client authorization-code path useful for manual/headless token setup, but the docs do not establish that it is equivalent to the connector's interactive loopback OAuth app configuration. Source: [Zoho Self Client authorization-code flow](https://www.zoho.com/developer/oauth/self-client/authorization-code-flow.html).

## Read scopes

The official API pages document resource-specific `.READ` scopes. Request these only; use the same pages to verify before adding or changing a scope:

| Resource | Read scope | Evidence |
|---|---|---|
| Items / item stock | `ZohoInventory.items.READ` | [Items API](https://www.zoho.com/inventory/api/v1/items/) |
| Sales orders | `ZohoInventory.salesorders.READ` | [Sales Orders API](https://www.zoho.com/inventory/api/v1/salesorders/) |
| Packages | `ZohoInventory.packages.READ` | [Packages API](https://www.zoho.com/inventory/api/v1/packages/) |
| Shipment orders | `ZohoInventory.shipmentorders.READ` | [Shipment Orders API](https://www.zoho.com/inventory/api/v1/shipmentorders/) |
| Invoices | `ZohoInventory.invoices.READ` | [Invoices API](https://www.zoho.com/inventory/api/v1/invoices/) |
| Contacts (only if needed for matching) | `ZohoInventory.contacts.READ` | [Contacts API](https://www.zoho.com/inventory/api/v1/contacts/) |
| Organizations | `ZohoInventory.settings.READ` | [Organizations API](https://www.zoho.com/inventory/api/v1/organizations/) |

The live seeder uses a separate refresh token and must have both the read scopes needed for preflight/idempotency (`ZohoInventory.items.READ`, `ZohoInventory.contacts.READ`, `ZohoInventory.salesorders.READ`, and `ZohoInventory.packages.READ`) and the write scopes for its planned endpoints (`ZohoInventory.items.CREATE`, `ZohoInventory.contacts.CREATE`, `ZohoInventory.salesorders.CREATE`, `ZohoInventory.packages.CREATE`, and `ZohoInventory.shipmentorders.CREATE`). It reads items, contacts, orders, and packages before or during deduplication; CREATE-only consent is insufficient. The connector's read token does not request these CREATE scopes. Exact resource route/schema uncertainties and lookup limits are recorded below; scope grants are never evidence that a live seed succeeded.

## Organization context, list operations, and filters

- `organization_id` is a required query parameter in the documented item, sales-order, package, shipment-order, and invoice operations. Sources: [Items API](https://www.zoho.com/inventory/api/v1/items/), [Sales Orders API](https://www.zoho.com/inventory/api/v1/salesorders/), [Packages API](https://www.zoho.com/inventory/api/v1/packages/), [Shipment Orders API](https://www.zoho.com/inventory/api/v1/shipmentorders/), [Invoices API](https://www.zoho.com/inventory/api/v1/invoices/).
- List endpoints use `page` and `per_page`; list responses carry a `page_context` object including `has_more_page`. The common default is 200 records/page, but endpoints can differ. Use a conservative connector maximum of 50 and follow `has_more_page`. Sources: [Pagination](https://www.zoho.com/inventory/api/v1/pagination/) and [Items API](https://www.zoho.com/inventory/api/v1/items/).
- Items support `search_text` (documented for name/SKU on the list operation) and `filter_by` enumerations, including active/inactive and low-stock categories. The item detail route is `GET /items/{item_id}`. Source: [Items API](https://www.zoho.com/inventory/api/v1/items/).
- Sales-order list and detail operations are documented as `GET /salesorders` and `GET /salesorders/{salesorder_id}`. Sales order fields include `reference_number`, `customer_id`, status, order date, and shipment date. The API page does not document a customer-email or Razorpay-order-ID search field. Source: [Sales Orders API](https://www.zoho.com/inventory/api/v1/salesorders/).
- Packages support list/detail reads and list search via `search_text`; documented status filters include All, NotShipped, Shipped, and Delivered. Package listing can be associated with a sales order. Source: [Packages API](https://www.zoho.com/inventory/api/v1/packages/).
- **Payment-to-order matching — `UNVERIFIED` as a Zoho-native feature:** `reference_number` exists on sales orders, but Zoho docs do not say that Razorpay order IDs are automatically written there or expose a named `razorpay_order_id` field. Matching works only if the merchant's integration stores the ID in that field or a configured custom field; always disclose the matched field as `match_basis`. Sources: [Sales Orders API](https://www.zoho.com/inventory/api/v1/salesorders/) and [Zoho Inventory custom fields](https://www.zoho.com/inventory/api/v1/salesorders/).
- **Customer-email matching — `UNVERIFIED` for sales orders:** contact objects expose email, but the sales-order API page does not document `customer_email` as a sales-order filter. Avoid passing email to an undocumented filter; if needed, resolve through a separately verified contact lookup flow. Sources: [Sales Orders API](https://www.zoho.com/inventory/api/v1/salesorders/) and [Contacts API](https://www.zoho.com/inventory/api/v1/contacts/).

## Stock field semantics

- Item responses document `stock_on_hand`, `reorder_level`, and per-location fields `location_stock_on_hand`, `location_available_stock`, and `location_actual_available_stock`. The docs describe these labels, but do not provide a precise formula tying committed orders, reservations, and pending shipments to each quantity. Source: [Items API](https://www.zoho.com/inventory/api/v1/items/).
- Treat `location_actual_available_stock` as the most explicitly named candidate for a sellable/available-to-promise quantity, but **`UNVERIFIED` whether Zoho's value is the right sellability rule for a particular merchant/channel**. Do not call `stock_on_hand` sellable stock. Surface the source field, location, and timestamp; validate the correct field and reservation behavior with the merchant before enabling automated nudge decisions.
- Item responses use `locations`, not a universally named `warehouses` property. Do not silently rename location IDs or aggregate across locations unless the merchant's fulfillment policy says which locations can serve an order. Source: [Items API](https://www.zoho.com/inventory/api/v1/items/).

## Fulfillment evidence fields

- Sales orders expose a `shipment_date` field and reference-number field. Sources: [Sales Orders API](https://www.zoho.com/inventory/api/v1/salesorders/).
- Package records document package date/status and item lines; the package API describes packages as slips for sales-order lines that can be tracked as shipped. Source: [Packages API](https://www.zoho.com/inventory/api/v1/packages/).
- Shipment-order records document `date` (described as the date the package is prepared), `status`, `detailed_status`, `status_message`, `carrier`, `tracking_number`, `reference_number`, and delivery-related details such as `delivery_days`. Source: [Shipment Orders API](https://www.zoho.com/inventory/api/v1/shipmentorders/).
- Shipment Orders documents a “Mark as Delivered” operation, but the record schema does not document a delivered-at timestamp/date. **Delivered date/time — `UNVERIFIED`:** don't invent a timestamp from the current status, shipment preparation date, or estimated delivery days. Report only explicit shipment status/details and mark the delivery timestamp unavailable unless a verified field/custom integration provides it. Source: [Shipment Orders API](https://www.zoho.com/inventory/api/v1/shipmentorders/).
- Invoice read/detail endpoints are available; invoices can be evidence fields where present. Source: [Invoices API](https://www.zoho.com/inventory/api/v1/invoices/).
- Composition rule: evidence completeness is limited to what the linked Zoho order, invoice, package, and shipment records actually expose. A tracking number or “delivered” status is not independent carrier proof of delivery. Missing fields remain unavailable; no implicit linkage or date inference.

## Limits and error codes

Official Inventory documentation currently states:

| Limit / code | Documented behavior | Connector implication |
|---|---|---|
| Per-minute | 100 requests/minute per organization | Keep client limiter below the upstream ceiling (project default 80/minute). |
| Daily API requests | Free 1,000; Standard 2,000; Professional 5,000; Premium 10,000; Enterprise 10,000 | Quota estimate must be configurable by plan and shared across all org consumers. |
| HTTP 429 / code 45 | Daily plan limit exceeded; example says maximum call rate limit of 1,000 | No retry that day; fail with quota guidance. |
| HTTP 429 / code 44 | Organization/account blocked for exceeding per-minute request limit | Open a cooldown circuit and fail fast. |
| Concurrent requests | Free: 5; paid: 10 (soft limit) | Default concurrency 5 is aligned with Free-plan max; do not assume paid soft limit. |
| HTTP 429 / code 1070 | Maximum in-process requests exceeded | Reduce parallelism and retry only within bounded policy. |

Source for all entries: [Zoho Inventory Introduction, API call limits](https://www.zoho.com/inventory/api/v1/introduction/). The public doc doesn't state an exact reset time or a `Retry-After` header contract; **both are `UNVERIFIED`**. Bound any wait and honor `Retry-After` only if Zoho actually returns it.

## Free-plan / throwaway-org availability

**Throwaway organization and API access remain `UNVERIFIED`.** A signed-in Zoho Inventory dashboard was observed in the India data center, showing a Premium trial with 14 days remaining and setup at 0%. The selected organization is institutional and the user explicitly prohibited using it; no test records, scopes, or credentials were created there. The user will create a separate throwaway organization under a personal Zoho account and handle all credential steps. This observation confirms neither access to that new organization nor live API behavior. Zoho's public India Inventory page advertises a free offering, but this does not verify access for a particular account or API access for the connector. Source: [Zoho Inventory India page](https://www.zoho.com/in/inventory/free-inventory-management-software/). The API limits documentation lists a Free plan quota, which does not establish account-specific access: [Zoho Inventory Introduction](https://www.zoho.com/inventory/api/v1/introduction/).

## HTTP and fault behavior references

- Zoho documents HTTP 401 for invalid authentication, 404 for a missing URL/resource, 429 for too many requests, and 500 for server errors. Some resource-level missing records are represented by an application JSON code/message even with a 200 example, so map both HTTP status and Zoho JSON `code`. Source: [Errors API](https://www.zoho.com/inventory/api/v1/errors/).
- The error page does not establish a universal `Retry-After` response header, or that every 404 means “record not found” (it describes a potentially incorrect URL). Treat those details as endpoint/runtime behavior to verify with an authorized test org.

## Official source index

- [Inventory OAuth](https://www.zoho.com/inventory/api/v1/oauth/)
- [Inventory Introduction (DCs and limits)](https://www.zoho.com/inventory/api/v1/introduction/)
- [OAuth token limits](https://www.zoho.com/developer/oauth/token-limits.html)
- [Self Client authorization-code flow and token response](https://www.zoho.com/developer/oauth/self-client/authorization-code-flow.html)
- [Pagination](https://www.zoho.com/inventory/api/v1/pagination/)
- [Items](https://www.zoho.com/inventory/api/v1/items/)
- [Sales Orders](https://www.zoho.com/inventory/api/v1/salesorders/)
- [Packages](https://www.zoho.com/inventory/api/v1/packages/)
- [Shipment Orders](https://www.zoho.com/inventory/api/v1/shipmentorders/)
- [Invoices](https://www.zoho.com/inventory/api/v1/invoices/)
- [Contacts](https://www.zoho.com/inventory/api/v1/contacts/)
- [Organizations](https://www.zoho.com/inventory/api/v1/organizations/)
- [Errors](https://www.zoho.com/inventory/api/v1/errors/)

## Optional isolated live-seed helper: write scopes, payloads, and duplicate checks

These write permissions belong only to `scripts/seed_zoho.py`; they must not be imported by or added to the read-only connector. All request examples below are endpoint-shape notes from documentation, not tested payloads. The DC root and `organization_id` handling are described above.

### Create fixture items with opening stock

- The Items documentation gives `ZohoInventory.items.CREATE` for create-item operations. Its item-create argument list documents a required item name (`name` in one section, `item_master_name` in a second item-master section), a required `unit` in the second section, optional `item_type`, `product_type`, `rate`, and `reorder_level`, and a `locations` array with `location_id`, `initial_stock`, and `initial_stock_rate`. This supports carrying initial stock in the create payload when locations are enabled. Source: [Items API, create item and create item-master sections](https://www.zoho.com/inventory/api/v1/items/).
- The same page documents `PUT /variants/{variant_id}/openingstock` with `ZohoInventory.items.UPDATE` as an alternate opening-stock operation. Without locations, it takes `initial_stock` and `initial_stock_rate`; with locations, use the `locations` array and do not also send the top-level stock fields. Source: [Items API, Update variant opening stock](https://www.zoho.com/inventory/api/v1/items/).
- **Item create route/payload version — `UNVERIFIED`:** the official page presents overlapping item and item-master/variant sections and names multiple routes (`POST /items` and `POST /itemmasters` in its endpoint index). It also differs in required name property (`name` versus `item_master_name`). Before live seeding, confirm which route/schema the target org's current OpenAPI document accepts. Do not send both name fields speculatively. If separate opening-stock update is used, the helper needs `items.CREATE` plus `items.UPDATE`; create-time locations stock is documented under `items.CREATE`.
- Stock-tracked item fields include `item_type=inventory`, `product_type=goods`, `track_inventory=true`, `rate`, `reorder_level`, `sku`, and the initial-stock fields. A sell price/account/tax configuration may be org-dependent; the docs do not give one universally minimal India-org body. **Minimum accepted item payload for this particular org — `UNVERIFIED`.** Do not hard-code IDs from sample payloads. Source: [Items API](https://www.zoho.com/inventory/api/v1/items/).

### Create a fictional customer contact (if one does not already exist)

- `POST /contacts` uses `ZohoInventory.contacts.CREATE`. `contact_name` is required; `contact_type` accepts `customer` or `vendor`. The create argument list includes `company_name`, `website`, `custom_fields`, `opening_balances`, and contact-person information. Sources: [Contacts API](https://www.zoho.com/inventory/api/v1/contacts/) and [Zoho Inventory contact-person endpoints](https://www.zoho.com/inventory/api/v1/contact-persons/).
- A seed helper can check `GET /contacts?organization_id=...&contact_name=<deterministic-fixture-name>` first; the list endpoint documents exact `contact_name` (max length 100), `company_name`, `email` and `search_text` filters plus `page` / `per_page`. Then create only if no exact fixture contact is found. Source: [Contacts API, list contacts](https://www.zoho.com/inventory/api/v1/contacts/).
- **Contact-person payload needed for a sales order — `UNVERIFIED`:** the Sales Orders schema exposes `contact_persons_associated`, but creating a contact does not require a contact person in the documented create argument list. The precise conditions under which an org requires one for sales-order creation are not established. Use no contact-person record unless the target org requires it; if required, create/list it using the contact-person API with the `contacts.CREATE` / `contacts.READ` scopes as documented. Sources: [Contacts API](https://www.zoho.com/inventory/api/v1/contacts/) and [Contact Persons API](https://www.zoho.com/inventory/api/v1/contact-persons/).

### Create a sales order

- `POST /salesorders` uses `ZohoInventory.salesorders.CREATE`. The create schema requires `customer_id`, a unique `salesorder_number`, and `line_items`. Each line item contains at minimum the documented identifying/product fields plus `rate`, `quantity`, and `unit`; use the fixture's returned item ID. `reference_number` is an accepted sales-order field and can hold a deterministic fictional payment/order reference for matching demonstrations. Sources: [Sales Orders API](https://www.zoho.com/inventory/api/v1/salesorders/) and [Items API](https://www.zoho.com/inventory/api/v1/items/).
- For reproducible fixtures, provide an explicit unique `salesorder_number` and `reference_number`, and pass `organization_id` as a query parameter. `date` is a supported field; no account-specific tax or delivery values should be copied from Zoho's examples. Source: [Sales Orders API, create sales order](https://www.zoho.com/inventory/api/v1/salesorders/).
- **Smallest valid line-item body — `UNVERIFIED`:** the docs label `line_items` required and enumerate fields, but do not establish that a given India organization accepts only `item_id`, `rate`, `quantity`, and `unit` without tax/account/location fields. Confirm with a throwaway org before relying on the minimum. Source: [Sales Orders API](https://www.zoho.com/inventory/api/v1/salesorders/).

### Create package, then shipment with fixture tracking

- `POST /packages` uses `ZohoInventory.packages.CREATE`; query parameters `organization_id` and `salesorder_id` are required. Body arguments require `date` and `line_items`. For direct packing of sales-order lines, each line uses `so_line_item_id` and `quantity`; when packing from a picklist, pass both `so_line_item_id` and `picklist_item_id`. `package_number` is documented and should be made deterministic for the fixture. Source: [Packages API, create package](https://www.zoho.com/inventory/api/v1/packages/).
- `POST /shipmentorders` uses `ZohoInventory.shipmentorders.CREATE`; query parameters `organization_id`, `package_ids`, and `salesorder_id` are required. The body schema lists `shipment_number`, `date`, `delivery_method`, `tracking_number`, and optional `reference_number` (also described as a tracking reference). This is the documented way to seed tracking data. Source: [Shipment Orders API, create shipment order](https://www.zoho.com/inventory/api/v1/shipmentorders/).
- An example shipment-create response includes status `shipped`; the docs do not say whether this state is guaranteed for every configuration or whether additional org workflow is required. **Automatic shipped state after create — `UNVERIFIED`.** A successful POST alone must not be described as real carrier acceptance or delivery. Source: [Shipment Orders API](https://www.zoho.com/inventory/api/v1/shipmentorders/).
- **Shipment duplicate lookup — `UNVERIFIED`:** the current Shipment Orders endpoint index documents create, update, retrieve-by-ID, delete, and mark-as-delivered; it does not expose a `GET /shipmentorders` list endpoint. A package detail example embeds a `shipment_order` object, but the documentation does not guarantee this nested object is returned for every package/configuration. Prefer GET the known package ID and inspect for an existing shipment before creating; verify actual response shape in the throwaway org. Sources: [Shipment Orders API](https://www.zoho.com/inventory/api/v1/shipmentorders/) and [Packages API](https://www.zoho.com/inventory/api/v1/packages/).

### Idempotency lookup strategy and limits

Zoho's Inventory API pages do not document a general idempotency-key header or create request key for these resources. Implement duplicate prevention in the seeder with deterministic fixture identifiers, preflight reads, and persisted returned Zoho IDs; do not assume the POST endpoints are idempotent. If a create times out after the server committed it, search again before retrying.

| Resource | Documented preflight read | Recommended key/check | Caveat |
|---|---|---|---|
| Contact | `GET /contacts` | Exact unique `contact_name` (or a unique fixture email via `email`) | Contact name/email filters are documented; no server idempotency token. [Contacts API](https://www.zoho.com/inventory/api/v1/contacts/) |
| Item | `GET /items` | Exact unique SKU via `sku` | Exact SKU is documented on the legacy item list; current item-master/variant listing uses different names and both routes appear in the doc. Confirm which schema applies. [Items API](https://www.zoho.com/inventory/api/v1/items/) |
| Sales order | `GET /salesorders` | Deterministic unique `salesorder_number`, then compare returned `reference_number` | List-all docs show pagination, but the rendered query list also marks `salesorder_ids` required and its example includes IDs; a direct server-side reference-number filter is not documented. **Whether list-all can be called without IDs is `UNVERIFIED`;** the connector maps an HTTP 400 to a recovery message recommending a verified ID, and suggests reference search only if the live probe confirms it works in that org. [Sales Orders API](https://www.zoho.com/inventory/api/v1/salesorders/) |
| Package | `GET /packages` or `GET /packages/{package_id}` | Link by known sales-order ID; compare fixture package number and inspect shipment link | List filters include `search_text`, package number prefix/contains, sales-order-number prefix/contains, status, dates, customer ID, and pagination. Some descriptions say “number” while naming IDs; verify exact filter semantics. [Packages API](https://www.zoho.com/inventory/api/v1/packages/) |
| Shipment | `GET /packages/{package_id}` if nested shipment details are present | Compare deterministic tracking number / shipment number on the known package | No shipment-order list endpoint is documented; nested package shipment details are not guaranteed. See `UNVERIFIED` above. [Shipment Orders API](https://www.zoho.com/inventory/api/v1/shipmentorders/) and [Packages API](https://www.zoho.com/inventory/api/v1/packages/) |

The package list's `salesorder_number_startswith` and `_contains` descriptions claim to search `salesorder_id`, and the package-number filters say they search `package_id`. This documentation wording is internally inconsistent; exact filter semantics are **`UNVERIFIED`** until exercised against the target org. Source: [Packages API](https://www.zoho.com/inventory/api/v1/packages/).
