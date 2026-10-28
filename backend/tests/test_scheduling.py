import pytest
import json
from pathlib import Path
from app.schemas.models import Job, Machine
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer
from app.scheduling.validator import ScheduleValidator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

@pytest.fixture
def sample_jobs():
    with open(DATA_DIR / "initial_jobs.json", "r") as f:
        data = json.load(f)
    return [Job(**item) for item in data[:4]]  # First 4 jobs for fast deterministic tests

@pytest.fixture
def sample_machines():
    with open(DATA_DIR / "initial_machines.json", "r") as f:
        data = json.load(f)
    return [Machine(**item) for item in data]

def test_fcfs_heuristic_validity(sample_jobs, sample_machines):
    res = DispatchHeuristicScheduler.schedule(sample_jobs, sample_machines, current_time=0.0, rule="FCFS")
    assert len(res.tasks) > 0
    is_valid, errors = ScheduleValidator.validate(res.tasks, sample_machines, current_time=0.0)
    assert is_valid, f"Validation errors: {errors}"
    assert res.metrics.makespan > 0

def test_spt_heuristic_validity(sample_jobs, sample_machines):
    res = DispatchHeuristicScheduler.schedule(sample_jobs, sample_machines, current_time=0.0, rule="SPT")
    assert len(res.tasks) > 0
    is_valid, errors = ScheduleValidator.validate(res.tasks, sample_machines, current_time=0.0)
    assert is_valid, f"Validation errors: {errors}"

def test_cpsat_optimizer_validity(sample_jobs, sample_machines):
    res = CPSATSchedulingOptimizer.optimize(sample_jobs, sample_machines, current_time=0.0, time_limit_seconds=2.0)
    assert len(res.tasks) > 0
    is_valid, errors = ScheduleValidator.validate(res.tasks, sample_machines, current_time=0.0)
    assert is_valid, f"Validation errors: {errors}"
    assert res.metrics.makespan > 0
    assert res.metrics.solver_status in ("OPTIMAL", "FEASIBLE")
