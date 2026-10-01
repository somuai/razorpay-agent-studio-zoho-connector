"""Deterministic seeded evaluation data for Agent Studio simulations (FR-10).

All data is strictly fictional, seeded with seed=42.
Generates 200 abandoned-cart events and 40 chargeback dispute cases.
"""

import random
from typing import Any

from mock_zoho.fixtures import PRODUCT_CATALOG, SEED, generate_fixtures


def generate_eval_datasets() -> dict[str, Any]:
    """Generate 200 abandoned cart events and 40 dispute cases deterministically."""
    rng = random.Random(SEED)

    # 1. Generate 200 Abandoned Cart Events
    # Distribution of items in Kaveri Home Goods catalog:
    # ~33% in_stock, ~33% low_stock, ~23% out_of_stock, ~10% multi_wh
    cart_events: list[dict[str, Any]] = []

    # Map catalog items
    catalog_items = []
    for idx, (name, sku, price, _reorder, stock_type) in enumerate(PRODUCT_CATALOG, start=1):
        catalog_items.append(
            {
                "item_id": f"item_{1000 + idx}",
                "sku": sku,
                "name": name,
                "price": price,
                "stock_type": stock_type,
            }
        )

    for i in range(1, 201):
        cart_id = f"cart_blr_{1000 + i}"
        customer_id = f"cust_sim_{rng.randint(100, 999)}"

        # Pick 1-2 items per cart
        num_items = 1 if rng.random() < 0.8 else 2
        selected_items = rng.sample(catalog_items, k=num_items)

        total_value = sum(item["price"] for item in selected_items)
        discount_offered = round(total_value * 0.10, 2)  # Standard 10% abandoned cart discount

        cart_events.append(
            {
                "cart_id": cart_id,
                "customer_id": customer_id,
                "items": selected_items,
                "cart_value": total_value,
                "discount_offered_inr": discount_offered,
                "primary_sku": selected_items[0]["sku"],
                "primary_item_id": selected_items[0]["item_id"],
                "underlying_stock_type": selected_items[0]["stock_type"],
            }
        )

    # 2. Generate 40 Dispute Cases
    # Map to seeded orders in mock_zoho/fixtures.py (so_2001 to so_2040)
    fixtures = generate_fixtures()
    sales_orders = fixtures["sales_orders"]
    dispute_cases: list[dict[str, Any]] = []

    for idx in range(1, 41):
        dispute_id = f"disp_kaveri_{3000 + idx}"
        order = sales_orders[idx - 1]
        so_id = order["salesorder_id"]

        dispute_cases.append(
            {
                "dispute_id": dispute_id,
                "salesorder_id": so_id,
                "salesorder_number": order["salesorder_number"],
                "customer_name": order["customer_name"],
                "dispute_amount_inr": order["total"],
                "reason_code": "product_not_received" if idx % 2 == 0 else "fraudulent_transaction",
                "dispute_opened_date": "2026-09-25",
            }
        )

    return {
        "simulation_mode": "SIMULATED",
        "seed": SEED,
        "cart_events": cart_events,
        "dispute_cases": dispute_cases,
    }
