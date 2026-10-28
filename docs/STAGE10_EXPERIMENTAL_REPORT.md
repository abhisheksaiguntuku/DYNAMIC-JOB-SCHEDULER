# STAGE 10 EXPERIMENTAL REPORT
## Corrected Statistical Benchmark (Tiers 1–4), Re-Entrant Routing Evaluation (Tier 5) & EPN Controlled Ablation Study

**Project:** Dynamic Job-Shop Scheduling System  
**Branch:** `stage10-research-audit`  
**Date:** 2026-10-28  
**Experiment Runner:** [`backend/app/experiments/stage10_runner.py`](file:///c:/Users/SUNITA\.gemini\antigravity\scratch/dynamic_job_shop_scheduler/backend/app/experiments/stage10_runner.py)

---

## 1. Experimental Scope & Total Trials Executed

Stage 10 evaluated **650 total verified scheduling trials** across five experimental tiers:
1. **Phase B Re-Audited Stage 9 Benchmark (`280` trials):** $4\text{ tiers} \times 10\text{ seeds} \times 7\text{ algorithms}$ (`FCFS`, `SPT`, `EDD`, `CR`, `AGING`, `CPSAT`, `EPN`), stored in [`backend/experiments/stage10_audit/`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_audit/).
2. **Phase D Repeated-Routing Benchmark (`TIER5_REPEATED_ROUTING`, `70` trials):** $10\text{ seeds (`5001–5010`)} \times 7\text{ algorithms}$ on a 12-job, 10-machine shop floor where $66.7\%$ ($8/12$) of jobs follow re-entrant routes revisiting the same machine multiple times (e.g., `M1 -> M3 -> M1 -> M9`, `M6 -> M4 -> M6 -> M5 -> M6 -> M9`), stored in [`backend/experiments/stage10_repeated_routing/`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_repeated_routing/).
3. **Phase E EPN Controlled Ablation Study (`300` trials):** $5\text{ tiers (Tiers 1–5)} \times 10\text{ seeds} \times 6\text{ methods}$ (`EPN_BASELINE`, `EPN_ABLATION_A_NO_OFFSET`, `EPN_ABLATION_B_OP_READY_DECODING`, `EPN_ABLATION_C_HYBRID_SPT`, `SPT`, `FCFS`), stored in [`backend/experiments/stage10_epn_ablation/`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_epn_ablation/).

Every single schedule ($650/650 = 100.0\%$) was verified by both [`ScheduleValidator.validate()`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/scheduling/validator.py) and [`IndependentScheduleAuditor.audit_schedule()`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/experiments/stage10_runner.py) with **zero constraint violations**.

---

## 2. Corrected Summary Tables Across Tiers 1–5 (Exact Student-$t$ $95\%$ CI, Median & IQR)

For $n = 10$ seeds per tier ($\text{df} = 9$), $95\%$ confidence intervals use the exact Student-$t$ multiplier $t_{0.975, 9} = 2.26216$ (reported alongside the asymptotic normal $z_{0.975} = 1.96$ in the CSV/JSON artifacts for direct comparison).

### 2.1 Tier 1 (`TIER1_SMALL`: 6 Jobs, 5 Machines, Static Arrivals, Seeds `1001–1010`)
| Algorithm | Valid / Optimal | Makespan Mean $\pm$ $\text{CI}_{95,t}$ (m) | Makespan Median (IQR) | Tardiness Mean $\pm$ $\text{CI}_{95,t}$ (m) | Tardiness Median (IQR) | Mean Waiting (m) | Mean Util (%) | Mean $J_{\text{CPSAT}}$ | Runtime Mean (Median) (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CPSAT** | 10/10 (**10 OPT**) | **153.10 $\pm$ 16.51** | 148.50 (19.00) | **34.84 $\pm$ 27.38** | 17.00 (50.85) | **36.60** | **60.58%** | **4,789.1** | 300.16 (216.44) |
| **FCFS** | 10/10 (0 OPT) | 155.70 $\pm$ 15.71 | 158.50 (37.00) | 76.64 $\pm$ 41.16 | 67.00 (70.30) | 41.60 | 59.52% | 9,487.6 | 1.84 (1.39) |
| **SPT** | 10/10 (0 OPT) | 255.80 $\pm$ 41.84 | 246.50 (104.50) | 304.88 $\pm$ 125.21 | 248.80 (250.85) | 82.77 | 37.15% | 27,994.4 | 1.01 (1.00) |
| **EDD** | 10/10 (0 OPT) | 321.60 $\pm$ 39.83 | 335.50 (70.25) | 412.34 $\pm$ 103.60 | 378.40 (188.95) | 102.72 | 29.10% | 35,727.1 | 1.02 (0.88) |
| **EPN (Baseline)** | 10/10 (0 OPT) | 333.20 $\pm$ 50.04 | 340.00 (73.00) | 543.02 $\pm$ 161.38 | 573.40 (308.45) | 123.95 | 28.55% | 30,975.1 | 107.80 (82.23) |
| **CR** | 10/10 (0 OPT) | 362.00 $\pm$ 57.08 | 390.00 (114.75) | 730.04 $\pm$ 179.39 | 695.80 (357.30) | 162.13 | 26.13% | 59,671.4 | **0.95 (0.97)** |
| **AGING** | 10/10 (0 OPT) | 393.50 $\pm$ 43.15 | 400.00 (51.50) | 1113.78 $\pm$ 248.25 | 1111.20 (292.90) | 224.85 | 23.56% | 90,476.8 | 1.03 (1.02) |

### 2.2 Tier 2 (`TIER2_MEDIUM`: 10 Jobs, 10 Machines, Poisson Arrivals, Seeds `2001–2010`)
| Algorithm | Valid / Optimal | Makespan Mean $\pm$ $\text{CI}_{95,t}$ (m) | Makespan Median (IQR) | Tardiness Mean $\pm$ $\text{CI}_{95,t}$ (m) | Tardiness Median (IQR) | Mean Waiting (m) | Mean Util (%) | Mean $J_{\text{CPSAT}}$ | Runtime Mean (Median) (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CPSAT** | 10/10 (**2 OPT**) | **191.70 $\pm$ 19.23** | 186.45 (26.80) | **101.64 $\pm$ 47.69** | 84.80 (85.88) | **36.35** | **45.89%** | **10,660.1** | 1679.37 (2027.18) |
| **SPT** | 10/10 (0 OPT) | 363.39 $\pm$ 32.69 | 379.10 (63.05) | 943.25 $\pm$ 217.22 | 950.30 (386.28) | 125.35 | 24.19% | 79,471.6 | **2.11 (2.21)** |
| **FCFS** | 10/10 (0 OPT) | 397.16 $\pm$ 51.26 | 375.25 (96.58) | 1132.68 $\pm$ 249.78 | 1140.90 (524.28) | 141.61 | 22.41% | 94,105.4 | 2.46 (2.06) |
| **EPN (Baseline)** | 10/10 (0 OPT) | 398.12 $\pm$ 50.50 | 376.10 (95.75) | 1139.64 $\pm$ 246.81 | 1145.70 (503.83) | 142.59 | 22.34% | 94,492.9 | 191.58 (117.91) |
| **EDD** | 10/10 (0 OPT) | 445.13 $\pm$ 48.86 | 433.90 (96.93) | 1178.07 $\pm$ 222.99 | 1158.35 (417.90) | 148.93 | 19.86% | 99,631.9 | 2.43 (2.23) |
| **CR** | 10/10 (0 OPT) | 617.07 $\pm$ 32.18 | 615.15 (70.78) | 2672.68 $\pm$ 147.01 | 2671.35 (167.85) | 302.66 | 14.11% | 224,106.7 | 3.15 (2.58) |
| **AGING** | 10/10 (0 OPT) | 625.58 $\pm$ 43.96 | 622.85 (96.75) | 3493.44 $\pm$ 342.04 | 3520.15 (611.25) | 384.37 | 13.92% | 281,581.5 | 2.98 (2.38) |

### 2.3 Tier 3 (`TIER3_DYNAMIC_BREAKDOWN`: 12 Jobs, 10 Machines, $t_{\text{now}}=15\text{m}$, Running Ops + `M2` Down, Seeds `3001–3010`)
| Algorithm | Valid / Optimal | Makespan Mean $\pm$ $\text{CI}_{95,t}$ (m) | Makespan Median (IQR) | Tardiness Mean $\pm$ $\text{CI}_{95,t}$ (m) | Tardiness Median (IQR) | Mean Waiting (m) | Mean Util (%) | Mean $J_{\text{CPSAT}}$ | Runtime Mean (Median) (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CPSAT** | 10/10 (0 OPT) | **217.40 $\pm$ 23.53** | 220.50 (30.25) | **261.86 $\pm$ 72.42** | 290.60 (107.98) | **53.92** | **46.79%** | **20,938.8** | 2054.11 (2031.24) |
| **SPT** | 10/10 (0 OPT) | 351.30 $\pm$ 33.62 | 356.50 (54.30) | 1109.30 $\pm$ 208.84 | 1159.75 (399.30) | 126.94 | 28.93% | 102,153.9 | 2.91 (3.06) |
| **FCFS** | 10/10 (0 OPT) | 503.30 $\pm$ 64.39 | 513.50 (116.75) | 1663.70 $\pm$ 293.64 | 1704.05 (495.45) | 170.21 | 20.42% | 147,873.2 | 2.74 (2.82) |
| **EDD** | 10/10 (0 OPT) | 516.30 $\pm$ 75.99 | 477.50 (103.75) | 1831.12 $\pm$ 454.71 | 1563.40 (672.23) | 188.80 | 19.97% | 158,051.8 | **2.34 (2.31)** |
| **EPN (Baseline)** | 10/10 (0 OPT) | 584.40 $\pm$ 76.30 | 584.00 (51.00) | 2473.20 $\pm$ 533.85 | 2496.55 (293.20) | 241.68 | 17.60% | 209,418.4 | 129.13 (112.26) |
| **CR** | 10/10 (0 OPT) | 714.50 $\pm$ 67.51 | 690.50 (124.75) | 3634.00 $\pm$ 363.18 | 3633.90 (568.28) | 340.57 | 14.17% | 309,084.4 | 2.68 (2.89) |
| **AGING** | 10/10 (0 OPT) | 727.70 $\pm$ 59.13 | 741.00 (131.00) | 4905.30 $\pm$ 734.68 | 5030.35 (1022.93) | 446.51 | 13.92% | 416,804.4 | 2.95 (2.94) |

### 2.4 Tier 4 (`TIER4_LARGE_SCALE`: 25 Jobs, 10 Machines, 125 Operations, Seeds `4001–4010`)
| Algorithm | Valid / Optimal | Makespan Mean $\pm$ $\text{CI}_{95,t}$ (m) | Makespan Median (IQR) | Tardiness Mean $\pm$ $\text{CI}_{95,t}$ (m) | Tardiness Median (IQR) | Mean Waiting (m) | Mean Util (%) | Mean $J_{\text{CPSAT}}$ | Runtime Mean (Median) (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CPSAT** | 10/10 (0 OPT) | **387.40 $\pm$ 26.46** | 373.25 (24.73) | **2408.60 $\pm$ 193.84** | 2437.25 (324.33) | **125.11** | **61.57%** | **151,975.4** | 2660.92 (2546.29) |
| **SPT** | 10/10 (0 OPT) | 825.95 $\pm$ 55.89 | 801.65 (128.93) | 8933.98 $\pm$ 602.59 | 8999.65 (372.43) | 386.54 | 28.85% | 712,002.3 | 15.53 (15.48) |
| **FCFS** | 10/10 (0 OPT) | 1253.64 $\pm$ 93.87 | 1253.35 (141.08) | 13067.78 $\pm$ 1326.79 | 12715.85 (1442.78) | 550.44 | 19.07% | 1,020,120.8 | **12.86 (13.06)** |
| **EDD** | 10/10 (0 OPT) | 1287.99 $\pm$ 89.02 | 1282.50 (106.20) | 13171.01 $\pm$ 1334.86 | 13462.40 (2276.20) | 555.31 | 18.51% | 999,946.1 | 13.45 (13.35) |
| **EPN (Baseline)** | 10/10 (0 OPT) | 1346.60 $\pm$ 118.09 | 1342.00 (253.00) | 14905.49 $\pm$ 1595.80 | 14618.70 (3430.73) | 624.35 | 17.83% | 1,161,810.0 | 383.31 (368.71) |
| **CR** | 10/10 (0 OPT) | 1775.74 $\pm$ 51.33 | 1782.15 (109.40) | 20492.54 $\pm$ 1002.50 | 20369.55 (1095.68) | 849.12 | 13.35% | 1,598,600.3 | 14.36 (14.12) |
| **AGING** | 10/10 (0 OPT) | 1908.13 $\pm$ 99.01 | 1948.45 (204.25) | 36598.39 $\pm$ 3064.12 | 36736.05 (6435.40) | 1493.35 | 12.44% | 2,877,679.6 | 18.76 (17.76) |

### 2.5 Phase D — Tier 5 (`TIER5_REPEATED_ROUTING`: 12 Jobs, 10 Machines, Re-Entrant Routes, Seeds `5001–5010`)
In `TIER5_REPEATED_ROUTING`, $8$ of $12$ jobs per instance ($66.7\%$) follow re-entrant manufacturing routes that revisit the same machine multiple times across non-adjacent operations (e.g., `M1 -> M3 -> M1 -> M9` or `M6 -> M4 -> M6 -> M5 -> M6 -> M9`), with variable operation lengths ($3\text{–}6$ operations/job, $53$ total operations/instance) and dynamic arrivals ([`tier5_summary_table.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_repeated_routing/tier5_summary_table.csv)):

| Algorithm | Valid / Optimal | Makespan Mean $\pm$ $\text{CI}_{95,t}$ (m) | Makespan Median (IQR) | Tardiness Mean $\pm$ $\text{CI}_{95,t}$ (m) | Tardiness Median (IQR) | Mean Waiting (m) | Mean Util (%) | Mean $J_{\text{CPSAT}}$ | Runtime Mean (Median) (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **CPSAT** | 10/10 (**3 OPT**) | **304.00 $\pm$ 23.93** | 307.50 (14.25) | **64.09 $\pm$ 40.02** | 77.40 (84.08) | **51.77** | **46.47%** | **13,357.1** | 2086.49 (2552.52) |
| **SPT** | 10/10 (0 OPT) | 547.30 $\pm$ 65.60 | 547.00 (74.50) | 1583.02 $\pm$ 449.36 | 1485.55 (692.75) | 195.32 | 26.15% | 136,036.1 | 3.50 (2.74) |
| **FCFS** | 10/10 (0 OPT) | 626.60 $\pm$ 76.08 | 651.00 (149.75) | 1674.16 $\pm$ 349.62 | 1668.45 (743.48) | 189.33 | 22.84% | 144,152.2 | 2.84 (2.82) |
| **EPN (Baseline)** | 10/10 (0 OPT) | 727.50 $\pm$ 69.27 | 720.00 (51.00) | 2564.13 $\pm$ 528.11 | 2351.55 (471.03) | 274.02 | 19.41% | 218,940.6 | 180.68 (122.78) |
| **EDD** | 10/10 (0 OPT) | 758.90 $\pm$ 78.99 | 745.00 (121.75) | 2103.30 $\pm$ 437.10 | 2158.70 (464.55) | 238.15 | 18.71% | 179,186.4 | **2.56 (2.59)** |
| **CR** | 10/10 (0 OPT) | 1005.50 $\pm$ 123.09 | 979.50 (241.00) | 4570.45 $\pm$ 649.09 | 4484.20 (834.33) | 451.72 | 14.23% | 376,196.3 | 3.67 (3.59) |
| **AGING** | 10/10 (0 OPT) | 1061.80 $\pm$ 99.90 | 1022.00 (196.00) | 6051.63 $\pm$ 764.64 | 5810.55 (1217.63) | 574.27 | 13.32% | 487,541.9 | 3.01 (2.85) |

---

## 3. Paired Within-Seed Statistical Comparisons (Tiers 1–5)

Selected key comparisons from [`stage10_paired_statistics.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_audit/stage10_paired_statistics.csv) and [`tier5_paired_statistics.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_repeated_routing/tier5_paired_statistics.csv) ($n = 10$ seeds per tier, Holm-Bonferroni step-down adjusted $p$-values):

| Tier ID | Metric | Reference vs. Compared | Mean Paired Diff ($\Delta \pm \text{CI}_{95,t}$) | Rel. Reduction | Wins/Ties/Losses | Paired $t$ ($p_{\text{Holm}}$) | Wilcoxon $W$ ($p_{\text{Holm}}$) | Cohen's $d_z$ | Sig. ($\alpha=0.05$) |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `TIER1_SMALL` | Makespan | `CPSAT` vs `FCFS` | $+2.60 \pm 7.74\text{m}$ | $1.67\%$ | 5 / 0 / 5 | $0.760$ ($0.467$) | $20.0$ ($0.484$) | $0.240$ | `False` |
| `TIER1_SMALL` | Tardiness | `CPSAT` vs `FCFS` | $+41.80 \pm 23.18\text{m}$ | $54.54\%$ | 10 / 0 / 0 | $4.080$ ($0.0028$) | $0.0$ ($0.0117$) | $1.290$ | **`True`** |
| `TIER1_SMALL` | Makespan | `CPSAT` vs `SPT` | $+102.70 \pm 31.34\text{m}$ | $40.15\%$ | 10 / 0 / 0 | $7.413$ ($8.1\text{e-}5$) | $0.0$ ($0.0117$) | $2.344$ | **`True`** |
| `TIER2_MEDIUM` | Makespan | `CPSAT` vs `SPT` | $+171.69 \pm 30.89\text{m}$ | $47.25\%$ | 10 / 0 / 0 | $12.573$ ($2.0\text{e-}6$) | $0.0$ ($0.0117$) | $3.976$ | **`True`** |
| `TIER2_MEDIUM` | Tardiness | `CPSAT` vs `SPT` | $+841.61 \pm 194.07\text{m}$ | $89.22\%$ | 10 / 0 / 0 | $9.810$ ($1.3\text{e-}5$) | $0.0$ ($0.0117$) | $3.102$ | **`True`** |
| `TIER2_MEDIUM` | Makespan | `SPT` vs `FCFS` | $+33.77 \pm 52.35\text{m}$ | $8.50\%$ | 7 / 0 / 3 | $1.459$ ($0.330$) | $15.0$ ($0.465$) | $0.461$ | `False` |
| `TIER3_DYNAMIC` | Makespan | `CPSAT` vs `SPT` | $+133.90 \pm 27.61\text{m}$ | $38.12\%$ | 10 / 0 / 0 | $10.971$ ($5.0\text{e-}6$) | $0.0$ ($0.0117$) | $3.469$ | **`True`** |
| `TIER3_DYNAMIC` | Tardiness | `CPSAT` vs `SPT` | $+847.44 \pm 175.65\text{m}$ | $76.39\%$ | 10 / 0 / 0 | $10.914$ ($5.0\text{e-}6$) | $0.0$ ($0.0117$) | $3.451$ | **`True`** |
| `TIER3_DYNAMIC` | Makespan | `SPT` vs `FCFS` | $+152.00 \pm 57.85\text{m}$ | $30.20\%$ | 10 / 0 / 0 | $5.944$ ($0.00043$) | $0.0$ ($0.0098$) | $1.880$ | **`True`** |
| `TIER4_LARGE` | Makespan | `CPSAT` vs `SPT` | $+438.55 \pm 54.55\text{m}$ | $53.10\%$ | 10 / 0 / 0 | $18.187$ ($<10^{-6}$) | $0.0$ ($0.0117$) | $5.751$ | **`True`** |
| `TIER4_LARGE` | Tardiness | `CPSAT` vs `SPT` | $+6525.38 \pm 550.41\text{m}$ | $73.04\%$ | 10 / 0 / 0 | $26.819$ ($<10^{-6}$) | $0.0$ ($0.0117$) | $8.481$ | **`True`** |
| `TIER5_REENTRANT` | Makespan | `CPSAT` vs `SPT` | $+243.30 \pm 64.32\text{m}$ | $44.45\%$ | 10 / 0 / 0 | $8.557$ ($1.3\text{e-}5$) | $0.0$ ($0.0117$) | $2.706$ | **`True`** |
| `TIER5_REENTRANT` | Tardiness | `CPSAT` vs `SPT` | $+1518.93 \pm 437.14\text{m}$ | $95.95\%$ | 10 / 0 / 0 | $7.860$ ($2.5\text{e-}5$) | $0.0$ ($0.0117$) | $2.486$ | **`True`** |

---

## 4. Phase E2 — Controlled EPN Ablation Study Across Tiers 1–5

To rigorously isolate why `EPN_BASELINE` underperformed in Stage 9 and evaluate whether operation-level decoding unlocks the trained EPN pointer network without retraining weights, four controlled EPN decoding variants were evaluated across all $50$ instances (Tiers 1–5, $10$ seeds each) alongside `SPT` and `FCFS` ([`epn_ablation_summary.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_epn_ablation/epn_ablation_summary.csv), [`epn_ablation_paired_stats.csv`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/experiments/stage10_epn_ablation/epn_ablation_paired_stats.csv)):

1. **`EPN_BASELINE`:** Unchanged Stage 9 job-sequential outer loop (`for j in sorted_jobs`) + positive neural slot offset (`neural_offset = slot_val * 2.0`).
2. **`EPN_ABLATION_A_NO_OFFSET`:** Job-sequential outer loop retained, positive neural slot offset disabled (`neural_offset = 0.0`).
3. **`EPN_ABLATION_B_OP_READY_DECODING` (Pure EPN Operation-Ready Decoding):** Replaces job-sequential outer-loop locking with chronological operation-level ready-queue dispatching ordered by `(earliest_start, epn_predicted_slot, -priority, arrival_time)` with zero artificial idle offset. **Uses pure EPN slot predictions and never uses SPT operation duration.**
4. **`EPN_ABLATION_C_HYBRID_SPT` (Hybrid EPN + SPT Active-Schedule Decoding):** Combines active-schedule idle-gap insertion with hybrid `epn_predicted_slot` + `op.duration` tie-breaking.

### 4.1 Ablation Results Table (Mean $\pm$ Student-$t$ $95\%$ CI)

| Tier ID | Variant | Makespan Mean $\pm$ $\text{CI}_{95,t}$ (m) | Tardiness Mean $\pm$ $\text{CI}_{95,t}$ (m) | Mean Util (%) | Mean $J_{\text{CPSAT}}$ | Makespan Reduction vs `EPN_BASELINE` | Paired $p_{\text{Holm}}$ vs `EPN_BASELINE` |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`TIER1_SMALL`** | `EPN_BASELINE` | $333.20 \pm 50.04$ | $543.02 \pm 161.38$ | $28.55\%$ | $30,975.1$ | — | — |
| | `EPN_ABLATION_A_NO_OFFSET` | $331.20 \pm 50.04$ | $534.02 \pm 160.36$ | $28.74\%$ | $30,358.5$ | $-0.60\%$ | — |
| | **`EPN_ABLATION_B_OP_READY_DECODING`** | **$169.10 \pm 15.08$** | **$71.68 \pm 40.17$** | **$54.83\%$** | **$7,493.6$** | **$-49.25\%$** | **$6.2 \times 10^{-5}$** |
| | `EPN_ABLATION_C_HYBRID_SPT` (Hybrid) | $164.40 \pm 20.67$ | $72.72 \pm 44.18$ | $56.80\%$ | $9,345.2$ | $-50.66\%$ | $<10^{-4}$ |
| | `SPT` (Classic Baseline) | $255.80 \pm 41.84$ | $304.88 \pm 125.21$ | $37.15\%$ | $27,994.4$ | — | — |
| **`TIER2_MEDIUM`** | `EPN_BASELINE` | $398.12 \pm 50.50$ | $1139.64 \pm 246.81$ | $22.34\%$ | $94,492.9$ | — | — |
| | `EPN_ABLATION_A_NO_OFFSET` | $396.66 \pm 50.85$ | $1128.98 \pm 247.85$ | $22.43\%$ | $93,687.0$ | $-0.37\%$ | — |
| | **`EPN_ABLATION_B_OP_READY_DECODING`** | **$196.38 \pm 12.65$** | **$134.55 \pm 46.40$** | **$44.39\%$** | **$14,643.9$** | **$-50.67\%$** | **$8.1 \times 10^{-5}$** |
| | `EPN_ABLATION_C_HYBRID_SPT` (Hybrid) | $196.84 \pm 11.60$ | $127.38 \pm 41.47$ | $44.27\%$ | $16,544.9$ | $-50.56\%$ | $<10^{-4}$ |
| | `SPT` (Classic Baseline) | $363.39 \pm 32.69$ | $943.25 \pm 217.22$ | $24.19\%$ | $79,471.6$ | — | — |
| **`TIER3_DYNAMIC`** | `EPN_BASELINE` | $584.40 \pm 76.30$ | $2473.20 \pm 533.85$ | $17.60\%$ | $209,418.4$ | — | — |
| | `EPN_ABLATION_A_NO_OFFSET` | $583.20 \pm 75.91$ | $2459.60 \pm 527.92$ | $17.63\%$ | $208,315.2$ | $-0.21\%$ | — |
| | **`EPN_ABLATION_B_OP_READY_DECODING`** | **$224.23 \pm 21.58$** | **$328.69 \pm 69.25$** | **$45.26\%$** | **$29,225.3$** | **$-61.63\%$** | **$8.0 \times 10^{-6}$** |
| | `EPN_ABLATION_C_HYBRID_SPT` (Hybrid) | $218.40 \pm 17.63$ | $277.09 \pm 77.25$ | $46.29\%$ | $29,769.8$ | $-62.63\%$ | $<10^{-5}$ |
| | `SPT` (Classic Baseline) | $351.30 \pm 33.62$ | $1109.30 \pm 208.84$ | $28.93\%$ | $102,153.9$ | — | — |
| **`TIER4_LARGE`** | `EPN_BASELINE` | $1346.60 \pm 118.09$ | $14905.49 \pm 1595.80$ | $17.83\%$ | $1,161,810.0$ | — | — |
| | `EPN_ABLATION_A_NO_OFFSET` | $1344.42 \pm 118.47$ | $14854.40 \pm 1602.83$ | $17.83\%$ | $1,157,747.1$ | $-0.16\%$ | — |
| | **`EPN_ABLATION_B_OP_READY_DECODING`** | **$388.74 \pm 24.35$** | **$2438.57 \pm 220.64$** | **$61.29\%$** | **$160,573.5$** | **$-71.13\%$** | **$< 10^{-6}$** |
| | `EPN_ABLATION_C_HYBRID_SPT` (Hybrid) | $380.41 \pm 29.19$ | $2333.35 \pm 179.49$ | $62.89\%$ | $190,063.3$ | $-71.75\%$ | $<10^{-6}$ |
| | `SPT` (Classic Baseline) | $825.95 \pm 55.89$ | $8933.98 \pm 602.59$ | $28.85\%$ | $712,002.3$ | — | — |
| **`TIER5_REENTRANT`** | `EPN_BASELINE` | $727.50 \pm 69.27$ | $2564.13 \pm 528.11$ | $19.41\%$ | $218,940.6$ | — | — |
| | `EPN_ABLATION_A_NO_OFFSET` | $725.70 \pm 69.29$ | $2547.13 \pm 526.49$ | $19.45\%$ | $217,561.4$ | $-0.25\%$ | — |
| | **`EPN_ABLATION_B_OP_READY_DECODING`** | **$299.60 \pm 18.97$** | **$163.91 \pm 60.74$** | **$46.90\%$** | **$20,250.9$** | **$-58.82\%$** | **$< 10^{-6}$** |
| | `EPN_ABLATION_C_HYBRID_SPT` (Hybrid) | $308.50 \pm 21.64$ | $136.61 \pm 67.82$ | $45.64\%$ | $20,287.3$ | $-57.60\%$ | $<10^{-6}$ |
| | `SPT` (Classic Baseline) | $547.30 \pm 65.60$ | $1583.02 \pm 449.36$ | $26.15\%$ | $136,036.1$ | — | — |

### 4.2 Scientific Interpretation of Ablation Findings
1. **Job-Sequential Serialization vs. Positive Offset:** Comparing `EPN_BASELINE` vs. `EPN_ABLATION_A_NO_OFFSET` proves that removing the positive offset alone (`slot_val * 2.0 = 0`) improves makespan by less than $0.60\%$ across all five tiers. Conversely, comparing `EPN_ABLATION_A_NO_OFFSET` vs. `EPN_ABLATION_B_OP_READY_DECODING` proves that switching from job-sequential outer-loop decoding to chronological operation-level ready-queue decoding (`(earliest_start, pred_slot, -priority, arrival_time)`) reduces mean makespan by **$49.25\%$ on Tier 1, $50.67\%$ on Tier 2, $61.63\%$ on Tier 3, $71.13\%$ on Tier 4, and $58.82\%$ on Tier 5** ($10/10$ seed wins on every tier, $p_{\text{Holm}} \le 8.1 \times 10^{-5}$, Cohen's $d_z \in [2.56, 5.89]$).
2. **Pure EPN Operation-Ready Decoding (`Ablation B`) vs. Hybrid EPN+SPT (`Ablation C`):** On all five tiers, the makespan difference between `EPN_ABLATION_B_OP_READY_DECODING` (which uses **only** EPN slot predictions and priority/arrival tie-breaking, never SPT duration) and `EPN_ABLATION_C_HYBRID_SPT` is statistically indistinguishable ($p_{\text{Holm}} \in [0.242, 0.927]$). In fact, on the combined objective $J_{\text{CPSAT}}$, pure `EPN_ABLATION_B_OP_READY_DECODING` outperforms `EPN_ABLATION_C_HYBRID_SPT` on Tier 2 ($p_{\text{Holm}} = 0.0459$) and Tier 4 ($p_{\text{Holm}} = 0.00069$) because prioritizing job priority (`-priority`) after EPN slot predictions protects high-weight jobs better than SPT duration tie-breaking.
3. **Near-CP-SAT Schedule Quality at $13\times\text{–}25\times$ Faster Inference:** On contended 10-machine shop floors (Tiers 2–5), `EPN_ABLATION_B_OP_READY_DECODING` achieves makespans within **$0.35\%\text{–}3.14\%$** of time-bounded `CP-SAT` (and $-1.45\%$ lower mean makespan on Tier 5: `299.60m` vs. `304.00m`) while running in **$64\text{–}172\text{ms}$ vs. $1679\text{–}2661\text{ms}$**.

---

## 5. Threats to Validity & Limitations

1. **Internal Validity (Scalar Watermark Dispatching in Classic Heuristics):** As documented in the Stage 10 Research Audit (Section 5.3), `DispatchHeuristicScheduler` sorts ready operations across jobs by `(rule_metric, est_start)` over a scalar `machine_free_time[m_id]` watermark rather than an interval list or chronological `(est_start, rule_metric)` non-delay dispatcher. Consequently, part of the gap between `EPN_ABLATION_B_OP_READY_DECODING` and `SPT` reflects chronological earliest-start event ordering (`est_start` primary key) in addition to EPN neural slot tie-breaking (`pred_slot` secondary key).
2. **Construct Validity (Multi-Criteria Objective Alignment & Utilization Denominator):** CP-SAT optimizes $J_{\text{CPSAT}} = 10 C_{\max} + 25 \sum w_j T_j + \sum w_j C_j$, whereas dispatching rules and EPN do not explicitly optimize weighted tardiness. Additionally, `avg_utilization` is normalized by $C_{\max}$, making it strictly proportional to $1 / C_{\max}$ for any fixed instance workload $\sum p_{ij}$.
3. **External Validity (Synthetic Instance Distributions & Fixed EPN Horizon):** Although Stage 10 expanded evaluation to 50 instances across 5 tiers including dynamic breakdowns (`TIER3`) and re-entrant repeated-machine routing (`TIER5`), all instances are synthetically generated with up to $25$ jobs and $10$ machines. The EPN checkpoint (`input_dim=5, horizon_T=40`) natively encodes up to $5$ operations per job pass and extrapolates the final predicted slot for operations beyond $5$.
4. **Statistical Conclusion Validity ($n = 10$ Seeds per Tier & Multi-Threaded CP-SAT):** While $n = 10$ seeds per tier provides $>99\%$ power for large effects ($d_z > 2.0$), smaller effect sizes ($|d_z| < 0.85$) require $n \ge 30$ seeds per tier to resolve. Furthermore, `CPSATSchedulingOptimizer` uses `num_search_workers = 4` with a wall-clock timeout, introducing minor incumbent variation on time-bounded instances if re-solved under different CPU loads.

---

## 6. Paper-Ready Claims Checklist (What Can and Cannot Be Claimed)

### Supported Claims (Backed by Verified Stage 9 & Stage 10 Artifacts)
- **Claim S1 (Constraint Satisfaction):** All seven scheduling algorithms (`FCFS`, `SPT`, `EDD`, `CR`, `AGING`, `CP-SAT`, `EPN`) and all four EPN ablation modes produce $100\%$ constraint-valid schedules across all $650$ evaluated trials, verified by two independent validators (`ScheduleValidator` and `IndependentScheduleAuditor`).
- **Claim S2 (CP-SAT vs. Classic Dispatching Heuristics):** Within a $2.0\text{s–}2.5\text{s}$ time budget, CP-SAT reduces mean makespan by **$38.12\%\text{–}53.10\%$** and mean total tardiness by **$73.04\%\text{–}95.95\%$** compared to `SPT` across medium (`TIER2`), dynamic breakdown (`TIER3`), large-scale (`TIER4`), and re-entrant routing (`TIER5`) shop floors ($p_{\text{Holm}} \le 2.5 \times 10^{-5}$ on all comparisons). On small low-contention instances (`TIER1_SMALL`), `FCFS` achieves a mean makespan within $1.67\%$ of `CP-SAT` ($p = 0.467$), though `CP-SAT` still significantly reduces total tardiness by $54.54\%$ ($p_{\text{Holm}} = 0.0028$).
- **Claim S3 (EPN Root-Cause & Operation-Level Ready-Queue Decoding):** The poor baseline performance of `EPN_BASELINE` in Stage 9 is caused ($>99\%$) by job-sequential outer-loop serialization rather than positive neural slot offsets (`<0.60%` impact). Replacing job-sequential decoding with chronological operation-level ready-queue decoding guided by pure EPN predicted slots (`EPN_ABLATION_B_OP_READY_DECODING`) — without retraining the PyTorch checkpoint or using SPT duration rules — reduces EPN mean makespan by **$49.25\%\text{–}71.13\%$** and total tardiness by **$83.64\%\text{–}93.61\%$** across Tiers 1–5 ($p_{\text{Holm}} \le 8.1 \times 10^{-5}$).

### Prohibited Claims (Must Not Appear in the Paper)
- **Do NOT claim** that CP-SAT reduces makespan by `"47%–53%"` across all multi-job tiers (the exact range across Tiers 2–5 is **$38.12\%\text{–}53.10\%$**).
- **Do NOT claim** that CP-SAT finds proven globally optimal schedules on all instances (it proves `OPTIMAL` on **$15/50 = 30.0\%$** of instances across Tiers 1–5 and returns time-bounded `FEASIBLE` solutions on the remaining $70.0\%$).
- **Do NOT claim** that `EPN_BASELINE` outperforms classic heuristics (`EPN_BASELINE` underperforms `SPT` on Tiers 1–5; only the operation-level ready-queue decoded variants `EPN_ABLATION_B_OP_READY_DECODING` and `EPN_ABLATION_C_HYBRID_SPT` outperform `SPT`).

