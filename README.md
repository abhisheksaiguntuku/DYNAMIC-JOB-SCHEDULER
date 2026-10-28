---
title: Dynamic Job-Shop Scheduler API
emoji: ⚙️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
suggested_hardware: cpu-basic
---

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
  - Dual schedule validation via [`ScheduleValidator`](backend/app/scheduling/validator.py) and zero-shared-code [`IndependentScheduleAuditor`](backend/app/experiments/stage10_runner.py).

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

## 4. Recommended Free-Tier Cloud Deployment & Known Limitations

- **Recommended Architecture (\$0/month, No Credit Card Required):**
  - **Backend API:** **Hugging Face Spaces (`cpu-basic`, Docker SDK)** — provides **2 vCPUs, 16 GB RAM, 50 GB ephemeral disk**, and a **48-hour inactivity timeout** (compared to Render Free's 512 MB RAM and 15-minute spin-down), effortlessly accommodating our measured **`401.62 MB` peak RSS** footprint and keeping the container warm throughout a scheduled faculty demonstration day.
  - **Frontend SPA:** **Cloudflare Pages (Free Plan)** — global CDN with unlimited static bandwidth/requests connected via `VITE_API_BASE_URL=https://<username>-<space-name>.hf.space/api`.
- **Ephemeral SQLite on Free Container Hosting:** Free container instances use ephemeral storage across container restarts or 48-hour idle sleep cycles. Whenever the container boots or **Reset Demo** (`POST /api/data/reset-demo`) is clicked, `startup_event()` automatically seeds the verified 10-job, 10-machine industrial dataset (`backend/data/initial_jobs.json`, `backend/data/initial_machines.json`).
- **CP-SAT Time Budget:** Online API calls cap CP-SAT at `2.0s–3.0s` (`num_search_workers = 4`), returning proven `OPTIMAL` schedules on small instances and high-quality time-bounded `FEASIBLE` schedules on contended 10–25 job instances.

---

## 5. Key Documentation

- **Release & Audit Reports:** [`docs/STAGE11_RELEASE_REPORT.md`](docs/STAGE11_RELEASE_REPORT.md) | [`docs/STAGE10_RESEARCH_AUDIT.md`](docs/STAGE10_RESEARCH_AUDIT.md) | [`docs/STAGE10_EXPERIMENTAL_REPORT.md`](docs/STAGE10_EXPERIMENTAL_REPORT.md)
- **Cloud Deployment Guide:** [`docs/DEPLOYMENT_GUIDE.md`](docs/DEPLOYMENT_GUIDE.md)
- **Faculty Demonstration Script:** [`docs/FACULTY_DEMO_SCRIPT.md`](docs/FACULTY_DEMO_SCRIPT.md)
- **GitHub Repository:** `https://github.com/abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER.git`
