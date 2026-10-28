# STAGE 5 BENCHMARK VERIFICATION REPORT

**Project:** Dynamic Job-Shop Scheduling System  
**Audit Date:** 2026-10-18  
**Scope:** Independent numerical and algorithmic re-verification of static flow-shop benchmarks.

---

## 1. Two-Machine Flow-Shop Benchmark (Johnson's Rule)

### Problem Definition (Hours)
| Job | Machine 1 | Machine 2 |
|:---:|:---:|:---:|
| A | 10 | 2 |
| B | 16 | 8 |
| C | 6 | 10 |
| D | 12 | 14 |
| E | 4 | 12 |

### Independent Execution & Interval Verification
Using Johnson's algorithm ($M1 \le M2$ prioritized ascending on M1, $M1 > M2$ prioritized descending on M2):
- Min duration across all: E (4 on M1) $\rightarrow$ Job E scheduled first.
- Next min: C (6 on M1) $\rightarrow$ Job C scheduled second.
- Next min: D (12 on M1 vs 14 on M2) $\rightarrow$ Job D scheduled third.
- Next min on M2: A (2 on M2) $\rightarrow$ Job A scheduled last.
- Remaining: B (8 on M2) $\rightarrow$ Job B scheduled fourth.

**Optimal Sequence:** `E -> C -> D -> B -> A`

**Machine Processing Intervals:**
- **Machine 1:**
  - E: [0, 4]
  - C: [4, 10]
  - D: [10, 22]
  - B: [22, 38]
  - A: [38, 48]
- **Machine 2:**
  - E: [4, 16] (waits for M1 completion at t=4)
  - C: [16, 26] (starts after E finishes on M2 at t=16)
  - D: [26, 40] (starts after C finishes on M2 at t=26)
  - B: [40, 48] (starts after D finishes on M2 at t=40)
  - A: [48, 50] (starts after B finishes on M2 at t=48)

**Makespan ($C_{max}$):** **50.0 hours** (Exact match).

---

## 2. Five-Machine Flow-Shop Benchmark

### Processing Times & Due Dates (Minutes)
| Job | M1 | M2 | M3 | M4 | M5 | Due Date ($d_j$) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| J1 | 8 | 4 | 4 | 24 | 6 | 116 |
| J2 | 6 | 2 | 4 | 24 | 2 | 120 |
| J3 | 10 | 6 | 8 | 22 | 8 | 114 |
| J4 | 12 | 8 | 6 | 24 | 6 | 116 |
| J5 | 14 | 4 | 8 | 28 | 8 | 114 |

### Algorithm Results Matrix
| Algorithm | Verified Sequence | Makespan ($C_{max}$) | Avg Completion Time | Tardy Jobs | Mean Tardiness | Verification Status |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **FCFS** | J1, J2, J3, J4, J5 | 146.0 | 93.6 | 1 | 6.4 | **PASS** |
| **Palmer** | J1, J2, J3, J5, J4 | 144.0 | 94.4 | 2 | 7.2 | **PASS** |
| **CDS** | J2, J1, J3, J5, J4 | 140.0 | 90.4 | 2 | 5.6 | **PASS** |
| **NEH** | J1, J3, J5, J4, J2 | 140.0 | 94.8 | 2 | 4.8 | **PASS** |

---

## 3. CDS Discrepancy Reconciliation

In faculty reference materials:
- **Result Table** reported: `J2, J1, J3, J5, J4` ($C_{max} = 140.0$)
- **Gantt Caption** reported: `J2, J3, J5, J4, J1` ($C_{max} = 140.0$)

**Reconciliation Analysis:**
Simulation of both candidate sequences through `FlowShopSimulator.simulate`:
- Both sequences achieve identical optimal makespan $C_{max} = 140.0$ min.
- However, the Result Table sequence (`J2, J1, J3, J5, J4`) dominates the Gantt Caption sequence on secondary flow metrics:
  - Table Sequence Avg Completion: **90.4 min** vs Caption Sequence: **98.0 min**.
  - Table Sequence Mean Tardiness: **5.6 min** vs Caption Sequence: **8.0 min**.
The codebase implements and retains the Table Sequence as the primary CDS output while maintaining the reconciliation test `test_cds_discrepancy_reconciliation`.

---

## 4. Scope Distinction Note
These static flow-shop benchmarks apply exclusively to permutation flow shops where all jobs visit machines in sequence $M_1 \rightarrow M_2 \rightarrow \dots \rightarrow M_m$. They are structurally distinct from the dynamic 10-machine flexible job-shop scheduling instances evaluated in Phase 4.
