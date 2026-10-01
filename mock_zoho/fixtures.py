"""Deterministic seeded fixtures for Mock Zoho Inventory Server (FR-9).

All data is fictional and seeded with seed=42.
"""

import random
from typing import Any

SEED = 42

WAREHOUSES = [
    {"warehouse_id": "wh_blr_central", "warehouse_name": "Bangalore Central Hub"},
    {"warehouse_id": "wh_blr_whitefield", "warehouse_name": "Whitefield Fulfillment Center"},
]

PRODUCT_CATALOG = [
    ("Handwoven Ikat Cushion Cover", "KHG-CUSH-001", 699.0, 10, "in_stock"),
    ("Brass Peacock Diya Lamp", "KHG-LAMP-002", 1499.0, 5, "in_stock"),
    ("Jaipuri Blue Pottery Vase", "KHG-VASE-003", 2199.0, 8, "in_stock"),
    ("Teakwood Coaster Set (6 pcs)", "KHG-COAST-004", 499.0, 15, "in_stock"),
    ("Khadi Cotton King Bedspread", "KHG-BED-005", 3499.0, 5, "in_stock"),
    ("Hand-carved Sheesham Spice Box", "KHG-SPICE-006", 1299.0, 8, "in_stock"),
    ("Kashmiri Walnut Wood Serving Tray", "KHG-TRAY-007", 2799.0, 4, "in_stock"),
    ("Hammered Pure Copper Pitcher", "KHG-COP-008", 1899.0, 6, "in_stock"),
    ("Block-Printed Linen Table Runner", "KHG-RUN-009", 899.0, 12, "in_stock"),
    ("Handmade Ceramic Coffee Mugs (Set of 2)", "KHG-MUG-010", 799.0, 10, "in_stock"),
    ("Dhokra Tribal Art Figurine", "KHG-DHOK-011", 1850.0, 5, "low_stock"),
    ("Mysore Sandalwood Incense Burner", "KHG-INC-012", 599.0, 4, "low_stock"),
    ("Embroidered Kantha Silk Throw", "KHG-THRW-013", 2999.0, 5, "low_stock"),
    ("Terracotta Hand-painted Planter", "KHG-PLNT-014", 650.0, 6, "low_stock"),
    ("Brass Bell Hanging Chime", "KHG-CHIME-015", 1150.0, 5, "low_stock"),
    ("Woven Jute Area Rug (4x6 ft)", "KHG-RUG-016", 3999.0, 3, "low_stock"),
    ("Channapatna Wooden Toy Figurine", "KHG-TOY-017", 450.0, 5, "low_stock"),
    ("Hand-knotted Macrame Wall Hanging", "KHG-MAC-018", 1250.0, 4, "low_stock"),
    ("Pure Silk Brocade Tablecloth", "KHG-SILK-019", 4299.0, 5, "out_of_stock"),
    ("Antiqued Bronze Urli Bowl", "KHG-URLI-020", 3200.0, 4, "out_of_stock"),
    ("Kutch Hand-embroidered Wall Tapestry", "KHG-TAP-021", 4999.0, 3, "out_of_stock"),
    ("Sandalwood Carved Elephant Keepsake", "KHG-ELE-022", 1699.0, 5, "out_of_stock"),
    ("Handmade Paper Leather Journal", "KHG-JRNL-023", 599.0, 10, "out_of_stock"),
    ("Cast Iron Vintage Spice Grinder", "KHG-GRND-024", 2150.0, 4, "out_of_stock"),
    ("Chanderi Silk Lumbar Pillow", "KHG-PILL-025", 1100.0, 5, "out_of_stock"),
    ("Tanjore Gold Foil Ganesha Frame", "KHG-TANJ-026", 8999.0, 2, "multi_wh"),
    ("Hand-beaten Bell Metal Dinner Thali", "KHG-THAL-027", 3499.0, 5, "multi_wh"),
    ("Organic Bamboo Fiber Bath Towels", "KHG-BAMB-028", 1499.0, 10, "multi_wh"),
    ("Hand-stitched Leather Ottoman Pouf", "KHG-POUF-029", 4599.0, 4, "multi_wh"),
    ("Pashmina Wool Chevron Stole", "KHG-PASH-030", 5499.0, 3, "multi_wh"),
]

CARRIERS = ["BlueDart", "Delhivery", "DTDC", "India Post"]


def generate_fixtures() -> dict[str, Any]:
    """Generate deterministic fixtures for Zoho items, sales orders, packages, shipments, invoices."""
    rng = random.Random(SEED)

    items: list[dict[str, Any]] = []
    for idx, (name, sku, price, reorder, stock_type) in enumerate(PRODUCT_CATALOG, start=1):
        item_id = f"item_{1000 + idx}"

        if stock_type == "in_stock":
            actual_stock = rng.randint(reorder + 10, reorder + 60)
            wh1 = actual_stock // 2
            wh2 = actual_stock - wh1
        elif stock_type == "low_stock":
            actual_stock = rng.randint(1, reorder)
            wh1 = actual_stock
            wh2 = 0
        elif stock_type == "out_of_stock":
            actual_stock = 0
            wh1 = 0
            wh2 = 0
        else:  # multi_wh
            actual_stock = rng.randint(reorder + 5, reorder + 30)
            wh1 = actual_stock // 2
            wh2 = actual_stock - wh1

        warehouses_data = [
            {
                "warehouse_id": WAREHOUSES[0]["warehouse_id"],
                "warehouse_name": WAREHOUSES[0]["warehouse_name"],
                "warehouse_stock_on_hand": wh1 + rng.randint(0, 3),
                "warehouse_available_stock": wh1,
            },
            {
                "warehouse_id": WAREHOUSES[1]["warehouse_id"],
                "warehouse_name": WAREHOUSES[1]["warehouse_name"],
                "warehouse_stock_on_hand": wh2 + rng.randint(0, 2),
                "warehouse_available_stock": wh2,
            },
        ]

        items.append(
            {
                "item_id": item_id,
                "name": name,
                "sku": sku,
                "status": "active",
                "rate": price,
                "reorder_level": reorder,
                "unit": "pcs",
                "stock_on_hand": actual_stock + rng.randint(0, 5),
                "available_stock": actual_stock,
                "actual_available_stock": actual_stock,
                "warehouses": warehouses_data,
                "description": f"Artisanal Indian decor: {name}",
            }
        )

    # Generate 40 sales orders
    sales_orders: list[dict[str, Any]] = []
    packages: list[dict[str, Any]] = []
    shipments: list[dict[str, Any]] = []
    invoices: list[dict[str, Any]] = []

    statuses = (
        ["fulfilled"] * 18
        + ["confirmed"] * 10
        + ["draft"] * 6
        + ["partial_fulfillment"] * 4
        + ["void"] * 2
    )

    for i in range(1, 41):
        so_id = f"so_{2000 + i}"
        so_number = f"SO-{10000 + i}"
        status = statuses[i - 1]
        day = (i % 28) + 1
        month = 8 if i <= 20 else 9
        date_str = f"2026-0{month}-{day:02d}"

        cust_id = f"cust_{300 + (i % 15)}"
        cust_name = f"Test Customer {i:03d}"
        cust_email = f"customer_{i:03d}@example.com"
        cust_phone = f"+9198765{10000 + i}"
        rzp_order_id = f"order_RzpKav{1000 + i}"

        # Choose 1 to 3 items
        order_items = rng.sample(items, k=rng.randint(1, 3))
        line_items = []
        total_amount = 0.0
        for it in order_items:
            qty = rng.randint(1, 3)
            subtot = it["rate"] * qty
            total_amount += subtot
            line_items.append(
                {
                    "item_id": it["item_id"],
                    "sku": it["sku"],
                    "name": it["name"],
                    "quantity": qty,
                    "rate": it["rate"],
                    "item_total": subtot,
                }
            )

        so_record = {
            "salesorder_id": so_id,
            "salesorder_number": so_number,
            "date": date_str,
            "status": "fulfilled" if status in ("fulfilled", "partial_fulfillment") else status,
            "customer_id": cust_id,
            "customer_name": cust_name,
            "customer_email": cust_email,
            "customer_phone": cust_phone,
            "reference_number": rzp_order_id,
            "total": total_amount,
            "currency_code": "INR",
            "line_items": line_items,
        }
        sales_orders.append(so_record)

        # Invoices
        if status in ("fulfilled", "partial_fulfillment", "confirmed"):
            inv_id = f"inv_{4000 + i}"
            invoices.append(
                {
                    "invoice_id": inv_id,
                    "invoice_number": f"INV-{20000 + i}",
                    "salesorder_id": so_id,
                    "date": date_str,
                    "status": "paid",
                    "total": total_amount,
                    "balance": 0.0,
                }
            )

        # Packages
        if status in ("fulfilled", "partial_fulfillment"):
            pkg_id = f"pkg_{5000 + i}"
            packages.append(
                {
                    "package_id": pkg_id,
                    "package_number": f"PKG-{30000 + i}",
                    "salesorder_id": so_id,
                    "date": date_str,
                    "status": "shipped" if status == "partial_fulfillment" else "delivered",
                }
            )

            # Shipments
            if status == "fulfilled":
                carrier = rng.choice(CARRIERS)
                track_num = f"{carrier[:2].upper()}{rng.randint(10000000, 99999999)}IN"
                ship_date = date_str
                deliv_date = f"2026-0{month}-{min(28, day + 3):02d}"
                shipments.append(
                    {
                        "shipment_id": f"ship_{6000 + i}",
                        "shipment_number": f"SHP-{40000 + i}",
                        "salesorder_id": so_id,
                        "package_id": pkg_id,
                        "carrier": carrier,
                        "tracking_number": track_num,
                        "shipment_date": ship_date,
                        "delivery_date": deliv_date,
                        "status": "delivered",
                    }
                )
            elif status == "partial_fulfillment":
                # Package created, carrier assigned, but tracking / delivery missing
                shipments.append(
                    {
                        "shipment_id": f"ship_{6000 + i}",
                        "shipment_number": f"SHP-{40000 + i}",
                        "salesorder_id": so_id,
                        "package_id": pkg_id,
                        "carrier": rng.choice(CARRIERS),
                        "tracking_number": None,
                        "shipment_date": date_str,
                        "delivery_date": None,
                        "status": "in_transit",
                    }
                )

    return {
        "items": items,
        "sales_orders": sales_orders,
        "packages": packages,
        "shipments": shipments,
        "invoices": invoices,
    }
