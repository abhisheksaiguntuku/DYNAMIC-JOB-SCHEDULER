# STAGE 11 RELEASE REPORT
## Release Readiness Audit, Free-Tier Cloud Deployment Architecture & Stage 12 Research Handoff

**Project:** Dynamic Job-Shop Scheduling System  
**Repository:** `https://github.com/abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER.git`  
**Research Baseline Branch:** `stage10-research-audit` (`ff2036b`)  
**Release Branch:** `stage11-release-deployment`  
**Date:** 2026-10-28

---

## 1. Phase A: Repository & Preservation Audit Summary

- **Baseline Commit Verification:** Confirmed Stage 9 commit `7d0e3be` on `master` and Stage 10 commit `ff2036b` on `stage10-research-audit`.
- **Branch Isolation:** Created `stage11-release-deployment` from `stage10-research-audit` (`ff2036b`) so all deployment and release-hygiene changes are isolated from the Stage 10 research baseline.
- **Database & Secret Hygiene:**
  - Untracked `backend/production_scheduler.db` (`git rm --cached backend/production_scheduler.db`) on `stage11-release-deployment` while keeping the file on disk for local development.
  - Updated [`.gitignore`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/.gitignore) to exclude `*.db`, `*.sqlite`, `*.sqlite3`, `*.db-journal`, `*.db-wal`, `*.db-shm`, `.env`, and `.env.*` while explicitly permitting `!.env.example`, `!/backend/.env.example`, and `!/frontend/.env.example`.
  - Audited all tracked files to confirm zero API keys, passwords, or private tokens exist in the repository.
- **Protected Artifact SHA-256 Hashes (Verified Unchanged):**
  - `backend/models/checkpoints/epn_model.pth`: `55F9E9227E1F527C86678AEF0565B16B92D450B2FC2D68ABADB0D3DF10970FA6`
  - `stage9_raw_results.csv`: `530BC6FE111B9ECE413CDB1FDDFC2DCF4F3CE182DF9EF706C2F86B145CC234F0`
  - `stage9_raw_results.json`: `385197957B111C62C97EEC4D398457DB6953459E97F48E125151B6B99AF6B421`
  - `stage9_summary_table.csv`: `CACEFB149B5FDC42865334873B9526F5685C7A1E10B26D21C44FAFF09E4403F2`
  - `stage9_summary_table.json`: `F696C7718EC79F255EBFDE4E5007AE3CD181C2EEC5296B5D2C007E52D11C1EBC`
  - `stage9_manifest.json`: `8EA804B96FF02899D432FBB46B6DC60C1F96F330EC5AAFA2B7A09DB0810B24CC`

---

## 2. Phase B: Application Release Audit & Test Verification

### 2.1 Backend Regression & Audit Suite
- **Command:** `cd backend; python -m pytest -v --tb=short`
- **Result:** **`87 passed, 518 warnings in 73.52s` (Exit Code `0`)**
- **Coverage Verified:**
  - Completed-operation preservation, running-operation locks, operation precedence, machine capacity non-overlap, simultaneous arrivals, dynamic arrivals, release/due dates (`test_dynamic_scheduling.py`, `test_stage41_integration.py`).
  - Flexible routing across `M1–M10`, repeated machine visits in a single job, invalid input rejection, and safe demo reset (`test_stage6_production_routing.py`).
  - SQLite simulation state persistence across restarts, machine downtime/recovery state machine, optimistic concurrency `state_version` (`HTTP 409` stale-schedule rejection), and `RLock` thread safety (`test_stage8_persistence.py`, `test_stage8_reliability.py`).
  - Stage 9 280-trial benchmark integrity (`test_stage9_experimental_benchmark.py`) and Stage 10 adversarial validator audit, Tier 5 repeated-routing, and EPN controlled ablations (`test_stage10_audit_and_ablation.py`).
- **Non-Blocking Warnings Observed:** Deprecation warnings from `datetime.utcnow()` and Pydantic V2 `.dict()` calls in `state_service.py` / `engine.py` and FastAPI `@app.on_event("startup")`. Left untouched to avoid unnecessary churn in core persistence logic.

### 2.2 Frontend Production Build
- **Command:** `cd frontend; npm run build`
- **Result:** **`1962 modules transformed, built in 3.57s` (Exit Code `0`)**
- **Output Bundle:** `dist/index.html` (`0.45 kB`), `dist/assets/index-DGNrK5qb.css` (`1.78 kB`), `dist/assets/index-FkfjXMK4.js` (`317.06 kB` / `98.47 kB` gzip).

### 2.3 Tested Dependency Versions ([`backend/requirements.txt`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/requirements.txt))
- Python runtime tested locally: `3.14.0` (compatible with Python `3.11+` / `3.12+` on Linux cloud hosts)
- `fastapi==0.135.3`, `uvicorn==0.44.0`, `sqlalchemy==2.0.49`, `pydantic==2.13.0`, `ortools==9.15.6755`, `torch==2.11.0` (with `--extra-index-url https://download.pytorch.org/whl/cpu`), `scikit-learn==1.8.0`, `numpy==2.4.4`, `scipy==1.17.1`, `pandas==3.0.3`, `pytest==9.1.1`, `httpx==0.28.1`.

---

## 3. Phase C & D: Free Deployment Design & Implementation

### 3.1 Selected Free Hosting Architecture
1. **Frontend — Cloudflare Pages (Free Plan):**
   - **Root Directory:** `frontend` | **Build Command:** `npm run build` | **Output Directory:** `dist`
   - **Environment Variable:** `VITE_API_BASE_URL=https://<your-render-service>.onrender.com/api`
   - **Plan Quotas:** Unlimited static bandwidth and requests, 500 builds/month, 1 concurrent build, 20-minute build timeout, global HTTPS CDN.
2. **Backend — Render (Free Web Service):**
   - **Root Directory:** `backend` | **Build Command:** `pip install -r requirements.txt` | **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health Check Endpoint:** `/api/health`
   - **Environment Variables:** `PYTHON_VERSION=3.12.8`, `PYTHONPATH=.`, `CORS_ORIGINS=*` (or the Cloudflare Pages origin).
   - **Plan Quotas & Limitations:** `512 MB` RAM, `0.1` shared CPU, `750` free instance hours/month, **ephemeral disk**, and **automatic spin-down after 15 minutes of inactivity** (`30–60s` cold start on next request).

### 3.2 Release-Specific Code Changes Made on `stage11-release-deployment`
1. **[`frontend/src/App.tsx`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/frontend/src/App.tsx#L10):** Replaced hardcoded `const API_BASE = 'http://127.0.0.1:8001/api';` with:
   ```ts
   const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001/api').replace(/\/+$/, '');
   ```
2. **[`backend/app/main.py`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/app/main.py#L20-L28):** Added `CORS_ORIGINS` environment variable support (defaulting to `["*"]` when unset).
3. **[`backend/requirements.txt`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/requirements.txt), [`backend/.env.example`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/backend/.env.example), [`frontend/.env.example`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/frontend/.env.example), and [`README.md`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/README.md):** Created reproducible dependency and environment templates and aligned the documented local `uvicorn` port to `8001`.

---

## 4. Phase E: Live Deployment & Verification Status

- **Local Pre-Deployment Verification:** Completed and passed (`87/87` backend tests passed, production `frontend/dist` build verified).
- **Cloud Account Authentication Boundary:** Because deploying to Render and Cloudflare Pages requires interactive OAuth sign-in to your personal GitHub, Render, and Cloudflare dashboards in a browser, no fake deployment URLs have been fabricated. Exact step-by-step deployment and post-deploy smoke-testing instructions are provided in [`docs/DEPLOYMENT_GUIDE.md`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/docs/DEPLOYMENT_GUIDE.md).

---

## 5. Phase G: Stage 12 & Manuscript Research-Readiness Checklist

Before drafting the final research manuscript in Stage 12, the following scientific, methodological, and experimental boundaries must be respected:

### 5.1 Resolved & Verified Research Assets
- [x] **5-Tier Reproducible Benchmark Suite (`350` main trials + `300` ablation trials = `650` verified schedules):**
  - Tiers 1–4 (`backend/experiments/stage9_benchmark/` and `backend/experiments/stage10_audit/`)
  - Tier 5 Re-Entrant / Repeated-Machine Routing (`backend/experiments/stage10_repeated_routing/`)
  - EPN Trace & 4-Variant Controlled Ablation Study (`backend/experiments/stage10_epn_ablation/`)
- [x] **Exact Small-Sample & Non-Parametric Statistics:** Student-$t$ $95\%$ CIs ($t_{0.975, 9} = 2.2622$), medians, IQRs, paired within-seed differences, paired $t$-tests, Wilcoxon signed-rank tests, Holm-Bonferroni corrections, and paired Cohen's $d_z$.
- [x] **Dual Zero-Trust Schedule Verification:** Every trial verified by both `ScheduleValidator` and zero-shared-code `IndependentScheduleAuditor`.

### 5.2 Open Methodological Questions & Guardrails for Stage 12 (Manuscript Stage)
1. **Strict Separation of Neural Contribution vs. Decoding Mechanics (Crucial):**
   - The manuscript **must not** claim that `EPN_BASELINE` outperforms classic heuristics or CP-SAT.
   - When presenting `EPN_ABLATION_B_OP_READY_DECODING`, the manuscript must explicitly distinguish between:
     1. **Decoding Architecture Effect:** Switching from job-sequential outer-loop serialization over a scalar machine watermark to chronological operation-level ready-queue dispatching (`earliest_start` primary key), and
     2. **Intrinsic Neural Tie-Breaking Contribution:** Using EPN's predicted slot (`pred_slot` secondary key) when multiple ready operations contend for a machine at the same `earliest_start`.
   - **Recommended Stage 12 Control Experiment:** To isolate the intrinsic value of EPN's neural slot predictions (`pred_slot`) purely from chronological `earliest_start` ordering, Stage 12 can compare `EPN_ABLATION_B_OP_READY_DECODING` (`(earliest_start, pred_slot, -priority, arrival_time)`) against a **non-delay chronological SPT/FCFS dispatcher** (`(earliest_start, op.duration, -priority, arrival_time)` and `(earliest_start, arrival_time, -priority)`) where `earliest_start` is also the primary key!
2. **Sample Size & Statistical Power ($n = 10$ vs. $n \ge 30$):**
   - While $n = 10$ seeds per tier provides $>99\%$ statistical power for large effects ($d_z > 2.0$, such as CP-SAT vs. SPT), resolving fine-grained tie-breaking differences ($|d_z| < 0.5$) would require $n \ge 30$ seeds per tier.
3. **CP-SAT Determinism & Time-Bounded Optimality:**
   - Describe CP-SAT on Tiers 2–5 as a **time-bounded constraint-programming optimizer (`2.0s–2.5s`, `num_search_workers = 4`)** that proves global optimality on $30.0\%$ ($15/50$) of instances and returns high-quality `FEASIBLE` incumbents on $70.0\%$.
4. **Literature Positioning:**
   - Position the work honestly as an **integrated dynamic job-shop scheduling testbed and empirical audit** comparing classic dispatching rules, time-bounded CP-SAT constraint programming, and pointer-network decoding strategies under dynamic arrivals, machine breakdowns, and re-entrant routing.

