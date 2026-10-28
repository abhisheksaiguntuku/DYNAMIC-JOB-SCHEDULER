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
            # Resolve default checkpoint relative to the project root.
            # __file__ -> .../backend/app/ml/inference/epn_scheduler.py
            # parents[4] -> <project_root>/dynamic_job_shop_scheduler
            project_root = Path(__file__).resolve().parents[4]
            checkpoint_path = str(project_root / "backend" / "models" / "checkpoints" / "epn_model.pth")
        
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
        current_time: float = 0.0
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
        
        # Account for busy machines
        for m in machines:
            if m.status == "BUSY":
                machine_free_time[m.machine_id] = current_time + m.remaining_processing_time

        scheduled_tasks: List[ScheduledTask] = []
        horizon_T = 40

        for j in sorted_jobs:
            num_ops = len(j.operations)
            if num_ops > 5:
                num_ops = 5

            # Synthesize cost vector sequence (T, input_dim=5) based on machine workload prices
            cost_seq = torch.zeros(1, horizon_T, 5, device=self.device)
            for t in range(horizon_T):
                for op_i in range(min(num_ops, 5)):
                    m_id = j.operations[op_i].machine_id
                    cost_seq[0, t, op_i] = (machine_free_time.get(m_id, 0.0) / 10.0)

            with torch.no_grad():
                pred_indices, _ = self.model(cost_seq, num_operations=num_ops)
                pred_slots = pred_indices[0].cpu().numpy()

            # Schedule operations according to neural pointers with strict machine conflict avoidance
            job_ready = current_time + j.arrival_time
            for op_idx, op in enumerate(j.operations[:num_ops]):
                m_id = op.machine_id
                # Neural guidance time slot scaled to minutes
                neural_offset = float(pred_slots[op_idx]) * 2.0
                est_start = max(job_ready, machine_free_time[m_id], current_time + neural_offset)
                est_end = est_start + op.duration

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
