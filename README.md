# AI-Assisted Dynamic Job-Shop Scheduling and Production Optimization System
## Complete System Guide & Reproduction Instructions

### 1. Overview
This production scheduling system is designed for high-mix, dynamic manufacturing environments with a **10-machine layout**. It implements:
- **Heuristics:** FCFS, SPT, EDD, Critical Ratio (CR), and Waiting Time Aging/Slack.
- **Exact Optimization:** Google OR-Tools CP-SAT constraint programming.
- **Machine Learning:** Supervised Random Forest strategy selector.
- **Dynamic Rescheduling:** Dynamic recalculation triggered whenever a new job enters or machine operations complete without resetting in-flight manufacturing states.
- **Full-Stack Application:** FastAPI backend with SQLite persistence and a modern React/TypeScript/Vite dashboard.

---

### 2. Verified Dataset
The initial factory state is seeded from the verified mechanical engineering dataset:
- **Core Jobs:** Truck Frame, NREC Axle, Coco Bogie, Coupler, Yoke, Knuckle, Striker, Side Frame, Bogie Bolster, PRS Xing.
- **Core 5-Stage Routing:** Pattern Making (M1) &rarr; Mould Making (M2) &rarr; Casting (M3) &rarr; Heat Treatment (M4) &rarr; Machining (M5).
- **Flexible Parallel Routing:** M6 through M10 provide auxiliary and parallel capacity for rapid unblocking.

---

### 3. How to Run the System

#### Step 1: Start the FastAPI Backend
Open a terminal in the project directory:
```powershell
cd C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler\backend
$env:PYTHONPATH="."
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
The backend API documentation will be available at: `http://127.0.0.1:8000/docs`

#### Step 2: Start the Frontend Application
Open a second terminal:
```powershell
cd C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler\frontend
npm run dev
```
Open your browser at: `http://localhost:5173`

#### Step 3: Run Automated Test Suite
To verify constraint enforcement and non-overlapping machine schedules:
```powershell
cd C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler
$env:PYTHONPATH="backend"
python -m pytest backend\tests\test_scheduling.py -v
```
