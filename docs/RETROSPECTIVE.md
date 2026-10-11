# Retrospective

This is a retrospective on the fictional Kaveri Home Goods connector project. It draws on [field notes](FIELD_NOTES.md), [live findings](LIVE_FINDINGS.md), and the repository history. No merchant interview or production outcome is claimed.

## What worked

Starting from cart and dispute decisions produced two useful composed tools: stock availability and fulfillment evidence. The deterministic evaluation and local mock made policy behavior repeatable. The live run then gave evidence the mock could not: a package-list filter returned packages from other orders, and the fix was to verify exact order IDs locally before using evidence. The follow-up assertions passed after that correction.

The evaluation was also reframed after review showed its headline zero was guaranteed by the policy itself. The results now call it a mechanism check, disclose the fixture's assumed out-of-stock rate, and include sensitivity and quota scenarios rather than presenting simulated results as merchant impact.

## What failed or remains open

The live smoke exposed identifiers in HTTP request logs. The token cache was also not initially bound to the client credentials that issued its refresh token. Both were fixed with offline regression coverage, but neither issue appeared in the original mock path. Later intermittent connection failures were first reported too much like credential failures; transport and token diagnostics were added. The recorded timeouts coincided with failures on the author's network, though the evidence does not establish the cause of every failed request.

Invoice creation in the throwaway organization was blocked by its migration date, so the invoice-present path was exercised only in the mock. The live stock assertion results did not retain their source field or quantity, leaving the mapping between Zoho API fields and UI on-hand/available-for-sale values inconclusive.

## What I would do differently

I would make live-shaped edge cases part of the mock earlier: ignored filters, token-cache credential changes, and URL logging. A mock can exercise those failure modes, even though only a real API run revealed this particular filter behavior. I would also include the chosen stock source and quantity in safe assertion output so a passing status cannot hide which field drove it.

With a real merchant, I would first map the sellable-stock definition and order reservation behavior; then trace how packages and delivery dates are recorded, including the source and update delay. I would compare Zoho values with the merchant UI and carrier source before changing the stock rule or claiming delivery proof. Next I would baseline unavailable-cart rate, shared API quota, and dispute evidence gaps, then agree on a shadow pilot and stop criteria.
