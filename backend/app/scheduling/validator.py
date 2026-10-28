from typing import List, Dict, Tuple
from app.schemas.models import ScheduledTask, ScheduleMetrics, Machine, MachineStatus

class ScheduleValidator:
    @staticmethod
    def validate(
        tasks: List[ScheduledTask],
        machines: List[Machine],
        current_time: float = 0.0
    ) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        machine_map: Dict[str, Machine] = {m.machine_id: m for m in machines}
        
        # 1. Check machine exclusivity (no two tasks on the same machine overlap)
        tasks_by_machine: Dict[str, List[ScheduledTask]] = {}
        for t in tasks:
            tasks_by_machine.setdefault(t.machine_id, []).append(t)
            
        for m_id, m_tasks in tasks_by_machine.items():
            sorted_m_tasks = sorted(m_tasks, key=lambda x: x.start_time)
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

        # 2. Check machine availability / downtime window for pending future tasks
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

        # 2. Check operation precedence per job
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
                    
        # 3. Check tasks start time consistency with current simulation time
        for t in tasks:
            if not t.is_completed and not t.is_running and t.start_time < current_time - 1e-4:
                errors.append(
                    f"Temporal Anomaly: Future Task {t.job_id}-Op{t.operation_sequence} "
                    f"starts at {t.start_time:.1f} which is prior to current_time {current_time:.1f}"
                )
                
        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def calculate_metrics(
        tasks: List[ScheduledTask],
        jobs_due_dates: Dict[str, float],
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
                avg_waiting_time=0.0,
                max_waiting_time=0.0,
                machine_utilization={m: 0.0 for m in machine_ids},
                avg_utilization=0.0,
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
            due = jobs_due_dates.get(j_id, c_j)
            arrival = jobs_arrival_times.get(j_id, 0.0)
            tardiness = max(0.0, c_j - due)
            if tardiness > 1e-4:
                late_jobs_count += 1
            total_tardiness += tardiness
            max_tardiness = max(max_tardiness, tardiness)
            
            # Flow time - total processing = waiting time
            total_proc = job_processing_times.get(j_id, 0.0)
            flow_time = max(0.0, c_j - arrival)
            waiting_time = max(0.0, flow_time - total_proc)
            waiting_times.append(waiting_time)
            
        avg_waiting = sum(waiting_times) / len(waiting_times) if waiting_times else 0.0
        max_waiting = max(waiting_times, default=0.0)
        
        # Machine utilization
        m_busy: Dict[str, float] = {m: 0.0 for m in machine_ids}
        for t in tasks:
            if t.machine_id in m_busy:
                m_busy[t.machine_id] += t.duration
                
        utilization = {}
        for m in machine_ids:
            utilization[m] = round((m_busy[m] / makespan) * 100.0, 1) if makespan > 0 else 0.0
            
        avg_util = sum(utilization.values()) / len(utilization) if utilization else 0.0
        
        return ScheduleMetrics(
            makespan=round(makespan, 2),
            total_tardiness=round(total_tardiness, 2),
            max_tardiness=round(max_tardiness, 2),
            late_jobs_count=late_jobs_count,
            avg_waiting_time=round(avg_waiting, 2),
            max_waiting_time=round(max_waiting, 2),
            machine_utilization=utilization,
            avg_utilization=round(avg_util, 1),
            computation_time_ms=round(computation_time_ms, 2),
            solver_status=solver_status
        )
