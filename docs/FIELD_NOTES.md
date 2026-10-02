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
| 2026-10-02 · current working tree (uncommitted) | Handoff | Added this handoff log, fresh mock evidence, screenshot inventory and submission note. No live command or network call was made for these changes. |

## Problems found and fixed

| Problem | Evidence and response | Remaining limit |
|---|---|---|
| HTTP request logs exposed Zoho identifiers during live smoke. | The finding is recorded in [LIVE_FINDINGS.md](LIVE_FINDINGS.md); commit `2cc5ba4` added redaction and `f0a03ad` added transport/request-path regression coverage. | Post-fix live output has not been rechecked; screenshot safety after the fix is not confirmed. |
| Token cache was not bound to the client credentials that issued its refresh token. | Commit `4083ea0` requires a matching credential fingerprint and preserves refresh-token rotation. Offline tests cover changed credentials and persistence. | A fresh live token exchange and refresh after the fix have not been confirmed. |
| Later transport failures were traced to a network outage on the author's connection. | During the same period, the author reported ping, DNS and GitHub timeouts; [LIVE_FINDINGS.md](LIVE_FINDINGS.md) also records earlier Python connect timeouts. Together these support a network-side outage rather than a Zoho authentication response. | They do not prove the cause of every individual failed Zoho request. No new connectivity test was run for this handoff. |
| Invoice creation was blocked by the throwaway org's migration date. | The author reported the Zoho UI rejected invoice creation because of the org migration date. The invoice-present path therefore remains mock-tested only. | No setting or date was changed to bypass the restriction. |

## Decisions and trade-offs

| Decision | Why | Trade-off |
|---|---|---|
| Keep the connector read-only. | Agents can inspect facts without changing merchant inventory or orders. | It cannot repair missing or incorrect records. |
| Compose sellability and evidence tools around agent decisions. | A bounded decision result is more useful than exposing raw endpoints alone. | Zoho-specific detail is hidden behind projections. |
| Return `unknown` or `not_available` when fields are missing. | Missing data must not become a guess. | More cases require a human or another source. |
| Cache access and stock data, with explicit expiry and provenance. | Reduces avoidable upstream calls and preserves freshness context. | Cache behavior depends on catalog shape and traffic; separate processes may refresh concurrently. |
| Treat Zoho shipment fields as fulfillment evidence, not delivery proof. | A shipment record has no documented delivered-at timestamp. | Carrier-confirmed proof requires another integration. |
| Make logs identifier-safe and audit events separate. | Diagnosis should not expose raw credentials or unnecessary record identifiers. | Redaction can reduce detail; live screenshot safety still needs a post-fix run. |

## Metrics scoreboard

| Measure | Result | Source |
|---|---:|---|
| Tests | 147 passed | `make test`; raw output: [make-test.txt](evidence/make-test.txt) |
| Source coverage | 90.56% | `make test`; raw output: [make-test.txt](evidence/make-test.txt) |
| Lint | Passed; 99 files formatted | `make lint` |
| Typecheck | Passed; 31 source files | `make typecheck` |
| MCP tools | 8 registered and spec verified | `make spec` |
| Cart mechanism check | 54/200 baseline unavailable nudges; connector-aware 0/200 by construction | `make eval`; raw output: [make-eval.txt](evidence/make-eval.txt) |
| Sensitivity rates | 2%, 5%, 10%, 27% assumed out-of-stock shares | `make eval`; raw output: [make-eval.txt](evidence/make-eval.txt) |
| Quota feasibility | Warm 0.15 calls/decision: 6,666 / 3,333 / 1,666; cold 1.235: 809 / 404 / 202 | `make eval`; raw output: [make-eval.txt](evidence/make-eval.txt) |
| Dispute evidence | 18/40 complete for six Zoho-documented fields; schema-faithful delivery proof 0/40 | `make eval`; raw output: [make-eval.txt](evidence/make-eval.txt) |
| Demo | 6 tool events, 3 retries, 1 throttled tool call | `make demo`; raw output: [make-demo.txt](evidence/make-demo.txt) |
| Confirmed successful live calls reported before this handoff | Preflight 8; all-tools smoke 14; later total is unknown | [LIVE_FINDINGS.md](LIVE_FINDINGS.md), [DONE_CHECKLIST.md](DONE_CHECKLIST.md). These are historical observations, not new calls. |
| Documentation files | See `find docs -type f | wc -l` at the bottom of [DONE_CHECKLIST.md](DONE_CHECKLIST.md). | Count includes evidence and this log. |

The evidence text files begin with `MOCK / SIMULATED`, the command, date, and current base commit hash. Their long-digit scan returned no matches. The evaluation stdout from two fresh runs compared byte-for-byte identical.

## What is not verified

Live verification is still pending. One earlier preflight and one all-tools smoke succeeded, but the live probe and live assertion have not run. The API fields corresponding to the manual UI stock quantities are unknown. The invoice-present path was not exercised live, and shipment delivery proof needs a carrier source. The Premium-trial run did not test free-plan quota behavior. No live screenshots are present.
