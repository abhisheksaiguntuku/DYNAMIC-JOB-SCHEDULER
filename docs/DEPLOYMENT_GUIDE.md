# STAGE 11 FREE-TIER DEPLOYMENT GUIDE
## Deploying the Dynamic Job-Shop Scheduling System (\$0 No-Subscription Architecture)

**Repository:** `https://github.com/abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER.git`  
**Release Branch:** `stage11-release-deployment`  
**Research Baseline Branch:** `stage10-research-audit` (`ff2036b`)

---

## 1. Official Free-Hosting Audit & Provider Selection (2025–2026)

### Measured Runtime & Memory Requirements
From our bounded runtime probes (`task-629` and `task-687`):
- **Startup Memory (FastAPI + SQLAlchemy + scikit-learn + OR-Tools CP-SAT):** `~185–200 MB` RSS (`startup_event()` completes in `0.500 s`).
- **Steady / Peak Memory After Genuine PyTorch EPN Inference (`torch==2.11.0+cpu` + `368 KB` `epn_model.pth`):** **`372.93 MB` steady RSS** / **`401.62 MB` peak RSS** (leaves **`~110 MB` headroom** inside a `512 MB` container).
- **Total Cold-Boot Initialization Time:** `9.793 s` locally (`~30–50 s` on `0.1` shared vCPU).
- **Python Version Requirement:** `Python >= 3.11` (`python:3.12-slim` in `Dockerfile` or `PYTHON_VERSION=3.12.8`).

### Comparison of Backend Hosting Candidates

| Provider | Genuinely Free Without Paid Subscription? | Card / Billing Required? | CPU / RAM / Disk Quotas | Inactivity Sleep / Cold-Start | Verdict for FastAPI + OR-Tools + PyTorch EPN (`401.62 MB` Peak RSS) | Official Source |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Render Free Web Service** *(Primary No-Card Option A)* | **Yes (\$0/mo)** (`750` free instance hours/month) | **No** (for Free Web Services) | `0.1 CPU`, `512 MB RAM`, ephemeral disk | Spins down after **15 minutes** idle (`30–60s` cold start; **0s** delay once warmed 2–3 min before demo) | **Viable & Verified Compatible** (`401.62 MB` peak RSS fits within `512 MB` using CPU-only PyTorch wheel) | [Render Free Tier Docs](https://render.com/docs/free) |
| **2. Koyeb Free Tier (`Nano`)** *(Primary No-Card Option B)* | **Yes (\$0/mo)** (`1` free web service per org) | **No** (unless flagged by automated anti-abuse check) | `0.1 vCPU`, `512 MB RAM`, `2 GB SSD` ephemeral disk | Scales to zero after **1 hour** idle (`10–30s` wake-up; stays awake 4x longer than Render) | **Viable & Verified Compatible** (Deploys directly from root `Dockerfile`; `1.15 GB` image fits `2 GB` SSD) | [Koyeb Pricing & Docs](https://www.koyeb.com/docs/run-and-scale/pricing) |
| **3. Hugging Face Spaces (`Docker` / `Gradio`)** | **No — Disqualified** (Docker & standard CPU Gradio Spaces are now gated behind paid **PRO** subscriptions on non-grandfathered accounts; only Static & limited ZeroGPU Spaces are free) | Paid PRO subscription required for Docker | `2 vCPU`, `16 GB RAM` (when unlocked) | 48h sleep | **Disqualified** under strict \$0 / no-subscription constraint | [HF Spaces Overview](https://huggingface.co/docs/hub/spaces-overview) |
| **4. Google Cloud Run** | Always Free monthly usage quota (`180k` vCPU-s, `360k` GiB-s, `2M` req/mo) | **Yes** (Requires active Cloud Billing Account + payment card; bills overages) | Configurable up to `4 vCPU`, `16 GiB` RAM | Scales to zero after `~15m` idle (`10–20s` cold start) | **Not Selected** without explicit billing-account approval due to card requirement & overage risk | [Cloud Run Pricing](https://cloud.google.com/run/pricing), [GCP Free Tier](https://cloud.google.com/free/docs/free-cloud-features) |
| **5. Railway** | **No permanent free tier** (One-time \$5 / 30-day trial credit only; \$5/mo Hobby plan thereafter) | **Yes** after trial | `0.5–1 GB` RAM on trial | Terminates when \$5 credit depletes | **Disqualified** (Temporary trial only) | [Railway Pricing](https://railway.com/pricing) |
| **6. Fly.io** | **Discontinued** permanent free tier (7-day / 2-hour trial only) | **Yes** | Paid usage after trial | N/A | **Disqualified** (No free tier) | [Fly.io Pricing](https://fly.io/docs/about/pricing/) |
| **7. PythonAnywhere** | Free Beginner account | No | `512 MiB` disk, `100` CPU-s/day | Manual monthly renewal | **Disqualified** (`512 MiB` disk cannot hold PyTorch + OR-Tools wheels) | [PythonAnywhere Plans](https://www.pythonanywhere.com/pricing/) |

---

## 2. Step 1: Deploy the Backend First (Choose Render Free OR Koyeb Free)

Both **Render Free** and **Koyeb Free** work directly with your pushed GitHub branch (`stage11-release-deployment`) without a paid subscription.

### Option A: Render Free Web Service (Lowest Signup Friction, No Card Required)
1. Sign in to **[https://dashboard.render.com](https://dashboard.render.com)** and click **New + &rarr; Web Service**.
2. Connect your GitHub account and select **`abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER`**.
3. Configure the exact settings below:
   - **Name:** `dynamic-job-shop-scheduler-api`
   - **Branch:** `stage11-release-deployment`
   - **Root Directory:** `backend`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free` (`$0/month`, `512 MB` RAM, `0.1` CPU)
4. Under **Advanced / Environment Variables**, set:
   - **Health Check Path:** `/api/health`
   - `PYTHON_VERSION` = `3.12.8`
   - `PYTHONPATH` = `.`
   - `CORS_ORIGINS` = `*` *(will be locked to your Cloudflare Pages URL after frontend deployment)*
5. Click **Create Web Service** and wait ~3–5 minutes for the build and startup to finish.
6. Copy your real public backend URL (`https://<your-service>.onrender.com`).

### Option B: Koyeb Free Tier (1-Hour Stay-Awake Window, Docker-Native)
1. Sign in to **[https://app.koyeb.com](https://app.koyeb.com)** and click **Create Web Service &rarr; GitHub**.
2. Select repository **`abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER`** and branch **`stage11-release-deployment`**.
3. Configure the build and instance settings:
   - **Builder:** `Dockerfile` (uses root `Dockerfile` automatically)
   - **Instance Type:** `Free` (`Nano`: `0.1 vCPU`, `512 MB RAM`, `2 GB SSD`, `$0/month`)
   - **Region:** `Washington, D.C.` or `Frankfurt`
   - **Port:** `7860` (HTTP, path `/`)
   - **Health Check:** HTTP on port `7860`, path `/api/health` (Grace period: `60s`)
   - **Environment Variables:** `PORT=7860`, `CORS_ORIGINS=*`
4. Click **Deploy** and copy your real public backend URL (`https://<your-app>-<your-org>.koyeb.app`).

---

## 3. Step 2: Verify the Live Backend Before Deploying Frontend

Once your backend service reports **Live / Healthy**, test the real public URL:
1. **Health Check:**
   - Open `https://<your-backend-url>/api/health`
   - Must return: `{"status":"HEALTHY","system":"Dynamic Job-Shop Scheduler"}`
2. **Genuine EPN Inference Check:**
   - Run: `curl -X POST "https://<your-backend-url>/api/schedules/recalculate?algorithm=EPN"`
   - Must return HTTP 200 JSON with `"algorithm":"PYTORCH EPN (Liu et al.)"` and `"solver_status":"NEURAL_PREDICTED_FEASIBLE"`.

---

## 4. Step 3: Deploy the Frontend on Cloudflare Pages (After Backend Verification)

1. Sign in to **[https://dash.cloudflare.com](https://dash.cloudflare.com)** &rarr; **Workers & Pages &rarr; Create &rarr; Pages &rarr; Connect to Git**.
2. Select **`abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER`**.
3. Configure build settings:
   - **Production branch:** `stage11-release-deployment`
   - **Framework preset:** `Vite`
   - **Root directory (path):** `frontend`
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
4. Add Environment Variables:
   - `VITE_API_BASE_URL` = `https://<your-actual-backend-url>/api`
   - `NODE_VERSION` = `22`
5. Click **Save and Deploy**, then update `CORS_ORIGINS` on your backend service to `https://<your-cloudflare-project>.pages.dev,http://localhost:5173`.

---

## 5. Free-Tier Operational Limitations & Faculty Demo Protocol

1. **Inactivity Spin-Down & Warm-Up Before Faculty Demo:**
   - Render Free spins down after **15 minutes** of zero traffic (`30–60s` cold start); Koyeb Free scales to zero after **1 hour** of zero traffic (`10–30s` cold start).
   - **Mandatory Pre-Demo Warm-Up:** Open `https://<your-actual-backend-url>/api/health` in a browser tab **3 minutes before** your faculty presentation starts. Once `{"status":"HEALTHY"}` appears, the container is warm in RAM and will respond with **0 ms cold-start delay** throughout your live demonstration.
2. **Ephemeral SQLite Storage Across Container Restarts:**
   - Free container filesystems are ephemeral across spin-downs and redeploys.
   - Whenever the container boots—or whenever you click **Reset Demo** (`POST /api/data/reset-demo`)—`startup_event()` automatically creates `production_scheduler.db` and seeds the verified 10-job (`JOB_001`–`JOB_010`), 10-machine (`M1`–`M10`) baseline workload.
