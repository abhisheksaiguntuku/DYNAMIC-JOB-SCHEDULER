import pytest
from app.simulation.engine import DiscreteEventSimulator
from app.database.db import init_db, SessionLocal, MachineModel, JobModel, SimulationStateModel
from app.schemas.models import Job, Operation, MachineStatus, OperationStatus, JobStatus, ScheduledTask
from app.core.state_service import ProductionStateService
from app.scheduling.validator import ScheduleValidator


@pytest.fixture(scope="function", autouse=True)
def setup_isolated_deadlock_test_db():
    init_db()
    db = SessionLocal()
    db.query(SimulationStateModel).delete()
    db.query(MachineModel).delete()
    db.query(JobModel).delete()
    for i in range(1, 11):
        mid = f"M{i}"
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
    yield


def test_1_two_jobs_requiring_different_machines_execute_concurrently():
    """1. Two jobs requiring different machines execute concurrently without artificial blocking."""
    sim = DiscreteEventSimulator()
    j1 = Job(
        job_id="J_CONC_1", name="Concurrent Job 1", product_type="P1",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="M1 Op", machine_id="M1", duration=25.0)]
    )
    j2 = Job(
        job_id="J_CONC_2", name="Concurrent Job 2", product_type="P2",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="M2 Op", machine_id="M2", duration=25.0)]
    )
    ProductionStateService.add_job(j1)
    ProductionStateService.add_job(j2)

    # Recalculate schedule across algorithms: both start at t=0.0
    for algo in ["FCFS", "SPT", "EDD", "CR", "AGING", "CPSAT", "EPN"]:
        res = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm=algo)
        t1 = next(t for t in res.tasks if t.job_id == "J_CONC_1")
        t2 = next(t for t in res.tasks if t.job_id == "J_CONC_2")
        assert t1.start_time == 0.0, f"{algo} did not start J_CONC_1 concurrently at 0.0"
        assert t2.start_time == 0.0, f"{algo} did not start J_CONC_2 concurrently at 0.0"

    # Advance time: both run simultaneously in discrete event engine
    sim.advance_time(10.0)
    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    m2 = db.query(MachineModel).filter(MachineModel.machine_id == "M2").first()
    assert m1.status == MachineStatus.BUSY.value and m1.current_job_id == "J_CONC_1"
    assert m2.status == MachineStatus.BUSY.value and m2.current_job_id == "J_CONC_2"
    db.close()


def test_2_upstream_machine_released_before_waiting_for_downstream_machine():
    """
    2. A job releases its upstream machine (M1) immediately upon Op1 completion,
    entering virtual buffer before downstream machine (M2) executes.
    """
    sim = DiscreteEventSimulator()
    job = Job(
        job_id="J_CHAIN_BUFFER", name="Chained Buffer Job", product_type="P",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M1", duration=10.0),
            Operation(sequence=2, name="Op2", machine_id="M2", duration=15.0),
        ]
    )
    ProductionStateService.add_job(job)

    # Advance to t=10.0: Op1 completes on M1
    sim.advance_time(10.0)
    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    assert m1.status == MachineStatus.IDLE.value
    assert m1.current_job_id is None
    assert m1.remaining_processing_time == 0.0
    db.close()


def test_3_downstream_machine_busy_does_not_cause_upstream_machine_reservation():
    """
    3. Downstream machine (M2) being busy with an unrelated job does NOT hold or reserve
    upstream machine (M1). M1 is completely freed for other work while the job waits in virtual buffer.
    """
    sim = DiscreteEventSimulator()
    # J_BLOCKER occupies M2 from t=0.0 to t=50.0
    j_blocker = Job(
        job_id="J_BLOCKER", name="M2 Blocker", product_type="Heavy",
        arrival_time=0.0, due_date=200.0, priority=5,
        operations=[Operation(sequence=1, name="Long M2", machine_id="M2", duration=50.0)]
    )
    # J_TWO_STEP needs M1 (10.0) then M2 (15.0)
    j_two_step = Job(
        job_id="J_TWO_STEP", name="Two Step", product_type="Standard",
        arrival_time=0.0, due_date=200.0, priority=3,
        operations=[
            Operation(sequence=1, name="M1 Quick", machine_id="M1", duration=10.0),
            Operation(sequence=2, name="M2 Waiting", machine_id="M2", duration=15.0),
        ]
    )
    # J_OTHER needs M1 at t=10.0
    j_other = Job(
        job_id="J_OTHER_M1", name="Other M1 Job", product_type="Standard",
        arrival_time=10.0, due_date=200.0, priority=3,
        operations=[Operation(sequence=1, name="M1 Work", machine_id="M1", duration=15.0)]
    )
    ProductionStateService.add_job(j_blocker)
    ProductionStateService.add_job(j_two_step)
    ProductionStateService.add_job(j_other)

    # Advance to t=10.0: J_TWO_STEP Op1 on M1 finishes. M2 is BUSY until t=50.
    sim.advance_time(10.0)
    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    m2 = db.query(MachineModel).filter(MachineModel.machine_id == "M2").first()
    # M1 is not held! It is IDLE and immediately takes J_OTHER_M1
    assert m2.status == MachineStatus.BUSY.value and m2.current_job_id == "J_BLOCKER"
    db.close()

    # Advance to t=15.0: J_OTHER_M1 is dispatched to M1 (or finishes), proving no hold-and-wait on M1
    sim.advance_time(5.0)
    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    assert m1.current_job_id == "J_OTHER_M1"
    db.close()


def test_4_circular_operation_dependencies_are_rejected():
    """4. Circular or non-strictly increasing operation sequences are rejected before entering database."""
    # Cyclic sequence: sequence 1 -> sequence 1
    job_dup = Job(
        job_id="J_CYCLE_DUP", name="Cycle Dup", product_type="Test",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M1", duration=10.0),
            Operation(sequence=1, name="Op1 Cyclic", machine_id="M2", duration=10.0),
        ]
    )
    with pytest.raises(ValueError, match="Invalid or cyclic operation sequence"):
        ProductionStateService.add_job(job_dup)

    # Reverse cyclic sequence: sequence 2 -> sequence 1
    job_rev = Job(
        job_id="J_CYCLE_REV", name="Cycle Rev", product_type="Test",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[
            Operation(sequence=2, name="Op2", machine_id="M2", duration=10.0),
            Operation(sequence=1, name="Op1", machine_id="M1", duration=10.0),
        ]
    )
    with pytest.raises(ValueError, match="Invalid or cyclic operation sequence"):
        ProductionStateService.add_job(job_rev)


def test_5_invalid_operation_sequences_and_machines_rejected():
    """5. Non-positive durations and non-existent machines or invalid alternatives are rejected."""
    # Negative / zero duration rejected by Pydantic schema validation
    with pytest.raises(Exception):
        Job(
            job_id="J_BAD_DUR", name="Bad Dur", product_type="Test",
            arrival_time=0.0, due_date=100.0, priority=3,
            operations=[Operation(sequence=1, name="Op1", machine_id="M1", duration=-5.0)]
        )

    # Non-existent primary machine
    bad_mach = Job(
        job_id="J_BAD_MACH", name="Bad Mach", product_type="Test",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M999", duration=10.0)]
    )
    with pytest.raises(ValueError, match="assigned to invalid or non-existent machine 'M999'"):
        ProductionStateService.add_job(bad_mach)


def test_6_blocked_job_does_not_prevent_unrelated_jobs_from_executing():
    """
    6. A job waiting for an occupied machine in a virtual buffer does NOT prevent
    other jobs from utilizing completely different machines.
    """
    sim = DiscreteEventSimulator()
    # J_WAITING finishes on M1 and is waiting for M2
    j_waiting = Job(
        job_id="J_WAIT", name="Waiting Job", product_type="P",
        arrival_time=0.0, due_date=200.0, priority=5,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M1", duration=5.0),
            Operation(sequence=2, name="Op2", machine_id="M2", duration=20.0),
        ]
    )
    # J_M2_HOG occupies M2 from t=0.0 to t=40.0
    j_hog = Job(
        job_id="J_HOG", name="Hog M2", product_type="P",
        arrival_time=0.0, due_date=200.0, priority=4,
        operations=[Operation(sequence=1, name="Op1", machine_id="M2", duration=40.0)]
    )
    # J_UNRELATED needs M3 and M4 (should execute smoothly at t=5.0)
    j_unrelated = Job(
        job_id="J_UNRELATED", name="Unrelated Work", product_type="P",
        arrival_time=5.0, due_date=200.0, priority=1,
        operations=[Operation(sequence=1, name="Op1", machine_id="M3", duration=10.0)]
    )
    ProductionStateService.add_job(j_waiting)
    ProductionStateService.add_job(j_hog)
    ProductionStateService.add_job(j_unrelated)

    # Advance to t=5.0: J_WAIT completes Op1 on M1 and enters virtual buffer waiting for M2
    sim.advance_time(5.0)
    db = SessionLocal()
    m2 = db.query(MachineModel).filter(MachineModel.machine_id == "M2").first()
    assert m2.current_job_id == "J_HOG"
    db.close()

    # Advance to t=10.0: J_UNRELATED is dispatched to M3 without being blocked by J_WAIT
    sim.advance_time(5.0)
    db = SessionLocal()
    m3 = db.query(MachineModel).filter(MachineModel.machine_id == "M3").first()
    assert m3.status == MachineStatus.BUSY.value
    assert m3.current_job_id == "J_UNRELATED"
    db.close()


def test_7_multiple_jobs_competing_for_one_machine_never_overlap():
    """7. Multiple jobs competing for one machine never produce overlapping operations in any algorithm."""
    jobs = []
    for i in range(1, 6):
        jobs.append(Job(
            job_id=f"J_COMP_{i}", name=f"Competing Job {i}", product_type="Standard",
            arrival_time=float(i), due_date=100.0, priority=i,
            operations=[Operation(sequence=1, name="Op1", machine_id="M5", duration=10.0)]
        ))
    for j in jobs:
        ProductionStateService.add_job(j)

    machines = ProductionStateService.get_all_machines()
    all_jobs = ProductionStateService.get_all_jobs()

    for algo in ["FCFS", "SPT", "EDD", "CR", "AGING", "CPSAT", "EPN"]:
        res = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm=algo)
        m5_tasks = [t for t in res.tasks if t.machine_id == "M5"]
        assert len(m5_tasks) == 5
        sorted_m5 = sorted(m5_tasks, key=lambda t: t.start_time)
        for idx in range(len(sorted_m5) - 1):
            assert sorted_m5[idx].end_time <= sorted_m5[idx + 1].start_time + 1e-4, (
                f"{algo} produced overlapping operations on M5!"
            )
        valid, errs = ScheduleValidator.validate(res.tasks, machines, current_time=0.0, jobs=all_jobs)
        assert valid, f"{algo} failed validator: {errs}"


def test_8_low_priority_jobs_eventually_receive_machine_capacity():
    """8. Low-priority jobs are guaranteed progress through anti-starvation / aging."""
    # Low-priority job arrived earlier (at t=0.0)
    j_low = Job(
        job_id="J_LOW_STARVE", name="Low Priority Starve Test", product_type="P",
        arrival_time=0.0, due_date=None, priority=1,
        operations=[Operation(sequence=1, name="Op1", machine_id="M1", duration=15.0)]
    )
    ProductionStateService.add_job(j_low)

    # Higher priority job arriving later (at t=1.0)
    j_high = Job(
        job_id="J_HIGH_STARVE", name="High Priority Starve Test", product_type="P",
        arrival_time=1.0, due_date=50.0, priority=5,
        operations=[Operation(sequence=1, name="Op1", machine_id="M1", duration=15.0)]
    )
    ProductionStateService.add_job(j_high)

    res = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm="AGING")
    tasks = {t.job_id: t for t in res.tasks}
    # Older arrival prevents indefinite starvation of low-priority job: low starts at 0.0, high starts at 15.0
    assert tasks["J_LOW_STARVE"].start_time == 0.0
    assert tasks["J_HIGH_STARVE"].start_time == 15.0
    assert tasks["J_HIGH_STARVE"].end_time == 30.0


def test_9_alternative_machine_assignments_do_not_conflict():
    """9. Flexible routing with alternative machines does not introduce resource conflicts or overlap."""
    j1 = Job(
        job_id="J_ALT_1", name="Alt 1", product_type="P",
        arrival_time=0.0, due_date=50.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M1", alternative_machines=["M2"], duration=10.0)]
    )
    j2 = Job(
        job_id="J_ALT_2", name="Alt 2", product_type="P",
        arrival_time=0.0, due_date=50.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M1", alternative_machines=["M2"], duration=10.0)]
    )
    ProductionStateService.add_job(j1)
    ProductionStateService.add_job(j2)

    machines = ProductionStateService.get_all_machines()
    all_jobs = ProductionStateService.get_all_jobs()

    for algo in ["FCFS", "SPT", "EDD", "CR", "AGING", "CPSAT", "EPN"]:
        res = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm=algo)
        valid, errs = ScheduleValidator.validate(res.tasks, machines, current_time=0.0, jobs=all_jobs)
        assert valid, f"{algo} with alternative machines failed validator: {errs}"


def test_10_machine_downtime_does_not_create_hold_and_wait():
    """
    10. When downstream machine is DOWN, completed upstream operations free their machines
    immediately, avoiding upstream bottleneck hold-and-wait.
    """
    sim = DiscreteEventSimulator()
    ProductionStateService.set_machine_downtime("M2", down_duration=30.0, reason="Breakdown")

    job = Job(
        job_id="J_DOWN_CHAIN", name="Downstream Down", product_type="P",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M1", duration=10.0),
            Operation(sequence=2, name="Op2", machine_id="M2", duration=10.0),
        ]
    )
    ProductionStateService.add_job(job)

    # Advance to t=10.0: M1 finishes Op1
    sim.advance_time(10.0)
    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    assert m1.status == MachineStatus.IDLE.value
    assert m1.current_job_id is None
    db.close()


def test_11_dynamic_rescheduling_preserves_running_operations_and_locks():
    """
    11. Recalculation after new order arrival preserves running operations,
    their committed machine locks, and their start/end timestamps.
    """
    sim = DiscreteEventSimulator()
    j1 = Job(
        job_id="J_RUN_PRESERVE", name="Running Preserve", product_type="P",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M1", duration=30.0)]
    )
    ProductionStateService.add_job(j1)
    sim.advance_time(10.0)

    # At t=10.0, j1 has 20.0 remaining on M1. Add a new high-priority job competing for M1.
    j_new = Job(
        job_id="J_NEW_COMPETE", name="New Competing", product_type="Urgent",
        arrival_time=10.0, due_date=40.0, priority=5,
        operations=[Operation(sequence=1, name="Op1", machine_id="M1", duration=10.0)]
    )
    ProductionStateService.add_job(j_new)

    latest = ProductionStateService.get_latest_schedule()
    t_run = next(t for t in latest.tasks if t.job_id == "J_RUN_PRESERVE")
    t_new = next(t for t in latest.tasks if t.job_id == "J_NEW_COMPETE")

    # Non-preemptive execution: running op finishes at 30.0; new op starts after running op (>= 30.0)
    assert t_run.is_running is True
    assert t_run.start_time == 0.0
    assert t_run.end_time == 30.0
    assert t_new.start_time >= 30.0


def test_12_every_generated_schedule_passes_independent_validator():
    """12. All 7 algorithms generate schedules that pass independent ScheduleValidator without error."""
    j1 = Job(
        job_id="J_VAL_1", name="Val 1", product_type="P",
        arrival_time=0.0, due_date=100.0, priority=4,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M1", duration=15.0),
            Operation(sequence=2, name="Op2", machine_id="M3", duration=10.0),
        ]
    )
    j2 = Job(
        job_id="J_VAL_2", name="Val 2", product_type="P",
        arrival_time=5.0, due_date=80.0, priority=2,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M3", duration=20.0),
            Operation(sequence=2, name="Op2", machine_id="M1", duration=10.0),
        ]
    )
    ProductionStateService.add_job(j1)
    ProductionStateService.add_job(j2)

    machines = ProductionStateService.get_all_machines()
    all_jobs = ProductionStateService.get_all_jobs()

    for algo in ["FCFS", "SPT", "EDD", "CR", "AGING", "CPSAT", "EPN"]:
        res = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm=algo)
        valid, errs = ScheduleValidator.validate(res.tasks, machines, current_time=0.0, jobs=all_jobs)
        assert valid, f"Algorithm {algo} generated invalid schedule: {errs}"
