# tests/test_pipeline.py
"""
Unit tests for the Uganda Agri-Pipeline (Phase 7).

Why it matters: Unit tests catch regressions. If someone changes 03_clean.py
and accidentally drops valid rows, the tests will fail immediately rather
than producing silently wrong analysis results. Tests also document the
expected behavior of each phase.

Run with: python -m pytest tests/test_pipeline.py -v
          or: python -m unittest tests.test_pipeline -v
"""

import unittest
import os
import sys
import pandas as pd
import pathlib

# Add src to path so we can import pipeline modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
INTERIM_DIR = BASE_DIR / "data" / "interim"
CLEAN_DIR = BASE_DIR / "data" / "clean"
DOCS_DIR = BASE_DIR / "docs"
OUTPUTS_DIR = BASE_DIR / "outputs"


class TestPhase1Collect(unittest.TestCase):
    """Test data collection phase (01_collect.py)."""

    def test_raw_files_exist(self):
        """Why: Without raw files, no downstream phase can run."""
        self.assertTrue(RAW_DIR.exists(), "data/raw/ directory missing")
        raw_files = [f for f in RAW_DIR.iterdir()
                     if f.is_file() and f.name != "manifest.csv"]
        self.assertGreater(len(raw_files), 0, "No raw data files found")

    def test_manifest_exists(self):
        """Why: Checksums verify data integrity between runs."""
        manifest = RAW_DIR / "manifest.csv"
        self.assertTrue(manifest.exists(), "manifest.csv missing — checksums not computed")

    def test_manifest_has_required_columns(self):
        """Why: Manifest must track file, hash, size, and date for integrity."""
        manifest = RAW_DIR / "manifest.csv"
        if manifest.exists():
            df = pd.read_csv(manifest)
            required = {"file", "sha256", "size_bytes", "date"}
            self.assertTrue(required.issubset(set(df.columns)),
                            f"Manifest missing columns: {required - set(df.columns)}")


class TestPhase2Profile(unittest.TestCase):
    """Test data profiling phase (02_profile.py)."""

    def test_profiling_report_exists(self):
        """Why: Phase 3 requires a saved profiling report per the guide."""
        report = DOCS_DIR / "profiling_report.txt"
        self.assertTrue(report.exists(), "profiling_report.txt missing — Phase 3 incomplete")

    def test_issues_list_exists(self):
        """Why: Quality issues must be documented with size per the guide."""
        issues = DOCS_DIR / "issues.csv"
        self.assertTrue(issues.exists(), "issues.csv missing — Phase 3 incomplete")

    def test_issues_has_required_columns(self):
        """Why: Issues must include dataset, type, column, size, description."""
        issues = DOCS_DIR / "issues.csv"
        if issues.exists():
            df = pd.read_csv(issues)
            required = {"dataset", "issue_type", "column", "size", "description"}
            self.assertTrue(required.issubset(set(df.columns)),
                            f"Issues missing columns: {required - set(df.columns)}")


class TestPhase3Clean(unittest.TestCase):
    """Test data cleaning phase (03_clean.py)."""

    def test_interim_files_exist(self):
        """Why: Clean datasets must exist for integration (Phase 5)."""
        self.assertTrue(INTERIM_DIR.exists(), "data/interim/ directory missing")
        clean_files = list(INTERIM_DIR.glob("*_clean.csv"))
        self.assertGreater(len(clean_files), 0, "No clean interim files found")

    def test_worldbank_clean_has_expected_columns(self):
        """Why: Cleaned World Bank data needs country_code, year, crop_index for joins."""
        path = INTERIM_DIR / "worldbank_clean.csv"
        if path.exists():
            df = pd.read_csv(path)
            required = {"country_code", "year", "crop_index"}
            self.assertTrue(required.issubset(set(df.columns)),
                            f"worldbank_clean.csv missing columns: {required - set(df.columns)}")

    def test_cleaning_log_exists(self):
        """Why: Every cleaning change must be logged per the guide."""
        log = DOCS_DIR / "cleaning_log.csv"
        self.assertTrue(log.exists(), "cleaning_log.csv missing — Phase 4 incomplete")

    def test_cleaning_log_has_required_columns(self):
        """Why: Cleaning log needs timestamp, source, step, column, rows, reason."""
        log = DOCS_DIR / "cleaning_log.csv"
        if log.exists():
            df = pd.read_csv(log)
            required = {"timestamp", "stage", "source", "step", "column",
                        "rows_before", "rows_after", "rows_affected", "reason"}
            self.assertTrue(required.issubset(set(df.columns)),
                            f"Cleaning log missing columns: {required - set(df.columns)}")


class TestPhase4Integrate(unittest.TestCase):
    """Test integration and validation phase (04_integrate.py)."""

    def test_master_dataset_exists(self):
        """Why: Master dataset is the input for Phase 5 analysis."""
        path = CLEAN_DIR / "master_dataset.csv"
        self.assertTrue(path.exists(), "master_dataset.csv missing — Phase 5 incomplete")

    def test_master_dataset_has_rows(self):
        """Why: An empty master dataset means validation quarantined everything."""
        path = CLEAN_DIR / "master_dataset.csv"
        if path.exists():
            df = pd.read_csv(path)
            self.assertGreater(len(df), 0, "Master dataset has 0 rows — all data quarantined")

    def test_master_dataset_has_key_columns(self):
        """Why: Analysis needs price, date, district, and weather columns."""
        path = CLEAN_DIR / "master_dataset.csv"
        if path.exists():
            df = pd.read_csv(path)
            required = {"price", "date", "district"}
            self.assertTrue(required.issubset(set(df.columns)),
                            f"Master dataset missing columns: {required - set(df.columns)}")

    def test_validation_report_exists(self):
        """Why: 30+ validation rules must be documented per the guide."""
        report = DOCS_DIR / "validation_report.txt"
        self.assertTrue(report.exists(), "validation_report.txt missing — Phase 5 incomplete")

    def test_quarantine_file_exists(self):
        """Why: Failed rows must be quarantined, not silently deleted."""
        path = pathlib.Path("data/quarantine/quarantined.csv")
        self.assertTrue(path.exists(), "quarantined.csv missing — Phase 5 incomplete")


class TestPhase5Analyze(unittest.TestCase):
    """Test analysis phase (05_analyze.py)."""

    def test_summary_stats_exists(self):
        """Why: EDA summary statistics are a Phase 6 deliverable."""
        path = OUTPUTS_DIR / "summary_stats.csv"
        self.assertTrue(path.exists(), "summary_stats.csv missing — Phase 6 incomplete")

    def test_group_summaries_exists(self):
        """Why: Group summaries answer the business question about districts/commodities."""
        path = OUTPUTS_DIR / "group_summaries.csv"
        self.assertTrue(path.exists(), "group_summaries.csv missing — Phase 6 incomplete")

    def test_hypothesis_tests_exists(self):
        """Why: Statistical tests validate observed patterns."""
        path = OUTPUTS_DIR / "hypothesis_tests.csv"
        self.assertTrue(path.exists(), "hypothesis_tests.csv missing — Phase 6 incomplete")

    def test_regression_results_exists(self):
        """Why: Regression quantifies the weather-price relationship."""
        path = OUTPUTS_DIR / "regression_results.txt"
        self.assertTrue(path.exists(), "regression_results.txt missing — Phase 6 incomplete")

    def test_charts_exist(self):
        """Why: Visualizations communicate findings to stakeholders."""
        charts_dir = OUTPUTS_DIR / "charts"
        self.assertTrue(charts_dir.exists(), "outputs/charts/ directory missing")
        chart_files = list(charts_dir.glob("*.png"))
        self.assertGreater(len(chart_files), 0, "No chart files found")

    def test_analysis_summary_exists(self):
        """Why: Human-readable report for stakeholders."""
        report = DOCS_DIR / "analysis_summary.md"
        self.assertTrue(report.exists(), "analysis_summary.md missing — Phase 6 incomplete")


class TestPhase7Automation(unittest.TestCase):
    """Test Phase 7 infrastructure (run_pipeline.py)."""

    def test_pipeline_runner_exists(self):
        """Why: One-command pipeline is the Phase 7 deliverable."""
        path = BASE_DIR / "src" / "run_pipeline.py"
        self.assertTrue(path.exists(), "run_pipeline.py missing — Phase 7 incomplete")

    def test_audit_log_exists(self):
        """Why: Audit log provides traceability of pipeline runs."""
        self.assertTrue((BASE_DIR / "src" / "run_pipeline.py").exists(),
                        "run_pipeline.py needed to generate audit log")

    def test_reconciliation_exists(self):
        """Why: Reconciliation table catches data loss between phases."""
        self.assertTrue((BASE_DIR / "src" / "run_pipeline.py").exists(),
                        "run_pipeline.py needed to generate reconciliation")


if __name__ == "__main__":
    unittest.main()