# Explore the MCP server with MCP Inspector

This is a manual inspection guide, not proof that a live Zoho organization has been tested. Use fictional mock fixtures offline. Do not place secrets in shell history, screenshots, or chat.

## Prerequisites

- Python 3.11+ and project dependencies (`make setup`).
- Node/npm and `npx` for the MCP Inspector package.
- For live mode only, an isolated Zoho Inventory test organization and environment variables from `.env.example`; never use real customer data.

## Mock server API

The Inspector is a separate MCP client window; it is not the terminal and it is not the Zoho API Console. The screenshot should show the Inspector connected to this server, its tool list, and one successful tool result. The offline steps below use fictional mock data. They prove the MCP interface can be explored, not that the Agent Studio runtime is connected.

1. In terminal A, start the local mock:

   ```bash
   make mock-server
   ```

   It is configured at `http://127.0.0.1:8000`; in another shell set `ZOHO_API_BASE_URL=http://127.0.0.1:8000/inventory/v1` and `ZOHO_ACCOUNTS_BASE_URL=http://127.0.0.1:8000` for the connector process. The server uses fictional seeded data.

2. Leave terminal A running. Open a second Terminal window (Terminal B) and paste the following block. The Inspector `-e` options pass fictional mock settings to its child server, including a separate temporary token-cache path so the project's real token file is not read. It starts the Inspector and its MCP server together; keep this window open while you inspect the browser tab that opens:

   ```bash
   npx --yes @modelcontextprotocol/inspector@latest \
     -e ZOHO_API_BASE_URL=http://127.0.0.1:8000/inventory/v1 \
     -e ZOHO_ACCOUNTS_BASE_URL=http://127.0.0.1:8000 \
     -e ZOHO_CLIENT_ID=mock_client_id \
     -e ZOHO_CLIENT_SECRET=mock_client_secret \
     -e ZOHO_REFRESH_TOKEN=mock_refresh_token \
     -e ZOHO_ORG_ID=org_kaveri_blr_001 \
     -e ZOHO_TOKEN_FILE=/tmp/fde-mock-inspector-token.json \
     .venv/bin/python -m zoho_inventory_connector.mcp_server.server
   ```

   The Inspector's local browser page can contain a one-session UI access token in its address bar. Crop the browser capture to the page content so the address bar is excluded. Do not type real Zoho credentials into Inspector; this section is mock mode. If your installed Node version is below the Inspector package's stated engine requirement, use a compatible Node version rather than an older Inspector release.

3. In the Inspector page, open **Tools**, confirm the connector's tools appear, select `get_stock_availability`, enter `{"skus_or_ids":["KHG-CUSH-001"]}`, and run it. Confirm the response shows a stock status, an as-of time, and cache state. The visible tool list plus that result is the mock Inspector screenshot. Do not label it as live.

4. Stop the Inspector process and mock server when done. Do not include unmasked order/customer information in a recording.

## Live mode (Zoho API path verified; Inspector live capture pending)

Only use the separate personal throwaway organization on the India data center. Never use an institutional organization. The author creates and populates this org manually and handles credentials outside chat. Use only the documented read scopes for the connector.

Follow [the live bring-up runbook](LIVE_BRINGUP.md): first run `make live-preflight` (it skips without credentials), exchange a fresh grant code with `make zoho-token`, then repeat preflight before running `make live-smoke`, `make live-probe`, and `make live-assert`. These commands are read-only and print masked summaries or field names/types. The probe writes shape-only findings to `docs/LIVE_FINDINGS.md`; it does not write to Zoho. The assertion uses expected fixture values in the local, gitignored `live_expected.yaml`. After an author-confirmed run, add only author-captured masked evidence under `docs/assets/`.

## What this check does not prove

Inspector confirms that an MCP client can discover and call a locally launched server. It does not establish current Zoho OAuth correctness, correct merchant-specific stock semantics, complete evidence, quota safety under shared usage, or Agent Studio runtime integration.
