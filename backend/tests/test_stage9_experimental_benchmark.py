"""
Stage 9 Automated Experimental Verification Tests
=================================================
Verifies that:
1. All 7 algorithms (FCFS, SPT, EDD, CR, AGING, CPSAT, EPN) produce valid,
   constraint-compliant schedules across all 4 experimental tiers, including
   dynamic in-flight running operations and machine breakdowns.
2. The Stage 9 benchmark artifacts (raw CSV/JSON, summary CSV/JSON, manifest, plots)
   exist and record 280 trials with 0 constraint violations.
"""
import json
from pathlib import Path
import pytest

from app.experiments.stage9_benchmark import (
    ALGORITHMS,
    generate_tier_instance,
    verify_schedule_exhaustive
)
from app.schemas.models import Job, Machine
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer
from app.ml.inference.epn_scheduler import EPNJobShopScheduler


@pytest.mark.parametrize("tier_id,seed", [
    ("TIER1_SMALL", 1001),
    ("TIER2_MEDIUM", 2001),
    ("TIER3_DYNAMIC_BREAKDOWN", 3001),
    ("TIER4_LARGE_SCALE", 4001),
])
def test_all_algorithms_feasible_across_tiers(tier_id, seed):
    """Every algorithm must produce a 100% valid schedule on each benchmark tier."""
    jobs, machines, current_time, meta = generate_tier_instance(tier_id, seed)
    epn = EPNJobShopScheduler()

    for algo in ALGORITHMS:
        j_copy = [Job(**j.model_dump()) for j in jobs]
        m_copy = [Machine(**m.model_dump()) for m in machines]

        if algo == "CPSAT":
            res = CPSATSchedulingOptimizer.optimize(j_copy, m_copy, current_time=current_time, time_limit_seconds=1.5)
        elif algo == "EPN":
            res = epn.schedule(j_copy, m_copy, current_time=current_time)
        else:
            res = DispatchHeuristicScheduler.schedule(j_copy, m_copy, current_time=current_time, rule=algo)

        is_valid, errs = verify_schedule_exhaustive(res.tasks, j_copy, m_copy, current_time)
        assert is_valid, f"{algo} failed exhaustive validation on {tier_id} (seed={seed}): {errs}"
        assert len(res.tasks) == meta["total_operations"]


def test_stage9_benchmark_artifacts_and_manifest_integrity():
    """Verify the generated Stage 9 benchmark files exist and match the 280-trial protocol."""
    out_dir = Path(__file__).resolve().parent.parent / "experiments" / "stage9_benchmark"
    assert (out_dir / "stage9_raw_results.csv").exists()
    assert (out_dir / "stage9_raw_results.json").exists()
    assert (out_dir / "stage9_summary_table.csv").exists()
    assert (out_dir / "stage9_summary_table.json").exists()
    assert (out_dir / "stage9_manifest.json").exists()

    with open(out_dir / "stage9_manifest.json", "r") as f:
        manifest = json.load(f)

    assert manifest["total_trials"] == 280
    assert manifest["total_violations"] == 0
    assert manifest["epn_checkpoint"]["loaded"] is True

