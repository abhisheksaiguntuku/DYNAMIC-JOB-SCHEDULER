import pytest
from app.schemas.models import Job, Operation, Machine, MachineStatus, JobStatus, OperationStatus
from app.scheduling.heuristics import DispatchHeuristicScheduler
from app.optimization.cpsat_solver import CPSATSchedulingOptimizer
from app.ml.inference.epn_scheduler import EPNJobShopScheduler
from app.scheduling.validator import ScheduleValidator

@pytest.fixture
def ten_machines():
    return [
        Machine(machine_id=f"M{i+1}", name=f"Machine {i+1}", capability=f"Process_{i+1}")
        for i in range(10)
    ]

def test_extreme_heterogeneous_industrial_jobs(ten_machines):
    """
    Simulates real-world unpredictable factory conditions:
    - Job 1 (Express Short Job): 1 machine (M1), duration 1.0 hr (60 min), URGENT due date in 1 day (1440 min)
    - Job 2 (Long Heavy Order): 5 machines (M1->M2->M3->M4->M5), total 30 hrs (1800 min), due date in 25 days (36000 min)
    - Job 3 (Relaxed Quick Task): 1 machine (M7), duration 1.0 hr (60 min), due date in 30 days (43200 min)
    - Job 4 (Complex Flexible Job): 4 machines (M6->M8->M9->M10), duration 12 hrs (720 min), due date in 3 days (4320 min)
    """
    jobs = [
        # Job 1: 1 Machine, 60 mins, Due at 1440 mins (Urgent single-stage)
        Job(
            job_id="IND_J1_EXPRESS",
            name="Emergency Hydraulic Fitting",
            product_type="Fast Turnaround",
            arrival_time=0.0,
            due_date=1440.0,
            priority=5,
            operations=[
                Operation(sequence=1, name="Precision Turning", machine_id="M1", duration=60.0)
            ]
        ),
        # Job 2: 5 Machines sequential, 1800 mins, Due at 36000 mins (Long heavy project)
        Job(
            job_id="IND_J2_HEAVY",
            name="Turbine Rotor Shaft",
            product_type="Heavy Component",
            arrival_time=0.0,
            due_date=36000.0,
            priority=3,
            operations=[
                Operation(sequence=1, name="Forging/Pattern", machine_id="M1", duration=360.0),
                Operation(sequence=2, name="Rough Machining", machine_id="M2", duration=480.0),
                Operation(sequence=3, name="Deep Heat Treatment", machine_id="M3", duration=400.0),
                Operation(sequence=4, name="Finish Grinding", machine_id="M4", duration=320.0),
                Operation(sequence=5, name="Inspection", machine_id="M5", duration=240.0)
            ]
        ),
        # Job 3: 1 Machine on an independent idle machine (M7), 60 mins, Due at 43200 mins (Relaxed)
        Job(
            job_id="IND_J3_RELAXED",
            name="Standard Flange",
            product_type="Stock Inventory",
            arrival_time=0.0,
            due_date=43200.0,
            priority=1,
            operations=[
                Operation(sequence=1, name="Drilling", machine_id="M7", duration=60.0)
            ]
        ),
        # Job 4: Parallel Routing on auxiliary machines (M6, M8, M9, M10), 720 mins, Due at 4320 mins
        Job(
            job_id="IND_J4_COMPLEX",
            name="Transmission Gearbox",
            product_type="Powertrain Subassembly",
            arrival_time=0.0,
            due_date=4320.0,
            priority=4,
            operations=[
                Operation(sequence=1, name="Core Casting Aux", machine_id="M6", duration=180.0),
                Operation(sequence=2, name="Milling Aux", machine_id="M8", duration=200.0),
                Operation(sequence=3, name="Hardening Aux", machine_id="M9", duration=220.0),
                Operation(sequence=4, name="CMM Metrology", machine_id="M10", duration=120.0)
            ]
        )
    ]

    # Test all 3 core engines on this diverse industrial scenario
    for algo in ["CPSAT", "EPN", "SPT"]:
        if algo == "CPSAT":
            res = CPSATSchedulingOptimizer.optimize(jobs, ten_machines, current_time=0.0, time_limit_seconds=2.0)
        elif algo == "EPN":
            res = EPNJobShopScheduler().schedule(jobs, ten_machines, current_time=0.0)
        else:
            res = DispatchHeuristicScheduler.schedule(jobs, ten_machines, current_time=0.0, rule=algo)

        # 1. Independent mathematical constraint verification
        is_valid, errors = ScheduleValidator.validate(res.tasks, ten_machines, current_time=0.0)
        assert is_valid, f"{algo} produced invalid schedule on heterogeneous dataset: {errors}"

        # 2. Verify that independent machine M7 was utilized concurrently without waiting for M1
        m7_tasks = [t for t in res.tasks if t.machine_id == "M7"]
        assert len(m7_tasks) == 1
        assert m7_tasks[0].job_id == "IND_J3_RELAXED"
        # M7 was idle at time 0, so Job 3 must start at time 0.0 for deterministic algorithms.
        # EPN may add a small neural offset, so we allow a tolerance for it.
        if algo == "EPN":
            # Neural model may add a learned offset; verify it is still near-immediate
            assert m7_tasks[0].start_time <= 10.0, (
                f"EPN delayed M7 excessively: start_time={m7_tasks[0].start_time}"
            )
        else:
            assert m7_tasks[0].start_time == 0.0, f"Idle machine opportunity missed for M7 by {algo}"

        # 3. Verify zero tardiness for all jobs since capacity is available
        assert res.metrics.late_jobs_count == 0, f"{algo} failed to meet deadlines"
        assert res.metrics.total_tardiness == 0.0

def test_dynamic_arrival_rescheduling_with_running_task_lock(ten_machines):
    """
    Simulates a live factory in progress:
    - Machine M1 is currently BUSY processing Job 2 with 120 minutes remaining.
    - A sudden URGENT Job enters (due in 200 minutes, needs M1 for 50 minutes).
    - The system must reschedule:
      * Machine M1 CANNOT be preempted (must finish its 120 minutes).
      * The new urgent job must be scheduled on M1 IMMEDIATELY at t = 120 mins.
      * Future remaining operations must be re-ordered without violating precedence.
    """
    # Factory state at sim_time = 100.0: M1 is busy
    busy_machines = [
        Machine(
            machine_id="M1",
            name="Machine 1",
            capability="Process_1",
            status=MachineStatus.BUSY,
            current_job_id="ACTIVE_HEAVY_JOB",
            current_operation_seq=1,
            remaining_processing_time=120.0 # Will finish at 100 + 120 = 220
        )
    ] + [
        Machine(machine_id=f"M{i+1}", name=f"Machine {i+1}", capability=f"Process_{i+1}")
        for i in range(1, 10)
    ]

    # Existing waiting job + New arrived urgent job
    jobs = [
        Job(
            job_id="EXISTING_JOB",
            name="Normal Job",
            product_type="Standard",
            arrival_time=0.0,
            due_date=1000.0,
            priority=2,
            operations=[
                Operation(sequence=1, name="Standard Milling", machine_id="M1", duration=90.0),
                Operation(sequence=2, name="Standard Polish", machine_id="M2", duration=60.0)
            ]
        ),
        Job(
            job_id="NEW_URGENT_ARRIVAL",
            name="Emergency Part",
            product_type="VIP Order",
            arrival_time=100.0, # Just arrived at sim_time = 100
            due_date=400.0,     # Very urgent
            priority=5,
            operations=[
                Operation(sequence=1, name="Urgent Cut", machine_id="M1", duration=50.0),
                Operation(sequence=2, name="Urgent Finish", machine_id="M3", duration=40.0)
            ]
        )
    ]

    current_sim_time = 100.0
    res = CPSATSchedulingOptimizer.optimize(jobs, busy_machines, current_time=current_sim_time, time_limit_seconds=2.0)

    # 1. Independent validation
    is_valid, errors = ScheduleValidator.validate(res.tasks, busy_machines, current_time=current_sim_time)
    assert is_valid, f"Reschedule failed validation: {errors}"

    # 2. Machine 1 was busy until 100 + 120 = 220.0
    # No new task on M1 should start before 220.0!
    m1_tasks = [t for t in res.tasks if t.machine_id == "M1"]
    for t in m1_tasks:
        assert t.start_time >= 220.0 - 1e-4, f"Preemption violation on M1: Task started at {t.start_time} before busy lock ended at 220.0"

    # 3. Dynamic priority check: Urgent job arrived with priority 5 and tight deadline
    # The optimizer should place the urgent job first on M1 at t = 220.0!
    urgent_m1 = next(t for t in m1_tasks if t.job_id == "NEW_URGENT_ARRIVAL")
    assert urgent_m1.start_time == 220.0, f"Urgent job was delayed to {urgent_m1.start_time} instead of starting immediately when M1 became free"
