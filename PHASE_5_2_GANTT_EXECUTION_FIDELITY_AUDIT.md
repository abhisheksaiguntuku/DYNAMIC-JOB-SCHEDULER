# PHASE 5.2: GANTT API AND ACTUAL EXECUTION HISTORY FIDELITY AUDIT

**System:** Dynamic Job-Shop Scheduling System  
**Audit Type:** Strictly Read-Only Architecture, API, & Execution History Verification  
**Audit Scope:** Planned vs. Actual Temporal Data Representation Across Backend & Frontend  
**Database Isolation:** Tested strictly in isolated temporary SQLite databases  
**Audit Date:** 2026-11-01  

---

## 1. Executive Summary & Verdict

### **FINAL VERDICT: PASS WITH GAPS**

- **Architecture Fidelity (PASS):** The backend maintains a strict structural separation between **Actual Physical Execution** (`JobModel.operations_json` with persistent `start_time`, `end_time`, and `assigned_machine_id`) and **Planned Future Horizons** (`ScheduleRecordModel.tasks_json` with `is_running`, `is_completed`, and projected intervals).
- **Decoupled Rescheduling (PASS):** Dynamic arrivals and machine disruptions never overwrite historical execution records. Running tasks are clamped and locked, while future operations are dynamically shifted.
- **Frontend Gantt Chart (PASS):** The frontend renders distinct visual indicators for `Completed` (#10b981), `Running (Sim Lock)` (#eab308), `Planned / Planned Future` (#0284c7), and `Late / Slack Deficit` (#f43f5e), including active downtime overlays and clock markers.
- **Identified API Gap (MINOR GAP):** Machine downtime is tracked on `Machine.status` and `Machine.remaining_processing_time`, but is **not** returned as a discrete entry in `ScheduleResult.tasks`. The frontend calculates the downtime visual bar directly by combining the simulation clock with `machine.remaining_processing_time` rather than consuming a unified calendar interval from `/schedules/latest`.

---

## 2. Architecture & Data Structure Findings

| Entity / Dimension | Planned Schedule Model (`ScheduledTask`) | Actual Execution Model (`Operation`) |
| :--- | :--- | :--- |
| **Storage Table** | `schedule_records` (`tasks_json`) | `jobs` (`operations_json`) & `machines` table |
| **API Endpoint** | `GET /api/schedules/latest` | `GET /api/jobs`, `GET /api/machines` |
| **Start Timestamp** | `t.start_time` (projected or locked) | `op.start_time` (recorded at physical dispatch) |
| **End Timestamp** | `t.end_time` (projected completion) | `op.end_time` (recorded when simulator finishes op) |
| **Machine Field** | `t.machine_id` | `op.assigned_machine_id` (fallback to `op.machine_id`) |
| **Status Flags** | `is_running: bool`, `is_completed: bool` | `status: PENDING \| RUNNING \| COMPLETED` |
| **Downtime Inclusion**| Excluded from tasks array; machine blocked via horizon constraint | Represented on machine: `status == DOWN`, `remaining_processing_time` |

### Key Code Mechanisms Verified:
1. **Physical Dispatch (`DiscreteEventSimulator._dispatch_ready_operations`):**
   When an operation is dispatched onto an IDLE machine at `t`, the simulator sets:
   - `op.status = OperationStatus.RUNNING`
   - `op.start_time = self.sim_time`
   - `op.assigned_machine_id = chosen_m_id`
   - `machine.current_job_id = job.job_id`
   - `machine.remaining_processing_time = op.duration`
2. **Scheduler Horizon Separation (`CPSATSchedulingOptimizer.optimize`):**
   - **Historical / Completed Operations:** Appended directly to `scheduled_tasks` with `is_completed = True`, preserving exact recorded `start_time` and `end_time`.
   - **Running Operations:** Clamped with `is_running = True`, fixing their start time to `op.start_time` and locking the machine until `cur_time + remaining_processing_time`.
   - **Future Pending Operations:** Assigned variable intervals starting $\ge \text{current\_time}$.
   - **Horizon Completion:** Once all operations in all jobs are `COMPLETED`, `recalculate_schedule` returns `tasks = []` and `queue_length = 0` because there is no remaining work to schedule.

---

## 3. Actual vs. Planned Execution Verification (Controlled Experiment)

Using an isolated SQLite environment, a controlled scenario was evaluated:
- **Baseline:** `JOB_BASE_1` on `M1` (dur: 10) $\to$ `M2` (dur: 10); `JOB_BASE_2` on `M2` (dur: 6).
- **Execution at $t = 0$:**
  - Planned: `JOB_BASE_1` Op 1 on `M1` ($0 \to 10$); `JOB_BASE_2` Op 1 on `M2` ($0 \to 6$).
- **Disruption at $t = 4.0$:**
  - Dynamic injection of `JOB_URG_3` (Priority 5, dur: 5) with primary `M1` and alternative `M2`.
  - Machine breakdown on `M1` (8.0 min repair window).
  - Physical non-preemption extended `M1` unavailable window to $4.0 + 6.0\text{ (remaining op)} + 8.0\text{ (repair)} = 18.0$.
- **Recalculation at $t = 4.0$:**
  - `JOB_BASE_1` Op 1 locked on `M1` with `is_running = True` ($0 \to 18$).
  - `JOB_BASE_2` Op 1 locked on `M2` with `is_running = True` ($0 \to 6$).
  - Because `M1` is blocked until $t = 18$ and `M2` becomes free at $t = 6$, the optimizer routes `JOB_URG_3` to alternative machine `M2` starting at $t = 6$.
- **Verification of Separate Representation:**
  - At no point did recalculation overwrite the historical start timestamps of the running jobs.
  - The planned schedule and actual physical execution were allowed to legitimately diverge upon disruption while remaining synchronized on machine constraints.

---

## 4. API Response Structure Examples

### A. Planned Schedule Task (`GET /api/schedules/latest`)
```json
{
  "job_id": "JOB_BASE_01",
  "job_name": "Turbine Shaft",
  "operation_sequence": 1,
  "operation_name": "Turn Shaft",
  "machine_id": "M1",
  "start_time": 0.0,
  "end_time": 10.0,
  "duration": 10.0,
  "is_running": false,
  "is_completed": true
}
```

### B. Actual Physical Operation (`GET /api/jobs`)
```json
{
  "sequence": 1,
  "name": "Turn Shaft",
  "machine_id": "M1",
  "duration": 10.0,
  "alternative_machines": [],
  "status": "COMPLETED",
  "start_time": 0.0,
  "end_time": 10.0,
  "assigned_machine_id": "M1"
}
```

### C. Active Machine Downtime (`GET /api/machines`)
```json
{
  "machine_id": "M4",
  "name": "Grinding Unit 1",
  "capability": "Grinding",
  "status": "DOWN",
  "current_job_id": null,
  "remaining_processing_time": 10.0,
  "total_busy_time": 12.0
}
```

---

## 5. Frontend Gantt Implementation Review

Inspection of `frontend/src/App.tsx` (lines 980–1160) revealed the following rendering mechanisms:

1. **Color Discrimination:**
   - **Completed:** Green (`#10b981`) when `t.is_completed === true`.
   - **Running:** Amber (`#eab308`) when `t.is_running === true`.
   - **Planned Future:** Blue (`#0284c7`) when neither completed nor running.
   - **Tardy Risk:** Crimson (`#f43f5e`) when `t.end_time > job.due_date`.
2. **Clock Marker:**
   - Red vertical line dynamically rendered at `(currentSim / maxHorizon) * 100%`.
3. **Machine Downtime Visualization:**
   - Handled directly in the timeline bar:
     ```tsx
     {(m.status === 'DOWN' || m.status === 'MAINTENANCE') && m.remaining_processing_time > 0 && (
       <div style={{
         left: `${(currentSim / maxHorizon) * 100}%`,
         width: `${(m.remaining_processing_time / maxHorizon) * 100}%`,
         backgroundColor: 'rgba(244, 63, 94, 0.28)',
         border: '1px dashed #f43f5e'
       }}>
         DOWN ({m.remaining_processing_time}m)
       </div>
     )}
     ```
   - **Finding:** The frontend renders downtime accurately on the machine row by combining `currentSim` with `m.remaining_processing_time`. However, because this is computed client-side from the machine object rather than schedule task intervals, historical past downtime that has already expired is not preserved in the Gantt timeline.

---

## 6. Recommendations (No Code Changed)

1. **Include Downtime Windows in `ScheduleResult.tasks`:**
   In future versions, the optimizer could output dedicated synthetic tasks (`job_id: "__DOWNTIME__"`, `is_downtime: true`) so that historical and planned downtime intervals are preserved uniformly in the schedule timeline.
2. **Explicit Historical Log for Completed Downtime:**
   Currently, once a machine recovers, `remaining_processing_time` resets to `0.0` and the machine returns to `IDLE`. Persisting a `downtime_history` array on `MachineModel` would allow the Gantt chart to show when breakdowns occurred in the past.

---

## 7. Verification Confirmation

- All experiments were conducted strictly in isolated temporary databases.
- Zero connections were made to Neon PostgreSQL, Render, or Vercel.
- Protected SHA-256 hashes for Stage 9 benchmarks and EPN checkpoints remain completely untouched.
- No production backend or frontend code was modified.

