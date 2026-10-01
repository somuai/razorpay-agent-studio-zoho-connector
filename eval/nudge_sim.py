"""Abandoned Cart Nudge Policy Simulation (FR-10, M1, M3).

Compares baseline naive nudge policy vs. stock-aware connector policy
over 200 seeded fictional cart abandonment events.
"""

import math
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
    baseline_correctly_nudged = 0
    baseline_wasted_discount_inr = 0.0
    baseline_discount_given_inr = 0.0

    for cart in cart_events:
        baseline_nudges_sent += 1
        discount = cart["discount_offered_inr"]
        baseline_discount_given_inr += discount

        # If SKU was out of stock, this nudge was completely wasted
        # A cart is unavailable when any included SKU is out of stock. This is
        # deliberately conservative: partial-cart recovery is a separate policy.
        if any(item["stock_type"] == "out_of_stock" for item in cart["items"]):
            baseline_wasted_nudges += 1
            baseline_wasted_discount_inr += discount
        else:
            baseline_correctly_nudged += 1

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
    logical_latencies_ms: list[float] = []

    for cart in cart_events:
        skus = [item["sku"] for item in cart["items"]]
        discount = cart["discount_offered_inr"]

        # One composed decision per cart. The virtual clock keeps this
        # deterministic; it is not a measure of real elapsed latency.
        start = stock_service.client.clock.monotonic()
        stock_resp = await stock_service.get_stock_availability(skus)
        logical_latencies_ms.append((stock_service.client.clock.monotonic() - start) * 1000.0)
        statuses = [item.status for item in stock_resp.items]
        if len(statuses) != len(skus):
            statuses.append(StockStatus.UNKNOWN)

        if StockStatus.OUT_OF_STOCK in statuses:
            # Policy Rule: Suppress nudge to protect brand and prevent wasted discount
            connector_suppressed_nudges += 1
            decisions.append(
                {
                    "cart_id": cart["cart_id"],
                    "skus": skus,
                    "action": "SUPPRESS_NUDGE",
                    "reason": "Item out of stock in warehouse",
                    "discount_applied_inr": 0.0,
                }
            )
        elif StockStatus.UNKNOWN in statuses:
            connector_suppressed_nudges += 1
            decisions.append(
                {
                    "cart_id": cart["cart_id"],
                    "skus": skus,
                    "action": "SUPPRESS_NUDGE",
                    "reason": "Stock status unconfirmed for at least one cart item",
                    "discount_applied_inr": 0.0,
                }
            )
        elif StockStatus.LOW_STOCK in statuses:
            # Policy Rule: Send scarcity message ("Only X left!"), offer 0% discount
            connector_nudges_sent += 1
            connector_scarcity_nudges += 1
            low_stock_item = next(
                item for item in stock_resp.items if item.status == StockStatus.LOW_STOCK
            )
            decisions.append(
                {
                    "cart_id": cart["cart_id"],
                    "skus": skus,
                    "action": "NUDGE_SCARCITY_NO_DISCOUNT",
                    "reason": f"At least one item is low-stock ({low_stock_item.quantity_sellable} sellable); urgency without margin loss",
                    "discount_applied_inr": 0.0,
                }
            )
        elif statuses and all(status == StockStatus.IN_STOCK for status in statuses):
            # Policy Rule: Safe to offer normal conversion discount
            connector_nudges_sent += 1
            connector_discount_nudges += 1
            connector_discount_given_inr += discount
            decisions.append(
                {
                    "cart_id": cart["cart_id"],
                    "skus": skus,
                    "action": "NUDGE_STANDARD_DISCOUNT",
                    "reason": "Ample stock verified across fulfillment centers",
                    "discount_applied_inr": discount,
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
    ordered_latencies = sorted(logical_latencies_ms)

    def percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        index = max(0, math.ceil(p * len(values)) - 1)
        return round(values[index], 2)

    return {
        "simulation_mode": "SIMULATED",
        "total_cart_events": total_carts,
        "baseline_policy": {
            "nudges_sent": baseline_nudges_sent,
            "wasted_nudges_count": baseline_wasted_nudges,
            "wasted_nudges_pct": baseline_wasted_pct,
            "correctly_nudged_count": baseline_correctly_nudged,
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
            "correctly_nudged_count": connector_nudges_sent,
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
            "tool_latency_p50_ms_virtual_clock": percentile(ordered_latencies, 0.50),
            "tool_latency_p95_ms_virtual_clock": percentile(ordered_latencies, 0.95),
            "latency_note": "Virtual-clock elapsed time; not a runtime latency benchmark.",
        },
    }
