"""Chargeback Dispute Evidence Evaluation (FR-10, M2, M3).

Evaluates fulfillment evidence compilation over 40 seeded fictional dispute cases.
Demonstrates automated packaging vs partial missing field enumeration.
"""

from collections import Counter
from typing import Any

from zoho_inventory_connector.models.evidence import EvidenceCompleteness
from zoho_inventory_connector.services.dispute_service import DisputeService


async def run_dispute_evaluation(
    dispute_cases: list[dict[str, Any]],
    dispute_service: DisputeService,
) -> dict[str, Any]:
    """Evaluate dispute fulfillment evidence completeness and missing field enumeration."""
    total_cases = len(dispute_cases)
    initial_api_calls = dispute_service.client.metrics.calls_made

    completeness_counts: Counter[str] = Counter()
    missing_fields_counter: Counter[str] = Counter()
    documented_complete_count = 0
    mock_delivery_date_count = 0
    detailed_cases: list[dict[str, Any]] = []

    for case in dispute_cases:
        so_id = case["salesorder_id"]
        evidence = await dispute_service.get_order_fulfillment_evidence(so_id)

        documented_fields = (
            evidence.sales_order,
            evidence.invoice,
            evidence.package,
            evidence.delivery_status,
            evidence.carrier,
            evidence.tracking_number,
        )
        if all(field.status == "present" for field in documented_fields):
            documented_complete_count += 1
        if evidence.delivery_date.status == "present":
            mock_delivery_date_count += 1

        completeness_counts[evidence.completeness.value] += 1
        for field in evidence.missing_fields:
            missing_fields_counter[field] += 1

        detailed_cases.append(
            {
                "dispute_id": case["dispute_id"],
                "salesorder_id": so_id,
                "salesorder_number": case["salesorder_number"],
                "dispute_amount_inr": case["dispute_amount_inr"],
                "completeness": evidence.completeness.value,
                "missing_fields": evidence.missing_fields,
                "fulfillment_summary": evidence.fulfillment_summary,
                "cached": evidence.cached,
            }
        )

    complete_count = completeness_counts[EvidenceCompleteness.COMPLETE.value]
    partial_count = completeness_counts[EvidenceCompleteness.PARTIAL.value]
    none_count = completeness_counts[EvidenceCompleteness.NONE.value]

    complete_pct = round((complete_count / total_cases) * 100, 2)
    partial_pct = round((partial_count / total_cases) * 100, 2)
    none_pct = round((none_count / total_cases) * 100, 2)

    total_api_calls = dispute_service.client.metrics.calls_made - initial_api_calls
    calls_per_case = round(total_api_calls / total_cases, 2)
    quota_limit = dispute_service.client.metrics.daily_quota_limit
    quota_consumed_pct = round((total_api_calls / quota_limit) * 100, 2) if quota_limit else 0.0

    return {
        "simulation_mode": "SIMULATED",
        "total_dispute_cases": total_cases,
        "mock_all_fields_completeness": {
            "complete_evidence_count": complete_count,
            "complete_evidence_pct": complete_pct,
            "partial_evidence_count": partial_count,
            "partial_evidence_pct": partial_pct,
            "no_evidence_count": none_count,
            "no_evidence_pct": none_pct,
        },
        "zoho_documented_evidence": {
            "definition": "Order, invoice, package, shipment status, carrier, and tracking number are present.",
            "complete_count": documented_complete_count,
            "complete_pct": round((documented_complete_count / total_cases) * 100, 2),
        },
        "delivery_proof": {
            "definition": "A carrier-confirmed delivered-at timestamp or equivalent.",
            "mock_delivery_date_field_present_count": mock_delivery_date_count,
            "mock_delivery_date_field_present_pct": round(
                (mock_delivery_date_count / total_cases) * 100, 2
            ),
            "schema_faithful_available_count": 0,
            "schema_faithful_available_pct": 0.0,
            "note": "SIMULATED 0/40 uses the pre-live reading of the public Zoho schema. The live response included shipment_delivered_date, blank on three checked shipments; its source is unverified and this does not establish carrier proof. Carrier integration remains the long-term route to independent proof.",
        },
        "missing_fields_breakdown": dict(missing_fields_counter),
        "ops_impact": {
            "evidence_checklist_complete_cases": complete_count,
            "ops_assisted_cases": partial_count,
            "unsupported_cases": none_count,
            "api_calls_per_dispute_case": calls_per_case,
            "upstream_api_calls": total_api_calls,
            "zoho_free_tier_quota_consumed_pct": quota_consumed_pct,
        },
    }
