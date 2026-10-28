# System Architecture & Technical Specification
## AI-Assisted Dynamic Job-Shop Scheduling and Production Optimization System

### 1. Overview
This system provides intelligent real-time production scheduling and dynamic rescheduling for a 10-machine manufacturing plant, incorporating:
- Google OR-Tools CP-SAT constraint optimization
- 5 Dispatch Heuristics (FCFS, SPT, EDD, Critical Ratio, Aging/Slack)
- Machine Learning (Random Forest / Gradient Boosting) Strategy Recommender
- Discrete-Event Dynamic Factory Simulator
- FastAPI backend with SQLite persistence
- Interactive React/TypeScript dashboard with a dynamic Gantt chart and live telemetry

### 2. Machine Configuration (10 Machines)
- **M1:** Pattern Making (Primary)
- **M2:** Mould Making (Primary)
- **M3:** Casting (Primary)
- **M4:** Heat Treatment (Primary)
- **M5:** Machining (Primary)
- **M6:** Pattern & Core Preparation (Alternative/Auxiliary)
- **M7:** Mould Assembly & Drying (Alternative/Auxiliary)
- **M8:** High-Capacity Casting & Pouring (Alternative/Auxiliary)
- **M9:** Secondary Annealing & Tempering (Alternative/Auxiliary)
- **M10:** Precision CNC Finishing & Quality Inspection (Alternative/Auxiliary)

### 3. Mathematical Formulation (Job-Shop Scheduling Problem)
- **Operations:** Each job $j \in J$ has an ordered sequence of operations $O_{j,1}, O_{j,2}, \dots, O_{j,n_j}$.
- **Precedence:** $\text{start}(O_{j,k}) \ge \text{end}(O_{j,k-1})$
- **Machine Exclusivity:** For any machine $m$, no two operations $O_a, O_b$ assigned to $m$ can overlap:
  $\text{end}(O_a) \le \text{start}(O_b) \lor \text{end}(O_b) \le \text{start}(O_a)$
- **Running Operations Commitment:** Any operation currently processing at time $t_{now}$ cannot be preempted and machine $m$ remains unavailable until $t_{now} + \text{remaining\_time}$.
- **Objectives:**
  $$\min \quad w_{makespan} \cdot C_{max} + w_{tardiness} \cdot \sum_{j} T_j + w_{waiting} \cdot \sum_{j} W_j$$
  where $T_j = \max(0, C_j - D_j)$ and $W_j = C_j - r_j - \sum p_{j,k}$.
