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

def compute_lifecycle_counts():
    """Simulate frontend lifecycle counter aggregation directly from backend state."""
    jobs = ProductionStateService.get_all_jobs()
    machines = ProductionStateService.get_all_machines()
    
    total = len(jobs)
    completed = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
    in_progress = sum(1 for j in jobs if j.status == JobStatus.IN_PROGRESS)
    pending = sum(1 for j in jobs if j.status == JobStatus.PENDING)
    
    busy_machines = sum(1 for m in machines if m.status == MachineStatus.BUSY)
    down_machines = sum(1 for m in machines if m.status in (MachineStatus.DOWN, MachineStatus.MAINTENANCE))
    idle_machines = sum(1 for m in machines if m.status == MachineStatus.IDLE)
    
    return {
        "total_jobs": total,
        "completed": completed,
        "in_progress": in_progress,
        "pending": pending,
        "busy_machines": busy_machines,
        "down_machines": down_machines,
        "idle_machines": idle_machines
    }

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

def test_scenario_1_full_factory_lifecycle_with_dynamic_events_and_gantt_fidelity(reset_db):
    """
    Scenario 1:
    Five machines (M1-M5), three multi-operation jobs.
    Tests:
    1. Parallel execution across M1 and M3.
    2. Dynamic arrival of urgent JOB_URGENT_03 at t=5.0 with alternative machine routing (M1 busy -> dispatches to M5).
    3. Machine failure on M4 while JOB_BASE_02 Op 2 is active: non-preemptive lock preserves operation and extends finish time.
    4. Automatic recovery and sequential completion across multi-event boundaries.
    5. Planned schedule vs actual execution timestamps validation (allowing legitimate variance).
    6. Frontend lifecycle counters matching backend state at every phase.
    """
    init_db()
    db = SessionLocal()
    machines_data = [
        ("M1", "CNC Lathe 1", "Turning"),
        ("M2", "Milling Center 1", "Milling"),
        ("M3", "Drilling Station 1", "Drilling"),
        ("M4", "Grinding Unit 1", "Grinding"),
        ("M5", "Polishing Station 1", "Polishing")
    ]
    for mid, name, cap in machines_data:
        db.add(MachineModel(
            machine_id=mid,
            name=name,
            capability=cap,
            status=MachineStatus.IDLE.value,
            remaining_processing_time=0.0,
            total_busy_time=0.0
        ))
    db.commit()
    db.close()

    # Initial Jobs:
    # JOB_BASE_01: Op 1 on M1 (dur: 10), Op 2 on M2 (dur: 10)
    job_base_01 = Job(
        job_id="JOB_BASE_01",
        name="Turbine Shaft",
        product_type="Shaft",
        quantity=1,
        arrival_time=0.0,
        due_date=100.0,
        priority=3,
        operations=[
            Operation(sequence=1, name="Turn Shaft", machine_id="M1", duration=10.0),
            Operation(sequence=2, name="Mill Keyway", machine_id="M2", duration=10.0)
        ]
    )
    # JOB_BASE_02: Op 1 on M3 (dur: 8), Op 2 on M4 (dur: 12)
    job_base_02 = Job(
        job_id="JOB_BASE_02",
        name="Bearing Housing",
        product_type="Housing",
        quantity=1,
        arrival_time=0.0,
        due_date=100.0,
        priority=3,
        operations=[
            Operation(sequence=1, name="Drill Mounting Holes", machine_id="M3", duration=8.0),
            Operation(sequence=2, name="Grind Inner Bore", machine_id="M4", duration=12.0)
        ]
    )
    ProductionStateService.add_job(job_base_01)
    ProductionStateService.add_job(job_base_02)

    # Initial planned schedule recalculation
    planned_sched_t0 = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm="CPSAT")
    assert len(planned_sched_t0.tasks) == 4
    # Planned schedule check: M1 planned for JOB_BASE_01 Op 1, M3 planned for JOB_BASE_02 Op 1
    t_base01_op1 = next(t for t in planned_sched_t0.tasks if t.job_id == "JOB_BASE_01" and t.operation_sequence == 1)
    t_base02_op1 = next(t for t in planned_sched_t0.tasks if t.job_id == "JOB_BASE_02" and t.operation_sequence == 1)
    assert t_base01_op1.machine_id == "M1"
    assert t_base01_op1.start_time == 0.0
    assert t_base01_op1.end_time == 10.0
    assert t_base02_op1.machine_id == "M3"
    assert t_base02_op1.start_time == 0.0
    assert t_base02_op1.end_time == 8.0

    # Step 1: Advance simulation to t = 5.0 -> Parallel execution on M1 and M3
    sim = DiscreteEventSimulator(restore_from_db=True)
    sim.advance_time(5.0)
    assert sim.sim_time == 5.0

    m1 = get_machine_by_id("M1")
    m3 = get_machine_by_id("M3")
    assert m1.status == MachineStatus.BUSY
    assert m1.current_job_id == "JOB_BASE_01"
    assert round(m1.remaining_processing_time, 2) == 5.0

    assert m3.status == MachineStatus.BUSY
    assert m3.current_job_id == "JOB_BASE_02"
    assert round(m3.remaining_processing_time, 2) == 3.0

    lc_t5 = compute_lifecycle_counts()
    assert lc_t5["busy_machines"] == 2
    assert lc_t5["idle_machines"] == 3
    assert lc_t5["in_progress"] == 2
    assert lc_t5["completed"] == 0

    # Step 2: Dynamic Urgent Arrival at t=5.0 with Alternative Machine Fallback
    # Primary: M1 (which is currently BUSY on JOB_BASE_01 until t=10.0)
    # Alternative: M5 (which is currently IDLE)
    job_urgent_03 = Job(
        job_id="JOB_URGENT_03",
        name="Critical Aerospace Valve",
        product_type="Aerospace",
        quantity=1,
        arrival_time=5.0,
        due_date=40.0,
        priority=5,
        operations=[
            Operation(
                sequence=1,
                name="Valve Facing",
                machine_id="M1",
                alternative_machines=["M5"],
                duration=8.0
            )
        ]
    )
    ProductionStateService.add_job(job_urgent_03)

    # Advance by 3.0 min -> t = 8.0
    # M1 is BUSY, so dispatcher immediately routes JOB_URGENT_03 to alternative machine M5!
    sim.advance_time(3.0)
    assert sim.sim_time == 8.0

    # Verify M5 was selected and is BUSY with JOB_URGENT_03
    m5 = get_machine_by_id("M5")
    assert m5.status == MachineStatus.BUSY, "Dispatcher failed to assign idle alternative machine M5!"
    assert m5.current_job_id == "JOB_URGENT_03"
    assert round(m5.remaining_processing_time, 2) == 5.0  # 8.0 dur - 3.0 elapsed = 5.0 remaining
    
    j_urg = get_job_by_id("JOB_URGENT_03")
    assert j_urg.status == JobStatus.IN_PROGRESS
    assert j_urg.operations[0].status == OperationStatus.RUNNING
    assert j_urg.operations[0].start_time == 5.0
    assert j_urg.operations[0].assigned_machine_id == "M5"

    # Also at t=8.0: JOB_BASE_02 Op 1 finished on M3!
    # Op 2 (dur: 12 on M4) immediately dispatches to IDLE M4
    m4_t8 = get_machine_by_id("M4")
    assert m4_t8.status == MachineStatus.BUSY
    assert m4_t8.current_job_id == "JOB_BASE_02"
    assert m4_t8.current_operation_seq == 2
    assert round(m4_t8.remaining_processing_time, 2) == 12.0

    # Step 3: Machine Failure on M4 at t=8.0 while JOB_BASE_02 Op 2 is active
    # Set 10 min downtime on M4
    ProductionStateService.set_machine_downtime("M4", down_duration=10.0, reason="Spindle Thermal Overload")
    m4_down = get_machine_by_id("M4")
    # Non-preemptive policy: remaining_processing_time extends by down_duration
    assert round(m4_down.remaining_processing_time, 2) == 22.0 # 12.0 op + 10.0 downtime

    # Mid-run planned schedule recalculation at t=8.0:
    # Shows how optimizer plans future unfinished work from t=8.0 forward
    planned_sched_t8 = ProductionStateService.recalculate_schedule(sim_time=8.0, algorithm="CPSAT")
    # Confirms remaining active ops planned without conflicting with running tasks
    assert len(planned_sched_t8.tasks) > 0
    t_urg_planned = next(t for t in planned_sched_t8.tasks if t.job_id == "JOB_URGENT_03")
    assert t_urg_planned.is_running is True
    assert t_urg_planned.machine_id == "M5"

    # Step 4: Advance to t = 10.0
    sim.advance_time(2.0)
    assert sim.sim_time == 10.0

    # At t=10.0: JOB_BASE_01 Op 1 finishes on M1!
    # Op 2 (dur: 10 on M2) immediately dispatches to IDLE M2
    m1_t10 = get_machine_by_id("M1")
    assert m1_t10.status == MachineStatus.IDLE
    m2_t10 = get_machine_by_id("M2")
    assert m2_t10.status == MachineStatus.BUSY
    assert m2_t10.current_job_id == "JOB_BASE_01"
    assert m2_t10.current_operation_seq == 2

    # Step 5: Advance to t = 13.0
    # JOB_URGENT_03 (start=5.0, dur=8.0) completes on M5!
    sim.advance_time(3.0)
    assert sim.sim_time == 13.0

    j_urg_t13 = get_job_by_id("JOB_URGENT_03")
    assert j_urg_t13.status == JobStatus.COMPLETED
    assert j_urg_t13.operations[0].status == OperationStatus.COMPLETED
    assert j_urg_t13.operations[0].start_time == 5.0
    assert j_urg_t13.operations[0].end_time == 13.0
    m5_t13 = get_machine_by_id("M5")
    assert m5_t13.status == MachineStatus.IDLE

    # Step 6: Advance to t = 20.0
    # JOB_BASE_01 Op 2 (start=10.0, dur=10.0) completes on M2!
    sim.advance_time(7.0)
    assert sim.sim_time == 20.0

    j_base01_t20 = get_job_by_id("JOB_BASE_01")
    assert j_base01_t20.status == JobStatus.COMPLETED
    assert j_base01_t20.operations[1].end_time == 20.0
    m2_t20 = get_machine_by_id("M2")
    assert m2_t20.status == MachineStatus.IDLE

    # Step 7: Advance to t = 30.0
    # M4 finishes repair & processing of JOB_BASE_02 Op 2 (12 op + 10 down = 22 mins from t=8 -> t=30.0)
    sim.advance_time(10.0)
    assert sim.sim_time == 30.0

    j_base02_t30 = get_job_by_id("JOB_BASE_02")
    assert j_base02_t30.status == JobStatus.COMPLETED
    assert j_base02_t30.operations[1].end_time == 30.0
    m4_t30 = get_machine_by_id("M4")
    assert m4_t30.status == MachineStatus.IDLE
    assert m4_t30.remaining_processing_time == 0.0

    # Final Lifecycle State Assertion:
    lc_final = compute_lifecycle_counts()
    assert lc_final["total_jobs"] == 3
    assert lc_final["completed"] == 3
    assert lc_final["in_progress"] == 0
    assert lc_final["pending"] == 0
    assert lc_final["busy_machines"] == 0
    assert lc_final["idle_machines"] == 5

    # Verification of all actual operation timestamps:
    all_jobs_final = ProductionStateService.get_all_jobs()
    for j in all_jobs_final:
        assert j.status == JobStatus.COMPLETED
        for op in j.operations:
            assert op.status == OperationStatus.COMPLETED
            assert op.start_time is not None
            assert op.end_time is not None
            assert op.end_time >= op.start_time + op.duration

    # When all jobs are completed, scheduler correctly leaves remaining queue empty
    sched_final = ProductionStateService.recalculate_schedule(sim_time=30.0, algorithm="CPSAT")
    assert len(sched_final.tasks) == 0
    assert sched_final.metrics.queue_length == 0

def test_scenario_2_full_system_persistence_and_reload_integrity(reset_db):
    """
    Scenario 2:
    Simulates mid-run application restart / process reload.
    1. Initializes 3 machines and 2 jobs.
    2. Runs simulation to an intermediate event point (t=7.0).
    3. Simulates a complete service teardown by discarding simulator instance and DB session.
    4. Re-initializes DiscreteEventSimulator(restore_from_db=True) and verifies:
       - Exact sim_time restored.
       - Machines retain BUSY status, current_job_id, and exact remaining processing time.
       - Active operation retains start_time.
       - Queued job remains PENDING.
    5. Advances resumed simulator to completion and confirms no duplicate operations or time drift.
    """
    init_db()
    db = SessionLocal()
    for mid in ["M1", "M2", "M3"]:
        db.add(MachineModel(
            machine_id=mid,
            name=f"Machine {mid}",
            capability="General",
            status=MachineStatus.IDLE.value,
            remaining_processing_time=0.0,
            total_busy_time=0.0
        ))
    db.commit()
    db.close()

    job_a = Job(
        job_id="JOB_PERSIST_A",
        name="Job A",
        product_type="TypeA",
        quantity=1,
        arrival_time=0.0,
        due_date=50.0,
        priority=3,
        operations=[Operation(sequence=1, name="A1", machine_id="M1", duration=14.0)]
    )
    job_b = Job(
        job_id="JOB_PERSIST_B",
        name="Job B",
        product_type="TypeB",
        quantity=1,
        arrival_time=0.0,
        due_date=50.0,
        priority=2,
        operations=[Operation(sequence=1, name="B1", machine_id="M1", duration=10.0)]
    )
    ProductionStateService.add_job(job_a)
    ProductionStateService.add_job(job_b)

    # Initial Run to intermediate clock t = 7.0
    sim_session1 = DiscreteEventSimulator(restore_from_db=True)
    sim_session1.advance_time(7.0)
    assert sim_session1.sim_time == 7.0

    # Verify state before simulated shutdown
    m1_s1 = get_machine_by_id("M1")
    assert m1_s1.status == MachineStatus.BUSY
    assert m1_s1.current_job_id == "JOB_PERSIST_A"
    assert round(m1_s1.remaining_processing_time, 2) == 7.0  # 14.0 - 7.0 = 7.0

    # Mid-run planned schedule check before restart
    sched_mid1 = ProductionStateService.recalculate_schedule(sim_time=7.0, algorithm="CPSAT")
    assert len(sched_mid1.tasks) == 2  # A1 (running) + B1 (pending)

    # SIMULATED APPLICATION CRASH / RESTART:
    del sim_session1

    # Start fresh simulator from DB
    sim_session2 = DiscreteEventSimulator(restore_from_db=True)
    
    # 1. Clock restoration
    assert sim_session2.sim_time == 7.0, f"Expected restored clock 7.0, found {sim_session2.sim_time}"

    # 2. Machine state restoration
    m1_s2 = get_machine_by_id("M1")
    assert m1_s2.status == MachineStatus.BUSY
    assert m1_s2.current_job_id == "JOB_PERSIST_A"
    assert round(m1_s2.remaining_processing_time, 2) == 7.0
    assert round(m1_s2.total_busy_time, 2) == 7.0

    # 3. Active and queued jobs restoration
    ja_s2 = get_job_by_id("JOB_PERSIST_A")
    assert ja_s2.status == JobStatus.IN_PROGRESS
    assert ja_s2.operations[0].status == OperationStatus.RUNNING
    assert ja_s2.operations[0].start_time == 0.0
    assert ja_s2.operations[0].end_time is None

    jb_s2 = get_job_by_id("JOB_PERSIST_B")
    assert jb_s2.status == JobStatus.PENDING
    assert jb_s2.operations[0].status == OperationStatus.PENDING
    assert jb_s2.operations[0].start_time is None

    # Mid-run planned schedule check after restart matches exactly
    sched_mid2 = ProductionStateService.recalculate_schedule(sim_time=7.0, algorithm="CPSAT")
    assert len(sched_mid2.tasks) == 2

    # 4. Resume execution to completion from restored state
    # Advance by 7.0 min -> t = 14.0 (Job A finishes, Job B starts on M1)
    sim_session2.advance_time(7.0)
    assert sim_session2.sim_time == 14.0

    ja_done = get_job_by_id("JOB_PERSIST_A")
    assert ja_done.status == JobStatus.COMPLETED
    assert ja_done.operations[0].end_time == 14.0

    m1_mid = get_machine_by_id("M1")
    assert m1_mid.status == MachineStatus.BUSY
    assert m1_mid.current_job_id == "JOB_PERSIST_B"
    assert round(m1_mid.remaining_processing_time, 2) == 10.0

    # Advance by 10.0 min -> t = 24.0 (Job B finishes)
    sim_session2.advance_time(10.0)
    assert sim_session2.sim_time == 24.0

    jb_done = get_job_by_id("JOB_PERSIST_B")
    assert jb_done.status == JobStatus.COMPLETED
    assert jb_done.operations[0].end_time == 24.0

    m1_final = get_machine_by_id("M1")
    assert m1_final.status == MachineStatus.IDLE
    assert m1_final.remaining_processing_time == 0.0
    assert round(m1_final.total_busy_time, 2) == 24.0

    # Confirm all jobs completed and final schedule queue is 0
    final_sched = ProductionStateService.recalculate_schedule(sim_time=24.0, algorithm="CPSAT")
    assert len(final_sched.tasks) == 0
    assert final_sched.metrics.queue_length == 0
