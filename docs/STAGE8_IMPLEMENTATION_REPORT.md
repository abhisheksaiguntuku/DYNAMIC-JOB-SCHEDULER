# Stage 8 Implementation Report: Production Reliability

**Project:** Dynamic Job-Shop Scheduling System  
**Directory:** `C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler`  
**Date:** 2026-10-28

---

## 1. Executive Summary

Stage 8 improved the production reliability of the Dynamic Job-Shop Scheduling System across four core engineering dimensions without rebuilding the platform or altering the underlying research algorithms:

1. **Baseline Preservation & Version Control (Phase 1):** Verified the Stage 7 baseline (`63 passed, 2 skipped`), backed up the SQLite database (`production_scheduler.db`), PyTorch EPN checkpoint (`epn_model.pth`), initial seed datasets, and experimental benchmark outputs into `backups/stage8_baseline/`, and initialized a Git repository with a clean baseline commit.
2. **Simulation-State Persistence (Phase 2):** Added a minimal `SimulationStateModel` (`simulation_state` table) in SQLite to persist `sim_time`, `is_running`, `speed_multiplier`, and `state_version`. Server restarts now automatically restore the exact simulation clock and production state, and invalid/missing records are safely repaired or inferred from historical completed operations.
3. **Machine Downtime & Recovery (Phase 3):** Implemented machine breakdown (`POST /api/machines/{machine_id}/downtime`) and recovery (`POST /api/machines/{machine_id}/recover`) workflows alongside automatic countdown recovery during `advance_time`. Updated the Heuristic Scheduler (`DispatchHeuristicScheduler`), Google OR-Tools CP-SAT Optimizer (`CPSATSchedulingOptimizer`), PyTorch EPN Scheduler (`EPNJobShopScheduler`), and `ScheduleValidator` to block unavailable intervals while preserving completed operations and non-preemptive running operations.
4. **Stale-Schedule & Concurrency Protection (Phase 4):** Implemented monotonic state versioning (`state_version`) and re-entrant thread locking (`ProductionStateService._lock`). Schedule recalculations requested against an obsolete `expected_state_version` or `expected_sim_time` (or a `sim_time` behind the persisted clock) are deterministically rejected with `StaleScheduleError` (HTTP `409 Conflict`).

---

## 2. Architecture Decisions & Database Changes

### 2.1 Simulation-State Persistence (`SimulationStateModel`)
- **Schema Addition (`backend/app/database/db.py`):**
  - Table `simulation_state` with single-row primary key `id = 1`:
    - `sim_time` (`Float`, default `0.0`)
    - `is_running` (`Boolean`, default `False`)
    - `speed_multiplier` (`Float`, default `1.0`)
    - `state_version` (`Integer`, default `1`)
    - `updated_at` (`DateTime`)
- **Startup, Shutdown & Recovery Behavior (`backend/app/simulation/engine.py` & `backend/app/main.py`):**
  - On `DiscreteEventSimulator.__init__()` and FastAPI `@app.on_event("startup")`, `load_state()` reads the singleton row (`id = 1`).
  - If the row does not exist yet (e.g., upgrading an older database), `load_state()` inspects existing `JobModel` records for the maximum `end_time` of any `COMPLETED` operation so that an existing mid-simulation database does not silently reset to `0.0`.
  - If persisted fields contain corrupted values (e.g., negative `sim_time`, non-positive `speed_multiplier`, or `state_version < 1`), `load_state()` sanitizes and repairs the row in-place.
  - Every `advance_time()`, `reset()`, and `reset_to_demo_workload()` call commits the updated `sim_time` and increments `state_version` within the same database transaction.

### 2.2 Machine Availability, Breakdown & Recovery Model
- **Breakdown Policy (`ProductionStateService.set_machine_downtime`):**
  - Validates that the machine exists, `down_duration > 0`, and the machine is not already `DOWN` (conflicting duplicate breakdowns are rejected with `ValueError`).
  - **Non-Preemptive Running Operation Preservation:** If a machine is `IDLE`, its status transitions immediately to `DOWN` with `remaining_processing_time = down_duration`. If the machine is currently `BUSY` executing a running operation, the running operation is not preempted; instead, `down_duration` is added to `remaining_processing_time` while preserving `current_job_id` and `current_operation_seq`.
- **Recovery Policy (`ProductionStateService.recover_machine` & `DiscreteEventSimulator.advance_time`):**
  - Manual recovery (`recover_machine`) transitions a `DOWN` or `MAINTENANCE` machine back to `IDLE` (`remaining_processing_time = 0.0`), but rejects forced recovery if the machine is currently `BUSY` with a running job.
  - Automatic recovery in `advance_time()` decrements `remaining_processing_time` on `DOWN`/`MAINTENANCE` machines and transitions them to `IDLE` once remaining downtime reaches `0.0`.
- **Scheduler & Validator Enforcement:**
  - `CPSATSchedulingOptimizer`: Adds a fixed disjunctive interval `[cur_t_int, cur_t_int + down_dur_int]` on any `DOWN`/`MAINTENANCE` machine before `model.AddNoOverlap`, and properly looks up `BooleanValue` from stored `op_presence_vars` when alternative machines are evaluated.
  - `DispatchHeuristicScheduler` & `EPNJobShopScheduler`: Set `machine_free_time[m.machine_id] = current_time + downtime_rem` for `DOWN`/`MAINTENANCE` machines and evaluate eligible alternative machines.
  - `ScheduleValidator`: Verifies that no pending operation starts on a `DOWN` or `MAINTENANCE` machine prior to `current_time + remaining_processing_time`.

### 2.3 Stale-Schedule & Concurrency Protection
- **State Versioning (`state_version`):**
  - Incremented atomically on every state mutation: `add_job`, `set_machine_downtime`, `recover_machine`, `advance_time`, `reset`, and `reset_to_demo_workload`.
  - `recalculate_schedule` accepts optional `expected_state_version` and `expected_sim_time` parameters, verifies them before and after solver execution, and embeds `"state_version"` in `ScheduleResult.explanation`.
  - Requests with stale versions or stale simulation timestamps raise `StaleScheduleError` (mapped to HTTP `409 Conflict` in `app/main.py`).
- **Concurrency Serialization:**
  - Protected `add_job`, `set_machine_downtime`, `recover_machine`, `recalculate_schedule`, `advance_time`, and `reset` with `ProductionStateService._lock` (`threading.RLock()`) to prevent race conditions and overlapping machine assignments under concurrent requests.

---

## 3. Files Changed & Created

| File | Action | Purpose |
|------|--------|---------|
| `.gitignore` | Created | Ignore `node_modules/`, `frontend/dist/`, `__pycache__/`, `.pytest_cache/`, `backups/` |
| `backend/app/database/db.py` | Modified | Added `SimulationStateModel` (`simulation_state` table) |
| `backend/app/simulation/engine.py` | Modified | Added SQLite state persistence (`load_state`, `save_state`), automatic machine recovery countdown, and concurrency lock protection |
| `backend/app/core/state_service.py` | Modified | Added `StaleScheduleError`, `RLock` concurrency synchronization, `get_state_version`/`increment_state_version`, `set_machine_downtime`, `recover_machine`, and stale-schedule checks in `recalculate_schedule` |
| `backend/app/scheduling/heuristics.py` | Modified | Added `DOWN`/`MAINTENANCE` availability horizon and alternative machine selection |
| `backend/app/optimization/cpsat_solver.py` | Modified | Added fixed non-overlapping downtime intervals for `DOWN`/`MAINTENANCE` machines and fixed `op_presence_vars` lookup for alternative machines |
| `backend/app/ml/inference/epn_scheduler.py` | Modified | Added `DOWN`/`MAINTENANCE` machine availability offset in neural pointer decoding |
| `backend/app/scheduling/validator.py` | Modified | Added `Machine Downtime Violation` check in `ScheduleValidator.validate` |
| `backend/app/main.py` | Modified | Added startup/shutdown persistence hooks, `/api/machines/{id}/downtime` and `/api/machines/{id}/recover` endpoints, and HTTP 409 handling for stale schedules |
| `frontend/src/App.tsx` | Modified | Added machine `DOWN` telemetry badges, `Sim Breakdown (+20m)` / `Recover M/C` action buttons, and Gantt downtime overlay blocks |
| `backend/tests/test_dynamic_scheduling.py` | Modified | Implemented and enabled `test_machine_downtime_and_recovery` and `test_stale_schedule_rejection` (0 skipped tests remaining) |
| `backend/tests/test_stage41_integration.py` | Modified | Included `SimulationStateModel` in test DB cleanup fixture |
| `backend/tests/test_simulation_engine.py` | Modified | Included `SimulationStateModel` in test DB cleanup fixture |
| `backend/tests/test_stage6_production_routing.py` | Modified | Included `SimulationStateModel` in test DB cleanup fixture |
| `backend/tests/test_stage8_persistence.py` | Created | 4 deterministic tests for saving, restoring, inferring, repairing, and resetting persisted simulation state |
| `backend/tests/test_stage8_reliability.py` | Created | 6 deterministic tests for breakdowns, auto-recovery, non-preemptive running ops, conflicting events, stale schedule HTTP 409 rejection, and multi-threaded concurrency |
| `docs/STAGE8_IMPLEMENTATION_REPORT.md` | Created | Stage 8 architecture and verification documentation |

---

## 4. Verification & Actual Test Results

### 4.1 Complete Backend Test Suite
- **Command:** `cd backend ; python -m pytest -v --tb=short`
- **Exit Code:** `0`
- **Results:** **`75 passed, 0 skipped, 0 failed`** (up from baseline `63 passed, 2 skipped`)
  - Both previously skipped tests (`test_machine_downtime_and_recovery` and `test_stale_schedule_rejection`) are now fully implemented and passing.
  - 4 new persistence tests in `tests/test_stage8_persistence.py` passed.
  - 6 new downtime, recovery, stale-schedule, and concurrency tests in `tests/test_stage8_reliability.py` passed.

### 4.2 Frontend Production Build
- **Command:** `cd frontend ; npm run build`
- **Exit Code:** `0`
- **Output:**
  - `tsc -b && vite build`
  - `dist/index.html` (`0.45 kB`)
  - `dist/assets/index-DGNrK5qb.css` (`1.78 kB`)
  - `dist/assets/index-FkfjXMK4.js` (`317.06 kB`, gzip `98.47 kB`)

### 4.3 End-to-End API & Persistence Verification
- Verified via FastAPI `TestClient` against the live database:
  - Demo reset (`/api/data/reset-demo`) initializes 10 baseline jobs at `sim_time = 0.0`.
  - Advancing simulation by 15 minutes (`/api/simulation/advance?step_minutes=15`) persists `sim_time = 15.0` across a newly instantiated `DiscreteEventSimulator()`.
  - Triggering a 25-minute breakdown on `M1` (`/api/machines/M1/downtime?duration=25`) shifts all pending `M1` tasks to `>= 40.0m` (`15m + 25m`) under CP-SAT.
  - Submitting a schedule recalculation with an outdated `expected_state_version` returns HTTP `409 Conflict`.
  - Recovering `M1` (`/api/machines/M1/recover`) and resetting demo workload restores the clean baseline state.

---

## 5. Known Limitations

1. **In-Process Concurrency Lock:** `ProductionStateService._lock` (`threading.RLock`) serializes concurrent threads within a single Python process. If deployed behind a multi-worker process manager (e.g., Gunicorn with multiple Uvicorn workers), SQLite file locking and `expected_state_version` optimistic concurrency checks still prevent stale overwrites, but migrating to PostgreSQL with row-level `SELECT ... FOR UPDATE` would be recommended for distributed multi-node deployments.
2. **Library Deprecation Warnings:** SQLAlchemy `datetime.utcnow()`, Pydantic V2 `.dict()`, and FastAPI `@app.on_event` emit deprecation warnings under Python 3.14. They remain fully functional and were kept untouched to avoid unnecessary churn outside Stage 8's reliability scope.

---

## 6. Instructions for Running the Updated System

1. **Run Backend Test Suite:**
   ```powershell
   cd backend
   python -m pytest -v --tb=short
   ```
2. **Start Backend API Server:**
   ```powershell
   cd backend
   python -m uvicorn app.main:app --port 8001 --reload
   ```
3. **Build or Start Frontend:**
   ```powershell
   cd frontend
   npm run build
   npm run dev
   ```

