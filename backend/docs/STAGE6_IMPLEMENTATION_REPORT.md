# Stage 6: Industrial Dashboard, Flexible Job Routing & Production Lifecycle Implementation Report

## Executive Summary
In Stage 6, the Dynamic Job-Shop Scheduling System was upgraded to support industrial-grade dynamic operations, full 10-machine telemetry, flexible cross-stage routing, and end-to-end production job lifecycle tracking.

**Final Test Suite Verification:**
- **65 tests collected**
- **63 passed**
- **2 skipped** (`test_machine_downtime_and_recovery`, `test_stale_schedule_rejection` — planned future enhancements)
- **0 failed**
- **Exit code 0**
- **Frontend build:** Clean production build via `tsc -b && vite build` (1962 modules transformed, built in 2.25s)

---

## 1. Task 1: Redesigned Flexible Job Registration Form

### Defects in Previous Implementation:
- Job registration form was hardcoded to a fixed sequence: `M1 → M2 → M3 → M4 → M5`.
- Machines M6–M10 were completely unavailable in the UI form.
- Processing times were prefilled with arbitrary positive values.
- Form lacked positive-duration validation and dynamic add/remove operation controls.

### Implementation Fixes in `frontend/src/App.tsx`:
1. **Dynamic Machine Population from Backend:** The form fetches the real 10-machine list via `GET /api/machines`. The dropdown displays `machine_id`, machine name, and capability (e.g. `M7 - Mould Assembly & Dry Aux (Mould Making)`).
2. **Arbitrary Valid Routes:** Jobs can start on any eligible machine (e.g. M6, M7, M10), route through any sequence of machines, and have variable operation counts.
3. **Repeated Machine Use:** Jobs can revisit the same machine across multiple steps (e.g. Rough Machining on M5 -> Heat Treatment on M4 -> Finish Machining on M5).
4. **Positive Duration Requirement:** Processing-time inputs initialize to `0` as an explicit placeholder. The form blocks submission if duration is `<= 0`.
5. **Backend Schema & Validation:** Added `Field(gt=0.0)` in `Operation` model and explicit validation in `ProductionStateService.add_job()` to reject empty operations, non-positive durations, duplicate job IDs, and invalid machine IDs.

---

## 2. Task 2: Operationalizing All Ten Machines (M1–M10)

### Verification & Findings:
- Database contains 10 industrial machines:
  - **M1–M5 (Primary Process Flow):** Pattern Making (M1), Mould Making (M2), Casting (M3), Heat Treatment (M4), Machining (M5).
  - **M6–M10 (Auxiliary Parallel Stations):** Pattern & Core Prep Aux (M6), Mould Assembly & Dry Aux (M7), Pouring & Casting Aux (M8), Annealing & Tempering Aux (M9), CNC Finishing & Quality Aux (M10).
- Baseline seed data (`initial_jobs.json`) only routes jobs through M1–M5; therefore, M6–M10 correctly appeared idle initially without implying a system defect.
- Scheduling engines (OR-Tools CP-SAT, FCFS, SPT, EDD, CR, Aging, EPN) fully support M6–M10 operations when jobs are routed to them.
- In `backend/tests/test_stage6_production_routing.py`, verified:
  - Job starting on M6 (`test_job_starting_on_m6_operational`)
  - Job starting on M7 (`test_job_starting_on_m7_operational`)
  - Job starting on M10 (`test_job_starting_on_m10_operational`)
  - Cross-stage mixed route `M1 -> M7 -> M8 -> M4 -> M10` (`test_mixed_cross_stage_routing_m1_m5_and_m6_m10`)
  - Repeated machine use on M5 (`test_repeated_machine_use_in_single_job`)
- Documented machine utilization denominator: `utilization = (busy_time / makespan) * 100%`. Idle machines with 0 tasks are accurately displayed as idle.

---

## 3. Task 3: Production Job Lifecycle Dashboard

### Implemented Capabilities in `frontend/src/App.tsx`:
1. **5 Concrete Lifecycle States:**
   - **Queued / Waiting:** Job has not yet started (no operations completed or running).
   - **In Progress:** At least one operation has completed or is currently running on a machine.
   - **Near Completion:** Rule documented and enforced: either `>= 70%` of operations are completed or remaining processing time is `<= 35` minutes with at least 1 op completed.
   - **Completed:** All operations are finished (`j.status == 'COMPLETED'`). Completed jobs do not reappear in the active waiting queue.
   - **Late / At Risk:** Distinguishes already late jobs (`current_sim_time > due_date`) from predicted risk (`estimated_completion > due_date`).
2. **Telemetry Per Job:**
   - Job ID, product name, product type.
   - Current stage and assigned machine.
   - Completed vs. total operations progress bar.
   - Actual or simulated start time.
   - Estimated completion time from scheduler.
   - Due time and remaining processing duration.
   - Delay / risk indicators with exact slack difference.
3. **Filtering and Search:**
   - Real-time search by Job ID, name, or product type.
   - Filter dropdown by Lifecycle Status (Queued, In Progress, Near Completion, Completed, Late/At Risk).
   - Filter dropdown by Machine assignment (M1 through M10).
4. **Summary Header:** Compact pill badges showing live counts of Queued, In Progress, Near Completion, Completed, and Late/At Risk jobs.

---

## 4. Task 4: Enhanced Dark Industrial Gantt Chart

### Implemented Improvements:
1. **All 10 Machine Rows Displayed:** M1 through M10 with machine IDs, display names, and capabilities.
2. **Current Simulation Clock Indicator:** High-contrast vertical crimson indicator line showing current simulation time relative to scheduled horizon.
3. **State-Based Color Coding:**
   - Completed (historical): Industrial Emerald Green (`#10b981`)
   - Running (active non-preemptible commitment): Warning Amber (`#eab308`)
   - Planned Future: Electric Cyan/Blue (`#0284c7`)
   - Late / Risk Operation: Crimson Rose (`#f43f5e`)
4. **Hover Details Panel:** Interactive inspection card showing Job ID, product name, operation sequence, operation name, machine ID, exact start/end time window, duration, and status.
5. **Idle State Notice:** Explicit, italicized notice on idle machine rows clarifying why no operations are currently allocated.
6. **Time Axis Scale:** Proportional tick marks at 0%, 25%, 50%, 75%, and 100% of maximum makespan horizon.

---

## 5. Task 5: Strict Separation of Test Data vs. Research Benchmarks

### Architectural Separation:
1. **Demo Workload (`backend/data/initial_jobs.json`):**
   - 10 baseline industrial jobs (`JOB_001` through `JOB_010`).
   - Visibly tagged in dashboard header.
   - Can be cleanly reset at any time via `POST /api/data/reset-demo` or the "Reset Demo" button in the UI without affecting other data.
2. **User-Entered Dynamic Production Jobs:**
   - Generated dynamically via the Add Dynamic Job modal.
   - Validated against positive duration and machine registry.
3. **Faculty Benchmark Instances (`backend/app/scheduling/flow_shop/`):**
   - Source D Two-Machine Benchmark: fixed processing times matrix `A:(10,2), B:(16,8), C:(6,10), D:(12,14), E:(4,12)`, optimal sequence `E -> C -> D -> B -> A`, makespan `50.0h`.
   - Source D Five-Machine Benchmark: 5-job 5-machine matrix tested under Johnson, Palmer, CDS, and NEH.
   - Benchmarks run against their own fixed in-memory data structures in `test_flow_shop_benchmarks.py` and are completely isolated from SQLite database state.
4. **Research Experiment Scenarios (`backend/app/experiments/runner.py`):**
   - Generates reproducible synthetic instances via explicit PRNG seeds (`seed=42`).

---

## 6. Files Changed & Added

| File | Status | Description |
|---|---|---|
| `backend/app/schemas/models.py` | Modified | Added `Field(gt=0.0)` validation on `Operation.duration`. |
| `backend/app/core/state_service.py` | Modified | Added validation for duration > 0, machine existence in `add_job()`, and added `reset_to_demo_workload()`. |
| `backend/app/main.py` | Modified | Added `POST /api/simulation/reset` and `POST /api/data/reset-demo` endpoints. |
| `backend/app/ml/recommender.py` | Modified | Made scenario generator resilient to small job lists (`min_sample = min(3, len(base_jobs))`). |
| `backend/tests/test_stage41_integration.py` | Modified | Updated fallback validation test to assert `HTTPException(400)` directly on endpoint call. |
| `backend/tests/test_stage6_production_routing.py` | Created | 10 new automated integration tests covering positive duration validation, non-existent machine rejection, M6/M7/M10 starting jobs, mixed routes, repeated machine use, and demo reset. |
| `frontend/src/App.tsx` | Modified | Complete redesign: dynamic M1–M10 machine selection, arbitrary routing, 0 placeholder validation, lifecycle dashboard with search/filters, enhanced 10-machine Gantt chart with clock line and hover inspector, and demo reset button. |
| `backend/docs/STAGE6_IMPLEMENTATION_REPORT.md` | Created | Comprehensive implementation report. |
| `backend/docs/STAGE6_MANUAL_QA_CHECKLIST.md` | Created | Step-by-step manual QA verification checklist. |

---

## 7. Known Limitations & Future Work
1. **Machine Breakdown & Recovery:** Currently simulated conceptually; full dynamic recovery rescheduling tests remain skipped pending discrete maintenance event triggers.
2. **Stale Schedule Concurrency Rejection:** Optimistic locking / revision tokens on simultaneous recalculations remain skipped pending multi-user concurrency design.
3. **Browser Automation:** Headless browser integration tests are pending; detailed manual QA steps provided in `STAGE6_MANUAL_QA_CHECKLIST.md`.
