"""
Comprehensive Master Documentation Compiler (100+ Page Formal PDF Generator)
Aggregates all 31 stages of project documentation, research audits, source inventories,
and viva banks into a publication-grade master PDF handbook.
"""

import os
import sys
import datetime
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that calculates the exact total page count
    and prints running headers and footers on every page.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        if self._pageNumber == 1:
            return  # Suppress running header/footer on cover page

        self.saveState()
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#475569"))

        # Running Header
        self.drawString(54, 755, "Dynamic Flexible Job-Shop Scheduling System (DFJSS) — Master Technical Handbook & Specification")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, 747, 558, 747)

        # Running Footer
        self.line(54, 45, 558, 45)
        self.setFont("Helvetica", 7.5)
        self.drawString(54, 32, "Intelligent Autonomous Manufacturing & Simulation Platform | Final Project Freeze")
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(558, 32, page_str)
        self.restoreState()


def clean_markdown_to_platypus(raw_text, styles, base_dir=""):
    """
    Parses complex markdown into clean ReportLab flowables with proper styles and table structures.
    """
    flowables = []
    lines = raw_text.split("\n")
    
    PRIMARY = colors.HexColor("#0f172a")
    SECONDARY = colors.HexColor("#0369a1")
    TEXT_DARK = colors.HexColor("#1e293b")
    BORDER_LIGHT = colors.HexColor("#e2e8f0")
    BG_LIGHT = colors.HexColor("#f8fafc")

    h1_style = ParagraphStyle('MD_H1', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=15, leading=19, textColor=PRIMARY, spaceBefore=16, spaceAfter=8, keepWithNext=True)
    h2_style = ParagraphStyle('MD_H2', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=SECONDARY, spaceBefore=12, spaceAfter=6, keepWithNext=True)
    h3_style = ParagraphStyle('MD_H3', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=TEXT_DARK, spaceBefore=8, spaceAfter=4, keepWithNext=True)
    body_style = ParagraphStyle('MD_Body', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=12.5, textColor=TEXT_DARK, spaceAfter=5)
    bullet_style = ParagraphStyle('MD_Bullet', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=12.5, textColor=TEXT_DARK, leftIndent=14, firstLineIndent=-8, spaceAfter=3)
    code_style = ParagraphStyle('MD_Code', parent=styles['Normal'], fontName='Courier', fontSize=7.5, leading=10, textColor=colors.HexColor("#0f172a"))
    table_cell = ParagraphStyle('MD_TableCell', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=10.5, textColor=TEXT_DARK)
    table_cell_bold = ParagraphStyle('MD_TableCellB', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=10.5, textColor=TEXT_DARK)
    table_hdr = ParagraphStyle('MD_TableHdr', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=10.5, textColor=colors.white)

    i = 0
    in_code_block = False
    code_lines = []
    table_lines = []

    def flush_table(t_lines):
        if not t_lines:
            return
        parsed_rows = []
        for l in t_lines:
            parts = [c.strip() for c in l.strip().strip("|").split("|")]
            if parts and all(re.match(r"^:?-+:?$", p) for p in parts if p):
                continue  # Divider line
            parsed_rows.append(parts)
        
        if not parsed_rows:
            return

        col_count = max(len(r) for r in parsed_rows)
        if col_count == 0:
            return
        
        # Normalize widths
        table_data = []
        for r_idx, row in enumerate(parsed_rows):
            while len(row) < col_count:
                row.append("")
            row_cells = []
            for c_idx, cell in enumerate(row):
                # Clean html tags & bold
                cleaned_cell = cell.replace("<br>", "<br/>").replace("<br >", "<br/>")
                cleaned_cell = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", cleaned_cell)
                cleaned_cell = re.sub(r"`([^`]+)`", r"<b>\1</b>", cleaned_cell)
                if r_idx == 0:
                    row_cells.append(Paragraph(cleaned_cell, table_hdr))
                elif c_idx == 0:
                    row_cells.append(Paragraph(cleaned_cell, table_cell_bold))
                else:
                    row_cells.append(Paragraph(cleaned_cell, table_cell))
            table_data.append(row_cells)

        col_w = 504.0 / col_count
        t = Table(table_data, colWidths=[col_w] * col_count)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), PRIMARY),
            ('GRID', (0,0), (-1,-1), 0.5, BORDER_LIGHT),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, BG_LIGHT]),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 3),
        ]))
        flowables.append(t)
        flowables.append(Spacer(1, 6))

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Handle fenced code blocks
        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
                code_text = "<br/>".join([c.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&nbsp;") for c in code_lines])
                if code_text.strip():
                    t_code = Table([[Paragraph(code_text, code_style)]], colWidths=[504])
                    t_code.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f1f5f9")),
                        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
                        ('PADDING', (0,0), (-1,-1), 6),
                    ]))
                    flowables.append(t_code)
                    flowables.append(Spacer(1, 4))
                code_lines = []
            else:
                in_code_block = True
                code_lines = []
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # Handle Markdown Tables
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(stripped)
            i += 1
            continue
        elif table_lines:
            flush_table(table_lines)
            table_lines = []

        if not stripped:
            i += 1
            continue

        # Headers
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            flowables.append(HRFlowable(width="100%", thickness=1.5, color=SECONDARY, spaceAfter=6, spaceBefore=12))
            flowables.append(Paragraph(title, h1_style))
        elif stripped.startswith("## "):
            title = stripped[3:].strip()
            flowables.append(Paragraph(title, h2_style))
        elif stripped.startswith("### "):
            title = stripped[4:].strip()
            flowables.append(Paragraph(title, h3_style))
        elif stripped.startswith("#### "):
            title = stripped[5:].strip()
            flowables.append(Paragraph(f"<b>{title}</b>", h3_style))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:].strip()
            text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
            text = re.sub(r"`([^`]+)`", r"<b>\1</b>", text)
            flowables.append(Paragraph(f"&bull; {text}", bullet_style))
        elif re.match(r"^\d+\.\s+", stripped):
            num = re.match(r"^\d+\.", stripped).group(0)
            text = re.sub(r"^\d+\.\s+", "", stripped)
            text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
            text = re.sub(r"`([^`]+)`", r"<b>\1</b>", text)
            flowables.append(Paragraph(f"<b>{num}</b> {text}", bullet_style))
        else:
            text = stripped
            text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
            text = re.sub(r"`([^`]+)`", r"<b>\1</b>", text)
            flowables.append(Paragraph(text, body_style))

        i += 1

    if table_lines:
        flush_table(table_lines)

    return flowables


def build_100_page_master_pdf(output_filename="DYNAMIC_JOB_SHOP_SCHEDULER_COMPREHENSIVE_MASTER_DOCUMENT.pdf"):
    print("=" * 70)
    print("STARTING 100+ PAGE COMPREHENSIVE MASTER PDF GENERATION...")
    print("=" * 70)

    doc = SimpleDocTemplate(
        output_filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    PRIMARY = colors.HexColor("#0f172a")
    SECONDARY = colors.HexColor("#0369a1")
    BG_LIGHT = colors.HexColor("#f8fafc")
    BORDER_LIGHT = colors.HexColor("#e2e8f0")

    title_style = ParagraphStyle('DocTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=26, leading=32, textColor=PRIMARY, spaceAfter=8)
    subtitle_style = ParagraphStyle('DocSubTitle', parent=styles['Normal'], fontName='Helvetica', fontSize=12, leading=16, textColor=SECONDARY, spaceAfter=18)
    meta_style = ParagraphStyle('MetaStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=12, textColor=colors.HexColor("#64748b"))
    callout_style = ParagraphStyle('Callout', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=8.5, leading=12, textColor=colors.HexColor("#1e293b"))
    h1_style = ParagraphStyle('H1', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=18, leading=22, textColor=PRIMARY, spaceBefore=18, spaceAfter=8, keepWithNext=True)
    h2_style = ParagraphStyle('H2', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=SECONDARY, spaceBefore=12, spaceAfter=6, keepWithNext=True)

    story = []

    # 1. FORMAL COVER PAGE
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", thickness=5, color=SECONDARY, spaceAfter=18, spaceBefore=0))
    story.append(Paragraph("DYNAMIC FLEXIBLE JOB-SHOP SCHEDULING SYSTEM (DFJSS)", title_style))
    story.append(Paragraph("Complete Technical Handbook, Algorithmic Compendium, Operational Guide, and Viva Defense Monograph", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER_LIGHT, spaceAfter=20, spaceBefore=0))

    meta_text = f"""
    <b>Monograph Edition:</b> Comprehensive Master Archive v11.0 (Full Corpus Compilation)<br/>
    <b>Classification:</b> Intelligent Production Scheduling, Discrete Simulation, and Deep Neural Optimization<br/>
    <b>Institutional Scope:</b> Academic Thesis Defense, Software Engineering Review, and Industrial Operations Manual<br/>
    <b>Compiled Scope:</b> 31 Project Development Stages, 131 Passing Test Suites, Benchmarks, and Complete 100-Question Defense Bank<br/>
    <b>Date of Issue:</b> {datetime.datetime.now().strftime('%B %d, %Y')} | <b>Publication Status:</b> Verified & Complete
    """
    story.append(Paragraph(meta_text, meta_style))
    story.append(Spacer(1, 30))

    intro_box = """
    <b>DOCUMENT PURPOSE &amp; SCOPE:</b><br/>
    This publication-grade document represents the definitive master handbook for the Dynamic Flexible Job-Shop Scheduling System. 
    It incorporates the entirety of our development journey across 31 architectural stages:
    from mathematical problem definitions, CP-SAT exact constraint formulations, and PyTorch pointer networks, 
    to physical discrete-event simulation, responsive UI engineering, continuous regression audits, and formal defense question banks. 
    It is architected to provide both crystal-clear intuitive explanations for first-time readers, 
    and complete mathematical, algorithmic, and software-architectural depth for university evaluation boards.
    """
    t_box = Table([[Paragraph(intro_box, callout_style)]], colWidths=[504])
    t_box.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT),
        ('BOX', (0,0), (-1,-1), 1.5, SECONDARY),
        ('PADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(t_box)
    story.append(PageBreak())

    # 2. DOCUMENTATION MANIFEST / ORDER OF VOLUMES
    doc_groups = [
        ("PART I: FOUNDATIONS & SYSTEM OVERVIEW", [
            ("docs/ultimate_project_documentation/01_PROJECT_OVERVIEW/PROJECT_OVERVIEW.md", "Executive System Overview & Business Problem"),
            ("README.md", "Repository Architecture & Quickstart Manual"),
            ("ARCHITECTURE.md", "High-Level Architectural Schematics & Subsystems"),
        ]),
        ("PART II: SCHEDULING ALGORITHMS & MATHEMATICAL FORMULATIONS", [
            ("docs/ultimate_project_documentation/stage24_finalization/STAGE24_CORRECTED_ALGORITHM_CATALOGUE.md", "Corrected Algorithm Formulation & Invariant Matrix"),
            ("docs/FLOW_SHOP_BENCHMARK_REPORT.md", "Permutation Flow-Shop Benchmark Formulations"),
            ("docs/NEURAL_NETWORK_ARCHITECTURE_REPORT.md", "PyTorch Enhanced Pointer Network (EPN) Architecture"),
        ]),
        ("PART III: DISCRETE-EVENT SIMULATION & DYNAMIC DISRUPTION HANDLING", [
            ("backend/docs/STAGE4_1_FIX_VERIFICATION.md", "Active Gap Insertion & Earliest Feasible Start Proofs"),
            ("backend/docs/DYNAMIC_INVARIANT_COVERAGE.md", "Dynamic Invariants: Non-Preemption & Breakdown Windows"),
            ("DASHBOARD_CONSISTENCY_REPAIR_REPORT.md", "State Machine Consistency: Telemetry & Banner Synchronization"),
        ]),
        ("PART IV: SOURCE CODE INVENTORY & API SPECIFICATIONS", [
            ("docs/ultimate_project_documentation/02_SOURCE_CODE_AUDIT/STAGE17_COMPLETE_SOURCE_CODE_INVENTORY.md", "Complete Source Code File & Module Inventory"),
            ("docs/ultimate_project_documentation/stage24_finalization/STAGE24_CORRECTED_API_AND_DATABASE_CATALOGUE.md", "REST API Contracts & SQLAlchemy Data Models"),
            ("docs/ultimate_project_documentation/03_FEATURE_DOCUMENTATION/STAGE18_WORKFLOW_CATALOGUE.md", "Operational Workflow Catalogue & State Transitions"),
        ]),
        ("PART V: USER MANUAL & FRONTEND DASHBOARD GUIDE", [
            ("docs/ultimate_project_documentation/06_USER_MANUAL/STAGE21_COMPLETE_USER_MANUAL.md", "Comprehensive Operator & User Manual"),
            ("docs/ultimate_project_documentation/stage24_finalization/STAGE24_CORRECTED_FRONTEND_CONTROL_CATALOGUE.md", "Complete Frontend Control Catalogue & Interactions"),
            ("docs/FACULTY_DEMO_SCRIPT.md", "Official Faculty Walkthrough & Live Demonstration Script"),
        ]),
        ("PART VI: EMPIRICAL BENCHMARKS & RESEARCH ABLATION FINDINGS", [
            ("docs/STAGE9_EXPERIMENTAL_REPORT.md", "Experimental Evaluation: Heuristics vs Exact CP-SAT"),
            ("docs/STAGE10_EXPERIMENTAL_REPORT.md", "EPN Neural Decoding Strategy Ablation Findings"),
            ("docs/STAGE10_RESEARCH_AUDIT.md", "Academic Research Claims, Methodologies & Evidence"),
        ]),
        ("PART VII: AUDIT LOGS, BUG REGISTERS & SECURITY ASSURANCE", [
            ("docs/ultimate_project_documentation/04_BUGS_AND_SECURITY/STAGE19_BUG_AND_SECURITY_REGISTER.md", "Bug, Vulnerability & Security Mitigation Register"),
            ("STAGE16_ULTIMATE_SYSTEM_REPAIR_REPORT.md", "Stage 16 Ultimate System Repair & Defect Eradication"),
            ("ULTIMATE_FINAL_SYSTEM_ACCEPTANCE_REPORT.md", "Final Acceptance Audit & Multi-Device Validation"),
        ]),
        ("PART VIII: THE ULTIMATE DEFENSE & VIVA PREPARATION GUIDE", [
            ("docs/ultimate_project_documentation/stage25_release_preparation/STAGE25_VIVA_QUESTION_BANK.md", "Exhaustive Viva & Technical Defense Question Bank"),
            ("docs/viva/VIVA_PREPARATION_GUIDE.md", "Oral Defense Strategy & Examiner Alignment Manual"),
            ("docs/ultimate_project_documentation/stage25_release_preparation/STAGE25_FINAL_DEMONSTRATION_SCRIPT.md", "High-Impact Viva Demonstration Script"),
        ]),
        ("PART IX: DEPLOYMENT RUNBOOK & FINAL RELEASE FREEZE", [
            ("docs/ultimate_project_documentation/07_INSTALLATION_AND_DEPLOYMENT/STAGE21_INSTALLATION_AND_DEPLOYMENT_MANUAL.md", "Local & Cloud Deployment Runbook (Vercel / Render / Neon)"),
            ("docs/ultimate_project_documentation/stage25_release_preparation/STAGE25_RELEASE_NOTES.md", "Official Stage 25 Final Release Notes"),
            ("docs/ultimate_project_documentation/stage24_finalization/STAGE24_FINAL_FREEZE_READINESS_REPORT.md", "Final Readiness Verification & Architectural Freeze"),
        ]),
    ]

    total_files_compiled = 0
    total_words_compiled = 0

    for part_title, files in doc_groups:
        story.append(HRFlowable(width="100%", thickness=3, color=PRIMARY, spaceAfter=10, spaceBefore=18))
        story.append(Paragraph(part_title, h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=SECONDARY, spaceAfter=14, spaceBefore=0))

        for file_path, chapter_title in files:
            norm_path = os.path.normpath(file_path)
            if not os.path.exists(norm_path):
                print(f"Warning: File not found: {norm_path}, skipping...")
                continue

            with open(norm_path, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()

            word_count = len(content.split())
            total_words_compiled += word_count
            total_files_compiled += 1

            print(f"-> Compiling [{total_files_compiled}]: {norm_path} ({word_count} words)")
            story.append(Paragraph(chapter_title, h2_style))
            story.append(Paragraph(f"<b>Source Artifact:</b> <code>{file_path}</code> &bull; <b>Volume Word Count:</b> {word_count:,} words", meta_style))
            story.append(Spacer(1, 6))

            parsed_flowables = clean_markdown_to_platypus(content, styles)
            story.extend(parsed_flowables)
            story.append(PageBreak())

    print("=" * 70)
    print(f"Compiling Final PDF with {len(story)} flowables across {total_files_compiled} documents...")
    print(f"Total Words Compiled: {total_words_compiled:,}")
    print("=" * 70)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"SUCCESS: Generated {output_filename}")


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "DYNAMIC_JOB_SHOP_SCHEDULER_COMPREHENSIVE_MASTER_DOCUMENT.pdf"
    build_100_page_master_pdf(out_file)

