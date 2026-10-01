"""Dispute fulfillment evidence composition models (FR-5.4, FR-6.1)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EvidenceCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NONE = "none"


class EvidenceField(BaseModel):
    """Represents a single verified evidence artifact."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(..., description="'present' or 'not_available'")
    value: str | None = None
    source_resource: str = Field(..., description="Zoho upstream resource supplying this fact")
    details: dict[str, object] | None = None

    @classmethod
    def present(
        cls, value: str, source: str, details: dict[str, object] | None = None
    ) -> "EvidenceField":
        return cls(status="present", value=value, source_resource=source, details=details)

    @classmethod
    def not_available(
        cls, source: str, reason: str = "Record or field not found in Zoho"
    ) -> "EvidenceField":
        return cls(
            status="not_available", value=None, source_resource=source, details={"reason": reason}
        )


class OrderFulfillmentEvidence(BaseModel):
    """Composed dispute evidence primitive for Dispute Responder agents (FR-5.4)."""

    model_config = ConfigDict(extra="ignore")

    salesorder_id: str
    completeness: EvidenceCompleteness = Field(
        ...,
        description="'complete' (all evidence present), 'partial' (some fields missing), or 'none'",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Explicit enumeration of required fulfillment evidence missing from Zoho",
    )

    # Individual evidence components:
    sales_order: EvidenceField
    invoice: EvidenceField
    package: EvidenceField
    carrier: EvidenceField
    tracking_number: EvidenceField
    shipment_date: EvidenceField
    delivery_date: EvidenceField
    delivery_status: EvidenceField

    # Summary timeline
    order_date: str | None = None
    fulfillment_summary: str = Field(
        ...,
        description="Fact-based summary statement describing verified timeline without speculation",
    )
    as_of: str = Field(..., description="ISO 8601 UTC timestamp of evidence retrieval")
    cached: bool = False
