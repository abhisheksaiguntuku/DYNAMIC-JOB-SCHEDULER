import json
import random
import time
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any

from app.schemas.models import Job, Machine, Operation
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer
from app.ml.inference.epn_scheduler import EPNJobShopScheduler
from app.scheduling.validator import ScheduleValidator

def generate_synthetic_scenario(
    num_jobs: int = 10,
    seed: int = 42,
    tightness_factor: float = 1.0,
    arrival_rate: float = 0.5
) -> Tuple[List[Job], List[Machine]]:
    random.seed(seed)
    np.random.seed(seed)

    # 10 Machines
    machines = [
        Machine(machine_id=f"M{i+1}", name=f"Stage {i+1}", capability=f"Process_{i+1}")
        for i in range(10)
    ]

    jobs = []
    for j_idx in range(num_jobs):
        job_id = f"EXP_JOB_{j_idx+1:03d}"
        arr_time = round(np.random.exponential(1.0 / arrival_rate), 1) if arrival_rate > 0 else 0.0

        # Operation sequence across 4 to 6 random machines
        route_len = random.randint(4, 6)
        m_sequence = random.sample(range(1, 11), route_len)

        operations = []
        total_p = 0.0
        for seq_i, m_num in enumerate(m_sequence):
            dur = float(random.randint(10, 35))
            total_p += dur
            operations.append(
                Operation(
                    sequence=seq_i + 1,
                    name=f"Op_{seq_i+1}",
                    machine_id=f"M{m_num}",
                    duration=dur,
                    setup_time=2.0
                )
            )

        # Due date calculation based on tightness factor
        slack = float(random.randint(10, 50)) * tightness_factor
        due_date = round(arr_time + total_p + slack, 1)

        jobs.append(
            Job(
                job_id=job_id,
                name=f"Component {j_idx+1}",
                product_type="Industrial Part",
                quantity=1,
                arrival_time=arr_time,
                due_date=due_date,
                priority=random.randint(1, 5),
                operations=operations
            )
        )

    return jobs, machines

def run_experiment_suite(num_runs: int = 15) -> Dict[str, Any]:
    print(f"Executing Empirical Research Experiment Suite across {num_runs} independent scenarios...")
    
    epn = EPNJobShopScheduler()
    algorithms = ["FCFS", "SPT", "EDD", "CR", "AGING", "CPSAT", "EPN"]
    
    records = []

    for run_idx in range(num_runs):
        seed = 1000 + run_idx
        # Alternate tightness and arrival intensity
        tightness = 0.7 if run_idx % 2 == 0 else 1.3
        arr_rate = 0.3 if run_idx % 3 == 0 else 0.7

        jobs, machines = generate_synthetic_scenario(num_jobs=8, seed=seed, tightness_factor=tightness, arrival_rate=arr_rate)

        for algo in algorithms:
            t0 = time.perf_counter()
            if algo == "CPSAT":
                res = CPSATSchedulingOptimizer.optimize(jobs, machines, current_time=0.0, time_limit_seconds=2.0)
            elif algo == "EPN":
                res = epn.schedule(jobs, machines, current_time=0.0)
            else:
                res = DispatchHeuristicScheduler.schedule(jobs, machines, current_time=0.0, rule=algo)
            t_elapsed = (time.perf_counter() - t0) * 1000.0

            # Independent validation
            is_valid, _ = ScheduleValidator.validate(res.tasks, machines, current_time=0.0)

            records.append({
                "run_id": run_idx + 1,
                "seed": seed,
                "tightness": tightness,
                "algorithm": algo,
                "makespan": res.metrics.makespan,
                "total_tardiness": res.metrics.total_tardiness,
                "max_tardiness": res.metrics.max_tardiness,
                "late_jobs_count": res.metrics.late_jobs_count,
                "avg_waiting_time": res.metrics.avg_waiting_time,
                "avg_utilization": res.metrics.avg_utilization,
                "latency_ms": round(t_elapsed, 2),
                "is_valid": is_valid
            })

    df = pd.DataFrame(records)

    # Compute statistical aggregation per algorithm
    summary = df.groupby("algorithm").agg({
        "makespan": ["mean", "std"],
        "total_tardiness": ["mean", "std"],
        "late_jobs_count": ["mean"],
        "avg_waiting_time": ["mean", "std"],
        "avg_utilization": ["mean"],
        "latency_ms": ["mean"]
    })

    summary.columns = ['_'.join(col).strip() for col in summary.columns.values]
    summary = summary.reset_index().round(2)

    output_dir = Path(__file__).resolve().parent.parent.parent / "experiments"
    raw_path = output_dir / "raw_results" / "experiment_suite_raw.json"
    summary_path = output_dir / "summaries" / "experiment_summary.json"

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with open(raw_path, "w") as f:
        json.dump(records, f, indent=2)

    summary_dict = summary.to_dict(orient="records")
    with open(summary_path, "w") as f:
        json.dump(summary_dict, f, indent=2)

    print("Experiment Suite completed successfully. Results saved to disk.")
    return summary_dict

if __name__ == "__main__":
    from typing import Tuple
    run_experiment_suite(15)
