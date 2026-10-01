# Zoho Inventory API Notes & Verified Facts

**Last Verified:** October 2026  
**Audience:** Integration Engineers, LLM Agent Builders  
**Guiding Principle:** Every fact must cite its documentation source. Items that cannot be directly reached or confirmed via live endpoints are explicitly marked `[UNVERIFIED]` and made configurable.

---

## 1. Data Center & Base Endpoints

- **Data Center Routing:** Zoho operates multiple data centers (.com, .eu, .in, .com.au, .jp, .ca). For the India Data Center (default for Kaveri Home Goods):
  - **Accounts / Auth Base:** `https://accounts.zoho.in`
  - **API Base:** `https://www.zohoapis.in/inventory/v1`
  - **Doc URL:** [Zoho Inventory Multi-DC API Documentation](https://www.zoho.com/inventory/api/v1/)
- **Dynamic API Domain (`api_domain`):**
  - In Zoho OAuth 2.0, the response to `/oauth/v2/token` includes `api_domain` (e.g., `https://www.zohoapis.in` or `https://www.zohoapis.com`).
  - *Implementation Rule:* The connector extracts `api_domain` from token responses and routes subsequent API calls to `{api_domain}/inventory/v1`. If absent, it defaults to the configured data center URL (`https://www.zohoapis.in/inventory/v1` for `ZOHO_DC=in`).
  - **Doc URL:** [Zoho Accounts OAuth Token Response](https://www.zoho.com/accounts/protocol/oauth/web-server-applications.html)

---

## 2. Authentication & OAuth 2.0 Flow

- **Authorization Request:**
  - **Endpoint:** `GET https://accounts.zoho.in/oauth/v2/auth`
  - **Parameters:**
    - `client_id`: Required.
    - `response_type`: `code`
    - `scope`: Comma-delimited list of scopes.
    - `redirect_uri`: `http://localhost:8080/callback` (or configured loopback address).
    - `access_type`: `offline` (Mandatory to receive a `refresh_token`).
    - `prompt`: `consent` (Ensures refresh token is re-minted upon re-authorization).
    - `state`: Cryptographic random string (CSRF protection, FR-1.1).
  - **Doc URL:** [Zoho OAuth Authorization Request](https://www.zoho.com/accounts/protocol/oauth/web-server-applications.html)
- **Token Exchange:**
  - **Endpoint:** `POST https://accounts.zoho.in/oauth/v2/token`
  - **Body Parameters (Form URL-encoded):**
    - `grant_type`: `authorization_code`
    - `client_id`: Client ID
    - `client_secret`: Client Secret
    - `redirect_uri`: Exact matching redirect URI
    - `code`: Authorization code from callback
  - **Doc URL:** [Zoho Token Exchange Documentation](https://www.zoho.com/accounts/protocol/oauth/web-server-applications.html)
- **Refresh Flow:**
  - **Endpoint:** `POST https://accounts.zoho.in/oauth/v2/token`
  - **Body Parameters:**
    - `grant_type`: `refresh_token`
    - `client_id`: Client ID
    - `client_secret`: Client Secret
    - `refresh_token`: Refresh token string
  - **Access Token Lifetime:** 3600 seconds (1 hour).
  - **Refresh Buffer:** TokenManager refreshes 300 seconds (5 minutes) before expiration.
- **Limits on Token Generation:**
  - Zoho strictly limits the generation of new refresh and access tokens per day/minute. Minting tokens per request causes account lockouts. Single-flight caching with `asyncio.Lock` is mandatory.
  - **Doc URL:** [Zoho OAuth Limits and Exceptions](https://www.zoho.com/accounts/protocol/oauth/limits.html)
- **PKCE Support `[UNVERIFIED]`:**
  - Zoho OAuth documentation mentions PKCE (`code_challenge` / `code_verifier`) for mobile and native clients, but support across regional accounts domains can vary.
  - *Resolution:* Supported if enabled via configuration, but loopback authorization server validates the cryptographically signed `state` parameter as the primary CSRF guard.

---

## 3. Headers & Organization Context

- **Authorization Header Format:**
  - Format: `Authorization: Zoho-oauthtoken <access_token>`
  - *Critical syntax note:* Notice the exact prefix `Zoho-oauthtoken ` followed by a single space. Passing standard `Bearer <access_token>` is rejected by Zoho Inventory v1.
  - **Doc URL:** [Zoho Inventory API Authentication](https://www.zoho.com/inventory/api/v1/)
- **Organization ID Requirement:**
  - All Inventory v1 endpoints require an active organization context.
  - Header or query parameter: Passed as query parameter `organization_id={org_id}` (or header `X-com-zoho-inventory-organizationid: {org_id}`).
  - *Implementation:* Passed consistently as query parameter `organization_id` on all GET requests.
  - **Doc URL:** [Zoho Inventory API Request Headers](https://www.zoho.com/inventory/api/v1/#organization-id)

---

## 4. Minimal Read-Only Scopes

Following the Principle of Least Privilege, the connector requests only read-only scopes. Full-access (`.ALL` or `.CREATE`) scopes are never requested:

| Scope Name | Resource Description | Required For |
|---|---|---|
| `ZohoInventory.items.READ` | Read items, item groups, inventory stock levels | `list_items`, `get_item`, `search_items`, `get_stock_availability` |
| `ZohoInventory.salesorders.READ` | Read sales orders, line items, status | `list_sales_orders`, `get_sales_order`, `search_sales_orders`, dispute evidence |
| `ZohoInventory.packages.READ` | Read packaging details and slip numbers | Fulfillment evidence compilation |
| `ZohoInventory.shipmentorders.READ` | Read courier shipments, tracking numbers, status | Dispute fulfillment proof (`tracking_number`, carrier, delivery date) |
| `ZohoInventory.invoices.READ` | Read billing invoices generated from orders | Dispute invoice evidence (`invoice_number`, status, amount) |
| `ZohoInventory.organizations.READ` | Read organization profile, currency, timezone | Organization verification, base currency lookup |

**Doc URL:** [Zoho Inventory Scopes Guide](https://www.zoho.com/inventory/api/v1/#oauth-scopes)

---

## 5. Rate Limits, Quotas & Error Codes

Zoho enforces three distinct rate control tiers:

1. **Per-Minute Rate Limit (HTTP 429 & Error Code 44):**
   - Standard limit: 100 requests per rolling minute per organization.
   - Connector client-side rate limiter: 80 requests per minute (token bucket with leaky refill) to ensure safety margins.
   - If exceeded upstream: Zoho returns HTTP 429 or JSON payload with `code: 44` ("You have exceeded the limit of requests per minute").
   - Action: Temporary cool-down; circuit breaker opens on code 44.
2. **Daily API Quota (Error Code 45):**
   - Daily cap depends on Zoho tier: Free = 1,000 requests/day; Standard = 2,500; Professional = 5,000; Premium = 75,000; Enterprise = 10,000.
   - When daily quota is exhausted, Zoho returns `code: 45` ("You have exceeded the maximum API call limit for the day").
   - *Rule (FR-3.4):* **NEVER RETRY** on code 45. Immediately fail fast and return `QuotaExhaustedError` informing the agent not to poll until the next midnight reset.
3. **Concurrency Soft Limit (Error Code 1070):**
   - Soft limit: ~10 concurrent requests in flight.
   - Exceeding returns `code: 1070` ("Maximum concurrent requests limit reached").
   - Connector concurrency control: Client-side `asyncio.Semaphore(5)` keeps concurrency safely below the threshold.
- **Doc URL:** [Zoho Inventory API Errors & Rate Limits](https://www.zoho.com/inventory/api/v1/#errors)

---

## 6. Inventory Items & Stock Availability Semantics

Zoho Inventory item objects contain multiple stock quantity fields with differing semantics:

- **`stock_on_hand`:** The physical count of units currently inside the warehouse(s). Does not account for committed or unfulfilled customer orders.
- **`available_stock`:** Physical stock based on shipments and receives.
- **`actual_available_stock`:** True sellable stock. Defined as `stock_on_hand` minus open committed sales orders.
  - *Decision:* For abandoned cart conversion nudges, the connector uses `actual_available_stock` (or falls back to `available_stock` if `actual_available_stock` is not returned). This guarantees nudges are not sent for inventory committed to other buyers.
- **`reorder_level`:** Configured threshold for replenishment.
  - If `actual_available_stock <= 0`: Status is `out_of_stock`.
  - If `0 < actual_available_stock <= reorder_level` (or default 5): Status is `low_stock`.
  - If `actual_available_stock > reorder_level`: Status is `in_stock`.
- **Per-Warehouse Breakdown:** Item details return `warehouses` array with `warehouse_id`, `warehouse_name`, `warehouse_stock_on_hand`, `warehouse_available_stock`.
- **Doc URL:** [Zoho Inventory Items API](https://www.zoho.com/inventory/api/v1/#items)

---

## 7. Sales Orders, Packages, Shipments & Invoices

- **Sales Order (`/salesorders/{id}`):**
  - Fields: `salesorder_id`, `salesorder_number`, `date`, `status` (`draft`, `confirmed`, `fulfilled`, `closed`, `void`), `customer_id`, `customer_name`, `reference_number`, `total`, `currency_code`.
  - Nested links: Zoho sometimes nests `invoices`, `packages`, or `shipments` within the sales order payload, but full tracking details reside in the dedicated sub-resources.
- **Packages (`/packages?salesorder_id={id}`):**
  - Fields: `package_id`, `package_number`, `date`, `status` (`not_shipped`, `shipped`, `delivered`).
- **Shipment Orders (`/shipmentorders/{id}`):**
  - Fields: `shipment_id`, `shipment_number`, `shipment_date`, `carrier`, `tracking_number`, `status`, `delivery_date`.
- **Dispute Fulfillment Evidence Composition (FR-5.4):**
  - Dispute defense requires showing an unbroken chain: Order -> Invoice -> Package -> Carrier Tracking -> Delivery Timestamp.
  - If any link is missing, the connector explicitly reports `present: false` / `status: "not_available"`. It never extrapolates or hallucinates dates.
- **Doc URL:** [Zoho Inventory Sales Orders API](https://www.zoho.com/inventory/api/v1/#sales-orders)  
- **Doc URL:** [Zoho Inventory Shipments API](https://www.zoho.com/inventory/api/v1/#shipments)

---

## 8. Pagination & Search Capabilities

- **List Pagination:**
  - Query parameters: `page` (1-indexed), `per_page` (default 200, bounded to <= 50 in our tools).
  - Response root metadata:
    ```json
    "page_context": {
      "page": 1,
      "per_page": 50,
      "has_more_page": true,
      "applied_filter": "Status.All",
      "sort_column": "created_time",
      "sort_order": "D"
    }
    ```
- **Filter and Search Parameters:**
  - Items: `search_text` (matches name or SKU), `status` (`active`, `inactive`).
  - Sales Orders: `search_text`, `status`, `customer_id`, `reference_number`, `date_start`, `date_end`.
- **Doc URL:** [Zoho Inventory Pagination & Filtering](https://www.zoho.com/inventory/api/v1/#pagination)
