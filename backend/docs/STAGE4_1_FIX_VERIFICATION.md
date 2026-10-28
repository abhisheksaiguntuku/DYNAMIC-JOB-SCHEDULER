# STAGE 4.1 FIX VERIFICATION REPORT

**Project:** Dynamic Job-Shop Scheduler  
**Stage:** 4.1 — Post-Test Fix Verification and Dynamic Scheduling Acceptance  
**Date:** 2026-10-12  
**Verified by:** Automated test execution + source inspection  

---

## 1. Baseline Test Run (Task 1)

### Command
```powershell
$env:PYTHONPATH="backend"
python -m pytest backend/tests/ -v --tb=short
```

### Working Directory
`C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler`

### Result (pre-Stage 4.1)
| Metric | Value |
|--------|-------|
| Tests collected | 25 |
| Passed | 23 |
| Skipped | 2 |
| Failed | 0 |
| Duration | 8.33 s |

### Skip Markers Confirmed
| Test | Skip Reason | Status |
|------|-------------|--------|
| `test_machine_downtime_and_recovery` | `"Machine breakdown feature not implemented in current codebase"` | NOT IMPLEMENTED |
| `test_stale_schedule_rejection` | `"Versioned schedule validation not present in backend"` | NOT IMPLEMENTED |

Neither skip is counted as a pass. Both correspond exactly to the features described.

---

## 2. Completed-Operation Preservation Through Real Workflow (Task 2)

### Finding: Engine Bug — SQLAlchemy JSON Mutation Not Detected

**Root cause:** `engine.py` mutated the `operations_json` list in place:
```python
for op in j_rec.operations_json:
    op["status"] = "COMPLETED"   # ← mutates dict in the existing list
j_rec.operations_json = ops      # ← same object, SQLAlchemy marks column NOT dirty
```
SQLAlchemy only tracks column assignment, not in-place mutations to JSON arrays. The write was silently discarded — the op status remained `RUNNING` in the database even though the job-level `status` was set correctly via a separate `j_rec.status =` assignment (scalar column, tracked).

**Fix applied (`backend/app/simulation/engine.py`):**
```python
new_ops = []
for op in j_rec.operations_json:
    op_copy = dict(op)           # fresh copy
    if op_copy["sequence"] == finished_seq:
        op_copy["status"] = "COMPLETED"
        op_copy["end_time"] = self.sim_time
    elif op_copy["status"] != "COMPLETED":
        all_done = False
    new_ops.append(op_copy)
j_rec.operations_json = new_ops  # new object → SQLAlchemy detects change
```

### Verification
| Test | Approach | Result |
|------|----------|--------|
| `test_single_op_job_completed_by_engine_not_rescheduled` | Engine-driven: machine BUSY, `advance_time(5)`, DB state checked, reschedule called | **PASS** |
| `test_multi_op_job_partial_completion_second_op_preserved` | Engine-driven: op1 completed, op2 PENDING, check op1 end_time in next schedule | **PASS** |

Both tests verify:
- Engine writes `COMPLETED` status and `end_time` to DB
- Historical timestamps are unchanged after rescheduling
- Completed operation is not re-inserted as a pending task
- Next operation respects precedence w.r.t. actual end_time

---

## 3. Running-Operation Preservation Audit (Task 3)

### Tests Added
| Test | What It Asserts |
|------|----------------|
| `test_running_op_machine_not_double_booked` | J2-Op1 on M1 must start after J1's running op ends (M1 free time) |
| `test_running_op_timestamps_unchanged_after_reschedule` | Running task's `start_time`/`end_time` identical before and after inserting a new job |
| `test_no_machine_overlap_with_running_op` | `ScheduleValidator.validate` confirms no overlap on the locked machine |

### Result
All three tests **PASS**. The heuristic scheduler correctly treats a BUSY machine's remaining time as a locked interval (line 33–37 of `heuristics.py`):
```python
if m.status == MachineStatus.BUSY:
    machine_free_time[m.machine_id] = current_time + m.remaining_processing_time
```
This forces any new task on that machine to start no earlier than `current_time + remaining`.

---

## 4. SPT Fallback Verification (Task 4)

### Code Path Inspected
`cpsat_solver.py` lines 235–240:
```python
else:
    from app.scheduling.heuristics import DispatchHeuristicScheduler
    fallback_res = DispatchHeuristicScheduler.schedule(jobs, machines, current_time, rule="SPT")
    fallback_res.metrics.solver_status = f"FALLBACK_SPT (CP-SAT {status_str})"
    return fallback_res
```

### Observations
| Property | Status |
|----------|--------|
| Fallback solver_status recorded | **PASS** — format `"FALLBACK_SPT (CP-SAT INFEASIBLE)"` |
| Fallback passes ScheduleValidator | **PASS** — confirmed by `test_fallback_schedule_passes_validator` |
| Running operations preserved in fallback | **PASS** — heuristic reads BUSY machine state |
| Machine no-overlap in fallback | **PASS** — SPT heuristic enforces `machine_free_time` |
| Job precedence in fallback | **PASS** — SPT heuristic enforces `job_ready_time` |
| Completed operations preserved in fallback | **PARTIAL** — heuristic preserves COMPLETED ops (flagged `is_completed=True`) but does not re-add them to the schedule; jobs filtered at service level |

### Limitation
The fallback does not independently re-validate its own output against `ScheduleValidator`. If a heuristic bug produces an overlap, the fallback will return it silently. **Recommendation:** add a post-solve validation call inside the fallback path (not implemented in this stage).

---

## 5. state_service.py Changes Verification (Task 5)

| Change | Verified |
|--------|---------|
| `time_limit_seconds` passed to CP-SAT (`solver.parameters.max_time_in_seconds`) | **PASS** — line 189 in `cpsat_solver.py` uses the parameter |
| Empty operation list raises `ValueError` before DB write | **PASS** — `test_empty_operations_raises_value_error` |
| COMPLETED jobs filtered before scheduling | **PASS** — `test_completed_jobs_excluded_from_schedule` |
| `CP_SAT` alias normalized via `.replace("_","").upper()` | **PASS** — `test_algorithm_alias_cp_sat_normalized` |
| `CPSAT` alias works | **PASS** — `test_algorithm_alias_cpsat_no_underscore` |
| FCFS still routes correctly | **PASS** — `test_heuristic_fcfs_still_works` |
| SPT still routes correctly | **PASS** — `test_heuristic_spt_still_works` |

---

## 6. Unsupported Features (Task 7)

| Feature | Status | Skip Reason |
|---------|--------|-------------|
| Machine downtime / breakdown recovery | NOT IMPLEMENTED | Requires machine state machine with `DOWN` transitions; not in current DB schema or engine |
| Stale-schedule concurrency control | NOT IMPLEMENTED | Requires schedule versioning or optimistic locking; not in DB model |

These tests remain skipped with accurate `reason` strings. They are **not described as working features** anywhere in the codebase or documentation.

---

## 7. Final Test Run Summary (Task 8)

### Command
```powershell
$env:PYTHONPATH="backend"
python -m pytest backend/tests/ -v --tb=short
```

### Result
| Metric | Value |
|--------|-------|
| Tests collected | 50 |
| Passed | **48** |
| Skipped | 2 |
| Failed | **0** |
| Duration | 17.25 s |

### Files Preserved
| Asset | Status |
|-------|--------|
| `production_scheduler.db` | Preserved (tests use isolated clean DB via fixture) |
| `models/checkpoints/epn_model.pth` | Preserved (not touched) |
| `experiments/` raw results | Preserved (not touched) |
| `frontend/` source | Preserved (not touched) |

---

## 8. Defects Found and Fixed

| # | File | Defect | Fix |
|---|------|--------|-----|
| 1 | `engine.py` | SQLAlchemy JSON mutation not persisted — op status stayed RUNNING after completion | Replaced in-place dict mutation with fresh copy list assignment |
| 2 | `state_service.py` | `time_limit_seconds` hard-coded as 3.0 despite parameter existence | Forwarded parameter through to CP-SAT optimizer |
| 3 | `state_service.py` | COMPLETED jobs re-entered scheduling loop | Added `j.status != JobStatus.COMPLETED` filter |
| 4 | `state_service.py` | `CP_SAT` alias not recognized | Added `.replace("_","").upper()` normalization |
| 5 | `state_service.py` | Jobs with empty `operations` passed to scheduler silently | Added `ValueError` guard |
| 6 | `test_dynamic_scheduling.py` | `result.status` used but `ScheduleResult` has no `status` field | Fixed to use `result.metrics.solver_status` with substring check |
