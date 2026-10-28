import os
import torch
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.ml.models.pointer_network import EnhancedPointerNetwork
from app.schemas.models import Job, Machine, ScheduledTask, ScheduleResult
from app.scheduling.validator import ScheduleValidator

class EPNJobShopScheduler:
    """
    Online Inference Engine integrating the trained PyTorch Enhanced Pointer Network (EPN)
    with the 10-Machine Job Shop Environment.
    
    1. Transforms shop-floor state and job routes into surrogate cost sequences.
    2. Runs forward pass through EPN with dynamic causal masking.
    3. Translates output pointers into feasible start times.
    4. Validates final schedule through zero-trust ScheduleValidator.
    """
    def __init__(self, checkpoint_path: str = None):
        """Initialize the EPN scheduler.

        If *checkpoint_path* is not provided, the method computes a default path
        that is independent of the current working directory. The default points
        to ``backend/models/checkpoints/epn_model.pth`` relative to the project
        root (the directory that contains the ``backend`` package).

        The logic uses ``Path(__file__).resolve().parents[4]`` which resolves to
        the project root regardless of where the process is launched from. The
        constructed path is then joined with the ``backend/models/checkpoints``
        sub‑directory.

        A boolean ``self.loaded`` indicates whether the model checkpoint was
        successfully loaded. If the checkpoint cannot be found, ``self.loaded``
        is set to ``False`` and the scheduler will fall back to the SPT
        heuristic when ``schedule`` is called.
        """
        if checkpoint_path is None:
            # Resolve default checkpoint relative to the project root (or backend root when deployed with Root Directory = backend).
            # __file__ -> .../backend/app/ml/inference/epn_scheduler.py
            # parents[4] -> <project_root>/dynamic_job_shop_scheduler
            # parents[3] -> <backend_root>
            project_root = Path(__file__).resolve().parents[4]
            candidate = project_root / "backend" / "models" / "checkpoints" / "epn_model.pth"
            if not candidate.exists():
                candidate = Path(__file__).resolve().parents[3] / "models" / "checkpoints" / "epn_model.pth"
            checkpoint_path = str(candidate)
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = EnhancedPointerNetwork(input_dim=5, hidden_dim=64, encoder_layers=2)
        
        if os.path.exists(checkpoint_path):
            ckpt = torch.load(checkpoint_path, map_location=self.device)
            self.model.load_state_dict(ckpt["model_state_dict"])
            self.model.to(self.device)
            self.model.eval()
            self.loaded = True
        else:
            self.loaded = False
            # Log the missing checkpoint for debugging purposes.
            print(f"[EPNJobShopScheduler] Checkpoint not found at '{checkpoint_path}'. Falling back to SPT.")

    def schedule(
        self,
        jobs: List[Job],
        machines: List[Machine],
        current_time: float = 0.0,
        ablation_mode: str = "BASELINE",
        record_traces: Optional[List[Dict[str, Any]]] = None
    ) -> ScheduleResult:
        import time
        import uuid
        start_cpu = time.perf_counter()

        # If model checkpoint not found, fallback to SPT heuristic
        if not self.loaded:
            from app.scheduling.heuristics import DispatchHeuristicScheduler
            res = DispatchHeuristicScheduler.schedule(jobs, machines, current_time, rule="SPT")
            res.metrics.solver_status = "FALLBACK_NO_MODEL"
            return res

        # Sort jobs by arrival and priority to sequence parts
        sorted_jobs = sorted(jobs, key=lambda j: (j.arrival_time, -j.priority))
        machine_free_time = {m.machine_id: current_time for m in machines}
        
        # Account for busy or down/maintenance machines
        for m in machines:
            if m.status == "BUSY":
                machine_free_time[m.machine_id] = current_time + m.remaining_processing_time
            elif m.status in ("DOWN", "MAINTENANCE"):
                downtime_rem = m.remaining_processing_time if m.remaining_processing_time > 1e-4 else 1e6
                machine_free_time[m.machine_id] = current_time + downtime_rem

        scheduled_tasks: List[ScheduledTask] = []
        horizon_T = 40

        if ablation_mode in ("BASELINE", "EPN_BASELINE", "ABLATION_A_NO_OFFSET", "EPN_ABLATION_A_NO_OFFSET"):
            use_offset = ablation_mode in ("BASELINE", "EPN_BASELINE")
            for j in sorted_jobs:
                pending_ops = []
                latest_comp = max(current_time, j.arrival_time)
                for op in j.operations:
                    if op.status == "COMPLETED":
                        e_t = op.end_time or 0.0
                        latest_comp = max(latest_comp, e_t)
                        scheduled_tasks.append(
                            ScheduledTask(
                                job_id=j.job_id,
                                job_name=j.name,
                                operation_sequence=op.sequence,
                                operation_name=op.name,
                                machine_id=op.assigned_machine_id or op.machine_id,
                                start_time=op.start_time or 0.0,
                                end_time=e_t,
                                duration=op.duration,
                                is_completed=True
                            )
                        )
                    elif op.status == "RUNNING":
                        s_t = op.start_time or current_time
                        m_obj = next((m for m in machines if m.machine_id == op.machine_id), None)
                        rem_t = m_obj.remaining_processing_time if m_obj else op.duration
                        e_t = current_time + rem_t
                        latest_comp = max(latest_comp, e_t)
                        machine_free_time[op.machine_id] = max(machine_free_time.get(op.machine_id, current_time), e_t)
                        scheduled_tasks.append(
                            ScheduledTask(
                                job_id=j.job_id,
                                job_name=j.name,
                                operation_sequence=op.sequence,
                                operation_name=op.name,
                                machine_id=op.machine_id,
                                start_time=s_t,
                                end_time=round(e_t, 2),
                                duration=op.duration,
                                is_running=True
                            )
                        )
                    else:
                        pending_ops.append(op)

                num_ops = len(pending_ops)
                if num_ops == 0:
                    continue
                neural_ops = min(num_ops, 5)

                # Synthesize cost vector sequence (T, input_dim=5) based on machine workload prices
                cost_seq = torch.zeros(1, horizon_T, 5, device=self.device)
                for t in range(horizon_T):
                    for op_i in range(neural_ops):
                        m_id = pending_ops[op_i].machine_id
                        cost_seq[0, t, op_i] = (machine_free_time.get(m_id, 0.0) / 10.0)

                with torch.no_grad():
                    pred_indices, _ = self.model(cost_seq, num_operations=neural_ops)
                    pred_slots = pred_indices[0].cpu().numpy()

                # Schedule operations according to neural pointers with strict machine conflict avoidance
                job_ready = latest_comp
                for op_idx, op in enumerate(pending_ops):
                    m_id = op.machine_id
                    # Neural guidance time slot scaled to minutes (for ops beyond 5, continue from last slot)
                    slot_val = float(pred_slots[op_idx]) if op_idx < neural_ops else float(pred_slots[neural_ops - 1])
                    neural_offset = (slot_val * 2.0) if use_offset else 0.0
                    m_free_before = machine_free_time[m_id]
                    earliest_feasible = max(job_ready, m_free_before)
                    neural_target = current_time + neural_offset
                    est_start = max(earliest_feasible, neural_target) if use_offset else earliest_feasible
                    est_end = est_start + op.duration

                    if record_traces is not None:
                        record_traces.append({
                            "ablation_mode": ablation_mode,
                            "job_id": j.job_id,
                            "op_sequence": op.sequence,
                            "machine_id": m_id,
                            "duration": round(op.duration, 2),
                            "pred_slot": int(slot_val),
                            "job_ready_time": round(job_ready, 2),
                            "machine_free_time_before": round(m_free_before, 2),
                            "earliest_feasible_start": round(earliest_feasible, 2),
                            "neural_offset_minutes": round(neural_offset, 2),
                            "neural_target_time": round(neural_target, 2),
                            "actual_start": round(est_start, 2),
                            "actual_end": round(est_end, 2),
                            "artificial_idle_gap": round(max(0.0, est_start - earliest_feasible), 2),
                            "offset_delayed_start": bool(est_start > earliest_feasible + 1e-6),
                        })

                    scheduled_tasks.append(
                        ScheduledTask(
                            job_id=j.job_id,
                            job_name=j.name,
                            operation_sequence=op.sequence,
                            operation_name=op.name,
                            machine_id=m_id,
                            start_time=round(est_start, 2),
                            end_time=round(est_end, 2),
                            duration=op.duration,
                            is_running=False,
                            is_completed=False
                        )
                    )

                    machine_free_time[m_id] = est_end
                    job_ready = est_end
        else:
            # Operation-level ready-queue decoding modes:
            # - ABLATION_B_OP_READY_DECODING: Pure EPN operation-level ready-queue decoding (no SPT duration rule)
            # - ABLATION_C_HYBRID_SPT: Hybrid EPN + SPT active-schedule gap-insertion decoding
            is_hybrid_spt = ablation_mode in ("ABLATION_C_HYBRID_SPT", "EPN_ABLATION_C_HYBRID_SPT")
            job_map = {j.job_id: j for j in sorted_jobs}
            job_pending_ops: Dict[str, List[Any]] = {}
            job_ready_time: Dict[str, float] = {}
            job_pred_slots: Dict[str, List[float]] = {}
            machine_intervals: Dict[str, List[ Any ]] = {m.machine_id: [] for m in machines}
            for m_id, free_t in machine_free_time.items():
                if free_t > current_time + 1e-6:
                    machine_intervals[m_id].append((0.0, free_t))

            for j in sorted_jobs:
                pending_ops = []
                latest_comp = max(current_time, j.arrival_time)
                for op in j.operations:
                    if op.status == "COMPLETED":
                        e_t = op.end_time or 0.0
                        latest_comp = max(latest_comp, e_t)
                        scheduled_tasks.append(
                            ScheduledTask(
                                job_id=j.job_id,
                                job_name=j.name,
                                operation_sequence=op.sequence,
                                operation_name=op.name,
                                machine_id=op.assigned_machine_id or op.machine_id,
                                start_time=op.start_time or 0.0,
                                end_time=e_t,
                                duration=op.duration,
                                is_completed=True
                            )
                        )
                    elif op.status == "RUNNING":
                        s_t = op.start_time or current_time
                        m_obj = next((m for m in machines if m.machine_id == op.machine_id), None)
                        rem_t = m_obj.remaining_processing_time if m_obj else op.duration
                        e_t = current_time + rem_t
                        latest_comp = max(latest_comp, e_t)
                        machine_free_time[op.machine_id] = max(machine_free_time.get(op.machine_id, current_time), e_t)
                        machine_intervals[op.machine_id].append((s_t, round(e_t, 2)))
                        scheduled_tasks.append(
                            ScheduledTask(
                                job_id=j.job_id,
                                job_name=j.name,
                                operation_sequence=op.sequence,
                                operation_name=op.name,
                                machine_id=op.machine_id,
                                start_time=s_t,
                                end_time=round(e_t, 2),
                                duration=op.duration,
                                is_running=True
                            )
                        )
                    else:
                        pending_ops.append(op)

                if pending_ops:
                    job_pending_ops[j.job_id] = pending_ops
                    job_ready_time[j.job_id] = latest_comp
                    num_ops = len(pending_ops)
                    neural_ops = min(num_ops, 5)
                    cost_seq = torch.zeros(1, horizon_T, 5, device=self.device)
                    for t in range(horizon_T):
                        for op_i in range(neural_ops):
                            m_id = pending_ops[op_i].machine_id
                            cost_seq[0, t, op_i] = (machine_free_time.get(m_id, 0.0) / 10.0) + (pending_ops[op_i].duration / 50.0)
                    with torch.no_grad():
                        pred_indices, _ = self.model(cost_seq, num_operations=neural_ops)
                        raw_slots = [float(x) for x in pred_indices[0].cpu().numpy()]
                    while len(raw_slots) < num_ops:
                        raw_slots.append(raw_slots[-1] if raw_slots else 0.0)
                    job_pred_slots[j.job_id] = raw_slots

            def _earliest_active_start(m_id: str, min_start: float, duration: float) -> float:
                intervals = sorted(machine_intervals[m_id], key=lambda x: x[0])
                cand = max(current_time, min_start)
                if not is_hybrid_spt:
                    # Pure operation-level end-of-machine queue decoding
                    return max(cand, machine_free_time[m_id])
                for iv_s, iv_e in intervals:
                    if cand + duration <= iv_s + 1e-6:
                        return cand
                    if cand < iv_e:
                        cand = iv_e
                return cand

            while job_pending_ops:
                candidates = []
                for j_id, ops_list in job_pending_ops.items():
                    j_obj = job_map[j_id]
                    op = ops_list[0]
                    slot_val = job_pred_slots[j_id][0]
                    j_ready = job_ready_time[j_id]
                    e_start = _earliest_active_start(op.machine_id, j_ready, op.duration)
                    if is_hybrid_spt:
                        # Hybrid EPN + SPT active-schedule priority key
                        sort_key = (e_start, op.duration + 0.25 * slot_val, -j_obj.priority, j_obj.arrival_time, j_id)
                    else:
                        # Pure EPN operation-ready decoding (no SPT duration rule)
                        sort_key = (e_start, slot_val, -j_obj.priority, j_obj.arrival_time, j_id)
                    candidates.append((sort_key, j_id, op, slot_val, j_ready, e_start))

                candidates.sort(key=lambda x: x[0])
                _, chosen_jid, chosen_op, chosen_slot, chosen_j_ready, est_start = candidates[0]
                j_obj = job_map[chosen_jid]
                m_id = chosen_op.machine_id
                m_free_before = machine_free_time[m_id]
                est_end = est_start + chosen_op.duration

                if record_traces is not None:
                    record_traces.append({
                        "ablation_mode": ablation_mode,
                        "job_id": chosen_jid,
                        "op_sequence": chosen_op.sequence,
                        "machine_id": m_id,
                        "duration": round(chosen_op.duration, 2),
                        "pred_slot": int(chosen_slot),
                        "job_ready_time": round(chosen_j_ready, 2),
                        "machine_free_time_before": round(m_free_before, 2),
                        "earliest_feasible_start": round(est_start, 2),
                        "neural_offset_minutes": 0.0,
                        "neural_target_time": round(current_time, 2),
                        "actual_start": round(est_start, 2),
                        "actual_end": round(est_end, 2),
                        "artificial_idle_gap": 0.0,
                        "offset_delayed_start": False,
                    })

                scheduled_tasks.append(
                    ScheduledTask(
                        job_id=chosen_jid,
                        job_name=j_obj.name,
                        operation_sequence=chosen_op.sequence,
                        operation_name=chosen_op.name,
                        machine_id=m_id,
                        start_time=round(est_start, 2),
                        end_time=round(est_end, 2),
                        duration=chosen_op.duration,
                        is_running=False,
                        is_completed=False
                    )
                )

                machine_intervals[m_id].append((round(est_start, 2), round(est_end, 2)))
                machine_free_time[m_id] = max(machine_free_time[m_id], est_end)
                job_ready_time[chosen_jid] = est_end
                job_pending_ops[chosen_jid].pop(0)
                job_pred_slots[chosen_jid].pop(0)
                if not job_pending_ops[chosen_jid]:
                    del job_pending_ops[chosen_jid]
                    del job_pred_slots[chosen_jid]

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
            solver_status="NEURAL_PREDICTED_FEASIBLE"
        )

        return ScheduleResult(
            schedule_id=f"SCHED-EPN-{uuid.uuid4().hex[:8]}",
            algorithm="PYTORCH EPN (Liu et al.)",
            created_at_sim_time=current_time,
            tasks=scheduled_tasks,
            metrics=metrics,
            explanation={
                "strategy": "PyTorch Enhanced Pointer Network",
                "method": "Liu et al. (IEEE TASE 2024)",
                "causal_masking": "Enabled (100% Precedence Guarantee)",
                "reason": "Subproblem start times predicted using trained bidirectional attention mechanism."
            }
        )
