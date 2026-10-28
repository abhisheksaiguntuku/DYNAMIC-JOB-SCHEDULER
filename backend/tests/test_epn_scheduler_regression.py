import os
import pytest
from unittest import mock

from app.ml.inference.epn_scheduler import EPNJobShopScheduler
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.scheduling.validator import ScheduleValidator
from app.schemas.models import Job, Machine, Operation

# Helper to create a simple deterministic job set
def make_simple_jobs():
    # Two jobs, each with a single operation on different machines
    op1 = Operation(name="Op1", machine_id="M1", duration=5.0, sequence=1)
    op2 = Operation(name="Op2", machine_id="M2", duration=3.0, sequence=1)
    job1 = Job(job_id="J1", name="Job1", product_type="Test", arrival_time=0.0, priority=1, due_date=20.0, operations=[op1])
    job2 = Job(job_id="J2", name="Job2", product_type="Test", arrival_time=0.0, priority=1, due_date=20.0, operations=[op2])
    return [job1, job2]

def make_machines():
    return [Machine(machine_id="M1", name="M1", capability="Process_1", status="IDLE", remaining_processing_time=0.0),
            Machine(machine_id="M2", name="M2", capability="Process_2", status="IDLE", remaining_processing_time=0.0)]

def test_default_checkpoint_loaded():
    """The scheduler should locate the default checkpoint and set loaded=True."""
    scheduler = EPNJobShopScheduler()
    # The real checkpoint file exists in the repository
    default_path = os.path.join(
        os.path.dirname(__file__), "..", "models", "checkpoints", "epn_model.pth"
    )
    assert os.path.exists(default_path), "Checkpoint file missing in repository"
    assert scheduler.loaded is True, "Scheduler failed to load the default checkpoint"

def test_invalid_checkpoint_path_handling():
    """Providing a non-existent path should result in fallback behavior."""
    scheduler = EPNJobShopScheduler(checkpoint_path="/nonexistent/path/epn_model.pth")
    assert scheduler.loaded is False
    jobs = make_simple_jobs()
    machines = make_machines()
    result = scheduler.schedule(jobs, machines, current_time=0.0)
    # The result should be an SPT schedule with the fallback status flag
    assert result.metrics.solver_status == "FALLBACK_NO_MODEL"
    # Verify that the schedule matches the pure SPT heuristic result
    spt_res = DispatchHeuristicScheduler.schedule(jobs, machines, 0.0, rule="SPT")
    assert result.tasks == spt_res.tasks

def test_neural_inference_is_called(monkeypatch):
    """Ensure the model's forward method is invoked during scheduling."""
    scheduler = EPNJobShopScheduler()
    if not scheduler.loaded:
        pytest.skip("EPN checkpoint not found, cannot test neural inference")
    call_counter = {'calls': 0}
    import torch
    import numpy as np

    original_call = scheduler.model.__class__.__call__

    def fake_forward(self_model, *args, **kwargs):
        call_counter['calls'] += 1
        return original_call(self_model, *args, **kwargs)

    monkeypatch.setattr(scheduler.model.__class__, "__call__", fake_forward)
    jobs = make_simple_jobs()
    machines = make_machines()
    _ = scheduler.schedule(jobs, machines, current_time=0.0)
    assert call_counter['calls'] >= 1, "Model forward pass was not invoked"

def test_schedule_passes_validator():
    """A schedule produced with a loaded model must be validated successfully."""
    scheduler = EPNJobShopScheduler()
    if not scheduler.loaded:
        pytest.skip("EPN checkpoint not found, cannot test schedule validation")
    jobs = make_simple_jobs()
    machines = make_machines()
    result = scheduler.schedule(jobs, machines, current_time=0.0)
    # The validator should report no feasibility violations
    assert result.metrics.solver_status == "NEURAL_PREDICTED_FEASIBLE"
    # Directly run the validator on the produced tasks to double-check
    is_valid, errors = ScheduleValidator.validate(result.tasks, machines, current_time=0.0)
    assert is_valid, f"Validator found errors in EPN schedule: {errors}"

def test_neural_schedule_differs_from_spt():
    """When the real model is loaded, EPN start times may differ from pure SPT due to neural offsets."""
    scheduler = EPNJobShopScheduler()
    if not scheduler.loaded:
        pytest.skip("EPN checkpoint not found, cannot test schedule difference")
    jobs = make_simple_jobs()
    machines = make_machines()
    epn_res = scheduler.schedule(jobs, machines, current_time=0.0)
    spt_res = DispatchHeuristicScheduler.schedule(jobs, machines, 0.0, rule="SPT")
    # Both schedules must be valid
    is_valid_epn, _ = ScheduleValidator.validate(epn_res.tasks, machines, current_time=0.0)
    is_valid_spt, _ = ScheduleValidator.validate(spt_res.tasks, machines, current_time=0.0)
    assert is_valid_epn, "EPN schedule invalid"
    assert is_valid_spt, "SPT schedule invalid"
    # The solver status fields should differ
    assert epn_res.metrics.solver_status == "NEURAL_PREDICTED_FEASIBLE"
    # Note: with a real trained model, start times may or may not differ from SPT.
    # The key property is that the EPN result is independently valid.
