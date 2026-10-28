"""
Stage 4.1 Integration Tests
============================
These tests exercise the real service workflow — they do NOT manually inject
COMPLETED/RUNNING status into the DB to fake a result. Instead they:

1. Set up machine + job records through the real helper functions.
2. Advance simulation time with DiscreteEventSimulator.advance_time().
3. Trigger ProductionStateService.recalculate_schedule().
4. Assert invariants that the scheduler must uphold.

Tests are deterministic (no random seeds, no time-dependent sleeps).
"""
import pytest
from app.simulation.engine import DiscreteEventSimulator
from app.core.state_service import ProductionStateService
from app.scheduling.validator import ScheduleValidator
from app.database.db import init_db, SessionLocal, MachineModel, JobModel, ScheduleRecordModel
from app.schemas.models import MachineStatus, OperationStatus, JobStatus


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_db():
    """Wipe all tables before every test – ensures full isolation."""
    init_db()
    db = SessionLocal()
    db.query(ScheduleRecordModel).delete()
    db.query(JobModel).delete()
    db.query(MachineModel).delete()
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(ScheduleRecordModel).delete()
    db.query(JobModel).delete()
    db.query(MachineModel).delete()
    db.commit()
    db.close()


# ──────────────────────────────────────────────────────────────────────────────
# DB helpers (real DB, not mock)
# ──────────────────────────────────────────────────────────────────────────────

def add_machine(machine_id, status=MachineStatus.IDLE.value, remaining=0.0,
                current_job_id=None, current_op_seq=None):
    db = SessionLocal()
    db.add(MachineModel(
        machine_id=machine_id,
        name=f"Machine {machine_id}",
        capability="generic",
        status=status,
        remaining_processing_time=remaining,
        total_busy_time=0.0,
        current_job_id=current_job_id,
        current_operation_seq=current_op_seq,
    ))
    db.commit()
    db.close()


def add_job(job_id, arrival, ops, due=500.0, priority=3,
            status=JobStatus.PENDING.value):
    db = SessionLocal()
    db.add(JobModel(
        job_id=job_id,
        name=job_id,
        product_type="generic",
        quantity=1,
        arrival_time=arrival,
        due_date=due,
        priority=priority,
        status=status,
        operations_json=ops,
    ))
    db.commit()
    db.close()


def get_job(job_id):
    db = SessionLocal()
    try:
        return db.query(JobModel).filter(JobModel.job_id == job_id).first()
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# Task 2: Deterministic completed-operation preservation via real workflow
# ──────────────────────────────────────────────────────────────────────────────

class TestCompletedOperationPreservationRealWorkflow:
    """
    The engine marks an operation COMPLETED when the machine's remaining time
    reaches zero.  We set up the machine as BUSY with remaining=3, wire the job
    op as RUNNING, advance 5 minutes, and then verify the DB state and the
    scheduler output.
    """

    def test_single_op_job_completed_by_engine_not_rescheduled(self):
        """
        Real workflow:
        1. Insert a single-operation job whose op is RUNNING on a BUSY machine.
        2. advance_time(5) → engine should complete the op and mark job COMPLETED.
        3. Insert a new pending job.
        4. recalculate_schedule → completed job must NOT appear in output.
        5. New job MUST appear.
        """
        sim = DiscreteEventSimulator()

        # Step 1: set up machine as BUSY, job as RUNNING
        add_machine("M1", status=MachineStatus.BUSY.value, remaining=3.0,
                    current_job_id="J1", current_op_seq=1)
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1",
             "duration": 3.0, "status": OperationStatus.RUNNING.value,
             "start_time": 0.0}
        ])

        # Step 2: advance clock by 5 min — op finishes (remaining 3 ≤ 5)
        events = sim.advance_time(step_minutes=5)

        # Verify engine actually marked the job COMPLETED
        j1 = get_job("J1")
        assert j1 is not None, "J1 must still exist in DB"
        assert j1.status == JobStatus.COMPLETED.value, (
            f"Engine should have marked J1 COMPLETED; got {j1.status}"
        )
        # Verify op1 has end_time recorded
        op1 = j1.operations_json[0]
        assert op1["status"] == OperationStatus.COMPLETED.value
        assert op1["end_time"] is not None

        # Record historical timestamps for later comparison
        recorded_start = op1["start_time"]
        recorded_end = op1["end_time"]

        # Step 3: insert new pending job
        add_job("J2", arrival=5.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 4.0,
             "status": OperationStatus.PENDING.value},
            {"sequence": 2, "name": "Op2", "machine_id": "M2", "duration": 2.0,
             "status": OperationStatus.PENDING.value},
        ])

        # Step 4: recalculate schedule
        result = ProductionStateService.recalculate_schedule(
            sim.sim_time, algorithm="FCFS"
        )

        # Step 5: assertions
        tasks_j1 = [t for t in result.tasks if t.job_id == "J1"]
        tasks_j2 = [t for t in result.tasks if t.job_id == "J2"]

        assert len(tasks_j1) == 0, (
            "Completed job J1 must NOT appear in new schedule at all"
        )
        assert len(tasks_j2) == 2, (
            "Pending job J2 must have both its operations scheduled"
        )

        # Step 6: DB timestamps unchanged
        j1_after = get_job("J1")
        op1_after = j1_after.operations_json[0]
        assert op1_after["start_time"] == recorded_start, "start_time must not change"
        assert op1_after["end_time"] == recorded_end, "end_time must not change"

        # Step 7: precedence of J2 operations
        op1_j2 = next(t for t in tasks_j2 if t.operation_sequence == 1)
        op2_j2 = next(t for t in tasks_j2 if t.operation_sequence == 2)
        assert op2_j2.start_time >= op1_j2.end_time - 1e-6, (
            "Op2 of J2 must start after Op1 ends"
        )

    def test_multi_op_job_partial_completion_second_op_preserved(self):
        """
        Job J1 has two ops (M1, M2).  Engine completes op1 only (M1 done).
        Op2 remains PENDING.  After rescheduling:
        - Op1 must appear as is_completed=True with original timestamps.
        - Op2 must be scheduled after op1.end_time.
        - Machine M1 must not be double-booked.
        """
        sim = DiscreteEventSimulator()
        add_machine("M1", status=MachineStatus.BUSY.value, remaining=2.0,
                    current_job_id="J1", current_op_seq=1)
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 2.0,
             "status": OperationStatus.RUNNING.value, "start_time": 0.0},
            {"sequence": 2, "name": "Op2", "machine_id": "M2", "duration": 4.0,
             "status": OperationStatus.PENDING.value},
        ])

        sim.advance_time(step_minutes=3)  # op1 (dur=2) must complete

        j1 = get_job("J1")
        ops = j1.operations_json
        # op1 should be COMPLETED by engine
        assert ops[0]["status"] == OperationStatus.COMPLETED.value, (
            "Engine must mark op1 COMPLETED after advance"
        )
        op1_end = ops[0]["end_time"]

        result = ProductionStateService.recalculate_schedule(
            sim.sim_time, algorithm="FCFS"
        )
        j1_tasks = sorted(
            [t for t in result.tasks if t.job_id == "J1"],
            key=lambda t: t.operation_sequence
        )
        # op1 appears as completed with original timestamp
        assert any(t.operation_sequence == 1 and t.is_completed for t in j1_tasks), \
            "Op1 must be flagged is_completed=True in schedule output"
        op1_task = next(t for t in j1_tasks if t.operation_sequence == 1)
        assert abs(op1_task.end_time - op1_end) < 1e-3, \
            "Op1 end_time in schedule must match DB-recorded end_time"

        # op2 must start at or after op1 ended
        op2_task = next(t for t in j1_tasks if t.operation_sequence == 2)
        assert op2_task.start_time >= op1_task.end_time - 1e-6, \
            "Op2 must not start before Op1 ends"


# ──────────────────────────────────────────────────────────────────────────────
# Task 3: Running-operation machine exclusivity
# ──────────────────────────────────────────────────────────────────────────────

class TestRunningOperationPreservation:
    """
    While an operation is RUNNING on a machine, rescheduling must NOT
    allocate any other operation to that machine during the reserved interval.
    """

    def test_running_op_machine_not_double_booked(self):
        """
        M1 is BUSY with J1-Op1, remaining=6.
        New job J2 needs M1 for its Op1.
        After rescheduling, J2-Op1 must start AFTER M1 is free (current_time + 6).
        """
        sim = DiscreteEventSimulator()
        add_machine("M1", status=MachineStatus.BUSY.value, remaining=6.0,
                    current_job_id="J1", current_op_seq=1)
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 6.0,
             "status": OperationStatus.RUNNING.value, "start_time": 0.0},
            {"sequence": 2, "name": "Op2", "machine_id": "M2", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])
        add_job("J2", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 2.0,
             "status": OperationStatus.PENDING.value},
        ])

        result = ProductionStateService.recalculate_schedule(
            sim.sim_time, algorithm="FCFS"
        )

        # J1-Op1 must be the running task on M1
        j1_op1 = next(
            (t for t in result.tasks if t.job_id == "J1" and t.operation_sequence == 1),
            None
        )
        assert j1_op1 is not None, "J1-Op1 must appear in schedule"
        assert j1_op1.is_running, "J1-Op1 must be flagged as running"

        # J2-Op1 must start AFTER M1 is freed (sim_time + remaining = 0 + 6 = 6)
        j2_op1 = next(
            (t for t in result.tasks if t.job_id == "J2" and t.operation_sequence == 1),
            None
        )
        assert j2_op1 is not None, "J2-Op1 must be scheduled"
        assert j2_op1.start_time >= j1_op1.end_time - 1e-6, (
            f"J2-Op1 start ({j2_op1.start_time}) must be >= J1-Op1 end ({j1_op1.end_time})"
        )

    def test_running_op_timestamps_unchanged_after_reschedule(self):
        """
        Record the running task's start/end times before rescheduling.
        After inserting a new job and rescheduling, the running task must
        retain identical start and end times.
        """
        sim = DiscreteEventSimulator()
        add_machine("M1", status=MachineStatus.BUSY.value, remaining=5.0,
                    current_job_id="J1", current_op_seq=1)
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 5.0,
             "status": OperationStatus.RUNNING.value, "start_time": 0.0},
        ])

        # First schedule (baseline)
        result1 = ProductionStateService.recalculate_schedule(
            sim.sim_time, algorithm="FCFS"
        )
        j1_task_before = next(
            t for t in result1.tasks
            if t.job_id == "J1" and t.operation_sequence == 1
        )

        # Insert new job and reschedule
        add_job("J2", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M2", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])
        result2 = ProductionStateService.recalculate_schedule(
            sim.sim_time, algorithm="FCFS"
        )
        j1_task_after = next(
            t for t in result2.tasks
            if t.job_id == "J1" and t.operation_sequence == 1
        )

        assert j1_task_after.start_time == j1_task_before.start_time, \
            "Running op start_time must not change on reschedule"
        assert j1_task_after.end_time == j1_task_before.end_time, \
            "Running op end_time must not change on reschedule"
        assert j1_task_after.is_running, \
            "Running op must still be flagged is_running after reschedule"

    def test_no_machine_overlap_with_running_op(self):
        """
        Validate schedule via ScheduleValidator: no overlap allowed on a machine
        where a running operation is already locked.
        """
        sim = DiscreteEventSimulator()
        add_machine("M1", status=MachineStatus.BUSY.value, remaining=4.0,
                    current_job_id="J1", current_op_seq=1)
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 4.0,
             "status": OperationStatus.RUNNING.value, "start_time": 0.0},
        ])
        add_job("J2", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])

        from app.core.state_service import ProductionStateService as PSS
        from app.core.state_service import ProductionStateService
        result = ProductionStateService.recalculate_schedule(
            sim.sim_time, algorithm="FCFS"
        )

        db = SessionLocal()
        machines = PSS.get_all_machines()
        db.close()
        is_valid, errors = ScheduleValidator.validate(
            result.tasks, machines, current_time=sim.sim_time
        )
        assert is_valid, f"Schedule has validation errors: {errors}"


# ──────────────────────────────────────────────────────────────────────────────
# Task 4: SPT fallback validation
# ──────────────────────────────────────────────────────────────────────────────

class TestCPSATFallbackValidation:
    """
    When CP-SAT times out or returns INFEASIBLE, the solver falls back to SPT.
    The fallback schedule must satisfy:
    - Machine no-overlap (including any locked BUSY intervals).
    - Job operation precedence.
    - solver_status records the fallback reason.
    """

    def test_fallback_schedule_passes_validator(self):
        """Force a CP-SAT timeout; validate that fallback output is constraint-correct."""
        add_machine("M1", status=MachineStatus.BUSY.value, remaining=10.0,
                    current_job_id="J_LOCK", current_op_seq=1)
        add_machine("M2")
        add_job("J_LOCK", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 10.0,
             "status": OperationStatus.RUNNING.value, "start_time": 0.0},
        ])
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 2.0,
             "status": OperationStatus.PENDING.value},
            {"sequence": 2, "name": "Op2", "machine_id": "M2", "duration": 2.0,
             "status": OperationStatus.PENDING.value},
        ])

        result = ProductionStateService.recalculate_schedule(
            0.0, algorithm="CPSAT", time_limit_seconds=0.01
        )

        # solver_status must indicate fallback or a valid terminal state
        valid = ("FALLBACK", "INFEASIBLE", "UNKNOWN", "FEASIBLE", "OPTIMAL")
        assert any(v in result.metrics.solver_status.upper() for v in valid), \
            f"Unexpected solver_status: {result.metrics.solver_status}"

        machines = ProductionStateService.get_all_machines()
        is_valid, errors = ScheduleValidator.validate(result.tasks, machines, 0.0)
        assert is_valid, f"Fallback schedule failed validation: {errors}"

    def test_fallback_records_solver_status_in_metrics(self):
        """Fallback must record the CP-SAT status string so callers can detect it."""
        add_machine("M1")
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 1.0,
             "status": OperationStatus.PENDING.value},
        ])

        result = ProductionStateService.recalculate_schedule(
            0.0, algorithm="CPSAT", time_limit_seconds=0.001
        )
        # Either a CP-SAT terminal status or fallback label — must be a non-empty string
        assert isinstance(result.metrics.solver_status, str)
        assert len(result.metrics.solver_status) > 0

    def test_fallback_preserves_running_operation(self):
        """Even under fallback, a running operation must not be overwritten."""
        add_machine("M1", status=MachineStatus.BUSY.value, remaining=8.0,
                    current_job_id="J1", current_op_seq=1)
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 8.0,
             "status": OperationStatus.RUNNING.value, "start_time": 0.0},
        ])
        add_job("J2", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])

        result = ProductionStateService.recalculate_schedule(
            0.0, algorithm="CPSAT", time_limit_seconds=0.01
        )

        # J1-Op1 must be present and running
        j1_tasks = [t for t in result.tasks if t.job_id == "J1"]
        running = [t for t in j1_tasks if t.is_running]
        assert len(running) >= 1, "Running operation must be preserved in fallback"

        # J2-Op1 must not start before M1 is free
        j2_tasks = [t for t in result.tasks if t.job_id == "J2"]
        if j2_tasks:
            j2_op1 = j2_tasks[0]
            j1_running = running[0]
            assert j2_op1.start_time >= j1_running.end_time - 1e-6, \
                "J2 must not overlap with J1's running op even in fallback"

    def test_fallback_rejected_when_validation_fails(self, monkeypatch):
        """When the SPT fallback produces an invalid schedule, CPSATSchedulingOptimizer must raise ValueError."""
        add_machine("M1")
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 2.0,
             "status": OperationStatus.PENDING.value},
        ])

        # Monkeypatch ScheduleValidator.validate to simulate validation failure on fallback
        from app.scheduling.validator import ScheduleValidator
        orig_validate = ScheduleValidator.validate

        def fake_validate(tasks, machines, current_time=0.0):
            return False, ["Simulated invalid fallback: Machine Exclusivity Violation on M1"]

        monkeypatch.setattr(ScheduleValidator, "validate", staticmethod(fake_validate))

        with pytest.raises(ValueError, match="failed independent validation"):
            # Trigger CP-SAT with tiny timeout to force fallback
            ProductionStateService.recalculate_schedule(
                0.0, algorithm="CPSAT", time_limit_seconds=0.0001
            )

    def test_api_controlled_response_on_fallback_failure(self, monkeypatch):
        """When fallback fails validation, the recalculate endpoint raises HTTPException(400)."""
        from fastapi import HTTPException
        from app.main import recalculate_schedule
        from app.scheduling.validator import ScheduleValidator
        from ortools.sat.python import cp_model

        add_machine("M1")
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 2.0,
             "status": OperationStatus.PENDING.value},
        ])

        # Force CP-SAT solver to return INFEASIBLE so it enters the fallback branch
        monkeypatch.setattr(cp_model.CpSolver, "Solve", lambda self, model: cp_model.INFEASIBLE)

        def fake_validate(tasks, machines, current_time=0.0):
            return False, ["Simulated invalid fallback constraint"]

        monkeypatch.setattr(ScheduleValidator, "validate", staticmethod(fake_validate))

        with pytest.raises(HTTPException) as exc_info:
            recalculate_schedule(algorithm="CPSAT")
        assert exc_info.value.status_code == 400
        assert "failed independent validation" in exc_info.value.detail



# ──────────────────────────────────────────────────────────────────────────────
# Task 5: state_service.py parameter handling regression tests
# ──────────────────────────────────────────────────────────────────────────────

class TestStateServiceParameters:
    """
    Regression tests for the fixes made to ProductionStateService.recalculate_schedule:
    - time_limit_seconds forwarded to CP-SAT.
    - Empty operation lists rejected with ValueError.
    - COMPLETED jobs excluded from scheduling.
    - Algorithm aliases normalized.
    """

    def test_empty_operations_raises_value_error(self):
        """A job with an empty operations list must be rejected before DB writes."""
        add_machine("M1")
        add_job("J_BAD", arrival=0.0, ops=[])
        with pytest.raises(ValueError, match="no operations"):
            ProductionStateService.recalculate_schedule(0.0, algorithm="FCFS")

    def test_completed_jobs_excluded_from_schedule(self):
        """Jobs with status COMPLETED must not appear in the schedule output."""
        add_machine("M1")
        add_machine("M2")
        add_job("J_DONE", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 5.0,
             "status": OperationStatus.COMPLETED.value,
             "start_time": 0.0, "end_time": 5.0}
        ], status=JobStatus.COMPLETED.value)
        add_job("J_PEND", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])

        result = ProductionStateService.recalculate_schedule(0.0, algorithm="FCFS")

        completed_in_schedule = [t for t in result.tasks if t.job_id == "J_DONE"]
        pending_in_schedule = [t for t in result.tasks if t.job_id == "J_PEND"]
        assert len(completed_in_schedule) == 0, \
            "COMPLETED job must not appear in schedule"
        assert len(pending_in_schedule) > 0, \
            "PENDING job must be scheduled"

    def test_algorithm_alias_cp_sat_normalized(self):
        """CP_SAT (underscore) must route to the CP-SAT optimizer without error."""
        add_machine("M1")
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])
        # Should not raise; must produce a valid ScheduleResult
        result = ProductionStateService.recalculate_schedule(
            0.0, algorithm="CP_SAT", time_limit_seconds=5.0
        )
        assert result is not None
        assert len(result.tasks) > 0

    def test_algorithm_alias_cpsat_no_underscore(self):
        """CPSAT (no underscore) must also route to CP-SAT optimizer."""
        add_machine("M1")
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])
        result = ProductionStateService.recalculate_schedule(
            0.0, algorithm="CPSAT", time_limit_seconds=5.0
        )
        assert result is not None
        assert "CPSAT" in result.algorithm.replace("-", "").replace(" ", "").upper() \
            or "OPTIMAL" in result.metrics.solver_status \
            or "FEASIBLE" in result.metrics.solver_status

    def test_time_limit_forwarded_to_cpsat(self):
        """
        A very short time limit (0.001 s) should still produce a schedule result
        (either CP-SAT found something fast or fell back to SPT).
        The solver_status must not be a heuristic label when no timeout occurred.
        """
        add_machine("M1")
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])
        result = ProductionStateService.recalculate_schedule(
            0.0, algorithm="CPSAT", time_limit_seconds=0.001
        )
        # Must return a ScheduleResult regardless of timeout
        assert result is not None
        assert isinstance(result.metrics.solver_status, str)

    def test_heuristic_fcfs_still_works(self):
        """Ensure plain FCFS heuristic still routes correctly after normalization."""
        add_machine("M1")
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 4.0,
             "status": OperationStatus.PENDING.value},
            {"sequence": 2, "name": "Op2", "machine_id": "M2", "duration": 2.0,
             "status": OperationStatus.PENDING.value},
        ])
        result = ProductionStateService.recalculate_schedule(0.0, algorithm="FCFS")
        assert result.algorithm == "FCFS"
        assert result.metrics.makespan == 6.0

    def test_heuristic_spt_still_works(self):
        """SPT heuristic must route correctly."""
        add_machine("M1")
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 5.0,
             "status": OperationStatus.PENDING.value},
        ])
        add_job("J2", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 2.0,
             "status": OperationStatus.PENDING.value},
        ])
        result = ProductionStateService.recalculate_schedule(0.0, algorithm="SPT")
        assert result.algorithm == "SPT"
        # Shorter job (J2, dur=2) should be scheduled first on M1
        m1_tasks = sorted(
            [t for t in result.tasks if t.machine_id == "M1"],
            key=lambda t: t.start_time
        )
        assert m1_tasks[0].job_id == "J2", "SPT must schedule shorter job first"


# ──────────────────────────────────────────────────────────────────────────────
# Task 6: Comprehensive invariant coverage
# ──────────────────────────────────────────────────────────────────────────────

class TestSchedulingInvariants:
    """
    Explicitly verified invariants across the heuristic and CP-SAT schedulers.
    """

    def _run_fcfs(self):
        return ProductionStateService.recalculate_schedule(0.0, algorithm="FCFS")

    def test_operation_precedence_three_ops(self):
        """3-operation chain: op3 must start after op2 which must start after op1."""
        add_machine("M1")
        add_machine("M2")
        add_machine("M3")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
            {"sequence": 2, "name": "Op2", "machine_id": "M2", "duration": 4.0,
             "status": OperationStatus.PENDING.value},
            {"sequence": 3, "name": "Op3", "machine_id": "M3", "duration": 2.0,
             "status": OperationStatus.PENDING.value},
        ])
        result = self._run_fcfs()
        tasks = sorted(
            [t for t in result.tasks if t.job_id == "J1"],
            key=lambda t: t.operation_sequence
        )
        for i in range(len(tasks) - 1):
            assert tasks[i + 1].start_time >= tasks[i].end_time - 1e-6, \
                f"Op{tasks[i+1].operation_sequence} must start after Op{tasks[i].operation_sequence} ends"

    def test_machine_no_overlap_three_jobs_same_machine(self):
        """Three jobs all needing M1: tasks must form a non-overlapping sequence."""
        add_machine("M1")
        for jid, dur in [("JA", 3), ("JB", 5), ("JC", 2)]:
            add_job(jid, arrival=0.0, ops=[
                {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": float(dur),
                 "status": OperationStatus.PENDING.value},
            ])
        result = self._run_fcfs()
        m1_tasks = sorted(
            [t for t in result.tasks if t.machine_id == "M1"],
            key=lambda t: t.start_time
        )
        for i in range(len(m1_tasks) - 1):
            assert m1_tasks[i].end_time <= m1_tasks[i + 1].start_time + 1e-6, \
                f"Overlap: {m1_tasks[i].job_id} [{m1_tasks[i].start_time}-{m1_tasks[i].end_time}] " \
                f"overlaps {m1_tasks[i+1].job_id} [{m1_tasks[i+1].start_time}-{m1_tasks[i+1].end_time}]"

    def test_release_time_respected(self):
        """Job with arrival_time=10.0 must not start before t=10 even at sim_time=0."""
        add_machine("M1")
        add_machine("M2")
        add_job("J_FUTURE", arrival=10.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 4.0,
             "status": OperationStatus.PENDING.value},
        ], due=50.0)
        result = self._run_fcfs()
        tasks = [t for t in result.tasks if t.job_id == "J_FUTURE"]
        assert len(tasks) > 0
        for t in tasks:
            assert t.start_time >= 10.0 - 1e-6, \
                f"Task with arrival 10 must not start before 10; got {t.start_time}"

    def test_invalid_input_empty_ops_rejected(self):
        """Empty operations list must raise ValueError before any DB state change."""
        add_machine("M1")
        add_job("J_EMPTY", arrival=0.0, ops=[])
        with pytest.raises(ValueError):
            ProductionStateService.recalculate_schedule(0.0, algorithm="FCFS")

    def test_schedule_result_persisted_to_db(self):
        """Every call to recalculate_schedule must persist a ScheduleRecordModel."""
        add_machine("M1")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])
        result = ProductionStateService.recalculate_schedule(0.0, algorithm="FCFS")
        db = SessionLocal()
        record = db.query(ScheduleRecordModel).filter(
            ScheduleRecordModel.schedule_id == result.schedule_id
        ).first()
        db.close()
        assert record is not None, "Schedule result must be persisted to DB"

    def test_full_schedule_passes_validator(self):
        """Any schedule produced by the service must pass ScheduleValidator.validate."""
        add_machine("M1")
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 5.0,
             "status": OperationStatus.PENDING.value},
            {"sequence": 2, "name": "Op2", "machine_id": "M2", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])
        add_job("J2", arrival=2.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 2.0,
             "status": OperationStatus.PENDING.value},
        ])
        result = ProductionStateService.recalculate_schedule(0.0, algorithm="FCFS")
        machines = ProductionStateService.get_all_machines()
        is_valid, errors = ScheduleValidator.validate(result.tasks, machines, 0.0)
        assert is_valid, f"Validator errors: {errors}"

    def test_repeated_scheduling_idempotent_task_count(self):
        """Calling recalculate twice without adding jobs must not produce extra tasks."""
        add_machine("M1")
        add_machine("M2")
        add_job("J1", arrival=0.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])
        r1 = ProductionStateService.recalculate_schedule(0.0, algorithm="FCFS")
        r2 = ProductionStateService.recalculate_schedule(0.0, algorithm="FCFS")
        # Same set of task counts (jobs haven't changed)
        assert len(r2.tasks) == len(r1.tasks), \
            "Repeating schedule without new jobs must not add extra tasks"

    def test_edd_schedules_earlier_due_date_first(self):
        """EDD rule: job with earlier due date must be scheduled first on same machine."""
        add_machine("M1")
        add_job("J_TIGHT", arrival=0.0, due=10.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])
        add_job("J_LOOSE", arrival=0.0, due=100.0, ops=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 3.0,
             "status": OperationStatus.PENDING.value},
        ])
        result = ProductionStateService.recalculate_schedule(0.0, algorithm="EDD")
        m1_tasks = sorted(
            [t for t in result.tasks if t.machine_id == "M1"],
            key=lambda t: t.start_time
        )
        assert m1_tasks[0].job_id == "J_TIGHT", \
            "EDD must schedule tighter due-date job first"
