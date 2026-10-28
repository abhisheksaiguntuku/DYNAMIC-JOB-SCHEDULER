# RESEARCH CLAIMS AND LIMITATIONS AUDIT

**Project:** Dynamic Job-Shop Scheduling System  
**Academic Level:** B.Tech Final Year CSE Research Project  
**Date:** 2026-10-18  

---

## 1. Verifiable Claims (Supported by Reproducible Evidence)

1. **Exact Benchmark Reproduction:**
   - Johnson's rule 2-machine flow-shop benchmark is mathematically reproduced with exact sequence `E -> C -> D -> B -> A` and makespan $C_{max} = 50.0$ hours.
   - Palmer, CDS, and NEH heuristics match reported faculty tables for the 5-machine flow-shop problem ($C_{max} = 144.0, 140.0, 140.0$ min).
2. **Constraint Enforcement & Schedule Safety:**
   - Hard precedence, machine exclusivity (no two tasks on the same machine overlap), and release time constraints are 100% verified by an independent zero-trust `ScheduleValidator`.
   - Running operations during dynamic in-flight rescheduling are strictly locked and cannot be preempted or overwritten.
3. **Solver Fallback Reliability:**
   - If the exact CP-SAT optimizer times out or proves infeasible, the system falls back to dispatch heuristics, independently validates the fallback output, and raises controlled errors if the fallback fails validation.
4. **Computational Latency Advantage:**
   - Single-pass dispatching heuristics and PyTorch EPN inference generate valid schedules in sub-millisecond to low millisecond time ($< 2$ ms), running over $70\times$ faster than CP-SAT integer programming ($~25$ to $3000$ ms).

---

## 2. Refuted, Unsubstantiated, or Overstated Claims

1. **"EPN outperforms CP-SAT by 3–5% in makespan":**
   - **REFUTED / UNSUBSTANTIATED.** On small to medium instances where CP-SAT is allowed sufficient solve time ($1.5$–$3.0$ s), CP-SAT reaches proven global mathematical optimality (`OPTIMAL`), achieving makespans strictly lower than EPN or any single dispatch heuristic (e.g., 147.2 min vs 224.8 min on 10 random seeds).
   - EPN does not outperform mathematically optimal solutions; its genuine academic contribution is **fast real-time inference** when CP-SAT cannot finish within dynamic industrial cycle times.
2. **"10 Dynamic Scenarios covered in unit tests":**
   - **CLARIFIED.** While comprehensive dynamic tests cover machine locks, precedence, release dates, and completed-op preservation across 13 integration scenarios, individual stochastic stress runs are captured through separate scenario scripts rather than unit test suites.
3. **"Full Machine Downtime Recovery Supported":**
   - **NOT IMPLEMENTED.** Although `MachineStatus.DOWN` exists in the schema, automated disruption event injection and recovery loops are not implemented.

---

## 3. Delimitations of the Research

- **Problem Class:** Evaluates 10-machine flexible job-shop scheduling instances with discrete operation sequences.
- **Model Training Scope:** Trained on synthetic surrogate part-level subproblems representing Lagrangian relaxation price vectors.
- **Testing Scope:** Backend unit, integration, and algorithmic correctness verified via pytest (48 passed, 2 skipped, 0 failed). Frontend static build verified (0 errors). Browser-level end-to-end UI rendering marked **NOT VERIFIED**.
