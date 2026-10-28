import json
from typing import List, Dict, Any, Optional
from app.database.db import SessionLocal, init_db, JobModel, MachineModel, ScheduleRecordModel
from app.schemas.models import Job, Machine, ScheduleResult, Operation, OperationStatus, MachineStatus, JobStatus
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer

class ProductionStateService:
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
            # Clear all current jobs and reset machines to IDLE
            db.query(JobModel).delete()
            machines = db.query(MachineModel).all()
            for m in machines:
                m.status = MachineStatus.IDLE.value
                m.current_job_id = None
                m.current_operation_seq = None
                m.remaining_processing_time = 0.0
                m.total_busy_time = 0.0

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
            db.commit()
            return job
        finally:
            db.close()

    @staticmethod
    def recalculate_schedule(sim_time: float = 0.0, algorithm: str = "CPSAT", time_limit_seconds: float = 3.0) -> ScheduleResult:
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

        # Save result to DB
        db = SessionLocal()
        try:
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
