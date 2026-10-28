# AI-Assisted Dynamic Job-Shop Scheduling & Production Optimization System

A full-stack research and production-scheduling prototype for high-mix, dynamic 10-machine manufacturing environments (`M1–M10`). Built with **FastAPI**, **Google OR-Tools CP-SAT**, **PyTorch Enhanced Pointer Network (EPN)**, **SQLite**, and **React / TypeScript / Vite**.

---

## 1. Architecture & Core Capabilities

- **10-Machine Flexible & Re-Entrant Shop Floor (`M1–M10`):**
  - Primary stages (`M1–M5`: Pattern Making, Mould Making, Casting, Heat Treatment, Machining) and parallel/auxiliary stations (`M6–M10`).
  - Supports arbitrary operation lengths, heterogeneous machine sequences, and re-entrant routes revisiting the same machine across non-adjacent passes.
- **Seven Scheduling Algorithms:**
  - **Classic Dispatching Rules:** `FCFS`, `SPT`, `EDD`, `CR` (Critical Ratio), `AGING` (anti-starvation waiting/slack score).
  - **Constraint Programming (`CPSAT`):** Google OR-Tools CP-SAT multi-criteria optimizer ($J = 10 C_{\max} + 25 \sum w_j T_j + \sum w_j C_j$).
  - **Neural Pointer Network (`EPN`):** PyTorch Enhanced Pointer Network with causal precedence masking (`backend/models/checkpoints/epn_model.pth`, 368 KB) plus Stage 10 operation-level ready-queue decoding modes (`ABLATION_B_OP_READY_DECODING`, `ABLATION_C_HYBRID_SPT`).
- **Production Reliability & Zero-Trust Verification:**
  - Persistent simulation clock and optimistic concurrency `state_version` tracking (`HTTP 409` stale-schedule protection).
  - Non-preemptive machine breakdown (`DOWN`) and recovery (`IDLE`) state transitions; completed and running operations are locked across rescheduling.
  - Dual schedule validation via [`ScheduleValidator`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/scheduling/validator.py) and zero-shared-code [`IndependentScheduleAuditor`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/experiments/stage10_runner.py).

---

## 2. Local Development Setup

### Step 1: Start the FastAPI Backend (Port `8001`)
```powershell
cd backend
python -m pip install -r requirements.txt
$env:PYTHONPATH="."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```
- Interactive OpenAPI Docs: `http://127.0.0.1:8001/docs`
- Health Check: `http://127.0.0.1:8001/api/health`
- On first startup, `ProductionStateService.seed_if_empty()` automatically creates `backend/production_scheduler.db` and seeds the 10 baseline industrial jobs (`JOB_001`–`JOB_010`) and 10 machines (`M1`–`M10`) from `backend/data/`.

### Step 2: Start the React/Vite Frontend (Port `5173`)
```powershell
cd frontend
npm install
npm run dev
```
- Open `http://localhost:5173` in your browser.
- By default, the frontend connects to `http://127.0.0.1:8001/api` (or `VITE_API_BASE_URL` when configured via `.env` / cloud build variables).

---

## 3. Verification & Reproducible Benchmarks

```powershell
# Run the complete 87-test backend regression & audit suite
cd backend
python -m pytest -v --tb=short

# Build the production frontend bundle
cd ../frontend
npm run build

# Run the reproducible Stage 9 & Stage 10 benchmark runners
cd ../backend
python -m app.experiments.stage9_benchmark
python -m app.experiments.stage10_runner
```

---

## 4. Known Limitations & Cloud Hosting Notes

- **Ephemeral SQLite on Free Cloud Hosting:** When deployed on Render Free Web Services, the container filesystem is ephemeral and spins down after 15 minutes of inactivity (causing a 30–60s cold-start delay on the next request). Any dynamic jobs or simulation clock advances made during a live session are reset to the 10-job baseline workload (`backend/data/initial_jobs.json`) whenever the container restarts or **Reset Demo** (`POST /api/data/reset-demo`) is clicked.
- **CP-SAT Time Budget:** Online API calls cap CP-SAT at `2.0s–3.0s` (`num_search_workers = 4`), returning proven `OPTIMAL` schedules on small instances and high-quality time-bounded `FEASIBLE` schedules on contended 10–25 job instances.

---

## 5. Key Documentation

- **Release & Audit Reports:** [`docs/STAGE11_RELEASE_REPORT.md`](docs/STAGE11_RELEASE_REPORT.md) | [`docs/STAGE10_RESEARCH_AUDIT.md`](docs/STAGE10_RESEARCH_AUDIT.md) | [`docs/STAGE10_EXPERIMENTAL_REPORT.md`](docs/STAGE10_EXPERIMENTAL_REPORT.md)
- **Cloud Deployment Guide:** [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md)
- **Faculty Demonstration Script:** [`docs/FACULTY_DEMO_SCRIPT.md`](docs/FACULTY_DEMO_SCRIPT.md)
- **GitHub Repository:** `https://github.com/abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER.git`
