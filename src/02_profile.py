import pandas as pd
import json
import glob
import os

RAW_DIR = "data/raw"

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
    print("=" * 70)
    print(f"DATASET: {name}")
    print(f"File: {path}")
    print("=" * 70)

    try:
        df = load_dataset(path)
    except Exception as e:
        print(f"Could not load this file: {e}")
        return None

    print(f"\nShape: {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"\nColumns and dtypes:")
    print(df.dtypes)

    print(f"\nMissing values per column:")
    missing = df.isna().sum()
    missing_pct = (missing / len(df) * 100).round(1)
    missing_summary = pd.DataFrame({"missing_count": missing, "missing_pct": missing_pct})
    print(missing_summary[missing_summary["missing_count"] > 0])

    print(f"\nDuplicate rows: {df.duplicated().sum()}")

    print(f"\nSummary stats (numeric columns):")
    print(df.describe())

    print(f"\nUnique value counts (first 10 columns):")
    for col in df.columns[:10]:
        print(f"  {col}: {df[col].nunique()} unique values")

    print("\n")
    return df

if __name__ == "__main__":
    datasets = {
        "World Bank": find_latest("worldbank_*.json"),
        "Weather": find_latest("weather_*.json"),
        "OWID": find_latest("owid_*.csv"),
        "WFP Food Prices": find_latest("wfp_*.csv"),
    }

    for name, path in datasets.items():
        if path is None:
            print(f"No file found for {name}, skipping\n")
            continue
        profile_dataset(name, path)