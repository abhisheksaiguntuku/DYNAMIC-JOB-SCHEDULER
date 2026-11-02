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

    def _dispatch_ready_operations(self, db, events: List[str]) -> None:
        """Helper to find ready operations and dispatch them to IDLE machines at current sim_time."""
        machines = db.query(MachineModel).all()
        idle_machines = {m.machine_id: m for m in machines if m.status == MachineStatus.IDLE.value}
        if not idle_machines:
            return

        all_jobs = db.query(JobModel).filter(JobModel.status != JobStatus.COMPLETED.value).all()
        ready_candidates = []
        for j in all_jobs:
            if (j.arrival_time or 0.0) <= self.sim_time + 1e-6:
                ops = j.operations_json or []
                sorted_ops = sorted(ops, key=lambda x: x["sequence"])
                for idx, op in enumerate(sorted_ops):
                    op_status = op.get("status", OperationStatus.PENDING.value)
                    if op_status == OperationStatus.COMPLETED.value:
                        continue
                    elif op_status == OperationStatus.PENDING.value:
                        preds_completed = all(p.get("status", OperationStatus.PENDING.value) == OperationStatus.COMPLETED.value for p in sorted_ops[:idx])
                        if preds_completed:
                            ready_candidates.append((j, op))
                    break

        def candidate_sort_key(item):
            job_obj, op_dict = item
            prio = getattr(job_obj, "priority", 3) or 3
            arr = job_obj.arrival_time or 0.0
            due = job_obj.due_date if (job_obj.due_date is not None and job_obj.due_date > 0) else 1e9
            return (-prio, arr, due, op_dict["duration"], job_obj.job_id)

        ready_candidates.sort(key=candidate_sort_key)

        dispatched_jobs = set()
        for job_obj, op_dict in ready_candidates:
            if job_obj.job_id in dispatched_jobs:
                continue
            req_m = op_dict["machine_id"]
            alt_ms = op_dict.get("alternative_machines") or []
            eligible_ms = [req_m] + [alt for alt in alt_ms if alt]

            chosen_m_id = None
            for em in eligible_ms:
                if em in idle_machines:
                    chosen_m_id = em
                    break

            if chosen_m_id is not None:
                machine_to_assign = idle_machines.pop(chosen_m_id)
                machine_to_assign.status = MachineStatus.BUSY.value
                machine_to_assign.current_job_id = job_obj.job_id
                machine_to_assign.current_operation_seq = op_dict["sequence"]
                machine_to_assign.remaining_processing_time = float(op_dict["duration"])

                updated_ops = []
                for op in job_obj.operations_json:
                    op_copy = dict(op)
                    if op_copy["sequence"] == op_dict["sequence"]:
                        op_copy["status"] = OperationStatus.RUNNING.value
                        op_copy["start_time"] = self.sim_time
                        op_copy["assigned_machine_id"] = chosen_m_id
                    updated_ops.append(op_copy)
                job_obj.operations_json = updated_ops
                job_obj.status = JobStatus.IN_PROGRESS.value
                dispatched_jobs.add(job_obj.job_id)
                events.append(
                    f"Dispatched {job_obj.job_id} Op {op_dict['sequence']} ({op_dict['name']}) "
                    f"to {chosen_m_id} at t={self.sim_time:.1f} (dur={op_dict['duration']})"
                )

    def advance_time(self, step_minutes: float = 5.0) -> Dict[str, Any]:
        if step_minutes <= 0:
            raise ValueError("step_minutes must be greater than zero.")
        with ProductionStateService._lock:
            self.load_state()
            events = []
            
            target_time = round(self.sim_time + step_minutes, 6)
            
            db = SessionLocal()
            try:
                # Dispatch any ready pending operations onto idle machines at the starting clock
                self._dispatch_ready_operations(db, events)
                
                while round(self.sim_time, 6) < target_time - 1e-6:
                    machines = db.query(MachineModel).all()
                    next_event_time = target_time
                    for m in machines:
                        if m.status == MachineStatus.BUSY.value and m.remaining_processing_time > 1e-6:
                            t_finish = round(self.sim_time + m.remaining_processing_time, 6)
                            if t_finish < next_event_time:
                                next_event_time = t_finish
                        elif m.status in (MachineStatus.DOWN.value, MachineStatus.MAINTENANCE.value) and m.remaining_processing_time > 1e-6:
                            t_rec = round(self.sim_time + m.remaining_processing_time, 6)
                            if t_rec < next_event_time:
                                next_event_time = t_rec
                                
                    delta = round(next_event_time - self.sim_time, 6)
                    self.sim_time = next_event_time
                    
                    machines_sorted = sorted(machines, key=lambda x: x.machine_id)
                    for m in machines_sorted:
                        if m.status == MachineStatus.BUSY.value:
                            prev_rem = m.remaining_processing_time
                            m.remaining_processing_time = max(0.0, m.remaining_processing_time - delta)
                            m.total_busy_time += min(delta, prev_rem)
                            
                            if m.remaining_processing_time <= 1e-4:
                                finished_job = m.current_job_id
                                finished_seq = m.current_operation_seq
                                m.status = MachineStatus.IDLE.value
                                m.current_job_id = None
                                m.current_operation_seq = None
                                m.remaining_processing_time = 0.0
                                
                                events.append(f"Operation finished on {m.machine_id}: Job {finished_job} Op {finished_seq}")
                                
                                j_rec = db.query(JobModel).filter(JobModel.job_id == finished_job).first()
                                if j_rec:
                                    new_ops = []
                                    all_done = True
                                    for op in j_rec.operations_json:
                                        op_copy = dict(op)
                                        if op_copy.get("sequence") == finished_seq:
                                            op_copy["status"] = OperationStatus.COMPLETED.value
                                            op_copy["end_time"] = self.sim_time
                                        elif op_copy.get("status", OperationStatus.PENDING.value) != OperationStatus.COMPLETED.value:
                                            all_done = False
                                        new_ops.append(op_copy)
                                    j_rec.operations_json = new_ops
                                    if all_done:
                                        j_rec.status = JobStatus.COMPLETED.value
                                        events.append(f"Job completed: {finished_job} at t={self.sim_time:.1f}")
                                    else:
                                        j_rec.status = JobStatus.IN_PROGRESS.value
                        elif m.status in (MachineStatus.DOWN.value, MachineStatus.MAINTENANCE.value):
                            if m.remaining_processing_time > 1e-4:
                                m.remaining_processing_time = max(0.0, m.remaining_processing_time - delta)
                                if m.remaining_processing_time <= 1e-4:
                                    m.remaining_processing_time = 0.0
                                    m.status = MachineStatus.IDLE.value
                                    m.current_job_id = None
                                    m.current_operation_seq = None
                                    events.append(f"Machine {m.machine_id} recovered and returned to IDLE at t={self.sim_time:.1f}")

                    # After completing operations or recovering machines at this step,
                    # immediately dispatch newly enabled ready operations
                    self._dispatch_ready_operations(db, events)

                self.sim_time = target_time
                self.save_state(db=db)
                ProductionStateService.increment_state_version(db)
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
