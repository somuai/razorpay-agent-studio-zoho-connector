"""Tool specification exporter and verification utility (FR-5.1).

Exports FastMCP tools to mcp/tool_spec.json and verifies in CI that the
committed specification has not drifted from code.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from zoho_inventory_connector.mcp_server.server import mcp

SPEC_PATH = Path("mcp/tool_spec.json")


async def generate_spec_dict() -> dict[str, Any]:
    """Extract tool schemas from FastMCP instance."""
    tools = await mcp.list_tools()
    tools_list = []
    for t in sorted(tools, key=lambda x: x.name):
        tool_entry = {
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        }
        tools_list.append(tool_entry)

    return {
        "server_name": "zoho-inventory-connector",
        "version": "1.0.0",
        "description": "Read-only Zoho Inventory FastMCP Connector for Razorpay Agent Studio",
        "tool_count": len(tools_list),
        "tools": tools_list,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export or verify MCP tool specification.")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify committed tool_spec.json matches current code without writing.",
    )
    args = parser.parse_args()

    spec_data = asyncio.run(generate_spec_dict())
    formatted_json = json.dumps(spec_data, indent=2, sort_keys=True) + "\n"

    if args.verify:
        if not SPEC_PATH.exists():
            sys.stderr.write(
                f"Error: {SPEC_PATH} does not exist. Run 'make spec' to generate it.\n"
            )
            sys.exit(1)

        existing_content = SPEC_PATH.read_text(encoding="utf-8")
        if existing_content.strip() != formatted_json.strip():
            sys.stderr.write(
                f"Error: {SPEC_PATH} has drifted from registered tools in server.py! Run 'make spec' to update.\n"
            )
            sys.exit(1)
        sys.stderr.write(f"Verification successful: {SPEC_PATH} matches current code.\n")
        sys.exit(0)

    # Write out specification
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(formatted_json, encoding="utf-8")
    sys.stderr.write(f"Successfully generated {SPEC_PATH} with {spec_data['tool_count']} tools.\n")


if __name__ == "__main__":
    main()
