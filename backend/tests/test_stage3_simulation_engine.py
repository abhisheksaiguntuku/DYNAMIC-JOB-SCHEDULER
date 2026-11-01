import pytest
from app.simulation.engine import DiscreteEventSimulator
from app.database.db import init_db, SessionLocal, MachineModel, JobModel, SimulationStateModel
from app.schemas.models import Job, Operation, MachineStatus, OperationStatus, JobStatus
from app.core.state_service import ProductionStateService
from app.scheduling.validator import ScheduleValidator


@pytest.fixture(scope="function", autouse=True)
def setup_isolated_test_db():
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


def test_idle_machine_automatically_starts_eligible_pending_op():
    """1. An idle machine automatically starts an eligible pending operation during advance_time."""
    sim = DiscreteEventSimulator()
    job = Job(
        job_id="J_AUTO_1", name="Auto Job", product_type="Widget",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M1", duration=10.0)]
    )
    ProductionStateService.add_job(job)

    # Advance simulation by 1.0 minute
    res = sim.advance_time(1.0)
    assert any("Dispatched J_AUTO_1 Op 1" in ev for ev in res["events"])

    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    assert m1.status == MachineStatus.BUSY.value
    assert m1.current_job_id == "J_AUTO_1"
    assert m1.current_operation_seq == 1
    assert m1.remaining_processing_time == 9.0  # 10.0 - 1.0

    j1 = db.query(JobModel).filter(JobModel.job_id == "J_AUTO_1").first()
    assert j1.status == JobStatus.IN_PROGRESS.value
    op1 = j1.operations_json[0]
    assert op1["status"] == OperationStatus.RUNNING.value
    assert op1["start_time"] == 0.0
    db.close()


def test_multiple_machines_process_different_jobs_simultaneously():
    """2. Multiple machines process different jobs simultaneously without hold-and-wait or blocking."""
    sim = DiscreteEventSimulator()
    job1 = Job(
        job_id="J_PAR_1", name="Parallel Job 1", product_type="P1",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M1", duration=20.0)]
    )
    job2 = Job(
        job_id="J_PAR_2", name="Parallel Job 2", product_type="P2",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M2", duration=20.0)]
    )
    job10 = Job(
        job_id="J_PAR_10", name="Parallel Job 10", product_type="P10",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M10", duration=20.0)]
    )
    ProductionStateService.add_job(job1)
    ProductionStateService.add_job(job2)
    ProductionStateService.add_job(job10)

    sim.advance_time(5.0)

    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    m2 = db.query(MachineModel).filter(MachineModel.machine_id == "M2").first()
    m10 = db.query(MachineModel).filter(MachineModel.machine_id == "M10").first()

    assert m1.status == MachineStatus.BUSY.value and m1.current_job_id == "J_PAR_1"
    assert m2.status == MachineStatus.BUSY.value and m2.current_job_id == "J_PAR_2"
    assert m10.status == MachineStatus.BUSY.value and m10.current_job_id == "J_PAR_10"
    db.close()


def test_successor_starts_immediately_when_predecessor_completes():
    """3. Successor starts immediately when its predecessor completes and required machine is available."""
    sim = DiscreteEventSimulator()
    job = Job(
        job_id="J_CHAIN", name="Chained Job", product_type="Chain",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M1", duration=10.0),
            Operation(sequence=2, name="Op2", machine_id="M2", duration=15.0),
        ]
    )
    ProductionStateService.add_job(job)

    # Step 1: Advance by 5 min -> Op1 is still running on M1, Op2 is PENDING
    sim.advance_time(5.0)
    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    m2 = db.query(MachineModel).filter(MachineModel.machine_id == "M2").first()
    assert m1.status == MachineStatus.BUSY.value
    assert m2.status == MachineStatus.IDLE.value
    db.close()

    # Step 2: Advance by 5 min -> Op1 completes at t=10.0, Op2 dispatched immediately to M2 at t=10.0
    res = sim.advance_time(5.0)
    assert any("Operation finished on M1: Job J_CHAIN Op 1" in ev for ev in res["events"])
    assert any("Dispatched J_CHAIN Op 2 (Op2) to M2 at t=10.0" in ev for ev in res["events"])

    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    m2 = db.query(MachineModel).filter(MachineModel.machine_id == "M2").first()
    assert m1.status == MachineStatus.IDLE.value
    assert m2.status == MachineStatus.BUSY.value and m2.current_job_id == "J_CHAIN"
    db.close()


def test_machine_released_immediately_after_operation_completion():
    """4. Machine is released immediately to IDLE when operation completes."""
    sim = DiscreteEventSimulator()
    job = Job(
        job_id="J_SINGLE", name="Single Op", product_type="Simple",
        arrival_time=0.0, due_date=50.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M3", duration=8.0)]
    )
    ProductionStateService.add_job(job)
    sim.advance_time(8.0)

    db = SessionLocal()
    m3 = db.query(MachineModel).filter(MachineModel.machine_id == "M3").first()
    assert m3.status == MachineStatus.IDLE.value
    assert m3.current_job_id is None
    assert m3.remaining_processing_time == 0.0

    j = db.query(JobModel).filter(JobModel.job_id == "J_SINGLE").first()
    assert j.status == JobStatus.COMPLETED.value
    assert j.operations_json[0]["status"] == OperationStatus.COMPLETED.value
    assert j.operations_json[0]["end_time"] == 8.0
    db.close()


def test_machine_recovering_from_downtime_automatically_receives_work():
    """5. Machine recovering from downtime automatically receives eligible work upon recovery."""
    sim = DiscreteEventSimulator()
    # Put M4 into downtime for 15.0 minutes
    ProductionStateService.set_machine_downtime("M4", down_duration=15.0, reason="Preventive Maintenance")

    job = Job(
        job_id="J_DOWN_WAIT", name="Waiting for M4", product_type="P",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M4", duration=10.0)]
    )
    ProductionStateService.add_job(job)

    # Advance 10 minutes -> M4 still DOWN (5 min remaining), job still PENDING
    sim.advance_time(10.0)
    db = SessionLocal()
    m4 = db.query(MachineModel).filter(MachineModel.machine_id == "M4").first()
    assert m4.status == MachineStatus.DOWN.value
    assert m4.remaining_processing_time == 5.0
    db.close()

    # Advance 10 minutes -> M4 recovers at t=15.0 and immediately receives J_DOWN_WAIT Op1
    res = sim.advance_time(10.0)
    assert any("Machine M4 recovered" in ev for ev in res["events"])
    assert any("Dispatched J_DOWN_WAIT Op 1 (Op1) to M4 at t=15.0" in ev for ev in res["events"])

    db = SessionLocal()
    m4 = db.query(MachineModel).filter(MachineModel.machine_id == "M4").first()
    assert m4.status == MachineStatus.BUSY.value
    assert m4.current_job_id == "J_DOWN_WAIT"
    assert m4.remaining_processing_time == 5.0  # 10.0 dur started at t=15, sim_time now 20 (20 - 15 = 5 processed)
    db.close()


def test_new_job_arriving_while_another_runs_reschedules_future_and_preserves_running():
    """
    6 & 7. A new job arriving during execution triggers future recalculation.
    Running operations remain unchanged with original start/completion commitments.
    The new job uses a different available machine (M10).
    """
    sim = DiscreteEventSimulator()
    j1 = Job(
        job_id="J_EXISTING", name="Existing Long Job", product_type="Core",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M1", duration=40.0),
            Operation(sequence=2, name="Op2", machine_id="M2", duration=20.0),
        ]
    )
    ProductionStateService.add_job(j1)
    # Start execution of J_EXISTING Op1 on M1
    sim.advance_time(10.0)

    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    assert m1.status == MachineStatus.BUSY.value
    assert m1.current_job_id == "J_EXISTING"
    assert m1.remaining_processing_time == 30.0
    db.close()

    # Now at t=10.0, a new urgent job arrives requiring M10
    j2 = Job(
        job_id="J_NEW_ARRIVING", name="New Arrival", product_type="Urgent",
        arrival_time=10.0, due_date=50.0, priority=5,
        operations=[Operation(sequence=1, name="Op1", machine_id="M10", duration=15.0)]
    )
    # Adding the job automatically triggers future schedule recalculation
    ProductionStateService.add_job(j2)

    # Check latest schedule record
    latest = ProductionStateService.get_latest_schedule()
    assert latest is not None

    # Verify running operation on M1 is preserved exactly
    t_running = next(t for t in latest.tasks if t.job_id == "J_EXISTING" and t.operation_sequence == 1)
    assert t_running.is_running is True
    assert t_running.start_time == 0.0
    assert t_running.end_time == 40.0

    # Advance time: new job starts immediately on IDLE M10
    sim.advance_time(5.0)
    db = SessionLocal()
    m10 = db.query(MachineModel).filter(MachineModel.machine_id == "M10").first()
    assert m10.status == MachineStatus.BUSY.value
    assert m10.current_job_id == "J_NEW_ARRIVING"
    db.close()


def test_large_time_advance_across_multiple_completion_events():
    """8 & 9. Large time advance crossing multiple operations finishes all sequentially without duplicate events."""
    sim = DiscreteEventSimulator()
    j1 = Job(
        job_id="J_MULTI_1", name="Multi 1", product_type="A",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M1", duration=5.0),
            Operation(sequence=2, name="Op2", machine_id="M2", duration=5.0),
            Operation(sequence=3, name="Op3", machine_id="M3", duration=5.0),
        ]
    )
    ProductionStateService.add_job(j1)

    # Advance by 50.0 minutes in a single advance_time call
    res = sim.advance_time(50.0)
    assert res["current_sim_time"] == 50.0
    assert any("Job completed: J_MULTI_1" in ev for ev in res["events"])

    db = SessionLocal()
    j = db.query(JobModel).filter(JobModel.job_id == "J_MULTI_1").first()
    assert j.status == JobStatus.COMPLETED.value
    assert all(op["status"] == OperationStatus.COMPLETED.value for op in j.operations_json)
    assert j.operations_json[0]["end_time"] == 5.0
    assert j.operations_json[1]["end_time"] == 10.0
    assert j.operations_json[2]["end_time"] == 15.0

    # All machines returned to IDLE
    for mid in ["M1", "M2", "M3"]:
        m = db.query(MachineModel).filter(MachineModel.machine_id == mid).first()
        assert m.status == MachineStatus.IDLE.value
        assert m.current_job_id is None
    db.close()


def test_no_eligible_work_leaves_machines_legitimately_idle():
    """10. Machines remain legitimately idle when there is no eligible work; no operations invented."""
    sim = DiscreteEventSimulator()
    res = sim.advance_time(20.0)
    assert res["current_sim_time"] == 20.0
    assert len(res["events"]) == 0

    db = SessionLocal()
    machines = db.query(MachineModel).all()
    for m in machines:
        assert m.status == MachineStatus.IDLE.value
        assert m.current_job_id is None
        assert m.remaining_processing_time == 0.0
    db.close()

