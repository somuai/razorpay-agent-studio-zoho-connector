# Zoho live API findings

> This file separates observations already made during the authorized live preflight/smoke from API facts still awaiting `make live-probe`. No full live probe or live assertion has been run. Do not claim a result until the command is run and the generated observations are reviewed.

Live-probe calls issued: not run (0). The separately authorized preflight used 8 API calls, and the prior live smoke used 14; neither produced the shape-only probe report.

| Probe | Result | Observed response shape / note | Update |
|---|---|---|---|
| `GET /salesorders` without `salesorder_ids` | INCONCLUSIVE | Awaiting authorized live run. | `docs/API_NOTES.md` |
| Item list filters (`search_text`, `filter_by`, `sku`) | INCONCLUSIVE | Awaiting authorized live run. | `docs/API_NOTES.md` |
| Item detail stock fields and locations | INCONCLUSIVE | Awaiting item data in the throwaway org. | `docs/API_NOTES.md` |
| Sales-order filters, including `reference_number` | INCONCLUSIVE | Awaiting fixture orders in the throwaway org. | `docs/API_NOTES.md` |
| Pagination and `per_page` behavior | INCONCLUSIVE | Awaiting authorized live run. | `docs/API_NOTES.md` |
| Package detail `shipment_order` embedding | INCONCLUSIVE | Awaiting package and shipment fixtures. | `docs/API_NOTES.md` |
| Shipment fields and delivered-at timestamp | INCONCLUSIVE | Shipped test fixtures exist, but the shape-only live probe has not yet been run. | `docs/API_NOTES.md` |
| `Retry-After` response header | INCONCLUSIVE | No throttling was induced; normal requests will only tell whether a header was naturally present. | `docs/API_NOTES.md` |
| Missing-record response code | INCONCLUSIVE | Awaiting authorized live run. | `docs/API_NOTES.md` |
| Scoped shipment detail route used by preflight | CONFIRMED | The read-scope check reached the route and received the expected not-found response for a nonexistent record. This does not establish a shipment list endpoint. | `docs/API_NOTES.md` |

## Live run finding: request identifiers in HTTP logs

During the authorized live smoke on 2026-10-02, HTTP request logs printed full Inventory request URLs, including organization and record identifiers. This was a logging defect; no identifier values are reproduced here. The connector now sets HTTPX/HTTPCore/urllib3 to WARNING by default and applies process-wide redaction to log records, exception text, connector telemetry, audit parameters, and not-found errors. Regression coverage exercises mock HTTP and each live helper without contacting Zoho. The live scripts have not been rerun after this fix, so screenshot safety on a subsequent live run remains to be confirmed.

## Unauthenticated connectivity diagnostic (2026-10-02)

This was run from the Codex command environment, not from the author's normal desktop terminal, and made no authenticated request. `curl -4` and `curl -6` each reached the Accounts homepage (HTTP 200); Python HTTPX timed out at connect with its default transport and with a transport bound to IPv4. DNS in that command environment returned one IPv4 answer and no IPv6 answer per tested Zoho host; no proxy variable names were set. These differing results do not establish the cause and do not prove that sandbox policy is responsible. Run the same Python check in the author's normal terminal before drawing that conclusion. Live commands should be run from the author's normal terminal; a transport timeout is not evidence of a credential rejection.

## Facts a bounded read-only probe cannot settle

These remain `INCONCLUSIVE` after a successful probe unless separately verified. The probe must not write records, exhaust quota, or infer merchant workflow from synthetic data.

| Claim | Result | How tested / why unresolved | Update |
|---|---|---|---|
| OAuth grant-code lifetime discrepancy; PKCE support; Self Client equivalence | INCONCLUSIVE | A prompt code exchange does not measure expiry timing or test alternate OAuth parameters/app types. | `docs/API_NOTES.md` |
| The merchant integration stores Razorpay payment IDs in `reference_number` | INCONCLUSIVE | A synthetic reference query validates Zoho behavior only; it cannot verify the upstream field mapping. | `docs/API_NOTES.md` |
| Customer-email-to-order matching | INCONCLUSIVE | No unique synthetic contact email is prepared for this probe. | `docs/API_NOTES.md` |
| Package number and sales-order number filter semantics | INCONCLUSIVE | The probe reads package pages/details but does not exercise the ambiguous package search filters. | `docs/API_NOTES.md` |
| Which stock quantity is sellable for the merchant | INCONCLUSIVE | The probe observes field names/types only; reservations and location allocation require merchant workflow evidence. | `docs/API_NOTES.md` |
| Exact quota reset time or guaranteed `Retry-After` behavior | INCONCLUSIVE | The probe will not exhaust quota or deliberately induce throttling. | `docs/API_NOTES.md` |
| Free-plan eligibility for the separate throwaway account | INCONCLUSIVE | The prior Premium trial observation belonged to a prohibited institutional organization. | `docs/API_NOTES.md` |
| Item create route and minimum accepted item payload | INCONCLUSIVE | Requires an Inventory item write; outside the GET-only probe. | `docs/API_NOTES.md` |
| Contact-person requirement for sales-order creation | INCONCLUSIVE | Requires a controlled sales-order write; outside the GET-only probe. | `docs/API_NOTES.md` |
| Minimum accepted sales-order line-item payload | INCONCLUSIVE | Requires a controlled sales-order write; outside the GET-only probe. | `docs/API_NOTES.md` |
| Whether shipment creation automatically sets shipped status | INCONCLUSIVE | Requires a shipment write/state transition; outside the GET-only probe. | `docs/API_NOTES.md` |
| Seeder idempotency under repeated writes | INCONCLUSIVE | Requires repeated Inventory writes; outside the GET-only probe. | `docs/API_NOTES.md` |

The probe records field paths and JSON types only. It never records resource values, identifiers, emails, phone numbers, tracking numbers, or response bodies. Tests use an in-memory GET-only fake and make no network calls.
