# src/03_clean.py
"""
Stage 3 of the pipeline: clean each raw source.

Reads the latest file of each source from data/raw/, applies cleaning
rules, logs every change to docs/cleaning_log.csv, and writes partly
processed output to data/interim/.

Raw files are never modified. All fixes happen in code.
"""
import pandas as pd
import json
import glob
import os
import csv
import datetime
import pathlib

# Paths
RAW_DIR = "data/raw"
INTERIM_DIR = "data/interim"
CLEAN_DIR = "data/clean"
QUARANTINE_DIR = "data/quarantine"
DOCS_DIR = "docs"
CLEANING_LOG = pathlib.Path(DOCS_DIR) / "cleaning_log.csv"

# Make sure destination folders exist (they already do, but be safe)
for d in (INTERIM_DIR, CLEAN_DIR, QUARANTINE_DIR):
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)


def find_latest(pattern):
    """Find the most recently dated file matching a glob in data/raw/."""
    matches = glob.glob(os.path.join(RAW_DIR, pattern))
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def load_dataset(path):
    """Load a raw file into a DataFrame. Same logic as 02_profile.py."""
    if path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) == 2 and isinstance(data[1], list):
            return pd.json_normalize(data[1])
        if isinstance(data, dict) and "daily" in data:
            return pd.DataFrame(data["daily"])
        return pd.json_normalize(data)
    else:
        df = pd.read_csv(path, low_memory=False)
        if len(df) > 0 and str(df.iloc[0, 0]).startswith("#"):
            print(f"  Note: dropped HXL tag row from {os.path.basename(path)}")
            df = df.iloc[1:].reset_index(drop=True)
        return df


def log_cleaning(stage, source, step, column, rows_before, rows_after, reason):
    """Append one line to docs/cleaning_log.csv."""
    write_header = not CLEANING_LOG.exists() or CLEANING_LOG.stat().st_size == 0
    with open(CLEANING_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow([
                "timestamp", "stage", "source", "step", "column",
                "rows_before", "rows_after", "rows_affected", "reason",
            ])
        w.writerow([
            datetime.datetime.now().isoformat(timespec="seconds"),
            stage, source, step, column,
            rows_before, rows_after, rows_before - rows_after, reason,
        ])

def remove_duplicates(df, source, step_name="remove_duplicates"):
    """Remove exact duplicate rows and log the change."""
    rows_before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    rows_after = len(df)
    if rows_before != rows_after:
        log_cleaning(
            stage="clean", source=source,
            step=step_name, column="*",
            rows_before=rows_before, rows_after=rows_after,
            reason=f"Removed {rows_before - rows_after} exact duplicate rows",
        )
        print(f"  Removed {rows_before - rows_after} duplicate rows")
    return df


def cap_outliers_iqr(df, column, source, step_name="cap_outliers", k=1.5):
    """Cap outliers in a numeric column using the IQR method (winsorization)."""
    if column not in df.columns:
        return df
    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1
    lower = q1 - k * iqr
    upper = q3 + k * iqr
    outlier_mask = (df[column] < lower) | (df[column] > upper)
    n_outliers = int(outlier_mask.sum())
    if n_outliers > 0:
        df = df.copy()
        df.loc[df[column] < lower, column] = lower
        df.loc[df[column] > upper, column] = upper
        log_cleaning(
            stage="clean", source=source,
            step=step_name, column=column,
            rows_before=len(df), rows_after=len(df),
            reason=f"Capped {n_outliers} outliers to [{lower:.2f}, {upper:.2f}] using IQR k={k}",
        )
        print(f"  Capped {n_outliers} outliers in {column} to [{lower:.2f}, {upper:.2f}]")
    return df


def clean_owid():
    """Load the latest OWID cereal yield file, filter to Uganda only."""
    path = find_latest("owid_uganda_cereal_yield_*.csv")
    if path is None:
        print("  No OWID file found in data/raw/, skipping")
        return None

    print(f"\n[OWID] Loading {os.path.basename(path)}")
    df = load_dataset(path)

    # --- Fix 1: keep only Uganda ----------------------------------------
    rows_before = len(df)
    df = df[df["Entity"] == "Uganda"].reset_index(drop=True)
    rows_after = len(df)
    print(f"  Filtered to Uganda: {rows_before} -> {rows_after} rows")

    log_cleaning(
        stage="clean",
        source="owid",
        step="filter_to_uganda",
        column="Entity",
        rows_before=rows_before,
        rows_after=rows_after,
        reason="Raw file contained 180 countries; project is Uganda-only",
    )

    # --- Fix 2: remove duplicates ---------------------------------------
    df = remove_duplicates(df, "owid", "remove_duplicates")

    # --- Fix 3: rename columns for joins --------------------------------
    df = df.rename(columns={
        "Entity": "entity",
        "Code": "country_code",
        "Year": "year",
    })

    # --- Fix 4: convert types -------------------------------------------
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    if "cereal_yield" in df.columns:
        df["cereal_yield"] = pd.to_numeric(df["cereal_yield"], errors="coerce")
    elif df.columns[-1] != "year":
        # Last numeric column is likely the yield value
        yield_col = df.columns[-1]
        df = df.rename(columns={yield_col: "cereal_yield"})
        df["cereal_yield"] = pd.to_numeric(df["cereal_yield"], errors="coerce")

    print(f"  Shape after cleaning: {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print(df.to_string())

    # --- Save to data/interim/ ------------------------------------------
    out_path = pathlib.Path(INTERIM_DIR) / "owid_clean.csv"
    df.to_csv(out_path, index=False)
    print(f"  Saved: {out_path}")
    return df

def clean_worldbank():
    """Load the World Bank crop index, tidy it for later joins."""
    path = find_latest("worldbank_crop_index_*.json")
    if path is None:
        print("  No World Bank file found, skipping")
        return None

    print(f"\n[World Bank] Loading {os.path.basename(path)}")
    df = load_dataset(path)
    rows_before = len(df)

    # --- Fix 1: drop columns that are identical in every row -------------
    redundant_cols = [
        "unit", "obs_status", "decimal",
        "indicator.id", "indicator.value",
        "country.id", "country.value",
    ]
    df = df.drop(columns=[c for c in redundant_cols if c in df.columns])
    log_cleaning(
        stage="clean", source="worldbank",
        step="drop_redundant_columns", column="*",
        rows_before=rows_before, rows_after=len(df),
        reason="Columns constant across all rows add no information",
    )

    # --- Fix 2: convert date to integer year -----------------------------
    df["date"] = pd.to_numeric(df["date"], errors="coerce").astype("Int64")

    # --- Fix 3: convert value to float -----------------------------------
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    # --- Fix 4: rename to clearer names for joins ------------------------
    df = df.rename(columns={
        "countryiso3code": "country_code",
        "date": "year",
        "value": "crop_index",
    })

    # --- Fix 5: remove duplicates ----------------------------------------
    df = remove_duplicates(df, "worldbank", "remove_duplicates")

    # --- Fix 6: cap outliers in crop_index -------------------------------
    df = cap_outliers_iqr(df, "crop_index", "worldbank", "cap_outliers_crop_index")

    print(f"  Shape after cleaning: {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print(f"  Missing crop_index: {df['crop_index'].isna().sum()}")
    print(f"  Year range: {df['year'].min()} to {df['year'].max()}")
    print(df.head(3).to_string())

    # --- Save to data/interim/ -------------------------------------------
    out_path = pathlib.Path(INTERIM_DIR) / "worldbank_clean.csv"
    df.to_csv(out_path, index=False)
    print(f"  Saved: {out_path}")
    return df
def clean_weather():
    """Load the latest Open-Meteo weather file, parse dates, handle missing."""
    path = find_latest("weather_*.json")
    if path is None:
        print("  No weather file found in data/raw/, skipping")
        return None

    print(f"\n[Weather] Loading {os.path.basename(path)}")
    df = load_dataset(path)
    rows_before = len(df)

    # --- Fix 1: parse date column -----------------------------------------
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.rename(columns={"time": "date"})

    # --- Fix 2: rename weather columns for joins --------------------------
    rename_map = {}
    if "precipitation_sum" in df.columns:
        rename_map["precipitation_sum"] = "precipitation_mm"
    if "temperature_2m_mean" in df.columns:
        rename_map["temperature_2m_mean"] = "temperature_mean_c"
    if rename_map:
        df = df.rename(columns=rename_map)

    # --- Fix 3: remove duplicates -----------------------------------------
    df = remove_duplicates(df, "weather", "remove_duplicates")

    # --- Fix 4: cap outliers in numeric weather columns -------------------
    for col in ["precipitation_mm", "temperature_mean_c"]:
        if col in df.columns:
            df = cap_outliers_iqr(df, col, "weather", f"cap_outliers_{col}")

    # --- Fix 5: log missing values ----------------------------------------
    missing_total = int(df.isna().sum().sum())
    log_cleaning(
        stage="clean", source="weather",
        step="missing_value_report", column="*",
        rows_before=len(df), rows_after=len(df),
        reason=f"{missing_total} missing values across all columns after cleaning",
    )

    print(f"  Shape after cleaning: {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    if "date" in df.columns:
        print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
    print(df.head(3).to_string())

    # --- Save to data/interim/ -------------------------------------------
    out_path = pathlib.Path(INTERIM_DIR) / "weather_clean.csv"
    df.to_csv(out_path, index=False)
    print(f"  Saved: {out_path}")
    return df


def clean_wfp():
    """Load the latest WFP food prices file, handle HXL rows, parse dates."""
    path = find_latest("wfp_*.csv")
    if path is None:
        print("  No WFP file found in data/raw/, skipping")
        return None

    print(f"\n[WFP Food Prices] Loading {os.path.basename(path)}")
    df = load_dataset(path)
    rows_before = len(df)

    # --- Fix 1: parse date column -----------------------------------------
    date_col = None
    for col in df.columns:
        if "date" in col.lower():
            date_col = col
            break
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.rename(columns={date_col: "date"})

    # --- Fix 2: standardize column names ----------------------------------
    rename_map = {}
    for col in df.columns:
        cl = col.lower().strip()
        if cl in ("price", "prices"):
            rename_map[col] = "price"
        elif cl in ("commodity", "item", "product"):
            rename_map[col] = "commodity"
        elif cl in ("district", "adm1", "adm2", "market"):
            rename_map[col] = "district"
    if rename_map:
        df = df.rename(columns=rename_map)

    # --- Fix 3: convert price to numeric ----------------------------------
    if "price" in df.columns:
        df["price"] = pd.to_numeric(df["price"], errors="coerce")

    # --- Fix 4: remove duplicates -----------------------------------------
    df = remove_duplicates(df, "wfp", "remove_duplicates")

    # --- Fix 5: cap outliers in price -------------------------------------
    if "price" in df.columns:
        df = cap_outliers_iqr(df, "price", "wfp", "cap_outliers_price")

    print(f"  Shape after cleaning: {df.shape}")
    print(f"  Columns: {list(df.columns)}")
    print(df.head(3).to_string())

    # --- Save to data/interim/ -------------------------------------------
    out_path = pathlib.Path(INTERIM_DIR) / "wfp_clean.csv"
    df.to_csv(out_path, index=False)
    print(f"  Saved: {out_path}")
    return df


if __name__ == "__main__":
    print("03_clean.py - starting")
    clean_owid()
    clean_worldbank()
    clean_weather()
    clean_wfp()
    print("\nDone.")