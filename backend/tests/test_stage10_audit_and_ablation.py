"""
Stage 10 Regression Test Suite:
  - Phase C: Adversarial schedule validation & IndependentScheduleAuditor tests
  - Phase D: TIER5_REPEATED_ROUTING re-entrant routing verification across all 7 algorithms
  - Phase E: EPN trace instrumentation and 4-variant controlled ablation verification
  - Phase B/F/H: Statistical helper verification and Stage 9 artifact SHA-256 preservation
"""

from pathlib import Path
import pytest

from app.schemas.models import (
    Job,
    JobStatus,
    Machine,
    MachineStatus,
    Operation,
    OperationStatus,
    ScheduledTask,
)
from app.scheduling.validator import ScheduleValidator
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer
from app.ml.inference.epn_scheduler import EPNJobShopScheduler
from app.experiments.stage10_runner import (
    EXPECTED_STAGE9_HASHES,
    IndependentScheduleAuditor,
    compute_sha256,
    generate_tier5_repeated_routing_instance,
    holm_bonferroni_adjust,
)


def _make_sample_problem():
    machines = [
        Machine(
            machine_id="M1",
            name="M1",
            capability="CNC_M1",
            status=MachineStatus.IDLE,
            remaining_processing_time=0.0,
            total_busy_time=0.0,
        ),
        Machine(
            machine_id="M2",
            name="M2",
            capability="CNC_M2",
            status=MachineStatus.IDLE,
            remaining_processing_time=0.0,
            total_busy_time=0.0,
        ),
        Machine(
            machine_id="M3",
            name="M3",
            capability="CNC_M3",
            status=MachineStatus.IDLE,
            remaining_processing_time=0.0,
            total_busy_time=0.0,
        ),
    ]
    # Re-entrant route J1: M1 -> M3 -> M1
    jobs = [
        Job(
            job_id="J1",
            name="Job 1 Reentrant",
            product_type="Aerospace-Reentrant",
            priority=3,
            arrival_time=5.0,
            due_date=80.0,
            status=JobStatus.PENDING,
            operations=[
                Operation(
                    operation_id="J1-OP1",
                    job_id="J1",
                    sequence=1,
                    name="Op1",
                    machine_id="M1",
                    duration=10.0,
                ),
                Operation(
                    operation_id="J1-OP2",
                    job_id="J1",
                    sequence=2,
                    name="Op2",
                    machine_id="M3",
                    duration=15.0,
                ),
                Operation(
                    operation_id="J1-OP3",
                    job_id="J1",
                    sequence=3,
                    name="Op3",
                    machine_id="M1",
                    duration=12.0,
                ),
            ],
        )
    ]
    return jobs, machines


def test_phase_c_valid_reentrant_schedule_accepted():
    jobs, machines = _make_sample_problem()
    tasks = [
        ScheduledTask(
            job_id="J1",
            job_name="Job 1 Reentrant",
            operation_sequence=1,
            operation_name="Op1",
            machine_id="M1",
            start_time=5.0,
            end_time=15.0,
            duration=10.0,
        ),
        ScheduledTask(
            job_id="J1",
            job_name="Job 1 Reentrant",
            operation_sequence=2,
            operation_name="Op2",
            machine_id="M3",
            start_time=15.0,
            end_time=30.0,
            duration=15.0,
        ),
        ScheduledTask(
            job_id="J1",
            job_name="Job 1 Reentrant",
            operation_sequence=3,
            operation_name="Op3",
            machine_id="M1",
            start_time=30.0,
            end_time=42.0,
            duration=12.0,
        ),
    ]
    v_ok, v_errs = ScheduleValidator.validate(tasks, machines, current_time=0.0)
    assert v_ok, f"Unexpected validator errors: {v_errs}"

    i_ok, i_errs, metrics = IndependentScheduleAuditor.audit_schedule(
        tasks, jobs, machines, current_time=0.0
    )
    assert i_ok, f"Unexpected independent auditor errors: {i_errs}"
    assert metrics["makespan"] == 42.0
    assert metrics["total_tardiness"] == 0.0


def test_phase_c_adversarial_machine_overlap_rejected():
    jobs, machines = _make_sample_problem()
    # Two operations of J1 on M1 overlapping in time
    tasks = [
        ScheduledTask(
            job_id="J1",
            job_name="Job 1",
            operation_sequence=1,
            operation_name="Op1",
            machine_id="M1",
            start_time=5.0,
            end_time=20.0,
            duration=15.0,
        ),
        ScheduledTask(
            job_id="J1",
            job_name="Job 1",
            operation_sequence=2,
            operation_name="Op2",
            machine_id="M3",
            start_time=20.0,
            end_time=35.0,
            duration=15.0,
        ),
        ScheduledTask(
            job_id="J1",
            job_name="Job 1",
            operation_sequence=3,
            operation_name="Op3",
            machine_id="M1",
            start_time=10.0,
            end_time=22.0,
            duration=12.0,
        ),
    ]
    v_ok, _ = ScheduleValidator.validate(tasks, machines, current_time=0.0)
    i_ok, i_errs, _ = IndependentScheduleAuditor.audit_schedule(
        tasks, jobs, machines, current_time=0.0
    )
    assert not v_ok
    assert not i_ok
    assert any("OVERLAP" in e or "PRECEDENCE" in e for e in i_errs)


def test_phase_c_adversarial_duration_and_duplicate_rejected():
    jobs, machines = _make_sample_problem()
    # Duplicate Op1 + duration mismatch on Op2 + negative duration on Op3
    tasks = [
        ScheduledTask(
            job_id="J1",
            job_name="Job 1",
            operation_sequence=1,
            operation_name="Op1",
            machine_id="M1",
            start_time=5.0,
            end_time=15.0,
            duration=10.0,
        ),
        ScheduledTask(
            job_id="J1",
            job_name="Job 1",
            operation_sequence=1,
            operation_name="Op1-Dup",
            machine_id="M2",
            start_time=15.0,
            end_time=25.0,
            duration=10.0,
        ),
        ScheduledTask(
            job_id="J1",
            job_name="Job 1",
            operation_sequence=2,
            operation_name="Op2",
            machine_id="M3",
            start_time=25.0,
            end_time=50.0,  # 25m interval != 15m duration
            duration=15.0,
        ),
        ScheduledTask(
            job_id="J1",
            job_name="Job 1",
            operation_sequence=3,
            operation_name="Op3",
            machine_id="M1",
            start_time=50.0,
            end_time=45.0,
            duration=-5.0,
        ),
    ]
    v_ok, v_errs = ScheduleValidator.validate(tasks, machines, current_time=0.0)
    i_ok, i_errs, _ = IndependentScheduleAuditor.audit_schedule(
        tasks, jobs, machines, current_time=0.0
    )
    assert not v_ok
    assert any("Duplicate Operation" in e for e in v_errs)
    assert any("Duration Mismatch" in e for e in v_errs)
    assert any("Duration Consistency" in e for e in v_errs)
    assert not i_ok
    assert any("INDEP-DUP" in e for e in i_errs)
    assert any("INDEP-DUR-MISMATCH" in e for e in i_errs)


def test_phase_c_adversarial_busy_lock_and_downtime_rejected():
    jobs, machines = _make_sample_problem()
    machines[0].status = MachineStatus.BUSY
    machines[0].remaining_processing_time = 20.0  # M1 busy until t=30 when current_time=10
    machines[2].status = MachineStatus.DOWN
    machines[2].remaining_processing_time = 40.0  # M3 down until t=50 when current_time=10

    tasks = [
        ScheduledTask(
            job_id="J1",
            job_name="Job 1",
            operation_sequence=1,
            operation_name="Op1",
            machine_id="M1",
            start_time=15.0,  # Violates M1 busy until 30.0
            end_time=25.0,
            duration=10.0,
        ),
        ScheduledTask(
            job_id="J1",
            job_name="Job 1",
            operation_sequence=2,
            operation_name="Op2",
            machine_id="M3",
            start_time=35.0,  # Violates M3 down until 50.0
            end_time=50.0,
            duration=15.0,
        ),
        ScheduledTask(
            job_id="J1",
            job_name="Job 1",
            operation_sequence=3,
            operation_name="Op3",
            machine_id="M1",
            start_time=50.0,
            end_time=62.0,
            duration=12.0,
        ),
    ]
    v_ok, v_errs = ScheduleValidator.validate(tasks, machines, current_time=10.0)
    i_ok, i_errs, _ = IndependentScheduleAuditor.audit_schedule(
        tasks, jobs, machines, current_time=10.0
    )
    assert not v_ok
    assert any("Busy Machine Lock Violation" in e for e in v_errs)
    assert any("Machine Downtime Violation" in e for e in v_errs)
    assert not i_ok
    assert any("INDEP-BUSY-LOCK" in e for e in i_errs)
    assert any("INDEP-DOWNTIME" in e for e in i_errs)


def test_phase_d_tier5_repeated_routing_all_algorithms_valid():
    jobs, machines, current_time = generate_tier5_repeated_routing_instance(5001)
    reentrant_jobs = [
        j
        for j in jobs
        if len({op.machine_id for op in j.operations}) < len(j.operations)
    ]
    assert len(reentrant_jobs) >= 6, "Expected >=50% of jobs to revisit machines"

    epn = EPNJobShopScheduler()
    for algo in ("FCFS", "SPT", "EDD", "CR", "AGING", "CPSAT", "EPN"):
        jobs_copy = [Job(**j.model_dump()) for j in jobs]
        machines_copy = [Machine(**m.model_dump()) for m in machines]
        if algo == "CPSAT":
            res = CPSATSchedulingOptimizer.optimize(
                jobs_copy, machines_copy, current_time=current_time, time_limit_seconds=1.5
            )
        elif algo == "EPN":
            res = epn.schedule(jobs_copy, machines_copy, current_time=current_time)
        else:
            res = DispatchHeuristicScheduler.schedule(
                jobs_copy, machines_copy, current_time=current_time, rule=algo
            )

        v_ok, v_errs = ScheduleValidator.validate(
            res.tasks, machines_copy, current_time=current_time
        )
        i_ok, i_errs, indep_metrics = IndependentScheduleAuditor.audit_schedule(
            res.tasks, jobs_copy, machines_copy, current_time=current_time
        )
        assert v_ok, f"{algo} failed ScheduleValidator on Tier 5: {v_errs}"
        assert i_ok, f"{algo} failed IndependentScheduleAuditor on Tier 5: {i_errs}"
        assert abs(res.metrics.makespan - indep_metrics["makespan"]) <= 1e-2


def test_phase_e_epn_traces_and_controlled_ablations():
    jobs, machines, current_time = generate_tier5_repeated_routing_instance(5002)
    epn = EPNJobShopScheduler()

    traces_base = []
    res_base = epn.schedule(
        [Job(**j.model_dump()) for j in jobs],
        [Machine(**m.model_dump()) for m in machines],
        current_time=current_time,
        ablation_mode="BASELINE",
        record_traces=traces_base,
    )
    assert len(traces_base) == sum(len(j.operations) for j in jobs)
    assert "artificial_idle_gap" in traces_base[0]
    assert "pred_slot" in traces_base[0]

    res_no_offset = epn.schedule(
        [Job(**j.model_dump()) for j in jobs],
        [Machine(**m.model_dump()) for m in machines],
        current_time=current_time,
        ablation_mode="ABLATION_A_NO_OFFSET",
    )
    res_op_ready = epn.schedule(
        [Job(**j.model_dump()) for j in jobs],
        [Machine(**m.model_dump()) for m in machines],
        current_time=current_time,
        ablation_mode="ABLATION_B_OP_READY_DECODING",
    )
    res_hybrid = epn.schedule(
        [Job(**j.model_dump()) for j in jobs],
        [Machine(**m.model_dump()) for m in machines],
        current_time=current_time,
        ablation_mode="ABLATION_C_HYBRID_SPT",
    )

    for mode_name, res in [
        ("BASELINE", res_base),
        ("NO_OFFSET", res_no_offset),
        ("OP_READY", res_op_ready),
        ("HYBRID", res_hybrid),
    ]:
        i_ok, i_errs, _ = IndependentScheduleAuditor.audit_schedule(
            res.tasks, jobs, machines, current_time=current_time
        )
        assert i_ok, f"EPN {mode_name} failed independent audit: {i_errs}"

    # Operation-level ready-queue decoding modes must strictly improve makespan over job-sequential baseline
    assert res_op_ready.metrics.makespan < res_base.metrics.makespan
    assert res_hybrid.metrics.makespan < res_base.metrics.makespan


def test_phase_b_holm_bonferroni_and_stage9_hashes_preserved():
    raw_p = [0.01, 0.04, 0.03, 0.20]
    adj_p = holm_bonferroni_adjust(raw_p)
    # Sorted: 0.01*4=0.04, 0.03*3=0.09, 0.04*2=0.08->max(0.09,0.08)=0.09, 0.20*1=0.20
    assert abs(adj_p[0] - 0.04) < 1e-9
    assert abs(adj_p[2] - 0.09) < 1e-9
    assert abs(adj_p[1] - 0.09) < 1e-9
    assert abs(adj_p[3] - 0.20) < 1e-9

    project_root = Path(__file__).resolve().parents[2]
    s9_dir = project_root / "backend" / "experiments" / "stage9_benchmark"
    ckpt_path = project_root / "backend" / "models" / "checkpoints" / "epn_model.pth"
    assert compute_sha256(ckpt_path) == EXPECTED_STAGE9_HASHES["epn_model.pth"]
    for fname, exp_hash in EXPECTED_STAGE9_HASHES.items():
        if fname == "epn_model.pth":
            continue
        assert compute_sha256(s9_dir / fname) == exp_hash

