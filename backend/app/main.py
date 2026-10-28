from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.schemas.models import Job, Machine, ScheduleResult, MachineStatus
from app.core.state_service import ProductionStateService
from app.ml.recommender import MLStrategyRecommender
from app.simulation.engine import DiscreteEventSimulator
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer

app = FastAPI(
    title="AI-Assisted Dynamic Job-Shop Scheduling System",
    description="Real-time multi-machine constraint optimization and machine learning scheduling platform",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ml_recommender = MLStrategyRecommender()
simulator = DiscreteEventSimulator()

@app.on_event("startup")
def startup_event():
    jobs_file = str(DATA_DIR / "initial_jobs.json")
    machines_file = str(DATA_DIR / "initial_machines.json")
    ProductionStateService.seed_if_empty(jobs_file, machines_file)
    
    # Train ML strategy recommender
    base_jobs = ProductionStateService.get_all_jobs()
    machines = ProductionStateService.get_all_machines()
    ml_recommender.train_on_simulated_scenarios(base_jobs, machines)

@app.get("/api/health")
def health_check():
    return {"status": "HEALTHY", "system": "Dynamic Job-Shop Scheduler"}

@app.get("/api/machines", response_model=List[Machine])
def get_machines():
    return ProductionStateService.get_all_machines()

@app.get("/api/jobs", response_model=List[Job])
def get_jobs():
    return ProductionStateService.get_all_jobs()

@app.post("/api/jobs", response_model=Job)
def register_job(job: Job):
    try:
        created = ProductionStateService.add_job(job)
        return created
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/schedules/recalculate", response_model=ScheduleResult)
def recalculate_schedule(algorithm: str = Query("CPSAT")):
    try:
        res = ProductionStateService.recalculate_schedule(sim_time=simulator.sim_time, algorithm=algorithm)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/schedules/compare")
def compare_all_algorithms():
    jobs = ProductionStateService.get_all_jobs()
    machines = ProductionStateService.get_all_machines()
    current_time = simulator.sim_time
    
    results = {}
    for rule in ["FCFS", "SPT", "EDD", "CR", "AGING"]:
        res = DispatchHeuristicScheduler.schedule(jobs, machines, current_time, rule=rule)
        results[rule] = res.metrics.dict()
        
    cpsat_res = CPSATSchedulingOptimizer.optimize(jobs, machines, current_time, time_limit_seconds=2.0)
    results["OR-TOOLS CP-SAT"] = cpsat_res.metrics.dict()
    
    return results

@app.get("/api/ml/recommend")
def recommend_strategy():
    jobs = ProductionStateService.get_all_jobs()
    machines = ProductionStateService.get_all_machines()
    return ml_recommender.recommend(jobs, machines, simulator.sim_time)

@app.post("/api/simulation/advance")
def advance_simulation(step_minutes: float = Query(5.0)):
    return simulator.advance_time(step_minutes)

@app.post("/api/simulation/reset")
def reset_simulation():
    simulator.reset()
    return {"status": "SUCCESS", "sim_time": simulator.sim_time}

@app.post("/api/data/reset-demo")
def reset_demo_workload():
    """
    Resets dynamic user-added jobs back to the original demo workload (JOB_001 to JOB_010).
    Faculty benchmark instances and EPN checkpoints remain completely untouched.
    """
    jobs_file = str(DATA_DIR / "initial_jobs.json")
    machines_file = str(DATA_DIR / "initial_machines.json")
    simulator.reset()
    count = ProductionStateService.reset_to_demo_workload(jobs_file, machines_file)
    # Re-train ML recommender with clean demo jobs
    base_jobs = ProductionStateService.get_all_jobs()
    machines = ProductionStateService.get_all_machines()
    ml_recommender.train_on_simulated_scenarios(base_jobs, machines)
    return {"status": "SUCCESS", "message": f"Reset to {count} baseline demo jobs. Non-demo jobs removed. Benchmarks intact."}

@app.get("/api/simulation/status")
def get_simulation_status():
    return simulator.get_status()
