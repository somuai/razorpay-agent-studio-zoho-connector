# Zoho Inventory connection: operations summary

**For a future merchant discussion.** Kaveri Home Goods is fictional. No merchant interview, live setup, or customer data is represented here.

| Can see | Masked | Never sees or does |
|---|---|---|
| Product names, SKUs, prices, stock quantities, sales orders, invoices, packages, shipment status, carrier and tracking number, when Zoho provides them. | Customer phone and email are partly hidden in normal order answers. | It cannot change stock or orders, issue refunds, send discounts, or submit chargebacks. It cannot invent missing delivery proof or guarantee an item stays available. |

Addresses and free-text notes are excluded from the answer shown to the agent; Zoho may include other fields in the response the connector receives. An authorized setup can permit fuller contact details for supported order lookups; see the [technical appendix](MERCHANT_SUMMARY_TECHNICAL.md).

## What could go wrong

- If Zoho's daily limit is reached, the lookup reports stock data is unavailable and tells the agent not to guess or retry that day.
- If Zoho is temporarily slow or unavailable, the lookup returns an error with retry guidance. An error is not treated as proof that an item or order is missing.
- If stock cannot be confirmed, the answer says “unknown”; it gives the agent no basis to promise availability.
- Stock can change after it is checked. The answer includes when it was read, and some recent answers may use a short-lived cached result.
- If shipment or invoice details are missing, the agent lists what is missing. Live Zoho package responses included a delivered-date field, but it was blank on the three test shipments checked. Even when populated, the date needs source validation; a date entered in Zoho does not by itself prove the carrier confirmed delivery. A carrier-tracking connection is the long-term route to independent delivery evidence.
- If required audit recording is unavailable, the lookup stops and reports an error.

## How we would know it is working

We would first measure the real share of eligible carts containing unavailable items. A fictional simulation checks that the stock rule suppresses carts labeled out of stock; its zero result is guaranteed by that rule and is not a merchant result. For a pilot, we would compare an agreed control and treatment, track stock freshness, tool failures, calls and discount cost, and measure conversion and contribution margin. For disputes, we would track missing evidence and the time operations spends assembling a case. See [the measurement plan](MEASUREMENT.md).

## What I need from you

- Show us how your team decides whether stock is safe to sell, including reservations and warehouse rules.
- Show where carrier-confirmed delivery events live and which carriers you use.
- Explain how a Razorpay order or payment is linked to a Zoho sales order.
- Provide an isolated test organization and approve the minimum read-only access.
- Agree on success measures, data access, and stop conditions before a pilot.

**Live status:** the read-only connector passed preflight, smoke, probe and 15/15 assertions against a throwaway Zoho org on a Premium trial. The invoice-present path, Free-plan quota behavior, carrier-confirmed delivery, and Agent Studio runtime integration remain unverified.
