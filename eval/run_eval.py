"""Evaluation Orchestrator for Agent Studio Zoho Connector (FR-10).

Executes deterministic simulations for:
1. Abandoned Cart Nudge Policy (200 seeded events)
2. Chargeback Dispute Evidence Compilation (40 seeded cases)

Outputs human-readable Markdown summary tables to stdout and writes
deterministic JSON artifacts to eval/results/.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from eval.dispute_eval import run_dispute_evaluation
from eval.nudge_sim import run_nudge_simulation
from eval.seed_data import generate_eval_datasets
from mock_zoho.app import app
from mock_zoho.faults import faults
from zoho_inventory_connector.auth.token_manager import TokenManager
from zoho_inventory_connector.client.client import ZohoClient
from zoho_inventory_connector.ratelimit.clock import VirtualClock
from zoho_inventory_connector.services.dispute_service import DisputeService
from zoho_inventory_connector.services.stock_service import StockService

RESULTS_DIR = Path("eval/results")


async def main() -> None:
    faults.reset()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Initialize deterministic mock client with VirtualClock
    clock = VirtualClock()
    http_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    token_manager = TokenManager(
        client_id="mock_client_id",
        client_secret="mock_client_secret",
        refresh_token="mock_refresh_token",
        clock=clock,
        http_client=http_client,
    )
    token_manager._access_token = "zoho_access_mock_token_12345"
    token_manager._expires_at_mono = clock.monotonic() + 3600.0

    client = ZohoClient(
        token_manager=token_manager,
        org_id="org_kaveri_blr_001",
        clock=clock,
        http_client=http_client,
        base_url_override="http://test/inventory/v1",
    )

    stock_service = StockService(client=client, default_low_stock_threshold=5.0)
    dispute_service = DisputeService(client=client)

    # 2. Load Seed Data
    datasets = generate_eval_datasets()
    cart_events = datasets["cart_events"]
    dispute_cases = datasets["dispute_cases"]

    # 3. Run Evaluations
    nudge_results = await run_nudge_simulation(cart_events, stock_service)
    dispute_results = await run_dispute_evaluation(dispute_cases, dispute_service)

    summary: dict[str, Any] = {
        "status": "COMPLETED",
        "simulation_mode": "SIMULATED",
        "disclaimer": (
            "ALL METRICS ARE SIMULATED ON FICTIONAL DATA (seed=42) FOR KAVERI HOME GOODS. "
            "NEVER CONSTRUE AS PRODUCTION RESULTS."
        ),
        "seed": 42,
        "quota_feasibility": {
            "simulation_mode": "SIMULATED",
            "daily_quota_assumption": 1000,
            "calls_per_decision": nudge_results["efficiency_and_cost"]["api_calls_per_decision"],
            "rows": [
                {
                    "quota_available_pct": pct,
                    "calls_available": int(1000 * pct / 100),
                    "decisions_per_day": int(
                        (1000 * pct / 100)
                        / nudge_results["efficiency_and_cost"]["api_calls_per_decision"]
                    ),
                }
                for pct in (100, 50, 25)
            ],
            "assumption": "The connector is the only consumer of its allocated share; capacity falls with shared org usage and changes with calls per decision/cache behavior.",
        },
        "metrics_summary": {
            "M1_wasted_nudges_baseline_pct": nudge_results["baseline_policy"]["wasted_nudges_pct"],
            "M1_wasted_nudges_connector_pct": nudge_results["connector_aware_policy"][
                "wasted_nudges_pct"
            ],
            "M1_discount_budget_saved_inr": nudge_results["connector_aware_policy"][
                "discount_budget_saved_inr"
            ],
            "M2_dispute_evidence_complete_pct": dispute_results["completeness_summary"][
                "complete_evidence_pct"
            ],
            "M2_dispute_evidence_partial_pct": dispute_results["completeness_summary"][
                "partial_evidence_pct"
            ],
            "M3_cart_api_calls_per_decision": nudge_results["efficiency_and_cost"][
                "api_calls_per_decision"
            ],
            "M3_cache_hit_pct": nudge_results["efficiency_and_cost"]["cache_hit_pct"],
            "M3_zoho_free_tier_quota_consumed_pct": nudge_results["efficiency_and_cost"][
                "zoho_free_tier_quota_consumed_pct"
            ],
            "M3_total_calls_both_sims": nudge_results["efficiency_and_cost"]["api_calls_made"]
            + dispute_results["ops_impact"]["upstream_api_calls"],
            "M3_total_quota_both_sims_pct": round(
                (
                    nudge_results["efficiency_and_cost"]["api_calls_made"]
                    + dispute_results["ops_impact"]["upstream_api_calls"]
                )
                / 1000.0
                * 100,
                2,
            ),
        },
        "nudge_simulation": nudge_results,
        "dispute_evaluation": dispute_results,
    }

    # 4. Save Deterministic Artifacts
    with open(RESULTS_DIR / "nudge_results.json", "w", encoding="utf-8") as f:
        json.dump(nudge_results, f, indent=2, sort_keys=True)

    with open(RESULTS_DIR / "dispute_results.json", "w", encoding="utf-8") as f:
        json.dump(dispute_results, f, indent=2, sort_keys=True)

    with open(RESULTS_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)

    # 5. Print Markdown Tables to stdout
    base = nudge_results["baseline_policy"]
    conn = nudge_results["connector_aware_policy"]
    eff = nudge_results["efficiency_and_cost"]
    disp = dispute_results["completeness_summary"]

    print("\n" + "=" * 80)
    print("RAZORPAY AGENT STUDIO - ZOHO INVENTORY CONNECTOR EVALUATION REPORT")
    print("Mode: SIMULATED | Merchant: Kaveri Home Goods (Fictional) | Seed: 42")
    print("=" * 80 + "\n")

    print("### METRIC 1: SIMULATED mechanism check (N = 200 fictional carts)\n")
    print(
        "The baseline fixture labels 27% of carts out of stock. The connector-aware zero is guaranteed by the policy rule that suppresses every cart labeled out of stock; neither is measured merchant impact.\n"
    )
    print(
        "| Metric / Policy Attribute | Baseline Policy (Unaware) | Connector-Aware Agent | Delta / Impact |"
    )
    print("|---|:---:|:---:|:---:|")
    print(
        f"| Nudges Sent | {base['nudges_sent']} | {conn['nudges_sent']} | -{conn['suppressed_nudges']} out-of-stock suppressed |"
    )
    print(
        f"| Nudges to carts with no out-of-stock item | {base['correctly_nudged_count']} | {conn['correctly_nudged_count']} | Seeded availability only; low-stock treatment differs by policy |"
    )
    print(
        f"| Wasted Nudges (Sent for Unavailable SKUs) | {base['wasted_nudges_count']} ({base['wasted_nudges_pct']}%) | {conn['wasted_nudges_count']} ({conn['wasted_nudges_pct']}%) | Policy mechanism check only |"
    )
    print(
        f"| Scarcity Nudges (No Discount Offered) | 0 | {conn['scarcity_no_discount_nudges']} | Driven by stock urgency |"
    )
    print(
        f"| Total Discount Disbursed (Fictional INR) | ₹{base['total_discount_disbursed_inr']:,.2f} | ₹{conn['total_discount_disbursed_inr']:,.2f} | ₹{conn['discount_budget_saved_inr']:,.2f} difference in fictional policy arithmetic |"
    )
    print(
        f"| Wasted Discount on Zero Stock (Fictional INR) | ₹{base['wasted_discount_inr']:,.2f} | ₹{conn['wasted_discount_inr']:,.2f} | SIMULATED fixture arithmetic |"
    )

    print("\n### SIMULATED sensitivity sweep (same fictional discount offers; seed 42)\n")
    print(
        "| Out-of-stock share assumption | Unavailable nudges: baseline → aware | Wasted discount (fictional INR): baseline → aware |"
    )
    print("|---:|---:|---:|")
    for row in nudge_results["sensitivity_sweep"]:
        print(
            f"| {row['out_of_stock_rate_pct']}% | {row['baseline_unavailable_nudges']} → {row['connector_aware_unavailable_nudges']} | ₹{row['baseline_wasted_discount_inr']:,.2f} → ₹{row['connector_aware_wasted_discount_inr']:,.2f} |"
        )

    print("\n### METRIC 2: Chargeback Dispute Evidence Completeness (N = 40 Cases)\n")
    print("| Evidence Classification | Cases | Pct (%) | Ops Workflow Action |")
    print("|---|:---:|:---:|---|")
    print(
        f"| Complete in mock fields (includes fictional delivery_date) | {disp['complete_evidence_count']} | **{disp['complete_evidence_pct']}%** | Fixture completeness only; does not prove live Zoho/carrier delivery evidence |"
    )
    print(
        f"| Partial Evidence (Missing tracking / delivery confirmation) | {disp['partial_evidence_count']} | **{disp['partial_evidence_pct']}%** | Ops triage with exact missing fields flagged |"
    )
    print(
        f"| No Evidence | {disp['no_evidence_count']} | {disp['no_evidence_pct']}% | Manual review; no evidence is inferred |"
    )

    print("\nMissing Fields Breakdown in Partial Disputes:")
    for field, count in dispute_results["missing_fields_breakdown"].items():
        print(f"  - `{field}`: missing in {count} cases")

    print("\n### METRIC 3: Agent Cost, Latency & Quota Efficiency\n")
    print(f"- Total Upstream API Calls (Nudge Sim): {eff['api_calls_made']}")
    print(f"- Cache Hits (TTL 60s): {eff['cache_hits']} ({eff['cache_hit_pct']}%)")
    print(f"- Upstream API Calls per Nudge Decision: {eff['api_calls_per_decision']}")
    print(
        f"- Deterministic virtual-clock p50/p95 tool latency: "
        f"{eff['tool_latency_p50_ms_virtual_clock']}/{eff['tool_latency_p95_ms_virtual_clock']} ms "
        "(not runtime latency)"
    )
    print(
        f"- Upstream API Calls per Dispute Case: {dispute_results['ops_impact']['api_calls_per_dispute_case']}"
    )
    print(
        f"- Daily Zoho Free-Tier Quota Consumed: {eff['zoho_free_tier_quota_consumed_pct']}% of 1,000 req/day limit"
    )
    print(
        f"- Combined quota estimate for both separate simulations: "
        f"{summary['metrics_summary']['M3_total_quota_both_sims_pct']}% of 1,000 requests/day"
    )
    print("\n### SIMULATED quota feasibility (1,000 calls/day cap assumption)\n")
    print(
        "| Share available to connector | Calls/day available | Decisions/day at 0.15 calls/decision |"
    )
    print("|---:|---:|---:|")
    for row in summary["quota_feasibility"]["rows"]:
        print(
            f"| {row['quota_available_pct']}% | {row['calls_available']} | {row['decisions_per_day']:,} |"
        )
    print(
        "Assumes no other connector consumes this allocation; shared usage and cache behavior change capacity.\n"
    )
    print("\n" + "=" * 80)
    print("ALL RESULTS ARE SIMULATED. End of Evaluation Report.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
