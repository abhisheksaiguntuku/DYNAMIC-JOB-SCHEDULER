# STAGE 5 BASELINE VERIFICATION REPORT

**Project:** Dynamic Job-Shop Scheduling System  
**Execution Date:** 2026-10-18  
**Operating System:** Windows (AMD64)  
**Root Directory:** `C:\Users\SUNITA\.gemini\antigravity\scratch\dynamic_job_shop_scheduler`  

---

## 1. Environment & Dependency Versions

| Component | Version | Verification Command / Source |
|---|---|---|
| **Python** | 3.14.0 (tags/v3.14.0:ebf955d, Oct 7 2025) | `python -c "import sys; print(sys.version)"` |
| **OR-Tools** | 9.15.6755 | `python -c "import ortools; print(ortools.__version__)"` |
| **PyTorch** | 2.11.0+cpu | `python -c "import torch; print(torch.__version__)"` |
| **FastAPI** | 0.135.3 | `python -c "import fastapi; print(fastapi.__version__)"` |
| **Pydantic** | 2.13.0 | `python -c "import pydantic; print(pydantic.__version__)"` |
| **Node.js** | v22.19.0 | `node -v` |
| **npm** | 11.19.1 | `npm -v` |
| **VCS / Git** | No Git repository initialized (`.git` absent) | `git status` -> fatal: not a git repository |

---

## 2. Asset Integrity Check

- **SQLite Database:** `backend/production_scheduler.db` (Present, 65,536 bytes)
- **Model Checkpoint:** `backend/models/checkpoints/epn_model.pth` (Present, 376,790 bytes)
- **Experiment Data:** `experiments/raw_results/`, `experiments/summaries/` (Present)
- **Frontend Source:** `frontend/src/`, `frontend/package.json` (Present)

---

## 3. Full Backend Pytest Suite Run

**Command:**
```powershell
$env:PYTHONPATH="backend"
python -m pytest backend/tests/ -v --tb=short
```

**Results:**
- **Total Tests Collected:** 50
- **Passed:** **48**
- **Skipped:** **2**
- **Failed:** **0**
- **Execution Time:** 12.73 seconds
- **Warnings:** 214 (SQLAlchemy `datetime.utcnow()` deprecation and Pydantic `.dict()` v2 deprecation warnings)

### Skipped Tests Audit:
1. `backend/tests/test_dynamic_scheduling.py::test_machine_downtime_and_recovery`
   - *Reason:* `"Machine breakdown feature not implemented in current codebase"`
   - *Classification:* **NOT IMPLEMENTED**
2. `backend/tests/test_dynamic_scheduling.py::test_stale_schedule_rejection`
   - *Reason:* `"Versioned schedule validation not present in backend"`
   - *Classification:* **NOT IMPLEMENTED**

Neither skipped test is counted as passed.

---

## 4. Benchmark Verification Run

**Command:**
```powershell
$env:PYTHONPATH="backend"
python -m pytest backend/tests/test_flow_shop_benchmarks.py -v
```

**Results:**
- `test_two_machine_benchmark_exact`: **PASSED** (0.19s)
- `test_five_machine_benchmark_exact`: **PASSED**
- `test_cds_discrepancy_reconciliation`: **PASSED**
- **Summary:** 3 passed in 0.19s
