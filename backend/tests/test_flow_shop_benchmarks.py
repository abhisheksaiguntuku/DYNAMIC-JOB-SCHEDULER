import pytest
from app.scheduling.flow_shop.johnson import JohnsonAlgorithm
from app.scheduling.flow_shop.heuristics import FlowShopHeuristics
from app.scheduling.flow_shop.simulator import FlowShopSimulator

def test_two_machine_benchmark_exact():
    """
    Source D: Faculty Two-Machine Benchmark.
    Job A: (10, 2)
    Job B: (16, 8)
    Job C: (6, 10)
    Job D: (12, 14)
    Job E: (4, 12)
    Reported sequence: E -> C -> D -> B -> A.
    Reported makespan: 50 hours.
    """
    proc_times = {
        "A": (10, 2),
        "B": (16, 8),
        "C": (6, 10),
        "D": (12, 14),
        "E": (4, 12),
    }

    result = JohnsonAlgorithm.solve(proc_times)
    seq = result["optimal_sequence"]
    sim = result["simulation"]

    # Verify optimal sequence matches source exactly
    assert seq == ["E", "C", "D", "B", "A"], f"Computed sequence {seq} differs from reported"
    assert sim["makespan"] == 50.0, f"Computed makespan {sim['makespan']} != 50.0 hours"

    # Verify Machine 1 exact intervals: E: 0-4, C: 4-10, D: 10-22, B: 22-38, A: 38-48
    m1_intervals = sim["intervals_by_machine"]["Machine 1"]
    expected_m1 = [("E", 0, 4), ("C", 4, 10), ("D", 10, 22), ("B", 22, 38), ("A", 38, 48)]
    for (exp_j, exp_s, exp_e), act in zip(expected_m1, m1_intervals):
        assert act["job_id"] == exp_j
        assert act["start"] == exp_s
        assert act["end"] == exp_e

    # Verify Machine 2 exact intervals: E: 4-16, C: 16-26, D: 26-40, B: 40-48, A: 48-50
    m2_intervals = sim["intervals_by_machine"]["Machine 2"]
    expected_m2 = [("E", 4, 16), ("C", 16, 26), ("D", 26, 40), ("B", 40, 48), ("A", 48, 50)]
    for (exp_j, exp_s, exp_e), act in zip(expected_m2, m2_intervals):
        assert act["job_id"] == exp_j
        assert act["start"] == exp_s
        assert act["end"] == exp_e

def test_five_machine_benchmark_exact():
    """
    Source C: Faculty Five-Machine Flow Shop Benchmark.
    Processing times on M1..M5 (minutes) and Due Dates:
    J1: (8, 4, 4, 24, 6), d1 = 116
    J2: (6, 2, 4, 24, 2), d2 = 120
    J3: (10, 6, 8, 22, 8), d3 = 114
    J4: (12, 8, 6, 24, 6), d4 = 116
    J5: (14, 4, 8, 28, 8), d5 = 114
    """
    proc_times = {
        "J1": [8, 4, 4, 24, 6],
        "J2": [6, 2, 4, 24, 2],
        "J3": [10, 6, 8, 22, 8],
        "J4": [12, 8, 6, 24, 6],
        "J5": [14, 4, 8, 28, 8],
    }
    due_dates = {
        "J1": 116.0,
        "J2": 120.0,
        "J3": 114.0,
        "J4": 116.0,
        "J5": 114.0,
    }

    # 1. FCFS (Natural Benchmark Order: J1, J2, J3, J4, J5)
    fcfs_res = FlowShopHeuristics.fcfs(["J1", "J2", "J3", "J4", "J5"], proc_times, due_dates)
    assert fcfs_res["makespan"] == 146.0
    assert fcfs_res["avg_completion_time"] == 93.6
    assert fcfs_res["tardy_jobs_count"] == 1
    assert fcfs_res["mean_tardiness"] == 6.4

    # 2. Palmer Heuristic
    palmer_res = FlowShopHeuristics.palmer(proc_times, due_dates, use_faculty_sign_convention=True)
    assert palmer_res["job_order"] == ["J1", "J2", "J3", "J5", "J4"]
    assert palmer_res["makespan"] == 144.0
    assert palmer_res["avg_completion_time"] == 94.4
    assert palmer_res["tardy_jobs_count"] == 2
    assert palmer_res["mean_tardiness"] == 7.2

    # 3. CDS Heuristic
    # Note: Evaluates candidate stages. We verify table sequence: J2, J1, J3, J5, J4
    cds_res = FlowShopHeuristics.cds(proc_times, due_dates)
    assert cds_res["job_order"] == ["J2", "J1", "J3", "J5", "J4"]
    assert cds_res["makespan"] == 140.0
    assert cds_res["avg_completion_time"] == 90.4
    assert cds_res["tardy_jobs_count"] == 2
    assert cds_res["mean_tardiness"] == 5.6

    # 4. NEH Heuristic
    neh_res = FlowShopHeuristics.neh(proc_times, due_dates)
    assert neh_res["job_order"] == ["J1", "J3", "J5", "J4", "J2"]
    assert neh_res["makespan"] == 140.0
    assert neh_res["avg_completion_time"] == 94.8
    assert neh_res["tardy_jobs_count"] == 2
    assert neh_res["mean_tardiness"] == 4.8

def test_cds_discrepancy_reconciliation():
    """
    Source C Discrepancy Investigation:
    Result Table reports: J2, J1, J3, J5, J4 (Cmax = 140)
    Gantt Caption reports: J2, J3, J5, J4, J1
    We independently simulate both and document the exact differences.
    """
    proc_times = {
        "J1": [8, 4, 4, 24, 6],
        "J2": [6, 2, 4, 24, 2],
        "J3": [10, 6, 8, 22, 8],
        "J4": [12, 8, 6, 24, 6],
        "J5": [14, 4, 8, 28, 8],
    }
    due_dates = {"J1": 116.0, "J2": 120.0, "J3": 114.0, "J4": 116.0, "J5": 114.0}

    table_seq = ["J2", "J1", "J3", "J5", "J4"]
    caption_seq = ["J2", "J3", "J5", "J4", "J1"]

    res_table = FlowShopSimulator.simulate(table_seq, proc_times, due_dates)
    res_caption = FlowShopSimulator.simulate(caption_seq, proc_times, due_dates)

    assert res_table["makespan"] == 140.0
    assert res_caption["makespan"] == 140.0
    # Both achieve the same optimal Cmax = 140, but caption sequence has higher average completion time and tardiness:
    assert res_caption["avg_completion_time"] > res_table["avg_completion_time"]
