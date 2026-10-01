# Agent capabilities and boundaries

This connector is a read-only context provider for the fictional Kaveri Home Goods scenario. Its outputs are evidence for an agent or operator; they are not authorization to take a business action.

| CAN | CANNOT | DEPENDS ON |
|---|---|---|
| Browse, retrieve, and search normalized item and sales-order records through the registered tools. | Create or edit an order, adjust stock, issue a refund, send a discount, or submit a chargeback response. | Zoho OAuth scopes, organization permissions, correct org/DC configuration, and live API compatibility. |
| Return an advisory stock classification from an explicit availability quantity, with a timestamp and cache indicator. | Guarantee real-time inventory, reserve units, or guarantee that a cart can be fulfilled at checkout. | Whether the merchant's configured availability field matches sellability; cache age; warehouse allocation and concurrent sales. Without a safe field or allocation rule, the result is `unknown`. |
| Assemble order, invoice, package, and shipment facts exposed by the configured Zoho responses and identify missing fields. | Produce proof Zoho or the connected systems do not hold; independently prove a parcel was delivered; determine dispute liability or outcome. | Whether packages, carrier, tracking, shipment and delivery dates are recorded and synchronized in Zoho. |
| Search for an order by an exact stored reference or contact email and explain the match basis. | Know that a Zoho order belongs to a Razorpay payment merely because an agent supplied an ID. | Whether the Razorpay order/payment identifier is stored on the Zoho order's `reference_number` or a supported custom field; uniqueness of the reference. The connector searches reference text and exact-compares returned orders; email search resolves a contact first, then searches that contact's orders. |
| Mask customer fields by default in sales-order projections. | Guarantee privacy in every surrounding log, agent, or deployment without a deployment-level review. | Correct use of `include_pii=false`, telemetry/audit configuration, access controls, and retention policy. |
| Return typed, actionable errors for several upstream/auth/quota conditions. | Guarantee availability when Zoho is down or its limits are reached. | Zoho quota is shared with every other consumer of the organization; exact plan caps and current error behavior require verification. |

### Safe agent policy

1. Check stock before deciding on a cart nudge. Treat `unknown`, stale data, or tool errors as “do not assume sellable”; hand off or retry according to the error guidance.
2. Suppressing an out-of-stock nudge or changing an offer remains a policy decision. The simulation policy is illustrative, not a live merchant rule.
3. For disputes, match the order first, verify the match, then retrieve evidence. A `complete` connector result means all fields in this connector's checklist were found, not that a network or issuer will accept a rebuttal.
4. Never turn missing data into a guessed tracking number, delivery event, or customer statement.
