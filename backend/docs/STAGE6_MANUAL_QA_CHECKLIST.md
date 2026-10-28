# Stage 6: Manual QA Verification Checklist

This document provides step-by-step instructions for human/evaluator manual verification of Stage 6 capabilities in the Dynamic Job-Shop Scheduling System.

---

## Prerequisites
1. Start the FastAPI backend:
   ```powershell
   cd C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler
   $env:PYTHONPATH="backend"
   python -m uvicorn app.main:app --port 8001 --reload
   ```
2. Start the Vite React frontend:
   ```powershell
   cd C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler\frontend
   npm run dev
   ```
3. Open a web browser and navigate to: `http://localhost:5173` (or the port Vite outputs).

---

## Test Scenario 1: Verify 10-Machine Telemetry & Idle Display
- [ ] Observe the **10-Machine Real-Time Factory Floor Telemetry** section.
- [ ] Verify that all ten machines (M1 through M10) are displayed:
  - M1: Pattern Making
  - M2: Mould Making
  - M3: Casting (Foundry)
  - M4: Heat Treatment Furnace
  - M5: Machining Center
  - M6: Pattern & Core Prep Aux
  - M7: Mould Assembly & Dry Aux
  - M8: Pouring & Casting Aux
  - M9: Annealing & Tempering Aux
  - M10: CNC Finishing & Quality Aux
- [ ] Notice M6–M10 initially display `Util: 0%` and the Gantt chart displays: *"Idle — No operations routed to M... (Capability)"*. This is expected because baseline demo jobs only route through primary stages M1–M5.

---

## Test Scenario 2: Flexible Dynamic Job Registration (Arbitrary Route & M6–M10)
- [ ] Click the green **"Add Dynamic Job"** button in the top navigation.
- [ ] Verify the modal opens:
  - Default Job ID is auto-generated (e.g. `JOB_DYN_...`) and editable.
  - Job Name is initially blank.
  - Operation 1 has duration `0` (or blank placeholder).
- [ ] **Validation Test - Zero Duration:**
  - Fill Job Name: `Test Blade`.
  - Leave duration as `0` and click **"Register Job & Re-Optimize"**.
  - **Expected:** An alert pops up: *"Operation 1 (...) duration must be greater than zero minutes. (Zero is just a placeholder)."* The job is NOT submitted.
- [ ] **Validation Test - Blank Name:**
  - Clear Job Name, enter duration `25`.
  - Click **"Register Job & Re-Optimize"**.
  - **Expected:** Form alerts that product/job name cannot be blank.
- [ ] **Configure an Arbitrary Cross-Stage Route:**
  - Job Name: `High-Pressure Valve Assembly`.
  - Due Date: `180`.
  - Priority: `4`.
  - Change Operation 1 Machine to `M6 - Pattern & Core Prep Aux (Pattern Making)` with duration `20`.
  - Click **"Add Operation"** &rarr; sets sequence `#2`. Select `M7 - Mould Assembly & Dry Aux` with duration `25`.
  - Click **"Add Operation"** &rarr; sets sequence `#3`. Select `M4 - Heat Treatment Furnace` with duration `30`.
  - Click **"Add Operation"** &rarr; sets sequence `#4`. Select `M10 - CNC Finishing & Quality Aux` with duration `15`.
  - Click **"Register Job & Re-Optimize"**.
- [ ] **Expected Outcome:**
  - Modal closes smoothly.
  - The Gantt chart updates: rows M6, M7, M4, and M10 show the new tasks.
  - M6 and M7 are no longer idle!
  - In the telemetry panel, M6 and M10 show non-zero utilization.

---

## Test Scenario 3: Production Job Lifecycle Dashboard Verification
- [ ] Scroll to the **Production Job Lifecycle Dashboard** table.
- [ ] Verify the summary pills at the top:
  - *Queued*, *In Progress*, *Near Completion*, *Completed*, *Late / At Risk*.
- [ ] Locate the newly registered job `High-Pressure Valve Assembly`:
  - Verify Status is `Queued` (or `In Progress`).
  - Verify Progress shows `0/4`.
  - Verify Remaining duration shows `90m` (`20 + 25 + 30 + 15`).
- [ ] **Filter and Search Testing:**
  - Type `Valve` into the search box: table instantly filters down to the valve job.
  - Clear the search box.
  - Change the **Status filter** dropdown to `Queued`: only queued jobs are displayed.
  - Change the **Machine filter** dropdown to `M10`: only jobs with operations on M10 appear.
  - Reset filters to `All Statuses` and `All Machines`.

---

## Test Scenario 4: Discrete Event Simulation Advancement & Lifecycle State Transition
- [ ] Click the **"+5 min"** button repeatedly (or **"+15 min"**).
- [ ] Observe the simulation clock updating in the top bar and the crimson vertical line moving across the Gantt chart.
- [ ] When operations on M1/M6 finish:
  - Completed operations turn emerald green (`#10b981`) in the Gantt chart.
  - In the lifecycle table, completed ops progress updates (e.g. `1/5`, `2/5`).
  - Status updates to `In Progress` (amber) or `Near Completion` (purple) as progress advances.
  - The job's remaining processing time strictly decreases.
  - Precedence constraints remain strictly satisfied (subsequent operations only start after prior operations end).
- [ ] If clock passes due date, status pill switches to `Late (Past Due)` (crimson).

---

## Test Scenario 5: Gantt Chart Usability & Details Panel
- [ ] Hover your mouse over any operation block in the Gantt chart.
- [ ] Observe the top inspection card:
  - Shows Job ID, Job Name, Operation Sequence, Operation Name, Machine ID, exact Start/End time window in minutes, and Status (`COMPLETED (Historical)`, `RUNNING (Locked)`, or `PLANNED FUTURE`).
- [ ] Verify that time axis ticks at 0%, 25%, 50%, 75%, and 100% align with total makespan.

---

## Test Scenario 6: Reset Demo Workload
- [ ] Click the **"Reset Demo"** button in the header.
- [ ] Confirm the prompt dialog: *"Reset all jobs to the original 10 baseline demo jobs?..."*
- [ ] Click OK.
- [ ] **Expected Outcome:**
  - Clock resets to 0.
  - User-added jobs are removed.
  - Original 10 jobs (`JOB_001` through `JOB_010`) are restored in PENDING state.
  - Primary benchmarks (Source D flow shop matrices) in backend tests remain completely intact and unaffected.
## Additional Verification for Lifecycle & Utilization

- [ ] **Lifecycle State Transition Accuracy**
  - Verify that a job marked **In Progress** has at least one ongoing operation **and** at least one unfinished operation.
  - Ensure that **Near Completion** status only appears when a job has unfinished operations but is close to finishing, and does not overlap with **Completed**.
  - Confirm that **Completed** jobs have all operations marked as completed with no remaining work.

- [ ] **Utilization & Benchmark Consistency**
  - Check that machine utilization percentages are calculated over the documented time horizon (e.g., the last 60 minutes of simulation).
  - Validate that live demo jobs do **not** influence the fixed faculty benchmark results stored in the backend.
  - After resetting the demo workload, ensure benchmark values remain unchanged and match the baseline data.

- [ ] **Manual QA Execution**
  - Run the entire checklist in an actual browser session to confirm UI interactions behave as expected, beyond automated build and backend test success.
