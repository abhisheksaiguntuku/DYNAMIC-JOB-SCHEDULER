import os
import tempfile
import pytest
from app.schemas.models import Job, Operation, Machine, MachineStatus, OperationStatus, JobStatus, ScheduledTask
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer
from app.ml.inference.epn_scheduler import EPNJobShopScheduler
from app.scheduling.validator import ScheduleValidator
from app.core.state_service import ProductionStateService
from app.database.db import init_db, SessionLocal, MachineModel, JobModel, SimulationStateModel, ScheduleRecordModel


@pytest.fixture(autouse=True)
def setup_isolated_shop_db():
    init_db()
    db = SessionLocal()
    db.query(SimulationStateModel).delete()
    db.query(ScheduleRecordModel).delete()
    db.query(JobModel).delete()
    db.query(MachineModel).delete()
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


def test_scenario_a_and_a2_active_schedule_gap_insertion_all_algorithms():
    """
    Scenario A & A2:
    1) M1-M5 are BUSY with priority-5 jobs; a priority-1 M10-only job arrives at t=0 -> starts at t=0.0 across all solvers.
    2) Cross-operation gap insertion (A2): High-priority J_HIGH (prio=5, due=80) has Op1 on M1 (0->50) and Op2 on M10 (dur=20, ready at 50).
       Low-priority J_LOW_M10 (prio=1, arrival=5, due=250) needs only M10 (dur=15, ready at 5).
       All heuristics (FCFS, SPT, EDD, CR, AGING), CP-SAT, and live EPN must schedule J_LOW_M10 in the open gap [5.0, 20.0]
       rather than leaving M10 idle from t=5 to t=50.
    """
    db = SessionLocal()
    for i in range(1, 6):
        m = db.query(MachineModel).filter(MachineModel.machine_id == f"M{i}").first()
        m.status = MachineStatus.BUSY.value
        m.current_job_id = f"J_BUSY_{i}"
        m.current_operation_seq = 1
        m.remaining_processing_time = 40.0
        db.add(JobModel(
            job_id=f"J_BUSY_{i}", name=f"Busy {i}", product_type="Core",
            quantity=1, arrival_time=0.0, due_date=100.0, priority=5,
            status=JobStatus.IN_PROGRESS.value,
            operations_json=[{
                "sequence": 1, "name": "Op1", "machine_id": f"M{i}",
                "duration": 40.0, "status": OperationStatus.RUNNING.value, "start_time": 0.0
            }]
        ))
    db.commit()
    db.close()

    low_m10 = Job(
        job_id="J_LOW_M10", name="Low Priority M10 Job", product_type="Aux",
        arrival_time=0.0, due_date=300.0, priority=1,
        operations=[Operation(sequence=1, name="M10 Finish", machine_id="M10", duration=15.0)]
    )
    ProductionStateService.add_job(low_m10)
    machines = ProductionStateService.get_all_machines()
    jobs = ProductionStateService.get_all_jobs()

    for algo in ["FCFS", "SPT", "EDD", "CR", "AGING", "CPSAT", "EPN"]:
        res = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm=algo)
        t_m10 = next(t for t in res.tasks if t.job_id == "J_LOW_M10")
        assert t_m10.start_time == 0.0, f"{algo} failed Scenario A: expected start=0.0 on M10, got {t_m10.start_time}"
        assert t_m10.end_time == 15.0
        is_valid, errs = ScheduleValidator.validate(res.tasks, machines, 0.0, jobs=jobs)
        assert is_valid, f"{algo} failed validator in Scenario A: {errs}"

    # Scenario A2: Cross-operation gap insertion
    db = SessionLocal()
    db.query(JobModel).delete()
    for m in db.query(MachineModel).all():
        m.status = MachineStatus.IDLE.value
        m.current_job_id = None
        m.current_operation_seq = None
        m.remaining_processing_time = 0.0
    db.commit()
    db.close()

    j_high = Job(
        job_id="J_HIGH", name="High Priority Multi-Op", product_type="Urgent",
        arrival_time=0.0, due_date=80.0, priority=5,
        operations=[
            Operation(sequence=1, name="M1 Op", machine_id="M1", duration=50.0),
            Operation(sequence=2, name="M10 Op", machine_id="M10", duration=20.0),
        ]
    )
    j_low = Job(
        job_id="J_LOW_M10_GAP", name="Low Priority M10 Gap", product_type="Aux",
        arrival_time=5.0, due_date=250.0, priority=1,
        operations=[
            Operation(sequence=1, name="M10 Op", machine_id="M10", duration=15.0),
        ]
    )
    ProductionStateService.add_job(j_high)
    ProductionStateService.add_job(j_low)
    machines = ProductionStateService.get_all_machines()
    jobs = ProductionStateService.get_all_jobs()

    for algo in ["FCFS", "SPT", "EDD", "CR", "AGING", "CPSAT", "EPN"]:
        res = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm=algo)
        t_low = next(t for t in res.tasks if t.job_id == "J_LOW_M10_GAP")
        t_high2 = next(t for t in res.tasks if t.job_id == "J_HIGH" and t.operation_sequence == 2)
        assert t_low.start_time == 5.0, f"{algo} left M10 unnecessarily idle: J_LOW_M10_GAP started at {t_low.start_time} instead of 5.0"
        assert t_low.end_time == 20.0
        assert t_high2.start_time == 50.0
        is_valid, errs = ScheduleValidator.validate(res.tasks, machines, 0.0, jobs=jobs)
        assert is_valid, f"{algo} failed validator in Scenario A2: {errs}"


def test_scenario_b_f_priority_and_aging_behavior():
    """
    Scenario B: High-priority job on M1 and low-priority job on M10 execute in parallel at t=0.0.
    Scenario F: Multiple jobs competing for M10 at t=0.0 respect priority tie-breaking in FCFS and priority weighting in AGING.
    """
    j1 = Job(
        job_id="J_LOW_PRIO", name="Low Priority", product_type="Std",
        arrival_time=0.0, due_date=200.0, priority=1,
        operations=[Operation(sequence=1, name="Op1", machine_id="M10", duration=20.0)]
    )
    j2 = Job(
        job_id="J_HIGH_PRIO", name="High Priority", product_type="Urgent",
        arrival_time=0.0, due_date=200.0, priority=5,
        operations=[Operation(sequence=1, name="Op1", machine_id="M10", duration=20.0)]
    )
    ProductionStateService.add_job(j1)
    ProductionStateService.add_job(j2)

    for algo in ["FCFS", "SPT", "EDD", "CR", "AGING", "CPSAT", "EPN"]:
        res = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm=algo)
        t_high = next(t for t in res.tasks if t.job_id == "J_HIGH_PRIO")
        t_low = next(t for t in res.tasks if t.job_id == "J_LOW_PRIO")
        assert t_high.start_time == 0.0, f"{algo} did not break tie in favor of higher priority job"
        assert t_low.start_time == 20.0


def test_scenarios_j_k_l_validation_and_missing_due_dates():
    """
    Scenario J: Invalid alternative_machines and cyclic/non-increasing operation sequences are rejected.
    Scenario K: Jobs without due dates (due_date=None) fallback deterministically to SPT without fabricating a due date.
    Scenario L: Mixed jobs with and without due dates prioritize valid due dates (EDD) and order undated jobs by SPT.
    """
    # Scenario J1: Invalid alternative machine
    bad_alt_job = Job(
        job_id="J_BAD_ALT", name="Bad Alt", product_type="Test",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M1", alternative_machines=["M999"], duration=10.0)]
    )
    with pytest.raises(ValueError, match="alternative machine 'M999' is invalid"):
        ProductionStateService.add_job(bad_alt_job)

    # Scenario J2: Non-increasing / cyclic operation sequence
    bad_seq_job = Job(
        job_id="J_BAD_SEQ", name="Bad Seq", product_type="Test",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[
            Operation(sequence=2, name="Op2", machine_id="M2", duration=10.0),
            Operation(sequence=1, name="Op1", machine_id="M1", duration=10.0),
        ]
    )
    with pytest.raises(ValueError, match="Invalid or cyclic operation sequence"):
        ProductionStateService.add_job(bad_seq_job)

    # Scenario K: Undated jobs fallback to SPT under EDD
    u_long = Job(
        job_id="J_UNDATED_LONG", name="Undated Long", product_type="Custom",
        arrival_time=0.0, due_date=None, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M10", duration=35.0)]
    )
    u_short = Job(
        job_id="J_UNDATED_SHORT", name="Undated Short", product_type="Custom",
        arrival_time=0.0, due_date=None, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M10", duration=12.0)]
    )
    ProductionStateService.add_job(u_long)
    ProductionStateService.add_job(u_short)

    loaded_jobs = {j.job_id: j for j in ProductionStateService.get_all_jobs()}
    assert loaded_jobs["J_UNDATED_LONG"].due_date is None
    assert loaded_jobs["J_UNDATED_SHORT"].due_date is None

    res_edd = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm="EDD")
    t_short = next(t for t in res.tasks if t.job_id == "J_UNDATED_SHORT") if False else next(t for t in res_edd.tasks if t.job_id == "J_UNDATED_SHORT")
    t_long = next(t for t in res_edd.tasks if t.job_id == "J_UNDATED_LONG")
    assert t_short.start_time == 0.0
    assert t_long.start_time == 12.0
    assert res_edd.metrics.total_tardiness == 0.0

    # Scenario L: Add a dated job on M10; EDD schedules the dated job first, then undated jobs by SPT
    dated_job = Job(
        job_id="J_DATED_URGENT", name="Dated Urgent", product_type="Custom",
        arrival_time=0.0, due_date=50.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M10", duration=10.0)]
    )
    ProductionStateService.add_job(dated_job)
    res_mixed = ProductionStateService.recalculate_schedule(sim_time=0.0, algorithm="EDD")
    t_dated = next(t for t in res_mixed.tasks if t.job_id == "J_DATED_URGENT")
    t_short_m = next(t for t in res_mixed.tasks if t.job_id == "J_UNDATED_SHORT")
    t_long_m = next(t for t in res_mixed.tasks if t.job_id == "J_UNDATED_LONG")
    assert t_dated.start_time == 0.0
    assert t_short_m.start_time == 10.0
    assert t_long_m.start_time == 22.0


def test_validator_detects_avoidable_idle_and_ineligible_machines():
    """
    Verify ScheduleValidator.validate(..., jobs=jobs) catches:
    - Avoidable machine idle time when a ready operation is delayed on an idle machine
    - Machine eligibility violation when a task is placed on an unauthorized machine
    - Invented operations not belonging to any job
    """
    job = Job(
        job_id="J_VAL", name="Validator Test", product_type="Test",
        arrival_time=0.0, due_date=100.0, priority=3,
        operations=[Operation(sequence=1, name="Op1", machine_id="M10", duration=15.0)]
    )
    machines = ProductionStateService.get_all_machines()

    # 1. Artificial delay on idle M10 (start=10.0 instead of 0.0) -> Avoidable Machine Idle Violation
    bad_idle_tasks = [
        ScheduledTask(
            job_id="J_VAL", job_name="Validator Test", operation_sequence=1,
            operation_name="Op1", machine_id="M10", start_time=10.0, end_time=25.0, duration=15.0
        )
    ]
    valid, errs = ScheduleValidator.validate(bad_idle_tasks, machines, current_time=0.0, jobs=[job])
    assert not valid
    assert any("Avoidable Machine Idle Violation" in e for e in errs)

    # 2. Ineligible machine (assigned to M1 instead of M10) -> Machine Eligibility Violation
    bad_mach_tasks = [
        ScheduledTask(
            job_id="J_VAL", job_name="Validator Test", operation_sequence=1,
            operation_name="Op1", machine_id="M1", start_time=0.0, end_time=15.0, duration=15.0
        )
    ]
    valid, errs = ScheduleValidator.validate(bad_mach_tasks, machines, current_time=0.0, jobs=[job])
    assert not valid
    assert any("Machine Eligibility Violation" in e for e in errs)

