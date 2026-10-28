import random
import numpy as np
from typing import List, Dict, Tuple
from sklearn.ensemble import RandomForestClassifier
from app.schemas.models import Job, Machine
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer

class MLStrategyRecommender:
    """
    Supervised Machine Learning Model for Intelligent Scheduling Strategy Selection.
    Extracts 8 state features from current shop floor and predicts best dispatch rule or CP-SAT.
    """
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=60, random_state=42)
        self.is_trained = False
        self.feature_names = [
            "num_jobs",
            "num_operations",
            "avg_job_slack",
            "min_job_slack",
            "urgent_jobs_ratio",
            "utilization_estimate",
            "arrival_dispersion",
            "workload_variance"
        ]

    def extract_features(self, jobs: List[Job], machines: List[Machine], current_time: float) -> np.ndarray:
        if not jobs:
            return np.zeros((1, len(self.feature_names)))

        total_ops = sum(len(j.operations) for j in jobs)
        slacks = []
        urgent_count = 0
        total_work = 0.0
        
        for j in jobs:
            rem_duration = sum(op.duration for op in j.operations)
            total_work += rem_duration
            time_left = j.due_date - current_time
            slack = time_left - rem_duration
            slacks.append(slack)
            if slack <= 30.0:
                urgent_count += 1
                
        avg_slack = float(np.mean(slacks)) if slacks else 0.0
        min_slack = float(np.min(slacks)) if slacks else 0.0
        urgent_ratio = urgent_count / len(jobs) if jobs else 0.0
        
        # Approximate utilization workload across machines
        work_per_machine = {m.machine_id: 0.0 for m in machines}
        for j in jobs:
            for op in j.operations:
                if op.machine_id in work_per_machine:
                    work_per_machine[op.machine_id] += op.duration
        work_vals = list(work_per_machine.values())
        work_var = float(np.var(work_vals)) if work_vals else 0.0
        util_est = total_work / (len(machines) * 200.0) if machines else 0.0
        
        arrivals = [j.arrival_time for j in jobs]
        arr_disp = float(np.std(arrivals)) if arrivals else 0.0
        
        features = np.array([
            len(jobs),
            total_ops,
            avg_slack,
            min_slack,
            urgent_ratio,
            util_est,
            arr_disp,
            work_var
        ]).reshape(1, -1)
        
        return features

    def train_on_simulated_scenarios(self, base_jobs: List[Job], machines: List[Machine]):
        """Generates synthetic shop floor conditions to train classifier."""
        if not base_jobs or len(base_jobs) < 1:
            return

        X_train = []
        y_train = []
        rules = ["FCFS", "SPT", "EDD", "CR", "AGING"]
        min_sample = min(3, len(base_jobs))
        
        for scenario_idx in range(40):
            # Vary deadlines, arrival times, job subsets
            sample_size = random.randint(min_sample, len(base_jobs))
            sub_jobs = random.sample(base_jobs, sample_size)
            
            # Perturb arrival and due date
            perturbed_jobs = []
            for j in sub_jobs:
                j_copy = j.copy(deep=True)
                j_copy.arrival_time = random.uniform(0.0, 30.0)
                j_copy.due_date = max(j_copy.arrival_time + 80.0, j_copy.due_date + random.uniform(-40.0, 50.0))
                perturbed_jobs.append(j_copy)
                
            features = self.extract_features(perturbed_jobs, machines, current_time=0.0)[0]
            
            # Evaluate all candidate heuristics
            best_rule = "EDD"
            best_cost = float('inf')
            
            for r in rules:
                res = DispatchHeuristicScheduler.schedule(perturbed_jobs, machines, current_time=0.0, rule=r)
                # Combined objective: makespan + 2 * total_tardiness
                cost = res.metrics.makespan + (2.0 * res.metrics.total_tardiness)
                if cost < best_cost:
                    best_cost = cost
                    best_rule = r
                    
            X_train.append(features)
            y_train.append(best_rule)
            
        self.model.fit(np.array(X_train), y_train)
        self.is_trained = True

    def recommend(self, jobs: List[Job], machines: List[Machine], current_time: float) -> Dict[str, Any]:
        if not self.is_trained:
            # Fallback to EDD/CR when untrained
            return {
                "recommended_algorithm": "EDD",
                "confidence": 0.85,
                "reason": "Default heuristic prioritizing approaching due dates."
            }
            
        features = self.extract_features(jobs, machines, current_time)
        pred = self.model.predict(features)[0]
        probs = self.model.predict_proba(features)[0]
        confidence = float(np.max(probs))
        
        return {
            "recommended_algorithm": pred,
            "confidence": round(confidence, 3),
            "reason": f"Predicted best strategy '{pred}' based on job urgency and workload features."
        }
