"""Dispute fulfillment evidence synthesis service (FR-5.4).

Compiles verified fulfillment artifacts across sales orders, invoices, packages,
and carrier shipment orders for chargeback rebuttal assembly.
"""

from datetime import UTC, datetime
from typing import Any

from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.client.errors import NotFoundError
from zoho_inventory_connector.client.parsing import parse_upstream_float
from zoho_inventory_connector.client.query_builder import ValidatedQueryBuilder
from zoho_inventory_connector.models.evidence import (
    EvidenceCompleteness,
    EvidenceField,
    OrderFulfillmentEvidence,
)


class DisputeService:
    """Service to assemble chargeback rebuttal fulfillment proof without speculation (FR-5.4)."""

    def __init__(self, client: ZohoClient) -> None:
        self.client = client

    async def get_order_fulfillment_evidence(
        self,
        salesorder_id: str,
        bypass_cache: bool = False,
    ) -> OrderFulfillmentEvidence:
        """Compose unbroken fulfillment evidence chain for dispute rebuttal.

        Never guesses missing tracking numbers or delivery timestamps.
        """
        # Validate ID with query builder (FR-13)
        so_id_clean = ValidatedQueryBuilder.validate_numeric_id(
            salesorder_id, field_name="salesorder_id"
        )
        as_of_now = datetime.now(UTC).isoformat()
        is_cached = False

        # 1. Fetch Sales Order
        try:
            so_res, is_cached, as_of_now = await self.client.get(
                f"/salesorders/{so_id_clean}",
                cache_ttl=120.0,
                bypass_cache=bypass_cache,
            )
            so_data: dict[str, Any] = so_res.get("salesorder", {})
        except NotFoundError:
            return OrderFulfillmentEvidence(
                salesorder_id=so_id_clean,
                completeness=EvidenceCompleteness.NONE,
                missing_fields=[
                    "sales_order",
                    "invoice",
                    "package",
                    "carrier",
                    "tracking_number",
                    "delivery_date",
                ],
                sales_order=EvidenceField.not_available(
                    "salesorders", "Sales order not found in Zoho Inventory"
                ),
                invoice=EvidenceField.not_available("invoices", "No associated invoices found"),
                package=EvidenceField.not_available("packages", "No associated packaging found"),
                carrier=EvidenceField.not_available("shipmentorders", "No carrier assigned"),
                tracking_number=EvidenceField.not_available(
                    "shipmentorders", "No tracking number recorded"
                ),
                shipment_date=EvidenceField.not_available("shipmentorders", "No shipment date"),
                delivery_date=EvidenceField.not_available(
                    "shipmentorders", "No delivery confirmation"
                ),
                delivery_status=EvidenceField.not_available("shipmentorders", "Status unknown"),
                fulfillment_summary="Order record does not exist in Zoho Inventory; rebuttal cannot be supported.",
                as_of=as_of_now,
                cached=is_cached,
            )

        # 2. Extract nested or fetch sub-resources (invoices, packages, shipments)
        invoices: list[dict[str, Any]] = so_data.get("invoices", [])
        packages: list[dict[str, Any]] = so_data.get("packages", [])
        shipments: list[dict[str, Any]] = so_data.get("shipments", [])

        # If sub-resources weren't embedded, fetch separately
        if not invoices:
            try:
                inv_res, _, _ = await self.client.get(
                    "/invoices",
                    params={"salesorder_id": so_id_clean},
                    cache_ttl=120.0,
                    bypass_cache=bypass_cache,
                )
                invoices = inv_res.get("invoices", [])
            except NotFoundError:
                invoices = []

        if not packages:
            try:
                pkg_res, _, _ = await self.client.get(
                    "/packages",
                    params={"salesorder_id": so_id_clean},
                    cache_ttl=120.0,
                    bypass_cache=bypass_cache,
                )
                packages = pkg_res.get("packages", [])
            except NotFoundError:
                packages = []

        if not shipments:
            try:
                shp_res, _, _ = await self.client.get(
                    "/shipmentorders",
                    params={"salesorder_id": so_id_clean},
                    cache_ttl=120.0,
                    bypass_cache=bypass_cache,
                )
                shipments = shp_res.get("shipmentorders", [])
            except NotFoundError:
                shipments = []

        # 3. Compile Individual Evidence Fields
        missing_fields: list[str] = []

        # Sales Order Field
        so_num = str(so_data.get("salesorder_number", ""))
        so_date = str(so_data.get("date", ""))
        so_status = str(so_data.get("status", ""))
        order_field = EvidenceField.present(
            value=so_num,
            source="salesorders",
            details={
                "status": so_status,
                "date": so_date,
                "total": parse_upstream_float(so_data.get("total"), "salesorder.total"),
                "currency": str(so_data.get("currency_code", "INR")),
            },
        )

        # Invoice Field
        if invoices:
            inv = invoices[0]
            invoice_field = EvidenceField.present(
                value=str(inv.get("invoice_number", "")),
                source="invoices",
                details={
                    "status": str(inv.get("status", "")),
                    "total": parse_upstream_float(inv.get("total"), "invoice.total"),
                    "date": str(inv.get("date", "")),
                },
            )
        else:
            invoice_field = EvidenceField.not_available(
                "invoices", "No tax invoice issued for this sales order"
            )
            missing_fields.append("invoice")

        # Package Field
        if packages:
            pkg = packages[0]
            package_field = EvidenceField.present(
                value=str(pkg.get("package_number", "")),
                source="packages",
                details={
                    "status": str(pkg.get("status", "")),
                    "date": str(pkg.get("date", "")),
                },
            )
        else:
            package_field = EvidenceField.not_available(
                "packages", "No packaging slips created for items"
            )
            missing_fields.append("package")

        # Shipment / Carrier / Tracking Fields
        active_shipment = shipments[0] if shipments else None

        if active_shipment and active_shipment.get("carrier"):
            carrier_field = EvidenceField.present(
                value=str(active_shipment["carrier"]),
                source="shipmentorders",
            )
        else:
            carrier_field = EvidenceField.not_available(
                "shipmentorders", "Shipping carrier not designated"
            )
            missing_fields.append("carrier")

        if active_shipment and active_shipment.get("tracking_number"):
            tracking_field = EvidenceField.present(
                value=str(active_shipment["tracking_number"]),
                source="shipmentorders",
            )
        else:
            tracking_field = EvidenceField.not_available(
                "shipmentorders", "Courier tracking number not recorded"
            )
            missing_fields.append("tracking_number")

        if active_shipment and active_shipment.get("shipment_date"):
            shipment_date_field = EvidenceField.present(
                value=str(active_shipment["shipment_date"]),
                source="shipmentorders",
            )
        else:
            shipment_date_field = EvidenceField.not_available(
                "shipmentorders", "Shipment dispatch date missing"
            )
            missing_fields.append("shipment_date")

        if active_shipment and active_shipment.get("delivery_date"):
            delivery_date_field = EvidenceField.present(
                value=str(active_shipment["delivery_date"]),
                source="shipmentorders",
            )
        else:
            delivery_date_field = EvidenceField.not_available(
                "shipmentorders", "Delivery date confirmation missing"
            )
            missing_fields.append("delivery_date")

        if active_shipment and active_shipment.get("status"):
            delivery_status_field = EvidenceField.present(
                value=str(active_shipment["status"]),
                source="shipmentorders",
            )
        else:
            delivery_status_field = EvidenceField.not_available(
                "shipmentorders", "Delivery status missing"
            )
            missing_fields.append("delivery_status")

        # 4. Assess Completeness and Summary
        if not missing_fields:
            completeness = EvidenceCompleteness.COMPLETE
            summary = (
                f"Order {so_num} fulfilled successfully via {carrier_field.value} "
                f"(Tracking #{tracking_field.value}). Zoho record lists delivery date {delivery_date_field.value}; "
                "carrier confirmation is not independently verified."
            )
        else:
            completeness = EvidenceCompleteness.PARTIAL
            missing_str = ", ".join(missing_fields)
            summary = (
                f"Order {so_num} has partial fulfillment proof in Zoho. "
                f"Missing critical evidence: [{missing_str}]."
            )

        return OrderFulfillmentEvidence(
            salesorder_id=so_id_clean,
            completeness=completeness,
            missing_fields=missing_fields,
            sales_order=order_field,
            invoice=invoice_field,
            package=package_field,
            carrier=carrier_field,
            tracking_number=tracking_field,
            shipment_date=shipment_date_field,
            delivery_date=delivery_date_field,
            delivery_status=delivery_status_field,
            order_date=so_date or None,
            fulfillment_summary=summary,
            as_of=as_of_now,
            cached=is_cached,
        )
