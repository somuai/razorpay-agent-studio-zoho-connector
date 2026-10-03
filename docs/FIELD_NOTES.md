# FDE field notes

A dated engineering log of the decisions and evidence in this repository. Dates and commit hashes come from `git log --date=short`; run outputs come from the commands named in the scoreboard. The merchant and all mock records are fictional.

## Timeline

| Date / commit | FDE loop step | What changed or was learned |
|---|---|---|
| 2026-10-02 · `0f9f491` | Stated ask and hypothesis | Framed the assignment around cart recovery and dispute response for fictional Kaveri Home Goods. The narrower hypothesis is that cart decisions lack a sellable-stock signal and dispute work needs fulfillment facts assembled across records. |
| 2026-10-02 · `5d0068b` | Research and foundation | Recorded Zoho API sources and unresolved facts; created the fictional mock and fixtures. |
| 2026-10-02 · `30f4734` | Design | Built a GET-only client, rate controls, circuit handling and cache around read-only Zoho access. |
| 2026-10-02 · `8492fe2` | Build | Added composed stock/evidence services, agent-facing projections and eight MCP tools. |
| 2026-10-02 · `8750044` | Measurement | Added deterministic cart and dispute evaluation. The fixture's baseline out-of-stock share is an assumption; the zero-aware result follows directly from policy. |
| 2026-10-02 · `a0b2d92`, `e2f60bb`, `a63b8de` | Live bring-up preparation | Added preflight, expected-data assertions, and a read-only shape probe. These tools are implemented; the probe and assertion have not been run against Zoho. |
| 2026-10-02 · `2cc5ba4`, `f0a03ad`, `4083ea0` | Live learning and fixes | A live smoke exposed identifiers in HTTP request logs; redaction and request-integrity tests followed. Later token work bound cached tokens to their issuing client credentials and improved diagnostics. |
| 2026-10-02 · `6daf5c0` | Handoff | Added the FDE field notes, mock evidence, screenshot inventory and submission note. That documentation change itself made no live API call. |
| 2026-10-03 · `d55bd8c` and current project changes | Live bring-up | Exchanged a read-scope grant and ran preflight, all eight smoke tools, the read-only probe, and expected-data assertions against the throwaway India org. The final saved burst passed the preflight, smoke, probe and assertion steps. |
| 2026-10-03 · current project changes | Assertion failure and diagnosis | The first live assertion run failed because the package list returned unrelated orders despite its sales-order filter. Taking the first returned package could have joined another order's shipment evidence to the dispute case. |
| 2026-10-03 · current project changes | Fix and re-measure | Added exact local `salesorder_id` filtering and package-detail reads for sparse shipment data, then reran the live assertions: 15/15 rows passed. The offline regression test is `test_dispute_service_ignores_packages_for_other_orders`. The live probe also showed `shipment_delivered_date`, blank on three checked shipments; source semantics remain open. |

## Problems found and fixed

| Problem | Evidence and response | Remaining limit |
|---|---|---|
| HTTP request logs exposed Zoho identifiers during live smoke. | The finding is recorded in [LIVE_FINDINGS.md](LIVE_FINDINGS.md); commit `2cc5ba4` added redaction and `f0a03ad` added transport/request-path regression coverage. The later burst's step outputs all passed the identifier/privacy scan. | Keep future outputs and screenshots subject to the capture guide's privacy scan. |
| Token cache was not bound to the client credentials that issued its refresh token. | Commit `4083ea0` requires a matching credential fingerprint and preserves refresh-token rotation. A fresh grant exchange and subsequent live preflight passed against the throwaway org. | This confirms the tested client's current credential binding; production multi-tenant rotation behavior still needs deployment validation. |
| Package lookup could attach another order's package. | The first live assertion run failed: `GET /packages?salesorder_id=…` returned four rows per lookup, including packages belonging to other orders. The old service could select an unrelated package and tracking number as dispute evidence. The connector now exact-filters `salesorder_id` before using a package, and the mixed-order regression is covered by `test_dispute_service_ignores_packages_for_other_orders` in `tests/test_services.py`. The subsequent live assertion passed 15/15 rows. | Pagination or a verified server-side filter is still needed for larger catalogs. |
| Delivery-date interpretation was too broad. | Live package details included the candidate field `shipment_delivered_date`, but it was blank on all three matching shipped test records. This corrects the earlier reading that the Zoho response had no delivered-date field. The field's source is not established by the response shape. | A populated value entered in Zoho is not automatically carrier-confirmed evidence. Verify its source and timing with operations and the carrier. |
| Sparse nested shipment data hid populated shipment fields. | Matching package detail included `status`, `carrier`, `tracking_number`, `shipping_date`, and `shipment_delivered_date`; the order-level embedded object was sparse. The service fetches package detail when key evidence fields are missing and maps Zoho's observed date aliases. | Carrier-source semantics for a populated delivery date remain unverified. |
| Later transport failures occurred during a period when the author's connection was failing. | The author reported ping, DNS and GitHub timeouts, and prior Zoho requests timed out; a later `make live-burst` succeeded after both unauthenticated Zoho hosts answered. | This sequence supports intermittent connectivity but does not prove the cause of every failed request. |
| Invoice creation was blocked by the throwaway org's migration date. | The author reported the Zoho UI rejected invoice creation because of the org migration date. The invoice-present path therefore remains mock-tested only. | No setting or date was changed to bypass the restriction. |

## Decisions and trade-offs

| Decision | Why | Trade-off |
|---|---|---|
| Keep the connector read-only. | Agents can inspect facts without changing merchant inventory or orders. | It cannot repair missing or incorrect records. |
| Compose sellability and evidence tools around agent decisions. | A bounded decision result is more useful than exposing raw endpoints alone. | Zoho-specific detail is hidden behind projections. |
| Return `unknown` or `not_available` when fields are missing. | Missing data must not become a guess. | More cases require a human or another source. |
| Cache access and stock data, with explicit expiry and provenance. | Reduces avoidable upstream calls and preserves freshness context. | Cache behavior depends on catalog shape and traffic; separate processes may refresh concurrently. |
| Treat Zoho shipment fields as fulfillment evidence, not automatically carrier-confirmed delivery proof. | The live response had `shipment_delivered_date`, blank on the three checked shipments; the field source and semantics are unknown. | Ask whether staff enter delivered status/date manually or from carrier sync, and integrate the authoritative carrier source when needed. |
| Make logs identifier-safe and audit events separate. | Diagnosis should not expose raw credentials or unnecessary record identifiers. | Redaction can reduce detail; continue scanning future command outputs and captures. |

## Metrics scoreboard

| Measure | Result | Source |
|---|---:|---|
| Tests | 168 passed | `make test` run on 2026-10-03 in the current project tree |
| Source coverage | 90.67% | `make test` run on 2026-10-03 in the current project tree |
| Lint | Passed; 102 files formatted | `make lint` |
| Typecheck | Passed; 31 source files | `make typecheck` |
| MCP tools | 8 registered and spec verified | `make spec` |
| Cart mechanism check | 54/200 baseline unavailable nudges; connector-aware 0/200 by construction | `make eval`; raw output: [make-eval.txt](evidence/make-eval.txt) |
| Sensitivity rates | 2%, 5%, 10%, 27% assumed out-of-stock shares | `make eval`; raw output: [make-eval.txt](evidence/make-eval.txt) |
| Quota feasibility | Warm 0.15 calls/decision: 6,666 / 3,333 / 1,666; cold 1.235: 809 / 404 / 202 | `make eval`; raw output: [make-eval.txt](evidence/make-eval.txt) |
| Dispute evidence | 18/40 complete for six Zoho-documented fields; schema-faithful delivery proof 0/40 | `make eval`; raw output: [make-eval.txt](evidence/make-eval.txt) |
| Demo | 6 tool events, 3 retries, 1 throttled tool call | `make demo`; raw output: [make-demo.txt](evidence/make-demo.txt) |
| Final live preflight / smoke | Passed; 7 / 10 upstream calls | `make live-burst`; `.live_out/20261003T083016Z/` (gitignored, output privacy scan passed) |
| Live probe | 16 HTTP attempts across 16 logical GET probes | `make live-burst`; saved probe output and [LIVE_FINDINGS.md](LIVE_FINDINGS.md) |
| Live assertion | 15/15 rows passed after fixing first-run failure; 31 HTTP attempts | `make live-burst`; saved assertion output and [LIVE_FINDINGS.md](LIVE_FINDINGS.md) |
| Documentation files | See `find docs -type f | wc -l` at the bottom of [DONE_CHECKLIST.md](DONE_CHECKLIST.md). | Count includes evidence and this log. |

The offline evidence text files begin with `MOCK / SIMULATED`, the command, date, and base commit hash. The final live-burst output is retained only in the gitignored `.live_out/` directory and every step scanned `SAFE TO SCREENSHOT`. Evaluation stdout from two current mock runs compared byte-for-byte identical.

## What is not verified

The read-only Zoho path passed preflight, all eight tools in smoke, probe, and all 15 assertion rows on 2026-10-03. The first assertion run failed and exposed the cross-order package bug; exact filtering and detail fallback fixed it, and the rerun passed. The manual UI stock quantities are still not mapped to API fields. Invoice-present remains mock-only because the throwaway org's migration date blocked invoice creation. A `shipment_delivered_date` field appeared in live responses but was blank on the three checked shipments; whether a populated value is staff-entered or carrier-sourced is not verified. The Premium-trial run did not test free-plan quota behavior or Agent Studio runtime loading. Author-supplied screenshots now cover tests, demo, smoke, assertions, one live Inspector call, and the Zoho UI; the evaluation capture is stale, and preflight/probe screenshots are unavailable.
