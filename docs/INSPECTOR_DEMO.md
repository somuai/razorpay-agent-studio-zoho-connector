# Explore the MCP server with MCP Inspector

This is a manual inspection guide, not proof that a live Zoho organization has been tested. Use fictional mock fixtures offline. Do not place secrets in shell history, screenshots, or chat.

## Prerequisites

- Python 3.11+ and project dependencies (`make setup`).
- Node/npm and `npx` for the MCP Inspector package.
- For live mode only, an isolated Zoho Inventory test organization and environment variables from `.env.example`; never use real customer data.

## Mock server API

1. In terminal A, start the local mock:

   ```bash
   make mock-server
   ```

   It is configured at `http://127.0.0.1:8000`; in another shell set `ZOHO_API_BASE_URL=http://127.0.0.1:8000/inventory/v1` and `ZOHO_ACCOUNTS_BASE_URL=http://127.0.0.1:8000` for the connector process. The server uses fictional seeded data.

2. In terminal B, launch the stdio server with the mock endpoints and placeholder mock credentials:

   ```bash
   export ZOHO_API_BASE_URL=http://127.0.0.1:8000/inventory/v1
   export ZOHO_ACCOUNTS_BASE_URL=http://127.0.0.1:8000
   export ZOHO_CLIENT_ID=mock_client_id
   export ZOHO_CLIENT_SECRET=mock_client_secret
   export ZOHO_REFRESH_TOKEN=mock_refresh_token
   export ZOHO_ORG_ID=org_kaveri_blr_001
   npx @modelcontextprotocol/inspector .venv/bin/python -m zoho_inventory_connector.mcp_server.server
   ```

   The exact Inspector CLI invocation can vary by installed Inspector version. If your version opens a browser UI without launching the command, select **STDIO**, enter the command and arguments separately (`.venv/bin/python`, `-m`, `zoho_inventory_connector.mcp_server.server`), then connect.

3. Inspect the registered tools and schemas. Try `search_items` with `{"query":"Ikat","limit":5}` or inspect `get_stock_availability` with the fictional SKU `KHG-CUSH-001`. Use returned IDs for detail and evidence tools; mock IDs are bounded fixture IDs and production Zoho IDs are validated before request construction.

4. Stop the Inspector process and mock server when done. Do not include unmasked order/customer information in a recording.

## Live mode (not verified)

Only use an isolated test organization. Configure OAuth credentials and `ZOHO_ORG_ID`, `ZOHO_DC`, and token settings in the shell. Use read-only scopes only. No live credentials are present in this project workspace. Run `make live-smoke`; it skips cleanly when required credentials are absent and prints only masked summaries when configured. After an author-confirmed run, add only author-captured masked evidence under `docs/assets/`.

## What this check does not prove

Inspector confirms that an MCP client can discover and call a locally launched server. It does not establish current Zoho OAuth correctness, correct merchant-specific stock semantics, complete evidence, quota safety under shared usage, or Agent Studio runtime integration.
