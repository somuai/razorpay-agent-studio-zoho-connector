# Screenshot capture guide

Capture only genuine output from commands run for this project. Do not generate, fake, edit, or composite a screenshot or terminal capture. The three offline captures must show mock/simulated output. The six live captures may be added only after the corresponding real run occurs; live status remains unverified until the author confirms it.

## Expected files

| Filename | Type | Must show |
|---|---|---|
| `tests_passing.png` | MOCK | Successful `make test` summary and coverage. |
| `eval_simulated.png` | MOCK / SIMULATED | `make eval` table and explicit simulation label. |
| `demo_mock.png` | MOCK | `make demo` exercising stock and fulfillment evidence. |
| `live_preflight_masked.png` | LIVE | A genuine successful `make live-preflight` summary. |
| `live_smoke_masked.png` | LIVE | A genuine `make live-smoke` summary, tools, calls and cache status. |
| `live_probe_findings.png` | LIVE | Genuine probe finding statuses; no response values or identifiers. |
| `live_assert_masked.png` | LIVE | Genuine live assertions and per-row outcomes. |
| `mcp_inspector_live.png` | LIVE | MCP Inspector connected to the authorized throwaway org with a real tool result. |
| `zoho_inventory_fictional_records.png` | LIVE | Zoho Inventory UI showing only the fictional test records needed to explain the test. |

## Exact commands and scan

Run offline captures from the repository root. Save command output outside the repository, scan it, then capture the terminal only after the scan passes:

```bash
set -o pipefail
make test 2>&1 | tee /tmp/tests_passing.txt
if grep -nE '[0-9]{8,}' /tmp/tests_passing.txt; then echo 'BLOCKED: inspect identifiers'; else echo 'PASS: no long digit strings'; fi
make eval 2>&1 | tee /tmp/eval_simulated.txt
if grep -nE '[0-9]{8,}' /tmp/eval_simulated.txt; then echo 'BLOCKED: inspect identifiers'; else echo 'PASS: no long digit strings'; fi
make demo 2>&1 | tee /tmp/demo_mock.txt
if grep -nE '[0-9]{8,}' /tmp/demo_mock.txt; then echo 'BLOCKED: inspect identifiers'; else echo 'PASS: no long digit strings'; fi
```

Live capture commands are included for the author when a real run is authorized and ready. They are instructions only; do not run them as part of offline documentation work:

```bash
make live-preflight 2>&1 | tee /tmp/live_preflight.txt
make live-smoke 2>&1 | tee /tmp/live_smoke.txt
make live-probe 2>&1 | tee /tmp/live_probe.txt
make live-assert 2>&1 | tee /tmp/live_assert.txt
```

For each terminal output, run `grep -nE '[0-9]{8,}' /tmp/<capture>.txt` before screenshotting. A match blocks capture until the issue is understood; do not edit the output to make the scan pass. Then visually inspect the full image. For Inspector and Zoho UI captures, visually inspect at full size because text embedded in images may not be caught by a terminal scan.

Save reviewed images under `docs/assets/` with exactly the filenames in the table. Never include the Zoho API Console. Crop or blur every email address, phone number, account ID, organization ID, Zoho record ID, and full tracking number. Keep only the last three tracking-number characters if the screenshot needs to demonstrate masking. Exclude tokens, grant codes, client IDs/secrets, authorization headers, `.env`, unrelated records and browser identity areas. If any secret is visible, discard the capture and take a clean one; do not modify an image to conceal altered live results.
