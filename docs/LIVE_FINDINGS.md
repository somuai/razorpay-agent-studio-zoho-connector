# Zoho live API findings

> This file is a report destination, not evidence by itself. `make live-probe` replaces it only after a credentialed run against the authorized personal throwaway organization. No live probe has been run yet. Do not claim a result until the command is run and the generated observations are reviewed.

Calls issued: not run (0).

| Probe | Result | Observed response shape / note | Update |
|---|---|---|---|
| `GET /salesorders` without `salesorder_ids` | INCONCLUSIVE | Awaiting authorized live run. | `docs/API_NOTES.md` |
| Item list filters (`search_text`, `filter_by`, `sku`) | INCONCLUSIVE | Awaiting authorized live run. | `docs/API_NOTES.md` |
| Item detail stock fields and locations | INCONCLUSIVE | Awaiting item data in the throwaway org. | `docs/API_NOTES.md` |
| Sales-order filters, including `reference_number` | INCONCLUSIVE | Awaiting fixture orders in the throwaway org. | `docs/API_NOTES.md` |
| Pagination and `per_page` behavior | INCONCLUSIVE | Awaiting authorized live run. | `docs/API_NOTES.md` |
| Package detail `shipment_order` embedding | INCONCLUSIVE | Awaiting package and shipment fixtures. | `docs/API_NOTES.md` |
| Shipment fields and delivered-at timestamp | INCONCLUSIVE | Awaiting shipped package fixtures. | `docs/API_NOTES.md` |
| `Retry-After` response header | INCONCLUSIVE | No throttling was induced; normal requests will only tell whether a header was naturally present. | `docs/API_NOTES.md` |
| Missing-record response code | INCONCLUSIVE | Awaiting authorized live run. | `docs/API_NOTES.md` |

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
