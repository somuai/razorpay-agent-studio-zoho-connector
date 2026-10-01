"""Abandoned Cart Nudge Policy Simulation (FR-10, M1, M3).

Compares baseline naive nudge policy vs. stock-aware connector policy
over 200 seeded fictional cart abandonment events.
"""

from typing import Any

from zoho_inventory_connector.models.item import StockStatus
from zoho_inventory_connector.services.stock_service import StockService


async def run_nudge_simulation(
    cart_events: list[dict[str, Any]],
    stock_service: StockService,
) -> dict[str, Any]:
    """Run comparative simulation between baseline and connector-aware nudge policies."""
    total_carts = len(cart_events)

    # -------------------------------------------------------------
    # 1. Baseline Policy (Unaware of stock levels)
    # -------------------------------------------------------------
    baseline_nudges_sent = 0
    baseline_wasted_nudges = 0
    baseline_wasted_discount_inr = 0.0
    baseline_discount_given_inr = 0.0

    for cart in cart_events:
        baseline_nudges_sent += 1
        discount = cart["discount_offered_inr"]
        baseline_discount_given_inr += discount

        # If SKU was out of stock, this nudge was completely wasted
        if cart["underlying_stock_type"] == "out_of_stock":
            baseline_wasted_nudges += 1
            baseline_wasted_discount_inr += discount

    # -------------------------------------------------------------
    # 2. Connector-Aware Policy (Queries get_stock_availability)
    # -------------------------------------------------------------
    connector_nudges_sent = 0
    connector_scarcity_nudges = 0  # Nudges without discount (scarcity only)
    connector_discount_nudges = 0  # Nudges with normal discount
    connector_suppressed_nudges = 0
    connector_wasted_nudges = 0
    connector_wasted_discount_inr = 0.0
    connector_discount_given_inr = 0.0

    decisions: list[dict[str, Any]] = []

    for cart in cart_events:
        sku = cart["primary_sku"]
        discount = cart["discount_offered_inr"]

        # Call stock service
        stock_resp = await stock_service.get_stock_availability([sku])
        item_stock = stock_resp.items[0] if stock_resp.items else None
        status = item_stock.status if item_stock else StockStatus.UNKNOWN

        if status == StockStatus.OUT_OF_STOCK:
            # Policy Rule: Suppress nudge to protect brand and prevent wasted discount
            connector_suppressed_nudges += 1
            decisions.append(
                {
                    "cart_id": cart["cart_id"],
                    "sku": sku,
                    "action": "SUPPRESS_NUDGE",
                    "reason": "Item out of stock in warehouse",
                    "discount_applied_inr": 0.0,
                }
            )
        elif status == StockStatus.LOW_STOCK:
            # Policy Rule: Send scarcity message ("Only X left!"), offer 0% discount
            connector_nudges_sent += 1
            connector_scarcity_nudges += 1
            decisions.append(
                {
                    "cart_id": cart["cart_id"],
                    "sku": sku,
                    "action": "NUDGE_SCARCITY_NO_DISCOUNT",
                    "reason": f"Low stock ({item_stock.quantity_sellable} remaining); urgency without margin loss",
                    "discount_applied_inr": 0.0,
                }
            )
        elif status == StockStatus.IN_STOCK:
            # Policy Rule: Safe to offer normal conversion discount
            connector_nudges_sent += 1
            connector_discount_nudges += 1
            connector_discount_given_inr += discount
            decisions.append(
                {
                    "cart_id": cart["cart_id"],
                    "sku": sku,
                    "action": "NUDGE_STANDARD_DISCOUNT",
                    "reason": "Ample stock verified across fulfillment centers",
                    "discount_applied_inr": discount,
                }
            )
        else:
            # Unknown status: Hold/Suppress
            connector_suppressed_nudges += 1
            decisions.append(
                {
                    "cart_id": cart["cart_id"],
                    "sku": sku,
                    "action": "SUPPRESS_NUDGE",
                    "reason": "Catalog status unconfirmed",
                    "discount_applied_inr": 0.0,
                }
            )

    # Calculate metrics
    baseline_wasted_pct = round((baseline_wasted_nudges / total_carts) * 100, 2)
    connector_wasted_pct = round((connector_wasted_nudges / total_carts) * 100, 2)
    discount_budget_saved_inr = round(baseline_discount_given_inr - connector_discount_given_inr, 2)

    metrics = stock_service.client.metrics
    total_api_calls = metrics.calls_made
    cache_hits = metrics.cache_hits
    cache_hit_pct = round((cache_hits / max(1, total_api_calls + cache_hits)) * 100, 2)
    calls_per_decision = round(total_api_calls / total_carts, 3)
    quota_consumed_pct = round((total_api_calls / 1000.0) * 100, 2)

    return {
        "simulation_mode": "SIMULATED",
        "total_cart_events": total_carts,
        "baseline_policy": {
            "nudges_sent": baseline_nudges_sent,
            "wasted_nudges_count": baseline_wasted_nudges,
            "wasted_nudges_pct": baseline_wasted_pct,
            "total_discount_disbursed_inr": round(baseline_discount_given_inr, 2),
            "wasted_discount_inr": round(baseline_wasted_discount_inr, 2),
        },
        "connector_aware_policy": {
            "nudges_sent": connector_nudges_sent,
            "discount_nudges": connector_discount_nudges,
            "scarcity_no_discount_nudges": connector_scarcity_nudges,
            "suppressed_nudges": connector_suppressed_nudges,
            "wasted_nudges_count": connector_wasted_nudges,
            "wasted_nudges_pct": connector_wasted_pct,
            "total_discount_disbursed_inr": round(connector_discount_given_inr, 2),
            "wasted_discount_inr": round(connector_wasted_discount_inr, 2),
            "discount_budget_saved_inr": discount_budget_saved_inr,
        },
        "efficiency_and_cost": {
            "api_calls_made": total_api_calls,
            "cache_hits": cache_hits,
            "cache_hit_pct": cache_hit_pct,
            "api_calls_per_decision": calls_per_decision,
            "zoho_free_tier_quota_consumed_pct": quota_consumed_pct,
        },
    }
