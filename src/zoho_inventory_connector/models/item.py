"""Pydantic projection models for Inventory items and stock availability (FR-5, FR-6)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StockStatus(StrEnum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


class WarehouseStock(BaseModel):
    """Stock breakdown by individual warehouse location."""

    model_config = ConfigDict(frozen=True)

    warehouse_id: str
    warehouse_name: str
    stock_on_hand: float = 0.0
    available_stock: float = 0.0


class ItemProjection(BaseModel):
    """Normalized projection of a Zoho item record (FR-6.1)."""

    model_config = ConfigDict(extra="ignore")

    item_id: str
    name: str
    sku: str
    status: str = "active"
    price: float = Field(default=0.0, description="Item sales price")
    currency_code: str = "INR"
    stock_on_hand: float = 0.0
    actual_available_stock: float = 0.0
    reorder_level: float = 0.0
    unit: str = "pcs"
    description: str | None = None


class ItemStockAvailability(BaseModel):
    """Sellable stock decision primitive for cart abandonment agents (FR-5)."""

    model_config = ConfigDict(extra="ignore")

    item_id: str
    sku: str
    name: str
    status: StockStatus
    quantity_sellable: float = Field(
        ...,
        description="True sellable inventory count accounting for committed sales orders",
    )
    source_stock_field: str = Field(
        default="actual_available_stock",
        description="Zoho field name used to derive sellable quantity (FR-6.1)",
    )
    reorder_level: float = 0.0
    unit: str = "pcs"
    warehouses: list[WarehouseStock] = Field(default_factory=list)
    as_of: str = Field(..., description="ISO 8601 UTC timestamp of data retrieval (FR-4.2)")
    cached: bool = Field(default=False, description="Whether data was served from local cache")


class StockAvailabilityResponse(BaseModel):
    """Batch stock availability response for up to 20 SKUs or Item IDs."""

    items: list[ItemStockAvailability]
    as_of: str
    cached: bool = False
    truncated: bool = False
