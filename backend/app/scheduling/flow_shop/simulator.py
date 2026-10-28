from typing import List, Dict, Tuple, Any

class FlowShopSimulator:
    """
    Standard Permutation Flow-Shop Schedule Simulator.
    Given a permutation sequence pi of jobs and an m x n processing matrix:
    Computes exact start and end times for each job on every machine using the recurrence:
        C(pi(k), i) = max(C(pi(k-1), i), C(pi(k), i-1)) + p(pi(k), i)
    """
    @staticmethod
    def simulate(
        job_order: List[str],
        processing_times: Dict[str, List[float]],
        due_dates: Dict[str, float] = None,
        machine_labels: List[str] = None
    ) -> Dict[str, Any]:
        num_jobs = len(job_order)
        if num_jobs == 0:
            return {"makespan": 0.0, "intervals": {}, "completion_times": {}}

        first_job = job_order[0]
        num_machines = len(processing_times[first_job])
        if machine_labels is None:
            machine_labels = [f"M{i+1}" for i in range(num_machines)]

        # Completion time table: completion_matrix[k][i] = completion time of job_order[k] on machine i
        completion_matrix = [[0.0] * num_machines for _ in range(num_jobs)]
        start_matrix = [[0.0] * num_machines for _ in range(num_jobs)]

        for k, job_id in enumerate(job_order):
            times = processing_times[job_id]
            for i in range(num_machines):
                p_val = times[i]
                prev_machine_comp = completion_matrix[k][i - 1] if i > 0 else 0.0
                prev_job_comp = completion_matrix[k - 1][i] if k > 0 else 0.0
                start_t = max(prev_machine_comp, prev_job_comp)
                end_t = start_t + p_val
                start_matrix[k][i] = round(start_t, 2)
                completion_matrix[k][i] = round(end_t, 2)

        # Build detailed schedule intervals
        intervals_by_machine: Dict[str, List[Dict[str, Any]]] = {m: [] for m in machine_labels}
        job_completions: Dict[str, float] = {}

        for k, job_id in enumerate(job_order):
            for i, m_name in enumerate(machine_labels):
                intervals_by_machine[m_name].append({
                    "job_id": job_id,
                    "start": start_matrix[k][i],
                    "end": completion_matrix[k][i],
                    "duration": processing_times[job_id][i]
                })
            job_completions[job_id] = completion_matrix[k][num_machines - 1]

        makespan = completion_matrix[num_jobs - 1][num_machines - 1]
        avg_completion = sum(job_completions.values()) / num_jobs

        # Tardiness metrics if due dates exist
        total_tardiness = 0.0
        tardy_jobs = 0
        tardiness_by_job: Dict[str, float] = {}
        if due_dates:
            for job_id, c_j in job_completions.items():
                d_j = due_dates.get(job_id, c_j)
                tardiness = max(0.0, c_j - d_j)
                tardiness_by_job[job_id] = round(tardiness, 2)
                total_tardiness += tardiness
                if tardiness > 1e-4:
                    tardy_jobs += 1

        mean_tardiness = total_tardiness / num_jobs if due_dates else 0.0

        return {
            "job_order": job_order,
            "makespan": round(makespan, 2),
            "avg_completion_time": round(avg_completion, 2),
            "total_tardiness": round(total_tardiness, 2),
            "mean_tardiness": round(mean_tardiness, 2),
            "tardy_jobs_count": tardy_jobs,
            "job_completions": job_completions,
            "tardiness_by_job": tardiness_by_job,
            "intervals_by_machine": intervals_by_machine
        }
