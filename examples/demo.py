"""Offline MCP transport walkthrough against a local fictional Zoho API."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx
from mcp.client.stdio import StdioServerParameters, stdio_client

from mcp import ClientSession

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tool_payload(result: Any) -> dict[str, Any]:
    """Decode the JSON payload returned by the stdio MCP server."""
    for content in result.content:
        if getattr(content, "text", None):
            try:
                value = json.loads(content.text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    raise RuntimeError("MCP tool returned no JSON object")


def _free_local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_for_mock(process: asyncio.subprocess.Process, base_url: str) -> None:
    async with httpx.AsyncClient(timeout=0.25) as client:
        for _ in range(80):
            if process.returncode is not None:
                raise RuntimeError("Local fictional mock exited before startup")
            try:
                response = await client.get(f"{base_url}/docs")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.05)
    raise RuntimeError("Local fictional mock did not become ready")


def _telemetry_summary(text: str) -> dict[str, int]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        marker = "[TELEMETRY] "
        if marker not in line:
            continue
        try:
            event = json.loads(line.split(marker, 1)[1])
        except json.JSONDecodeError:
            continue
        events.append(event)
    return {
        "tool_events": len(events),
        "upstream_retries": sum(int(event.get("retries", 0)) for event in events),
        "throttled_tool_calls": sum(bool(event.get("throttled")) for event in events),
        "tool_errors": sum(event.get("status") == "error" for event in events),
    }


async def run_demo() -> None:
    port = _free_local_port()
    mock_root = f"http://127.0.0.1:{port}"
    api_root = f"{mock_root}/inventory/v1"
    python = sys.executable
    mock_process = await asyncio.create_subprocess_exec(
        python,
        "-m",
        "uvicorn",
        "mock_zoho.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "error",
        cwd=REPO_ROOT,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await _wait_for_mock(mock_process, mock_root)
        env = os.environ.copy()
        env.update(
            {
                "ZOHO_API_BASE_URL": api_root,
                "ZOHO_ACCOUNTS_BASE_URL": mock_root,
                "ZOHO_CLIENT_ID": "mock_client_id",
                "ZOHO_CLIENT_SECRET": "mock_client_secret",
                "ZOHO_REFRESH_TOKEN": "mock_refresh_token",
                "ZOHO_ORG_ID": "org_kaveri_blr_001",
                "ZOHO_DC": "in",
            }
        )
        params = StdioServerParameters(
            command=python,
            args=["-m", "zoho_inventory_connector.mcp_server.server"],
            cwd=REPO_ROOT,
            env=env,
        )
        scenarios = (
            ("in_stock", "KHG-CUSH-001"),
            ("low_stock", "KHG-DHOK-011"),
            ("out_of_stock", "KHG-SILK-019"),
        )
        print("OFFLINE DEMO — fictional Zoho data via MCP stdio transport")
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as captured_stderr:
            async with stdio_client(params, errlog=captured_stderr) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    for label, sku in scenarios:
                        result = _tool_payload(
                            await session.call_tool(
                                "get_stock_availability",
                                {"skus_or_ids": [sku], "bypass_cache": True},
                            )
                        )
                        row = (result.get("items") or [{}])[0]
                        print(
                            json.dumps(
                                {
                                    "scenario": label,
                                    "sku": sku,
                                    "decision": row.get("status", "error"),
                                    "quantity": row.get("quantity_sellable"),
                                    "as_of": result.get("as_of"),
                                    "cached": result.get("cached"),
                                },
                                sort_keys=True,
                            )
                        )

                    evidence = _tool_payload(
                        await session.call_tool(
                            "get_order_fulfillment_evidence",
                            {"salesorder_id": "so_2001", "bypass_cache": True},
                        )
                    )
                    print(
                        json.dumps(
                            {
                                "scenario": "dispute_evidence",
                                "completeness": evidence.get("completeness"),
                                "missing_fields": evidence.get("missing_fields", []),
                            },
                            sort_keys=True,
                        )
                    )

                    partial_evidence = _tool_payload(
                        await session.call_tool(
                            "get_order_fulfillment_evidence",
                            {"salesorder_id": "so_2035", "bypass_cache": True},
                        )
                    )
                    print(
                        json.dumps(
                            {
                                "scenario": "partial_dispute_evidence",
                                "completeness": partial_evidence.get("completeness"),
                                "missing_fields": partial_evidence.get("missing_fields", []),
                            },
                            sort_keys=True,
                        )
                    )

                    async with httpx.AsyncClient(timeout=2.0) as client:
                        await client.post(
                            f"{mock_root}/mock/faults/configure",
                            json={"inject_429_rate_limit": True, "retry_after_seconds": 0.01},
                        )
                    throttled = _tool_payload(
                        await session.call_tool(
                            "get_stock_availability",
                            {"skus_or_ids": ["KHG-CUSH-001"], "bypass_cache": True},
                        )
                    )
                    print(
                        json.dumps(
                            {
                                "scenario": "throttle_backoff",
                                "error": throttled.get("error"),
                                "retryable": throttled.get("retryable"),
                            },
                            sort_keys=True,
                        )
                    )
            captured_stderr.seek(0)
            summary = _telemetry_summary(captured_stderr.read())
        print(json.dumps({"scenario": "metrics_summary", **summary}, sort_keys=True))
    finally:
        mock_process.terminate()
        try:
            await asyncio.wait_for(mock_process.wait(), timeout=3.0)
        except TimeoutError:
            mock_process.kill()
            await mock_process.wait()


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
