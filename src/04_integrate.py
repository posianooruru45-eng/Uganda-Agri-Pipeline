# src/04_integrate.py
"""
Stage 5 of the pipeline: Integrate and validate.

Reads the 4 clean datasets from data/interim/, standardizes district names
and dates, joins them into a master dataset, applies 30+ validation rules,
quarantines failures, and writes:
  - data/clean/master_dataset.csv   (rows that pass all validation)
  - data/quarantine/quarantined.csv (rows that fail one or more rules)
  - docs/validation_report.txt      (summary of every rule and failures)

Raw/interim files are never modified. All fixes happen in code.
"""

import pandas as pd
import json
import glob
import os
import csv
import datetime
import pathlib

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
INTERIM_DIR = "data/interim"
CLEAN_DIR = "data/clean"
QUARANTINE_DIR = "data/quarantine"
DOCS_DIR = "docs"
MASTER_PATH = pathlib.Path(CLEAN_DIR) / "master_dataset.csv"
QUARANTINE_PATH = pathlib.Path(QUARANTINE_DIR) / "quarantined.csv"
VALIDATION_REPORT = pathlib.Path(DOCS_DIR) / "validation_report.txt"

# ---------------------------------------------------------------------------
# Ensure output folders exist
# ---------------------------------------------------------------------------
for d in (CLEAN_DIR, QUARANTINE_DIR, DOCS_DIR):
    pathlib.Path(d).mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Uganda district reference list (standard names used for mapping)
# ---------------------------------------------------------------------------
# These are the major districts covered by WFP food price data.
# Variants from raw sources are mapped to these canonical names.
UGANDA_DISTRICTS = [
    "Kampala", "Wakiso", "Mukono", "Jinja", "Iganga", "Tororo", "Mbale",
    "Soroti", "Lira", "Gulu", "Arua", "Mbarara", "Masaka", "Fort Portal",
    "Hoima", "Masindi", "Kabarole", "Kasese", "Busia", "Malaba",
    "Kabale", "Kisoro", "Ntungamo", "Bushenyi", "Rukungiri", "Kanungu",
    "Mubende", "Luwero", "Nakasongola", "Nakaseke", "Lyantonde",
    "Sembabule", "Rakai", "Kalangala", "Mpigi", "Butambala", "Gomba",
    "Bukomansimbi", "Kalungu", "Lwengo", "Kyotera", "Mityana", "Mubende",
    "Kyegegwa", "Kyenjojo", "Kamwenge", "Kibaale", "Kagadi", "Kakumiro",
    "Buliisa", "Kiryandongo", "Nakasongola", "Apac", "Oyam", "Kole",
    "Kwania", "Amolatar", "Dokolo", "Alebtong", "Otuke", "Katakwi",
    "Amuria", "Kumi", "Ngora", "Serere", "Pallisa", "Butaleja",
    "Namutumba", "Iganga", "Bugiri", "Namayingo", "Mayuge", "Buyende",
    "Kaliro", "Luuka", "Namutumba", "Bududa", "Bulambuli", "Sironko",
    "Manafwa", "Budaka", "Kibuku", "Butebo", "Pallisa",
    "Kikuube", "Kyegegwa", "Kamwenge", "Moyo", "Yumbe", "Adjumani",
    "Terego", "Koboko", "Isingiro", "Kiryandongo", "Lamwo", "Obongi",
    "Kapchorwa",
]

# Common variant mappings (raw value -> canonical district)
# Includes market names, admin names, and refugee settlements mapped to their host district
DISTRICT_ALIASES = {
    # Kampala markets/areas
    "kampala": "Kampala",
    "kampala central": "Kampala",
    "central kampala": "Kampala",
    "owino": "Kampala",
    "nakawa": "Kampala",
    "kisenyi": "Kampala",
    # Wakiso areas
    "wakiso": "Wakiso",
    "ennebbe": "Wakiso",
    "kasangati": "Wakiso",
    # Mukono
    "mukono": "Mukono",
    # Jinja
    "jinja": "Jinja",
    # Iganga
    "iganga": "Iganga",
    # Tororo
    "tororo": "Tororo",
    # Mbale
    "mbale": "Mbale",
    # Soroti
    "soroti": "Soroti",
    # Lira
    "lira": "Lira",
    "lira municipality": "Lira",
    # Gulu
    "gulu": "Gulu",
    # Arua
    "arua": "Arua",
    # Mbarara
    "mbarara": "Mbarara",
    # Masaka
    "masaka": "Masaka",
    # Fort Portal
    "fort portal": "Fort Portal",
    # Hoima
    "hoima": "Hoima",
    # Masindi
    "masindi": "Masindi",
    # Kabarole
    "kabarole": "Kabarole",
    # Kasese
    "kasese": "Kasese",
    # Busia
    "busia": "Busia",
    "malaba": "Busia",
    # Kabale
    "kabale": "Kabale",
    # Kisoro
    "kisoro": "Kisoro",
    # Ntungamo
    "ntungamo": "Ntungamo",
    # Bushenyi
    "bushenyi": "Bushenyi",
    # Rukungiri
    "rukungiri": "Rukungiri",
    # Kanungu
    "kanungu": "Kanungu",
    # Mubende
    "mubende": "Mubende",
    # Luwero
    "luwero": "Luwero",
    # Refugee settlements -> host districts
    "kyangwali (refugee settlement)": "Kikuube",
    "kyaka ii (refugee settlement)": "Kyegegwa",
    "rwamwanja (refugee settlement)": "Kamwenge",
    "palorinya (refugee settlement)": "Moyo",
    "bidibidi (refugee settlement)": "Yumbe",
    "adjumani (refugee settlement)": "Adjumani",
    "imvepi (refugee settlement)": "Terego",
    "lobule (refugee settlement)": "Koboko",
    "nakivale (refugee settlement)": "Isingiro",
    "orucheinga (refugee settlement)": "Isingiro",
    "kiryandongo (refugee settlement)": "Kiryandongo",
    "palabek (refugee settlement)": "Lamwo",
    "rhino camp (refugee settlement)": "Terego",
    # Admin-level names
    "terege": "Terego",
    "bukanga": "Iganga",
    "buhaguzi": "Kikuube",
    "kibale": "Kibaale",
    "obongi": "Obongi",
    "aringa": "Yumbe",
    "kapchorwa": "Kapchorwa",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_latest(pattern, directory=INTERIM_DIR):
    """Find the most recently modified file matching a glob."""
    matches = glob.glob(os.path.join(directory, pattern))
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def load_dataset(path):
    """Load a cleaned interim file into a DataFrame."""
    if path is None:
        return None
    return pd.read_csv(path, low_memory=False)


def standardize_district_name(raw_value):
    """Map a raw district name to a canonical Uganda district name.

    Returns the canonical name, or None if no match is found.
    """
    if pd.isna(raw_value):
        return None
    key = str(raw_value).strip().lower()
    if key in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[key]
    # Try title-case direct match
    titled = str(raw_value).strip().title()
    if titled in UGANDA_DISTRICTS:
        return titled
    return None


# ---------------------------------------------------------------------------
# 5.1 Load clean interim datasets
# ---------------------------------------------------------------------------

def load_clean_data():
    """Load all four clean interim datasets."""
    datasets = {}

    wb_path = find_latest("worldbank_clean.csv")
    datasets["worldbank"] = load_dataset(wb_path) if wb_path else None
    print(f"[Load] World Bank: {wb_path}")

    owid_path = find_latest("owid_clean.csv")
    datasets["owid"] = load_dataset(owid_path) if owid_path else None
    print(f"[Load] OWID: {owid_path}")

    weather_path = find_latest("weather_clean.csv")
    datasets["weather"] = load_dataset(weather_path) if weather_path else None
    print(f"[Load] Weather: {weather_path}")

    wfp_path = find_latest("wfp_clean.csv")
    datasets["wfp"] = load_dataset(wfp_path) if wfp_path else None
    print(f"[Load] WFP: {wfp_path}")

    return datasets


# ---------------------------------------------------------------------------
# 5.2 Standardize district names & dates
# ---------------------------------------------------------------------------

def standardize_datasets(datasets):
    """Standardize district names and date columns across all datasets."""
    # --- World Bank: national-level, yearly. No district column needed. ---
    if datasets["worldbank"] is not None:
        df = datasets["worldbank"]
        if "year" in df.columns:
            df["year"] = pd.to_numeric(df["year"], errors="coerce")
        datasets["worldbank"] = df

    # --- OWID: national-level, yearly. ---
    if datasets["owid"] is not None:
        df = datasets["owid"]
        if "year" in df.columns:
            df["year"] = pd.to_numeric(df["year"], errors="coerce")
        # Ensure cereal_yield exists
        if "cereal_yield" not in df.columns and df.columns[-1] not in ("year", "country_code", "entity"):
            df = df.rename(columns={df.columns[-1]: "cereal_yield"})
        datasets["owid"] = df

    # --- Weather: Kampala only, daily dates. ---
    if datasets["weather"] is not None:
        df = datasets["weather"]
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["district"] = "Kampala"  # Weather station is Kampala
        datasets["weather"] = df

    # --- WFP: market-level, daily dates, district column. ---
    if datasets["wfp"] is not None:
        df = datasets["wfp"]
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        # Standardize district names
        if "district" in df.columns:
            df["district"] = df["district"].apply(standardize_district_name)
        elif "admin2" in df.columns:
            df["district"] = df["admin2"].apply(standardize_district_name)
        elif "market" in df.columns:
            # Fallback: use market as district proxy
            df["district"] = df["market"].apply(standardize_district_name)
        datasets["wfp"] = df

    return datasets


# ---------------------------------------------------------------------------
# 5.3 Add year column for joining yearly national data
# ---------------------------------------------------------------------------

def add_year_column(datasets):
    """Extract year from date columns so yearly sources can join."""
    for name in ("weather", "wfp"):
        df = datasets[name]
        if df is not None and "date" in df.columns:
            df["year"] = df["date"].dt.year
            datasets[name] = df
    return datasets


# ---------------------------------------------------------------------------
# 5.4 Join sources into master dataset
# ---------------------------------------------------------------------------

def join_sources(datasets):
    """
    Build the master dataset.

    Grain: WFP market-day-commodity row (most granular).
    - WFP rows keep district, date, commodity, price.
    - Weather joins on date (Kampala weather applied to all rows that date).
    - World Bank crop_index joins on year.
    - OWID cereal_yield joins on year.
    """
    wfp = datasets["wfp"]
    if wfp is None:
        raise ValueError("WFP dataset is required for the master dataset.")

    master = wfp.copy()

    # --- Join weather on date ---
    weather = datasets["weather"]
    if weather is not None:
        weather_cols = ["date", "precipitation_mm", "temperature_mean_c"]
        weather_cols = [c for c in weather_cols if c in weather.columns]
        master = master.merge(
            weather[weather_cols],
            on="date",
            how="left",
            suffixes=("", "_weather"),
        )

    # --- Join World Bank crop_index on year ---
    wb = datasets["worldbank"]
    if wb is not None:
        wb_cols = ["year", "crop_index"]
        wb_cols = [c for c in wb_cols if c in wb.columns]
        master = master.merge(
            wb[wb_cols],
            on="year",
            how="left",
            suffixes=("", "_wb"),
        )

    # --- Join OWID cereal_yield on year ---
    owid = datasets["owid"]
    if owid is not None:
        owid_cols = ["year", "cereal_yield"]
        owid_cols = [c for c in owid_cols if c in owid.columns]
        master = master.merge(
            owid[owid_cols],
            on="year",
            how="left",
            suffixes=("", "_owid"),
        )

    return master


# ---------------------------------------------------------------------------
# 5.5 Validation rules (30+)
# ---------------------------------------------------------------------------

def build_validation_rules():
    """Define 30+ validation rules across categories."""
    rules = []

    # ---- Category: Completeness (rules 1-6) ----
    rules.append({
        "id": "V01", "category": "Completeness",
        "description": "price must not be null",
        "check": lambda df: df["price"].notna() if "price" in df.columns else pd.Series([True] * len(df)),
        "severity": "Critical",
    })
    rules.append({
        "id": "V02", "category": "Completeness",
        "description": "date must not be null",
        "check": lambda df: df["date"].notna() if "date" in df.columns else pd.Series([True] * len(df)),
        "severity": "Critical",
    })
    rules.append({
        "id": "V03", "category": "Completeness",
        "description": "district must not be null",
        "check": lambda df: df["district"].notna() if "district" in df.columns else pd.Series([True] * len(df)),
        "severity": "Critical",
    })
    rules.append({
        "id": "V04", "category": "Completeness",
        "description": "commodity must not be null",
        "check": lambda df: df["commodity"].notna() if "commodity" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V05", "category": "Completeness",
        "description": "precipitation_mm must not be null",
        "check": lambda df: df["precipitation_mm"].notna() if "precipitation_mm" in df.columns else pd.Series([True] * len(df)),
        "severity": "Minor",
    })
    rules.append({
        "id": "V06", "category": "Completeness",
        "description": "temperature_mean_c must not be null",
        "check": lambda df: df["temperature_mean_c"].notna() if "temperature_mean_c" in df.columns else pd.Series([True] * len(df)),
        "severity": "Minor",
    })

    # ---- Category: Uniqueness (rules 7-8) ----
    # NOTE: market_id and commodity_id legitimately repeat across dates,
    # so we do NOT check global uniqueness for those fields.
    rules.append({
        "id": "V07", "category": "Uniqueness",
        "description": "No duplicate WFP market-date-commodity rows",
        "check": lambda df: ~df.duplicated(subset=["date", "district", "commodity"], keep=False) if all(c in df.columns for c in ["date", "district", "commodity"]) else pd.Series([True] * len(df)),
        "severity": "Critical",
    })
    rules.append({
        "id": "V08", "category": "Uniqueness",
        "description": "No duplicate WFP market-date-commodity-priceflag rows",
        "check": lambda df: ~df.duplicated(subset=["date", "district", "commodity", "priceflag"], keep=False) if all(c in df.columns for c in ["date", "district", "commodity", "priceflag"]) else pd.Series([True] * len(df)),
        "severity": "Major",
    })

    # ---- Category: Range/Validity (rules 10-18) ----
    rules.append({
        "id": "V10", "category": "Range",
        "description": "price must be >= 0",
        "check": lambda df: df["price"] >= 0 if "price" in df.columns else pd.Series([True] * len(df)),
        "severity": "Critical",
    })
    rules.append({
        "id": "V11", "category": "Range",
        "description": "price must be <= 100,000 UGX (upper sanity bound)",
        "check": lambda df: df["price"] <= 100000 if "price" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V12", "category": "Range",
        "description": "precipitation_mm must be >= 0",
        "check": lambda df: df["precipitation_mm"] >= 0 if "precipitation_mm" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V13", "category": "Range",
        "description": "precipitation_mm must be <= 500 mm/day (physical upper bound)",
        "check": lambda df: df["precipitation_mm"] <= 500 if "precipitation_mm" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V14", "category": "Range",
        "description": "temperature_mean_c must be between 10 and 40 (Uganda climate range)",
        "check": lambda df: df["temperature_mean_c"].between(10, 40) if "temperature_mean_c" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V15", "category": "Range",
        "description": "crop_index must be >= 0 if present",
        "check": lambda df: df["crop_index"].isna() | (df["crop_index"] >= 0) if "crop_index" in df.columns else pd.Series([True] * len(df)),
        "severity": "Minor",
    })
    rules.append({
        "id": "V16", "category": "Range",
        "description": "cereal_yield must be >= 0 if present",
        "check": lambda df: df["cereal_yield"].isna() | (df["cereal_yield"] >= 0) if "cereal_yield" in df.columns else pd.Series([True] * len(df)),
        "severity": "Minor",
    })
    rules.append({
        "id": "V17", "category": "Range",
        "description": "latitude must be between -2 and 5 (Uganda bounds)",
        "check": lambda df: df["latitude"].between(-2, 5) if "latitude" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V18", "category": "Range",
        "description": "longitude must be between 29 and 35 (Uganda bounds)",
        "check": lambda df: df["longitude"].between(29, 35) if "longitude" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    # ---- Category: Referential Integrity (rules 19-23) ----
    rules.append({
        "id": "V19", "category": "Referential Integrity",
        "description": "district must be a recognized Uganda district",
        "check": lambda df: df["district"].isin(UGANDA_DISTRICTS) if "district" in df.columns else pd.Series([True] * len(df)),
        "severity": "Critical",
    })
    rules.append({
        "id": "V20", "category": "Referential Integrity",
        "description": "commodity must not be empty string",
        "check": lambda df: df["commodity"].astype(str).str.strip().ne("") if "commodity" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V21", "category": "Referential Integrity",
        "description": "currency must be UGX or USD",
        "check": lambda df: df["currency"].isin(["UGX", "USD"]) if "currency" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V22", "category": "Referential Integrity",
        "description": "unit must not be null",
        "check": lambda df: df["unit"].notna() if "unit" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V23", "category": "Referential Integrity",
        "description": "category must not be null",
        "check": lambda df: df["category"].notna() if "category" in df.columns else pd.Series([True] * len(df)),
        "severity": "Minor",
    })

    # ---- Category: Cross-Field Consistency (rules 24-29) ----
    rules.append({
        "id": "V24", "category": "Cross-Field",
        "description": "usdprice must be >= 0 if present",
        "check": lambda df: df["usdprice"].isna() | (df["usdprice"] >= 0) if "usdprice" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V25", "category": "Cross-Field",
        "description": "priceflag must be 'actual' or 'provisional'",
        "check": lambda df: df["priceflag"].isin(["actual", "provisional"]) if "priceflag" in df.columns else pd.Series([True] * len(df)),
        "severity": "Minor",
    })
    rules.append({
        "id": "V26", "category": "Cross-Field",
        "description": "pricetype must be 'Wholesale' or 'Retail'",
        "check": lambda df: df["pricetype"].isin(["Wholesale", "Retail"]) if "pricetype" in df.columns else pd.Series([True] * len(df)),
        "severity": "Minor",
    })
    rules.append({
        "id": "V27", "category": "Cross-Field",
        "description": "If currency is USD, usdprice should roughly equal price",
        "check": lambda df: (df["currency"] != "USD") | (df["usdprice"].isna()) | (abs(df["price"] - df["usdprice"]) < 1000) if all(c in df.columns for c in ["currency", "price", "usdprice"]) else pd.Series([True] * len(df)),
        "severity": "Minor",
    })
    rules.append({
        "id": "V28", "category": "Cross-Field",
        "description": "market_id and market must not both be null",
        "check": lambda df: df["market_id"].notna() | df["market"].notna() if all(c in df.columns for c in ["market_id", "market"]) else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V29", "category": "Cross-Field",
        "description": "commodity_id and commodity must not both be null",
        "check": lambda df: df["commodity_id"].notna() | df["commodity"].notna() if all(c in df.columns for c in ["commodity_id", "commodity"]) else pd.Series([True] * len(df)),
        "severity": "Major",
    })

    # ---- Category: Temporal Consistency (rules 30-33) ----
    rules.append({
        "id": "V30", "category": "Temporal",
        "description": "date must be within project period 2015-01-01 to 2024-12-31",
        "check": lambda df: df["date"].between(pd.Timestamp("2015-01-01"), pd.Timestamp("2024-12-31")) if "date" in df.columns else pd.Series([True] * len(df)),
        "severity": "Critical",
    })
    rules.append({
        "id": "V31", "category": "Temporal",
        "description": "year must be between 2015 and 2024 if present",
        "check": lambda df: df["year"].isna() | df["year"].between(2015, 2024) if "year" in df.columns else pd.Series([True] * len(df)),
        "severity": "Major",
    })
    rules.append({
        "id": "V32", "category": "Temporal",
        "description": "No future dates (after today)",
        "check": lambda df: df["date"] <= pd.Timestamp.now() if "date" in df.columns else pd.Series([True] * len(df)),
        "severity": "Critical",
    })
    rules.append({
        "id": "V33", "category": "Temporal",
        "description": "date must not be before 1900",
        "check": lambda df: df["date"] >= pd.Timestamp("1900-01-01") if "date" in df.columns else pd.Series([True] * len(df)),
        "severity": "Minor",
    })

    return rules


# ---------------------------------------------------------------------------
# 5.6 Apply validation & quarantine failures
# ---------------------------------------------------------------------------

def apply_validation(df, rules):
    """Run every validation rule; return (pass_df, fail_df, rule_results)."""
    fail_mask = pd.Series([False] * len(df), index=df.index)
    rule_results = []

    for rule in rules:
        try:
            passed = rule["check"](df)
            passed = pd.Series(passed, index=df.index).fillna(False)
            rule_failures = int((~passed).sum())
            fail_mask = fail_mask | (~passed)

            rule_results.append({
                "id": rule["id"],
                "category": rule["category"],
                "description": rule["description"],
                "severity": rule["severity"],
                "failures": rule_failures,
                "passed": int(passed.sum()),
                "total": len(df),
            })
        except Exception as e:
            rule_results.append({
                "id": rule["id"],
                "category": rule["category"],
                "description": rule["description"],
                "severity": rule["severity"],
                "failures": -1,
                "passed": -1,
                "total": len(df),
                "error": str(e),
            })

    pass_df = df[~fail_mask].copy()
    fail_df = df[fail_mask].copy()

    return pass_df, fail_df, rule_results


# ---------------------------------------------------------------------------
# 5.7 Write outputs
# ---------------------------------------------------------------------------

def write_master_dataset(df):
    """Save the validated master dataset."""
    pathlib.Path(CLEAN_DIR).mkdir(parents=True, exist_ok=True)
    df.to_csv(MASTER_PATH, index=False)
    print(f"[Save] Master dataset: {MASTER_PATH} ({len(df)} rows)")
    return MASTER_PATH


def write_quarantined(df):
    """Save quarantined (failed) rows."""
    pathlib.Path(QUARANTINE_DIR).mkdir(parents=True, exist_ok=True)
    if len(df) > 0:
        df.to_csv(QUARANTINE_PATH, index=False)
        print(f"[Save] Quarantined: {QUARANTINE_PATH} ({len(df)} rows)")
    else:
        df.to_csv(QUARANTINE_PATH, index=False)
        print(f"[Save] Quarantined: {QUARANTINE_PATH} (0 rows)")
    return QUARANTINE_PATH


def write_validation_report(rule_results, total_rows, pass_rows, fail_rows):
    """Write a human-readable validation report."""
    pathlib.Path(DOCS_DIR).mkdir(parents=True, exist_ok=True)
    report_lines = []
    report_lines.append("VALIDATION REPORT — Phase 5: Integrate and Validate")
    report_lines.append("=" * 70)
    report_lines.append(f"Total rows evaluated: {total_rows}")
    report_lines.append(f"Rows passed all rules: {pass_rows}")
    report_lines.append(f"Rows quarantined (failed >= 1 rule): {fail_rows}")
    report_lines.append(f"Pass rate: {pass_rows / total_rows * 100:.1f}%" if total_rows > 0 else "N/A")
    report_lines.append("")
    report_lines.append(f"{'Rule':<6} {'Category':<18} {'Severity':<10} {'Failures':>10}  Description")
    report_lines.append("-" * 70)

    for r in rule_results:
        status = "ERROR" if r["failures"] < 0 else f"{r['failures']}"
        report_lines.append(
            f"{r['id']:<6} {r['category']:<18} {r['severity']:<10} {status:>10}  {r['description']}"
        )
        if "error" in r:
            report_lines.append(f"           Error: {r['error']}")

    report_lines.append("")
    report_lines.append("=" * 70)
    report_lines.append("End of validation report.")

    report_text = "\n".join(report_lines)
    with open(VALIDATION_REPORT, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"[Save] Validation report: {VALIDATION_REPORT}")
    return VALIDATION_REPORT


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("04_integrate.py - starting Phase 5: Integrate and Validate\n")

    # 5.1 Load
    datasets = load_clean_data()

    # 5.2 Standardize
    datasets = standardize_datasets(datasets)

    # 5.3 Add year column
    datasets = add_year_column(datasets)

    # 5.4 Join
    master = join_sources(datasets)
    print(f"\n[Join] Master dataset shape: {master.shape}")
    print(f"[Join] Columns: {list(master.columns)}\n")

    # 5.5-5.6 Validate
    rules = build_validation_rules()
    print(f"[Validate] Running {len(rules)} validation rules...\n")
    pass_df, fail_df, rule_results = apply_validation(master, rules)

    # 5.7 Write outputs
    write_master_dataset(pass_df)
    write_quarantined(fail_df)
    write_validation_report(rule_results, len(master), len(pass_df), len(fail_df))

    print("\n04_integrate.py - Done.")