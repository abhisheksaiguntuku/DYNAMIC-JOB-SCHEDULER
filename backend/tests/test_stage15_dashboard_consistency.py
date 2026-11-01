import os
import json
import pytest
from pathlib import Path
from app.schemas.models import Job, Operation, Machine, MachineStatus, JobStatus, OperationStatus
from app.simulation.engine import DiscreteEventSimulator
from app.core.state_service import ProductionStateService
from app.database.db import init_db, SessionLocal, JobModel, MachineModel, ScheduleRecordModel, SimulationStateModel, engine

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def test_database_isolation_environment_safety(reset_db):
    """Confirm strictly isolated SQLite temporary engine."""
    assert engine.dialect.name == "sqlite"
    url_str = str(engine.url)
    assert "postgres" not in url_str.lower()
    assert "neon" not in url_str.lower()
    assert "pytest_isolated_production_scheduler.db" in url_str or "temp" in url_str.lower()

def test_seed_if_empty_initializes_10_jobs_and_schedule(reset_db):
    """
    1. Initial demo initialization seeds exactly 10 baseline demo jobs and 10 machines.
    2. Automatically generates an initial schedule so GET /api/schedules/latest never returns 404.
    3. Repeated initialization does not duplicate jobs or machines.
    """
    jobs_file = str(DATA_DIR / "initial_jobs.json")
    machines_file = str(DATA_DIR / "initial_machines.json")

    # First Seed
    ProductionStateService.seed_if_empty(jobs_file, machines_file)
    jobs = ProductionStateService.get_all_jobs()
    machines = ProductionStateService.get_all_machines()
    assert len(jobs) == 10
    assert len(machines) == 10
    assert sorted([j.job_id for j in jobs]) == [f"JOB_{i:03d}" for i in range(1, 11)]

    # Confirm initial schedule was generated
    latest_sched = ProductionStateService.get_latest_schedule()
    assert latest_sched is not None
    assert len(latest_sched.tasks) > 0

    # Second Seed - idempotency check
    ProductionStateService.seed_if_empty(jobs_file, machines_file)
    jobs2 = ProductionStateService.get_all_jobs()
    machines2 = ProductionStateService.get_all_machines()
    assert len(jobs2) == 10
    assert len(machines2) == 10

def test_atomic_reset_demo_restores_clean_state_and_replaces_schedule(reset_db):
    """
    1. Seed baseline jobs.
    2. Add custom dynamic job (JOB_DYN_999).
    3. Advance simulation time.
    4. Run reset_to_demo_workload.
    5. Verify:
       - Custom job is removed.
       - Exactly 10 baseline jobs exist.
       - Simulation time reset to 0.0.
       - Stale schedules removed and replaced with a fresh schedule for the 10 demo jobs only.
       - No deleted job tasks appear in the fresh schedule.
    """
    jobs_file = str(DATA_DIR / "initial_jobs.json")
    machines_file = str(DATA_DIR / "initial_machines.json")
    ProductionStateService.seed_if_empty(jobs_file, machines_file)

    # Add dynamic custom job
    dyn_job = Job(
        job_id="JOB_DYN_999",
        name="Custom Impeller",
        product_type="Custom",
        quantity=1,
        arrival_time=0.0,
        due_date=100.0,
        priority=4,
        operations=[Operation(sequence=1, name="Custom Cut", machine_id="M1", duration=12.0)]
    )
    ProductionStateService.add_job(dyn_job)
    assert len(ProductionStateService.get_all_jobs()) == 11

    # Advance simulation
    sim = DiscreteEventSimulator(restore_from_db=True)
    sim.advance_time(5.0)
    assert sim.sim_time == 5.0

    # Generate schedule with dynamic job
    sched_before = ProductionStateService.recalculate_schedule(sim_time=5.0, algorithm="CPSAT")
    task_job_ids_before = {t.job_id for t in sched_before.tasks}
    assert "JOB_DYN_999" in task_job_ids_before

    # Execute atomic reset
    sim.reset()
    reset_res = ProductionStateService.reset_to_demo_workload(jobs_file, machines_file)
    assert reset_res["jobs_count"] == 10

    # Verify restored state
    jobs_after = ProductionStateService.get_all_jobs()
    assert len(jobs_after) == 10
    assert "JOB_DYN_999" not in [j.job_id for j in jobs_after]

    sim_after = DiscreteEventSimulator(restore_from_db=True)
    assert sim_after.sim_time == 0.0
    assert sim_after.is_running is False

    # Verify fresh schedule
    latest_sched = ProductionStateService.get_latest_schedule()
    assert latest_sched is not None
    task_job_ids_after = {t.job_id for t in latest_sched.tasks}
    assert "JOB_DYN_999" not in task_job_ids_after, "Deleted dynamic job must not linger in latest schedule!"
    assert len(task_job_ids_after) == 10

def test_latest_schedule_read_only_graceful_handling_when_empty(reset_db):
    """
    Verify GET /api/schedules/latest remains strictly read-only:
    - If database is empty, get_latest_schedule returns None without throwing 404/500 errors.
    """
    sched = ProductionStateService.get_latest_schedule()
    assert sched is None

