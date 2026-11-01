import pytest
import os
from app.schemas.models import Job, Operation, Machine, MachineStatus, OperationStatus
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.simulation.engine import DiscreteEventSimulator
from app.core.state_service import ProductionStateService, StaleScheduleError
from app.scheduling.validator import ScheduleValidator
from app.database.db import init_db, SessionLocal, JobModel, MachineModel

def test_adversarial_machine_failure_during_concurrent_execution(reset_db):
    """
    PART 10-A: Three independent jobs running on M1, M2, and M3.
    M2 fails unexpectedly (downtime).
    Verify that M1 and M3 continue uninterrupted to completion,
    while only M2's job is delayed by the repair window.
    """
    machines = [
        Machine(machine_id="M1", name="CNC Lathe 1", capability="Turning", status=MachineStatus.IDLE),
        Machine(machine_id="M2", name="Milling Center", capability="Milling", status=MachineStatus.IDLE),
        Machine(machine_id="M3", name="Grinding Station", capability="Grinding", status=MachineStatus.IDLE),
    ]
    jobs = [
        Job(job_id="J_A", name="Part A", product_type="Shaft", quantity=1, arrival_time=0.0, due_date=100.0, priority=3,
            operations=[Operation(sequence=1, name="Turn", machine_id="M1", duration=10.0)]),
        Job(job_id="J_B", name="Part B", product_type="Bracket", quantity=1, arrival_time=0.0, due_date=100.0, priority=3,
            operations=[Operation(sequence=1, name="Mill", machine_id="M2", duration=15.0)]),
        Job(job_id="J_C", name="Part C", product_type="Pin", quantity=1, arrival_time=0.0, due_date=100.0, priority=3,
            operations=[Operation(sequence=1, name="Grind", machine_id="M3", duration=8.0)]),
    ]

    # Save to isolated DB
    init_db()
    db = SessionLocal()
    for m in machines:
        db.add(MachineModel(machine_id=m.machine_id, name=m.name, capability=m.capability, status=m.status.value,
                           remaining_processing_time=0.0, total_busy_time=0.0))
    for j in jobs:
        db.add(JobModel(job_id=j.job_id, name=j.name, product_type=j.product_type, quantity=1, arrival_time=0.0,
                        due_date=100.0, priority=3, status="PENDING",
                        operations_json=[op.dict() for op in j.operations]))
    db.commit()
    db.close()

    # Step sim to t=2.0 -> All three jobs dispatched to M1, M2, M3
    sim = DiscreteEventSimulator(restore_from_db=True)
    sim.advance_time(2.0)
    
    # Assert all three machines are BUSY
    db = SessionLocal()
    m_states = {m.machine_id: m.status for m in db.query(MachineModel).all()}
    assert m_states["M1"] == MachineStatus.BUSY.value
    assert m_states["M2"] == MachineStatus.BUSY.value
    assert m_states["M3"] == MachineStatus.BUSY.value
    db.close()

    # Trigger breakdown on M2 for 20 mins
    ProductionStateService.set_machine_downtime("M2", down_duration=20.0, reason="Spindle Failure")

    # M1 and M3 must continue unaffected: advance to t=10.0
    sim.advance_time(8.0) # now t=10.0
    db = SessionLocal()
    j_c = db.query(JobModel).filter(JobModel.job_id == "J_C").first()
    j_a = db.query(JobModel).filter(JobModel.job_id == "J_A").first()
    j_b = db.query(JobModel).filter(JobModel.job_id == "J_B").first()
    
    # J_C (duration 8) must be COMPLETED at t=8.0
    assert j_c.status == "COMPLETED"
    # J_A (duration 10) must be COMPLETED at t=10.0
    assert j_a.status == "COMPLETED"
    # J_B (duration 15 + 20 downtime) is still running or repairing
    assert j_b.status != "COMPLETED"
    db.close()


def test_scheduling_stress_30_heterogeneous_jobs(reset_db):
    """
    PART 10-B: Scheduling stress test with 30 jobs having heterogeneous
    durations (5 to 120 minutes) across 10 machines.
    Asserts solver produces valid, gap-inserted, non-overlapping schedule in < 5 seconds.
    """
    import time
    machines = [
        Machine(machine_id=f"M{i}", name=f"Machine {i}", capability=f"Cap_{i}", status=MachineStatus.IDLE)
        for i in range(1, 11)
    ]
    durations = [5.0, 12.0, 25.0, 45.0, 60.0, 90.0, 120.0]
    jobs = []
    for j_idx in range(1, 31):
        m_id = f"M{(j_idx % 10) + 1}"
        alt_m = f"M{((j_idx + 1) % 10) + 1}"
        dur = durations[j_idx % len(durations)]
        jobs.append(
            Job(
                job_id=f"JOB_STRESS_{j_idx:02d}",
                name=f"Stress Job {j_idx}",
                product_type="Component",
                quantity=1,
                arrival_time=float((j_idx % 5) * 10),
                due_date=float(300 + j_idx * 20),
                priority=(j_idx % 5) + 1,
                operations=[
                    Operation(sequence=1, name="Stage 1", machine_id=m_id, alternative_machines=[alt_m], duration=dur),
                    Operation(sequence=2, name="Stage 2", machine_id=alt_m, duration=dur * 0.8)
                ]
            )
        )

    t0 = time.perf_counter()
    res = DispatchHeuristicScheduler.schedule(jobs, machines, current_time=0.0, rule="SPT")
    t1 = time.perf_counter()

    assert len(res.tasks) == 60 # 30 jobs * 2 operations
    assert t1 - t0 < 5.0 # fast heuristic execution

    # Independent validation
    is_valid, errors = ScheduleValidator.validate(res.tasks, machines, current_time=0.0, jobs=jobs)
    assert is_valid, f"Stress schedule failed validation: {errors}"


def test_concurrent_api_recalculation_conflict(reset_db):
    """
    PART 10-C: Tests concurrency state versioning.
    When a client recalculates with an outdated expected_state_version,
    the backend must reject the request with a StaleScheduleError (HTTP 409).
    """
    init_db()
    db = SessionLocal()
    for i in range(1, 4):
        db.add(MachineModel(machine_id=f"M{i}", name=f"M{i}", capability="Work", status="IDLE",
                           remaining_processing_time=0.0, total_busy_time=0.0))
    db.add(JobModel(job_id="J_CONC", name="Concurrent Job", product_type="P", quantity=1, arrival_time=0.0,
                    due_date=100.0, priority=3, status="PENDING",
                    operations_json=[{"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 10.0, "status": "PENDING"}]))
    db.commit()
    db.close()

    # Initial recalculation
    res1 = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm="SPT")
    v1 = res1.explanation.get("state_version", 1)

    # State update happens (e.g. new job arrives or downtime triggered), incrementing version
    ProductionStateService.set_machine_downtime("M1", down_duration=10.0)

    # Client attempts recalculation expecting old version v1 -> Must raise StaleScheduleError
    with pytest.raises(StaleScheduleError) as exc_info:
        ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm="SPT", expected_state_version=v1)
    
    assert "Stale schedule request rejected" in str(exc_info.value)
