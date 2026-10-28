# Flow Shop Benchmarks Verification Report
## Verification of Faculty Benchmarks & Mathematical Reconciliation

### 1. Two-Machine Benchmark ($F2 \mid \mid C_{\max}$)

#### Data
- **Units**: Hours
- Jobs:
  - $A: (10, 2)$
  - $B: (16, 8)$
  - $C: (6, 10)$
  - $D: (12, 14)$
  - $E: (4, 12)$

#### Execution of Johnson's Rule
1. Smallest duration across all unscheduled jobs is $2$ (Job $A$ on Machine 2). Assigned to last position: `[_, _, _, _, A]`.
2. Smallest duration is $4$ (Job $E$ on Machine 1). Assigned to earliest position: `[E, _, _, _, A]`.
3. Smallest duration is $6$ (Job $C$ on Machine 1). Assigned to earliest position: `[E, C, _, _, A]`.
4. Smallest duration is $8$ (Job $B$ on Machine 2). Assigned to latest position: `[E, C, _, B, A]`.
5. Remaining Job $D$ placed in remaining slot: `[E, C, D, B, A]`.

#### Schedule Intervals & Verification
- **Optimal Sequence**: $E \to C \to D \to B \to A$
- **Machine 1 Schedule**: $E: [0, 4]$, $C: [4, 10]$, $D: [10, 22]$, $B: [22, 38]$, $A: [38, 48]$
- **Machine 2 Schedule**: $E: [4, 16]$, $C: [16, 26]$, $D: [26, 40]$, $B: [40, 48]$, $A: [48, 50]$
- **Verified Makespan**: **50.0 Hours** ($\Delta = 0.00$, Exact Match).

---

### 2. Five-Machine Benchmark ($F5 \mid \mid C_{\max}, \bar{T}, \sum \mathbb{I}(T_j > 0)$)

#### Summary of Reconciled Results

| Algorithm | Verified Sequence | $C_{\max}$ (min) | $\bar{C}$ (min) | Tardy Jobs | Mean Tardiness $\bar{T}$ (min) | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **FCFS** | $J_1 \to J_2 \to J_3 \to J_4 \to J_5$ | **146.0** | **93.6** | **1** | **6.4** | Exact Match |
| **Palmer** | $J_1 \to J_2 \to J_3 \to J_5 \to J_4$ | **144.0** | **94.4** | **2** | **7.2** | Exact Match |
| **CDS** | $J_2 \to J_1 \to J_3 \to J_5 \to J_4$ | **140.0** | **90.4** | **2** | **5.6** | Exact Match |
| **NEH** | $J_1 \to J_3 \to J_5 \to J_4 \to J_2$ | **140.0** | **94.8** | **2** | **4.8** | Exact Match |

---

### 3. Documentation of Discrepancies & Clarifications

1. **Faculty Palmer Slope Convention**:
   - Standard slope weights $w_i = (2i - m - 1)$ produce slope indices:
     - $J_1: +32$
     - $J_2: +28$
     - $J_3: +24$
     - $J_5: +24$
     - $J_4: +8$
   - Sorting in descending order with natural index tie-breaking ($J_3$ before $J_5$) reproduces the reported sequence: $J_1 \to J_2 \to J_3 \to J_5 \to J_4$.

2. **CDS Result Table vs. Gantt Caption**:
   - The faculty table reports $J_2 \to J_1 \to J_3 \to J_5 \to J_4$ ($C_{\max} = 140, \bar{C} = 90.4, \bar{T} = 5.6$).
   - The caption of the faculty Gantt figure cites $J_2 \to J_3 \to J_5 \to J_4 \to J_1$ ($C_{\max} = 140, \bar{C} = 93.6, \bar{T} = 7.2$).
   - **Conclusion**: Both sequences achieve identical optimal makespan $C_{\max} = 140$, but the table sequence is strictly superior on mean flow time ($\bar{C}$) and tardiness ($\bar{T}$).

3. **NEH Mathematical Tie-Breaking**:
   - At the final insertion step for Job $J_2$ into partial sequence $[J_1, J_3, J_5, J_4]$:
     - Position 0 yields: $[J_2, J_1, J_3, J_5, J_4]$ ($C_{\max} = 140.0, \bar{T} = 5.6$).
     - Position 4 yields: $[J_1, J_3, J_5, J_4, J_2]$ ($C_{\max} = 140.0, \bar{T} = 4.8$).
   - The faculty document selected Position 4, achieving the minimal mean tardiness of **4.8 minutes**.
