"""Stock availability business domain service for cart-nudge decisions (FR-5, FR-5.2)."""

from datetime import UTC, datetime
from typing import Any

from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.client.errors import InputValidationError, NotFoundError
from zoho_inventory_connector.client.query_builder import ValidatedQueryBuilder
from zoho_inventory_connector.models.item import (
    ItemStockAvailability,
    StockAvailabilityResponse,
    StockStatus,
    WarehouseStock,
)

DEFAULT_LOW_STOCK_THRESHOLD = 5.0
STOCK_CACHE_TTL_SECONDS = 60.0


class StockService:
    """Stock evaluation service determining sellability for cart abandonment agents."""

    def __init__(
        self,
        client: ZohoClient,
        default_low_stock_threshold: float = DEFAULT_LOW_STOCK_THRESHOLD,
        cache_ttl: float = STOCK_CACHE_TTL_SECONDS,
    ) -> None:
        self.client = client
        self.default_low_stock_threshold = default_low_stock_threshold
        self.cache_ttl = cache_ttl

    async def get_stock_availability(
        self,
        skus_or_ids: list[str],
        bypass_cache: bool = False,
    ) -> StockAvailabilityResponse:
        """Evaluate stock availability for up to 20 SKUs or item IDs (FR-5)."""
        if not skus_or_ids:
            raise InputValidationError(
                field="skus_or_ids",
                value="[]",
                reason="At least one SKU or item ID must be provided.",
            )
        if len(skus_or_ids) > 20:
            raise InputValidationError(
                field="skus_or_ids",
                value=f"List of {len(skus_or_ids)} items",
                reason="Batch stock check cannot exceed 20 items per request.",
            )

        # Validate inputs with query builder
        sanitized_identifiers: list[str] = []
        for ident in skus_or_ids:
            ident_clean = ident.strip()
            if not ident_clean:
                continue
            # Validate SKU pattern or numeric ID pattern
            if ident_clean.isdigit():
                ValidatedQueryBuilder.validate_numeric_id(ident_clean, field_name="skus_or_ids")
            else:
                ValidatedQueryBuilder.validate_sku(ident_clean, field_name="skus_or_ids")
            sanitized_identifiers.append(ident_clean)

        results: list[ItemStockAvailability] = []
        all_cached = True
        latest_as_of = datetime.now(UTC).isoformat()

        # Fetch items from Zoho
        for ident in sanitized_identifiers:
            item_raw: dict[str, Any] | None = None
            is_cached = False
            as_of_str = latest_as_of

            # Try direct item_id lookup first if numeric or prefixed
            if ident.isdigit() or ident.startswith("item_"):
                try:
                    data, is_cached, as_of_str = await self.client.get(
                        f"/items/{ident}",
                        cache_ttl=self.cache_ttl,
                        bypass_cache=bypass_cache,
                    )
                    item_raw = data.get("item")
                except NotFoundError:
                    item_raw = None

            # Fallback to search by SKU or name
            if not item_raw:
                try:
                    data, is_cached, as_of_str = await self.client.get(
                        "/items",
                        params={"search_text": ident, "per_page": "10"},
                        cache_ttl=self.cache_ttl,
                        bypass_cache=bypass_cache,
                    )
                    items_list = data.get("items", [])
                    # Find exact SKU match or exact ID match
                    for it in items_list:
                        if (
                            it.get("sku", "").lower() == ident.lower()
                            or str(it.get("item_id")) == ident
                        ):
                            item_raw = it
                            break
                    if not item_raw and items_list:
                        item_raw = items_list[0]
                except NotFoundError:
                    item_raw = None

            if not is_cached:
                all_cached = False

            if not item_raw:
                # SKU not found in Zoho catalog
                results.append(
                    ItemStockAvailability(
                        item_id="unknown",
                        sku=ident,
                        name="Unknown Product",
                        status=StockStatus.UNKNOWN,
                        quantity_sellable=0.0,
                        source_stock_field="none",
                        reorder_level=self.default_low_stock_threshold,
                        warehouses=[],
                        as_of=as_of_str,
                        cached=is_cached,
                    )
                )
                continue

            # Determine sellable quantity (FR-6.1, Assumption A1)
            # Prioritize actual_available_stock -> available_stock -> stock_on_hand
            stock_field = "actual_available_stock"
            raw_qty = item_raw.get("actual_available_stock")
            if raw_qty is None:
                stock_field = "available_stock"
                raw_qty = item_raw.get("available_stock")
            if raw_qty is None:
                stock_field = "stock_on_hand"
                raw_qty = item_raw.get("stock_on_hand", 0.0)

            sellable_qty = float(raw_qty or 0.0)
            reorder_lvl = float(item_raw.get("reorder_level") or self.default_low_stock_threshold)
            if reorder_lvl <= 0:
                reorder_lvl = self.default_low_stock_threshold

            # Derive stock status (FR-5.2)
            if sellable_qty <= 0:
                status = StockStatus.OUT_OF_STOCK
            elif sellable_qty <= reorder_lvl:
                status = StockStatus.LOW_STOCK
            else:
                status = StockStatus.IN_STOCK

            # Warehouse breakdown
            warehouses_raw = item_raw.get("warehouses", [])
            wh_list: list[WarehouseStock] = []
            if isinstance(warehouses_raw, list):
                for wh in warehouses_raw:
                    if isinstance(wh, dict):
                        wh_list.append(
                            WarehouseStock(
                                warehouse_id=str(wh.get("warehouse_id", "")),
                                warehouse_name=str(wh.get("warehouse_name", "Main Warehouse")),
                                stock_on_hand=float(wh.get("warehouse_stock_on_hand", 0.0)),
                                available_stock=float(wh.get("warehouse_available_stock", 0.0)),
                            )
                        )

            results.append(
                ItemStockAvailability(
                    item_id=str(item_raw.get("item_id", "")),
                    sku=str(item_raw.get("sku", ident)),
                    name=str(item_raw.get("name", "Product")),
                    status=status,
                    quantity_sellable=sellable_qty,
                    source_stock_field=stock_field,
                    reorder_level=reorder_lvl,
                    unit=str(item_raw.get("unit", "pcs")),
                    warehouses=wh_list,
                    as_of=as_of_str,
                    cached=is_cached,
                )
            )

        return StockAvailabilityResponse(
            items=results,
            as_of=latest_as_of,
            cached=all_cached and len(results) > 0,
            truncated=False,
        )
