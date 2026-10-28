import pytest
from app.schemas.models import Job, Operation, Machine
from app.core.state_service import ProductionStateService
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.scheduling.validator import ScheduleValidator
from app.database.db import init_db, SessionLocal, JobModel, MachineModel, SimulationStateModel
import pydantic_core

@pytest.fixture(autouse=True)
def setup_ten_machines_db():
    init_db()
    db = SessionLocal()
    db.query(SimulationStateModel).delete()
    db.query(JobModel).delete()
    db.query(MachineModel).delete()
    # Add all 10 machines
    capabilities = {
        "M1": "Pattern Making", "M2": "Mould Making", "M3": "Casting",
        "M4": "Heat Treatment", "M5": "Machining",
        "M6": "Pattern Making", "M7": "Mould Making", "M8": "Casting",
        "M9": "Heat Treatment", "M10": "Machining"
    }
    for i in range(1, 11):
        mid = f"M{i}"
        db.add(MachineModel(
            machine_id=mid,
            name=f"Stage {i} Machine",
            capability=capabilities[mid],
            status="IDLE",
            remaining_processing_time=0.0,
            total_busy_time=0.0
        ))
    db.commit()
    db.close()
    yield

def test_job_validation_zero_duration_rejected():
    """Duration <= 0 must be rejected by Pydantic schema validation."""
    with pytest.raises(Exception):
        Operation(sequence=1, name="InvalidOp", machine_id="M1", duration=0.0)

def test_job_validation_negative_duration_rejected():
    """Negative duration must be rejected."""
    with pytest.raises(Exception):
        Operation(sequence=1, name="InvalidOp", machine_id="M1", duration=-5.0)

def test_job_validation_empty_operations_rejected():
    """Job with empty operations must be rejected by ProductionStateService."""
    job = Job(
        job_id="EMPTY_JOB",
        name="Empty Job",
        product_type="Test",
        due_date=100.0,
        operations=[]
    )
    with pytest.raises(ValueError, match="at least one operation"):
        ProductionStateService.add_job(job)

def test_job_validation_nonexistent_machine_rejected():
    """Job with non-existent machine ID must be rejected by ProductionStateService."""
    job = Job(
        job_id="BAD_MACHINE_JOB",
        name="Bad Machine Job",
        product_type="Test",
        due_date=100.0,
        operations=[
            Operation(sequence=1, name="Op1", machine_id="M999", duration=15.0)
        ]
    )
    with pytest.raises(ValueError, match="invalid or non-existent machine"):
        ProductionStateService.add_job(job)

def test_job_starting_on_m6_operational():
    """Job starting on auxiliary machine M6 is scheduled and validated."""
    job = Job(
        job_id="J_START_M6",
        name="Turbine Core Prep",
        product_type="Aerospace",
        arrival_time=0.0,
        due_date=150.0,
        priority=4,
        operations=[
            Operation(sequence=1, name="Aux Pattern Prep", machine_id="M6", duration=25.0),
            Operation(sequence=2, name="Aux Mould Prep", machine_id="M7", duration=30.0)
        ]
    )
    ProductionStateService.add_job(job)
    machines = ProductionStateService.get_all_machines()
    
    # Verify CP-SAT schedules on M6 and M7
    res_cpsat = CPSATSchedulingOptimizer.optimize([job], machines, current_time=0.0)
    is_valid, errors = ScheduleValidator.validate(res_cpsat.tasks, machines, 0.0)
    assert is_valid, f"CP-SAT failed on M6 route: {errors}"
    
    m6_tasks = [t for t in res_cpsat.tasks if t.machine_id == "M6"]
    assert len(m6_tasks) == 1
    assert m6_tasks[0].job_id == "J_START_M6"
    assert m6_tasks[0].start_time == 0.0

def test_job_starting_on_m7_operational():
    """Job starting directly on M7 with single operation."""
    job = Job(
        job_id="J_START_M7",
        name="Quick Mould Repair",
        product_type="Tooling",
        arrival_time=0.0,
        due_date=60.0,
        priority=5,
        operations=[
            Operation(sequence=1, name="Rapid Assembly", machine_id="M7", duration=20.0)
        ]
    )
    ProductionStateService.add_job(job)
    machines = ProductionStateService.get_all_machines()
    
    res = DispatchHeuristicScheduler.schedule([job], machines, current_time=0.0, rule="SPT")
    is_valid, errors = ScheduleValidator.validate(res.tasks, machines, 0.0)
    assert is_valid, f"SPT failed on M7 route: {errors}"
    assert any(t.machine_id == "M7" and t.start_time == 0.0 for t in res.tasks)

def test_job_starting_on_m10_operational():
    """Job starting directly on M10 (CNC Finishing Aux)."""
    job = Job(
        job_id="J_START_M10",
        name="Direct CNC Polish",
        product_type="Finishing",
        arrival_time=0.0,
        due_date=80.0,
        priority=3,
        operations=[
            Operation(sequence=1, name="Aux CNC Finish", machine_id="M10", duration=18.0)
        ]
    )
    ProductionStateService.add_job(job)
    machines = ProductionStateService.get_all_machines()
    
    res = CPSATSchedulingOptimizer.optimize([job], machines, current_time=0.0)
    is_valid, errors = ScheduleValidator.validate(res.tasks, machines, 0.0)
    assert is_valid, f"Validation failed on M10 start: {errors}"
    assert any(t.machine_id == "M10" for t in res.tasks)

def test_mixed_cross_stage_routing_m1_m5_and_m6_m10():
    """
    Mixed route using both primary (M1, M4) and auxiliary (M7, M8, M10) machines.
    Route: M1 -> M7 -> M8 -> M4 -> M10.
    """
    job = Job(
        job_id="J_MIXED_ROUTING",
        name="Hybrid Subassembly",
        product_type="High Precision Flange",
        arrival_time=0.0,
        due_date=300.0,
        priority=4,
        operations=[
            Operation(sequence=1, name="Primary Pattern", machine_id="M1", duration=20.0),
            Operation(sequence=2, name="Aux Mould Assembly", machine_id="M7", duration=25.0),
            Operation(sequence=3, name="Aux Pouring", machine_id="M8", duration=35.0),
            Operation(sequence=4, name="Primary Furnace", machine_id="M4", duration=30.0),
            Operation(sequence=5, name="Aux CNC Quality", machine_id="M10", duration=22.0)
        ]
    )
    ProductionStateService.add_job(job)
    machines = ProductionStateService.get_all_machines()
    
    # Test across CP-SAT and all heuristics
    for algo in ["CPSAT", "FCFS", "SPT", "EDD"]:
        if algo == "CPSAT":
            res = CPSATSchedulingOptimizer.optimize([job], machines, current_time=0.0)
        else:
            res = DispatchHeuristicScheduler.schedule([job], machines, current_time=0.0, rule=algo)
            
        is_valid, errors = ScheduleValidator.validate(res.tasks, machines, 0.0)
        assert is_valid, f"Mixed route failed under {algo}: {errors}"
        
        # Verify precedence across all 5 operations
        sorted_tasks = sorted(res.tasks, key=lambda t: t.operation_sequence)
        assert len(sorted_tasks) == 5
        for k in range(len(sorted_tasks) - 1):
            assert sorted_tasks[k+1].start_time >= sorted_tasks[k].end_time - 1e-4

def test_repeated_machine_use_in_single_job():
    """Job route that revisits machine M5 twice (e.g., rough machining then final grinding)."""
    job = Job(
        job_id="J_REPEATED_M5",
        name="Dual Machining Component",
        product_type="Shaft",
        arrival_time=0.0,
        due_date=200.0,
        priority=3,
        operations=[
            Operation(sequence=1, name="Rough Machining", machine_id="M5", duration=15.0),
            Operation(sequence=2, name="Heat Treatment", machine_id="M4", duration=20.0),
            Operation(sequence=3, name="Finish Machining", machine_id="M5", duration=10.0)
        ]
    )
    ProductionStateService.add_job(job)
    machines = ProductionStateService.get_all_machines()
    
    res = CPSATSchedulingOptimizer.optimize([job], machines, current_time=0.0)
    is_valid, errors = ScheduleValidator.validate(res.tasks, machines, 0.0)
    assert is_valid, f"Repeated machine use failed validation: {errors}"
    
    m5_tasks = sorted([t for t in res.tasks if t.machine_id == "M5"], key=lambda t: t.start_time)
    assert len(m5_tasks) == 2
    # Ensure no overlap on M5 between Op 1 and Op 3
    assert m5_tasks[1].start_time >= m5_tasks[0].end_time - 1e-4

def test_demo_reset_preserves_database_and_clears_user_jobs(tmp_path):
    """Verify reset_to_demo_workload restores exactly demo jobs."""
    from pathlib import Path
    data_dir = Path(__file__).resolve().parent.parent / "data"
    jobs_file = str(data_dir / "initial_jobs.json")
    machines_file = str(data_dir / "initial_machines.json")
    
    # Insert custom job
    custom_job = Job(
        job_id="CUSTOM_USER_JOB_999",
        name="Custom Job",
        product_type="Custom",
        due_date=100.0,
        operations=[Operation(sequence=1, name="Op", machine_id="M1", duration=10.0)]
    )
    ProductionStateService.add_job(custom_job)
    assert any(j.job_id == "CUSTOM_USER_JOB_999" for j in ProductionStateService.get_all_jobs())
    
    # Reset to demo
    count = ProductionStateService.reset_to_demo_workload(jobs_file, machines_file)
    assert count == 10
    jobs_after = ProductionStateService.get_all_jobs()
    assert len(jobs_after) == 10
    assert not any(j.job_id == "CUSTOM_USER_JOB_999" for j in jobs_after)
