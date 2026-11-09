# DASHBOARD CONSISTENCY REPAIR REPORT

**System:** Dynamic Job-Shop Scheduling System  
**Report Type:** Root Cause Analysis, Workload Lifecycle, Gantt Consistency, & Repair Implementation  
**Status:** Implementation & Verification Complete (Awaiting Deployment Authorization)  
**Date:** 2026-11-01  

---

## PART 1: ROOT CAUSE INVESTIGATION & FINDINGS

### 1. Where do the 12 jobs originate?
- **Root Cause:** The 12 jobs observed in the screenshot (`JOB_001` through `JOB_010`, plus `JOB_DYN_201` and `JOB_DYN_906`) originated from two persistent sources:
  1. The 10 baseline demo jobs (`JOB_001`–`JOB_010`) seeded from `backend/data/initial_jobs.json`.
  2. The 2 dynamic user jobs (`JOB_DYN_201` and `JOB_DYN_906`) registered through the **"Add Dynamic Job"** modal during interactive testing.
- **Persistence:** All 12 jobs are persisted in the backend database (`jobs` table). They are not frontend-only mock objects.

### 2. Why was the Gantt chart empty despite 12 jobs existing?
- **Root Cause:** The Gantt chart exclusively renders `schedule.tasks`.
- In the previously deployed backend on Render, the endpoint `GET /api/schedules/latest` queried the `schedule_records` table:
  ```python
  record = db.query(ScheduleRecordModel).order_by(ScheduleRecordModel.created_at.desc()).first()
  if not record:
      return None  # -> FastAPI converted this to HTTP 404 Not Found
  ```
- Before anyone clicks **Re-Solve**, or after database re-creations, **zero schedule records exist**.
- When the frontend loaded and fetched `/api/schedules/latest`, the backend returned **HTTP 404**, which triggered the orange alert banner:
  ```text
  Notice: Not Found
  ```
  Because `schedule` was set to `null`, the Gantt chart rendered all 10 machines as `"Idle — No operations routed to M..."`.

### 3. Why did JOB_001–JOB_010 appear in the Gantt after clicking "Re-Solve"?
- When the user clicked **Re-Solve** (`runRecalculation()`), the frontend made a POST request to `/api/schedules/recalculate?algorithm=CPSAT`.
- The CP-SAT optimizer solved the scheduling problem for existing jobs, saved a new record in `schedule_records`, and returned the populated `tasks` array.
- The frontend updated `setSchedule(res.data)`, rendering the scheduled operations in the Gantt chart.

### 4. Why did the lifecycle dashboard show 0 jobs after clicking "Reset Demo", while the Gantt still showed old operations?
- **State Decoupling in `resetToDemo()`:**
  - The previous frontend implementation executed:
    ```typescript
    await axios.post(`${API_BASE}/data/reset-demo`, ...);
    await runRecalculation();
    ```
  - If a network error, auth restriction, or timing gap occurred between `/data/reset-demo` and `fetchData()`, `jobs` in React state became empty or was cleared, while the previously stored `schedule` in component state remained untouched.
  - This created a desynchronized UI where the lifecycle table showed 0 jobs (`"No jobs match the current filter or search criteria"`), while the Gantt chart continued displaying the old operations from before the reset.

### 5. Why did the header continue displaying "Workload: Demo Workload + Dynamic User Jobs"?
- In `frontend/src/App.tsx`, the text was previously hardcoded in JSX:
  ```tsx
  Workload: <strong style={{ color: '#cbd5e1' }}>Demo Workload + Dynamic User Jobs</strong>
  ```
  It was static and did not reflect the actual state of `jobs` in memory.

---

## PART 2: ARCHITECTURAL REPAIRS IMPLEMENTED

### 1. Read-Only `GET /api/schedules/latest` with Graceful Handling
- As required by architectural constraints, **GET endpoints remain strictly read-only** and do not trigger optimizer solver runs.
- `GET /api/schedules/latest` in `backend/app/main.py` now queries the latest record and returns `None` (HTTP 200 with `null` body) when empty, instead of throwing an unhandled 404.
- In `backend/app/core/state_service.py`, `seed_if_empty()` now auto-computes and stores an initial CP-SAT schedule at container boot time when seeding baseline jobs.
- In `frontend/src/App.tsx`, `fetchData(true)` safely catches missing schedules and sets `schedule = null` without popping an error notice banner.

### 2. Atomic Server-Side Reset Demo Workflow (`/api/data/reset-demo`)
`ProductionStateService.reset_to_demo_workload()` was upgraded into an atomic multi-step procedure:
1. Stops the simulation engine and resets simulation clock to `0.0`, version to `v1`.
2. Purges all stale schedule records (`ScheduleRecordModel`).
3. Resets all 10 machines to `IDLE` with 0 busy time and 0 remaining time.
4. Purges all jobs and restores the clean 10 baseline demo jobs with valid `"status": "PENDING"` operations.
5. Immediately computes a fresh baseline schedule using Google OR-Tools CP-SAT and persists it to `ScheduleRecordModel`.
6. Returns an atomic response payload:
   ```json
   {
     "status": "SUCCESS",
     "message": "Demo workload restored (10 baseline jobs) and initial schedule generated",
     "jobs": [...],
     "machines": [...],
     "sim_status": { ... },
     "schedule": { ... }
   }
   ```
7. Returns a backwards-compatible `DemoResetResult(int)` so existing test suites asserting `assert count == 10` continue to pass without modification.

### 3. Synchronized Frontend Reset Handling (`frontend/src/App.tsx`)
- In `resetToDemo()`:
  - Immediately invokes `setSchedule(null)` to eliminate phantom Gantt bars.
  - Consumes the atomic reset response payload directly to update `jobs`, `machines`, `simStatus`, and `schedule` in a single React render cycle.
  - Refreshes strategy benchmarks in the background.

### 4. Dynamic Workload Badge in Header (`frontend/src/App.tsx`)
Replaced the hardcoded label with a dynamic reactive helper:
```tsx
const getWorkloadLabel = () => {
  if (jobs.length === 0) return 'No Workload (Empty)';
  const hasDynamicJobs = jobs.some(j => j.job_id.startsWith('JOB_DYN') || !j.job_id.startsWith('JOB_0'));
  if (jobs.length === 10 && !hasDynamicJobs) return '10 Baseline Demo Jobs';
  return 'Demo Workload + Dynamic User Jobs';
};
```

---

## PART 3: TEST VERIFICATION & VALIDATION RESULTS

1. **Stage 15 Dedicated Consistency Suite (`backend/tests/test_stage15_dashboard_consistency.py`):**
   - Verified read-only `/api/schedules/latest` behavior.
   - Verified initial schedule auto-generation during database initialization.
   - Verified atomic demo reset, schedule persistence, machine IDLE state, and job synchronization.
   - Verified that dynamic job additions accurately update workload categorization without corrupting baseline state.
   - **Result:** `4 passed in 18.35s` (100% pass rate).

2. **Full Backend Regression Suite:**
   - Ran `pytest backend/tests -v` across all 15 stages.
   - **Result:** **126 passed, 0 failed** in 98.31s.

3. **Frontend Production Build:**
   - Ran `npm --prefix frontend run build`.
   - **Result:** Vite v5.4.14 built production bundle cleanly in 3.50s (`dist/assets/index-CDKRGJ87.js`, 321.10 kB).

4. **Protected Assets Integrity:**
   - Zero modifications to Stage 9 benchmarks, neural checkpoint `epn_model.pth`, or live PostgreSQL/Render environments.

---

## PART 4: DEPLOYMENT READINESS & NEXT STEPS

The fix is fully verified locally and ready for deployment:
- **Files Modified:**
  - `backend/app/core/state_service.py`
  - `backend/app/main.py`
  - `frontend/src/App.tsx`
  - `backend/tests/test_stage15_dashboard_consistency.py` (New test suite)
- **Deployment Action Required:**
  1. Commit and push the changes to GitHub `main` / `stage11-release-deployment`.
  2. Vercel and Render will automatically trigger CI/CD deployment builds.
  3. Verify public URLs (`https://dynamic-job-scheduler.vercel.app` and `https://dynamic-job-scheduler.onrender.com`).
