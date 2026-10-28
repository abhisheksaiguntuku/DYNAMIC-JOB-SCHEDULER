import pytest
import json
import torch
from pathlib import Path
from app.schemas.models import Job, Machine
from app.ml.models.pointer_network import EnhancedPointerNetwork
from app.ml.inference.epn_scheduler import EPNJobShopScheduler
from app.scheduling.validator import ScheduleValidator

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

@pytest.fixture
def sample_jobs():
    with open(DATA_DIR / "initial_jobs.json", "r") as f:
        data = json.load(f)
    return [Job(**item) for item in data[:4]]

@pytest.fixture
def sample_machines():
    with open(DATA_DIR / "initial_machines.json", "r") as f:
        data = json.load(f)
    return [Machine(**item) for item in data]

def test_pointer_network_causal_masking_precedence():
    """
    Direct verification of Liu et al. (IEEE TASE 2024) Causal Masking Guarantee:
    Predicted start time indices must strictly satisfy psi_{j} <= psi_{j+1}.
    """
    model = EnhancedPointerNetwork(input_dim=5, hidden_dim=32, encoder_layers=1)
    model.eval()

    batch_size = 4
    horizon_T = 30
    num_ops = 5

    # Random cost input sequence
    dummy_input = torch.rand(batch_size, horizon_T, 5)

    with torch.no_grad():
        preds, attention = model(dummy_input, num_operations=num_ops)

    assert preds.shape == (batch_size, num_ops)
    assert attention.shape == (batch_size, num_ops, horizon_T)

    # Check precedence for every batch item
    for b in range(batch_size):
        times = preds[b].tolist()
        for i in range(len(times) - 1):
            assert times[i] <= times[i + 1], (
                f"Causal masking violation in batch {b}: "
                f"Op {i} at time {times[i]} followed by Op {i+1} at earlier time {times[i+1]}"
            )

def test_epn_scheduler_end_to_end(sample_jobs, sample_machines):
    """
    Tests that the trained PyTorch EPN scheduler outputs schedules
    that pass 100% of zero-trust ScheduleValidator checks.
    """
    scheduler = EPNJobShopScheduler()
    res = scheduler.schedule(sample_jobs, sample_machines, current_time=0.0)

    assert len(res.tasks) > 0
    assert res.metrics.makespan > 0

    # Strict independent validation
    is_valid, errors = ScheduleValidator.validate(res.tasks, sample_machines, current_time=0.0)
    assert is_valid, f"EPN Schedule failed validation: {errors}"
