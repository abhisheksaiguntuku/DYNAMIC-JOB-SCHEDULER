# STAGE 4 FINAL REPORT: RESEARCH-GRADE VALIDATION & DEFECT REPAIR

**Project:** Dynamic Job-Shop Scheduling System  
**Level:** B.Tech Final Year CSE Research Project  
**Date:** 2026-10-18  
**Verification Environment:** Windows, Python 3.14.0, pytest 9.1.1, Google OR-Tools, PyTorch, FastAPI  

---

## 1. Executive Summary & Status Classification

Every claim in the project was audited against the actual source code, database operations, constraint programming optimizer, and integration test suites.

| Module / Component | Status | Summary of Evidence |
|--------------------|--------|---------------------|
| **Discrete Event Engine (Simulation)** | **PASS** | Time advancement, event loop, busy-time tracking, and SQLAlchemy JSON mutation fix verified. |
| **Heuristic Dispatchers (FCFS, SPT, EDD, CR, AGING)** | **PASS** | Dynamic ready times, machine exclusivity, and due-date ordering independently validated. |
| **CP-SAT Optimizer Formulation** | **PASS** | Disjunctive non-overlapping constraints, job precedence, release times, and multi-objective solved via OR-Tools. |
| **Independent CP-SAT Fallback Validation** | **PASS** | SPT fallback is independently verified via `ScheduleValidator.validate` before return; invalid schedules raise controlled errors (HTTP 400). |
| **Faculty Flow-Shop Benchmarks** | **PASS** | Johnson's 2-machine (50h makespan, sequence E->C->D->B->A), CDS 5-machine, and Palmer exact verification confirmed. |
| **Industrial Heterogeneous Scenarios** | **PASS** | Highly variable job durations and dynamic machine locks tested and verified. |
| **Schedule Validator** | **PASS** | Precedence, machine exclusivity, and temporal consistency constraints verified. |
| **Database & Entity Persistence** | **PASS** | SQLite persistence of jobs, machines, and schedules verified across restarts and recalculations. |
| **Machine Breakdown & Downtime Recovery** | **NOT IMPLEMENTED** | Schema contains `DOWN` status enum, but dynamic disruption events and repair loops are not implemented. Retained as explicit skipped test. |
| **Stale Schedule Rejection / Optimistic Concurrency** | **NOT IMPLEMENTED** | Concurrency versioning not implemented in data layer. Retained as explicit skipped test. |
| **EPN Neural Network Research Evidence** | **PARTIAL** | Model architecture, inference pipeline, masking, and checkpoint loading verify. Statistical proof of general improvement over CP-SAT requires held-out multi-seed benchmark runs. |
| **Full Browser-Level UI Verification** | **PARTIAL** | React/Vite dashboard and Gantt source code exist; automated end-to-end browser tests (e.g. Playwright) are not part of backend unit suite. |

---

## 2. Test Execution Evidence

### 2.1 Complete Backend Test Suite
- **Command:** `$env:PYTHONPATH="backend"; python -m pytest backend/tests/ -v --tb=short`
- **Result:**
  - **Collected:** 50 items
  - **Passed:** **48 passed**
  - **Skipped:** **2 skipped** (`test_machine_downtime_and_recovery`, `test_stale_schedule_rejection`)
  - **Failed:** **0 failed**
  - **Duration:** 17.25 seconds

### 2.2 Benchmark Test Suite
- **Command:** `$env:PYTHONPATH="backend"; python -m pytest backend/tests/test_flow_shop_benchmarks.py -v`
- **Result:**
  - `test_two_machine_benchmark_exact`: **PASSED**
  - `test_five_machine_benchmark_exact`: **PASSED**
  - `test_cds_discrepancy_reconciliation`: **PASSED**
  - **Duration:** 0.19 seconds

---

## 3. Confirmed Defects and Implemented Solutions

1. **CP-SAT Fallback Schedule Validation (Stage 4.2):**
   - *Defect:* CP-SAT falling back to SPT upon timeout/infeasibility returned the schedule without independent verification.
   - *Fix:* Added `ScheduleValidator.validate` inside `cpsat_solver.py` before returning fallback. If validation fails, raises `ValueError` with error details, and FastAPI returns HTTP 400.
2. **Engine JSON Mutation Invisibility in SQLite (Stage 4.1):**
   - *Defect:* SQLAlchemy JSON column mutation in place was ignored by SQLite dirty tracking, causing completed operations to remain `RUNNING` in DB.
   - *Fix:* Cloned operations into a fresh list in `engine.py` before assigning to `operations_json`.
3. **Completed Job Re-scheduling (Stage 4.1):**
   - *Defect:* Fully completed jobs were fed back to the solver on schedule recalculation.
   - *Fix:* Added `j.status != JobStatus.COMPLETED` filtering in `ProductionStateService.recalculate_schedule`.
4. **CP-SAT Solver Parameter Propagation (Stage 4.1):**
   - *Defect:* Solver timeout was hard-coded to 3.0s.
   - *Fix:* Propagated `time_limit_seconds` through `recalculate_schedule` to `CPSATSchedulingOptimizer.optimize`.
5. **Algorithm Alias Inconsistency:**
   - *Defect:* `"CP_SAT"` alias was unrecognized, causing fallback to heuristic dispatching.
   - *Fix:* Normalized algorithm names by stripping underscores (`.replace("_", "").upper()`).
6. **Empty Job Operation Handling:**
   - *Defect:* Jobs with 0 operations were accepted, leading to downstream solver exceptions.
   - *Fix:* Validated that every job contains at least one operation in `recalculate_schedule`.

---

## 4. Preservation Verification

All pre-existing core assets remain completely intact:
- **Database:** `backend/production_scheduler.db` (preserved, 65,536 bytes)
- **Model Checkpoints:** `backend/models/checkpoints/epn_model.pth` (preserved, 376,790 bytes)
- **Experiments:** `experiments/raw_results/`, `experiments/summaries/` (preserved)
- **Frontend Source:** `frontend/src/`, `frontend/package.json` (preserved)

---

## 5. Scope & Future Research Work

- **Machine Breakdown / Disruption Invariant:** Implementation of an event-driven failure injector and repair timeline.
- **Optimistic Concurrency Control:** Version headers for state recalculation requests.
- **EPN Generalization Study:** Multi-seed empirical benchmarking across varying job and machine cluster distributions.
