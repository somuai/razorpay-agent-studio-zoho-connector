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
    stock_on_hand: float | None = None
    available_stock: float | None = None


class ItemProjection(BaseModel):
    """Normalized projection of a Zoho item record (FR-6.1)."""

    model_config = ConfigDict(extra="ignore")

    item_id: str
    name: str
    sku: str
    status: str = "active"
    price: float = Field(default=0.0, description="Item sales price")
    currency_code: str = "INR"
    # Missing inventory fields must remain unavailable, not be turned into zero.
    stock_on_hand: float | None = None
    actual_available_stock: float | None = None
    reorder_level: float | None = None
    unit: str = "pcs"
    description: str | None = None


class ItemStockAvailability(BaseModel):
    """Advisory availability projection for cart agents; not a reservation (FR-5)."""

    model_config = ConfigDict(extra="ignore")

    item_id: str
    sku: str
    name: str
    status: StockStatus
    availability_note: str | None = Field(
        default=None,
        description="Why availability is unknown when the upstream schema lacks a usable stock value",
    )
    quantity_sellable: float = Field(
        ...,
        description="Quantity from the selected Zoho availability field; merchant sellability rules must be confirmed",
    )
    source_stock_field: str = Field(
        default="actual_available_stock",
        description="Zoho field name used for the advisory availability quantity (FR-6.1)",
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
