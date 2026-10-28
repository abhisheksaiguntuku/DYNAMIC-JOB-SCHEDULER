from typing import List, Dict, Tuple, Any
from app.scheduling.flow_shop.simulator import FlowShopSimulator

class FlowShopHeuristics:
    """
    Classic Multi-Machine Permutation Flow Shop Heuristics:
    1. Palmer's Slope Heuristic
    2. Campbell, Dudek, and Smith (CDS) Heuristic
    3. Nawaz, Enscore, and Ham (NEH) Heuristic
    4. First-Come, First-Served (FCFS) Benchmark Order
    """

    @staticmethod
    def fcfs(
        job_order: List[str],
        processing_times: Dict[str, List[float]],
        due_dates: Dict[str, float] = None
    ) -> Dict[str, Any]:
        return FlowShopSimulator.simulate(job_order, processing_times, due_dates)

    @staticmethod
    def palmer(
        processing_times: Dict[str, List[float]],
        due_dates: Dict[str, float] = None,
        use_faculty_sign_convention: bool = False
    ) -> Dict[str, Any]:
        """
        Palmer's Slope Index Heuristic.
        Standard definition:
            w_i = 2*i - m - 1 for i in 1..m
            S_j = sum_{i=1}^m w_i * p_{j, i}
        Jobs are ordered in descending order of S_j:
            J1 (32) > J2 (28) > J3 (24) = J5 (24) > J4 (8)
        With tie-breaking by original index (J3 before J5):
            Sequence: J1, J2, J3, J5, J4
        """
        jobs = list(processing_times.keys())
        m = len(processing_times[jobs[0]])

        slope_indices: Dict[str, float] = {}
        for j in jobs:
            times = processing_times[j]
            # Standard Palmer weight: (2*i - m - 1)
            slope = sum((2 * (i + 1) - m - 1) * times[i] for i in range(m))
            slope_indices[j] = slope

        # Sort jobs in descending order of slope index, breaking ties by job order
        job_indices = {j: idx for idx, j in enumerate(jobs)}
        sorted_jobs = sorted(jobs, key=lambda j: (-slope_indices[j], job_indices[j]))
        sim_res = FlowShopSimulator.simulate(sorted_jobs, processing_times, due_dates)
        sim_res["slope_indices"] = slope_indices
        return sim_res

    @staticmethod
    def cds(
        processing_times: Dict[str, List[float]],
        due_dates: Dict[str, float] = None
    ) -> Dict[str, Any]:
        """
        Campbell-Dudek-Smith (CDS) Heuristic.
        Builds m-1 surrogate two-machine problems.
        Stage k (k = 1 ... m-1):
            A_{j, k} = sum_{i=1}^k p_{j, i}
            B_{j, k} = sum_{i=m-k+1}^m p_{j, i}
        Solves each artificial 2-machine problem with Johnson's rule.
        Evaluates resulting permutation on full m-machine shop and picks the best makespan.
        """
        jobs = list(processing_times.keys())
        m = len(processing_times[jobs[0]])

        candidate_schedules = []

        for k in range(1, m):
            surrogate_pt = {}
            for j in jobs:
                a_jk = sum(processing_times[j][:k])
                b_jk = sum(processing_times[j][m - k:])
                surrogate_pt[j] = (a_jk, b_jk)

            # Solve surrogate with Johnson's rule
            from app.scheduling.flow_shop.johnson import JohnsonAlgorithm
            johnson_res = JohnsonAlgorithm.solve(surrogate_pt)
            cand_seq = johnson_res["optimal_sequence"]

            # Evaluate on full flow shop
            sim_cand = FlowShopSimulator.simulate(cand_seq, processing_times, due_dates)
            candidate_schedules.append({
                "stage": k,
                "sequence": cand_seq,
                "makespan": sim_cand["makespan"],
                "sim_result": sim_cand
            })

        # Select candidate with minimal makespan
        best_candidate = min(candidate_schedules, key=lambda x: (x["makespan"], x["sim_result"]["total_tardiness"]))
        res = best_candidate["sim_result"]
        res["all_candidates"] = candidate_schedules
        return res

    @staticmethod
    def neh(
        processing_times: Dict[str, List[float]],
        due_dates: Dict[str, float] = None,
        tie_break_strategy: str = "reported"
    ) -> Dict[str, Any]:
        """
        Nawaz-Enscore-Ham (NEH) Heuristic.
        1. Calculate total processing time for each job across all m machines:
           J5 (62), J4 (56), J3 (54), J1 (46), J2 (38).
        2. Sort jobs descending by total processing time.
        3. Iterative insertion:
           - Insert J4 with J5: [J5, J4] (Cmax=84) vs [J4, J5] (Cmax=86) -> [J5, J4]
           - Insert J3: [J3, J5, J4] (Cmax=104)
           - Insert J1: [J1, J3, J5, J4] (Cmax=120)
           - Insert J2:
             pos 0: ['J2', 'J1', 'J3', 'J5', 'J4'] -> Cmax = 140.0
             pos 4: ['J1', 'J3', 'J5', 'J4', 'J2'] -> Cmax = 140.0
             TIE-BREAK:
             - 'reported': selects pos 4 yielding the faculty's exact reported sequence
               ['J1', 'J3', 'J5', 'J4', 'J2'] with mean tardiness = 4.8.
             - 'first': selects pos 0 ['J2', 'J1', 'J3', 'J5', 'J4'] with mean tardiness = 5.6.
        """
        jobs = list(processing_times.keys())
        total_times = {j: sum(processing_times[j]) for j in jobs}

        # Step 2: Sort descending
        sorted_by_total = sorted(jobs, key=lambda j: (-total_times[j], j))

        current_seq = [sorted_by_total[0]]

        for next_job in sorted_by_total[1:]:
            best_pos = 0
            best_partial_makespan = float('inf')

            # Evaluate insertion positions
            positions = list(range(len(current_seq) + 1))
            if tie_break_strategy == "reported":
                # Reverse iteration breaks ties towards later positions, matching faculty document
                positions = list(reversed(positions))

            for pos in positions:
                trial_seq = current_seq[:pos] + [next_job] + current_seq[pos:]
                trial_res = FlowShopSimulator.simulate(trial_seq, processing_times)
                if trial_res["makespan"] < best_partial_makespan:
                    best_partial_makespan = trial_res["makespan"]
                    best_pos = pos

            current_seq = current_seq[:best_pos] + [next_job] + current_seq[best_pos:]

        return FlowShopSimulator.simulate(current_seq, processing_times, due_dates)
