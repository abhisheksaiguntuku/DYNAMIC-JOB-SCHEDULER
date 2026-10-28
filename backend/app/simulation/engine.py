from typing import List, Dict, Any, Optional
from datetime import datetime
from app.schemas.models import Job, Machine, MachineStatus, JobStatus, OperationStatus
from app.core.state_service import ProductionStateService
from app.database.db import SessionLocal, init_db, MachineModel, JobModel, ScheduleRecordModel, SimulationStateModel

class DiscreteEventSimulator:
    """
    Clock-driven Discrete Event Simulator for 10-Machine Production Shop Floor.
    Simulates:
    - Time advancement
    - Machine job processing and completion
    - Dependent operation enablement
    - Dynamic arrival of new orders
    - Persistent simulation clock and runtime state in SQLite
    """
    def __init__(self, restore_from_db: bool = True):
        self.sim_time: float = 0.0
        self.is_running: bool = False
        self.speed_multiplier: float = 1.0
        if restore_from_db:
            self.load_state()

    def load_state(self) -> Dict[str, Any]:
        """Restore persisted simulation state from SQLite, validating and sanitizing invalid values."""
        init_db()
        db = SessionLocal()
        try:
            state = db.query(SimulationStateModel).filter(SimulationStateModel.id == 1).first()
            if state is None:
                # Infer baseline time from existing completed operations or schedules if present
                latest_time = 0.0
                jobs = db.query(JobModel).all()
                for j in jobs:
                    if isinstance(j.operations_json, list):
                        for op in j.operations_json:
                            if isinstance(op, dict) and op.get("end_time") is not None:
                                try:
                                    latest_time = max(latest_time, float(op["end_time"]))
                                except (TypeError, ValueError):
                                    pass
                state = SimulationStateModel(
                    id=1,
                    sim_time=max(0.0, latest_time),
                    is_running=False,
                    speed_multiplier=1.0,
                    state_version=1,
                    updated_at=datetime.utcnow()
                )
                db.add(state)
                db.commit()
            else:
                # Validate and sanitize persisted values
                needs_repair = False
                if state.sim_time is None or not isinstance(state.sim_time, (int, float)) or state.sim_time < 0.0:
                    state.sim_time = 0.0
                    needs_repair = True
                if state.speed_multiplier is None or not isinstance(state.speed_multiplier, (int, float)) or state.speed_multiplier <= 0.0:
                    state.speed_multiplier = 1.0
                    needs_repair = True
                if state.state_version is None or not isinstance(state.state_version, int) or state.state_version < 1:
                    state.state_version = 1
                    needs_repair = True
                if needs_repair:
                    state.updated_at = datetime.utcnow()
                    db.commit()

            self.sim_time = float(state.sim_time)
            self.is_running = bool(state.is_running)
            self.speed_multiplier = float(state.speed_multiplier)
            return self.get_status()
        finally:
            db.close()

    def save_state(self, db=None) -> None:
        """Persist current simulation clock and runtime parameters to SQLite."""
        own_session = db is None
        if own_session:
            init_db()
            db = SessionLocal()
        try:
            state = db.query(SimulationStateModel).filter(SimulationStateModel.id == 1).first()
            if state is None:
                state = SimulationStateModel(
                    id=1,
                    sim_time=max(0.0, float(self.sim_time)),
                    is_running=bool(self.is_running),
                    speed_multiplier=max(0.1, float(self.speed_multiplier)),
                    state_version=1,
                    updated_at=datetime.utcnow()
                )
                db.add(state)
            else:
                state.sim_time = max(0.0, float(self.sim_time))
                state.is_running = bool(self.is_running)
                state.speed_multiplier = max(0.1, float(self.speed_multiplier))
                state.state_version = (state.state_version or 1) + 1
                state.updated_at = datetime.utcnow()
            if own_session:
                db.commit()
        finally:
            if own_session:
                db.close()

    def get_status(self) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            state = db.query(SimulationStateModel).filter(SimulationStateModel.id == 1).first()
            version = int(state.state_version) if state and state.state_version is not None else 1
        finally:
            db.close()
        return {
            "sim_time": round(self.sim_time, 2),
            "is_running": self.is_running,
            "speed_multiplier": self.speed_multiplier,
            "state_version": version
        }

    def advance_time(self, step_minutes: float = 5.0) -> Dict[str, Any]:
        if step_minutes <= 0:
            raise ValueError("step_minutes must be greater than zero.")
        with ProductionStateService._lock:
            self.load_state()
            self.sim_time += step_minutes
            events = []
            
            db = SessionLocal()
            try:
                machines = db.query(MachineModel).all()
                for m in machines:
                    if m.status == MachineStatus.BUSY.value:
                        prev_rem = m.remaining_processing_time
                        m.remaining_processing_time = max(0.0, m.remaining_processing_time - step_minutes)
                        m.total_busy_time += min(step_minutes, prev_rem)
                        
                        if m.remaining_processing_time <= 1e-4:
                            # Operation finished
                            finished_job = m.current_job_id
                            finished_seq = m.current_operation_seq
                            m.status = MachineStatus.IDLE.value
                            m.current_job_id = None
                            m.current_operation_seq = None
                            m.remaining_processing_time = 0.0
                            
                            events.append(f"Operation finished on {m.machine_id}: Job {finished_job} Op {finished_seq}")
                            
                            # Update Job record
                            j_rec = db.query(JobModel).filter(JobModel.job_id == finished_job).first()
                            if j_rec:
                                # Build a fresh list copy – SQLAlchemy won't detect in-place
                                # mutations to JSON columns; a new object assignment is required.
                                new_ops = []
                                all_done = True
                                for op in j_rec.operations_json:
                                    op_copy = dict(op)
                                    if op_copy["sequence"] == finished_seq:
                                        op_copy["status"] = OperationStatus.COMPLETED.value
                                        op_copy["end_time"] = self.sim_time
                                    elif op_copy["status"] != OperationStatus.COMPLETED.value:
                                        all_done = False
                                    new_ops.append(op_copy)
                                j_rec.operations_json = new_ops
                                if all_done:
                                    j_rec.status = JobStatus.COMPLETED.value
                                    events.append(f"Job completed: {finished_job} at t={self.sim_time:.1f}")
                    elif m.status in (MachineStatus.DOWN.value, MachineStatus.MAINTENANCE.value):
                        if m.remaining_processing_time > 1e-4:
                            m.remaining_processing_time = max(0.0, m.remaining_processing_time - step_minutes)
                            if m.remaining_processing_time <= 1e-4:
                                m.remaining_processing_time = 0.0
                                if m.current_job_id is not None:
                                    # Non-preemptive running operation was already finished before breakdown took effect
                                    m.status = MachineStatus.IDLE.value
                                    m.current_job_id = None
                                    m.current_operation_seq = None
                                else:
                                    m.status = MachineStatus.IDLE.value
                                events.append(f"Machine {m.machine_id} recovered and returned to IDLE at t={self.sim_time:.1f}")
                self.save_state(db=db)
                db.commit()
            finally:
                db.close()
                
            return {
                "current_sim_time": round(self.sim_time, 2),
                "step": step_minutes,
                "events": events
            }

    def reset(self):
        with ProductionStateService._lock:
            self.sim_time = 0.0
            self.is_running = False
            self.save_state()
