import json
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.database.db import SessionLocal, init_db, JobModel, MachineModel, ScheduleRecordModel, SimulationStateModel
from app.schemas.models import Job, Machine, ScheduleResult, Operation, OperationStatus, MachineStatus, JobStatus
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer


class StaleScheduleError(ValueError):
    """Raised when a schedule calculation or update is attempted against an obsolete production state."""
    pass


class ProductionStateService:
    _lock = threading.RLock()

    @staticmethod
    def get_state_version(db=None) -> int:
        own_session = db is None
        if own_session:
            init_db()
            db = SessionLocal()
        try:
            state = db.query(SimulationStateModel).filter(SimulationStateModel.id == 1).first()
            if state is None:
                state = SimulationStateModel(
                    id=1,
                    sim_time=0.0,
                    is_running=False,
                    speed_multiplier=1.0,
                    state_version=1,
                    updated_at=datetime.utcnow()
                )
                db.add(state)
                if own_session:
                    db.commit()
            return int(state.state_version or 1)
        finally:
            if own_session:
                db.close()

    @staticmethod
    def increment_state_version(db) -> int:
        state = db.query(SimulationStateModel).filter(SimulationStateModel.id == 1).first()
        if state is None:
            state = SimulationStateModel(
                id=1,
                sim_time=0.0,
                is_running=False,
                speed_multiplier=1.0,
                state_version=2,
                updated_at=datetime.utcnow()
            )
            db.add(state)
            return 2
        else:
            state.state_version = int(state.state_version or 1) + 1
            state.updated_at = datetime.utcnow()
            return state.state_version
    @staticmethod
    def seed_if_empty(initial_jobs_path: str, initial_machines_path: str):
        init_db()
        db = SessionLocal()
        try:
            if db.query(MachineModel).count() == 0:
                with open(initial_machines_path, "r") as f:
                    machines_data = json.load(f)
                for m in machines_data:
                    db.add(MachineModel(
                        machine_id=m["machine_id"],
                        name=m["name"],
                        capability=m["capability"],
                        status=m["status"],
                        remaining_processing_time=0.0,
                        total_busy_time=0.0
                    ))
                db.commit()

            if db.query(JobModel).count() == 0:
                with open(initial_jobs_path, "r") as f:
                    jobs_data = json.load(f)
                for j in jobs_data:
                    db.add(JobModel(
                        job_id=j["job_id"],
                        name=j["name"],
                        product_type=j["product_type"],
                        quantity=j.get("quantity", 1),
                        arrival_time=j.get("arrival_time", 0.0),
                        due_date=j["due_date"],
                        priority=j.get("priority", 3),
                        status="PENDING",
                        operations_json=[op for op in j["operations"]]
                    ))
                db.commit()
        finally:
            db.close()

    @staticmethod
    def reset_to_demo_workload(initial_jobs_path: str, initial_machines_path: str) -> int:
        """
        Resets jobs and machines to the baseline demo dataset.
        Faculty benchmarks and EPN checkpoints remain completely untouched.
        """
        init_db()
        db = SessionLocal()
        try:
            # Clear all current jobs and reset machines to baseline demo machines
            db.query(JobModel).delete()
            if initial_machines_path:
                db.query(MachineModel).delete()
                with open(initial_machines_path, "r") as f:
                    machines_data = json.load(f)
                for m in machines_data:
                    db.add(MachineModel(
                        machine_id=m["machine_id"],
                        name=m["name"],
                        capability=m["capability"],
                        status=MachineStatus.IDLE.value,
                        remaining_processing_time=0.0,
                        total_busy_time=0.0
                    ))
            else:
                machines = db.query(MachineModel).all()
                for m in machines:
                    m.status = MachineStatus.IDLE.value
                    m.current_job_id = None
                    m.current_operation_seq = None
                    m.remaining_processing_time = 0.0
                    m.total_busy_time = 0.0

            sim_state = db.query(SimulationStateModel).filter(SimulationStateModel.id == 1).first()
            if sim_state:
                sim_state.sim_time = 0.0
                sim_state.is_running = False
                sim_state.state_version = (sim_state.state_version or 1) + 1
            else:
                db.add(SimulationStateModel(id=1, sim_time=0.0, is_running=False, speed_multiplier=1.0, state_version=1))

            # Re-seed baseline demo jobs
            with open(initial_jobs_path, "r") as f:
                jobs_data = json.load(f)
            for j in jobs_data:
                db.add(JobModel(
                    job_id=j["job_id"],
                    name=j["name"],
                    product_type=j["product_type"],
                    quantity=j.get("quantity", 1),
                    arrival_time=j.get("arrival_time", 0.0),
                    due_date=j["due_date"],
                    priority=j.get("priority", 3),
                    status="PENDING",
                    operations_json=[op for op in j["operations"]]
                ))
            db.commit()
            return len(jobs_data)
        finally:
            db.close()

    @staticmethod
    def get_all_jobs() -> List[Job]:
        db = SessionLocal()
        try:
            records = db.query(JobModel).all()
            jobs = []
            for r in records:
                ops = [Operation(**op_dict) for op_dict in r.operations_json]
                jobs.append(Job(
                    job_id=r.job_id,
                    name=r.name,
                    product_type=r.product_type,
                    quantity=r.quantity,
                    arrival_time=r.arrival_time,
                    due_date=r.due_date,
                    priority=r.priority,
                    status=JobStatus(r.status),
                    operations=ops
                ))
            return jobs
        finally:
            db.close()

    @staticmethod
    def get_all_machines() -> List[Machine]:
        db = SessionLocal()
        try:
            records = db.query(MachineModel).all()
            return [
                Machine(
                    machine_id=r.machine_id,
                    name=r.name,
                    capability=r.capability,
                    status=MachineStatus(r.status),
                    current_job_id=r.current_job_id,
                    current_operation_seq=r.current_operation_seq,
                    remaining_processing_time=r.remaining_processing_time,
                    total_busy_time=r.total_busy_time
                ) for r in records
            ]
        finally:
            db.close()

    @staticmethod
    def add_job(job: Job) -> Job:
        with ProductionStateService._lock:
            db = SessionLocal()
            try:
                existing = db.query(JobModel).filter(JobModel.job_id == job.job_id).first()
                if existing:
                    raise ValueError(f"Job with ID '{job.job_id}' already exists.")
                if not job.operations or len(job.operations) == 0:
                    raise ValueError("Job must contain at least one operation.")

                # Validate all operations: duration > 0 and machine exists
                known_machines = {m.machine_id for m in db.query(MachineModel).all()}
                for op in job.operations:
                    if op.duration <= 0:
                        raise ValueError(f"Operation {op.sequence} ({op.name}) duration must be greater than zero. Received: {op.duration}")
                    if known_machines and op.machine_id not in known_machines:
                        raise ValueError(f"Operation {op.sequence} assigned to invalid or non-existent machine '{op.machine_id}'. Valid machines: {sorted(known_machines)}")

                job_rec = JobModel(
                    job_id=job.job_id,
                    name=job.name,
                    product_type=job.product_type,
                    quantity=job.quantity,
                    arrival_time=job.arrival_time,
                    due_date=job.due_date,
                    priority=job.priority,
                    status=job.status.value,
                    operations_json=[op.dict() for op in job.operations]
                )
                db.add(job_rec)
                ProductionStateService.increment_state_version(db)
                db.commit()
                return job
            finally:
                db.close()

    @staticmethod
    def set_machine_downtime(machine_id: str, down_duration: float = 20.0, reason: str = "Breakdown") -> Machine:
        """
        Triggers a machine breakdown or maintenance event.
        - Rejects invalid durations (< 0) or non-existent machines.
        - Rejects conflicting breakdown if the machine is already DOWN.
        - Non-preemptive policy: if the machine is currently BUSY with a running operation,
          the running operation finishes first and the downtime duration extends the machine's
          unavailable window (remaining_processing_time += down_duration) while preserving
          current_job_id/current_operation_seq so no running operation is lost.
          If IDLE, the machine transitions immediately to DOWN for down_duration.
        """
        if down_duration <= 0:
            raise ValueError("Downtime duration must be greater than zero.")
        with ProductionStateService._lock:
            db = SessionLocal()
            try:
                m = db.query(MachineModel).filter(MachineModel.machine_id == machine_id).first()
                if not m:
                    raise ValueError(f"Machine '{machine_id}' does not exist.")
                if m.status == MachineStatus.DOWN.value:
                    raise ValueError(f"Machine '{machine_id}' is already DOWN.")

                if m.status == MachineStatus.BUSY.value and m.remaining_processing_time > 1e-4:
                    # Non-preemptive: preserve running operation and append breakdown repair duration
                    m.remaining_processing_time = float(m.remaining_processing_time) + float(down_duration)
                else:
                    m.status = MachineStatus.DOWN.value
                    m.remaining_processing_time = float(down_duration)

                ProductionStateService.increment_state_version(db)
                db.commit()
                db.refresh(m)
                return Machine(
                    machine_id=m.machine_id,
                    name=m.name,
                    capability=m.capability,
                    status=MachineStatus(m.status),
                    current_job_id=m.current_job_id,
                    current_operation_seq=m.current_operation_seq,
                    remaining_processing_time=m.remaining_processing_time,
                    total_busy_time=m.total_busy_time
                )
            finally:
                db.close()

    @staticmethod
    def recover_machine(machine_id: str) -> Machine:
        """
        Recovers a DOWN or MAINTENANCE machine back to IDLE and clears remaining downtime.
        Rejects recovery if the machine is currently BUSY with a running operation.
        """
        with ProductionStateService._lock:
            db = SessionLocal()
            try:
                m = db.query(MachineModel).filter(MachineModel.machine_id == machine_id).first()
                if not m:
                    raise ValueError(f"Machine '{machine_id}' does not exist.")
                if m.status == MachineStatus.BUSY.value and m.current_job_id is not None:
                    raise ValueError(f"Cannot force-recover machine '{machine_id}' while BUSY with running job '{m.current_job_id}'.")

                m.status = MachineStatus.IDLE.value
                m.remaining_processing_time = 0.0
                m.current_job_id = None
                m.current_operation_seq = None
                ProductionStateService.increment_state_version(db)
                db.commit()
                db.refresh(m)
                return Machine(
                    machine_id=m.machine_id,
                    name=m.name,
                    capability=m.capability,
                    status=MachineStatus(m.status),
                    current_job_id=m.current_job_id,
                    current_operation_seq=m.current_operation_seq,
                    remaining_processing_time=m.remaining_processing_time,
                    total_busy_time=m.total_busy_time
                )
            finally:
                db.close()

    @staticmethod
    def recalculate_schedule(
        sim_time: float = 0.0,
        algorithm: str = "CPSAT",
        time_limit_seconds: float = 3.0,
        expected_state_version: Optional[int] = None,
        expected_sim_time: Optional[float] = None
    ) -> ScheduleResult:
        with ProductionStateService._lock:
            db_check = SessionLocal()
            try:
                sim_state = db_check.query(SimulationStateModel).filter(SimulationStateModel.id == 1).first()
                current_version = int(sim_state.state_version) if sim_state and sim_state.state_version is not None else 1
                persisted_sim_time = float(sim_state.sim_time) if sim_state and sim_state.sim_time is not None else 0.0
            finally:
                db_check.close()

            if expected_state_version is not None and expected_state_version != current_version:
                raise StaleScheduleError(
                    f"Stale schedule request rejected: expected state_version={expected_state_version}, "
                    f"current state_version={current_version}."
                )
            if expected_sim_time is not None and abs(expected_sim_time - persisted_sim_time) > 1e-4:
                raise StaleScheduleError(
                    f"Stale schedule request rejected: expected sim_time={expected_sim_time}, "
                    f"current persisted sim_time={persisted_sim_time}."
                )
            if sim_time < persisted_sim_time - 1e-4:
                raise StaleScheduleError(
                    f"Stale schedule calculation rejected: requested sim_time={sim_time} "
                    f"is behind persisted production sim_time={persisted_sim_time}."
                )

            jobs = ProductionStateService.get_all_jobs()
            machines = ProductionStateService.get_all_machines()
            
            # Validate each job has at least one operation
            for job in jobs:
                if not job.operations:
                    raise ValueError(f"Job {job.job_id} has no operations defined.")

            # Exclude completed jobs from scheduling
            jobs_to_schedule = [j for j in jobs if j.status != JobStatus.COMPLETED]

            # Normalize: CP_SAT → CPSAT etc.
            algo = algorithm.replace("_", "").upper()

            if algo == "CPSAT":
                result = CPSATSchedulingOptimizer.optimize(jobs_to_schedule, machines, current_time=sim_time, time_limit_seconds=time_limit_seconds)
            elif algo == "EPN":
                from app.ml.inference.epn_scheduler import EPNJobShopScheduler
                epn_scheduler = EPNJobShopScheduler()
                result = epn_scheduler.schedule(jobs_to_schedule, machines, current_time=sim_time)
            else:
                result = DispatchHeuristicScheduler.schedule(jobs_to_schedule, machines, current_time=sim_time, rule=algo)

            # Verify state did not change mid-solve and attach state_version
            db = SessionLocal()
            try:
                sim_state_after = db.query(SimulationStateModel).filter(SimulationStateModel.id == 1).first()
                version_after = int(sim_state_after.state_version) if sim_state_after and sim_state_after.state_version is not None else 1
                if expected_state_version is not None and version_after != expected_state_version:
                    raise StaleScheduleError(
                        f"Production state changed during schedule computation (expected {expected_state_version}, now {version_after})."
                    )
                result.explanation["state_version"] = version_after
                record = ScheduleRecordModel(
                    schedule_id=result.schedule_id,
                    algorithm=result.algorithm,
                    created_at_sim_time=result.created_at_sim_time,
                    tasks_json=[t.dict() for t in result.tasks],
                    metrics_json=result.metrics.dict(),
                    explanation_json=result.explanation
                )
                db.add(record)
                db.commit()
            finally:
                db.close()
                
            return result
