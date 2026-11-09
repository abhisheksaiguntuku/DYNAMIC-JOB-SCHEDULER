import sys
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def generate_handbook(pdf_path: str):
    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'],
        fontSize=22, leading=26, textColor=colors.HexColor('#0f172a'), alignment=1, spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'DocSub', parent=styles['Normal'],
        fontSize=11, leading=15, textColor=colors.HexColor('#475569'), alignment=1, spaceAfter=14
    )
    h1_style = ParagraphStyle(
        'H1', parent=styles['Heading2'],
        fontSize=13, leading=17, textColor=colors.HexColor('#0284c7'), spaceBefore=12, spaceAfter=6, keepWithNext=True
    )
    h2_style = ParagraphStyle(
        'H2', parent=styles['Heading3'],
        fontSize=10, leading=14, textColor=colors.HexColor('#0f172a'), spaceBefore=8, spaceAfter=4, keepWithNext=True
    )
    body_style = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontSize=8.5, leading=12.5, textColor=colors.HexColor('#1e293b'), spaceAfter=5
    )
    code_body = ParagraphStyle(
        'CodeBody', parent=styles['Normal'],
        fontSize=8, leading=11, fontName='Helvetica-Oblique', textColor=colors.HexColor('#0369a1')
    )
    table_cell = ParagraphStyle(
        'TableCell', parent=styles['Normal'],
        fontSize=8, leading=10, textColor=colors.HexColor('#1e293b')
    )
    table_hdr = ParagraphStyle(
        'TableHdr', parent=styles['Normal'],
        fontSize=8, leading=10, fontName='Helvetica-Bold', textColor=colors.white
    )

    elements = []

    # Title Banner
    elements.append(Paragraph("Dynamic Job Shop & Flow Shop Scheduling Engine", title_style))
    elements.append(Paragraph("<b>Operator & User Mini Handbook</b> — Complete Guide to Every Button, Metric, Engine & Algorithm", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284c7'), spaceAfter=10))

    # SECTION 1: WHAT IS THIS SYSTEM?
    elements.append(Paragraph("1. System Overview: What Is This Project?", h1_style))
    elements.append(Paragraph(
        "This platform is an <b>AI-Powered Real-Time Dynamic Job Shop and Flow Shop Production Scheduler</b>. "
        "In modern manufacturing plants (like heavy railway engineering, automotive foundries, and CNC centers), "
        "multiple custom work orders compete for the same physical machines. If machines are scheduled poorly, "
        "work-in-progress (WIP) queues pile up, jobs get delayed, and machines sit idle.<br/>"
        "This system solves that by offering: "
        "<b>1) Real-Time Simulation</b>, <b>2) Exact Optimization via Google OR-Tools CP-SAT</b>, "
        "<b>3) Academic Flow Shop Heuristics (Palmer, CDS, NEH)</b>, <b>4) Deep Learning (Pointer Networks)</b>, and "
        "<b>5) Machine Learning Strategy Recommendation</b>.",
        body_style
    ))

    # SECTION 2: TOP HEADER & ACTION CONTROLS
    elements.append(Paragraph("2. Top Navigation Bar: What Every Button Means", h1_style))
    btn_data = [
        [Paragraph("Control / Button", table_hdr), Paragraph("Visual Icon", table_hdr), Paragraph("What It Actually Does / Purpose", table_hdr)],
        [Paragraph("Sim Clock Display", table_cell), Paragraph("e.g. 540 hrs", code_body), Paragraph("Shows the current virtual factory time in <b>hours</b>. All operations and progress move relative to this clock.", table_cell)],
        [Paragraph("+5, +15, +30, +60 hrs", table_cell), Paragraph("FastForward (Blue)", code_body), Paragraph("Advances virtual factory time. Machines finish active tasks, IDLE machines pick the next queued job, and telemetry updates.", table_cell)],
        [Paragraph("Auto Play (1x, 2x, 5x)", table_cell), Paragraph("Play / Pause (Green)", code_body), Paragraph("Hands-free execution. Runs the factory continuously at selected speeds so you can watch live progress on the Gantt chart.", table_cell)],
        [Paragraph("Export CSV", table_cell), Paragraph("Download (Cyan)", code_body), Paragraph("Exports the exact current schedule, including job dispatches, assigned machines, start and end hours, into an Excel-ready CSV file.", table_cell)],
        [Paragraph("Upload Excel/CSV", table_cell), Paragraph("Upload (Blue)", code_body), Paragraph("Batch registers multiple jobs at once from an Excel (.xlsx) or CSV file. Automatically reads machines, operations, and due dates.", table_cell)],
        [Paragraph("Add Dynamic Job", table_cell), Paragraph("PlusCircle (Emerald)", code_body), Paragraph("Opens a form to add a single emergency or custom job. Automatically determines job priority from due date slack.", table_cell)],
        [Paragraph("Reset Demo", table_cell), Paragraph("RotateCcw (Slate)", code_body), Paragraph("Restores the factory to the standard 10 baseline demo jobs and resets the clock to 0 hrs without clearing algorithms.", table_cell)],
        [Paragraph("Clear All", table_cell), Paragraph("Trash (Red)", code_body), Paragraph("Clears all jobs from the factory floor to simulate a clean empty shop floor ready for custom input.", table_cell)],
        [Paragraph("How It Works", table_cell), Paragraph("HelpCircle (Cyan)", code_body), Paragraph("Launches an interactive 5-step tutorial walkthrough highlighting each major dashboard section.", table_cell)],
    ]
    t_btn = Table(btn_data, colWidths=[120, 85, 335])
    t_btn.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f8fafc'), colors.white]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    elements.append(t_btn)
    elements.append(Spacer(1, 10))

    # SECTION 3: TOP KPI METRICS BAR
    elements.append(Paragraph("3. Factory KPI Metric Cards: What Each Card Means", h1_style))
    kpi_data = [
        [Paragraph("KPI Card Title", table_hdr), Paragraph("Unit", table_hdr), Paragraph("Industrial Meaning & Calculation", table_hdr)],
        [Paragraph("Makespan (Cmax)", table_cell), Paragraph("Hours (hrs)", code_body), Paragraph("Total elapsed time until the very last operation of the last job is completed. Lower is better.", table_cell)],
        [Paragraph("Total Tardiness", table_cell), Paragraph("Hours (hrs)", code_body), Paragraph("Sum of delivery delay past the due date: $\\sum \\max(0, C_j - DD_j)$. Zero means all orders delivered on time.", table_cell)],
        [Paragraph("Late Jobs", table_cell), Paragraph("Count", code_body), Paragraph("Number of customer orders that missed their promised deadline ($C_j > DD_j$).", table_cell)],
        [Paragraph("Avg Waiting Time", table_cell), Paragraph("Hours (hrs)", code_body), Paragraph("Average time jobs spend queueing in front of machines before getting worked on.", table_cell)],
        [Paragraph("Schedule Utilization", table_cell), Paragraph("Percentage (%)", code_body), Paragraph("Percentage of total shop floor machine capacity actively engaged in cutting, moulding, or casting.", table_cell)],
        [Paragraph("Solver Status / Latency", table_cell), Paragraph("Status / ms", code_body), Paragraph("Displays whether the solution is OPTIMAL or FEASIBLE and execution time in milliseconds (typically 0.2 to 3 ms).", table_cell)],
    ]
    t_kpi = Table(kpi_data, colWidths=[130, 75, 335])
    t_kpi.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0369a1')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f8fafc'), colors.white]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    elements.append(t_kpi)

    elements.append(PageBreak())

    # SECTION 4: PRODUCTION JOB LIFECYCLE DASHBOARD & EDIT PENCIL
    elements.append(Paragraph("4. Production Job Lifecycle Dashboard & Table Actions", h1_style))
    elements.append(Paragraph(
        "This interactive table lists every active job order on the shop floor with its status, progress, assigned machine, and deadlines.",
        body_style
    ))
    elements.append(Paragraph(
        "<b>Action Column Icons:</b><br/>"
        "• <b>✏️ Pencil Icon (Edit Job):</b> Appears <b>only for Unstarted / Pending jobs</b> waiting in the queue. "
        "Once a job starts cutting on a machine or finishes completely, industrial protocol prevents altering its physical work order. "
        "Clicking this icon opens a modal to adjust due dates, stage names, or machine durations.<br/>"
        "• <b>🗑️ Trash Icon (Delete Job):</b> Cancels and removes an unstarted job order and immediately recalculates the schedule.",
        body_style
    ))
    elements.append(Paragraph(
        "<b>Automatic Priority Badges:</b><br/>"
        "The system calculates priority automatically from Due Date Slack ($Slack = DD - [Arrival + \\sum Duration]$):<br/>"
        "• <font color='#ef4444'><b>P1 (Critical / Urgent):</b></font> Assigned when $Slack \\le 5\\text{ hrs}$. Requires immediate machine allocation.<br/>"
        "• <font color='#f59e0b'><b>P2 (High Priority):</b></font> Assigned when $5 < Slack \\le 20\\text{ hrs}$.<br/>"
        "• <font color='#38bdf8'><b>P3 (Normal / Routine):</b></font> Assigned when $Slack > 20\\text{ hrs}$. Ample buffer time.",
        body_style
    ))
    elements.append(Spacer(1, 8))

    # SECTION 5: MACHINE TELEMETRY & BREAKDOWN SIMULATION
    elements.append(Paragraph("5. 10-Machine Real-Time Factory Floor Telemetry", h1_style))
    elements.append(Paragraph(
        "Ten production stations ($M_1 \\dots M_{10}$) represent physical primary foundry stages and parallel auxiliary stations:<br/>"
        "• <b>M1:</b> Pattern Making | <b>M2:</b> Mould Making | <b>M3:</b> Casting (Foundry) | <b>M4:</b> Heat Treatment | <b>M5:</b> Machining Center<br/>"
        "• <b>M6-M10:</b> Auxiliary parallel prep, dry, pouring, tempering, and quality finishing centers.<br/>"
        "• <b>'Sim Breakdown (+20 hrs)':</b> Simulates a real-world machine outage (e.g., motor failure). "
        "The engine marks the machine <b>DOWN</b> in red, suspends its progress, and instantly re-routes pending work to available parallel machines without deadlock.<br/>"
        "• <b>'Recover Machine':</b> Simulates completed maintenance, returning the station to <b>IDLE</b>.",
        body_style
    ))
    elements.append(Spacer(1, 8))

    # SECTION 6: AI STRATEGY ADVISOR & DISPATCH SELECTOR
    elements.append(Paragraph("6. AI Strategy Advisor: How Suggestions Work & Where Palmer Is", h1_style))
    elements.append(Paragraph(
        "<b>Where to find Palmer's Algorithm:</b><br/>"
        "In the <b>'AI Strategy Advisor & Dispatch'</b> panel on the right side of the screen, look at the dropdown menu under "
        "<b>'Active Scheduling Engine'</b>. Select <b>'Palmer's Heuristic Algorithm (Slope Index)'</b> and click the blue <b>'Re-Solve'</b> button. "
        "The engine will instantly compute Palmer's slope indices for all jobs and dispatch them in optimal descending order.",
        body_style
    ))
    elements.append(Paragraph(
        "<b>How the ML Strategy Recommendation Works:</b><br/>"
        "The AI Advisor continuously analyzes shop floor conditions (workload urgency, machine congestion, queue variance, breakdown counts) "
        "and uses a trained Random Forest model to recommend the best dispatching rule:<br/>"
        "• <b>SPT:</b> Recommended during high backlogs to minimize average queue waiting.<br/>"
        "• <b>EDD:</b> Recommended when deadlines are tight to eliminate late penalty costs.<br/>"
        "• <b>AGING:</b> Recommended when older orders sit too long in queue to prevent starvation.<br/>"
        "• <b>PALMER:</b> Recommended for multi-stage continuous flow patterns.<br/>"
        "• <b>CP-SAT:</b> Recommended for finding the mathematically provable minimum makespan.<br/>"
        "Clicking <b>'⚡ Apply Recommendation & Re-Solve'</b> switches to the recommended rule in one click.",
        body_style
    ))

    elements.append(PageBreak())

    # SECTION 7: FAIR ALGORITHM BENCHMARK MATRIX
    elements.append(Paragraph("7. Fair Algorithm Benchmark & Performance Matrix: What It Shows", h1_style))
    elements.append(Paragraph(
        "Located at the bottom of the dashboard, this table takes the <b>exact current factory workload</b> and runs all "
        "seven scheduling engines in parallel side-by-side to show you how each one performs:",
        body_style
    ))
    matrix_cols = [
        [Paragraph("Algorithm in Matrix", table_hdr), Paragraph("Type", table_hdr), Paragraph("Optimization Logic / Core Behavior", table_hdr)],
        [Paragraph("FCFS", table_cell), Paragraph("Baseline Heuristic", code_body), Paragraph("Dispatches jobs strictly in the order they arrived on the shop floor.", table_cell)],
        [Paragraph("SPT", table_cell), Paragraph("Heuristic", code_body), Paragraph("Dispatches shortest duration jobs first; minimizes average waiting time.", table_cell)],
        [Paragraph("EDD", table_cell), Paragraph("Heuristic", code_body), Paragraph("Dispatches jobs with the earliest due date first; minimizes maximum tardiness.", table_cell)],
        [Paragraph("CR (Critical Ratio)", table_cell), Paragraph("Heuristic", code_body), Paragraph("Considers remaining slack relative to work content; balances urgency dynamically.", table_cell)],
        [Paragraph("AGING", table_cell), Paragraph("Heuristic", code_body), Paragraph("Anti-starvation priority rule; guarantees older jobs are not trapped behind quick jobs.", table_cell)],
        [Paragraph("PALMER", table_cell), Paragraph("Flow Shop Heuristic", code_body), Paragraph("Computes slope index $S_j = \\sum (2i - m - 1)p_{j,i}$ to optimize continuous flow shops.", table_cell)],
        [Paragraph("OR-TOOLS CP-SAT", table_cell), Paragraph("Exact Solver", code_body), Paragraph("Google Constraint Programming solver guaranteeing the absolute global minimum makespan.", table_cell)],
    ]
    t_mat = Table(matrix_cols, colWidths=[120, 100, 320])
    t_mat.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#94a3b8')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f8fafc'), colors.white]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    elements.append(t_mat)
    elements.append(Spacer(1, 10))

    # SECTION 8: STEP-BY-STEP USER WALKTHROUGH
    elements.append(Paragraph("8. Quick 5-Step Operator Walkthrough", h1_style))
    elements.append(Paragraph(
        "<b>Step 1: Check Current Shop Floor State</b> — Look at the top KPI cards (Makespan, Tardiness, Late Jobs).<br/>"
        "<b>Step 2: Add or Upload Work Orders</b> — Use <b>'Upload Excel/CSV'</b> to batch load test cases, or click <b>'Add Dynamic Job'</b> for single jobs.<br/>"
        "<b>Step 3: Modify Pending Orders</b> — Click the <b>✏️ Pencil icon</b> next to any unstarted job in the table to modify its parameters.<br/>"
        "<b>Step 4: Select an Algorithm & Re-Solve</b> — Choose <b>Palmer</b>, <b>CP-SAT</b>, <b>SPT</b>, or <b>EDD</b> from the dropdown and click <b>'Re-Solve'</b>.<br/>"
        "<b>Step 5: Advance Time & Watch Execution</b> — Click <b>'+15 hrs'</b> or toggle <b>'Auto Play'</b> to watch the Gantt chart and machine stations execute tasks live.",
        body_style
    ))
    elements.append(Spacer(1, 12))

    # Signoff Footer
    signoff = [
        [Paragraph("<b>Document:</b>", table_hdr), Paragraph("Dynamic Job Shop & Flow Shop Mini Handbook (v2.0)", table_cell)],
        [Paragraph("<b>Status:</b>", table_hdr), Paragraph("<font color='#059669'><b>OFFICIALLY VERIFIED & PRODUCTION READY</b></font>", table_cell)],
        [Paragraph("<b>GitHub:</b>", table_hdr), Paragraph("https://github.com/abhisheksaiguntuku/DYNAMIC-JOB-SCHEDULER", table_cell)],
    ]
    t_s = Table(signoff, colWidths=[90, 450])
    t_s.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#0284c7')),
        ('BACKGROUND', (1,0), (1,-1), colors.HexColor('#f1f5f9')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(KeepTogether(t_s))

    doc.build(elements)
    print(f"Handbook PDF generated: {pdf_path}")

if __name__ == "__main__":
    out = os.path.abspath("OPERATOR_AND_USER_MINI_HANDBOOK.pdf")
    generate_handbook(out)
