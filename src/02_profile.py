import pandas as pd
import json
import glob
import os
import pathlib
import csv

RAW_DIR = "data/raw"
REPORT_DIR = pathlib.Path("docs")

def find_latest(pattern):
    """Find the most recently modified file matching a glob pattern in data/raw/."""
    matches = glob.glob(os.path.join(RAW_DIR, pattern))
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)

def load_dataset(path):
    """Load a file as a DataFrame, handling each source's quirks."""
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # World Bank API returns [metadata, records]
        if isinstance(data, list) and len(data) == 2 and isinstance(data[1], list):
            return pd.json_normalize(data[1])
        # Open-Meteo returns {"daily": {"time": [...], "precipitation_sum": [...], ...}}
        if isinstance(data, dict) and "daily" in data:
            return pd.DataFrame(data["daily"])
        return pd.json_normalize(data)
    else:
        df = pd.read_csv(path, low_memory=False)
        # HDX files often have an HXL tag row (#date, #adm1+name...) under the header
        if len(df) > 0 and str(df.iloc[0, 0]).startswith("#"):
            print("  Note: dropped HXL tag row (row 2) from this file")
            df = df.iloc[1:].reset_index(drop=True)
            for col in df.columns:
                try:
                    df[col] = pd.to_numeric(df[col])
                except (ValueError, TypeError):
                    pass  # leave text columns (district, commodity, etc.) as they are
        return df

def profile_dataset(name, path):
    """Profile a single dataset and return (df, summary_dict)."""
    report_lines = []
    report_lines.append("=" * 70)
    report_lines.append(f"DATASET: {name}")
    report_lines.append(f"File: {path}")
    report_lines.append("=" * 70)

    try:
        df = load_dataset(path)
    except Exception as e:
        report_lines.append(f"Could not load this file: {e}")
        return None, {"name": name, "path": path, "error": str(e)}

    report_lines.append(f"\nShape: {df.shape[0]} rows x {df.shape[1]} columns")
    report_lines.append(f"\nColumns and dtypes:")
    report_lines.append(str(df.dtypes))

    missing = df.isna().sum()
    missing_pct = (missing / len(df) * 100).round(1)
    missing_summary = pd.DataFrame({"missing_count": missing, "missing_pct": missing_pct})
    missing_issues = missing_summary[missing_summary["missing_count"] > 0]
    report_lines.append(f"\nMissing values per column:")
    report_lines.append(str(missing_issues))

    dup_count = int(df.duplicated().sum())
    report_lines.append(f"\nDuplicate rows: {dup_count}")

    report_lines.append(f"\nSummary stats (numeric columns):")
    report_lines.append(str(df.describe()))

    report_lines.append(f"\nUnique value counts (first 10 columns):")
    for col in df.columns[:10]:
        report_lines.append(f"  {col}: {df[col].nunique()} unique values")

    report_lines.append("\n")

    report_text = "\n".join(report_lines)
    print(report_text)

    summary = {
        "name": name,
        "path": path,
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "dtypes": df.dtypes.astype(str).to_dict(),
        "missing_count": missing.to_dict(),
        "missing_pct": missing_pct.to_dict(),
        "duplicate_rows": dup_count,
        "describe": df.describe().to_dict() if len(df.select_dtypes(include="number").columns) > 0 else {},
        "unique_counts": {col: int(df[col].nunique()) for col in df.columns[:10]},
        "report_text": report_text,
    }
    return df, summary


def write_profiling_report(all_summaries):
    """Write the combined profiling report to docs/profiling_report.txt."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / "profiling_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("DATA PROFILING REPORT\n")
        f.write("=" * 70 + "\n\n")
        for s in all_summaries:
            f.write(s["report_text"])
    print(f"\nProfiling report saved to {report_path}")


def write_issues_list(all_summaries):
    """Write a list of all data quality issues to docs/issues.csv."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    issues_path = REPORT_DIR / "issues.csv"
    with open(issues_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dataset", "issue_type", "column", "size", "description"])
        for s in all_summaries:
            name = s["name"]
            # Missing value issues
            for col, cnt in s["missing_count"].items():
                if cnt > 0:
                    w.writerow([
                        name, "missing_values", col, int(cnt),
                        f"{s['missing_pct'][col]}% missing",
                    ])
            # Duplicate row issues
            if s["duplicate_rows"] > 0:
                w.writerow([
                    name, "duplicate_rows", "*", s["duplicate_rows"],
                    "Exact duplicate rows found",
                ])
    print(f"Issues list saved to {issues_path}")

if __name__ == "__main__":
    datasets = {
        "World Bank": find_latest("worldbank_*.json"),
        "Weather": find_latest("weather_*.json"),
        "OWID": find_latest("owid_*.csv"),
        "WFP Food Prices": find_latest("wfp_*.csv"),
    }

    all_summaries = []
    for name, path in datasets.items():
        if path is None:
            print(f"No file found for {name}, skipping\n")
            continue
        df, summary = profile_dataset(name, path)
        if summary is not None:
            all_summaries.append(summary)

    write_profiling_report(all_summaries)
    write_issues_list(all_summaries)