"""
Stage 8 Phase 2 Tests: Simulation State Persistence
===================================================
Tests saving state, restarting the backend simulator, restoring state,
and handling empty or invalid persisted state.
"""
import pytest
from app.simulation.engine import DiscreteEventSimulator
from app.core.state_service import ProductionStateService
from app.database.db import init_db, SessionLocal, MachineModel, JobModel, SimulationStateModel
from app.schemas.models import MachineStatus, OperationStatus, JobStatus


def test_save_and_restore_sim_state_across_restart():
    """
    Advancing simulation time persists sim_time to SQLite.
    Creating a fresh DiscreteEventSimulator instance (simulating backend restart)
    restores the exact sim_time and preserves consistent machine/job states.
    """
    sim1 = DiscreteEventSimulator()
    assert sim1.sim_time == 0.0

    db = SessionLocal()
    db.add(MachineModel(
        machine_id="M1",
        name="Machine M1",
        capability="Casting",
        status=MachineStatus.BUSY.value,
        current_job_id="J_PERSIST",
        current_operation_seq=1,
        remaining_processing_time=12.0,
        total_busy_time=0.0
    ))
    db.add(JobModel(
        job_id="J_PERSIST",
        name="Persistent Job",
        product_type="Steel",
        quantity=1,
        arrival_time=0.0,
        due_date=100.0,
        priority=3,
        status=JobStatus.IN_PROGRESS.value,
        operations_json=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 12.0,
             "status": OperationStatus.RUNNING.value, "start_time": 0.0}
        ]
    ))
    db.commit()
    db.close()

    # Advance twice: 5.0 + 10.0 = 15.0 minutes
    sim1.advance_time(5.0)
    assert sim1.sim_time == 5.0

    # Simulate backend restart BEFORE operation completes
    sim_restarted_mid = DiscreteEventSimulator()
    assert sim_restarted_mid.sim_time == 5.0
    m1_mid = ProductionStateService.get_all_machines()[0]
    assert m1_mid.status == MachineStatus.BUSY
    assert m1_mid.remaining_processing_time == 7.0

    # Advance another 10 minutes on the restarted simulator
    sim_restarted_mid.advance_time(10.0)
    assert sim_restarted_mid.sim_time == 15.0

    # Simulate second restart
    sim_restarted_final = DiscreteEventSimulator()
    assert sim_restarted_final.sim_time == 15.0
    m1_final = ProductionStateService.get_all_machines()[0]
    assert m1_final.status == MachineStatus.IDLE
    j_final = ProductionStateService.get_all_jobs()[0]
    assert j_final.status == JobStatus.COMPLETED
    assert j_final.operations[0].end_time == 15.0


def test_empty_persisted_state_infers_or_defaults_cleanly():
    """
    When simulation_state table is empty, DiscreteEventSimulator initializes
    a valid record at 0.0 (or inferred from completed operations if present).
    """
    db = SessionLocal()
    db.query(SimulationStateModel).delete()
    db.add(JobModel(
        job_id="J_HIST",
        name="Historical Job",
        product_type="Demo",
        quantity=1,
        arrival_time=0.0,
        due_date=50.0,
        priority=3,
        status=JobStatus.COMPLETED.value,
        operations_json=[
            {"sequence": 1, "name": "Op1", "machine_id": "M1", "duration": 20.0,
             "status": OperationStatus.COMPLETED.value, "start_time": 0.0, "end_time": 20.0}
        ]
    ))
    db.commit()
    db.close()

    # Simulator should infer 20.0 from completed operation end_time rather than resetting to 0
    sim = DiscreteEventSimulator()
    assert sim.sim_time == 20.0


def test_invalid_persisted_state_repaired_gracefully():
    """
    If persisted state has invalid negative sim_time or non-positive speed_multiplier,
    load_state repairs it cleanly without crashing.
    """
    db = SessionLocal()
    db.query(SimulationStateModel).delete()
    db.add(SimulationStateModel(
        id=1,
        sim_time=-50.0,
        is_running=False,
        speed_multiplier=-2.0,
        state_version=0
    ))
    db.commit()
    db.close()

    sim = DiscreteEventSimulator()
    assert sim.sim_time == 0.0
    assert sim.speed_multiplier == 1.0

    db = SessionLocal()
    repaired = db.query(SimulationStateModel).filter(SimulationStateModel.id == 1).first()
    assert repaired.sim_time == 0.0
    assert repaired.speed_multiplier == 1.0
    assert repaired.state_version == 1
    db.close()


def test_reset_persists_zero_sim_time():
    """Resetting the simulator persists sim_time = 0.0 across restarts."""
    sim = DiscreteEventSimulator()
    sim.advance_time(25.0)
    assert DiscreteEventSimulator().sim_time == 25.0

    sim.reset()
    assert sim.sim_time == 0.0
    assert DiscreteEventSimulator().sim_time == 0.0

