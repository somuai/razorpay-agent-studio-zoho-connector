# Three-minute walkthrough outline

Use this as a narration outline; speak only to what has been verified. All mock/evaluation data is fictional and simulated. Live mode is not yet verified.

## 0:00–0:30 — Problem and hypothesis

“This is a fictional Bangalore home-decor merchant. The asks are cart recovery and chargeback response. My hypothesis is that the cart agent lacks current stock context and that dispute operations need order and fulfillment facts assembled across records. I have not interviewed this merchant; this is a problem-led design assumption.”

## 0:30–0:55 — Boundary and assumptions

“The connector is read-only. The agent can inspect a product or order and ask for two composed answers: stock availability and fulfillment evidence. It cannot reserve stock, issue discounts, or file a dispute. The sellable-stock field and the payment-to-order link still need validation with a real merchant.”

## 0:55–1:35 — Demo path

Run `make demo`. It starts the fictional mock API and a separate MCP stdio server, then uses an MCP client to show one in-stock, one low-stock, and one out-of-stock result, one evidence result, and a forced 429/backoff path with per-tool retry telemetry. Identify every record as fictional mock data.

For a live demonstration, run the read-only smoke path only after credentials and a throwaway Zoho org are configured. `make live-smoke` is implemented and skips if the read credentials are absent. No live run is confirmed; do not claim live verification or display invented output.

## 1:35–2:10 — Simulated evaluation

Show `make eval` output/results and label every number **SIMULATED**. In the checked-in seed-42 outputs: the policy suppresses 54 out-of-stock nudges among 200 carts (27% baseline to 0% under the simulated connector-aware policy); 18 of 40 disputes have all checklist fields and 22 are partial; the cart simulation records 0.15 API calls per decision and 87.85% cache hits. The cart simulation estimates 3% of the modeled daily quota; both simulations together use 9.6% (96 mock API calls, including 1.65 calls per dispute case). These figures are not production outcomes or a measured uplift. The recorded latency uses a virtual clock and is not a runtime benchmark.

## 2:10–2:35 — Limits and safety

Call out cached stock, unknown sellability semantics, assumed order linkage, missing shipment evidence, shared Zoho quota, and the unverified live API shapes. Upstream failures remain errors rather than being reported as missing evidence.

## 2:35–3:00 — Next steps

Ask a real merchant to confirm stock semantics, identifier linkage, evidence locations, API quota, and safe data access. Run shadow mode, agree a control and kill criteria, and proceed only if freshness, completeness, and quota impact are acceptable.
