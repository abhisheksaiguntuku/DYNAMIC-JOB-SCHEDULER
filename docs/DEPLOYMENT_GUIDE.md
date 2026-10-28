# STAGE 11 FREE-TIER DEPLOYMENT GUIDE
## Deploying the Dynamic Job-Shop Scheduling System (\$0, No Docker, No Render Limit)

**Repository:** `https://github.com/abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER.git`  
**Release Branch:** `stage11-release-deployment`  
**Research Baseline Branch:** `stage10-research-audit` (`ff2036b`)

---

## 1. Why Docker & Render Were Replaced

1. **Docker Is Not Required:** FastAPI + OR-Tools + CPU PyTorch runs natively on standard Python 3.12 runtimes using `pip install -r requirements.txt` and `uvicorn`. Removing `Dockerfile` avoids Hugging Face Spaces' paid Docker paywall and enables direct native Python builds on **Leapcell** and **Koyeb**.
2. **Render Free Disqualified for Your Account:** Render limits workspaces to 750 free hours/month (already consumed by your previous project) and spins down after 15 minutes with a 50–60s cold start.

### Comparison of Non-Render, No-Docker Free Backend Hosts

| Provider | Genuinely Free (\$0, No Card)? | Docker Required? | Project / Resource Limits | Sleep / Wake-Up Behavior | Verdict for FastAPI + OR-Tools + PyTorch EPN | Official Docs |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Leapcell (Free Hobby Tier)** *(Recommended Primary)* | **Yes (\$0/mo, No Card)** | **No** (Native Python runtime) | Up to **20 free projects**, up to **3 vCPU / 4 GB RAM** per project | Serverless scale-to-zero with **fast `<1s` (`~250ms`) wake-up** (no 60s Render hang) | **Best Fit** — `4 GB` RAM easily holds `401.62 MB` peak RSS; `db.py` automatically uses writable `/tmp/production_scheduler.db` | [Leapcell FastAPI Docs](https://docs.leapcell.io/) |
| **2. Koyeb (Free Tier)** *(Recommended Alternative)* | **Yes (\$0/mo, No Card)** | **No** (Native Python Buildpack via `Procfile` + `.python-version`) | `1` free Nano service (`0.1 vCPU`, `512 MB RAM`, `2 GB SSD`) | Sleeps only after **1 full hour (60 min)** of inactivity (4x longer than Render) | **Strong Alternative** — `401.62 MB` peak RSS fits within `512 MB` RAM | [Koyeb Python Buildpack Docs](https://www.koyeb.com/docs/deploy/python) |

---

## 2. Step 1: Deploy the Backend First (No Docker Required)

### Option A: Leapcell Free Tier (Recommended — Up to 4 GB RAM, 20 Free Projects, Fast Wake-Up)
1. Go to **[https://leapcell.io](https://leapcell.io)** and sign in with your **GitHub** account (no credit card required).
2. Click **Create Service** and select your repository **`abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER`**.
3. Configure the service settings:
   - **Branch:** `stage11-release-deployment`
   - **Root Directory:** `backend` (or leave as `.` — both work)
   - **Runtime:** `Python (3.12)`
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command:**
     ```bash
     uvicorn app.main:app --host 0.0.0.0 --port 8080
     ```
   - **Serving Port:** `8080`
   - **Environment Variables:**
     - `PYTHONPATH` = `.` (if Root Directory is `backend`) or `backend` (if Root Directory is `.`)
     - `CORS_ORIGINS` = `*`
4. Click **Deploy**. Once deployed, copy your public Leapcell HTTPS URL.

### Option B: Koyeb Free Tier (Native Python Buildpack — 1-Hour Stay-Awake, No Docker)
1. Go to **[https://app.koyeb.com](https://app.koyeb.com)** and sign in with **GitHub**.
2. Click **Create Web Service &rarr; GitHub** and select **`abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER`**.
3. Configure:
   - **Branch:** `stage11-release-deployment`
   - **Builder:** `Buildpack` (automatically detects root `Procfile`, `.python-version`, and `requirements.txt` — **no Docker used**)
   - **Instance Type:** `Free` (`0.1 vCPU`, `512 MB RAM`)
   - **Port:** `8080`
   - **Health Check Path:** `/api/health`
   - **Environment Variables:** `PORT=8080`, `PYTHONPATH=backend`, `CORS_ORIGINS=*`
4. Click **Deploy** and copy your public Koyeb HTTPS URL (`https://<your-app>-<your-org>.koyeb.app`).

---

## 3. Step 2: Verify the Live Backend Before Deploying Frontend

Test your deployed backend URL:
1. **Health Endpoint:** `https://<your-backend-url>/api/health` &rarr; must return `{"status":"HEALTHY","system":"Dynamic Job-Shop Scheduler"}`
2. **Genuine EPN Inference:** `POST https://<your-backend-url>/api/schedules/recalculate?algorithm=EPN` &rarr; must return `"solver_status":"NEURAL_PREDICTED_FEASIBLE"`.

---

## 4. Step 3: Deploy the Frontend on Cloudflare Pages (After Backend Is Verified)

1. In **[https://dash.cloudflare.com](https://dash.cloudflare.com)** &rarr; **Workers & Pages &rarr; Create &rarr; Pages &rarr; Connect to Git**, select **`abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER`**.
2. Configure:
   - **Production branch:** `stage11-release-deployment`
   - **Framework preset:** `Vite`
   - **Root directory:** `frontend`
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
   - **Environment Variables:** `VITE_API_BASE_URL=https://<your-actual-backend-url>/api`, `NODE_VERSION=22`
3. Click **Save and Deploy**, then set `CORS_ORIGINS=https://<your-cloudflare-project>.pages.dev,http://localhost:5173` in your backend environment variables.
