from typing import List, Dict, Tuple, Optional
from app.schemas.models import ScheduledTask, ScheduleMetrics, Machine, MachineStatus, Job, OperationStatus, JobStatus

class ScheduleValidator:
    @staticmethod
    def validate(
        tasks: List[ScheduledTask],
        machines: List[Machine],
        current_time: float = 0.0,
        jobs: Optional[List[Job]] = None,
        check_active_schedule: bool = True
    ) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        machine_map: Dict[str, Machine] = {m.machine_id: m for m in machines}
        
        # 1. Check machine exclusivity (no two tasks on the same machine overlap)
        tasks_by_machine: Dict[str, List[ScheduledTask]] = {}
        for t in tasks:
            if machine_map and t.machine_id not in machine_map:
                errors.append(
                    f"Unknown Machine Violation: Task {t.job_id}-Op{t.operation_sequence} "
                    f"assigned to unknown machine '{t.machine_id}'"
                )
            tasks_by_machine.setdefault(t.machine_id, []).append(t)
            
        for m_id, m_tasks in tasks_by_machine.items():
            sorted_m_tasks = sorted(m_tasks, key=lambda x: (x.start_time, x.end_time))
            for i in range(len(sorted_m_tasks) - 1):
                t1 = sorted_m_tasks[i]
                t2 = sorted_m_tasks[i + 1]
                # If t2 starts before t1 ends (beyond negligible numerical tolerance 1e-4)
                if t2.start_time < t1.end_time - 1e-4:
                    errors.append(
                        f"Machine Exclusivity Violation on {m_id}: "
                        f"Task {t1.job_id}-Op{t1.operation_sequence} [{t1.start_time:.1f}-{t1.end_time:.1f}] "
                        f"overlaps with {t2.job_id}-Op{t2.operation_sequence} [{t2.start_time:.1f}-{t2.end_time:.1f}]"
                    )

        # 2. Check machine availability / downtime window and BUSY lock for pending future tasks
        for t in tasks:
            if not t.is_completed and not t.is_running:
                m = machine_map.get(t.machine_id)
                if m and m.status in (MachineStatus.DOWN, MachineStatus.MAINTENANCE):
                    down_until = current_time + (m.remaining_processing_time if m.remaining_processing_time > 1e-4 else 1e6)
                    if t.start_time < down_until - 1e-4:
                        errors.append(
                            f"Machine Downtime Violation on {t.machine_id}: "
                            f"Pending Task {t.job_id}-Op{t.operation_sequence} scheduled at {t.start_time:.1f} "
                            f"while machine is {m.status.value} until {down_until:.1f}"
                        )
                elif m and m.status == MachineStatus.BUSY and m.remaining_processing_time > 1e-4:
                    busy_until = current_time + m.remaining_processing_time
                    if t.start_time < busy_until - 1e-4:
                        errors.append(
                            f"Busy Machine Lock Violation on {t.machine_id}: "
                            f"Pending Task {t.job_id}-Op{t.operation_sequence} scheduled at {t.start_time:.1f} "
                            f"while machine is BUSY until {busy_until:.1f}"
                        )

        # 3. Check duration and interval consistency
        seen_job_ops = set()
        for t in tasks:
            op_key = (t.job_id, t.operation_sequence)
            if op_key in seen_job_ops:
                errors.append(
                    f"Duplicate Operation Violation: Task {t.job_id}-Op{t.operation_sequence} "
                    f"appears multiple times in the schedule"
                )
            seen_job_ops.add(op_key)

            if t.duration <= 0 or t.end_time < t.start_time - 1e-4:
                errors.append(
                    f"Duration Consistency Violation in {t.job_id}-Op{t.operation_sequence}: "
                    f"Invalid duration ({t.duration:.2f}) or negative interval [{t.start_time:.2f}-{t.end_time:.2f}]"
                )
            elif not t.is_running and abs((t.end_time - t.start_time) - t.duration) > 1e-1:
                errors.append(
                    f"Duration Mismatch Violation in {t.job_id}-Op{t.operation_sequence}: "
                    f"end_time - start_time ({t.end_time - t.start_time:.2f}) != duration ({t.duration:.2f})"
                )

        # 4. Check operation precedence per job
        tasks_by_job: Dict[str, List[ScheduledTask]] = {}
        for t in tasks:
            tasks_by_job.setdefault(t.job_id, []).append(t)
            
        for j_id, j_tasks in tasks_by_job.items():
            sorted_j_tasks = sorted(j_tasks, key=lambda x: x.operation_sequence)
            for i in range(len(sorted_j_tasks) - 1):
                op_prev = sorted_j_tasks[i]
                op_curr = sorted_j_tasks[i + 1]
                if op_curr.start_time < op_prev.end_time - 1e-4:
                    errors.append(
                        f"Precedence Violation in Job {j_id}: "
                        f"Op{op_curr.operation_sequence} starts at {op_curr.start_time:.1f} before "
                        f"Op{op_prev.operation_sequence} finishes at {op_prev.end_time:.1f}"
                    )
                    
        # 5. Check tasks start time consistency with current simulation time
        for t in tasks:
            if not t.is_completed and not t.is_running and t.start_time < current_time - 1e-4:
                errors.append(
                    f"Temporal Anomaly: Future Task {t.job_id}-Op{t.operation_sequence} "
                    f"starts at {t.start_time:.1f} which is prior to current_time {current_time:.1f}"
                )

        # 6. Extended job-level checks (real op correspondence, eligibility, release time, running lock, active schedule)
        if jobs is not None:
            job_map: Dict[str, Job] = {j.job_id: j for j in jobs}
            op_lookup: Dict[Tuple[str, int], Tuple[Job, any]] = {}
            for j in jobs:
                seen_seqs = set()
                prev_seq = 0
                for op in j.operations:
                    if op.sequence <= 0 or op.sequence in seen_seqs or op.sequence <= prev_seq:
                        errors.append(
                            f"Dependency Cycle / Sequence Violation in Job {j.job_id}: "
                            f"Invalid or non-increasing operation sequence {op.sequence}"
                        )
                    seen_seqs.add(op.sequence)
                    prev_seq = op.sequence
                    op_lookup[(j.job_id, op.sequence)] = (j, op)

                    # Verify running operations are preserved in schedule
                    if j.status != JobStatus.COMPLETED and op.status == OperationStatus.RUNNING:
                        matching_running = [
                            t for t in tasks
                            if t.job_id == j.job_id and t.operation_sequence == op.sequence and t.is_running
                        ]
                        if not matching_running:
                            errors.append(
                                f"Running Operation Preservation Violation: "
                                f"Job {j.job_id}-Op{op.sequence} is RUNNING on {op.machine_id} but missing or not marked running in schedule"
                            )

            for t in tasks:
                key = (t.job_id, t.operation_sequence)
                if key not in op_lookup:
                    errors.append(
                        f"Invented Operation Violation: ScheduledTask {t.job_id}-Op{t.operation_sequence} "
                        f"does not correspond to any real job operation"
                    )
                    continue
                j_obj, op_obj = op_lookup[key]
                eligible_machines = [op_obj.machine_id] + list(op_obj.alternative_machines or [])
                if not t.is_completed and t.machine_id not in eligible_machines:
                    errors.append(
                        f"Machine Eligibility Violation: Task {t.job_id}-Op{t.operation_sequence} "
                        f"assigned to '{t.machine_id}', but eligible machines are {eligible_machines}"
                    )
                if not t.is_completed and not t.is_running and t.start_time < j_obj.arrival_time - 1e-4:
                    errors.append(
                        f"Release Time Violation: Task {t.job_id}-Op{t.operation_sequence} "
                        f"starts at {t.start_time:.1f} before job arrival_time {j_obj.arrival_time:.1f}"
                    )

            # Active-schedule avoidable idle time check
            if check_active_schedule:
                # Build occupied intervals per machine from locked busy/down windows and all scheduled tasks
                occupied_by_machine: Dict[str, List[Tuple[float, float, Optional[Tuple[str, int]]]]] = {
                    m.machine_id: [] for m in machines
                }
                for m in machines:
                    if m.status == MachineStatus.BUSY and m.remaining_processing_time > 1e-4:
                        occupied_by_machine[m.machine_id].append(
                            (current_time, current_time + m.remaining_processing_time, None)
                        )
                    elif m.status in (MachineStatus.DOWN, MachineStatus.MAINTENANCE):
                        down_rem = m.remaining_processing_time if m.remaining_processing_time > 1e-4 else 1e6
                        occupied_by_machine[m.machine_id].append(
                            (current_time, current_time + down_rem, None)
                        )
                for t in tasks:
                    occupied_by_machine.setdefault(t.machine_id, []).append(
                        (t.start_time, t.end_time, (t.job_id, t.operation_sequence))
                    )

                for j_id, j_tasks in tasks_by_job.items():
                    if j_id not in job_map:
                        continue
                    j_obj = job_map[j_id]
                    sorted_j_tasks = sorted(j_tasks, key=lambda x: x.operation_sequence)
                    prev_end = max(current_time, j_obj.arrival_time)
                    for t in sorted_j_tasks:
                        if t.is_completed or t.is_running:
                            prev_end = max(prev_end, t.end_time)
                            continue
                        ready_t = max(current_time, j_obj.arrival_time, prev_end)
                        # Check if t.machine_id is completely idle in [ready_t, ready_t + t.duration]
                        if t.start_time > ready_t + 1e-4:
                            m_intervals = [
                                (iv_s, iv_e)
                                for iv_s, iv_e, iv_key in occupied_by_machine.get(t.machine_id, [])
                                if iv_key != (t.job_id, t.operation_sequence)
                            ]
                            has_conflict = any(
                                not (ready_t + t.duration <= iv_s + 1e-4 or ready_t >= iv_e - 1e-4)
                                for iv_s, iv_e in m_intervals
                            )
                            if not has_conflict:
                                errors.append(
                                    f"Avoidable Machine Idle Violation on {t.machine_id}: "
                                    f"Task {t.job_id}-Op{t.operation_sequence} is ready at {ready_t:.1f} "
                                    f"(duration {t.duration:.1f}m) and {t.machine_id} is idle in "
                                    f"[{ready_t:.1f}, {ready_t + t.duration:.1f}], but task was delayed until {t.start_time:.1f}"
                                )
                        prev_end = max(prev_end, t.end_time)
                
        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def calculate_metrics(
        tasks: List[ScheduledTask],
        jobs_due_dates: Dict[str, Optional[float]],
        jobs_arrival_times: Dict[str, float],
        machine_ids: List[str],
        computation_time_ms: float = 0.0,
        solver_status: str = "FEASIBLE"
    ) -> ScheduleMetrics:
        if not tasks:
            return ScheduleMetrics(
                makespan=0.0,
                total_tardiness=0.0,
                max_tardiness=0.0,
                late_jobs_count=0,
                total_waiting_time=0.0,
                avg_waiting_time=0.0,
                max_waiting_time=0.0,
                machine_utilization={m: 0.0 for m in machine_ids},
                machine_idle_time={m: 0.0 for m in machine_ids},
                avg_utilization=0.0,
                throughput=0.0,
                queue_length=0,
                computation_time_ms=computation_time_ms,
                solver_status=solver_status
            )
            
        makespan = max((t.end_time for t in tasks), default=0.0)
        
        # Job completions
        job_completions: Dict[str, float] = {}
        job_processing_times: Dict[str, float] = {}
        for t in tasks:
            job_completions[t.job_id] = max(job_completions.get(t.job_id, 0.0), t.end_time)
            job_processing_times[t.job_id] = job_processing_times.get(t.job_id, 0.0) + t.duration
            
        total_tardiness = 0.0
        max_tardiness = 0.0
        late_jobs_count = 0
        waiting_times: List[float] = []
        
        for j_id, c_j in job_completions.items():
            due = jobs_due_dates.get(j_id)
            arrival = jobs_arrival_times.get(j_id, 0.0)
            if due is not None and due > 0:
                tardiness = max(0.0, c_j - due)
            else:
                tardiness = 0.0
            if tardiness > 1e-4:
                late_jobs_count += 1
            total_tardiness += tardiness
            max_tardiness = max(max_tardiness, tardiness)
            
            # Flow time - total processing = waiting time
            total_proc = job_processing_times.get(j_id, 0.0)
            flow_time = max(0.0, c_j - arrival)
            waiting_time = max(0.0, flow_time - total_proc)
            waiting_times.append(waiting_time)
            
        total_waiting = sum(waiting_times)
        avg_waiting = total_waiting / len(waiting_times) if waiting_times else 0.0
        max_waiting = max(waiting_times, default=0.0)
        
        # Machine utilization and idle time
        m_busy: Dict[str, float] = {m: 0.0 for m in machine_ids}
        for t in tasks:
            if t.machine_id in m_busy:
                m_busy[t.machine_id] += t.duration
                
        utilization = {}
        idle_time = {}
        for m in machine_ids:
            utilization[m] = round((m_busy[m] / makespan) * 100.0, 1) if makespan > 0 else 0.0
            idle_time[m] = round(max(0.0, makespan - m_busy[m]), 2) if makespan > 0 else 0.0
            
        avg_util = sum(utilization.values()) / len(utilization) if utilization else 0.0
        num_jobs_scheduled = len(job_completions)
        throughput = round((num_jobs_scheduled / makespan) * 60.0, 2) if makespan > 0 else 0.0
        pending_queue_len = sum(1 for t in tasks if not t.is_completed and not t.is_running)
        
        return ScheduleMetrics(
            makespan=round(makespan, 2),
            total_tardiness=round(total_tardiness, 2),
            max_tardiness=round(max_tardiness, 2),
            late_jobs_count=late_jobs_count,
            total_waiting_time=round(total_waiting, 2),
            avg_waiting_time=round(avg_waiting, 2),
            max_waiting_time=round(max_waiting, 2),
            machine_utilization=utilization,
            machine_idle_time=idle_time,
            avg_utilization=round(avg_util, 1),
            throughput=throughput,
            queue_length=pending_queue_len,
            computation_time_ms=round(computation_time_ms, 2),
            solver_status=solver_status
        )
