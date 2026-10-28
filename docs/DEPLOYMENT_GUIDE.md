# STAGE 11 FREE-TIER DEPLOYMENT GUIDE
## Deploying the Dynamic Job-Shop Scheduling System (Hugging Face Spaces Docker + Cloudflare Pages)

**Repository:** `https://github.com/abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER.git`  
**Release Branch:** `stage11-release-deployment`  
**Research Baseline Branch:** `stage10-research-audit` (`ff2036b`)

---

## 1. Free Hosting Evaluation & Selected Architecture

Our runtime compatibility probe measured a single-worker footprint of **`372.93 MB` steady RSS** and **`401.62 MB` peak RSS** (loading `FastAPI`, `SQLAlchemy`, `scikit-learn`, `OR-Tools CP-SAT`, and CPU-only `PyTorch 2.11.0` with the `368 KB` `epn_model.pth` checkpoint), with a **`9.793 s` cold-boot initialization time** (`9.271 s` module imports + `0.500 s` SQLite seed & Random Forest strategy training + `22.02 ms` EPN checkpoint load).

Based on official provider documentation (2025–2026), we evaluated 7 free-hosting candidates:

| Provider | Free Eligibility & Cost | Card / Billing Required? | CPU / RAM / Disk Quotas | Inactivity Sleep / Cold-Start | Fits `401.62 MB` Peak RSS + PyTorch + OR-Tools? | Official Source |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Hugging Face Spaces (`cpu-basic`, Docker SDK)** *(Selected Backend)* | **$0/mo** permanent free tier for all accounts | **No** (Zero overage risk) | **2 vCPU**, **16 GB RAM**, **50 GB** ephemeral disk | Sleeps only after **48 hours** of inactivity (`~15–25s` initial container boot; **0s** delay once woken within 48h) | **Yes — Ideal** (`401.62 MB` is only `2.5%` of `16 GB` RAM; 2 vCPUs accelerate CP-SAT & EPN) | [HF Spaces Overview](https://huggingface.co/docs/hub/spaces-overview), [HF Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker), [HF Pricing](https://huggingface.co/pricing) |
| **2. Google Cloud Run** | Always Free monthly quota (`180,000` vCPU-s, `360,000` GiB-s, `2M` req/mo) | **Yes** (Active Cloud Billing Account & card required; pay-as-you-go overages) | Configurable up to `4 vCPU` / `16 GiB` RAM (ephemeral disk in RAM) | Scales to zero after **~15 min** idle (`10–20s` cold start per new instance) | **Technically Yes**, but requires credit card and carries billing overage risk if quotas are exceeded | [Cloud Run Pricing](https://cloud.google.com/run/pricing), [GCP Free Tier](https://cloud.google.com/free/docs/free-cloud-features) |
| **3. Render Free Web Service** *(Secondary Fallback)* | **$0/mo** (`750` free instance hours/month) | No (for standard free web services) | **0.1 CPU**, **512 MB RAM**, ephemeral disk | Spins down after **15 minutes** idle (**30–60s** cold start on `0.1` CPU) | **Marginal / Tight** (`401.62 MB` peak RSS leaves only `~110 MB` headroom before `512 MB` OOM; frequent 15m sleep disrupts demos) | [Render Free Docs](https://render.com/docs/free) |
| **4. Koyeb Free Tier** | **$0/mo** (1 free Nano web service) | No (subject to anti-abuse check) | **0.1 vCPU**, **512 MB RAM**, **2 GB** ephemeral SSD | Scales to zero after **1 hour** idle | **Marginal / Tight** (`512 MB` RAM limit and `0.1` vCPU throttle CP-SAT & PyTorch imports) | [Koyeb Pricing & Docs](https://www.koyeb.com/docs/run-and-scale/pricing) |
| **5. Fly.io** | **Discontinued** permanent free tier (7-day / 2-hour trial only) | **Yes** | Paid usage after trial | N/A | **No** (Not genuinely free) | [Fly.io Plan Pricing](https://fly.io/docs/about/pricing/) |
| **6. Railway** | **No permanent free tier** (One-time \$5 / 30-day trial credit only) | **Yes** after 30-day trial | `0.5 GB–1 GB` RAM on trial | Sleeps/expires when \$5 credit depletes | **No** (Expires after 30 days / \$5 credit) | [Railway Pricing](https://railway.com/pricing) |
| **7. PythonAnywhere** | Free Beginner account | No | `512 MiB` disk, `100` CPU-s/day, outbound allowlist only | Manual monthly renewal | **No** (`512 MiB` disk cannot hold PyTorch + OR-Tools + scikit-learn wheels) | [PythonAnywhere Plans](https://www.pythonanywhere.com/pricing/) |

### Selected Production Architecture
- **Backend API:** **Hugging Face Spaces (`cpu-basic`, Docker SDK)** (`https://<your-hf-username>-<your-space-name>.hf.space`) — $0/month, no credit card, **2 vCPUs**, **16 GB RAM**, **48-hour inactivity timeout**.
- **Frontend SPA:** **Cloudflare Pages (Free Plan)** (`https://<your-project>.pages.dev`) — $0/month, unlimited static bandwidth/requests, global HTTPS CDN.

---

## 2. Step-by-Step GitHub Push Instructions

From the project root (`C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler`):

```powershell
# 1. Verify remote origin points to your GitHub repository
git remote -v

# 2. Confirm backend/production_scheduler.db is excluded from the release commit
git ls-files backend/production_scheduler.db
# (Must return empty output)

# 3. Push the release branch to GitHub (will prompt via Git Credential Manager if needed)
git push -u origin stage11-release-deployment
```

---

## 3. Deploying the Backend on Hugging Face Spaces (Free `cpu-basic` Docker SDK)

The repository root now contains a production [`Dockerfile`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/Dockerfile), [`.dockerignore`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/.dockerignore), and Hugging Face Spaces YAML frontmatter in [`README.md`](file:///c:/Users/SUNITA/.gemini/antigravity/scratch/dynamic_job_shop_scheduler/README.md).

### Step 3.1: Create the Free Docker Space
1. Sign in to [https://huggingface.co](https://huggingface.co) (free account, no credit card required) and go to **[https://huggingface.co/new-space](https://huggingface.co/new-space)**.
2. Configure the Space:
   - **Space name:** `dynamic-job-shop-scheduler`
   - **Select the Space SDK:** `Docker` &rarr; select **Blank**
   - **Space Hardware:** `CPU basic · 2 vCPU · 16 GB · FREE`
   - **Visibility:** `Public`
3. Click **Create Space**.

### Step 3.2: Push the Release Branch to Your Hugging Face Space
In your local terminal (from `C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler`):

```powershell
# Add your Hugging Face Space as a secondary Git remote
git remote add space https://huggingface.co/spaces/<your-hf-username>/dynamic-job-shop-scheduler

# Push stage11-release-deployment to the Space's main branch
# (When prompted for password, use a Hugging Face User Access Token with Write permissions from https://huggingface.co/settings/tokens)
git push space stage11-release-deployment:main
```

### Step 3.3: Verify the Public Backend URL, Health & EPN Inference
1. Hugging Face Spaces will automatically build the root `Dockerfile` (`python:3.12-slim`) and start `uvicorn app.main:app --host 0.0.0.0 --port 7860`.
2. Once the Space badge turns **Running**, your direct public HTTPS URL is:
   ```text
   https://<your-hf-username>-dynamic-job-shop-scheduler.hf.space
   ```
3. Verify the endpoints in your browser or via `curl`:
   - **Health Endpoint:**
     ```bash
     curl https://<your-hf-username>-dynamic-job-shop-scheduler.hf.space/api/health
     # Expected: {"status":"HEALTHY","system":"Dynamic Job-Shop Scheduler"}
     ```
   - **Genuine EPN Neural Inference Endpoint:**
     ```bash
     curl -X POST "https://<your-hf-username>-dynamic-job-shop-scheduler.hf.space/api/schedules/recalculate?algorithm=EPN"
     # Expected: HTTP 200 JSON with "algorithm":"PYTORCH EPN (Liu et al.)" and "solver_status":"NEURAL_PREDICTED_FEASIBLE"
     ```

---

## 4. Deploying the Frontend on Cloudflare Pages (Free Static Host)

1. Sign in to the [Cloudflare Dashboard](https://dash.cloudflare.com) and navigate to **Workers & Pages &rarr; Create &rarr; Pages &rarr; Connect to Git**.
2. Select **`abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER`**.
3. Configure the build settings:
   - **Project Name:** `dynamic-job-shop-scheduler`
   - **Production Branch:** `stage11-release-deployment` (or `main` once promoted)
   - **Framework Preset:** `Vite`
   - **Root Directory (path):** `frontend`
   - **Build Command:** `npm run build`
   - **Build Output Directory:** `dist`
4. Under **Environment Variables (Production & Preview)**, add:
   - `VITE_API_BASE_URL` = `https://<your-hf-username>-dynamic-job-shop-scheduler.hf.space/api`
   - `NODE_VERSION` = `22`
5. Click **Save and Deploy**.
6. Once Cloudflare Pages assigns your frontend domain (`https://<your-project>.pages.dev`), optionally restrict CORS in your Hugging Face Space (**Settings &rarr; Variables and secrets &rarr; New variable**):
   - **Name:** `CORS_ORIGINS`
   - **Value:** `https://<your-project>.pages.dev,http://localhost:5173`

---

## 5. Faculty Demonstration Warm-Up & Storage Behavior

1. **48-Hour Stay-Awake Window (No 15-Minute Sleep During Demos):**
   - Unlike Render Free (which sleeps after 15 minutes of inactivity), Hugging Face Spaces (`cpu-basic`) stays awake for **48 hours** after the last request.
   - **Demo Preparation:** Open `https://<your-hf-username>-dynamic-job-shop-scheduler.hf.space/api/health` once **10–30 minutes before** (or the morning of) your faculty presentation. If the Space was sleeping after >48 hours of inactivity, it will wake up in ~15–25 seconds and remain continuously warm with **0 ms cold-start latency** for the next 48 hours.
2. **Ephemeral Container SQLite & Safe Demo Reset:**
   - Free Hugging Face Spaces use ephemeral container storage across container rebuilds or 48-hour sleep cycles (persistent disk storage is a paid add-on and is **not** needed for this prototype).
   - During your active 48-hour session, all SQLite tables (`jobs`, `machines`, `schedule_records`, `simulation_state`) persist normally on the container filesystem (`/home/user/app/backend/production_scheduler.db`).
   - Whenever the container restarts—or whenever you click **Reset Demo** (`POST /api/data/reset-demo`) in the UI—the backend automatically restores the verified 10-job (`JOB_001`–`JOB_010`), 10-machine (`M1`–`M10`) baseline workload from `backend/data/`.
