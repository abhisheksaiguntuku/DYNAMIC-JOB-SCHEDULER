# STAGE 11 FREE-TIER DEPLOYMENT GUIDE
## Deploying the Dynamic Job-Shop Scheduling System (Cloudflare Pages + Render Free Tier)

**Repository:** `https://github.com/abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER.git`  
**Release Branch:** `stage11-release-deployment`  
**Research Baseline Branch:** `stage10-research-audit` (`ff2036b`)

---

## 1. Architecture & Provider Selection Summary

To host the full-stack research prototype at **\$0/month** without credit-card overage risk while supporting Python (`FastAPI`, `ortools`, `torch` CPU, `scikit-learn`) and the React/TypeScript (`Vite`) dashboard:

| Component | Recommended Free Host | Root Directory | Runtime / Plan Quotas |
| :--- | :--- | :--- | :--- |
| **Backend API** | **Render** (Free Web Service) | `backend` | Python 3 (`512 MB` RAM, `0.1` shared CPU, `750` free instance hours/month, ephemeral disk, spins down after `15m` inactivity with `30–60s` cold start) |
| **Frontend UI** | **Cloudflare Pages** (Free Static Site) | `frontend` | Node.js `20+` (`500` builds/month, **unlimited** static bandwidth & static requests, global HTTPS CDN) |

---

## 2. Step-by-Step GitHub Push Instructions

From the project root (`C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler`):

```powershell
# 1. Verify remote origin points to your GitHub repository
git remote -v
# If not yet added:
git remote add origin https://github.com/abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER.git

# 2. Verify backend/production_scheduler.db is untracked on stage11-release-deployment
git status -s
git ls-files backend/production_scheduler.db
# (Must return empty output)

# 3. Push the release branch to GitHub
git push -u origin stage11-release-deployment
```

> [!IMPORTANT]
> **Rule 3 Compliance (`production_scheduler.db`):** On earlier branches (`master` and `stage10-research-audit`), `backend/production_scheduler.db` was tracked in Git history. On `stage11-release-deployment`, `backend/production_scheduler.db` is untracked (`git rm --cached`) and excluded via `.gitignore`. Only promote `stage11-release-deployment` to `main` (`git push -u origin stage11-release-deployment:main`) after reviewing the release branch.

---

## 3. Deploying the Backend on Render (Free Web Service)

1. Sign in to [https://dashboard.render.com](https://dashboard.render.com) and click **New + &rarr; Web Service**.
2. Connect your GitHub account and select **`abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER`**.
3. Configure the service settings exactly as follows:
   - **Name:** `dynamic-job-shop-scheduler-api`
   - **Branch:** `stage11-release-deployment` (or `main` once promoted)
   - **Root Directory:** `backend`
   - **Runtime:** `Python 3`
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
     *(Note: `backend/requirements.txt` includes `--extra-index-url https://download.pytorch.org/whl/cpu` so Render installs the lightweight CPU-only PyTorch wheel instead of a 2.5 GB CUDA wheel, keeping memory well within the `512 MB` Free Tier limit).*
   - **Start Command:**
     ```bash
     uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type:** `Free` (\$0/month, 512 MB RAM, 0.1 CPU)
4. Expand **Advanced** and set:
   - **Health Check Path:** `/api/health`
   - **Environment Variables:**
     - `PYTHON_VERSION`: `3.12.8` (recommended stable Python 3.12 wheel support on Linux)
     - `PYTHONPATH`: `.`
     - `CORS_ORIGINS`: `*` (or your Cloudflare Pages domain `https://<your-project>.pages.dev` once created)
5. Click **Create Web Service**.
6. Wait for the build to finish and verify the public health check URL:
   - `https://<your-render-service>.onrender.com/api/health`
   - Expected JSON response: `{"status": "HEALTHY", "system": "Dynamic Job-Shop Scheduler"}`

### Runtime Assets Verified in `backend/`
- `backend/data/initial_jobs.json` & `backend/data/initial_machines.json`: Automatically loaded by `ProductionStateService.seed_if_empty()` on startup to create and seed `production_scheduler.db`.
- `backend/models/checkpoints/epn_model.pth` (`376,790` bytes / `368 KB`): Loaded automatically by `EPNJobShopScheduler` via `Path(__file__).resolve().parents[4] / "backend" / "models" / "checkpoints" / "epn_model.pth"`.

---

## 4. Deploying the Frontend on Cloudflare Pages (Free Static Host)

1. Sign in to the [Cloudflare Dashboard](https://dash.cloudflare.com) and navigate to **Workers & Pages &rarr; Create &rarr; Pages &rarr; Connect to Git**.
2. Select **`abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER`**.
3. Configure the build settings:
   - **Project Name:** `dynamic-job-shop-scheduler`
   - **Production Branch:** `stage11-release-deployment` (or `main` once promoted)
   - **Framework Preset:** `Vite`
   - **Root Directory (path):** `frontend`
   - **Build Command:**
     ```bash
     npm run build
     ```
   - **Build Output Directory:**
     ```text
     dist
     ```
4. Under **Environment Variables (Production & Preview)**, add:
   - **Variable Name:** `VITE_API_BASE_URL`
   - **Value:** `https://<your-render-service>.onrender.com/api`  
     *(Ensure there is no trailing slash, though `App.tsx` automatically strips trailing slashes).*
   - **Variable Name:** `NODE_VERSION`
   - **Value:** `22`
5. Click **Save and Deploy**.
6. Once deployed, copy your Cloudflare Pages URL (`https://<your-project>.pages.dev`) and optionally update `CORS_ORIGINS` in your Render service environment variables to `https://<your-project>.pages.dev,http://localhost:5173`.

---

## 5. Free-Tier Operational Behavior & Persistence Limitations

1. **Cold Starts on Render Free Tier (`15m` Inactivity Spin-Down):**
   - Render spins down free web services after 15 minutes without inbound traffic.
   - When opening the dashboard for a faculty demonstration after inactivity, the first API request will take **30–60 seconds** while Render boots the container, seeds SQLite (`seed_if_empty()`), and trains the lightweight Random Forest strategy recommender (`train_on_simulated_scenarios()`).
   - **Tip for Live Demos:** Open `https://<your-render-service>.onrender.com/api/health` in a browser tab **2 minutes before** starting your presentation so the container is warm.
2. **Ephemeral SQLite Filesystem:**
   - Render Free Web Services do **not** include persistent disk storage across container restarts or spin-downs.
   - During an active session, all SQLite tables (`jobs`, `machines`, `schedule_records`, `simulation_state`) operate normally on the container's local filesystem.
   - When the container spins down or restarts, `startup_event()` automatically re-creates `production_scheduler.db` and seeds the 10 verified baseline industrial jobs (`JOB_001`–`JOB_010`) and 10 machines (`M1`–`M10`).
   - Users can also manually restore the clean 10-job baseline at any time via the **Reset Demo** button in the top navigation bar (`POST /api/data/reset-demo`).

