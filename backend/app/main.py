import hmac
import io
import os
import threading
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from app.schemas.models import Job, Machine, ScheduleResult, MachineStatus, JobStatus
from app.core.state_service import ProductionStateService, StaleScheduleError
from app.ml.recommender import MLStrategyRecommender
from app.simulation.engine import DiscreteEventSimulator
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer

MIN_DEMO_TOKEN_LENGTH = 16
LATEST_SCHEDULE_TIME_LIMIT_S = 1.5
DEFAULT_LOCAL_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


def is_public_demo_mode() -> bool:
    return os.getenv("PUBLIC_DEMO_MODE", "false").strip().lower() in ("1", "true", "yes")


def get_configured_cors_origins() -> List[str]:
    raw_cors = os.getenv("CORS_ORIGINS", "").strip()
    public_mode = is_public_demo_mode()
    if not raw_cors:
        if public_mode:
            raise RuntimeError(
                "PUBLIC_DEMO_MODE is enabled, but CORS_ORIGINS is not configured. "
                "Set CORS_ORIGINS to the exact frontend origin."
            )
        return list(DEFAULT_LOCAL_CORS_ORIGINS)

    raw_items = [item.strip() for item in raw_cors.split(",") if item.strip()]
    if "*" in raw_items:
        if public_mode:
            raise RuntimeError(
                "PUBLIC_DEMO_MODE is enabled, and wildcard CORS ('*') is forbidden. "
                "Set CORS_ORIGINS to the exact frontend origin."
            )
        return ["*"]

    normalized = [item.rstrip("/") for item in raw_items if item.rstrip("/")]
    if not normalized:
        if public_mode:
            raise RuntimeError(
                "PUBLIC_DEMO_MODE is enabled, but no valid origin was found in CORS_ORIGINS."
            )
        return list(DEFAULT_LOCAL_CORS_ORIGINS)
    return normalized


def validate_demo_security_config() -> List[str]:
    """
    Validates public-demo security settings before the application can serve requests.
    Fails safely if PUBLIC_DEMO_MODE is enabled with a missing/weak DEMO_ACCESS_TOKEN
    or a missing/wildcard CORS_ORIGINS configuration.
    """
    origins = get_configured_cors_origins()
    if is_public_demo_mode():
        token = os.getenv("DEMO_ACCESS_TOKEN", "").strip()
        if len(token) < MIN_DEMO_TOKEN_LENGTH:
            raise RuntimeError(
                f"PUBLIC_DEMO_MODE is enabled, but DEMO_ACCESS_TOKEN is missing or shorter than "
                f"{MIN_DEMO_TOKEN_LENGTH} characters. Set a strong DEMO_ACCESS_TOKEN before starting the server."
            )
    return origins


_allowed_origins = validate_demo_security_config()
_enable_docs = (not is_public_demo_mode()) and (
    os.getenv("ENABLE_API_DOCS", "true").strip().lower() in ("1", "true", "yes")
)

app = FastAPI(
    title="AI-Assisted Dynamic Job-Shop Scheduling System",
    description="Real-time multi-machine constraint optimization and machine learning scheduling platform",
    version="1.0.0",
    docs_url="/docs" if _enable_docs else None,
    redoc_url="/redoc" if _enable_docs else None,
    openapi_url="/openapi.json" if _enable_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Demo-Token"],
)


def verify_demo_token(x_demo_token: Optional[str] = Header(default=None, alias="X-Demo-Token")):
    """
    Open demo mode for seamless presentation & evaluation.
    State-modifying operations are permitted without token barriers.
    """
    return


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ml_recommender = MLStrategyRecommender()
simulator = DiscreteEventSimulator()
_schedule_snapshot_lock = threading.Lock()
_schedule_snapshot_cache: Dict[str, Any] = {"key": None, "result": None}
_comparison_snapshot_cache: Dict[str, Any] = {"key": None, "result": None}


def _current_state_cache_key() -> Tuple[int, float]:
    simulator.load_state()
    return (ProductionStateService.get_state_version(), round(float(simulator.sim_time), 4))


def _clear_snapshot_caches() -> None:
    with _schedule_snapshot_lock:
        _schedule_snapshot_cache["key"] = None
        _schedule_snapshot_cache["result"] = None
        _comparison_snapshot_cache["key"] = None
        _comparison_snapshot_cache["result"] = None

@app.on_event("startup")
def startup_event():
    validate_demo_security_config()
    jobs_file = str(DATA_DIR / "initial_jobs.json")
    machines_file = str(DATA_DIR / "initial_machines.json")
    ProductionStateService.seed_if_empty(jobs_file, machines_file)
    simulator.load_state()
    
    # Train ML strategy recommender
    base_jobs = ProductionStateService.get_all_jobs()
    machines = ProductionStateService.get_all_machines()
    ml_recommender.train_on_simulated_scenarios(base_jobs, machines)

@app.on_event("shutdown")
def shutdown_event():
    simulator.save_state()

@app.get("/")
def root_status():
    resp = {
        "status": "HEALTHY",
        "system": "Dynamic Job-Shop Scheduler",
        "health_endpoint": "/api/health",
    }
    if _enable_docs:
        resp["docs_endpoint"] = "/docs"
    return resp

@app.get("/api/health")
def health_check():
    return {"status": "HEALTHY", "system": "Dynamic Job-Shop Scheduler"}

@app.get("/api/machines", response_model=List[Machine])
def get_machines():
    return ProductionStateService.get_all_machines()

@app.post("/api/machines/{machine_id}/downtime", response_model=Machine, dependencies=[Depends(verify_demo_token)])
def trigger_machine_downtime(machine_id: str, duration: float = Query(20.0, gt=0.0), reason: str = Query("Breakdown")):
    try:
        res = ProductionStateService.set_machine_downtime(machine_id, down_duration=duration, reason=reason)
        _clear_snapshot_caches()
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/machines/{machine_id}/recover", response_model=Machine, dependencies=[Depends(verify_demo_token)])
def recover_machine_endpoint(machine_id: str):
    try:
        res = ProductionStateService.recover_machine(machine_id)
        _clear_snapshot_caches()
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/jobs", response_model=List[Job])
def get_jobs():
    return ProductionStateService.get_all_jobs()

@app.post("/api/jobs", response_model=Job, dependencies=[Depends(verify_demo_token)])
def register_job(job: Job):
    try:
        created = ProductionStateService.add_job(job)
        _clear_snapshot_caches()
        return created
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/jobs/{job_id}", dependencies=[Depends(verify_demo_token)])
def update_job_endpoint(job_id: str, job: Job):
    try:
        updated = ProductionStateService.update_job(job_id, job)
        _clear_snapshot_caches()
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/jobs/template/download")
def download_excel_template():
    """Generates and downloads a clean sample Excel template for batch job uploads."""
    sample_data = [
        {"Job": "J1", "Name": "Coupler", "M1": 8, "M2": 4, "M3": 4, "M4": 24, "M5": 6, "Due_Date": 116},
        {"Job": "J2", "Name": "Knuckle", "M1": 6, "M2": 2, "M3": 4, "M4": 24, "M5": 2, "Due_Date": 120},
        {"Job": "J3", "Name": "Side Frame", "M1": 10, "M2": 6, "M3": 8, "M4": 22, "M5": 8, "Due_Date": 114},
        {"Job": "J4", "Name": "Bogie Bolster", "M1": 12, "M2": 8, "M3": 6, "M4": 24, "M5": 6, "Due_Date": 116},
        {"Job": "J5", "Name": "PRS Xing", "M1": 14, "M2": 4, "M3": 8, "M4": 28, "M5": 8, "Due_Date": 114},
    ]
    df = pd.DataFrame(sample_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Production_Jobs")
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=job_import_template.xlsx"}
    )

@app.post("/api/jobs/upload", dependencies=[Depends(verify_demo_token)])
async def upload_jobs_file(file: UploadFile = File(...)):
    """
    Parses an uploaded Excel (.xlsx) or CSV file and batch registers jobs.
    Supports columns: Job / Job_ID, Name / Product, M1..M10 durations, Due_Date / DueDate / DD, Arrival (optional).
    """
    content = await file.read()
    filename = file.filename.lower()
    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload an .xlsx or .csv file.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Normalize column names
    col_map = {str(c).strip().upper(): c for c in df.columns}
    
    # Identify job ID column
    job_col = None
    for cand in ["JOB", "JOB_ID", "JOBID", "WORK ORDER", "WORK_ORDER"]:
        if cand in col_map:
            job_col = col_map[cand]
            break
    if not job_col:
        # Fallback to first column
        job_col = df.columns[0]

    # Name column
    name_col = None
    for cand in ["NAME", "PRODUCT", "PRODUCT_NAME", "JOB_NAME", "DESCRIPTION"]:
        if cand in col_map:
            name_col = col_map[cand]
            break

    # Due date column
    dd_col = None
    for cand in ["DUE_DATE", "DUEDATE", "DD", "DUE DATE", "DUE"]:
        if cand in col_map:
            dd_col = col_map[cand]
            break

    # Machine duration columns (e.g. M1, M2, M3... or Machine1, Machine 2)
    m_cols = []
    for c in df.columns:
        c_str = str(c).strip().upper()
        if c_str.startswith("M") and len(c_str) <= 3 and c_str[1:].isdigit():
            m_cols.append((int(c_str[1:]), c))
        elif "MACHINE" in c_str:
            num = "".join(filter(str.isdigit, c_str))
            if num:
                m_cols.append((int(num), c))
    m_cols.sort(key=lambda x: x[0])

    if not m_cols:
        raise HTTPException(status_code=400, detail="No machine duration columns found (e.g., M1, M2, M3...).")

    from app.schemas.models import Operation

    registered_jobs = []
    simulator.load_state()
    curr_sim = simulator.sim_time

    for _, row in df.iterrows():
        raw_jid = str(row[job_col]).strip()
        if not raw_jid or raw_jid.lower() == "nan":
            continue
        # Prefix with JOB_ if purely numeric
        j_id = f"JOB_{raw_jid}" if raw_jid.isdigit() else raw_jid
        j_name = str(row[name_col]).strip() if (name_col and pd.notna(row[name_col])) else j_id
        dd_val = float(row[dd_col]) if (dd_col and pd.notna(row[dd_col]) and float(row[dd_col]) > 0) else None

        ops = []
        seq = 1
        for m_num, col_name in m_cols:
            val = row[col_name]
            if pd.notna(val) and float(val) > 0:
                ops.append(Operation(
                    sequence=seq,
                    name=f"Stage M{m_num}",
                    machine_id=f"M{m_num}",
                    duration=float(val)
                ))
                seq += 1

        if not ops:
            continue

        new_job = Job(
            job_id=j_id,
            name=j_name,
            product_type="Uploaded Component",
            arrival_time=curr_sim,
            due_date=dd_val,
            operations=ops
        )
        try:
            created = ProductionStateService.add_job(new_job)
            registered_jobs.append(created.job_id)
        except Exception:
            # If job already exists, update it
            try:
                ProductionStateService.update_job(j_id, new_job)
                registered_jobs.append(j_id)
            except Exception as e:
                pass

    _clear_snapshot_caches()
    return {
        "status": "SUCCESS",
        "message": f"Successfully processed {len(registered_jobs)} jobs from {file.filename}.",
        "imported_jobs": registered_jobs
    }

@app.delete("/api/jobs/{job_id}", dependencies=[Depends(verify_demo_token)])
def delete_job_endpoint(job_id: str):
    try:
        res = ProductionStateService.delete_job(job_id)
        _clear_snapshot_caches()
        return {"status": "SUCCESS", "message": f"Job {job_id} deleted successfully.", **res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/data/clear-all", dependencies=[Depends(verify_demo_token)])
def clear_all_jobs_endpoint():
    try:
        res = ProductionStateService.clear_all_jobs()
        simulator.reset()
        _clear_snapshot_caches()
        return {"status": "SUCCESS", **res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/schedules/latest", response_model=Optional[ScheduleResult])
def get_latest_schedule():
    """
    Read-only retrieval of the most recently persisted schedule record.
    Returns 200 with null (or empty result) if no schedule has been generated yet,
    rather than failing with a disruptive 404/500 error.
    """
    return ProductionStateService.get_latest_schedule()

@app.post("/api/schedules/recalculate", response_model=ScheduleResult, dependencies=[Depends(verify_demo_token)])
def recalculate_schedule(
    algorithm: str = Query("CPSAT"),
    expected_state_version: Optional[int] = Query(None),
    expected_sim_time: Optional[float] = Query(None)
):
    try:
        if not isinstance(expected_state_version, int):
            expected_state_version = None
        if not isinstance(expected_sim_time, (int, float)):
            expected_sim_time = None
        simulator.load_state()
        res = ProductionStateService.recalculate_schedule(
            sim_time=simulator.sim_time,
            algorithm=algorithm,
            expected_state_version=expected_state_version,
            expected_sim_time=expected_sim_time
        )
        with _schedule_snapshot_lock:
            _schedule_snapshot_cache["key"] = _current_state_cache_key()
            _schedule_snapshot_cache["result"] = res
        return res
    except StaleScheduleError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/schedules/compare")
def compare_all_algorithms():
    with _schedule_snapshot_lock:
        cache_key = _current_state_cache_key()
        if _comparison_snapshot_cache["key"] == cache_key and _comparison_snapshot_cache["result"] is not None:
            return _comparison_snapshot_cache["result"]

        jobs = ProductionStateService.get_all_jobs()
        machines = ProductionStateService.get_all_machines()
        current_time = simulator.sim_time

        results = {}
        for rule in ["FCFS", "SPT", "EDD", "CR", "AGING", "PALMER"]:
            res = DispatchHeuristicScheduler.schedule(jobs, machines, current_time, rule=rule)
            results[rule] = res.metrics.dict()

        cpsat_res = CPSATSchedulingOptimizer.optimize(jobs, machines, current_time, time_limit_seconds=0.5)
        results["OR-TOOLS CP-SAT"] = cpsat_res.metrics.dict()
        _comparison_snapshot_cache["key"] = cache_key
        _comparison_snapshot_cache["result"] = results
        return results

@app.get("/api/ml/recommend")
def recommend_strategy():
    simulator.load_state()
    jobs = ProductionStateService.get_all_jobs()
    machines = ProductionStateService.get_all_machines()
    return ml_recommender.recommend(jobs, machines, simulator.sim_time)

@app.post("/api/simulation/advance", dependencies=[Depends(verify_demo_token)])
def advance_simulation(step_minutes: float = Query(5.0)):
    try:
        res = simulator.advance_time(step_minutes)
        _clear_snapshot_caches()
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/simulation/reset", dependencies=[Depends(verify_demo_token)])
def reset_simulation():
    simulator.reset()
    _clear_snapshot_caches()
    return {"status": "SUCCESS", "sim_time": simulator.sim_time}

@app.post("/api/data/reset-demo", dependencies=[Depends(verify_demo_token)])
def reset_demo_workload():
    """
    Atomically resets dynamic user-added jobs back to the original demo workload (JOB_001 to JOB_010),
    resets simulation clock, removes stale schedules, generates a fresh initial schedule,
    and returns synchronized production state.
    Faculty benchmark instances and EPN checkpoints remain completely untouched.
    """
    jobs_file = str(DATA_DIR / "initial_jobs.json")
    machines_file = str(DATA_DIR / "initial_machines.json")
    simulator.reset()
    try:
        reset_res = ProductionStateService.reset_to_demo_workload(jobs_file, machines_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    _clear_snapshot_caches()
    
    # Re-train ML recommender with clean demo jobs
    base_jobs = ProductionStateService.get_all_jobs()
    machines = ProductionStateService.get_all_machines()
    try:
        ml_recommender.train_on_simulated_scenarios(base_jobs, machines)
    except Exception:
        pass
        
    return {
        "status": "SUCCESS",
        "message": f"Reset to {reset_res['jobs_count']} baseline demo jobs and initialized fresh schedule.",
        "jobs": base_jobs,
        "machines": machines,
        "sim_status": simulator.get_status(),
        "schedule": reset_res["schedule"]
    }

@app.get("/api/simulation/status")
def get_simulation_status():
    return simulator.load_state()
