import os
import pytest
from pathlib import Path
from fastapi import HTTPException
from app.main import (
    verify_demo_token,
    advance_simulation,
    register_job,
    delete_job_endpoint,
    clear_all_jobs_endpoint,
    reset_demo_workload
)
from app.schemas.models import Job, Operation, OperationStatus, MachineStatus, JobStatus
from app.core.state_service import ProductionStateService
from app.simulation.engine import DiscreteEventSimulator
from app.database.db import SessionLocal, JobModel, MachineModel, ScheduleRecordModel, SimulationStateModel

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_auth_token_enforcement():
    """Verify verify_demo_token permits open access for interactive demo."""
    verify_demo_token(x_demo_token=None)
    verify_demo_token(x_demo_token="AnyToken")


def test_simulation_advance_and_intermediate_dispatch(reset_db):
    """Verify +5 min and +15 min simulation advancement dispatches ready operations."""
    jobs_file = str(DATA_DIR / "initial_jobs.json")
    machines_file = str(DATA_DIR / "initial_machines.json")
    ProductionStateService.seed_if_empty(jobs_file, machines_file)

    # Advance 5 min
    res5 = advance_simulation(step_minutes=5.0)
    assert res5["current_sim_time"] == 5.0
    assert len(res5["events"]) > 0

    # Advance 15 min
    res15 = advance_simulation(step_minutes=15.0)
    assert res15["current_sim_time"] == 20.0

    # Verify simulation persistence
    sim = DiscreteEventSimulator()
    assert sim.sim_time == 20.0


def test_job_registration_and_individual_deletion(reset_db):
    """Verify arbitrary valid job registration and individual job deletion."""
    jobs_file = str(DATA_DIR / "initial_jobs.json")
    machines_file = str(DATA_DIR / "initial_machines.json")
    ProductionStateService.seed_if_empty(jobs_file, machines_file)

    initial_jobs = ProductionStateService.get_all_jobs()
    assert len(initial_jobs) == 10

    # Register arbitrary manufacturing job
    new_job = Job(
        job_id="JOB_TEST_STAGE16",
        name="Precision Turbine Casing",
        product_type="Aerospace Component",
        quantity=1,
        arrival_time=0.0,
        due_date=180.0,
        priority=5,
        status=JobStatus.PENDING,
        operations=[
            Operation(
                sequence=1,
                name="Pattern Making",
                machine_id="M1",
                duration=12.0,
                status=OperationStatus.PENDING,
                alternative_machines=["M6"]
            ),
            Operation(
                sequence=2,
                name="Machining Center",
                machine_id="M5",
                duration=15.0,
                status=OperationStatus.PENDING,
                alternative_machines=["M10"]
            )
        ]
    )

    created = register_job(new_job)
    assert created.job_id == "JOB_TEST_STAGE16"

    # Confirm 11 jobs exist
    jobs_after_add = ProductionStateService.get_all_jobs()
    assert len(jobs_after_add) == 11

    # Delete the newly created job
    del_res = delete_job_endpoint("JOB_TEST_STAGE16")
    assert del_res["status"] == "SUCCESS"
    assert del_res["remaining_jobs_count"] == 10

    # Confirm job count is back to 10 and deleted job is absent
    jobs_after_del = ProductionStateService.get_all_jobs()
    assert len(jobs_after_del) == 10
    assert not any(j.job_id == "JOB_TEST_STAGE16" for j in jobs_after_del)


def test_running_job_deletion_rejected(reset_db):
    """Confirm a job currently executing on a machine cannot be deleted."""
    jobs_file = str(DATA_DIR / "initial_jobs.json")
    machines_file = str(DATA_DIR / "initial_machines.json")
    ProductionStateService.seed_if_empty(jobs_file, machines_file)

    # Advance 5 minutes to trigger dispatch onto M1
    advance_simulation(step_minutes=5.0)

    machines = ProductionStateService.get_all_machines()
    busy_m = [m for m in machines if m.status == MachineStatus.BUSY]
    assert len(busy_m) > 0
    running_job_id = busy_m[0].current_job_id
    assert running_job_id is not None

    # Deleting running job raises 400
    with pytest.raises(HTTPException) as exc:
        delete_job_endpoint(running_job_id)
    assert exc.value.status_code == 400
    assert "RUNNING" in exc.value.detail


def test_clear_all_jobs_and_empty_state(reset_db):
    """Verify Clear All Jobs produces a clean empty shop floor state and Reset Demo restores it."""
    jobs_file = str(DATA_DIR / "initial_jobs.json")
    machines_file = str(DATA_DIR / "initial_machines.json")
    ProductionStateService.seed_if_empty(jobs_file, machines_file)

    # Clear all jobs
    clear_res = clear_all_jobs_endpoint()
    assert clear_res["status"] == "SUCCESS"
    assert clear_res["cleared_jobs_count"] == 10

    # Ensure 0 jobs exist
    assert len(ProductionStateService.get_all_jobs()) == 0

    # Ensure schedule is null
    assert ProductionStateService.get_latest_schedule() is None

    # Reset back to demo workload
    reset_res = reset_demo_workload()
    assert reset_res["status"] == "SUCCESS"
    assert len(reset_res["jobs"]) == 10
    assert reset_res["schedule"] is not None
