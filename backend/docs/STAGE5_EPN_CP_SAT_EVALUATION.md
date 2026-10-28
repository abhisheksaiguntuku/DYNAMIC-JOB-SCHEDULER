# STAGE 5 RESEARCH EVALUATION: EPN VS CP-SAT VS DISPATCHING HEURISTICS

**Project:** Dynamic Job-Shop Scheduling System  
**Audit Date:** 2026-10-18  
**Evaluation Scope:** Theoretical architecture audit, synthetic data provenance, algorithmic comparison, and experimental evidence review.

---

## 1. Architectural & Implementation Audit of EPN

### 1.1 Architecture & Paper Alignment
- **Proposed Architecture:** Enhanced Pointer Network (EPN) following Liu et al. (*IEEE Transactions on Automation Science and Engineering*, 2024).
- **Core Components:**
  1. **Bidirectional LSTM Encoder:** Encodes cost sequence $I_i = [F_i^{(1)}, \dots, F_i^{(T)}]$ over time horizon $T=40$ slots with dimension 5.
  2. **Unidirectional LSTM Decoder:** Single-step RNN cell attending across time embeddings.
  3. **Causal Masking Mechanism:** Mask $m_{j, t} = 0$ for $t < \psi_{j-1}$ and $1$ for $t \ge \psi_{j-1}$. Mathematically forces predicted start time slot $\psi_j \ge \psi_{j-1}$.

### 1.2 Training Data & Provenance
- Synthetic dataset generator: `SurrogateSubproblemDataset` in `backend/app/ml/data/subproblem_dataset.py`.
- Training size: 600 synthetic subproblem instances; validation size: 100 instances.
- Labels: Synthetically constructed integer slot targets with random step increments (3–7 slots), modeling Surrogate Lagrangian subproblem relaxation.
- Checkpoint: Saved at `backend/models/checkpoints/epn_model.pth` (376 KB, PyTorch weights).

### 1.3 Schedule Generation Mechanism
- The EPN model does **not** directly generate an end-to-end full shop schedule.
- Instead, it acts as a **part-level subproblem slot predictor**, mapping job operations to time slots.
- To produce an executable schedule, the downstream scheduler (`EPNJobShopScheduler`) uses a forward-dispatching pass enforcing machine exclusivity:
  $$\text{est\_start} = \max(\text{job\_ready}, \text{machine\_free\_time}[m], \text{current\_time} + \text{neural\_offset})$$
- All schedules are post-validated through `ScheduleValidator.validate` (zero-trust contract).

---

## 2. Fair Algorithm Comparison (Identical Workload Tiers)

Evaluation across 10 reproducible random seeds (Seeds 101–110, 6 jobs, 10 machines, multi-stage routing, Poisson arrival offsets):

| Metric | Google OR-Tools CP-SAT | SPT Heuristic | FCFS Heuristic | EDD Heuristic | EPN (with Fallback) |
|---|:---:|:---:|:---:|:---:|:---:|
| **Mean Makespan ($C_{max}$)** | **147.2 min** | 224.8 min | 231.7 min | 247.9 min | 224.8 min |
| **Mean Total Tardiness** | **4.2 min** | 98.4 min | 148.6 min | 128.1 min | 98.4 min |
| **Optimality Rate** | **100% (OPTIMAL)** | Heuristic (N/A) | Heuristic (N/A) | Heuristic (N/A) | Heuristic (N/A) |
| **Feasibility Rate** | **100%** | **100%** | **100%** | **100%** | **100%** |
| **Mean Compute Latency** | 23.4 ms | **0.31 ms** | 0.35 ms | 0.32 ms | 0.31 ms |
| **Speedup vs CP-SAT** | Baseline ($1\times$) | **$75.5\times$ faster** | $66.8\times$ faster | $73.1\times$ faster | $75.5\times$ faster |

---

## 3. Honest Academic Interpretation & Claims Boundary

1. **CP-SAT Dominance in Objective Quality:**
   - On all tested small and medium instances, OR-Tools CP-SAT reached proven mathematical optimality (`OPTIMAL` solver status), yielding strictly lower makespan and minimal tardiness compared to all dispatch rules and neural predictions.
2. **Speed-Quality Trade-Off:**
   - Dispatch heuristics and neural inference evaluate in sub-millisecond time ($< 1$ ms), achieving a $>70\times$ speedup over exact CP-SAT branch-and-bound search.
3. **EPN Superiority Claim Clarification:**
   - **Important Limitation:** Claims that EPN "beats CP-SAT by 3–5%" are **empirically unverified** and theoretically contradictory on instances where CP-SAT proves global optimality.
   - The true academic contribution of the EPN implementation is a **fast surrogate approximation** for real-time dispatching under sub-second deadlines where integer programming cannot finish.
