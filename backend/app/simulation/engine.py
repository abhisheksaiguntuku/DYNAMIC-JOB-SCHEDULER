from typing import List, Dict, Any, Optional
from app.schemas.models import Job, Machine, MachineStatus, JobStatus, OperationStatus
from app.core.state_service import ProductionStateService
from app.database.db import SessionLocal, MachineModel, JobModel, ScheduleRecordModel

class DiscreteEventSimulator:
    """
    Clock-driven Discrete Event Simulator for 10-Machine Production Shop Floor.
    Simulates:
    - Time advancement
    - Machine job processing and completion
    - Dependent operation enablement
    - Dynamic arrival of new orders
    """
    def __init__(self):
        self.sim_time: float = 0.0
        self.is_running: bool = False
        self.speed_multiplier: float = 1.0

    def get_status(self) -> Dict[str, Any]:
        return {
            "sim_time": round(self.sim_time, 2),
            "is_running": self.is_running,
            "speed_multiplier": self.speed_multiplier
        }

    def advance_time(self, step_minutes: float = 5.0) -> Dict[str, Any]:
        self.sim_time += step_minutes
        events = []
        
        db = SessionLocal()
        try:
            machines = db.query(MachineModel).all()
            for m in machines:
                if m.status == MachineStatus.BUSY.value:
                    m.remaining_processing_time = max(0.0, m.remaining_processing_time - step_minutes)
                    m.total_busy_time += min(step_minutes, m.remaining_processing_time + step_minutes)
                    
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
            db.commit()
        finally:
            db.close()
            
        return {
            "current_sim_time": round(self.sim_time, 2),
            "step": step_minutes,
            "events": events
        }

    def reset(self):
        self.sim_time = 0.0
        self.is_running = False
