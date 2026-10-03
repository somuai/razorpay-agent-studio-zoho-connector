# Screenshot capture guide

Capture only genuine output from commands run for this project. Do not generate, fake, edit, or composite a screenshot or terminal capture. The three offline captures must show mock/simulated output. The read-only Zoho command path passed on 2026-10-03. Author-supplied captures now cover mock test/demo, live smoke/assertion, one successful live Inspector tool call, and Zoho inventory/order screens. Separate preflight and probe captures remain unavailable, and the evaluation capture is stale. Do not imply Agent Studio runtime verification.

## Expected files

| Filename | Type | Must show |
|---|---|---|
| `tests_passing.png`, `.jpg`, or `.heic` | MOCK | Successful `make test` summary and coverage. |
| `eval_simulated.png`, `.jpg`, or `.heic` | MOCK / SIMULATED | Current `make eval` table and explicit simulation label. Recapture after any explanatory text change. |
| `demo_mock.png`, `.jpg`, or `.heic` | MOCK | `make demo` exercising stock and fulfillment evidence. |
| `live_preflight_masked.png`, `.jpg`, or `.heic` | LIVE | A genuine successful `make live-preflight` summary. |
| `live_smoke_masked.png`, `.jpg`, or `.heic` | LIVE | A genuine `make live-smoke` summary, tools, calls and cache status. |
| `live_probe_findings.png`, `.jpg`, or `.heic` | LIVE | Genuine probe finding statuses; no response values or identifiers. |
| `live_assert_masked.png`, `.jpg`, or `.heic` | LIVE | Genuine live assertions and per-row outcomes. |
| `mcp_inspector_live.png`, `.jpg`, or `.heic` | LIVE | MCP Inspector connected to the authorized throwaway org with a real tool result. |
| `live_pii_masking.png`, `.jpg`, or `.heic` | LIVE | A real `make live-pii-check` run showing masked order contact fields and the clean digit/email scan. |
| `zoho_inventory_fictional_records.png`, `.jpg`, or `.heic` | LIVE | Zoho Inventory UI showing only fictional test records needed to explain the test. Separate item and orders captures are acceptable if both are present and privacy-reviewed. |

## Exact commands and scan

Run offline captures from the repository root. Save command output outside the repository, scan it, then capture the Terminal window only after the scan passes. macOS may save JPEG depending on Screenshot settings; keep its real extension and use either PNG or JPG names listed above. Do not convert screenshots to satisfy the filenames.

```bash
set -o pipefail
make test 2>&1 | tee /tmp/tests_passing.txt
if grep -nE '[0-9]{8,}' /tmp/tests_passing.txt; then echo 'BLOCKED: inspect identifiers'; else echo 'PASS: no long digit strings'; fi
make eval 2>&1 | tee /tmp/eval_simulated.txt
if grep -nE '[0-9]{8,}' /tmp/eval_simulated.txt; then echo 'BLOCKED: inspect identifiers'; else echo 'PASS: no long digit strings'; fi
make demo 2>&1 | tee /tmp/demo_mock.txt
if grep -nE '[0-9]{8,}' /tmp/demo_mock.txt; then echo 'BLOCKED: inspect identifiers'; else echo 'PASS: no long digit strings'; fi
```

For a live Terminal capture, use a successful existing output from `.live_out/<run>/` or run the live command again if needed. Scan all output first; then in Terminal display the saved text without editing it, for example `cat .live_out/<run>/live-smoke.txt`, and use **Cmd+Shift+5 → Capture Selected Window** to capture the Terminal window. The command output must be genuine and must match the code version being submitted. Do not capture `.env`, the token helper prompt, or API Console. Live capture commands:

The Inspector capture serves a different purpose from Terminal output: it shows the Inspector connected to the server, discovering the registered tools, and displaying one tool call and response. Use `get_stock_availability` with a fictional SKU (input field `skus_or_ids`, for example `KHG-CUSH-001` in mock mode); keep the selected tool, input, and result visible. Ensure the organization and record IDs, account identity, and secrets are not in the window. The exact launch and connection steps are in [INSPECTOR_DEMO.md](../INSPECTOR_DEMO.md). Inspector output is MOCK if connected to the local fixture and must not use the live filename. For a live capture, use the authorized throwaway org and verify the tool result against Zoho. If the local token is unbound to the current client credentials, resolve that in the author's terminal before connecting live; do not capture an auth error as successful evidence. The Inspector URL can carry a one-session UI access token in its address bar; crop the screenshot to exclude browser chrome.

```bash
make live-preflight 2>&1 | tee /tmp/live_preflight.txt
make live-smoke 2>&1 | tee /tmp/live_smoke.txt
make live-probe 2>&1 | tee /tmp/live_probe.txt
make live-assert 2>&1 | tee /tmp/live_assert.txt
make live-pii-check 2>&1 | tee /tmp/live_pii_masking.txt
```

For each terminal output, run `grep -nE '[0-9]{8,}' /tmp/<capture>.txt` before screenshotting. A match blocks capture until the issue is understood; do not edit the output to make the scan pass. Then visually inspect the full image. For Inspector and Zoho UI captures, visually inspect at full size because text embedded in images may not be caught by a terminal scan.

Save reviewed originals under `docs/assets/` with the filenames in the table. Preserve originals when making a format copy for GitHub rendering; format conversion must not crop, redact, or otherwise change screenshot content. Never include the Zoho API Console. Crop or blur every email address, phone number, account ID, organization ID, Zoho record ID, and full tracking number. Keep only the last three tracking-number characters if the screenshot needs to demonstrate masking. Exclude tokens, grant codes, client IDs/secrets, authorization headers, `.env`, unrelated records and browser identity areas. If any secret is visible, discard the capture and take a clean one; do not modify an image to conceal altered live results.
