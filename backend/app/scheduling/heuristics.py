import time
import uuid
from typing import List, Dict, Tuple, Optional
from app.schemas.models import Job, Machine, ScheduledTask, ScheduleResult, OperationStatus, MachineStatus
from app.scheduling.validator import ScheduleValidator

class DispatchHeuristicScheduler:
    """
    Simulates dynamic dispatching rules for Job Shop Scheduling:
    - FCFS: First Come, First Served
    - SPT: Shortest Processing Time
    - EDD: Earliest Due Date
    - CR: Critical Ratio (Slack / Remaining Processing Time)
    - AGING: Waiting Time Priority (Combines wait time + urgency to prevent starvation)
    """

    @classmethod
    def schedule(
        cls,
        jobs: List[Job],
        machines: List[Machine],
        current_time: float,
        rule: str = "FCFS"
    ) -> ScheduleResult:
        start_cpu = time.perf_counter()
        
        # 1. Capture locked state of running & completed operations
        scheduled_tasks: List[ScheduledTask] = []
        machine_free_time: Dict[str, float] = {}
        
        # Machine state baseline
        for m in machines:
            if m.status in (MachineStatus.DOWN, MachineStatus.MAINTENANCE):
                # Unavailable until recovery or current_time + remaining downtime
                downtime_rem = m.remaining_processing_time if m.remaining_processing_time > 1e-4 else 1e6
                machine_free_time[m.machine_id] = current_time + downtime_rem
            elif m.status == MachineStatus.BUSY:
                # Locked until current_time + remaining processing time
                machine_free_time[m.machine_id] = current_time + m.remaining_processing_time
            else:
                machine_free_time[m.machine_id] = current_time
                
        # Job state tracking
        job_next_op_idx: Dict[str, int] = {}
        job_ready_time: Dict[str, float] = {}
        job_map: Dict[str, Job] = {j.job_id: j for j in jobs}
        
        for j in jobs:
            next_idx = 0
            latest_comp = j.arrival_time
            for idx, op in enumerate(j.operations):
                if op.status == OperationStatus.COMPLETED:
                    if op.end_time is not None:
                        latest_comp = max(latest_comp, op.end_time)
                        scheduled_tasks.append(
                            ScheduledTask(
                                job_id=j.job_id,
                                job_name=j.name,
                                operation_sequence=op.sequence,
                                operation_name=op.name,
                                machine_id=op.assigned_machine_id or op.machine_id,
                                start_time=op.start_time or 0.0,
                                end_time=op.end_time or 0.0,
                                duration=op.duration,
                                is_completed=True
                            )
                        )
                    next_idx = idx + 1
                elif op.status == OperationStatus.RUNNING:
                    start_t = op.start_time or current_time
                    m_obj = next((m for m in machines if m.machine_id == op.machine_id), None)
                    rem_t = m_obj.remaining_processing_time if m_obj else op.duration
                    end_t = current_time + rem_t
                    scheduled_tasks.append(
                        ScheduledTask(
                            job_id=j.job_id,
                            job_name=j.name,
                            operation_sequence=op.sequence,
                            operation_name=op.name,
                            machine_id=op.machine_id,
                            start_time=start_t,
                            end_time=end_t,
                            duration=op.duration,
                            is_running=True
                        )
                    )
                    machine_free_time[op.machine_id] = max(machine_free_time.get(op.machine_id, current_time), end_t)
                    latest_comp = max(latest_comp, end_t)
                    next_idx = idx + 1
                    break
            job_next_op_idx[j.job_id] = next_idx
            job_ready_time[j.job_id] = max(latest_comp, current_time)

        # 2. Simulation forward-pass dispatching remaining operations
        all_machine_ids = {m.machine_id for m in machines}
        while True:
            # Gather all eligible pending operations
            candidate_ops: List[Tuple[Job, int, float, str]] = [] # (job, op_index, candidate_start_time, chosen_machine_id)
            for j_id, idx in job_next_op_idx.items():
                j = job_map[j_id]
                if idx < len(j.operations):
                    op = j.operations[idx]
                    eligible_m = [op.machine_id] + [alt for alt in op.alternative_machines if alt in all_machine_ids]
                    best_m = op.machine_id
                    best_start = max(job_ready_time[j_id], machine_free_time.get(best_m, current_time))
                    for cand_m in eligible_m:
                        cand_start = max(job_ready_time[j_id], machine_free_time.get(cand_m, current_time))
                        if cand_start < best_start:
                            best_start = cand_start
                            best_m = cand_m
                    candidate_ops.append((j, idx, best_start, best_m))
                    
            if not candidate_ops:
                break # All operations scheduled
                
            # Sort candidate operations according to the chosen dispatch rule
            def get_sort_key(item: Tuple[Job, int, float, str]):
                j, idx, est_start, _ = item
                op = j.operations[idx]
                rem_work = sum(o.duration for o in j.operations[idx:])
                time_until_due = j.due_date - est_start
                waiting_so_far = max(0.0, est_start - j.arrival_time)
                
                if rule.upper() == "FCFS":
                    return (j.arrival_time, est_start)
                elif rule.upper() == "SPT":
                    return (op.duration, est_start)
                elif rule.upper() == "EDD":
                    return (j.due_date, est_start)
                elif rule.upper() == "CR":
                    # Critical Ratio = (Due Date - Now) / Remaining Work
                    cr = (time_until_due / rem_work) if rem_work > 0 else 0.0
                    return (cr, est_start)
                elif rule.upper() == "AGING":
                    # Priority score: Higher waiting & tighter slack gets scheduled earlier (negated for ascending sort)
                    slack = time_until_due - rem_work
                    score = (1.5 * waiting_so_far) - (0.8 * slack) - (0.2 * op.duration)
                    return (-score, est_start)
                else:
                    return (est_start, j.arrival_time)

            candidate_ops.sort(key=get_sort_key)
            
            # Dispatch top candidate
            chosen_job, chosen_idx, _, m_id = candidate_ops[0]
            chosen_op = chosen_job.operations[chosen_idx]
            
            actual_start = max(job_ready_time[chosen_job.job_id], machine_free_time[m_id])
            actual_end = actual_start + chosen_op.duration
            
            scheduled_tasks.append(
                ScheduledTask(
                    job_id=chosen_job.job_id,
                    job_name=chosen_job.name,
                    operation_sequence=chosen_op.sequence,
                    operation_name=chosen_op.name,
                    machine_id=m_id,
                    start_time=round(actual_start, 2),
                    end_time=round(actual_end, 2),
                    duration=chosen_op.duration,
                    is_running=False,
                    is_completed=False
                )
            )
            
            # Update states
            machine_free_time[m_id] = actual_end
            job_ready_time[chosen_job.job_id] = actual_end
            job_next_op_idx[chosen_job.job_id] += 1

        duration_ms = (time.perf_counter() - start_cpu) * 1000.0
        
        # Calculate metrics
        due_dates = {j.job_id: j.due_date for j in jobs}
        arrivals = {j.job_id: j.arrival_time for j in jobs}
        machine_ids = [m.machine_id for m in machines]
        
        metrics = ScheduleValidator.calculate_metrics(
            tasks=scheduled_tasks,
            jobs_due_dates=due_dates,
            jobs_arrival_times=arrivals,
            machine_ids=machine_ids,
            computation_time_ms=duration_ms,
            solver_status="FEASIBLE"
        )
        
        return ScheduleResult(
            schedule_id=f"SCHED-{rule.upper()}-{uuid.uuid4().hex[:8]}",
            algorithm=rule.upper(),
            created_at_sim_time=current_time,
            tasks=scheduled_tasks,
            metrics=metrics,
            explanation={
                "strategy": rule.upper(),
                "reason": f"Dispatched based on {rule.upper()} criterion with dynamic non-overlapping constraints."
            }
        )
