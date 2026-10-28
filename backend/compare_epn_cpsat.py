import random, time, json, os
from pathlib import Path

# Ensure import path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.optimization.cpsat_solver import CPSATSchedulingOptimizer
from app.ml.inference.epn_scheduler import EPNScheduler
from app.schemas.models import Job, Operation, Machine, MachineStatus, OperationStatus, JobStatus
from app.core.state_service import ProductionStateService
from app.database.db import init_db, SessionLocal, MachineModel, JobModel


def generate_random_instance(num_jobs=5, num_machines=5, seed=0):
    random.seed(seed)
    machines = []
    for i in range(1, num_machines + 1):
        m = Machine(
            machine_id=f"M{i}",
            name=f"Machine {i}",
            capability="generic",
            status=MachineStatus.IDLE,
        )
        machines.append(m)
    jobs = []
    for j in range(1, num_jobs + 1):
        ops = []
        for m in machines:
            duration = random.randint(1, 10)
            ops.append(
                Operation(
                    sequence=len(ops) + 1,
                    name=f"Op{len(ops)+1}",
                    machine_id=m.machine_id,
                    duration=duration,
                    status=OperationStatus.PENDING,
                )
            )
        job = Job(
            job_id=f"J{j}",
            name=f"Job {j}",
            product_type="generic",
            quantity=1,
            arrival_time=0.0,
            due_date=sum(op.duration for op in ops) + random.randint(5, 15),
            priority=3,
            status=JobStatus.PENDING,
            operations=ops,
        )
        jobs.append(job)
    return jobs, machines

def run_comparison(seeds=[0,1,2,3,4]):
    results = []
    for seed in seeds:
        jobs, machines = generate_random_instance(seed=seed)
        # CP-SAT
        start = time.time()
        cp_result = CPSATSchedulingOptimizer.optimize(
            jobs=jobs,
            machines=machines,
            current_time=0.0,
            time_limit_seconds=5.0,
        )
        cp_time = time.time() - start
        # EPN
        start = time.time()
        epn_sched = EPNScheduler()
        epn_result = epn_sched.schedule(jobs, machines)
        epn_time = time.time() - start
        # Record metrics
        results.append({
            "seed": seed,
            "cp": {
                "status": cp_result.status,
                "makespan": cp_result.metrics.makespan,
                "total_tardiness": cp_result.metrics.total_tardiness,
                "mean_tardiness": cp_result.metrics.mean_tardiness,
                "runtime": cp_time,
            },
            "epn": {
                "status": epn_result.status,
                "makespan": epn_result.metrics.makespan,
                "total_tardiness": epn_result.metrics.total_tardiness,
                "mean_tardiness": epn_result.metrics.mean_tardiness,
                "runtime": epn_time,
            },
        })
    # Summarize
    summary_path = Path(__file__).resolve().parent / "epn_cpsat_comparison.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)
    print("Comparison written to", summary_path)

if __name__ == "__main__":
    init_db()
    run_comparison()
