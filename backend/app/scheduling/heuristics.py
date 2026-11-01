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
        machine_intervals: Dict[str, List[Tuple[float, float]]] = {m.machine_id: [] for m in machines}
        
        # Machine state baseline
        for m in machines:
            if m.status in (MachineStatus.DOWN, MachineStatus.MAINTENANCE):
                # Unavailable until recovery or current_time + remaining downtime
                downtime_rem = m.remaining_processing_time if m.remaining_processing_time > 1e-4 else 1e6
                free_at = current_time + downtime_rem
                machine_free_time[m.machine_id] = free_at
                machine_intervals[m.machine_id].append((current_time, free_at))
            elif m.status == MachineStatus.BUSY:
                # Locked until current_time + remaining processing time
                free_at = current_time + m.remaining_processing_time
                machine_free_time[m.machine_id] = free_at
                if m.remaining_processing_time > 1e-4:
                    machine_intervals[m.machine_id].append((current_time, free_at))
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
                    run_m_id = op.assigned_machine_id or op.machine_id
                    m_obj = next((m for m in machines if m.machine_id == run_m_id), None)
                    rem_t = m_obj.remaining_processing_time if (m_obj and m_obj.remaining_processing_time > 1e-4) else op.duration
                    end_t = current_time + rem_t
                    scheduled_tasks.append(
                        ScheduledTask(
                            job_id=j.job_id,
                            job_name=j.name,
                            operation_sequence=op.sequence,
                            operation_name=op.name,
                            machine_id=run_m_id,
                            start_time=start_t,
                            end_time=round(end_t, 2),
                            duration=op.duration,
                            is_running=True
                        )
                    )
                    machine_free_time[run_m_id] = max(machine_free_time.get(run_m_id, current_time), end_t)
                    machine_intervals.setdefault(run_m_id, []).append((start_t, end_t))
                    latest_comp = max(latest_comp, end_t)
                    next_idx = idx + 1
                    break
            job_next_op_idx[j.job_id] = next_idx
            job_ready_time[j.job_id] = max(latest_comp, current_time)

        def _earliest_feasible_start(m_id: str, min_ready: float, duration: float) -> float:
            """
            Active-schedule gap insertion: finds the earliest time >= max(current_time, min_ready)
            on machine m_id where [cand, cand + duration] does not overlap any existing commitment.
            """
            cand = max(current_time, min_ready)
            intervals = sorted(machine_intervals.get(m_id, []), key=lambda x: (x[0], x[1]))
            for iv_s, iv_e in intervals:
                if cand + duration <= iv_s + 1e-6:
                    return cand
                if cand < iv_e:
                    cand = iv_e
            return cand

        # 2. Active-schedule forward-pass dispatching remaining operations
        all_machine_ids = {m.machine_id for m in machines}
        while True:
            # Gather all eligible pending operations
            candidate_ops: List[Tuple[Job, int, float, str]] = [] # (job, op_index, candidate_start_time, chosen_machine_id)
            for j_id, idx in job_next_op_idx.items():
                j = job_map[j_id]
                if idx < len(j.operations):
                    op = j.operations[idx]
                    eligible_m = [op.machine_id] + [
                        alt for alt in (op.alternative_machines or [])
                        if alt in all_machine_ids and alt != op.machine_id
                    ]
                    best_m = eligible_m[0]
                    best_start = _earliest_feasible_start(best_m, job_ready_time[j_id], op.duration)
                    for cand_m in eligible_m[1:]:
                        cand_start = _earliest_feasible_start(cand_m, job_ready_time[j_id], op.duration)
                        if cand_start < best_start - 1e-6:
                            best_start = cand_start
                            best_m = cand_m
                    candidate_ops.append((j, idx, best_start, best_m))
                    
            if not candidate_ops:
                break # All operations scheduled

            # Active-schedule Giffler-Thompson frontier:
            # Let min_completion be the earliest possible completion time among all ready candidate operations.
            # Any candidate whose earliest start is < min_completion is in the active frontier (0);
            # unready future operations with est_start >= min_completion (1) cannot block an available machine.
            min_completion = min(est_start + j.operations[idx].duration for j, idx, est_start, _ in candidate_ops)
                
            # Sort candidate operations according to the chosen dispatch rule within the active frontier
            def get_sort_key(item: Tuple[Job, int, float, str]):
                j, idx, est_start, _ = item
                op = j.operations[idx]
                in_active_frontier = 0 if est_start < min_completion - 1e-6 else 1
                rem_work = sum(o.duration for o in j.operations[idx:])
                has_due = j.due_date is not None and j.due_date > 0
                waiting_so_far = max(0.0, est_start - j.arrival_time)
                prio = getattr(j, "priority", 3) or 3
                
                r_upper = rule.upper()
                if r_upper == "FCFS":
                    return (in_active_frontier, j.arrival_time, -prio, op.duration, est_start, j.job_id)
                elif r_upper == "SPT":
                    due_tie = j.due_date if has_due else float("inf")
                    return (in_active_frontier, op.duration, -prio, due_tie, j.arrival_time, est_start, j.job_id)
                elif r_upper == "EDD":
                    # Agreed policy: if valid due dates are available, use EDD;
                    # if due date is unavailable, fallback deterministically to SPT, with anti-starvation aging promotion.
                    if has_due:
                        return (in_active_frontier, 0, float(j.due_date), -prio, -waiting_so_far, op.duration, est_start, j.job_id)
                    elif waiting_so_far >= 60.0:
                        # Prevent starvation of undated jobs after extended waiting
                        eff_due = est_start + rem_work
                        return (in_active_frontier, 0, eff_due, -prio, -waiting_so_far, op.duration, est_start, j.job_id)
                    else:
                        return (in_active_frontier, 1, op.duration, -prio, -waiting_so_far, j.arrival_time, est_start, j.job_id)
                elif r_upper == "CR":
                    if has_due:
                        time_until_due = float(j.due_date) - est_start
                        cr = (time_until_due / rem_work) if rem_work > 0 else 0.0
                        return (in_active_frontier, 0, cr, -prio, -waiting_so_far, op.duration, est_start, j.job_id)
                    else:
                        return (in_active_frontier, 1, op.duration, -prio, -waiting_so_far, j.arrival_time, est_start, j.job_id)
                elif r_upper == "AGING":
                    # Priority score: Higher waiting & tighter slack gets scheduled earlier (negated for ascending sort)
                    # Priority acts as a tie-breaker / bonus without drowning out earlier arrivals
                    if has_due:
                        time_until_due = float(j.due_date) - est_start
                        slack = time_until_due - rem_work
                        score = (1.5 * waiting_so_far) - (0.8 * slack) - (0.2 * op.duration) + (0.01 * prio)
                    else:
                        score = (1.5 * waiting_so_far) - (0.5 * op.duration) + (0.01 * prio)
                    return (in_active_frontier, -score, -prio, est_start, j.job_id)
                else:
                    return (in_active_frontier, est_start, -prio, j.arrival_time, j.job_id)

            candidate_ops.sort(key=get_sort_key)
            
            # Dispatch top candidate using gap-inserted start time
            chosen_job, chosen_idx, est_start, m_id = candidate_ops[0]
            chosen_op = chosen_job.operations[chosen_idx]
            
            actual_start = _earliest_feasible_start(m_id, job_ready_time[chosen_job.job_id], chosen_op.duration)
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
            machine_intervals.setdefault(m_id, []).append((actual_start, actual_end))
            machine_free_time[m_id] = max(machine_free_time.get(m_id, current_time), actual_end)
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
