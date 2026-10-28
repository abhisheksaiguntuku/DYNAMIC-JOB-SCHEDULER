# STAGE 11 FACULTY DEMONSTRATION SCRIPT
## Step-by-Step Live Walkthrough of the AI-Assisted Dynamic Job-Shop Scheduling System

**Estimated Duration:** 10–12 minutes  
**Pre-Demo Check (2 minutes prior):**
- If presenting from the public deployment, open the Render backend `/api/health` endpoint 2 minutes early to wake the free-tier container, then open the frontend dashboard and click **Reset Demo** to start from `Sim Clock = 0 min` with the 10 baseline industrial jobs (`JOB_001`–`JOB_010`).
- If presenting locally, ensure `uvicorn app.main:app --host 127.0.0.1 --port 8001` and `npm run dev` (`http://localhost:5173`) are running.

---

### Step 1: System Overview & Flexible Job Creation Across 10 Machines (`M1–M10`)
1. **Point out the 10-Machine Telemetry Grid:**
   - Explain that `M1–M5` represent the core 5-stage foundry/machining line (`Pattern Making`, `Mould Making`, `Casting`, `Heat Treatment`, `Machining`), while `M6–M10` represent auxiliary and parallel industrial stations (`3D Sand Printing`, `Robotic Core Assembly`, `Vacuum Induction Melting`, `Cryogenic Tempering`, `5-Axis CNC Finishing`).
2. **Click "+ Add Dynamic Job" to open the registration modal:**
   - Enter **Product / Job Name:** `High-Speed Bogie Bolster`
   - Set **Priority:** `5` (highest priority) and **Due Date:** `180` mins.
   - Configure a **custom multi-machine route** (including auxiliary machines `M6–M10` or repeated visits):
     - **Op #1:** `M6 - 3D Sand Printing` (`Duration = 18 min`)
     - Click **+ Add Operation** &rarr; **Op #2:** `M8 - Vacuum Induction Melting` (`Duration = 25 min`)
     - Click **+ Add Operation** &rarr; **Op #3:** `M10 - 5-Axis CNC Finishing` (`Duration = 20 min`)
     - Click **+ Add Operation** &rarr; **Op #4 (Re-Entrant Pass):** `M6 - 3D Sand Printing` (`Duration = 12 min`)
3. **Demonstrate Input Validation:**
   - Briefly clear one operation's duration to `0` and click **Register Job & Re-Optimize** to show that zero/negative durations are immediately blocked by both frontend and backend validation (`HTTP 400`).
   - Restore the duration to `12` min and click **Register Job & Re-Optimize**.

---

### Step 2: Running & Comparing Scheduling Algorithms
1. **Inspect the "AI Strategy Advisor & Dispatch" panel:**
   - Show the ML Strategy Recommender's real-time confidence score and rationale based on shop-floor contention and slack.
2. **Switch the "Active Scheduling Engine" dropdown across algorithms and click "Re-Solve":**
   - **`Google OR-Tools CP-SAT`:** Point out the lowest makespan ($C_{\max}$) and lowest total tardiness in the top KPI bar, along with the solver status (`OPTIMAL` or time-bounded `FEASIBLE`) and compute latency.
   - **`SPT (Shortest Processing Time)` & `FCFS`:** Show sub-5ms heuristic execution and compare the resulting makespan and tardiness increases.
   - **`PyTorch Pointer Network (EPN)`:** Show neural inference (`NEURAL_PREDICTED_FEASIBLE`) executing from the trained checkpoint (`epn_model.pth`).
3. **Scroll down to the "Fair Algorithm Benchmark & Performance Matrix" table:**
   - Highlight the side-by-side comparison across `FCFS`, `SPT`, `EDD`, `CR`, `AGING`, and `OR-TOOLS CP-SAT` evaluated on the exact same current shop-floor state.

---

### Step 3: Visualizing the Schedule in the 10-Machine Gantt Chart
1. **Inspect the "10-Machine Dynamic Production Gantt Schedule":**
   - Show that all 10 machines (`M1–M10`) are rendered on a unified timeline from `0m` to $C_{\max}$.
   - Point out that your newly created job (`High-Speed Bogie Bolster`) is scheduled across `M6`, `M8`, and `M10` with strict precedence (`Op1` finishes before `Op2` starts, `Op2` finishes before `Op3` starts, and `Op3` finishes before re-entrant `Op4` starts on `M6`).
2. **Hover over operation blocks:**
   - Show the fixed-height telemetry detail bar above the Gantt chart displaying `Job ID`, `Operation Sequence`, `Assigned Machine`, exact `[start_time -> end_time]` window, and execution status (`PLANNED FUTURE`, `RUNNING (Locked)`, or `COMPLETED (Historical)`).

---

### Step 4: Advancing the Simulation Clock & Dynamic Rescheduling
1. **Click "+15 min" twice in the top Sim Clock bar (advancing `Sim Clock` to `30 min`):**
   - Point out the red vertical **Clock Marker** line at `30m` on the Gantt chart.
   - In the **Production Job Lifecycle Dashboard**, show jobs automatically transitioning from **Queued** (blue) to **In Progress** (yellow), **Near Completion** (purple), and **Completed** (green).
   - In the **10-Machine Telemetry Grid**, show active machines marked `BUSY` with their exact `remaining_processing_time`.
2. **Add another urgent job at `t = 30 min` and re-solve:**
   - Point out that **Completed** operations (green blocks left of `30m`) and **Running** operations (yellow blocks straddling `30m`) remain 100% locked at their original timestamps—only pending future operations are rescheduled around them.

---

### Step 5: Demonstrating Machine Downtime & Recovery
1. **Trigger a Breakdown on `M2` or `M3`:**
   - In the **10-Machine Telemetry Grid**, click **`Sim Breakdown (+20m)`** on `M2`.
   - Explain the **non-preemptive safety policy**: if `M2` is `IDLE`, it immediately enters `DOWN` for `20m` (rendered as a red dashed `DOWN (20m)` block on the Gantt chart) and all pending operations on `M2` are automatically right-shifted past the repair window. If `M2` is `BUSY`, the currently running operation finishes without corruption and the repair duration extends the machine's unavailable window.
2. **Recover the Machine:**
   - Click **`Recover M/C`** on `M2` to restore it to `IDLE` and trigger automatic schedule recalculation.
3. **Click "Reset Demo":**
   - Show that clicking **Reset Demo** cleanly restores the 10 baseline jobs (`JOB_001`–`JOB_010`) at `Sim Clock = 0 min` while keeping all Stage 9/10 research benchmark files untouched.

---

### Step 6: Explaining the Dual Schedule Validation Architecture (`IndependentScheduleAuditor`)
- Explain to the committee that the project enforces a **zero-trust validation architecture**:
  1. **Runtime Validator ([`ScheduleValidator.validate()`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/scheduling/validator.py)):** Checks machine exclusivity, downtime windows, `BUSY` machine locks, duplicate operations, duration/interval equality, intra-job precedence, and release-time boundaries on every API schedule calculation.
  2. **Zero-Shared-Code Research Auditor ([`IndependentScheduleAuditor`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/experiments/stage10_runner.py)):** Built in Stage 10 without sharing any code with `ScheduleValidator`. It independently verified all **$650$ experimental trials** ($280$ Stage 9 trials + $70$ Tier 5 Repeated-Routing trials + $300$ EPN Ablation trials) with **$100.0\%$ validity and $0$ constraint violations**.

---

### Step 7: Presenting Honest Experimental Findings & Limitations
Present the key empirical findings from [`docs/STAGE10_EXPERIMENTAL_REPORT.md`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/docs/STAGE10_EXPERIMENTAL_REPORT.md) transparently:
1. **CP-SAT vs. Classic Dispatching Heuristics (Tiers 1–5):**
   - Across contended multi-job tiers (Tier 2 Medium, Tier 3 Dynamic Breakdown, Tier 4 Large Scale, and Tier 5 Repeated Routing), time-bounded **CP-SAT (`2.0s–2.5s`) reduces mean makespan by `38.12%–53.10%` and mean total tardiness by `73.04%–95.95%`** compared to `SPT` ($p_{\text{Holm}} \le 2.5 \times 10^{-5}$).
   - On small 6-job instances (`TIER1_SMALL`), `FCFS` (`155.70m`) matches `CP-SAT` (`153.10m`, $p = 0.467$) on makespan, though `CP-SAT` reduces total tardiness by `54.54%` ($p_{\text{Holm}} = 0.0028$).
   - Clarify that CP-SAT proves global `OPTIMAL` status on **$15/50$ ($30.0\%$)** of benchmark instances within the 2.0s–2.5s budget and returns high-quality `FEASIBLE` schedules on the remaining $70.0\%$.
2. **EPN Root-Cause Diagnosis & Controlled Ablation Study:**
   - Explain why the baseline EPN (`EPN_BASELINE`) lagged behind `SPT` in Stage 9: our Stage 10 trace and ablation study proved that **$>99\%$ of EPN's makespan inflation was caused by job-sequential outer-loop decoding** (`for j in sorted_jobs`), whereas the positive neural slot offset (`slot * 2.0`) accounted for `<0.60%`.
   - When we replace job-sequential decoding with chronological **operation-level ready-queue decoding guided by pure EPN predicted slots (`EPN_ABLATION_B_OP_READY_DECODING`)** — without retraining the checkpoint or using SPT duration tie-breaking — EPN makespan drops by **`49.25%–71.13%`** across all 5 tiers ($p_{\text{Holm}} \le 8.1 \times 10^{-5}$).
   - Be explicit about the **internal validity nuance**: part of `EPN_ABLATION_B`'s improvement over `DispatchHeuristicScheduler` (`SPT`/`FCFS`) stems from chronological earliest-start event ordering (`earliest_start` primary key over a scalar machine watermark) in addition to EPN's neural slot tie-breaking (`pred_slot` secondary key).

