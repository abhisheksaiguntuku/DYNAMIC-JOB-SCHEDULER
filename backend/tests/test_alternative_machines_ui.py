import pytest
from app.schemas.models import Job, Operation, Machine, MachineStatus
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer
from app.scheduling.validator import ScheduleValidator

def test_alternative_machines_workflow_in_solver_and_validator(reset_db):
    """
    Demonstrates the exact workflow requested:
    - Operation 1: M1 or M3
    - Operation 2: M4 or M5
    - Operation 3: M7 only
    Asserts CP-SAT allocates only valid alternative machines and passes independent validation.
    """
    machines = [
        Machine(machine_id=f"M{i}", name=f"Machine {i}", capability=f"Cap {i}", status=MachineStatus.IDLE)
        for i in range(1, 11)
    ]
    job = Job(
        job_id="JOB_ALT_TEST",
        name="Flexible Aircraft Fitting",
        product_type="Fitting",
        quantity=1,
        arrival_time=0.0,
        due_date=100.0,
        priority=4,
        operations=[
            Operation(sequence=1, name="Rough Turn", machine_id="M1", alternative_machines=["M3"], duration=10.0),
            Operation(sequence=2, name="Precision Mill", machine_id="M4", alternative_machines=["M5"], duration=15.0),
            Operation(sequence=3, name="Final QA", machine_id="M7", alternative_machines=[], duration=8.0)
        ]
    )

    res = CPSATSchedulingOptimizer.optimize([job], machines, current_time=0.0)
    assert len(res.tasks) == 3

    t1 = next(t for t in res.tasks if t.operation_sequence == 1)
    t2 = next(t for t in res.tasks if t.operation_sequence == 2)
    t3 = next(t for t in res.tasks if t.operation_sequence == 3)

    # Assert assigned machines belong exclusively to the eligible sets
    assert t1.machine_id in ("M1", "M3")
    assert t2.machine_id in ("M4", "M5")
    assert t3.machine_id == "M7"

    # Assert precedence
    assert t2.start_time >= t1.end_time
    assert t3.start_time >= t2.end_time

    # Validate against zero-trust schedule validator
    is_valid, errors = ScheduleValidator.validate(res.tasks, machines, current_time=0.0, jobs=[job])
    assert is_valid, f"Schedule validation errors: {errors}"

