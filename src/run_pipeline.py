# src/run_pipeline.py
"""
Phase 7: Integrity and Automation.

One-command pipeline runner that executes all phases in order:
  01_collect.py   -> 02_profile.py   -> 03_clean.py   -> 04_integrate.py -> 05_analyze.py

Creates:
  - docs/audit_log.csv         (pipeline run history)
  - outputs/reconciliation.csv (row counts at each stage)

Raw/interim/clean files are never modified by this script. All fixes happen in code.
"""

import subprocess
import sys
import os
import csv
import datetime
import pathlib
import json

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SRC_DIR = pathlib.Path("src")
DOCS_DIR = pathlib.Path("docs")
OUTPUTS_DIR = pathlib.Path("outputs")
AUDIT_LOG = DOCS_DIR / "audit_log.csv"
RECONCILIATION = OUTPUTS_DIR / "reconciliation.csv"

# Pipeline phases in execution order
PHASES = [
    {"name": "01_collect",   "script": "01_collect.py",   "description": "Data collection"},
    {"name": "02_profile",   "script": "02_profile.py",   "description": "Data profiling"},
    {"name": "03_clean",     "script": "03_clean.py",     "description": "Data cleaning"},
    {"name": "04_integrate", "script": "04_integrate.py", "description": "Integration & validation"},
    {"name": "05_analyze",   "script": "05_analyze.py",   "description": "Analysis"},
]

# Ensure output folders exist
for d in (DOCS_DIR, OUTPUTS_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 7.2 Audit Log
# ---------------------------------------------------------------------------

def init_audit_log():
    """Create the audit log file with headers if it doesn't exist."""
    if not AUDIT_LOG.exists() or AUDIT_LOG.stat().st_size == 0:
        with open(AUDIT_LOG, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "run_id", "phase", "status", "started_at", "finished_at",
                "duration_seconds", "rows_input", "rows_output", "error_message",
            ])
        print(f"[Audit] Initialized audit log at {AUDIT_LOG}")


def log_run(run_id, phase_name, status, started_at, finished_at,
            rows_input, rows_output, error_message=None):
    """Append one row to the audit log.

    Why it matters: Provides traceability. If a pipeline run fails partway
    through, you can see exactly which phase failed, when, and why. The
    row counts also feed into the reconciliation table (Step 7.3).
    """
    duration = (finished_at - started_at).total_seconds()
    with open(AUDIT_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            run_id, phase_name, status,
            started_at.isoformat(timespec="seconds"),
            finished_at.isoformat(timespec="seconds"),
            round(duration, 2),
            rows_input, rows_output,
            error_message or "",
        ])
    print(f"[Audit] {phase_name}: {status} ({round(duration, 2)}s)")


# ---------------------------------------------------------------------------
# Helpers: count rows in output files
# ---------------------------------------------------------------------------

def count_rows_in_csv(path):
    """Count data rows (excluding header) in a CSV file."""
    if not path or not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None:
                return 0
            return sum(1 for _ in reader)
    except Exception:
        return 0


def find_latest_file(pattern, directory):
    """Find the most recently modified file matching a glob pattern."""
    import glob
    matches = glob.glob(os.path.join(str(directory), pattern))
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


# ---------------------------------------------------------------------------
# 7.3 Reconciliation Table
# ---------------------------------------------------------------------------

def write_reconciliation(run_id, stage_counts):
    """Write the reconciliation table showing row counts at each pipeline stage.

    Why it matters: Catches silent data loss between phases. For example, if
    Phase 3 cleaning drops 50% of rows unexpectedly, the reconciliation table
    makes that visible immediately rather than discovering it during analysis.

    Args:
        run_id: Unique identifier for this pipeline run
        stage_counts: dict of {stage_name: (rows_input, rows_output)}
    """
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RECONCILIATION, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "run_id", "stage", "rows_input", "rows_output",
            "rows_lost", "loss_pct",
        ])
        for stage, (rows_in, rows_out) in stage_counts.items():
            lost = rows_in - rows_out
            pct = (lost / rows_in * 100) if rows_in > 0 else 0.0
            w.writerow([
                run_id, stage, rows_in, rows_out,
                lost, round(pct, 2),
            ])
    print(f"[Reconciliation] Table saved to {RECONCILIATION}")
    print(f"{'Stage':<25} {'Input':>8} {'Output':>8} {'Lost':>8} {'Loss%':>8}")
    print("-" * 57)
    for stage, (rows_in, rows_out) in stage_counts.items():
        lost = rows_in - rows_out
        pct = (lost / rows_in * 100) if rows_in > 0 else 0.0
        print(f"{stage:<25} {rows_in:>8} {rows_out:>8} {lost:>8} {pct:>7.2f}%")


# ---------------------------------------------------------------------------
# Phase runner
# ---------------------------------------------------------------------------

def run_phase(run_id, phase):
    """Run a single pipeline phase script and capture results.

    Why it matters: Each phase is isolated. If one phase fails, the pipeline
    stops and reports which phase failed, rather than cascading errors through
    downstream phases. Row counts are captured for the reconciliation table.

    Args:
        run_id: Unique identifier for this pipeline run
        phase: dict with keys 'name', 'script', 'description'

    Returns:
        dict: {status, rows_input, rows_output, error_message}
    """
    script_path = SRC_DIR / phase["script"]
    started_at = datetime.datetime.now()
    status = "SUCCESS"
    error_message = None
    rows_input = 0
    rows_output = 0

    print(f"\n{'=' * 70}")
    print(f"RUNNING PHASE: {phase['name']} — {phase['description']}")
    print(f"{'=' * 70}")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour max per phase
        )

        # Print the phase's stdout so the user sees progress
        if result.stdout:
            print(result.stdout)

        if result.returncode != 0:
            status = "FAILED"
            error_message = result.stderr[-2000:] if result.stderr else "Unknown error"
            print(f"[ERROR] Phase {phase['name']} failed with return code {result.returncode}")
            if result.stderr:
                print(result.stderr[-2000:])

    except subprocess.TimeoutExpired:
        status = "FAILED"
        error_message = "Phase timed out after 1 hour"
        print(f"[ERROR] Phase {phase['name']} timed out")
    except Exception as e:
        status = "FAILED"
        error_message = str(e)
        print(f"[ERROR] Phase {phase['name']} raised exception: {e}")

    finished_at = datetime.datetime.now()

    # Try to capture row counts from output files
    rows_input, rows_output = capture_row_counts(phase["name"])

    log_run(
        run_id=run_id,
        phase_name=phase["name"],
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        rows_input=rows_input,
        rows_output=rows_output,
        error_message=error_message,
    )

    return {"status": status, "rows_input": rows_input, "rows_output": rows_output,
            "error_message": error_message}


def capture_row_counts(phase_name):
    """Attempt to read row counts from a phase's output files.

    Why it matters: Row counts feed the reconciliation table, which catches
    silent data loss between phases.
    """
    rows_input = 0
    rows_output = 0

    if phase_name == "01_collect":
        # Input: N/A (collects from external APIs)
        # Output: raw files in data/raw/
        raw_dir = pathlib.Path("data/raw")
        if raw_dir.exists():
            files = list(raw_dir.glob("*"))
            rows_output = len([f for f in files if f.is_file() and f.name != "manifest.csv"])

    elif phase_name == "02_profile":
        # Input: raw files
        raw_dir = pathlib.Path("data/raw")
        if raw_dir.exists():
            rows_input = len([f for f in raw_dir.glob("*") if f.is_file() and f.name != "manifest.csv"])
        # Output: profiling report (not a CSV with countable rows)
        rows_output = 1 if (DOCS_DIR / "profiling_report.txt").exists() else 0

    elif phase_name == "03_clean":
        # Input: raw files
        raw_dir = pathlib.Path("data/raw")
        if raw_dir.exists():
            rows_input = len([f for f in raw_dir.glob("*") if f.is_file() and f.name != "manifest.csv"])
        # Output: interim clean files
        interim_dir = pathlib.Path("data/interim")
        if interim_dir.exists():
            rows_output = len([f for f in interim_dir.glob("*_clean.csv") if f.is_file()])

    elif phase_name == "04_integrate":
        # Input: interim clean files
        interim_dir = pathlib.Path("data/interim")
        if interim_dir.exists():
            rows_input = sum(
                count_rows_in_csv(f) for f in interim_dir.glob("*_clean.csv")
            )
        # Output: master dataset
        master_path = pathlib.Path("data/clean/master_dataset.csv")
        rows_output = count_rows_in_csv(master_path)

    elif phase_name == "05_analyze":
        # Input: master dataset
        master_path = pathlib.Path("data/clean/master_dataset.csv")
        rows_input = count_rows_in_csv(master_path)
        # Output: analysis outputs (not a single countable CSV)
        rows_output = 1 if (OUTPUTS_DIR / "summary_stats.csv").exists() else 0

    return rows_input, rows_output


# ---------------------------------------------------------------------------
# Main — run all phases
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"=" * 70)
    print(f"PIPELINE RUN ID: {run_id}")
    print(f"Started: {datetime.datetime.now().isoformat()}")
    print(f"=" * 70)

    # 7.2 Initialize audit log
    init_audit_log()

    # Run all phases in order
    stage_counts = {}
    all_success = True

    for phase in PHASES:
        result = run_phase(run_id, phase)
        stage_counts[phase["name"]] = (
            result["rows_input"],
            result["rows_output"],
        )
        if result["status"] != "SUCCESS":
            all_success = False
            print(f"\n[STOP] Pipeline halted at phase {phase['name']} due to failure.")
            break

    # 7.3 Write reconciliation table
    write_reconciliation(run_id, stage_counts)

    # Final summary
    print(f"\n{'=' * 70}")
    print(f"PIPELINE RUN COMPLETE: {run_id}")
    print(f"Status: {'ALL PHASES PASSED' if all_success else 'SOME PHASES FAILED'}")
    print(f"Finished: {datetime.datetime.now().isoformat()}")
    print(f"Audit log: {AUDIT_LOG}")
    print(f"Reconciliation: {RECONCILIATION}")
    print(f"{'=' * 70}")

    sys.exit(0 if all_success else 1)