from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class MachineStatus(str, Enum):
    IDLE = "IDLE"
    BUSY = "BUSY"
    SETUP = "SETUP"
    MAINTENANCE = "MAINTENANCE"
    DOWN = "DOWN"
    BLOCKED = "BLOCKED"

class JobStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    DELAYED = "DELAYED"

class OperationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"

class Operation(BaseModel):
    sequence: int
    name: str
    machine_id: str
    duration: float = Field(gt=0.0, description="Processing duration in minutes must be greater than zero")
    setup_time: float = 0.0
    alternative_machines: List[str] = Field(default_factory=list)
    status: OperationStatus = OperationStatus.PENDING
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    assigned_machine_id: Optional[str] = None

class Job(BaseModel):
    job_id: str
    name: str
    product_type: str
    quantity: int = 1
    arrival_time: float = 0.0
    due_date: float
    priority: int = 3
    operations: List[Operation]
    status: JobStatus = JobStatus.PENDING
    predicted_completion_time: Optional[float] = None
    actual_completion_time: Optional[float] = None

class Machine(BaseModel):
    machine_id: str
    name: str
    capability: str
    status: MachineStatus = MachineStatus.IDLE
    current_job_id: Optional[str] = None
    current_operation_seq: Optional[int] = None
    current_operation_start: Optional[float] = None
    remaining_processing_time: float = 0.0
    total_busy_time: float = 0.0

class ScheduledTask(BaseModel):
    job_id: str
    job_name: str
    operation_sequence: int
    operation_name: str
    machine_id: str
    start_time: float
    end_time: float
    duration: float
    is_running: bool = False
    is_completed: bool = False

class ScheduleMetrics(BaseModel):
    makespan: float
    total_tardiness: float
    max_tardiness: float
    late_jobs_count: int
    avg_waiting_time: float
    max_waiting_time: float
    machine_utilization: Dict[str, float]
    avg_utilization: float
    computation_time_ms: float
    solver_status: str

class ScheduleResult(BaseModel):
    schedule_id: str
    algorithm: str
    created_at_sim_time: float
    tasks: List[ScheduledTask]
    metrics: ScheduleMetrics
    explanation: Dict[str, Any] = Field(default_factory=dict)
