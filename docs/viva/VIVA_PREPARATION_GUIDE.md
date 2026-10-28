# Academic Viva Defense & Technical Q&A Preparation Guide
## Machine-Learning-Assisted Dynamic Job-Shop Production Scheduling

### 1. Fundamentals of Job-Shop Scheduling
**Q: What is the fundamental difference between a Flow Shop and a Job Shop?**
- **A**: In a **Flow Shop** (like the 2-machine and 5-machine benchmarks), all jobs follow an identical, unidirectional machine route ($M_1 \to M_2 \dots \to M_m$). In a **Job Shop** (our 10-machine system), each job has its own specific operation sequence, which may visit machines in arbitrary orders and omit certain machines entirely.

**Q: Why is Job-Shop Scheduling NP-Hard?**
- **A**: The disjunctive sequencing of operations across shared machine resources results in a combinatorial search space of $(n!)^m$ possible permutations for $n$ jobs across $m$ machines.

---

### 2. Faculty Benchmark Verification
**Q: How did you verify the 2-Machine Flow-Shop benchmark?**
- **A**: We implemented **Johnson’s Algorithm** ($F2 \mid \mid C_{\max}$). The smallest durations on $M_1$ are placed earliest, and smallest on $M_2$ latest. The resulting sequence $E \to C \to D \to B \to A$ was simulated using the recurrence relation:
  $$C_{\pi(k), i} = \max(C_{\pi(k-1), i}, C_{\pi(k), i-1}) + p_{\pi(k), i}$$
  yielding an exact makespan of **50.0 Hours**.

**Q: What discrepancy did you discover in the 5-Machine benchmark?**
- **A**: In the faculty document, the CDS heuristic results table reported the sequence $J_2 \to J_1 \to J_3 \to J_5 \to J_4$, whereas the Gantt figure caption cited $J_2 \to J_3 \to J_5 \to J_4 \to J_1$. We simulated both: both achieve the optimal makespan of $140.0$ minutes, but the table sequence achieves a lower mean flow time (90.4 vs 93.6 min) and lower mean tardiness (5.6 vs 7.2 min).

---

### 3. Dynamic Event Handling & State Preservation
**Q: What happens when a new job arrives in your system?**
- **A**: The system triggers an **event-driven recalculation** rather than an arbitrary append to a queue:
  1. The simulation clock is preserved.
  2. Completed operations remain immutable historical records.
  3. Operations currently running on machines remain locked in-flight (non-preemption).
  4. The future planning horizon is re-optimized for all remaining and newly arrived operations.

---

### 4. Neural Network Methodology (Liu et al., IEEE TASE 2024)
**Q: How does your neural network guarantee 100% precedence feasibility?**
- **A**: We implemented the **Enhanced Pointer Network (EPN)** with a **dynamic causal masking mechanism**. During decoding of operation $j+1$, all time slots $t < \psi_j$ are masked with $-\infty$ attention logits. This mathematically prevents the decoder from predicting an earlier start time for a subsequent operation.

**Q: Why not use direct end-to-end Reinforcement Learning for the entire factory?**
- **A**: As proved by Liu et al. (2024), direct RL on full multi-machine factories suffers from combinatorial state explosion and frequent constraint violations. Decomposing the problem into surrogate part-level subproblems makes the learning problem tractable and highly generalizable.
