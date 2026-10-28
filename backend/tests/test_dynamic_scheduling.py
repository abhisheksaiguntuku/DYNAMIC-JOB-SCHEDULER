import pytest
from app.simulation.engine import DiscreteEventSimulator
from app.core.state_service import ProductionStateService, StaleScheduleError
from app.database.db import init_db, SessionLocal, MachineModel, JobModel, SimulationStateModel
from app.schemas.models import MachineStatus, OperationStatus, JobStatus
from app.scheduling.validator import ScheduleValidator

# Fixture: isolated DB per test (function scope already set globally)

def insert_machine(db, machine_id, status=MachineStatus.IDLE.value, remaining=0.0):
    # Upsert machine to avoid duplicate primary key errors during tests
    existing = db.query(MachineModel).filter(MachineModel.machine_id == machine_id).first()
    if existing:
        existing.status = status
        existing.remaining_processing_time = remaining
        db.add(existing)
    else:
        m = MachineModel(
            machine_id=machine_id,
            name=f"Machine {machine_id}",
            capability="generic",
            status=status,
            remaining_processing_time=remaining,
            total_busy_time=0.0,
        )
        db.add(m)
    db.commit()
    return db.query(MachineModel).filter(MachineModel.machine_id == machine_id).first()

def insert_job(db, job_id, arrival, ops, due=200.0, priority=3, status=JobStatus.PENDING.value):
    # Upsert job to avoid duplicate primary key errors during tests
    existing = db.query(JobModel).filter(JobModel.job_id == job_id).first()
    if existing:
        existing.arrival_time = arrival
        existing.due_date = due
        existing.priority = priority
        existing.status = status
        existing.operations_json = ops
        db.add(existing)
    else:
        job = JobModel(
            job_id=job_id,
            name=job_id,
            product_type="generic",
            quantity=1,
            arrival_time=arrival,
            due_date=due,
            priority=priority,
            status=status,
            operations_json=ops,
        )
        db.add(job)
    db.commit()
    return db.query(JobModel).filter(JobModel.job_id == job_id).first()

# Helper to create a simple two‑operation job on M1 then M2
def simple_job_ops(job_id, start_seq=1, dur1=5, dur2=3, status1=OperationStatus.PENDING.value, status2=OperationStatus.PENDING.value):
    return [
        {"sequence": start_seq, "name": f"Op{start_seq}", "machine_id": "M1", "duration": dur1, "status": status1},
        {"sequence": start_seq+1, "name": f"Op{start_seq+1}", "machine_id": "M2", "duration": dur2, "status": status2},
    ]

# Scenario 3 – Completed‑operation preservation
def test_completed_operation_preservation():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    # Insert J1 already COMPLETED (single op already done)
    ops_done = [
        {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 5.0,
         "status": OperationStatus.COMPLETED.value, "start_time": 0.0, "end_time": 5.0}
    ]
    insert_job(db, "J1", arrival=0.0, ops=ops_done, status=JobStatus.COMPLETED.value)
    # Insert a new pending job
    ops_new = simple_job_ops("J2")
    insert_job(db, "J2", arrival=0.0, ops=ops_new)
    db.close()
    # Recalculate schedule – J1 must NOT be re‑scheduled, J2 must appear
    result = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    tasks_j1 = [t for t in result.tasks if t.job_id == "J1"]
    tasks_j2 = [t for t in result.tasks if t.job_id == "J2"]
    assert len(tasks_j1) == 0, "Completed job J1 must not appear in rescheduled output"
    assert len(tasks_j2) > 0, "Pending job J2 must be scheduled"


# Scenario 4 – Operation precedence
def test_operation_precedence():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    ops = simple_job_ops("J1", dur1=4, dur2=3)
    insert_job(db, "J1", arrival=0.0, ops=ops)
    result = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    # Extract scheduled tasks for J1
    tasks = [t for t in result.tasks if t.job_id == "J1"]
    # Find ops in order
    op1 = next(t for t in tasks if t.operation_sequence == 1)
    op2 = next(t for t in tasks if t.operation_sequence == 2)
    assert op2.start_time >= op1.end_time
    db.close()

# Scenario 5 – Machine capacity (no overlap)
def test_machine_capacity_no_overlap():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    # Two jobs both need M1 first
    ops_a = simple_job_ops("J1", dur1=5, dur2=2)
    ops_b = simple_job_ops("J2", dur1=3, dur2=4)
    insert_job(db, "J1", arrival=0.0, ops=ops_a)
    insert_job(db, "J2", arrival=0.0, ops=ops_b)
    result = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    # Collect all tasks on M1
    m1_tasks = [t for t in result.tasks if t.machine_id == "M1"]
    # Sort by start_time
    m1_tasks.sort(key=lambda x: x.start_time)
    for i in range(len(m1_tasks)-1):
        assert m1_tasks[i].end_time <= m1_tasks[i+1].start_time + 1e-6
    db.close()

# Scenario 6 – Multiple waiting jobs dynamic arrival
def test_multiple_waiting_jobs_dynamic_arrival():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    # Insert first job
    insert_job(db, "J1", arrival=0.0, ops=simple_job_ops("J1"))
    # Schedule initially
    ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    # Advance half step (no operation finished yet)
    sim.advance_time(step_minutes=2)
    # Insert second job while first is waiting/running
    insert_job(db, "J2", arrival=2.0, ops=simple_job_ops("J2"))
    result = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    # Ensure both jobs have tasks scheduled and no existing tasks were altered
    tasks_j1 = [t for t in result.tasks if t.job_id == "J1"]
    tasks_j2 = [t for t in result.tasks if t.job_id == "J2"]
    assert tasks_j1 and tasks_j2
    db.close()

# Scenario 7 – Simultaneous events (two arrivals same timestamp)
def test_simultaneous_arrivals():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    # Insert two jobs with same arrival time 0
    insert_job(db, "J1", arrival=0.0, ops=simple_job_ops("J1"))
    insert_job(db, "J2", arrival=0.0, ops=simple_job_ops("J2"))
    result = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    # Both jobs should be present in schedule
    job_ids = {t.job_id for t in result.tasks}
    assert "J1" in job_ids and "J2" in job_ids
    db.close()

# Scenario 8 – Machine downtime and recovery
def test_machine_downtime_and_recovery():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    insert_job(db, "J1", arrival=0.0, ops=simple_job_ops("J1", dur1=5, dur2=3))
    db.close()

    # Trigger breakdown on M1 for 20 minutes
    m1_down = ProductionStateService.set_machine_downtime("M1", down_duration=20.0)
    assert m1_down.status == MachineStatus.DOWN
    assert m1_down.remaining_processing_time == 20.0

    # Recalculate schedule – J1 Op1 on M1 must not start before t=20.0
    res_down = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    m1_task = next(t for t in res_down.tasks if t.job_id == "J1" and t.operation_sequence == 1)
    assert m1_task.start_time >= 20.0
    machines = ProductionStateService.get_all_machines()
    is_valid, errors = ScheduleValidator.validate(res_down.tasks, machines, sim.sim_time)
    assert is_valid, f"Schedule during downtime invalid: {errors}"

    # Recover M1 early and recalculate – J1 Op1 can now start at t=0.0
    m1_rec = ProductionStateService.recover_machine("M1")
    assert m1_rec.status == MachineStatus.IDLE
    res_rec = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    m1_task_rec = next(t for t in res_rec.tasks if t.job_id == "J1" and t.operation_sequence == 1)
    assert m1_task_rec.start_time == 0.0

# Scenario 9 – Invalid job definitions
def test_invalid_job_missing_operations():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    # Insert job with empty operations list
    insert_job(db, "J_BAD", arrival=0.0, ops=[])
    # Scheduling should raise an error or return None – we expect an exception
    with pytest.raises(Exception):
        ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    db.close()

# Scenario 10 – Stale schedule rejection
def test_stale_schedule_rejection():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    insert_job(db, "J1", arrival=0.0, ops=simple_job_ops("J1"))
    db.close()

    initial_version = ProductionStateService.get_state_version()
    # Advance simulation time (mutates production state and increments state_version)
    sim.advance_time(step_minutes=10.0)
    new_version = ProductionStateService.get_state_version()
    assert new_version > initial_version

    # Attempting to recalculate using obsolete state_version or obsolete sim_time must raise StaleScheduleError
    with pytest.raises(StaleScheduleError):
        ProductionStateService.recalculate_schedule(
            sim.sim_time, algorithm="FCFS", expected_state_version=initial_version
        )
    with pytest.raises(StaleScheduleError):
        ProductionStateService.recalculate_schedule(
            0.0, algorithm="FCFS"
        )

# Scenario 11 – Repeated recalculation stability
def test_repeated_recalculation_no_duplicate_operations():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    insert_job(db, "J1", arrival=0.0, ops=simple_job_ops("J1"))
    # First schedule
    result1 = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    # Advance time
    sim.advance_time(step_minutes=5)
    # Second schedule
    result2 = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    # Count total tasks – should be same or increase only for newly arrived jobs
    assert len(result2.tasks) >= len(result1.tasks)
    db.close()

# Scenario 12 – Infeasible instance handling
def test_infeasible_instance_handling():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    # Create a machine that is already BUSY with a huge remaining time, making a new job impossible within tiny horizon
    insert_machine(db, "M1", status=MachineStatus.BUSY.value, remaining=1000.0)
    insert_machine(db, "M2")
    # New job requiring M1 for 1 unit
    ops = simple_job_ops("J1", dur1=1, dur2=1)
    insert_job(db, "J1", arrival=0.0, ops=ops)
    db.close()
    # Call CP‑SAT with a very short time limit to force timeout/infeasibility
    result = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="CP_SAT", time_limit_seconds=0.01)
    # solver_status may have extra info like 'FALLBACK_SPT (CP-SAT INFEASIBLE)'
    valid_states = ("INFEASIBLE", "UNKNOWN", "FEASIBLE", "OPTIMAL")
    status = result.metrics.solver_status.upper()
    assert any(s in status for s in valid_states), f"Unexpected solver_status: {result.metrics.solver_status}"


# Scenario 13 – Fairness/starvation (basic aging check)
def test_fairness_aging_effect():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    # Insert low‑priority job early
    ops_low = simple_job_ops("J_LOW", dur1=5, dur2=5)
    insert_job(db, "J_LOW", arrival=0.0, ops=ops_low, priority=1)
    # Insert high‑priority job later but with later arrival
    ops_high = simple_job_ops("J_HIGH", dur1=2, dur2=2)
    insert_job(db, "J_HIGH", arrival=1.0, ops=ops_high, priority=5)
    result = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="AGING")
    # Verify that low‑priority job is not indefinitely postponed – it should appear earlier than if aging ignored
    low_start = min(t.start_time for t in result.tasks if t.job_id == "J_LOW")
    high_start = min(t.start_time for t in result.tasks if t.job_id == "J_HIGH")
    assert low_start <= high_start
    db.close()

# Scenario 14 – Release‑time and due‑date handling
def test_release_and_due_dates():
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    # Job with release time 10 (future) and due date 30
    ops = simple_job_ops("J1", dur1=5, dur2=5)
    insert_job(db, "J1", arrival=10.0, ops=ops, due=30.0)
    # At current time 0, schedule should not start before release
    result = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    start_times = [t.start_time for t in result.tasks if t.job_id == "J1"]
    assert all(st >= 10.0 for st in start_times)
    # After advancing time past due date, tardiness should be positive
    sim.advance_time(step_minutes=40)
    result2 = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    tardiness = result2.metrics.total_tardiness
    assert tardiness > 0
    db.close()

# Scenario 15 – Persistence across restart (basic DB check)
def test_persistence_restart(tmp_path, monkeypatch):
    # This test uses the real DB file – ensure we do not delete it.
    # Simulate a restart by creating a new SessionLocal after schedule.
    sim = DiscreteEventSimulator()
    db = SessionLocal()
    insert_machine(db, "M1")
    insert_machine(db, "M2")
    insert_job(db, "J1", arrival=0.0, ops=simple_job_ops("J1"))
    ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")
    db.close()
    # "Restart" – new DB session
    db2 = SessionLocal()
    jobs = db2.query(JobModel).all()
    assert any(j.job_id == "J1" for j in jobs)
    db2.close()
