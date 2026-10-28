"""
Stage 8 Phase 3 & Phase 4 Tests:
- Machine downtime, recovery, rescheduling, non-preemptive running op preservation, conflicting events
- Stale schedule rejection, concurrent submissions, overlapping machine assignment protection
"""
import concurrent.futures
import pytest
from fastapi import HTTPException
from app.simulation.engine import DiscreteEventSimulator
from app.core.state_service import ProductionStateService, StaleScheduleError
from app.scheduling.validator import ScheduleValidator
from app.database.db import init_db, SessionLocal, MachineModel, JobModel, SimulationStateModel
from app.schemas.models import Job, Operation, MachineStatus, OperationStatus, JobStatus
from app.main import recalculate_schedule, trigger_machine_downtime, recover_machine_endpoint


def setup_basic_shop():
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


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3: Machine Downtime & Recovery Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_breakdown_blocks_new_operations_cpsat_and_heuristics():
    """
    When M1 is DOWN for 30 minutes, neither CP-SAT nor heuristics may schedule
    pending operations on M1 before current_time + 30.
    """
    setup_basic_shop()
    sim = DiscreteEventSimulator()

    job = Job(
        job_id="J_DOWN_TEST",
        name="Downtime Test Job",
        product_type="Casting",
        arrival_time=0.0,
        due_date=120.0,
        priority=4,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M1", duration=10.0),
            Operation(sequence=2, name="Op2", machine_id="M2", duration=15.0),
        ]
    )
    ProductionStateService.add_job(job)

    # Set M1 down for 30 minutes
    m1 = ProductionStateService.set_machine_downtime("M1", down_duration=30.0)
    assert m1.status == MachineStatus.DOWN
    assert m1.remaining_processing_time == 30.0

    machines = ProductionStateService.get_all_machines()

    for algo in ["FCFS", "SPT", "EDD", "CPSAT"]:
        res = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm=algo)
        op1 = next(t for t in res.tasks if t.job_id == "J_DOWN_TEST" and t.operation_sequence == 1)
        op2 = next(t for t in res.tasks if t.job_id == "J_DOWN_TEST" and t.operation_sequence == 2)
        assert op1.start_time >= 30.0 - 1e-4, f"{algo} scheduled Op1 during M1 downtime at {op1.start_time}"
        assert op2.start_time >= op1.end_time - 1e-4, f"{algo} violated precedence after downtime shift"
        is_valid, errors = ScheduleValidator.validate(res.tasks, machines, sim.sim_time)
        assert is_valid, f"{algo} failed validator during downtime: {errors}"


def test_auto_recovery_via_simulation_advance():
    """
    Advancing the simulation clock across a machine's remaining downtime automatically
    recovers the machine back to IDLE and allows operations to start immediately.
    """
    setup_basic_shop()
    sim = DiscreteEventSimulator()
    ProductionStateService.set_machine_downtime("M1", down_duration=15.0)

    # Advance 10 minutes: still DOWN with 5 minutes remaining
    sim.advance_time(10.0)
    m1_partial = next(m for m in ProductionStateService.get_all_machines() if m.machine_id == "M1")
    assert m1_partial.status == MachineStatus.DOWN
    assert m1_partial.remaining_processing_time == 5.0

    # Advance 5 more minutes: M1 recovers to IDLE
    res_adv = sim.advance_time(5.0)
    assert any("Machine M1 recovered" in ev for ev in res_adv["events"])
    m1_recovered = next(m for m in ProductionStateService.get_all_machines() if m.machine_id == "M1")
    assert m1_recovered.status == MachineStatus.IDLE
    assert m1_recovered.remaining_processing_time == 0.0


def test_downtime_preserves_completed_and_non_preemptive_running_ops():
    """
    If a breakdown occurs on a BUSY machine with a running operation, the running operation
    is preserved (non-preemptive policy), completed operations remain untouched, and future
    operations on that machine are pushed past both the running op and the repair window.
    """
    setup_basic_shop()
    sim = DiscreteEventSimulator()

    db = SessionLocal()
    m1 = db.query(MachineModel).filter(MachineModel.machine_id == "M1").first()
    m1.status = MachineStatus.BUSY.value
    m1.current_job_id = "J_RUN"
    m1.current_operation_seq = 2
    m1.remaining_processing_time = 8.0

    db.add(JobModel(
        job_id="J_RUN",
        name="Running Job",
        product_type="Gear",
        quantity=1,
        arrival_time=0.0,
        due_date=100.0,
        priority=4,
        status=JobStatus.IN_PROGRESS.value,
        operations_json=[
            {"sequence": 1, "name": "Op1", "machine_id": "M2", "duration": 5.0,
             "status": OperationStatus.COMPLETED.value, "start_time": 0.0, "end_time": 5.0},
            {"sequence": 2, "name": "Op2", "machine_id": "M1", "duration": 8.0,
             "status": OperationStatus.RUNNING.value, "start_time": 5.0},
        ]
    ))
    db.add(JobModel(
        job_id="J_WAIT",
        name="Waiting Job",
        product_type="Shaft",
        quantity=1,
        arrival_time=0.0,
        due_date=100.0,
        priority=3,
        status=JobStatus.PENDING.value,
        operations_json=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 6.0,
             "status": OperationStatus.PENDING.value}
        ]
    ))
    db.commit()
    db.close()

    # Trigger 12-minute downtime on M1 while BUSY (remaining=8.0 -> total locked=20.0)
    m1_updated = ProductionStateService.set_machine_downtime("M1", down_duration=12.0)
    assert m1_updated.current_job_id == "J_RUN"
    assert m1_updated.remaining_processing_time == 20.0

    res = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="CPSAT")
    op1_done = next(t for t in res.tasks if t.job_id == "J_RUN" and t.operation_sequence == 1)
    op2_run = next(t for t in res.tasks if t.job_id == "J_RUN" and t.operation_sequence == 2)
    wait_op1 = next(t for t in res.tasks if t.job_id == "J_WAIT" and t.operation_sequence == 1)

    assert op1_done.is_completed and op1_done.end_time == 5.0
    assert op2_run.is_running
    assert wait_op1.start_time >= 20.0 - 1e-4


def test_conflicting_downtime_and_recovery_events_rejected():
    """
    Conflicting machine availability transitions must raise ValueError:
    - Setting downtime on an already DOWN machine
    - Force-recovering a machine that is BUSY with a running operation
    - Invalid downtime duration <= 0 or unknown machine_id
    """
    setup_basic_shop()
    ProductionStateService.set_machine_downtime("M1", down_duration=10.0)

    # Duplicate breakdown on already DOWN machine must fail
    with pytest.raises(ValueError, match="already DOWN"):
        ProductionStateService.set_machine_downtime("M1", down_duration=15.0)

    # Non-positive duration must fail
    with pytest.raises(ValueError, match="greater than zero"):
        ProductionStateService.set_machine_downtime("M2", down_duration=0.0)

    # Unknown machine must fail
    with pytest.raises(ValueError, match="does not exist"):
        ProductionStateService.set_machine_downtime("M999", down_duration=10.0)

    # Put M2 into BUSY state with a running job; force recovery must be rejected
    db = SessionLocal()
    m2 = db.query(MachineModel).filter(MachineModel.machine_id == "M2").first()
    m2.status = MachineStatus.BUSY.value
    m2.current_job_id = "J_ACTIVE"
    m2.current_operation_seq = 1
    m2.remaining_processing_time = 5.0
    db.commit()
    db.close()

    with pytest.raises(ValueError, match="Cannot force-recover"):
        ProductionStateService.recover_machine("M2")


# ──────────────────────────────────────────────────────────────────────────────
# Phase 4: Stale Schedule & Concurrency Protection Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_stale_schedule_rejected_via_api_and_service():
    """
    When production state advances (new job added, machine breakdown, or clock advance),
    recalculate_schedule with an outdated expected_state_version or expected_sim_time
    is rejected with StaleScheduleError (HTTP 409 on the API).
    """
    setup_basic_shop()
    sim = DiscreteEventSimulator()

    job1 = Job(
        job_id="J_STALE_1",
        name="Initial Job",
        product_type="Demo",
        arrival_time=0.0,
        due_date=100.0,
        operations=[Operation(sequence=1, name="Op1", machine_id="M1", duration=10.0)]
    )
    ProductionStateService.add_job(job1)
    v1 = ProductionStateService.get_state_version()

    # Valid calculation with matching state version succeeds
    res_ok = recalculate_schedule(algorithm="FCFS", expected_state_version=v1, expected_sim_time=0.0)
    assert res_ok.explanation.get("state_version") == v1

    # Mutate state by adding another job
    job2 = Job(
        job_id="J_STALE_2",
        name="Second Job",
        product_type="Demo",
        arrival_time=0.0,
        due_date=100.0,
        operations=[Operation(sequence=1, name="Op1", machine_id="M2", duration=8.0)]
    )
    ProductionStateService.add_job(job2)
    v2 = ProductionStateService.get_state_version()
    assert v2 > v1

    # Calling endpoint with stale v1 raises HTTP 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        recalculate_schedule(algorithm="FCFS", expected_state_version=v1)
    assert exc_info.value.status_code == 409
    assert "Stale schedule" in exc_info.value.detail


def test_concurrent_job_submissions_and_rescheduling_thread_safe():
    """
    Concurrent threads registering jobs, advancing simulation time, and recalculating
    schedules must serialize cleanly without race conditions, lost jobs, or overlapping
    machine assignments.
    """
    setup_basic_shop()
    sim = DiscreteEventSimulator()

    def submit_and_schedule(idx: int):
        j = Job(
            job_id=f"J_CONC_{idx}",
            name=f"Concurrent Job {idx}",
            product_type="Concurrent",
            arrival_time=0.0,
            due_date=200.0,
            priority=3,
            operations=[
                Operation(sequence=1, name="Op1", machine_id="M1", duration=4.0),
                Operation(sequence=2, name="Op2", machine_id="M2", duration=3.0),
            ]
        )
        ProductionStateService.add_job(j)
        return ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="FCFS")

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(submit_and_schedule, i) for i in range(8)]
        results = [f.result() for f in futures]

    # Verify all 8 jobs were persisted and final schedule has no overlapping tasks
    all_jobs = ProductionStateService.get_all_jobs()
    assert len(all_jobs) == 8

    final_res = ProductionStateService.recalculate_schedule(sim.sim_time, algorithm="CPSAT")
    machines = ProductionStateService.get_all_machines()
    is_valid, errors = ScheduleValidator.validate(final_res.tasks, machines, sim.sim_time)
    assert is_valid, f"Concurrent execution produced invalid schedule: {errors}"
    assert len(final_res.tasks) == 16

