from typing import List, Dict, Tuple, Any
from app.scheduling.flow_shop.simulator import FlowShopSimulator

class JohnsonAlgorithm:
    """
    Johnson's Rule for Two-Machine Flow Shops (F2 || Cmax).
    Finds the exact optimal job sequence minimizing makespan.
    Rule:
    1. Look for the minimum processing time among all remaining unscheduled jobs across M1 and M2.
    2. If the minimum occurs on Machine 1, place that job in the earliest available position.
    3. If the minimum occurs on Machine 2, place that job in the latest available position.
    4. Remove the job and repeat until all jobs are sequenced.
    """
    @classmethod
    def solve(cls, processing_times: Dict[str, Tuple[float, float]]) -> Dict[str, Any]:
        jobs = list(processing_times.keys())
        n = len(jobs)
        sequence: List[str] = [None] * n
        left = 0
        right = n - 1

        unscheduled = set(jobs)

        while unscheduled:
            min_val = float('inf')
            best_job = None
            machine_idx = None

            for j in sorted(list(unscheduled)):  # Deterministic tie-breaking by name
                p1, p2 = processing_times[j]
                if p1 < min_val:
                    min_val = p1
                    best_job = j
                    machine_idx = 0
                if p2 < min_val:
                    min_val = p2
                    best_job = j
                    machine_idx = 1

            if machine_idx == 0:
                sequence[left] = best_job
                left += 1
            else:
                sequence[right] = best_job
                right -= 1

            unscheduled.remove(best_job)

        # Convert to list of processing durations for simulator
        pt_dict = {j: list(processing_times[j]) for j in sequence}
        sim_res = FlowShopSimulator.simulate(sequence, pt_dict, machine_labels=["Machine 1", "Machine 2"])

        return {
            "algorithm": "Johnson's Rule",
            "optimal_sequence": sequence,
            "simulation": sim_res
        }
