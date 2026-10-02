"""FastMCP server exposing 8 read-only Zoho Inventory tools (FR-5, FR-6, FR-7, NFR-8)."""

import json
import os
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Annotated, Any, TypeVar

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.client.errors import (
    AuditSinkError,
    ConnectorError,
    InputValidationError,
    UpstreamError,
)
from zoho_inventory_connector.client.parsing import (
    parse_optional_upstream_float,
    parse_upstream_float,
)
from zoho_inventory_connector.client.query_builder import ValidatedQueryBuilder
from zoho_inventory_connector.events.audit import AuditEvent, default_audit_logger
from zoho_inventory_connector.events.emitter import ToolExecutionEvent, default_emitter
from zoho_inventory_connector.events.logging_safety import new_request_id
from zoho_inventory_connector.models.order import SalesOrderProjection
from zoho_inventory_connector.ratelimit.metrics import ACTIVE_TOOL_CALL_METRICS, ToolCallMetrics
from zoho_inventory_connector.services.dispute_service import DisputeService
from zoho_inventory_connector.services.stock_service import StockService

MAX_OUTPUT_BYTES = 8192  # 8 KB hard cap for LLM context safety (FR-6.2)


def _dict_rows(value: object) -> list[dict[str, Any]]:
    """Keep schema-drifted collection values from crashing a tool projection."""
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


# Initialize FastMCP Server
mcp = FastMCP("zoho-inventory-connector")

# Global singleton dependencies (lazily initialized or injected for testing)
_client: ZohoClient | None = None
_stock_service: StockService | None = None
_dispute_service: DisputeService | None = None

_ToolCallable = TypeVar("_ToolCallable", bound=Callable[..., Awaitable[dict[str, Any]]])


def _capture_tool_metrics(function: _ToolCallable) -> _ToolCallable:
    """Attach request-local retry/throttle counters to emitted tool events."""

    @wraps(function)
    async def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        call_metrics = ToolCallMetrics()
        token = ACTIVE_TOOL_CALL_METRICS.set(call_metrics)
        try:
            try:
                return await function(*args, **kwargs)
            except AuditSinkError as error:
                default_emitter.emit(
                    ToolExecutionEvent.create(
                        tool=error.tool,
                        status="error",
                        latency_ms=0.0,
                        http_status=None,
                        zoho_code=None,
                        result_count=0,
                        request_id=error.request_id,
                    )
                )
                return error.to_dict()
        finally:
            ACTIVE_TOOL_CALL_METRICS.reset(token)

    return wrapped  # type: ignore[return-value]


def get_client() -> ZohoClient:
    """Retrieve or initialize global ZohoClient from environment."""
    global _client
    if _client is None:
        client_id = os.environ.get("ZOHO_CLIENT_ID", "")
        client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "")
        refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN")
        org_id = os.environ.get("ZOHO_ORG_ID", "")
        dc = os.environ.get("ZOHO_DC", "in")
        accounts_override = os.environ.get("ZOHO_ACCOUNTS_BASE_URL")
        api_override = os.environ.get("ZOHO_API_BASE_URL")
        token_file = os.environ.get("ZOHO_TOKEN_FILE", ".zoho_token.json")

        tm = TokenManager(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            token_file=token_file,
            dc=dc,
            accounts_base_url=accounts_override,
        )
        _client = ZohoClient(
            token_manager=tm,
            org_id=org_id,
            base_url_override=api_override,
        )
    return _client


def set_client(client: ZohoClient) -> None:
    """Set global ZohoClient (for testing and dependency injection)."""
    global _client, _stock_service, _dispute_service
    _client = client
    _stock_service = StockService(client)
    _dispute_service = DisputeService(client)


def get_stock_service() -> StockService:
    global _stock_service
    if _stock_service is None:
        _stock_service = StockService(get_client())
    return _stock_service


def get_dispute_service() -> DisputeService:
    global _dispute_service
    if _dispute_service is None:
        _dispute_service = DisputeService(get_client())
    return _dispute_service


def _enforce_output_cap(payload: dict[str, Any], list_key: str | None = None) -> dict[str, Any]:
    """Ensure serialized response does not exceed 8 KB limit (FR-6.2)."""
    payload = dict(payload)
    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized.encode("utf-8")) <= MAX_OUTPUT_BYTES:
        return payload

    # If exceeding, truncate list if present
    payload["truncated"] = True
    payload["truncation_guidance"] = (
        "Response exceeded 8 KB context safety cap. Results were truncated. "
        "Narrow your query parameters or specify a smaller 'limit' or 'per_page'."
    )

    if list_key and list_key in payload and isinstance(payload[list_key], list):
        items = list(payload[list_key])
        while (
            items
            and len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_OUTPUT_BYTES
        ):
            items.pop()
        payload[list_key] = items

    # A single unusually large projected field can exceed the cap even after a
    # list is emptied. Return a small, deterministic envelope in that case.
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_OUTPUT_BYTES:
        payload = {
            "truncated": True,
            "truncation_guidance": (
                "Response exceeded 8 KB context safety cap. Narrow the query or request fewer fields."
            ),
        }
        if list_key:
            payload[list_key] = []

    return payload


# ==============================================================================
# MCP Tool 1: list_items
# ==============================================================================
@mcp.tool(
    name="list_items",
    description=(
        "Browse the merchant's Zoho Inventory catalog with pagination. "
        "Use this tool when you need an overview of products, item IDs, and active statuses. "
        "DO NOT use this for real-time cart-nudge stock decisions (use 'get_stock_availability' instead)."
    ),
)
@_capture_tool_metrics
async def list_items(
    page: Annotated[int, Field(ge=1, le=1000)] = 1,
    per_page: Annotated[int, Field(ge=1, le=50)] = 50,
    status: str | None = None,
) -> dict[str, Any]:
    req_id = new_request_id()
    default_audit_logger.record(
        AuditEvent.create(
            "list_items", {"page": page, "per_page": per_page, "status": status}, req_id
        )
    )

    start_mono = get_client().clock.monotonic()
    try:
        p, pp = ValidatedQueryBuilder.validate_pagination(page, per_page, max_per_page=50)
        st = (
            ValidatedQueryBuilder.validate_status(
                status, allowed={"active", "inactive", "all"}, field_name="status"
            )
            if status
            else None
        )

        params: dict[str, str] = {"page": str(p), "per_page": str(pp)}
        if st and st != "all":
            params["status"] = st

        data, is_cached, as_of = await get_client().get("/items", params=params, cache_ttl=300.0)
        items_raw = _dict_rows(data.get("items", []))
        page_ctx = data.get("page_context", {})
        if not isinstance(page_ctx, dict):
            page_ctx = {}

        items_projected = [
            {
                "item_id": str(it.get("item_id")),
                "name": str(it.get("name")),
                "sku": str(it.get("sku")),
                "status": str(it.get("status")),
                "rate": parse_upstream_float(it.get("rate"), "rate"),
                "stock_on_hand": parse_optional_upstream_float(
                    it.get("stock_on_hand"), "stock_on_hand"
                ),
                "actual_available_stock": parse_optional_upstream_float(
                    it.get("actual_available_stock"), "actual_available_stock"
                ),
                "reorder_level": parse_optional_upstream_float(
                    it.get("reorder_level"), "reorder_level"
                ),
            }
            for it in items_raw
        ]

        result = {
            "items": items_projected,
            "page": p,
            "per_page": pp,
            "has_more": bool(page_ctx.get("has_more_page", False)),
            "next_page": p + 1 if page_ctx.get("has_more_page") else None,
            "as_of": as_of,
            "cached": is_cached,
            "truncated": False,
        }
        res_capped = _enforce_output_cap(result, list_key="items")

        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="list_items",
                status="success",
                latency_ms=latency,
                cache_hit=is_cached,
                result_count=len(items_projected),
                request_id=req_id,
            )
        )
        return res_capped

    except ConnectorError as err:
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="list_items",
                status="error",
                latency_ms=latency,
                zoho_code=err.zoho_code,
                http_status=err.http_status,
                request_id=req_id,
            )
        )
        return err.to_dict()


# ==============================================================================
# MCP Tool 2: get_item
# ==============================================================================
@mcp.tool(
    name="get_item",
    description=(
        "Retrieve comprehensive projection of a single inventory item by numeric item_id. "
        "Use this tool when you need granular product details (price, description, unit). "
        "DO NOT use this for multi-item cart availability decisions (use 'get_stock_availability')."
    ),
)
@_capture_tool_metrics
async def get_item(item_id: str) -> dict[str, Any]:
    req_id = new_request_id()
    default_audit_logger.record(AuditEvent.create("get_item", {"item_id": item_id}, req_id))
    start_mono = get_client().clock.monotonic()

    try:
        clean_id = ValidatedQueryBuilder.validate_numeric_id(item_id, field_name="item_id")
        data, is_cached, as_of = await get_client().get(f"/items/{clean_id}", cache_ttl=300.0)
        it = data.get("item", {})
        if not isinstance(it, dict):
            it = {}

        result = {
            "item_id": str(it.get("item_id")),
            "name": str(it.get("name")),
            "sku": str(it.get("sku")),
            "status": str(it.get("status")),
            "rate": parse_upstream_float(it.get("rate"), "rate"),
            "currency_code": str(it.get("currency_code", "INR")),
            "stock_on_hand": parse_optional_upstream_float(
                it.get("stock_on_hand"), "stock_on_hand"
            ),
            "actual_available_stock": parse_optional_upstream_float(
                it.get("actual_available_stock"), "actual_available_stock"
            ),
            "reorder_level": parse_optional_upstream_float(
                it.get("reorder_level"), "reorder_level"
            ),
            "unit": str(it.get("unit", "pcs")),
            "description": it.get("description"),
            "as_of": as_of,
            "cached": is_cached,
        }
        res_capped = _enforce_output_cap(result)
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="get_item",
                status="success",
                latency_ms=latency,
                cache_hit=is_cached,
                request_id=req_id,
            )
        )
        return res_capped

    except ConnectorError as err:
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="get_item",
                status="error",
                latency_ms=latency,
                zoho_code=err.zoho_code,
                http_status=err.http_status,
                request_id=req_id,
            )
        )
        return err.to_dict()


# ==============================================================================
# MCP Tool 3: search_items
# ==============================================================================
@mcp.tool(
    name="search_items",
    description=(
        "Search catalog items by name or SKU substring, with optional low-stock filter. "
        "Use this tool when customer mentions a product name or partial SKU. "
        "DO NOT use raw query syntax; input is strictly validated."
    ),
)
@_capture_tool_metrics
async def search_items(
    query: Annotated[str | None, Field(max_length=100)] = None,
    sku: Annotated[str | None, Field(max_length=50)] = None,
    only_low_stock: bool = False,
    limit: Annotated[int, Field(ge=1, le=25)] = 25,
) -> dict[str, Any]:
    req_id = new_request_id()
    default_audit_logger.record(
        AuditEvent.create("search_items", {"query": query, "sku": sku, "limit": limit}, req_id)
    )
    start_mono = get_client().clock.monotonic()

    try:
        clean_q = ValidatedQueryBuilder.validate_search_text(query, field_name="query")
        clean_sku = ValidatedQueryBuilder.validate_sku(sku, field_name="sku")
        _, bounded_limit = ValidatedQueryBuilder.validate_pagination(
            page=1, per_page=limit, max_per_page=25
        )

        search_term = clean_sku or clean_q or ""
        params: dict[str, str] = {"per_page": str(bounded_limit)}
        if search_term:
            params["search_text"] = search_term

        data, is_cached, as_of = await get_client().get("/items", params=params, cache_ttl=120.0)
        items_raw = _dict_rows(data.get("items", []))

        results = []
        for it in items_raw:
            actual_avail = parse_optional_upstream_float(
                it.get("actual_available_stock"), "actual_available_stock"
            )
            reorder = parse_optional_upstream_float(it.get("reorder_level"), "reorder_level")
            reorder = reorder if reorder is not None else 5.0
            if only_low_stock and actual_avail is not None and actual_avail > reorder:
                continue

            results.append(
                {
                    "item_id": str(it.get("item_id")),
                    "name": str(it.get("name")),
                    "sku": str(it.get("sku")),
                    "rate": parse_upstream_float(it.get("rate"), "rate"),
                    "actual_available_stock": actual_avail,
                    "reorder_level": reorder,
                    "availability_status": (
                        "unknown"
                        if actual_avail is None
                        else "out_of_stock"
                        if actual_avail <= 0
                        else "low_stock"
                        if actual_avail <= reorder
                        else "in_stock"
                    ),
                    "is_low_stock": actual_avail is not None and 0 < actual_avail <= reorder,
                    "is_out_of_stock": actual_avail is not None and actual_avail <= 0,
                }
            )

        output = {
            "items": results[:bounded_limit],
            "count": len(results[:bounded_limit]),
            "as_of": as_of,
            "cached": is_cached,
            "truncated": False,
        }
        res_capped = _enforce_output_cap(output, list_key="items")
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="search_items",
                status="success",
                latency_ms=latency,
                cache_hit=is_cached,
                result_count=len(results[:bounded_limit]),
                request_id=req_id,
            )
        )
        return res_capped

    except ConnectorError as err:
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="search_items",
                status="error",
                latency_ms=latency,
                zoho_code=err.zoho_code,
                http_status=err.http_status,
                request_id=req_id,
            )
        )
        return err.to_dict()


# ==============================================================================
# MCP Tool 4: get_stock_availability (Cart-Nudge Primitive)
# ==============================================================================
@mcp.tool(
    name="get_stock_availability",
    description=(
        "PRIMARY DECISION PRIMITIVE for Abandoned Cart Conversion agents (FR-5). "
        "Returns an advisory stock status using an explicit Zoho availability quantity for up to 20 SKUs or item IDs. "
        "Confirm with the merchant that this field matches channel sellability before acting. "
        "Returns 'in_stock', 'low_stock', 'out_of_stock', or 'unknown', with data freshness 'as_of' and 'cached'."
    ),
)
@_capture_tool_metrics
async def get_stock_availability(
    skus_or_ids: Annotated[list[str], Field(min_length=1, max_length=20)],
    bypass_cache: bool = False,
) -> dict[str, Any]:
    req_id = new_request_id()
    default_audit_logger.record(
        AuditEvent.create("get_stock_availability", {"skus_or_ids": skus_or_ids}, req_id)
    )
    start_mono = get_client().clock.monotonic()

    try:
        response_model = await get_stock_service().get_stock_availability(
            skus_or_ids=skus_or_ids,
            bypass_cache=bypass_cache,
        )
        res_dict = response_model.model_dump()
        res_capped = _enforce_output_cap(res_dict, list_key="items")

        # Telemetry stock status rollup
        first_status = res_dict["items"][0]["status"] if res_dict["items"] else "unknown"
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="get_stock_availability",
                status="success",
                latency_ms=latency,
                cache_hit=response_model.cached,
                stock_status=str(first_status),
                result_count=len(res_dict["items"]),
                request_id=req_id,
            )
        )
        return res_capped

    except ConnectorError as err:
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="get_stock_availability",
                status="error",
                latency_ms=latency,
                zoho_code=err.zoho_code,
                http_status=err.http_status,
                request_id=req_id,
            )
        )
        return err.to_dict()


# ==============================================================================
# MCP Tool 5: list_sales_orders
# ==============================================================================
@mcp.tool(
    name="list_sales_orders",
    description=(
        "Browse sales orders with status and date range filtering. "
        "Use this tool to find orders by timeframe or customer. "
        "DO NOT use raw queries; date strings must be YYYY-MM-DD."
    ),
)
@_capture_tool_metrics
async def list_sales_orders(
    status: Annotated[str | None, Field(max_length=30)] = None,
    customer_id: Annotated[str | None, Field(max_length=50)] = None,
    date_from: Annotated[str | None, Field(max_length=10)] = None,
    date_to: Annotated[str | None, Field(max_length=10)] = None,
    page: Annotated[int, Field(ge=1, le=1000)] = 1,
    per_page: Annotated[int, Field(ge=1, le=50)] = 50,
) -> dict[str, Any]:
    req_id = new_request_id()
    default_audit_logger.record(
        AuditEvent.create("list_sales_orders", {"status": status, "page": page}, req_id)
    )
    start_mono = get_client().clock.monotonic()

    try:
        p, pp = ValidatedQueryBuilder.validate_pagination(page, per_page, max_per_page=50)
        st = (
            ValidatedQueryBuilder.validate_status(
                status,
                allowed={"draft", "confirmed", "fulfilled", "closed", "void", "all"},
                field_name="status",
            )
            if status
            else None
        )
        cid = (
            ValidatedQueryBuilder.validate_numeric_id(customer_id, field_name="customer_id")
            if customer_id
            else None
        )
        df = (
            ValidatedQueryBuilder.validate_iso_date(date_from, field_name="date_from")
            if date_from
            else None
        )
        dt = (
            ValidatedQueryBuilder.validate_iso_date(date_to, field_name="date_to")
            if date_to
            else None
        )

        params: dict[str, str] = {"page": str(p), "per_page": str(pp)}
        if st and st != "all":
            params["status"] = st
        if cid:
            params["customer_id"] = cid
        if df:
            params["date_start"] = df
        if dt:
            params["date_end"] = dt

        data, is_cached, as_of = await get_client().get(
            "/salesorders", params=params, cache_ttl=60.0
        )
        orders_raw = _dict_rows(data.get("salesorders", []))
        page_ctx = data.get("page_context", {})
        if not isinstance(page_ctx, dict):
            page_ctx = {}

        orders_projected = [
            SalesOrderProjection.from_raw_zoho(so, include_pii=False).model_dump()
            for so in orders_raw
        ]

        result = {
            "sales_orders": orders_projected,
            "page": p,
            "per_page": pp,
            "has_more": bool(page_ctx.get("has_more_page", False)),
            "next_page": p + 1 if page_ctx.get("has_more_page") else None,
            "as_of": as_of,
            "cached": is_cached,
            "truncated": False,
        }
        res_capped = _enforce_output_cap(result, list_key="sales_orders")
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="list_sales_orders",
                status="success",
                latency_ms=latency,
                cache_hit=is_cached,
                result_count=len(orders_projected),
                request_id=req_id,
            )
        )
        return res_capped

    except ConnectorError as err:
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="list_sales_orders",
                status="error",
                latency_ms=latency,
                zoho_code=err.zoho_code,
                http_status=err.http_status,
                request_id=req_id,
            )
        )
        if isinstance(err, UpstreamError) and err.http_status == 400:
            return {
                "error": "SalesOrderListUnsupportedError",
                "message": "Zoho rejected the sales-order list request. This organization may require a narrower, verified filter or a sales-order ID.",
                "agent_guidance": "Use get_sales_order with a verified salesorder_id. Use search_sales_orders with a merchant-verified reference_number only if live-probe confirmed that reference search works in this organization; otherwise report that order lookup needs a verified ID. Never guess IDs or payment matches.",
                "retryable": False,
                "http_status": 400,
            }
        return err.to_dict()


# ==============================================================================
# MCP Tool 6: get_sales_order
# ==============================================================================
@mcp.tool(
    name="get_sales_order",
    description=(
        "Retrieve details of a single sales order by salesorder_id. "
        "Customer PII is masked by default (set include_pii=True only if strictly necessary). "
        "DO NOT use this for dispute rebuttal assembly (use 'get_order_fulfillment_evidence' instead)."
    ),
)
@_capture_tool_metrics
async def get_sales_order(
    salesorder_id: Annotated[str, Field(min_length=1, max_length=50)],
    include_pii: bool = False,
) -> dict[str, Any]:
    req_id = new_request_id()
    default_audit_logger.record(
        AuditEvent.create(
            "get_sales_order", {"salesorder_id": salesorder_id, "include_pii": include_pii}, req_id
        )
    )
    start_mono = get_client().clock.monotonic()

    try:
        so_id_clean = ValidatedQueryBuilder.validate_numeric_id(
            salesorder_id, field_name="salesorder_id"
        )
        data, is_cached, as_of = await get_client().get(
            f"/salesorders/{so_id_clean}", cache_ttl=120.0
        )
        so_raw = data.get("salesorder", {})

        projection = SalesOrderProjection.from_raw_zoho(so_raw, include_pii=include_pii)
        result = projection.model_dump()
        result["as_of"] = as_of
        result["cached"] = is_cached

        res_capped = _enforce_output_cap(result)
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="get_sales_order",
                status="success",
                latency_ms=latency,
                cache_hit=is_cached,
                request_id=req_id,
            )
        )
        return res_capped

    except ConnectorError as err:
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="get_sales_order",
                status="error",
                latency_ms=latency,
                zoho_code=err.zoho_code,
                http_status=err.http_status,
                request_id=req_id,
            )
        )
        return err.to_dict()


# ==============================================================================
# MCP Tool 7: search_sales_orders
# ==============================================================================
@mcp.tool(
    name="search_sales_orders",
    description=(
        "Match a customer payment or dispute to a Zoho sales order. "
        "Accepts reference_number, customer_email, or razorpay_order_id. "
        "Returns matching orders with an explicit 'match_basis' explaining how match occurred (FR-5.3)."
    ),
)
@_capture_tool_metrics
async def search_sales_orders(
    reference_number: Annotated[str | None, Field(max_length=64)] = None,
    customer_email: Annotated[str | None, Field(max_length=100)] = None,
    razorpay_order_id: Annotated[str | None, Field(max_length=64)] = None,
    include_pii: bool = False,
    limit: Annotated[int, Field(ge=1, le=25)] = 25,
) -> dict[str, Any]:
    req_id = new_request_id()
    default_audit_logger.record(
        AuditEvent.create(
            "search_sales_orders",
            {"reference_number": reference_number, "email": customer_email},
            req_id,
        )
    )
    start_mono = get_client().clock.monotonic()

    try:
        ref_clean = ValidatedQueryBuilder.validate_reference_number(
            razorpay_order_id or reference_number, field_name="reference_number"
        )
        email_clean = ValidatedQueryBuilder.validate_email(
            customer_email, field_name="customer_email"
        )
        _, bounded_limit = ValidatedQueryBuilder.validate_pagination(
            page=1, per_page=limit, max_per_page=25
        )

        if not ref_clean and not email_clean:
            raise InputValidationError(
                field="search_sales_orders",
                value="None",
                reason="At least one of 'reference_number', 'razorpay_order_id', or 'customer_email' must be provided.",
            )

        orders_raw: list[dict[str, Any]] = []
        match_basis = "no_match"
        as_of = datetime.now(UTC).isoformat()
        is_cached = False
        if ref_clean:
            data, is_cached, as_of = await get_client().get(
                "/salesorders",
                params={"search_text": ref_clean, "per_page": str(bounded_limit)},
                cache_ttl=60.0,
            )
            orders_raw = [
                order
                for order in data.get("salesorders", [])
                if str(order.get("reference_number", "")) == ref_clean
            ]
            match_basis = "reference_number_exact" if orders_raw else "no_match"
        elif email_clean:
            contacts_data, is_cached, as_of = await get_client().get(
                "/contacts",
                params={"email": email_clean, "per_page": "25"},
                cache_ttl=60.0,
            )
            matching_contacts = [
                contact
                for contact in contacts_data.get("contacts", [])
                if str(contact.get("email", "")).casefold() == email_clean.casefold()
            ]
            contact_ids = list(
                dict.fromkeys(str(contact.get("contact_id", "")) for contact in matching_contacts)
            )
            contact_ids = [contact_id for contact_id in contact_ids if contact_id]
            for contact_id in contact_ids[:5]:
                clean_contact_id = ValidatedQueryBuilder.validate_numeric_id(
                    contact_id, field_name="contact_id"
                )
                data, orders_cached, orders_as_of = await get_client().get(
                    "/salesorders",
                    params={"customer_id": clean_contact_id, "per_page": str(bounded_limit)},
                    cache_ttl=60.0,
                )
                is_cached = is_cached and orders_cached
                as_of = max(as_of, orders_as_of)
                orders_raw.extend(data.get("salesorders", []))
                if len(orders_raw) >= bounded_limit:
                    break
            match_basis = (
                "contact_email_exact"
                if len(contact_ids) == 1
                else ("contact_email_multiple_contacts" if contact_ids else "no_match")
            )

        projected = [
            SalesOrderProjection.from_raw_zoho(
                so, include_pii=include_pii, match_basis=match_basis
            ).model_dump()
            for so in orders_raw
        ]

        result = {
            "sales_orders": projected[:bounded_limit],
            "count": len(projected[:bounded_limit]),
            "match_basis": match_basis if projected else "no_match",
            "as_of": as_of,
            "cached": is_cached,
            "truncated": False,
        }
        res_capped = _enforce_output_cap(result, list_key="sales_orders")
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="search_sales_orders",
                status="success",
                latency_ms=latency,
                cache_hit=is_cached,
                result_count=len(projected),
                request_id=req_id,
            )
        )
        return res_capped

    except ConnectorError as err:
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="search_sales_orders",
                status="error",
                latency_ms=latency,
                zoho_code=err.zoho_code,
                http_status=err.http_status,
                request_id=req_id,
            )
        )
        return err.to_dict()


# ==============================================================================
# MCP Tool 8: get_order_fulfillment_evidence (Dispute Primitive)
# ==============================================================================
@mcp.tool(
    name="get_order_fulfillment_evidence",
    description=(
        "PRIMARY DECISION PRIMITIVE for Dispute Responder chargeback rebuttals (FR-5.4). "
        "Assembles cross-object fulfillment proof across sales order, tax invoice, packaging slip, "
        "carrier designation, tracking number, and delivery date. Never guesses absent fields. "
        "Returns completeness: 'complete' (all fields in this connector's checklist were found), "
        "'partial' (enumerates missing fields), or 'none'. Completeness does not determine whether a rebuttal is sufficient."
    ),
)
@_capture_tool_metrics
async def get_order_fulfillment_evidence(
    salesorder_id: Annotated[str, Field(min_length=1, max_length=50)],
    bypass_cache: bool = False,
) -> dict[str, Any]:
    req_id = new_request_id()
    default_audit_logger.record(
        AuditEvent.create(
            "get_order_fulfillment_evidence", {"salesorder_id": salesorder_id}, req_id
        )
    )
    start_mono = get_client().clock.monotonic()

    try:
        evidence_model = await get_dispute_service().get_order_fulfillment_evidence(
            salesorder_id=salesorder_id,
            bypass_cache=bypass_cache,
        )
        res_dict = evidence_model.model_dump()
        res_capped = _enforce_output_cap(res_dict)

        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="get_order_fulfillment_evidence",
                status="success",
                latency_ms=latency,
                cache_hit=evidence_model.cached,
                result_count=1,
                request_id=req_id,
            )
        )
        return res_capped

    except ConnectorError as err:
        latency = (get_client().clock.monotonic() - start_mono) * 1000.0
        default_emitter.emit(
            ToolExecutionEvent.create(
                tool="get_order_fulfillment_evidence",
                status="error",
                latency_ms=latency,
                zoho_code=err.zoho_code,
                http_status=err.http_status,
                request_id=req_id,
            )
        )
        return err.to_dict()


def run_stdio() -> None:
    """Run FastMCP server on stdio (default). Strictly preserves stdout hygiene (NFR-8)."""
    # Verify no accidental stdout redirection
    sys.stderr.write("Starting Zoho Inventory FastMCP stdio server...\n")
    sys.stderr.flush()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()
