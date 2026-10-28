# STAGE 5 SCHEDULING-CORRECTNESS AUDIT

**Project:** Dynamic Job-Shop Scheduling System  
**Audit Date:** 2026-10-18  
**Scope:** Simulation Engine, Production State Service, CP-SAT Solver, Dispatch Heuristics, Schedule Validator, Database Models, and API Endpoints.

---

## 1. Verified Scheduling Invariants

| Invariant | Implementation Mechanism | Test Verification | Status |
|---|---|---|---|
| **Single Operation Representation** | Operations tracked sequentially via `sequence` field. Finished operations become `is_completed=True`, active become `is_running=True`, remaining are dispatched. | `test_repeated_recalculation_no_duplicate_operations`, `test_repeated_scheduling_idempotent_task_count` | **PASS** |
| **Completed Operation Preservation** | Completed operations are logged with historical `start_time` and `end_time`. Entirely completed jobs (`JobStatus.COMPLETED`) are filtered out prior to re-dispatching. Engine mutations use list copy for SQLite JSON persistence. | `test_completed_operation_preservation`, `test_single_op_job_completed_by_engine_not_rescheduled`, `test_multi_op_job_partial_completion_second_op_preserved` | **PASS** |
| **Running Operation Preservation** | Machine busy time is locked for `remaining_processing_time`. Heuristics advance machine free time to `current_time + m.remaining_processing_time`. CP-SAT adds fixed `NewIntervalVar` for busy interval. | `test_scenario_running_operation_preserved`, `test_running_op_machine_not_double_booked`, `test_running_op_timestamps_unchanged_after_reschedule` | **PASS** |
| **Machine Exclusivity (No-Overlap)** | Heuristics enforce monotonic `machine_free_time[m]`. CP-SAT enforces `model.AddNoOverlap(machine_intervals[m])`. Independent validation verifies `t2.start_time >= t1.end_time - 1e-4`. | `test_machine_capacity_no_overlap`, `test_machine_no_overlap_three_jobs_same_machine`, `test_no_machine_overlap_with_running_op` | **PASS** |
| **Operation Precedence** | Successor operation start is constrained by `start_var >= prev_end_var` (CP-SAT) or `max(job_ready_time, machine_free_time)` (heuristics). Validator checks `op_curr.start_time >= op_prev.end_time - 1e-4`. | `test_operation_precedence`, `test_operation_precedence_three_ops` | **PASS** |
| **Release Time Enforcement** | Heuristics set `job_ready_time = max(latest_comp, current_time, j.arrival_time)`. CP-SAT enforces `start_var >= j_arr_int`. Validator checks future tasks do not start before `current_time`. | `test_release_and_due_dates`, `test_release_time_respected` | **PASS** |
| **Input Validation** | `ProductionStateService.recalculate_schedule` checks `if not job.operations: raise ValueError(...)`. API handles `ValueError` and yields HTTP 400. | `test_invalid_job_missing_operations`, `test_empty_operations_raises_value_error`, `test_invalid_input_empty_ops_rejected` | **PASS** |
| **Fallback Validation & Safety** | If CP-SAT returns INFEASIBLE/timeout, SPT fallback is generated and independently verified with `ScheduleValidator.validate`. If invalid, `ValueError` is raised, preventing corruption of schedule records. | `test_fallback_schedule_passes_validator`, `test_fallback_rejected_when_validation_fails`, `test_api_controlled_response_on_fallback_failure` | **PASS** |
| **Solver Status Transparency** | Schedule result records accurate solver status: `OPTIMAL`, `FEASIBLE`, or `FALLBACK_SPT (CP-SAT <status>)`. | `test_infeasible_instance_handling`, `test_fallback_records_solver_status_in_metrics` | **PASS** |
| **Persistence and Restart** | Schedules are committed to SQLite `schedule_records` table with JSON tasks and metrics. | `test_persistence_restart`, `test_schedule_result_persisted_to_db` | **PASS** |

---

## 2. Unsupported Features (Honest Scope Delimitation)

1. **Machine Breakdown / Downtime Recovery (`test_machine_downtime_and_recovery`):**
   - *Status:* **NOT IMPLEMENTED**
   - *Reason:* The `MachineStatus` enum has a `DOWN` state, but the discrete-event simulator does not implement stochastic or scheduled machine breakdown events, preemption handling, or recovery rescheduling. The test remains skipped.
2. **Stale Schedule Rejection / Optimistic Concurrency (`test_stale_schedule_rejection`):**
   - *Status:* **NOT IMPLEMENTED**
   - *Reason:* No optimistic version tag (`version_id` or `etag`) exists on `ScheduleRecordModel` to reject concurrent requests from stale factory states. The test remains skipped.
