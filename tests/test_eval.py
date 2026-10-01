"""Unit and regression tests for evaluation harness and simulation determinism (FR-10)."""

import json
from pathlib import Path

import pytest

from eval.run_eval import RESULTS_DIR
from eval.run_eval import main as run_eval_main


@pytest.mark.asyncio
async def test_eval_harness_determinism_and_labels(tmp_path: Path) -> None:
    """# FR-10: Verify eval runs produce deterministic artifacts with SIMULATED label."""
    await run_eval_main()

    summary_file = RESULTS_DIR / "summary.json"
    nudge_file = RESULTS_DIR / "nudge_results.json"
    dispute_file = RESULTS_DIR / "dispute_results.json"

    assert summary_file.exists()
    assert nudge_file.exists()
    assert dispute_file.exists()

    with open(summary_file, encoding="utf-8") as f:
        summary_1 = json.load(f)

    # Assert SIMULATED label
    assert summary_1["simulation_mode"] == "SIMULATED"
    assert "SIMULATED" in summary_1["disclaimer"]
    assert summary_1["seed"] == 42

    # Assert Metric targets
    m = summary_1["metrics_summary"]
    assert m["M1_wasted_nudges_baseline_pct"] > 20.0
    assert m["M1_wasted_nudges_connector_pct"] == 0.0
    assert m["M1_discount_budget_saved_inr"] > 10000.0
    assert m["M2_dispute_evidence_complete_pct"] > 40.0
    assert m["M3_cart_api_calls_per_decision"] < 0.5
    assert m["M3_cache_hit_pct"] >= 80.0

    # Rerun and verify byte-identical reproduction
    with open(summary_file, encoding="utf-8") as f:
        raw_1 = f.read()

    await run_eval_main()

    with open(summary_file, encoding="utf-8") as f:
        raw_2 = f.read()

    assert raw_1 == raw_2
