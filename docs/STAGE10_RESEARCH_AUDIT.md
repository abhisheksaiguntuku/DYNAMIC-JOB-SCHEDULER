# STAGE 10 RESEARCH AUDIT REPORT
## Experimental Methodology, Independent Schedule Verification, Statistical Corrections & EPN Root-Cause Diagnosis

**Project:** Dynamic Job-Shop Scheduling System  
**Branch:** `stage10-research-audit` (branched from Stage 9 baseline commit `7d0e3be`)  
**Audit Date:** 2026-10-28  
**Audit Artifacts Directory:** [`backend/experiments/stage10_audit/`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_audit/)

---

## 1. Executive Summary

Stage 10 conducted a comprehensive, zero-trust research audit of the Stage 9 benchmark suite ($280$ trials across $4$ tiers), the schedule validation pipeline ([`validator.py`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/scheduling/validator.py)), the Google OR-Tools CP-SAT optimizer ([`cpsat_solver.py`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/optimization/cpsat_solver.py)), the classic dispatching heuristics ([`heuristics.py`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/scheduling/heuristics.py)), and the PyTorch Enhanced Pointer Network scheduler ([`epn_scheduler.py`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/ml/inference/epn_scheduler.py)).

### Key Audit Conclusions
1. **Stage 9 Artifact Preservation & Integrity (`280/280` Valid):** All original Stage 9 CSV, JSON, SVG, report, and PyTorch checkpoint files are 100% preserved with identical SHA-256 cryptographic hashes before and after Stage 10 execution. All $280$ Stage 9 trials pass both the strengthened [`ScheduleValidator.validate()`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/scheduling/validator.py#L6-L103) and the newly constructed zero-shared-code [`IndependentScheduleAuditor.audit_schedule()`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/experiments/stage10_runner.py#L112-L344) with **zero constraint violations**.
2. **Correction of Stage 9 Narrative & Statistical Claims:** Six specific numerical, statistical, and methodological nuances were identified in [`STAGE9_EXPERIMENTAL_REPORT.md`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/docs/STAGE9_EXPERIMENTAL_REPORT.md) and [`stage9_benchmark.py`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/experiments/stage9_benchmark.py) and formally corrected in [`stage10_claims_correction_table.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_audit/stage10_claims_correction_table.csv):
   - **CLAIM-01 (Makespan Reduction Range):** Section 9 Conclusion 1 quoted a `"47%–53%"` makespan reduction for CP-SAT vs. SPT across medium, dynamic breakdown, and large-scale tiers, omitting the `38.12%` reduction on `TIER3_DYNAMIC_BREAKDOWN` (`217.40m` vs. `351.30m`) that was reported in Section 6. Furthermore, on `TIER1_SMALL`, `FCFS` (`155.70m`) outperformed `SPT` (`255.80m`) and was statistically indistinguishable from `CP-SAT` (`153.10m`, paired $t = 0.760, p = 0.467$).
   - **CLAIM-02 (Runtime Speedup Range):** Mean runtime speedup of `SPT` relative to `CP-SAT` spans **`171.4x–797.4x`** (`298.1x` on Tier 1, `797.4x` on Tier 2, `706.6x` on Tier 3, `171.4x` on Tier 4) rather than `"170x–700x"`.
   - **CLAIM-03 (Small-Sample $95\%$ Confidence Intervals):** Stage 9 used the asymptotic normal multiplier $z_{0.975} = 1.96$ for $n = 10$ seeds ($\text{df} = 9$) instead of the exact Student-$t$ critical value $t_{0.975, 9} = 2.26216$, understating marginal $95\%$ CI half-widths by $13.36\%$ (exact Student-$t$ CIs are $+15.42\%$ wider). Stage 10 recomputes all tables with exact Student-$t$ CIs, medians, interquartile ranges (IQR), paired differences, paired Student $t$-tests, Wilcoxon signed-rank tests, Holm-Bonferroni step-down corrections, and paired Cohen's $d_z$.
   - **CLAIM-04 (Proven `OPTIMAL` vs. Time-Bounded `FEASIBLE` CP-SAT Solutions):** Across the $40$ Stage 9 instances (and $10$ new Tier 5 instances), CP-SAT proves global optimality within its $2.0\text{s–}2.5\text{s}$ wall-clock limit on **$12/40$ ($30.0\%$) Stage 9 instances** ($10/10$ Tier 1, $2/10$ Tier 2, $0/10$ Tier 3, $0/10$ Tier 4) and **$3/10$ ($30.0\%$) Tier 5 instances**. On Tiers 2–5, CP-SAT must be described as a *time-bounded constraint-programming optimizer* rather than an exact global optimum solver.
   - **CLAIM-05 (Causal Decomposition of EPN Underperformance):** Stage 9 hypothesized two causes for EPN's underperformance: (a) the job-sequential outer loop (`for j in sorted_jobs`) and (b) the positive neural slot offset (`slot * 2.0`). Stage 10's controlled ablation proves that **removing the positive slot offset alone (`EPN_ABLATION_A_NO_OFFSET`) reduces mean makespan by only $0.16\%\text{–}0.60\%$**, whereas **replacing job-sequential decoding with operation-level ready-queue decoding guided by pure EPN predicted slots (`EPN_ABLATION_B_OP_READY_DECODING`) reduces mean makespan by $49.25\%\text{–}71.13\%$** across all cinco tiers ($p_{\text{Holm}} \le 8.1 \times 10^{-5}$).
   - **CLAIM-06 (Multi-Threaded CP-SAT Re-Execution Drift):** All $240/240$ deterministic trials (`FCFS`, `SPT`, `EDD`, `CR`, `AGING`, `EPN`) reproduce with $0.00$ discrepancy upon re-execution. However, [`CPSATSchedulingOptimizer.optimize`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/optimization/cpsat_solver.py#L213) sets `num_search_workers = 4` with a wall-clock timeout, causing $18/40$ CP-SAT trials on non-trivial instances to exhibit minor multi-threaded incumbent drift when re-run under varying CPU thread scheduling.

---

## 2. Baseline Preservation & Cryptographic Hash Verification

Before creating any Stage 10 code or running any experiments, all Stage 9 artifacts and checkpoints were backed up to `backups/stage10_baseline_snapshot/` and verified via SHA-256 hashes before and after all Stage 10 runs:

| File Path | Expected & Verified SHA-256 Hash | Status |
| :--- | :--- | :--- |
| [`backend/models/checkpoints/epn_model.pth`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/models/checkpoints/epn_model.pth) | `55F9E9227E1F527C86678AEF0565B16B92D450B2FC2D68ABADB0D3DF10970FA6` | **MATCH (UNCHANGED)** |
| [`backend/experiments/stage9_benchmark/stage9_raw_results.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage9_benchmark/stage9_raw_results.csv) | `530BC6FE111B9ECE413CDB1FDDFC2DCF4F3CE182DF9EF706C2F86B145CC234F0` | **MATCH (UNCHANGED)** |
| [`backend/experiments/stage9_benchmark/stage9_raw_results.json`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage9_benchmark/stage9_raw_results.json) | `385197957B111C62C97EEC4D398457DB6953459E97F48E125151B6B99AF6B421` | **MATCH (UNCHANGED)** |
| [`backend/experiments/stage9_benchmark/stage9_summary_table.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage9_benchmark/stage9_summary_table.csv) | `CACEFB149B5FDC42865334873B9526F5685C7A1E10B26D21C44FAFF09E4403F2` | **MATCH (UNCHANGED)** |
| [`backend/experiments/stage9_benchmark/stage9_summary_table.json`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage9_benchmark/stage9_summary_table.json) | `F696C7718EC79F255EBFDE4E5007AE3CD181C2EEC5296B5D2C007E52D11C1EBC` | **MATCH (UNCHANGED)** |
| [`backend/experiments/stage9_benchmark/stage9_manifest.json`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage9_benchmark/stage9_manifest.json) | `8EA804B96FF02899D432FBB46B6DC60C1F96F330EC5AAFA2B7A09DB0810B24CC` | **MATCH (UNCHANGED)** |

---

## 3. Phase B Audit: Complete Stage 9 Claims Correction Table

All $280$ trials in [`stage9_raw_results.json`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage9_benchmark/stage9_raw_results.json) were audited against regenerated instances and independently recomputed metrics in [`stage10_audit_recomputed_summary.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_audit/stage10_audit_recomputed_summary.csv).

| Claim ID | Source Location | Original Stage 9 Statement | Exact Recomputed Audit Values | Audit Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **CLAIM-01** | `docs/STAGE9_EXPERIMENTAL_REPORT.md` Sec. 9 Conclusion 1 | *"CP-SAT consistently achieves the lowest makespan and total tardiness across all four tiers, reducing mean makespan by 47%–53% and mean total tardiness by 73%–89% compared to the strongest dispatching heuristic (SPT) on medium, dynamic breakdown, and large-scale tiers."* | **Makespan reduction (CP-SAT vs. SPT):**<br>• Tier 1: **$40.15\%$** (`153.10m` vs `255.80m`; note `FCFS` is `155.70m`, so CP-SAT vs best heuristic `FCFS` on Tier 1 is **$1.67\%$**, $p = 0.467$)<br>• Tier 2: **$47.25\%$** (`191.70m` vs `363.39m`)<br>• Tier 3: **$38.12\%$** (`217.40m` vs `351.30m`)<br>• Tier 4: **$53.10\%$** (`387.40m` vs `825.95m`)<br>**Tardiness reduction (CP-SAT vs. SPT):**<br>• Tier 1: **$88.57\%$** (vs `FCFS`: **$54.54\%$**)<br>• Tier 2: **$89.22\%$**<br>• Tier 3: **$76.39\%$**<br>• Tier 4: **$73.04\%$** | **NEEDS NUMERICAL RANGE CORRECTION** (Correct range across Tiers 2–4 is **$38.12\%\text{–}53.10\%$**, not $47\%\text{–}53\%$; Tier 1 best heuristic is `FCFS`). |
| **CLAIM-02** | `docs/STAGE9_EXPERIMENTAL_REPORT.md` Sec. 9 Conclusion 2 | *"SPT is the strongest baseline on contended multi-job shop floors (Tiers 2, 3, and 4), executing in 1–16ms (170x–700x faster than CP-SAT)."* | **Mean runtime ratio ($\bar{t}_{\text{CPSAT}} / \bar{t}_{\text{SPT}}$):**<br>• Tier 1: **$298.1\times$** (`300.16ms / 1.01ms`)<br>• Tier 2: **$797.4\times$** (`1679.37ms / 2.11ms`)<br>• Tier 3: **$706.6\times$** (`2054.11ms / 2.91ms`)<br>• Tier 4: **$171.4\times$** (`2660.92ms / 15.53ms`) | **MINOR UPPER BOUND UNDERSPECIFIED** (Actual speedup range is **$171.4\times\text{–}797.4\times$**). |
| **CLAIM-03** | `backend/app/experiments/stage9_benchmark.py` L431 | *"95% confidence intervals computed using normal multiplier $1.96 \cdot s / \sqrt{10}$."* | For $n = 10$ ($\text{df} = 9$), the exact Student-$t$ critical value is $t_{0.975, 9} = 2.26216$, widening all marginal $95\%$ CI half-widths by **$+15.42\%$** relative to $1.96$. | **METHODOLOGICAL CORRECTION APPLIED** (Exact Student-$t$ CIs + paired within-seed CIs + non-parametric medians/IQRs added). |
| **CLAIM-04** | `docs/STAGE9_EXPERIMENTAL_REPORT.md` Sec. 5 | *"CP-SAT reported OPTIMAL on Tier 1 (10/10) and FEASIBLE on Tier 2 (8/10 FEASIBLE, 2/10 OPTIMAL), Tier 3 (10/10 FEASIBLE), and Tier 4 (10/10 FEASIBLE)."* | Proven `OPTIMAL` rate in Stage 9 is **$12/40$ ($30.0\%$)** overall ($100\%$ Tier 1, $20\%$ Tier 2, $0\%$ Tier 3, $0\%$ Tier 4), and $3/10$ ($30.0\%$) on Stage 10 Tier 5. | **VERIFIED & CLARIFIED** (Must describe Tiers 2–5 CP-SAT results as time-bounded `FEASIBLE` solutions). |
| **CLAIM-05** | `docs/STAGE9_EXPERIMENTAL_REPORT.md` Sec. 6 Obs. 3 | *"EPN lags behind SPT and CP-SAT due to job-sequential outer loop and positive neural slot offset (`slot * 2.0`)."* | Removing the positive slot offset alone (`Ablation A`) reduces makespan by only **$0.16\%\text{–}0.60\%$**. Switching to operation-level ready-queue decoding (`Ablation B`) reduces makespan by **$49.25\%\text{–}71.13\%$**. | **CAUSAL MECHANISM QUANTIFIED** ($>99\%$ of EPN makespan inflation is caused by job-sequential outer-loop serialization). |
| **CLAIM-06** | `backend/app/optimization/cpsat_solver.py` L213 | *"All 280 trials are deterministically reproducible from explicit seeds."* | $240/240$ deterministic trials reproduce identically ($0$ discrepancies). $18/40$ multi-threaded CP-SAT runs (`num_search_workers = 4`) show minor incumbent drift under wall-clock timeout. | **REPRODUCIBILITY NUANCE DOCUMENTED** (Set `num_search_workers = 1` or `random_seed` if strict bit-level CP-SAT replay is required). |

---

## 4. Phase C Audit: Schedule Validation & Independent Auditor

### 4.1 Audit of Existing `ScheduleValidator.validate()`
Inspection of [`backend/app/scheduling/validator.py`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/scheduling/validator.py) revealed that while `stage9_benchmark.py` supplemented `ScheduleValidator.validate()` with `verify_schedule_exhaustive()`, `ScheduleValidator.validate()` itself had four gaps when called standalone by API endpoints:
1. **No Duplicate Operation Check:** If a schedule contained two `ScheduledTask` objects with the same `(job_id, operation_sequence)` on different machines with non-overlapping times, `ScheduleValidator.validate()` did not flag the duplicate operation.
2. **No Duration/Interval Consistency Check:** If a task had `duration <= 0`, `end_time < start_time`, or `end_time - start_time != duration` (for non-running tasks), `ScheduleValidator.validate()` did not reject it unless it caused an overlap or precedence error.
3. **No Standalone `BUSY` Machine Lock Check:** While `ScheduleValidator.validate()` checked `DOWN` and `MAINTENANCE` windows, it relied on the running task being included in `tasks` to catch overlaps on a `BUSY` machine. If a caller omitted the running task from `tasks`, scheduling a pending task on a `BUSY` machine before `current_time + remaining_processing_time` was not caught.

### 4.2 Hardening Applied to `ScheduleValidator.validate()`
In Stage 10, [`ScheduleValidator.validate()`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/scheduling/validator.py#L32-L75) was strengthened to enforce:
- **Busy Machine Lock Protection:** Any pending task on a `BUSY` machine with `remaining_processing_time > 1e-4` starting before `current_time + remaining_processing_time - 1e-4` raises a `Busy Machine Lock Violation`.
- **Duplicate Operation Detection:** Any repeated `(job_id, operation_sequence)` raises a `Duplicate Operation Violation`.
- **Duration & Interval Consistency:** Any task with `duration <= 0` or `end_time < start_time - 1e-4` raises a `Duration Consistency Violation`, and any non-running task with `|(end_time - start_time) - duration| > 0.1` raises a `Duration Mismatch Violation`.

### 4.3 Zero-Shared-Code `IndependentScheduleAuditor`
To eliminate any possibility of common-mode validation bugs, [`IndependentScheduleAuditor`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/experiments/stage10_runner.py#L112-L344) was implemented from scratch without importing or calling `ScheduleValidator` or `verify_schedule_exhaustive`:
- Verifies exact 1-to-1 bijection between expected operations `(job_id, sequence)` across active jobs and scheduled tasks (`[INDEP-DUP]`, `[INDEP-UNKNOWN-OP]`, `[INDEP-MISSING-OP]`).
- Verifies positive durations, interval equality (`end_time - start_time == duration`), specification duration equality, and exact machine assignment (`[INDEP-WRONG-MACHINE]`, `[INDEP-SPEC-DUR]`).
- Verifies job release times (`start_time >= max(current_time, job.arrival_time)`), machine downtime windows (`[INDEP-DOWNTIME]`), and machine busy locks (`[INDEP-BUSY-LOCK]`).
- Verifies intra-job operation sequence ordering and precedence (`op_{k}.start_time >= op_{k-1}.end_time - 1e-4`), naturally supporting jobs that visit the same machine multiple times across non-adjacent operations.
- Verifies pairwise $O(N^2)$ interval non-overlap on every machine (`max(s_a, s_b) < min(e_a, e_b) - 1e-4`).
- Independently recomputes all metrics plus CP-SAT's multi-criteria objective $J_{\text{CPSAT}} = 10 C_{\max} + 25 \sum_{j} w_j T_j + \sum_{j} w_j C_j$.

Across **$650$ total schedules** audited in Stage 10 ($280$ Stage 9 trials $+ 70$ Tier 5 Repeated-Routing trials $+ 300$ Phase E Ablation trials), `IndependentScheduleAuditor` reported **$650/650$ ($100.0\%$) valid schedules** and **$0$ constraint violations**.

---

## 5. Phase E1 Audit: Root-Cause Diagnosis of EPN Underperformance & Heuristic Dispatching Mechanics

### 5.1 Two Suspected Bottlenecks in `EPNJobShopScheduler.schedule()`
Inspection of [`backend/app/ml/inference/epn_scheduler.py`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/ml/inference/epn_scheduler.py) identified two distinct mechanisms in the baseline EPN decoder:
1. **Mechanism 1 — Positive Neural Slot Offset (`neural_offset = slot_val * 2.0`):**
   ```python
   neural_offset = slot_val * 2.0
   est_start = max(job_ready, machine_free_time[m_id], current_time + neural_offset)
   ```
   Whenever `current_time + slot_val * 2.0 > max(job_ready, machine_free_time[m_id])`, the operation is artificially delayed beyond the earliest time both the job and machine are ready.
2. **Mechanism 2 — Job-Sequential Outer Loop (`for j in sorted_jobs`):**
   ```python
   sorted_jobs = sorted(jobs, key=lambda j: (j.arrival_time, -j.priority))
   for j in sorted_jobs:
       ...
       for op_idx, op in enumerate(pending_ops):
           est_start = max(job_ready, machine_free_time[m_id], current_time + neural_offset)
           est_end = est_start + op.duration
           machine_free_time[m_id] = est_end
           job_ready = est_end
   ```
   Because the outer loop iterates over jobs `j` and the inner loop schedules **all operations `op_1 .. op_k` of job `j` to completion** while updating a single scalar watermark `machine_free_time[m_id] = est_end`, scheduling Job 1's Operation 5 on machine `M4` at $[90, 115]$ sets `machine_free_time["M4"] = 115`. When Job 2 is processed in the next outer-loop iteration, its Operation 1 on `M4` (which was ready at $t = 0$ while `M4` was completely idle during $[0, 90]$!) is forced to start at $t \ge 115$.

### 5.2 Operation-Level Trace Evidence (`epn_trace_summary.csv`)
Stage 10 instrumented `EPNJobShopScheduler` to log every operation's predicted slot, `job_ready_time`, `machine_free_time_before`, `earliest_feasible_start`, `neural_target_time`, and `artificial_idle_gap = max(0, actual_start - earliest_feasible_start)` ([`epn_trace_summary.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_epn_ablation/epn_trace_summary.csv)):

| Tier ID | Seed | Traced Ops | Unique Predicted Slots (`EPN_BASELINE`) | Mean Slot | Ops Delayed by `slot * 2.0` Offset | Total Artificial Idle Gap from Offset (min) | Max Single-Op Offset Gap (min) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `TIER1_SMALL` | `1001` | 24 | `[0, 1, 2, 5]` | 1.83 | **2 / 24** | **6.0m** | 4.0m |
| `TIER2_MEDIUM` | `2001` | 46 | `[0, 1, 2, 3, 4]` | 2.22 | **2 / 46** | **6.5m** | 4.7m |
| `TIER3_DYNAMIC_BREAKDOWN` | `3001` | 53 | `[0, 1, 2, 39]` | 6.15 | **1 / 53** | **4.0m** | 4.0m |
| `TIER4_LARGE_SCALE` | `4001` | 125 | `[0, 1, 2, 4, 5, 7, 8, 39]` | 4.80 | **3 / 125** | **13.1m** | 7.3m |
| `TIER5_REPEATED_ROUTING` | `5001` | 53 | `[0, 1, 3, 4, 7]` | 1.58 | **2 / 53** | **8.0m** | 6.0m |

**Why does `slot * 2.0` only delay 1–3 operations per instance?**  
Because `neural_target = current_time + slot_val * 2.0` is anchored to `current_time`! For normal predicted slots (`0..8`, corresponding to `0..16m` after `current_time`), as soon as the first $1\text{–}2$ operations of the first job are scheduled, `job_ready_time` and `machine_free_time[m_id]` exceed `current_time + 16m`. For all subsequent operations ($>94\%$ of operations), `max(job_ready, machine_free_time[m_id]) > current_time + slot_val * 2.0`, rendering `neural_offset` inactive! Only when EPN predicts slot `39` (`+78m` offset) on an early operation does it inject a larger delay, and even then, job-sequential watermark advancement dominates total makespan.

### 5.3 Scalar Watermark Inversion in Classic Heuristics (`DispatchHeuristicScheduler`)
Audit of [`DispatchHeuristicScheduler.schedule()`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/scheduling/heuristics.py#L117-L143) also uncovered an important structural property of the existing heuristic implementation:
- `DispatchHeuristicScheduler` maintains a single scalar `machine_free_time[m_id]` per machine and sorts all currently ready operations across all jobs by:
  - `FCFS`: `(j.arrival_time, est_start)`
  - `SPT`: `(op.duration, est_start)`
  - `EDD`: `(j.due_date, est_start)`
  - `CR`: `(cr, est_start)`
  - `AGING`: `(-score, est_start)`
- Because `j.arrival_time` (in `FCFS`) and `j.due_date` (in `EDD`) are job-level constants placed **before** `est_start` in the sort tuple, once Job 1 has the earliest arrival time (or earliest due date), `FCFS` (or `EDD`) dispatches Job 1's Op 1, Op 2, Op 3, Op 4, and Op 5 consecutively before dispatching Job 2's Op 1!
- Even in `SPT` (`(op.duration, est_start)`), a short late operation (`duration = 8m`, `est_start = 110m` on `M3`) is dispatched before a slightly longer operation that is ready right now (`duration = 12m`, `est_start = 0m` on `M3`). Updating the scalar `machine_free_time["M3"] = 118m` destroys the $[0, 110\text{m}]$ idle window on `M3`.
- This explains two key empirical phenomena in Stage 9 and Stage 10:
  1. Why `FCFS` (`397.16m`) and `EPN_BASELINE` (`398.12m`) had virtually identical makespans on Tier 2 (`p = 0.251`): both serialized jobs by `arrival_time` over a scalar `machine_free_time` watermark!
  2. Why `EPN_ABLATION_B_OP_READY_DECODING` (which dispatches ready operations in chronological `earliest_start` order `(earliest_start, pred_slot, -priority, arrival_time)`) outperforms `SPT` by **$33.89\%\text{–}52.93\%$** on makespan across Tiers 1–5!

---

## 6. Phase F Audit: CP-SAT Multi-Objective & Optimality Fairness

Inspection of [`CPSATSchedulingOptimizer.optimize()`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/optimization/cpsat_solver.py#L194-L209) confirmed that CP-SAT minimizes a scaled multi-criteria objective ($\text{SCALE} = 10$ ticks per minute):
$$J_{\text{CPSAT}} = 10 \, C_{\max} + 25 \sum_{j \in \mathcal{J}} w_j T_j + \sum_{j \in \mathcal{J}} w_j C_j$$
where $w_j \in \{1, \dots, 5\}$ is job priority, $T_j = \max(0, C_j - d_j)$ is job tardiness, and $C_j$ is job completion time.

In contrast, dispatching heuristics (`FCFS`, `SPT`, `EDD`, `CR`, `AGING`) and `EPN` are single-pass greedy rules that do not explicitly optimize $J_{\text{CPSAT}}$. In Stage 10, `IndependentScheduleAuditor` computed $J_{\text{CPSAT}}$ across all algorithms ([`stage10_cpsat_objective_audit.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_audit/stage10_cpsat_objective_audit.csv)):

| Tier ID | CP-SAT Proven `OPTIMAL` | CP-SAT Time-Bounded `FEASIBLE` | CP-SAT Mean $J_{\text{CPSAT}}$ | Best Classic Heuristic Mean $J_{\text{CPSAT}}$ | `EPN_BASELINE` Mean $J_{\text{CPSAT}}$ | `EPN_ABLATION_B` (Op-Ready) Mean $J_{\text{CPSAT}}$ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `TIER1_SMALL` | **10 / 10 (100%)** | 0 / 10 (0%) | **4,789.1** | 9,487.6 (`FCFS`, $1.98\times$) | 30,975.1 ($6.47\times$) | **7,493.6** ($1.56\times$) |
| `TIER2_MEDIUM` | **2 / 10 (20%)** | 8 / 10 (80%) | **10,660.1** | 79,471.6 (`SPT`, $7.46\times$) | 94,492.9 ($8.86\times$) | **14,643.9** ($1.37\times$) |
| `TIER3_DYNAMIC_BREAKDOWN` | **0 / 10 (0%)** | 10 / 10 (100%) | **20,938.8** | 102,153.9 (`SPT`, $4.88\times$) | 209,418.4 ($10.00\times$) | **29,225.3** ($1.40\times$) |
| `TIER4_LARGE_SCALE` | **0 / 10 (0%)** | 10 / 10 (100%) | **151,975.4** | 712,002.3 (`SPT`, $4.69\times$) | 1,161,810.0 ($7.64\times$) | **160,573.5** ($1.06\times$) |
| `TIER5_REPEATED_ROUTING` | **3 / 10 (30%)** | 7 / 10 (70%) | **13,357.1** | 136,036.1 (`SPT`, $10.18\times$) | 218,940.6 ($16.39\times$) | **20,250.9** ($1.52\times$) |

### Statistical Power & Sample-Size Audit ($n = 10$ Seeds per Tier)
With $n = 10$ paired instances per tier ($\text{df} = 9$, two-sided $\alpha = 0.05$, Holm-Bonferroni corrected across $k = 6$ comparisons so $\alpha_{\text{min}} = 0.05 / 6 = 0.00833$), a paired Student $t$-test requires a minimum detectable effect size of **Cohen's $d_z \ge 1.28$** to achieve $80\%$ statistical power ($1 - \beta = 0.80$).
- Across Tiers 2–5, the observed paired effect sizes for `CP-SAT` vs. `SPT` ($d_z \in [2.71, 5.75]$ on makespan; $d_z \in [2.49, 8.48]$ on tardiness) and for `EPN_ABLATION_B_OP_READY_DECODING` vs. `EPN_BASELINE` ($d_z \in [2.56, 5.89]$ on makespan) are **very large ($d_z > 2.5$)**, achieving $>99.9\%$ statistical power even at $n = 10$.
- Conversely, subtle differences with $|d_z| < 0.85$ (such as `CP-SAT` vs. `FCFS` makespan on Tier 1 where $d_z = 0.24$, or `EPN_ABLATION_B` vs. `EPN_ABLATION_C` makespan where $|d_z| \in [0.03, 0.40]$) are appropriately reported as **statistically non-significant** at $n = 10$.

