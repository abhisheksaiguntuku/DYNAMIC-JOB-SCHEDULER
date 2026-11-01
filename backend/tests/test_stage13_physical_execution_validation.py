import os
import pytest
from pathlib import Path
from app.schemas.models import Job, Operation, Machine, MachineStatus, JobStatus, OperationStatus
from app.simulation.engine import DiscreteEventSimulator
from app.core.state_service import ProductionStateService
from app.database.db import init_db, SessionLocal, JobModel, MachineModel, SimulationStateModel, engine

def get_machine_by_id(machine_id: str) -> Machine:
    for m in ProductionStateService.get_all_machines():
        if m.machine_id == machine_id:
            return m
    raise ValueError(f"Machine {machine_id} not found")

def get_job_by_id(job_id: str) -> Job:
    for j in ProductionStateService.get_all_jobs():
        if j.job_id == job_id:
            return j
    raise ValueError(f"Job {job_id} not found")

def test_database_isolation_environment_safety(reset_db):
    """
    Mandatory Safety Check:
    Verify that the test database dialect is SQLite, pointing to a temporary file,
    and cannot possibly connect to or modify Neon PostgreSQL or production_scheduler.db.
    """
    dialect_name = engine.dialect.name
    assert dialect_name == "sqlite", f"Safety violation: Test engine dialect must be 'sqlite', found '{dialect_name}'"
    
    url_str = str(engine.url)
    assert "postgres" not in url_str.lower(), f"Safety violation: PostgreSQL URL detected: {url_str}"
    assert "neon" not in url_str.lower(), f"Safety violation: Neon database detected: {url_str}"
    
    # Must point to pytest isolated temp database path
    assert "pytest_isolated_production_scheduler.db" in url_str or "temp" in url_str.lower()
    assert not url_str.endswith("dynamic_job_shop_scheduler/backend/production_scheduler.db")

def test_scenario_a_non_preemptive_lock_and_sequential_dispatch(reset_db):
    """
    Scenario A:
    1. JOB_DYN_201 arrives at t=0.0 (dur=10.0, priority=2, on M10).
    2. Simulation advances to t=2.0 -> JOB_DYN_201 dispatched to M10.
    3. JOB_DYN_906 arrives at t=2.0 (dur=15.0, priority=5, on M10) while JOB_DYN_201 is running.
    4. Confirm JOB_DYN_201 continues uninterrupted; JOB_DYN_906 remains queued.
    5. Complete JOB_DYN_201 at t=10.0.
    6. Confirm M10 transitions cleanly and JOB_DYN_906 is dispatched next without overlap.
    7. Complete JOB_DYN_906 at t=25.0.
    """
    init_db()
    db = SessionLocal()
    # Create Machine M10
    db.add(MachineModel(
        machine_id="M10",
        name="Packaging & Inspection Station",
        capability="Inspection",
        status=MachineStatus.IDLE.value,
        remaining_processing_time=0.0,
        total_busy_time=0.0
    ))
    db.commit()
    db.close()

    # Step 1: Add JOB_DYN_201 (Lower Priority = 2, Duration = 10 min, arrival = 0.0)
    job_201 = Job(
        job_id="JOB_DYN_201",
        name="Standard Quality Order",
        product_type="Standard",
        quantity=1,
        arrival_time=0.0,
        due_date=100.0,
        priority=2,
        operations=[
            Operation(sequence=1, name="Inspection Op 1", machine_id="M10", duration=10.0)
        ]
    )
    ProductionStateService.add_job(job_201)

    sim = DiscreteEventSimulator(restore_from_db=True)
    assert sim.sim_time == 0.0

    # Step 2: Advance by 2.0 min -> t = 2.0
    adv_res = sim.advance_time(2.0)
    assert adv_res["current_sim_time"] == 2.0

    # Verify M10 is BUSY with JOB_DYN_201
    m10 = get_machine_by_id("M10")
    assert m10.status == MachineStatus.BUSY
    assert m10.current_job_id == "JOB_DYN_201"
    assert m10.current_operation_seq == 1
    assert round(m10.remaining_processing_time, 2) == 8.0
    assert round(m10.total_busy_time, 2) == 2.0

    # Verify JOB_DYN_201 state
    j201_curr = get_job_by_id("JOB_DYN_201")
    assert j201_curr.status == JobStatus.IN_PROGRESS
    assert j201_curr.operations[0].status == OperationStatus.RUNNING
    assert j201_curr.operations[0].start_time == 0.0
    assert j201_curr.operations[0].end_time is None

    # Step 3: High Priority JOB_DYN_906 arrives at t=2.0 (Priority = 5, Duration = 15 min)
    job_906 = Job(
        job_id="JOB_DYN_906",
        name="Urgent Priority Order",
        product_type="Urgent",
        quantity=1,
        arrival_time=2.0,
        due_date=50.0,
        priority=5,
        operations=[
            Operation(sequence=1, name="High Priority Inspection", machine_id="M10", duration=15.0)
        ]
    )
    ProductionStateService.add_job(job_906)

    # Advance by 3.0 min -> t = 5.0
    sim.advance_time(3.0)
    assert sim.sim_time == 5.0

    # Step 4: Confirm non-preemptive execution
    m10_t5 = get_machine_by_id("M10")
    assert m10_t5.status == MachineStatus.BUSY
    assert m10_t5.current_job_id == "JOB_DYN_201"
    assert round(m10_t5.remaining_processing_time, 2) == 5.0
    assert round(m10_t5.total_busy_time, 2) == 5.0

    j906_t5 = get_job_by_id("JOB_DYN_906")
    assert j906_t5.status == JobStatus.PENDING
    assert j906_t5.operations[0].status == OperationStatus.PENDING
    assert j906_t5.operations[0].start_time is None

    # Step 5 & 6: Advance by 5.0 min -> t = 10.0 (JOB_DYN_201 finishes, JOB_DYN_906 dispatched)
    sim.advance_time(5.0)
    assert sim.sim_time == 10.0

    j201_t10 = get_job_by_id("JOB_DYN_201")
    assert j201_t10.status == JobStatus.COMPLETED
    assert j201_t10.operations[0].status == OperationStatus.COMPLETED
    assert j201_t10.operations[0].start_time == 0.0
    assert j201_t10.operations[0].end_time == 10.0

    # JOB_DYN_906 should now be immediately dispatched onto M10 at t=10.0
    m10_t10 = get_machine_by_id("M10")
    assert m10_t10.status == MachineStatus.BUSY
    assert m10_t10.current_job_id == "JOB_DYN_906"
    assert m10_t10.current_operation_seq == 1
    assert round(m10_t10.remaining_processing_time, 2) == 15.0
    assert round(m10_t10.total_busy_time, 2) == 10.0

    j906_t10 = get_job_by_id("JOB_DYN_906")
    assert j906_t10.status == JobStatus.IN_PROGRESS
    assert j906_t10.operations[0].status == OperationStatus.RUNNING
    assert j906_t10.operations[0].start_time == 10.0

    # Step 7: Advance by 15.0 min -> t = 25.0 (JOB_DYN_906 completes)
    sim.advance_time(15.0)
    assert sim.sim_time == 25.0

    j906_t25 = get_job_by_id("JOB_DYN_906")
    assert j906_t25.status == JobStatus.COMPLETED
    assert j906_t25.operations[0].status == OperationStatus.COMPLETED
    assert j906_t25.operations[0].start_time == 10.0
    assert j906_t25.operations[0].end_time == 25.0

    # M10 returns to IDLE
    m10_t25 = get_machine_by_id("M10")
    assert m10_t25.status == MachineStatus.IDLE
    assert m10_t25.current_job_id is None
    assert m10_t25.remaining_processing_time == 0.0
    assert round(m10_t25.total_busy_time, 2) == 25.0

    # Verification of no overlapping operations on M10
    assert j201_t10.operations[0].end_time <= j906_t25.operations[0].start_time

def test_scenario_b_head_to_head_priority_arbitration(reset_db):
    """
    Scenario B:
    1. Both JOB_DYN_201 (priority=2, dur=10) and JOB_DYN_906 (priority=5, dur=15)
       are present at t=0.0 before any simulation step.
    2. Advance simulation -> Priority arbitration strictly selects JOB_DYN_906 first.
    3. JOB_DYN_201 waits until JOB_DYN_906 completes at t=15.0.
    4. JOB_DYN_201 dispatches at t=15.0 and completes at t=25.0.
    """
    init_db()
    db = SessionLocal()
    db.add(MachineModel(
        machine_id="M10",
        name="Packaging & Inspection Station",
        capability="Inspection",
        status=MachineStatus.IDLE.value,
        remaining_processing_time=0.0,
        total_busy_time=0.0
    ))
    db.commit()
    db.close()

    # Add lower-priority job first to ensure insertion order does not bias arbitration
    job_201 = Job(
        job_id="JOB_DYN_201",
        name="Low Priority Order",
        product_type="Standard",
        quantity=1,
        arrival_time=0.0,
        due_date=100.0,
        priority=2,
        operations=[Operation(sequence=1, name="Low Op", machine_id="M10", duration=10.0)]
    )
    job_906 = Job(
        job_id="JOB_DYN_906",
        name="High Priority Order",
        product_type="Urgent",
        quantity=1,
        arrival_time=0.0,
        due_date=50.0,
        priority=5,
        operations=[Operation(sequence=1, name="High Op", machine_id="M10", duration=15.0)]
    )
    ProductionStateService.add_job(job_201)
    ProductionStateService.add_job(job_906)

    sim = DiscreteEventSimulator(restore_from_db=True)
    assert sim.sim_time == 0.0

    # Advance by 5.0 min -> t = 5.0
    sim.advance_time(5.0)

    # Arbitration must have selected JOB_DYN_906
    m10_t5 = get_machine_by_id("M10")
    assert m10_t5.status == MachineStatus.BUSY
    assert m10_t5.current_job_id == "JOB_DYN_906"
    assert round(m10_t5.remaining_processing_time, 2) == 10.0

    j906_t5 = get_job_by_id("JOB_DYN_906")
    assert j906_t5.status == JobStatus.IN_PROGRESS
    assert j906_t5.operations[0].status == OperationStatus.RUNNING
    assert j906_t5.operations[0].start_time == 0.0

    j201_t5 = get_job_by_id("JOB_DYN_201")
    assert j201_t5.status == JobStatus.PENDING
    assert j201_t5.operations[0].status == OperationStatus.PENDING
    assert j201_t5.operations[0].start_time is None

    # Advance across event boundary to t=15.0
    sim.advance_time(10.0)
    assert sim.sim_time == 15.0

    j906_t15 = get_job_by_id("JOB_DYN_906")
    assert j906_t15.status == JobStatus.COMPLETED
    assert j906_t15.operations[0].end_time == 15.0

    # JOB_DYN_201 should immediately dispatch at t=15.0
    m10_t15 = get_machine_by_id("M10")
    assert m10_t15.status == MachineStatus.BUSY
    assert m10_t15.current_job_id == "JOB_DYN_201"
    assert round(m10_t15.remaining_processing_time, 2) == 10.0

    j201_t15 = get_job_by_id("JOB_DYN_201")
    assert j201_t15.status == JobStatus.IN_PROGRESS
    assert j201_t15.operations[0].status == OperationStatus.RUNNING
    assert j201_t15.operations[0].start_time == 15.0

    # Advance to t=25.0
    sim.advance_time(10.0)
    assert sim.sim_time == 25.0

    j201_t25 = get_job_by_id("JOB_DYN_201")
    assert j201_t25.status == JobStatus.COMPLETED
    assert j201_t25.operations[0].end_time == 25.0

    m10_t25 = get_machine_by_id("M10")
    assert m10_t25.status == MachineStatus.IDLE
    assert round(m10_t25.total_busy_time, 2) == 25.0

def test_scenario_c_machine_downtime_and_automatic_post_recovery_dispatch(reset_db):
    """
    Scenario C:
    1. Machine M10 is placed into DOWN status for 10.0 minutes at t=0.0.
    2. JOB_DYN_906 arrives at t=0.0.
    3. Confirm JOB_DYN_906 cannot dispatch while M10 is DOWN.
    4. Advance simulation across the 10-minute recovery boundary to t=10.0.
    5. Confirm M10 recovers and automatically dispatches JOB_DYN_906 at t=10.0.
    6. Complete JOB_DYN_906 at t=25.0.
    """
    init_db()
    db = SessionLocal()
    db.add(MachineModel(
        machine_id="M10",
        name="Packaging & Inspection Station",
        capability="Inspection",
        status=MachineStatus.IDLE.value,
        remaining_processing_time=0.0,
        total_busy_time=0.0
    ))
    db.commit()
    db.close()

    # Place M10 in DOWN status for 10 minutes
    ProductionStateService.set_machine_downtime("M10", down_duration=10.0, reason="Sensor Calibration")
    m10_down = get_machine_by_id("M10")
    assert m10_down.status == MachineStatus.DOWN
    assert m10_down.remaining_processing_time == 10.0

    job_906 = Job(
        job_id="JOB_DYN_906",
        name="High Priority Order",
        product_type="Urgent",
        quantity=1,
        arrival_time=0.0,
        due_date=50.0,
        priority=5,
        operations=[Operation(sequence=1, name="High Op", machine_id="M10", duration=15.0)]
    )
    ProductionStateService.add_job(job_906)

    sim = DiscreteEventSimulator(restore_from_db=True)
    
    # Advance by 4.0 min -> t = 4.0
    sim.advance_time(4.0)
    assert sim.sim_time == 4.0

    m10_t4 = get_machine_by_id("M10")
    assert m10_t4.status == MachineStatus.DOWN
    assert round(m10_t4.remaining_processing_time, 2) == 6.0

    j906_t4 = get_job_by_id("JOB_DYN_906")
    assert j906_t4.status == JobStatus.PENDING

    # Advance by 6.0 min -> t = 10.0 (Downtime expires, recovery occurs, job dispatched)
    sim.advance_time(6.0)
    assert sim.sim_time == 10.0

    m10_t10 = get_machine_by_id("M10")
    assert m10_t10.status == MachineStatus.BUSY
    assert m10_t10.current_job_id == "JOB_DYN_906"
    assert round(m10_t10.remaining_processing_time, 2) == 15.0

    j906_t10 = get_job_by_id("JOB_DYN_906")
    assert j906_t10.status == JobStatus.IN_PROGRESS
    assert j906_t10.operations[0].status == OperationStatus.RUNNING
    assert j906_t10.operations[0].start_time == 10.0

    # Advance to t=25.0 -> Job completes
    sim.advance_time(15.0)
    assert sim.sim_time == 25.0

    j906_t25 = get_job_by_id("JOB_DYN_906")
    assert j906_t25.status == JobStatus.COMPLETED
    assert j906_t25.operations[0].end_time == 25.0

    m10_t25 = get_machine_by_id("M10")
    assert m10_t25.status == MachineStatus.IDLE
