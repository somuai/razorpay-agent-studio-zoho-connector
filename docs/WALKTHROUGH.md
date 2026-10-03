# Ten-minute reviewer tour

This is a written tour. No video or recording is required. All offline examples use fictional mock data; evaluation values are **SIMULATED**. The read-only Zoho preflight, smoke, probe and assertions passed on 2026-10-03; no Agent Studio runtime integration or live screenshots are included.

## 1. Read the handoff (2 minutes)

Start with the README opening: fictional merchant ask, narrower hypothesis, findings and live status. Check that the manual stock comparison is labeled as a UI observation and not an API result. The connector field mapping remains unconfirmed.

## 2. Run the three offline commands (5 minutes)

From the repository root, with Python 3.11+ and `uv` installed:

```bash
make setup
make eval
make demo
```

`make eval` reproduces the deterministic fictional metrics. `make demo` starts the local mock and demonstrates stock decisions, fulfillment evidence and the throttling path. `make setup` prepares the environment. These commands do not verify real Zoho behavior.

## 3. Read these four documents (3 minutes)

1. [Merchant summary](MERCHANT_SUMMARY.md) — what the agent can see, what is masked, what it cannot do, and failure handling.
2. [Measurement plan](MEASUREMENT.md) — the first merchant measurement, instrumentation, control design and kill criteria.
3. [API notes](API_NOTES.md) — documented Zoho behavior, limits and unresolved questions.
4. [Live findings](LIVE_FINDINGS.md) — observed live evidence and what remains inconclusive.

End with the boundary: this is an MCP-compatible, read-only connector prototype. Private Agent Studio connector loading and credential storage are assumptions, and no integration inside Razorpay's runtime is claimed.
