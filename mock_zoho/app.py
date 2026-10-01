"""FastAPI application emulating Zoho Inventory API and OAuth 2.0 (FR-9)."""

from typing import Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from mock_zoho.faults import faults
from mock_zoho.fixtures import generate_fixtures

app = FastAPI(title="Deterministic Mock Zoho Inventory API", version="1.0.0")

# Preload seeded fixtures
FIXTURES = generate_fixtures()
MOCK_ACCESS_TOKEN = "zoho_access_mock_token_12345"
MOCK_REFRESH_TOKEN = "zoho_refresh_mock_token_67890"


@app.get("/oauth/v2/auth")
async def mock_oauth_auth(
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    response_type: str = Query("code"),
    state: str | None = Query(None),
    access_type: str | None = Query("offline"),
) -> RedirectResponse:
    """Emulate Zoho OAuth authorization consent screen redirect."""
    code = "mock_auth_grant_code_xyz"
    redirect_target = f"{redirect_uri}?code={code}"
    if state:
        redirect_target += f"&state={state}"
    return RedirectResponse(url=redirect_target, status_code=302)


@app.post("/oauth/v2/token")
async def mock_oauth_token(request: Request) -> JSONResponse:
    """Emulate Zoho OAuth token exchange and refresh flows."""
    form = await request.form()
    grant_type = form.get("grant_type")
    client_id = form.get("client_id")
    client_secret = form.get("client_secret")

    if not client_id or not client_secret:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_client", "error_description": "Missing client credentials"},
        )

    if grant_type == "authorization_code":
        code = form.get("code")
        if not code or "invalid" in str(code):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_grant",
                    "error_description": "Invalid or expired authorization code",
                },
            )
        return JSONResponse(
            status_code=200,
            content={
                "access_token": MOCK_ACCESS_TOKEN,
                "refresh_token": MOCK_REFRESH_TOKEN,
                "api_domain": "http://127.0.0.1:8000",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    elif grant_type == "refresh_token":
        ref_token = form.get("refresh_token")
        if not ref_token or "invalid" in str(ref_token):
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_grant", "error_description": "Invalid refresh token"},
            )
        return JSONResponse(
            status_code=200,
            content={
                "access_token": MOCK_ACCESS_TOKEN,
                "api_domain": "http://127.0.0.1:8000",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    return JSONResponse(
        status_code=400,
        content={
            "error": "unsupported_grant_type",
            "error_description": f"Unsupported grant_type: {grant_type}",
        },
    )


def _check_faults_and_auth(authorization: str | None) -> JSONResponse | None:
    """Helper to check injected faults and validate Authorization header."""
    if faults.inject_latency_seconds > 0:
        # Note: non-blocking wait handled in route if needed
        pass

    if faults.inject_401_expired_token:
        return JSONResponse(
            status_code=401,
            content={"code": 57, "message": "Invalid OAuth token or token expired."},
        )

    if faults.inject_429_rate_limit:
        headers = {}
        if faults.retry_after_seconds:
            headers["Retry-After"] = str(faults.retry_after_seconds)
        return JSONResponse(
            status_code=429,
            content={"code": 429, "message": "Too many requests. Please slow down."},
            headers=headers,
        )

    if faults.inject_code_44_block:
        return JSONResponse(
            status_code=429,
            content={
                "code": 44,
                "message": "You have exceeded the limit of requests per minute. Access blocked.",
            },
        )

    if faults.inject_code_45_quota_exhausted:
        return JSONResponse(
            status_code=429,
            content={
                "code": 45,
                "message": "You have exceeded the maximum API call limit for the day.",
            },
        )

    if faults.inject_code_1070_concurrency:
        return JSONResponse(
            status_code=429,
            content={"code": 1070, "message": "Maximum concurrent requests limit reached."},
        )

    if faults.inject_500_server_error:
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "Internal server error encountered in Zoho Inventory.",
            },
        )

    if not authorization or not authorization.startswith("Zoho-oauthtoken "):
        return JSONResponse(
            status_code=401,
            content={
                "code": 57,
                "message": "Authorization header must be in format 'Zoho-oauthtoken <token>'",
            },
        )

    token = authorization.split(" ", 1)[1]
    if token != MOCK_ACCESS_TOKEN and not token.startswith("valid_"):
        return JSONResponse(
            status_code=401,
            content={"code": 57, "message": "OAuth token is invalid or expired."},
        )

    return None


@app.get("/inventory/v1/organizations")
async def list_organizations(
    authorization: str | None = Header(None),
) -> Any:
    fault = _check_faults_and_auth(authorization)
    if fault:
        return fault

    return {
        "code": 0,
        "message": "success",
        "organizations": [
            {
                "organization_id": "org_kaveri_blr_001",
                "name": "Kaveri Home Goods Bangalore",
                "is_default_org": True,
                "currency_code": "INR",
                "currency_symbol": "₹",
                "time_zone": "Asia/Calcutta",
            }
        ],
    }


@app.get("/inventory/v1/items")
async def list_items(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search_text: str | None = Query(None),
    status: str | None = Query(None),
    organization_id: str | None = Query(None),
    authorization: str | None = Header(None),
) -> Any:
    fault = _check_faults_and_auth(authorization)
    if fault:
        return fault

    all_items = FIXTURES["items"]
    filtered = all_items

    if status:
        filtered = [it for it in filtered if it.get("status", "").lower() == status.lower()]

    if search_text:
        st = search_text.lower()
        filtered = [
            it
            for it in filtered
            if st in it.get("name", "").lower()
            or st in it.get("sku", "").lower()
            or st in it.get("item_id", "").lower()
        ]

    start = (page - 1) * per_page
    end = start + per_page
    paged = filtered[start:end]
    has_more = end < len(filtered)

    return {
        "code": 0,
        "message": "success",
        "items": paged,
        "page_context": {
            "page": page,
            "per_page": per_page,
            "has_more_page": has_more,
            "total": len(filtered),
        },
    }


@app.get("/inventory/v1/items/{item_id}")
async def get_item(
    item_id: str,
    organization_id: str | None = Query(None),
    authorization: str | None = Header(None),
) -> Any:
    fault = _check_faults_and_auth(authorization)
    if fault:
        return fault

    for it in FIXTURES["items"]:
        if it["item_id"] == item_id:
            return {"code": 0, "message": "success", "item": it}

    return JSONResponse(
        status_code=404, content={"code": 1002, "message": f"Item {item_id} not found."}
    )


@app.get("/inventory/v1/salesorders")
async def list_sales_orders(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search_text: str | None = Query(None),
    status: str | None = Query(None),
    customer_id: str | None = Query(None),
    reference_number: str | None = Query(None),
    customer_email: str | None = Query(None),
    organization_id: str | None = Query(None),
    authorization: str | None = Header(None),
) -> Any:
    fault = _check_faults_and_auth(authorization)
    if fault:
        return fault

    all_orders = FIXTURES["sales_orders"]
    filtered = all_orders

    if status:
        filtered = [so for so in filtered if so.get("status", "").lower() == status.lower()]
    if customer_id:
        filtered = [so for so in filtered if so.get("customer_id") == customer_id]
    if reference_number:
        filtered = [so for so in filtered if so.get("reference_number") == reference_number]
    if customer_email:
        filtered = [
            so for so in filtered if so.get("customer_email", "").lower() == customer_email.lower()
        ]
    if search_text:
        st = search_text.lower()
        filtered = [
            so
            for so in filtered
            if st in so.get("salesorder_number", "").lower()
            or st in str(so.get("reference_number", "")).lower()
            or st in so.get("customer_name", "").lower()
        ]

    start = (page - 1) * per_page
    end = start + per_page
    paged = filtered[start:end]
    has_more = end < len(filtered)

    return {
        "code": 0,
        "message": "success",
        "salesorders": paged,
        "page_context": {
            "page": page,
            "per_page": per_page,
            "has_more_page": has_more,
            "total": len(filtered),
        },
    }


@app.get("/inventory/v1/salesorders/{salesorder_id}")
async def get_sales_order(
    salesorder_id: str,
    organization_id: str | None = Query(None),
    authorization: str | None = Header(None),
) -> Any:
    fault = _check_faults_and_auth(authorization)
    if fault:
        return fault

    for so in FIXTURES["sales_orders"]:
        if so["salesorder_id"] == salesorder_id:
            # Check attached invoices, packages, shipments
            order_invoices = [
                inv for inv in FIXTURES["invoices"] if inv["salesorder_id"] == salesorder_id
            ]
            order_packages = [
                pkg for pkg in FIXTURES["packages"] if pkg["salesorder_id"] == salesorder_id
            ]
            order_shipments = [
                shp for shp in FIXTURES["shipments"] if shp["salesorder_id"] == salesorder_id
            ]

            full_so = dict(so)
            full_so["invoices"] = order_invoices
            full_so["packages"] = order_packages
            full_so["shipments"] = order_shipments
            return {"code": 0, "message": "success", "salesorder": full_so}

    return JSONResponse(
        status_code=404,
        content={"code": 1002, "message": f"Sales order {salesorder_id} not found."},
    )


@app.get("/inventory/v1/packages")
async def list_packages(
    salesorder_id: str | None = Query(None),
    organization_id: str | None = Query(None),
    authorization: str | None = Header(None),
) -> Any:
    fault = _check_faults_and_auth(authorization)
    if fault:
        return fault

    pkgs = FIXTURES["packages"]
    if salesorder_id:
        pkgs = [p for p in pkgs if p["salesorder_id"] == salesorder_id]
    return {"code": 0, "message": "success", "packages": pkgs}


@app.get("/inventory/v1/shipmentorders")
async def list_shipment_orders(
    salesorder_id: str | None = Query(None),
    organization_id: str | None = Query(None),
    authorization: str | None = Header(None),
) -> Any:
    fault = _check_faults_and_auth(authorization)
    if fault:
        return fault

    shps = FIXTURES["shipments"]
    if salesorder_id:
        shps = [s for s in shps if s["salesorder_id"] == salesorder_id]
    return {"code": 0, "message": "success", "shipmentorders": shps}


@app.get("/inventory/v1/invoices")
async def list_invoices(
    salesorder_id: str | None = Query(None),
    organization_id: str | None = Query(None),
    authorization: str | None = Header(None),
) -> Any:
    fault = _check_faults_and_auth(authorization)
    if fault:
        return fault

    invs = FIXTURES["invoices"]
    if salesorder_id:
        invs = [inv for inv in invs if inv["salesorder_id"] == salesorder_id]
    return {"code": 0, "message": "success", "invoices": invs}


@app.post("/mock/faults/configure")
async def configure_faults(req: Request) -> JSONResponse:
    """Control endpoint for fault injection during testing."""
    body = await req.json()
    if "inject_401_expired_token" in body:
        faults.inject_401_expired_token = bool(body["inject_401_expired_token"])
    if "inject_429_rate_limit" in body:
        faults.inject_429_rate_limit = bool(body["inject_429_rate_limit"])
    if "retry_after_seconds" in body:
        faults.retry_after_seconds = body["retry_after_seconds"]
    if "inject_code_44_block" in body:
        faults.inject_code_44_block = bool(body["inject_code_44_block"])
    if "inject_code_45_quota_exhausted" in body:
        faults.inject_code_45_quota_exhausted = bool(body["inject_code_45_quota_exhausted"])
    if "inject_code_1070_concurrency" in body:
        faults.inject_code_1070_concurrency = bool(body["inject_code_1070_concurrency"])
    if "inject_500_server_error" in body:
        faults.inject_500_server_error = bool(body["inject_500_server_error"])
    if "inject_latency_seconds" in body:
        faults.inject_latency_seconds = float(body["inject_latency_seconds"])
    return JSONResponse(content={"status": "ok", "faults": faults.__dict__})


@app.post("/mock/faults/reset")
async def reset_faults() -> JSONResponse:
    faults.reset()
    return JSONResponse(content={"status": "reset", "faults": faults.__dict__})
