"""
Stage 9 Reproducible Experimental Benchmark Suite
=================================================
Evaluates FCFS, SPT, EDD, CR, AGING, Google OR-Tools CP-SAT, and PyTorch EPN
under identical, independently generated problem instances across four experimental tiers:

1. Tier 1 (Small Verification): 6 jobs, 5 machines, 3-5 ops/job, static arrivals (10 seeds: 1001-1010)
2. Tier 2 (Medium Industrial 10-Machine): 10 jobs, 10 machines, 4-5 ops/job, Poisson arrivals (10 seeds: 2001-2010)
3. Tier 3 (Dynamic In-Flight + Machine Breakdown): 12 jobs, 10 machines, current_time=15.0,
   completed & running operations locked, M2 DOWN for 25m (10 seeds: 3001-3010)
4. Tier 4 (Large Scalability Stress): 25 jobs, 10 machines, 5 ops/job, high contention (10 seeds: 4001-4010)

Every schedule returned by every algorithm on every instance is independently verified
using ScheduleValidator.validate() plus completeness, release-time, running-op lock,
and completed-op preservation checks. No failed trials are discarded.
"""
import csv
import json
import os
import platform
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Tuple

import numpy as np
import pandas as pd
import torch
import ortools

from app.schemas.models import (
    Job, Machine, Operation, ScheduledTask,
    MachineStatus, OperationStatus, JobStatus
)
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer
from app.ml.inference.epn_scheduler import EPNJobShopScheduler
from app.scheduling.validator import ScheduleValidator


ALGORITHMS = ["FCFS", "SPT", "EDD", "CR", "AGING", "CPSAT", "EPN"]


def generate_tier_instance(
    tier_id: str,
    seed: int
) -> Tuple[List[Job], List[Machine], float, Dict[str, Any]]:
    """
    Independently generates a deterministic problem instance (jobs, machines, current_time, metadata)
    from an explicit random seed.
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    if tier_id == "TIER1_SMALL":
        num_jobs = 6
        num_machines = 5
        min_ops, max_ops = 3, 5
        current_time = 0.0
        tightness = 1.2
        has_breakdown = False
        has_running = False
    elif tier_id == "TIER2_MEDIUM":
        num_jobs = 10
        num_machines = 10
        min_ops, max_ops = 4, 5
        current_time = 0.0
        tightness = 0.9 if (seed % 2 == 0) else 1.2
        has_breakdown = False
        has_running = False
    elif tier_id == "TIER3_DYNAMIC_BREAKDOWN":
        num_jobs = 12
        num_machines = 10
        min_ops, max_ops = 4, 5
        current_time = 15.0
        tightness = 1.0
        has_breakdown = True
        has_running = True
    elif tier_id == "TIER4_LARGE_SCALE":
        num_jobs = 25
        num_machines = 10
        min_ops, max_ops = 5, 5
        current_time = 0.0
        tightness = 0.85
        has_breakdown = False
        has_running = False
    else:
        raise ValueError(f"Unknown tier_id: {tier_id}")

    machines: List[Machine] = []
    for m_idx in range(1, num_machines + 1):
        mid = f"M{m_idx}"
        machines.append(
            Machine(
                machine_id=mid,
                name=f"Stage {m_idx} Station",
                capability=f"Process_{m_idx}",
                status=MachineStatus.IDLE,
                remaining_processing_time=0.0,
                total_busy_time=0.0
            )
        )

    jobs: List[Job] = []
    for j_idx in range(1, num_jobs + 1):
        jid = f"J{j_idx:03d}"
        route_len = rng.randint(min_ops, max_ops)
        m_seq = rng.sample(range(1, num_machines + 1), route_len)

        if tier_id == "TIER1_SMALL":
            arrival_t = 0.0
        elif tier_id == "TIER3_DYNAMIC_BREAKDOWN":
            # First 4 jobs arrived at 0.0, remaining jobs arrive dynamically between 5.0 and 30.0
            arrival_t = 0.0 if j_idx <= 4 else round(float(rng.uniform(5.0, 30.0)), 1)
        else:
            arrival_t = round(float(np_rng.exponential(8.0)), 1)

        ops: List[Operation] = []
        total_proc = 0.0
        for seq_i, m_num in enumerate(m_seq, start=1):
            dur = float(rng.randint(8, 30))
            total_proc += dur
            ops.append(
                Operation(
                    sequence=seq_i,
                    name=f"Op_{seq_i}",
                    machine_id=f"M{m_num}",
                    duration=dur,
                    setup_time=0.0,
                    status=OperationStatus.PENDING
                )
            )

        slack = float(rng.randint(15, 55)) * tightness
        due_date = round(arrival_t + total_proc + slack, 1)
        priority = rng.randint(1, 5)

        jobs.append(
            Job(
                job_id=jid,
                name=f"Order_{jid}",
                product_type="Precision Component",
                quantity=1,
                arrival_time=arrival_t,
                due_date=due_date,
                priority=priority,
                status=JobStatus.PENDING,
                operations=ops
            )
        )

    # For Tier 3: Inject realistic in-flight state at current_time = 15.0
    if has_running:
        # J001 Op1 completed at t=10.0 on its assigned machine; Op2 is RUNNING on M1 with 8m remaining
        j1 = jobs[0]
        j1.status = JobStatus.IN_PROGRESS
        j1.operations[0].machine_id = "M3"
        j1.operations[0].duration = 10.0
        j1.operations[0].status = OperationStatus.COMPLETED
        j1.operations[0].start_time = 0.0
        j1.operations[0].end_time = 10.0

        j1.operations[1].machine_id = "M1"
        j1.operations[1].duration = 13.0
        j1.operations[1].status = OperationStatus.RUNNING
        j1.operations[1].start_time = 10.0
        # Ensure remaining ops of J001 don't conflict with M1/M3 immediately
        for k in range(2, len(j1.operations)):
            j1.operations[k].machine_id = f"M{((k + 3) % num_machines) + 1}"

        # Lock M1 as BUSY with J001 Op2 (remaining = 8.0m -> finishes at t=23.0)
        m1 = next(m for m in machines if m.machine_id == "M1")
        m1.status = MachineStatus.BUSY
        m1.current_job_id = j1.job_id
        m1.current_operation_seq = 2
        m1.remaining_processing_time = 8.0

    if has_breakdown:
        # Set M2 as DOWN for 25.0 minutes (unavailable from t=15.0 until t=40.0)
        m2 = next(m for m in machines if m.machine_id == "M2")
        m2.status = MachineStatus.DOWN
        m2.remaining_processing_time = 25.0

    meta = {
        "tier_id": tier_id,
        "seed": seed,
        "num_jobs": num_jobs,
        "num_machines": num_machines,
        "total_operations": sum(len(j.operations) for j in jobs),
        "current_time": current_time,
        "tightness": tightness,
        "has_breakdown": has_breakdown,
        "has_running": has_running,
    }
    return jobs, machines, current_time, meta


def verify_schedule_exhaustive(
    tasks: List[ScheduledTask],
    jobs: List[Job],
    machines: List[Machine],
    current_time: float
) -> Tuple[bool, List[str]]:
    """
    Runs ScheduleValidator.validate() PLUS exhaustive checks:
    - Every operation of every non-completed job is present in tasks
    - Release time (arrival_time) respected for all pending operations
    - Completed operations retain exact start_time and end_time
    - Running operations retain is_running=True and end_time = current_time + remaining
    """
    is_valid, errors = ScheduleValidator.validate(tasks, machines, current_time=current_time)
    all_errors = list(errors)

    task_map: Dict[Tuple[str, int], ScheduledTask] = {
        (t.job_id, t.operation_sequence): t for t in tasks
    }
    machine_map: Dict[str, Machine] = {m.machine_id: m for m in machines}

    for j in jobs:
        if j.status == JobStatus.COMPLETED:
            continue
        for op in j.operations:
            key = (j.job_id, op.sequence)
            if key not in task_map:
                all_errors.append(f"Missing operation in schedule: Job {j.job_id} Op {op.sequence}")
                continue
            t = task_map[key]
            if op.status == OperationStatus.COMPLETED:
                if not t.is_completed:
                    all_errors.append(f"Completed Op {j.job_id}-Op{op.sequence} not marked is_completed")
                if op.end_time is not None and abs(t.end_time - op.end_time) > 1e-2:
                    all_errors.append(f"Completed Op {j.job_id}-Op{op.sequence} end_time altered: {t.end_time} != {op.end_time}")
            elif op.status == OperationStatus.RUNNING:
                if not t.is_running:
                    all_errors.append(f"Running Op {j.job_id}-Op{op.sequence} not marked is_running")
                m_obj = machine_map.get(op.machine_id)
                expected_end = current_time + (m_obj.remaining_processing_time if m_obj else op.duration)
                if abs(t.end_time - expected_end) > 1e-1:
                    all_errors.append(f"Running Op {j.job_id}-Op{op.sequence} end_time {t.end_time} != {expected_end}")
            else:
                # Pending operation must respect job arrival_time
                if t.start_time < j.arrival_time - 1e-4:
                    all_errors.append(
                        f"Release Time Violation: {j.job_id}-Op{op.sequence} starts at {t.start_time} < arrival {j.arrival_time}"
                    )

    return len(all_errors) == 0, all_errors


def run_stage9_benchmark() -> Dict[str, Any]:
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    out_dir = project_root / "backend" / "experiments" / "stage9_benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)

    epn_scheduler = EPNJobShopScheduler()

    tiers = [
        ("TIER1_SMALL", list(range(1001, 1011)), 2.0),
        ("TIER2_MEDIUM", list(range(2001, 2011)), 2.0),
        ("TIER3_DYNAMIC_BREAKDOWN", list(range(3001, 3011)), 2.0),
        ("TIER4_LARGE_SCALE", list(range(4001, 4011)), 2.5),
    ]

    records: List[Dict[str, Any]] = []
    violations_log: List[Dict[str, Any]] = []

    print("Starting Stage 9 Reproducible Experimental Benchmark Suite...")
    t_suite_start = time.perf_counter()

    for tier_id, seeds, cpsat_limit in tiers:
        print(f"  -> Running {tier_id} ({len(seeds)} instances, CP-SAT limit={cpsat_limit}s)...")
        for seed in seeds:
            jobs, machines, current_time, meta = generate_tier_instance(tier_id, seed)
            num_jobs = meta["num_jobs"]

            for algo in ALGORITHMS:
                # Deep-copy jobs/machines via Pydantic reconstruction to prevent any cross-algorithm mutation
                jobs_copy = [Job(**j.model_dump()) for j in jobs]
                machines_copy = [Machine(**m.model_dump()) for m in machines]

                t0 = time.perf_counter()
                solver_time_limit = cpsat_limit if algo == "CPSAT" else None
                epn_mode = "N/A"

                try:
                    if algo == "CPSAT":
                        res = CPSATSchedulingOptimizer.optimize(
                            jobs_copy, machines_copy, current_time=current_time, time_limit_seconds=cpsat_limit
                        )
                    elif algo == "EPN":
                        res = epn_scheduler.schedule(
                            jobs_copy, machines_copy, current_time=current_time
                        )
                        epn_mode = (
                            "NEURAL_INFERENCE"
                            if res.metrics.solver_status == "NEURAL_PREDICTED_FEASIBLE"
                            else "FALLBACK_SPT"
                        )
                    else:
                        res = DispatchHeuristicScheduler.schedule(
                            jobs_copy, machines_copy, current_time=current_time, rule=algo
                        )
                    wall_ms = (time.perf_counter() - t0) * 1000.0

                    is_valid, errs = verify_schedule_exhaustive(
                        res.tasks, jobs_copy, machines_copy, current_time
                    )
                    if not is_valid:
                        violations_log.append({
                            "tier_id": tier_id,
                            "seed": seed,
                            "algorithm": algo,
                            "errors": errs
                        })

                    mean_tardiness = round(res.metrics.total_tardiness / num_jobs, 2) if num_jobs > 0 else 0.0

                    records.append({
                        "tier_id": tier_id,
                        "seed": seed,
                        "num_jobs": num_jobs,
                        "num_machines": meta["num_machines"],
                        "total_operations": meta["total_operations"],
                        "current_time": current_time,
                        "has_breakdown": meta["has_breakdown"],
                        "has_running": meta["has_running"],
                        "algorithm": algo,
                        "makespan": res.metrics.makespan,
                        "total_tardiness": res.metrics.total_tardiness,
                        "mean_tardiness": mean_tardiness,
                        "max_tardiness": res.metrics.max_tardiness,
                        "late_jobs_count": res.metrics.late_jobs_count,
                        "mean_waiting_time": res.metrics.avg_waiting_time,
                        "max_waiting_time": res.metrics.max_waiting_time,
                        "mean_utilization_pct": res.metrics.avg_utilization,
                        "runtime_ms": round(wall_ms, 3),
                        "solver_status": res.metrics.solver_status,
                        "time_limit_s": solver_time_limit if solver_time_limit is not None else 0.0,
                        "epn_execution_mode": epn_mode,
                        "is_feasible_valid": is_valid,
                        "violation_count": len(errs)
                    })
                except Exception as exc:
                    wall_ms = (time.perf_counter() - t0) * 1000.0
                    violations_log.append({
                        "tier_id": tier_id,
                        "seed": seed,
                        "algorithm": algo,
                        "errors": [f"Exception: {str(exc)}"]
                    })
                    records.append({
                        "tier_id": tier_id,
                        "seed": seed,
                        "num_jobs": num_jobs,
                        "num_machines": meta["num_machines"],
                        "total_operations": meta["total_operations"],
                        "current_time": current_time,
                        "has_breakdown": meta["has_breakdown"],
                        "has_running": meta["has_running"],
                        "algorithm": algo,
                        "makespan": -1.0,
                        "total_tardiness": -1.0,
                        "mean_tardiness": -1.0,
                        "max_tardiness": -1.0,
                        "late_jobs_count": -1,
                        "mean_waiting_time": -1.0,
                        "max_waiting_time": -1.0,
                        "mean_utilization_pct": -1.0,
                        "runtime_ms": round(wall_ms, 3),
                        "solver_status": f"ERROR: {type(exc).__name__}",
                        "time_limit_s": solver_time_limit if solver_time_limit is not None else 0.0,
                        "epn_execution_mode": epn_mode,
                        "is_feasible_valid": False,
                        "violation_count": 1
                    })

    total_elapsed_s = round(time.perf_counter() - t_suite_start, 2)
    df = pd.DataFrame(records)

    # Compute optimality gap (%) relative to CP-SAT makespan on the same (tier_id, seed)
    cpsat_makespans = (
        df[df["algorithm"] == "CPSAT"]
        .set_index(["tier_id", "seed"])["makespan"]
        .to_dict()
    )
    df["makespan_gap_vs_cpsat_pct"] = df.apply(
        lambda r: round(((r["makespan"] - cpsat_makespans[(r["tier_id"], r["seed"])]) / cpsat_makespans[(r["tier_id"], r["seed"])]) * 100.0, 2)
        if cpsat_makespans.get((r["tier_id"], r["seed"]), 0) > 0 else 0.0,
        axis=1
    )

    # Save raw CSV and JSON
    raw_csv_path = out_dir / "stage9_raw_results.csv"
    raw_json_path = out_dir / "stage9_raw_results.json"
    df.to_csv(raw_csv_path, index=False)
    with open(raw_json_path, "w") as f:
        json.dump(df.to_dict(orient="records"), f, indent=2)

    # Statistical aggregations by (tier_id, algorithm) with mean, std, 95% CI half-width (1.96 * std / sqrt(N))
    summary_rows = []
    for (tier_id, algo), grp in df.groupby(["tier_id", "algorithm"], sort=False):
        n = len(grp)
        sqrt_n = np.sqrt(n) if n > 0 else 1.0
        mk_mean = grp["makespan"].mean()
        mk_std = grp["makespan"].std(ddof=1) if n > 1 else 0.0
        td_mean = grp["total_tardiness"].mean()
        td_std = grp["total_tardiness"].std(ddof=1) if n > 1 else 0.0
        mt_mean = grp["mean_tardiness"].mean()
        wt_mean = grp["mean_waiting_time"].mean()
        wt_std = grp["mean_waiting_time"].std(ddof=1) if n > 1 else 0.0
        ut_mean = grp["mean_utilization_pct"].mean()
        ut_std = grp["mean_utilization_pct"].std(ddof=1) if n > 1 else 0.0
        rt_mean = grp["runtime_ms"].mean()
        rt_std = grp["runtime_ms"].std(ddof=1) if n > 1 else 0.0
        gap_mean = grp["makespan_gap_vs_cpsat_pct"].mean()
        gap_std = grp["makespan_gap_vs_cpsat_pct"].std(ddof=1) if n > 1 else 0.0

        optimal_count = int((grp["solver_status"] == "OPTIMAL").sum())
        feasible_count = int(grp["is_feasible_valid"].sum())

        summary_rows.append({
            "tier_id": tier_id,
            "algorithm": algo,
            "n_trials": n,
            "feasible_valid_count": feasible_count,
            "optimal_status_count": optimal_count,
            "makespan_mean": round(mk_mean, 2),
            "makespan_std": round(mk_std, 2),
            "makespan_ci95": round(1.96 * mk_std / sqrt_n, 2),
            "total_tardiness_mean": round(td_mean, 2),
            "total_tardiness_std": round(td_std, 2),
            "total_tardiness_ci95": round(1.96 * td_std / sqrt_n, 2),
            "mean_tardiness_mean": round(mt_mean, 2),
            "waiting_time_mean": round(wt_mean, 2),
            "waiting_time_std": round(wt_std, 2),
            "utilization_pct_mean": round(ut_mean, 2),
            "utilization_pct_std": round(ut_std, 2),
            "runtime_ms_mean": round(rt_mean, 3),
            "runtime_ms_std": round(rt_std, 3),
            "makespan_gap_vs_cpsat_pct_mean": round(gap_mean, 2),
            "makespan_gap_vs_cpsat_pct_std": round(gap_std, 2),
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_csv_path = out_dir / "stage9_summary_table.csv"
    summary_json_path = out_dir / "stage9_summary_table.json"
    summary_df.to_csv(summary_csv_path, index=False)
    with open(summary_json_path, "w") as f:
        json.dump(summary_rows, f, indent=2)

    # Save experiment manifest
    manifest = {
        "experiment_suite": "Stage 9 Reproducible Research Validation & Benchmarking",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_trials": len(records),
        "total_violations": len(violations_log),
        "total_elapsed_seconds": total_elapsed_s,
        "environment": {
            "os": platform.platform(),
            "python_version": sys.version,
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "pytorch_version": torch.__version__,
            "ortools_version": ortools.__version__,
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
        },
        "epn_checkpoint": {
            "loaded": epn_scheduler.loaded,
            "device": str(epn_scheduler.device),
            "path": "backend/models/checkpoints/epn_model.pth"
        },
        "tiers": [
            {
                "tier_id": "TIER1_SMALL",
                "description": "Small verification instances (6 jobs, 5 machines, 3-5 ops/job, static arrivals)",
                "seeds": list(range(1001, 1011)),
                "cpsat_time_limit_s": 2.0
            },
            {
                "tier_id": "TIER2_MEDIUM",
                "description": "Medium 10-machine shop instances (10 jobs, 10 machines, 4-5 ops/job, Poisson arrivals)",
                "seeds": list(range(2001, 2011)),
                "cpsat_time_limit_s": 2.0
            },
            {
                "tier_id": "TIER3_DYNAMIC_BREAKDOWN",
                "description": "Dynamic in-flight rescheduling at t=15m with completed/running op locks and M2 breakdown (25m)",
                "seeds": list(range(3001, 3011)),
                "cpsat_time_limit_s": 2.0
            },
            {
                "tier_id": "TIER4_LARGE_SCALE",
                "description": "Large scalability stress instances (25 jobs, 10 machines, 125 operations total)",
                "seeds": list(range(4001, 4011)),
                "cpsat_time_limit_s": 2.5
            }
        ],
        "violations": violations_log
    }
    manifest_path = out_dir / "stage9_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    generate_stage9_svg_plots(summary_df, out_dir / "plots")

    print(f"Stage 9 Benchmark completed in {total_elapsed_s}s: {len(records)} trials, {len(violations_log)} violations.")
    return {
        "manifest": manifest,
        "summary": summary_rows
    }


def generate_stage9_svg_plots(df: pd.DataFrame, plots_dir: Path) -> None:
    plots_dir.mkdir(parents=True, exist_ok=True)
    tiers = ["TIER1_SMALL", "TIER2_MEDIUM", "TIER3_DYNAMIC_BREAKDOWN", "TIER4_LARGE_SCALE"]
    algos = ["CPSAT", "FCFS", "SPT", "EDD", "EPN", "CR", "AGING"]
    colors = {
        "CPSAT": "#0284c7",
        "FCFS": "#10b981",
        "SPT": "#f59e0b",
        "EDD": "#8b5cf6",
        "EPN": "#ec4899",
        "CR": "#64748b",
        "AGING": "#ef4444",
    }

    def write_bar_svg(metric_col: str, title: str, filename: str, max_y: float) -> None:
        width, height = 860, 440
        pad_l, pad_r, pad_t, pad_b = 75, 30, 60, 75
        plot_w = width - pad_l - pad_r
        plot_h = height - pad_t - pad_b
        lines = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" style="background:#0f172a;font-family:system-ui,sans-serif;">',
            f'<text x="{width/2}" y="32" text-anchor="middle" fill="#f8fafc" font-size="16" font-weight="bold">{title}</text>',
            f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t+plot_h}" stroke="#475569" stroke-width="1.5"/>',
            f'<line x1="{pad_l}" y1="{pad_t+plot_h}" x2="{pad_l+plot_w}" y2="{pad_t+plot_h}" stroke="#475569" stroke-width="1.5"/>',
        ]
        for k in range(6):
            val = max_y * k / 5.0
            y = pad_t + plot_h - (val / max_y) * plot_h
            lines.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l+plot_w}" y2="{y:.1f}" stroke="#1e293b" stroke-dasharray="4,4"/>')
            lines.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" fill="#94a3b8" font-size="11">{val:.0f}</text>')

        group_w = plot_w / len(tiers)
        bar_w = (group_w * 0.78) / len(algos)
        for t_i, tier in enumerate(tiers):
            gx = pad_l + t_i * group_w + group_w * 0.11
            sub = df[df["tier_id"] == tier].set_index("algorithm")
            for a_i, algo in enumerate(algos):
                val = float(sub.loc[algo, metric_col]) if algo in sub.index else 0.0
                bh = min(plot_h, (val / max_y) * plot_h)
                bx = gx + a_i * bar_w
                by = pad_t + plot_h - bh
                c = colors[algo]
                lines.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w-2:.1f}" height="{bh:.1f}" fill="{c}" rx="2"/>')
            lines.append(f'<text x="{pad_l + (t_i + 0.5)*group_w:.1f}" y="{pad_t+plot_h+24}" text-anchor="middle" fill="#cbd5e1" font-size="11" font-weight="bold">{tier}</text>')

        lx = pad_l + 20
        ly = height - 22
        for a_i, algo in enumerate(algos):
            ox = lx + a_i * 105
            lines.append(f'<rect x="{ox}" y="{ly-10}" width="12" height="12" fill="{colors[algo]}" rx="2"/>')
            lines.append(f'<text x="{ox+16}" y="{ly}" fill="#e2e8f0" font-size="11">{algo}</text>')

        lines.append("</svg>")
        (plots_dir / filename).write_text("\n".join(lines), encoding="utf-8")

    write_bar_svg("makespan_mean", "Stage 9: Mean Makespan (min) by Tier and Algorithm (Lower is Better)", "makespan_by_tier.svg", 2000.0)
    write_bar_svg("total_tardiness_mean", "Stage 9: Mean Total Tardiness (min) by Tier and Algorithm (Lower is Better)", "tardiness_by_tier.svg", 38000.0)
    write_bar_svg("runtime_ms_mean", "Stage 9: Mean Scheduling Runtime (ms) by Tier and Algorithm", "runtime_by_tier.svg", 2800.0)


if __name__ == "__main__":
    run_stage9_benchmark()

