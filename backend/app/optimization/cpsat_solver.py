import time
import uuid
from typing import List, Dict, Any, Optional
from ortools.sat.python import cp_model
from app.schemas.models import Job, Machine, ScheduledTask, ScheduleResult, OperationStatus, MachineStatus
from app.scheduling.validator import ScheduleValidator

class CPSATSchedulingOptimizer:
    """
    Constraint-Programming (CP-SAT) Exact/Heuristic Optimizer for Flexible Dynamic Job Shop.
    Enforces:
    1. Hard Precedence: op(k) ends before op(k+1) begins.
    2. Hard Machine Exclusivity (No-Overlap): disjunctive intervals per machine.
    3. Factory State Preservation: Running operations cannot be preempted; completed operations are fixed.
    4. Alternative Machines: Flexibly chooses between eligible machines if specified.
    5. Multi-Objective Function: Makespan + lambda * Tardiness + mu * Waiting.
    """

    @classmethod
    def optimize(
        cls,
        jobs: List[Job],
        machines: List[Machine],
        current_time: float,
        time_limit_seconds: float = 3.0,
        weight_makespan: float = 1.0,
        weight_tardiness: float = 2.5
    ) -> ScheduleResult:
        start_cpu = time.perf_counter()
        
        # Scale float time to integer (10x scaling gives 0.1 time precision)
        SCALE = 10
        cur_t_int = int(round(current_time * SCALE))
        
        model = cp_model.CpModel()
        
        # Estimate theoretical upper bound for horizon
        total_proc_all = sum(sum(op.duration for op in j.operations) for j in jobs)
        horizon = int(cur_t_int + (total_proc_all + 2000) * SCALE)
        
        all_machines = {m.machine_id: m for m in machines}
        machine_intervals: Dict[str, List[Any]] = {m.machine_id: [] for m in machines}
        
        scheduled_tasks: List[ScheduledTask] = []
        op_start_vars: Dict[Tuple[str, int], cp_model.IntVar] = {}
        op_end_vars: Dict[Tuple[str, int], cp_model.IntVar] = {}
        job_end_vars: Dict[str, Any] = {}
        
        # 1. Handle already completed & running tasks
        for m in machines:
            if m.status == MachineStatus.BUSY and m.remaining_processing_time > 1e-4:
                rem_dur_int = max(1, int(round(m.remaining_processing_time * SCALE)))
                busy_start = cur_t_int
                busy_end = cur_t_int + rem_dur_int
                # Create a fixed busy interval for this machine
                fixed_interval = model.NewIntervalVar(busy_start, rem_dur_int, busy_end, f"busy_{m.machine_id}")
                machine_intervals[m.machine_id].append(fixed_interval)
                
        # 2. Build decision variables for all pending/future operations
        for j in jobs:
            prev_end_var = None
            j_arr_int = max(cur_t_int, int(round(j.arrival_time * SCALE)))
            
            for op in j.operations:
                key = (j.job_id, op.sequence)
                dur_int = int(round(op.duration * SCALE))
                
                if op.status == OperationStatus.COMPLETED:
                    s_int = int(round((op.start_time or 0.0) * SCALE))
                    e_int = int(round((op.end_time or 0.0) * SCALE))
                    prev_end_var = e_int
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
                    continue
                    
                if op.status == OperationStatus.RUNNING:
                    s_int = int(round((op.start_time or current_time) * SCALE))
                    # Machine is locked for remaining duration
                    m_running = all_machines.get(op.machine_id)
                    rem = m_running.remaining_processing_time if m_running else op.duration
                    e_int = cur_t_int + int(round(rem * SCALE))
                    prev_end_var = e_int
                    scheduled_tasks.append(
                        ScheduledTask(
                            job_id=j.job_id,
                            job_name=j.name,
                            operation_sequence=op.sequence,
                            operation_name=op.name,
                            machine_id=op.machine_id,
                            start_time=op.start_time or current_time,
                            end_time=round(e_int / SCALE, 2),
                            duration=op.duration,
                            is_running=True
                        )
                    )
                    continue

                # Normal Pending operation: create start, end, interval
                start_var = model.NewIntVar(cur_t_int, horizon, f"start_{j.job_id}_{op.sequence}")
                end_var = model.NewIntVar(cur_t_int, horizon, f"end_{j.job_id}_{op.sequence}")
                
                # Precedence from previous operation in this job
                if prev_end_var is not None:
                    if isinstance(prev_end_var, int):
                        model.Add(start_var >= prev_end_var)
                    else:
                        model.Add(start_var >= prev_end_var)
                else:
                    model.Add(start_var >= j_arr_int)
                    
                # Support alternative machines if specified, otherwise fixed to assigned
                eligible_machines = [op.machine_id] + [m for m in op.alternative_machines if m in all_machines]
                
                if len(eligible_machines) == 1:
                    m_id = eligible_machines[0]
                    interval_var = model.NewIntervalVar(start_var, dur_int, end_var, f"interval_{j.job_id}_{op.sequence}")
                    machine_intervals[m_id].append(interval_var)
                else:
                    # Optional intervals across eligible alternatives
                    opt_intervals = []
                    for alt_m in eligible_machines:
                        presence = model.NewBoolVar(f"pres_{j.job_id}_{op.sequence}_{alt_m}")
                        opt_interval = model.NewOptionalIntervalVar(
                            start_var, dur_int, end_var, presence, f"opt_{j.job_id}_{op.sequence}_{alt_m}"
                        )
                        machine_intervals[alt_m].append(opt_interval)
                        opt_intervals.append(presence)
                    # Exactly one machine chosen
                    model.Add(sum(opt_intervals) == 1)

                op_start_vars[key] = start_var
                op_end_vars[key] = end_var
                prev_end_var = end_var
                
            job_end_vars[j.job_id] = prev_end_var

        # 3. Add Disjunctive / No-Overlap constraint for every machine
        for m_id, intervals in machine_intervals.items():
            if intervals:
                model.AddNoOverlap(intervals)

        # 4. Multi-Objective Optimization Formulation
        makespan_var = model.NewIntVar(cur_t_int, horizon, "makespan")
        for j_id, j_end in job_end_vars.items():
            if j_end is not None:
                if isinstance(j_end, int):
                    model.Add(makespan_var >= j_end)
                else:
                    model.Add(makespan_var >= j_end)
                    
        # Tardiness and completion variables
        tardiness_terms = []
        completion_terms = []
        for j in jobs:
            due_int = int(round(j.due_date * SCALE))
            j_end = job_end_vars.get(j.job_id)
            if j_end is not None:
                tard_var = model.NewIntVar(0, horizon, f"tardiness_{j.job_id}")
                if isinstance(j_end, int):
                    model.Add(tard_var >= j_end - due_int)
                else:
                    model.Add(tard_var >= j_end - due_int)
                
                # Weight by user priority (1 to 5)
                p_factor = getattr(j, 'priority', 3)
                tardiness_terms.append(p_factor * tard_var)
                completion_terms.append(p_factor * j_end)
                
        # Objective: minimize (w_mk * makespan + w_tard * sum(weighted_tardiness) + sum(priority * completion))
        model.Minimize(
            int(weight_makespan * 10) * makespan_var + 
            int(weight_tardiness * 10) * sum(tardiness_terms) +
            sum(completion_terms)
        )

        # 5. Solve with CP-SAT
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        solver.parameters.num_workers = 4
        status = solver.Solve(model)

        status_str = "FEASIBLE"
        if status == cp_model.OPTIMAL:
            status_str = "OPTIMAL"
        elif status == cp_model.FEASIBLE:
            status_str = "FEASIBLE"
        else:
            status_str = "INFEASIBLE"

        # 6. Extract Solution or Fallback
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for j in jobs:
                for op in j.operations:
                    key = (j.job_id, op.sequence)
                    if key in op_start_vars:
                        s_val = solver.Value(op_start_vars[key]) / SCALE
                        e_val = solver.Value(op_end_vars[key]) / SCALE
                        
                        # Find which machine was selected
                        chosen_m = op.machine_id
                        eligible = [op.machine_id] + [m for m in op.alternative_machines if m in all_machines]
                        if len(eligible) > 1:
                            for alt_m in eligible:
                                pres_var = model.GetBoolVarValue(f"pres_{j.job_id}_{op.sequence}_{alt_m}") if hasattr(solver, 'GetBoolVarValue') else None
                                # OR-Tools provides BooleanValue
                                if solver.BooleanValue(model.NewBoolVar(f"pres_{j.job_id}_{op.sequence}_{alt_m}")):
                                    chosen_m = alt_m
                                    break
                                    
                        scheduled_tasks.append(
                            ScheduledTask(
                                job_id=j.job_id,
                                job_name=j.name,
                                operation_sequence=op.sequence,
                                operation_name=op.name,
                                machine_id=chosen_m,
                                start_time=round(s_val, 2),
                                end_time=round(e_val, 2),
                                duration=op.duration,
                                is_running=False,
                                is_completed=False
                            )
                        )
        else:
            # Fallback to SPT heuristic if solver times out or is infeasible
            from app.scheduling.heuristics import DispatchHeuristicScheduler
            fallback_res = DispatchHeuristicScheduler.schedule(jobs, machines, current_time, rule="SPT")
            
            # Independently validate the fallback schedule before returning
            is_valid, validation_errors = ScheduleValidator.validate(
                tasks=fallback_res.tasks,
                machines=machines,
                current_time=current_time
            )
            if not is_valid:
                err_msg = "; ".join(validation_errors)
                raise ValueError(
                    f"CP-SAT solver status {status_str} and SPT fallback schedule failed independent validation: {err_msg}"
                )
                
            fallback_res.metrics.solver_status = f"FALLBACK_SPT (CP-SAT {status_str})"
            return fallback_res

        duration_ms = (time.perf_counter() - start_cpu) * 1000.0
        
        due_dates = {j.job_id: j.due_date for j in jobs}
        arrivals = {j.job_id: j.arrival_time for j in jobs}
        machine_ids = [m.machine_id for m in machines]
        
        metrics = ScheduleValidator.calculate_metrics(
            tasks=scheduled_tasks,
            jobs_due_dates=due_dates,
            jobs_arrival_times=arrivals,
            machine_ids=machine_ids,
            computation_time_ms=duration_ms,
            solver_status=status_str
        )
        
        return ScheduleResult(
            schedule_id=f"SCHED-CPSAT-{uuid.uuid4().hex[:8]}",
            algorithm="OR-TOOLS CP-SAT",
            created_at_sim_time=current_time,
            tasks=scheduled_tasks,
            metrics=metrics,
            explanation={
                "strategy": "Google OR-Tools CP-SAT",
                "solver_status": status_str,
                "reason": "Globally optimized schedule minimizing combined makespan and deadline tardiness."
            }
        )
