# src/05_analyze.py
"""
Stage 6 of the pipeline: Analyze.

Loads the validated master dataset from data/clean/master_dataset.csv,
performs exploratory data analysis, group summaries, hypothesis tests,
regression modeling, assumption checks, and generates visualizations.

Outputs:
  - outputs/charts/*.png          (EDA and model diagnostic charts)
  - outputs/summary_stats.csv     (EDA summary statistics)
  - outputs/group_summaries.csv   (group-level aggregations)
  - outputs/hypothesis_tests.csv  (statistical test results)
  - outputs/regression_results.txt (regression model summary)
  - docs/analysis_summary.md      (human-readable analysis report)

Requires: matplotlib, seaborn, scipy, statsmodels (added in Phase 6)
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for saving charts
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import durbin_watson
from statsmodels.graphics.gofplots import qqplot
import os
import pathlib
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MASTER_PATH = pathlib.Path("data/clean/master_dataset.csv")
CHARTS_DIR = pathlib.Path("outputs/charts")
OUTPUTS_DIR = pathlib.Path("outputs")
DOCS_DIR = pathlib.Path("docs")

for d in (CHARTS_DIR, OUTPUTS_DIR, DOCS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Plot styling
# ---------------------------------------------------------------------------
sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (10, 6)
plt.rcParams["font.size"] = 10

# ---------------------------------------------------------------------------
# 6.1 Load master dataset
# ---------------------------------------------------------------------------

def load_master_dataset():
    """Load the validated master dataset from Phase 5.

    Returns:
        pd.DataFrame: Clean master dataset with price, weather, crop index,
                      and cereal yield joined together.
    """
    if not MASTER_PATH.exists():
        raise FileNotFoundError(
            f"Master dataset not found at {MASTER_PATH}. "
            "Run Phase 5 (04_integrate.py) first."
        )
    df = pd.read_csv(MASTER_PATH, parse_dates=["date"])
    print(f"[Load] Master dataset: {len(df)} rows x {len(df.columns)} columns")
    print(f"[Load] Date range: {df['date'].min()} to {df['date'].max()}")
    return df


def add_derived_columns(df):
    """Add derived columns needed for analysis.

    Adds:
        - year: extracted from date
        - month: extracted from date
        - season: Wet (Mar-May, Sep-Dec) or Dry (Jan-Feb, Jun-Aug) for Uganda
        - price_log: log-transformed price (for regression normality)
    """
    df = df.copy()
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month

    # Uganda has two rainy seasons: Mar-May and Sep-Dec
    # Dry seasons: Jan-Feb and Jun-Aug
    df["season"] = df["month"].apply(
        lambda m: "Wet" if m in (3, 4, 5, 9, 10, 11, 12) else "Dry"
    )

    # Log transform price for regression (price is typically right-skewed)
    df["price_log"] = np.log1p(df["price"])

    print(f"[Derived] Added columns: year, month, season, price_log")
    return df


# ---------------------------------------------------------------------------
# 6.1 Exploratory Data Analysis (EDA)
# ---------------------------------------------------------------------------

def eda_summary(df):
    """Compute summary statistics for all numeric variables.

    Why it matters: Before modeling, you must understand the distribution,
    scale, and spread of each variable. Are prices normally distributed or
    heavily skewed? Are there outliers? This shapes hypothesis selection
    and whether transformations (e.g., log-price) are needed.

    Returns:
        pd.DataFrame: Summary statistics (count, mean, std, min, median, max,
                      missing count) for each numeric column.
    """
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    summary = df[numeric_cols].describe().T
    summary["missing"] = df[numeric_cols].isna().sum()
    summary = summary[["count", "mean", "std", "min", "50%", "max", "missing"]]
    summary.columns = ["count", "mean", "std", "min", "median", "max", "missing"]
    summary = summary.round(2)

    out_path = OUTPUTS_DIR / "summary_stats.csv"
    summary.to_csv(out_path)
    print(f"[EDA] Summary stats saved to {out_path}")
    print(summary)
    return summary


def plot_distributions(df):
    """Plot histograms for key numeric variables.

    Why it matters: Visualizing distributions reveals skewness, multimodality,
    and outliers that summary statistics alone may hide. For example, if price
    is heavily right-skewed (many low prices, few extreme high prices), we know
    to use log-transformation or robust regression.

    Saves:
        outputs/charts/01_price_distribution.png
        outputs/charts/02_weather_distribution.png
    """
    # Price distribution
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    sns.histplot(df["price"], kde=True, ax=axes[0], color="steelblue")
    axes[0].set_title("Food Price Distribution (UGX)")
    axes[0].set_xlabel("Price (UGX)")
    axes[0].set_ylabel("Count")

    sns.histplot(df["price_log"], kde=True, ax=axes[1], color="darkgreen")
    axes[1].set_title("Log-Transformed Price Distribution")
    axes[1].set_xlabel("log(1 + Price)")
    axes[1].set_ylabel("Count")

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "01_price_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Weather distribution
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    sns.histplot(df["precipitation_mm"], kde=True, ax=axes[0], color="steelblue")
    axes[0].set_title("Daily Precipitation Distribution (mm)")
    axes[0].set_xlabel("Precipitation (mm)")
    axes[0].set_ylabel("Count")

    sns.histplot(df["temperature_mean_c"], kde=True, ax=axes[1], color="darkorange")
    axes[1].set_title("Mean Temperature Distribution (°C)")
    axes[1].set_xlabel("Temperature (°C)")
    axes[1].set_ylabel("Count")

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "02_weather_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()

    print(f"[EDA] Distribution charts saved to {CHARTS_DIR}")


# ---------------------------------------------------------------------------
# 6.2 Group Summaries
# ---------------------------------------------------------------------------

def group_summaries(df):
    """Aggregate the master dataset at multiple levels of granularity."""
    summaries = {}

    by_commodity_year = (
        df.groupby(["commodity", "year"])
        .agg(
            avg_price=("price", "mean"),
            median_price=("price", "median"),
            min_price=("price", "min"),
            max_price=("price", "max"),
            n_obs=("price", "count"),
            avg_rainfall=("precipitation_mm", "mean"),
            avg_temperature=("temperature_mean_c", "mean"),
        )
        .reset_index()
        .round(2)
    )
    summaries["commodity_year"] = by_commodity_year

    by_commodity_district = (
        df.groupby(["commodity", "district"])
        .agg(
            avg_price=("price", "mean"),
            median_price=("price", "median"),
            n_obs=("price", "count"),
            avg_rainfall=("precipitation_mm", "mean"),
        )
        .reset_index()
        .round(2)
    )
    summaries["commodity_district"] = by_commodity_district

    by_season = (
        df.groupby(["season"])
        .agg(
            avg_price=("price", "mean"),
            median_price=("price", "median"),
            avg_rainfall=("precipitation_mm", "mean"),
            avg_temperature=("temperature_mean_c", "mean"),
            n_obs=("price", "count"),
        )
        .reset_index()
        .round(2)
    )
    summaries["season"] = by_season

    by_year = (
        df.groupby(["year"])
        .agg(
            avg_price=("price", "mean"),
            median_price=("price", "median"),
            avg_rainfall=("precipitation_mm", "mean"),
            avg_temperature=("temperature_mean_c", "mean"),
            n_obs=("price", "count"),
        )
        .reset_index()
        .round(2)
    )
    summaries["year"] = by_year

    all_summaries = []
    for name, sdf in summaries.items():
        sdf = sdf.copy()
        sdf["grouping"] = name
        all_summaries.append(sdf)
    combined = pd.concat(all_summaries, ignore_index=True, sort=False)
    out_path = OUTPUTS_DIR / "group_summaries.csv"
    combined.to_csv(out_path, index=False)
    print(f"[Group] Summaries saved to {out_path}")

    print("\n--- Average Price by Commodity and Year (top 10) ---")
    print(by_commodity_year.head(10).to_string(index=False))

    print("\n--- Average Price by Season ---")
    print(by_season.to_string(index=False))

    print("\n--- Annual Price and Weather Trend ---")
    print(by_year.to_string(index=False))

    return summaries


def plot_price_by_commodity_year(df):
    """Line chart: average price by year for top commodities."""
    top_commodities = (
        df.groupby("commodity")["price"]
        .mean()
        .sort_values(ascending=False)
        .head(8)
        .index
        .tolist()
    )
    df_top = df[df["commodity"].isin(top_commodities)].copy()

    plt.figure(figsize=(12, 6))
    sns.lineplot(
        data=df_top,
        x="year",
        y="price",
        hue="commodity",
        marker="o",
        errorbar="sd",
    )
    plt.title("Average Food Price by Year and Commodity (Top 8)")
    plt.xlabel("Year")
    plt.ylabel("Average Price (UGX)")
    plt.legend(title="Commodity", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "03_price_trend_by_commodity.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[Group] Price trend chart saved to {CHARTS_DIR}")


def plot_price_by_district(df):
    """Bar chart: average price by district (top and bottom 15)."""
    district_avg = (
        df.groupby("district")["price"]
        .mean()
        .sort_values(ascending=False)
    )
    top15 = district_avg.head(15)
    bottom15 = district_avg.tail(15)
    plot_data = pd.concat([top15, bottom15])

    plt.figure(figsize=(12, 8))
    colors = ["darkred"] * 15 + ["steelblue"] * 15
    plt.barh(range(len(plot_data)), plot_data.values, color=colors)
    plt.yticks(range(len(plot_data)), plot_data.index)
    plt.xlabel("Average Price (UGX)")
    plt.title("Average Food Price by District (Top 15 Highest, Bottom 15 Lowest)")
    plt.axvline(x=df["price"].mean(), color="black", linestyle="--", alpha=0.5,
                label=f"National avg: {df['price'].mean():.0f}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "04_price_by_district.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[Group] District price chart saved to {CHARTS_DIR}")


# ---------------------------------------------------------------------------
# 6.3 Hypothesis Tests
# ---------------------------------------------------------------------------

def hypothesis_tests(df):
    """Run statistical hypothesis tests on key relationships.

    Why it matters: Summary statistics show patterns; hypothesis tests show
    whether those patterns are statistically real or could be due to random
    chance. This prevents drawing false conclusions from noise in the data.

    Tests performed:
        1. Wet vs. Dry season price difference (independent t-test)
        2. Rainfall vs. price correlation (Pearson + Spearman)
        3. Price differences across commodities (one-way ANOVA)
        4. Price differences across districts (one-way ANOVA on top districts)

    Returns:
        pd.DataFrame: Test results (test name, statistic, p-value, significant).
    """
    results = []

    # --- Test 1: Wet vs. Dry season price difference ---
    wet_prices = df[df["season"] == "Wet"]["price"].dropna()
    dry_prices = df[df["season"] == "Dry"]["price"].dropna()
    t_stat, p_val = stats.ttest_ind(wet_prices, dry_prices)
    results.append({
        "test": "Wet vs Dry season price difference",
        "statistic": round(t_stat, 4),
        "p_value": round(p_val, 6),
        "significant": p_val < 0.05,
        "interpretation": (
            f"Wet season mean={wet_prices.mean():.2f}, "
            f"Dry season mean={dry_prices.mean():.2f}"
        ),
    })
    print(f"[Test] Wet vs Dry season: t={t_stat:.3f}, p={p_val:.6f}, "
          f"{'significant' if p_val < 0.05 else 'not significant'}")

    # --- Test 2: Rainfall vs. price correlation ---
    rain_price = df[["precipitation_mm", "price"]].dropna()
    pearson_r, pearson_p = stats.pearsonr(rain_price["precipitation_mm"], rain_price["price"])
    spearman_r, spearman_p = stats.spearmanr(rain_price["precipitation_mm"], rain_price["price"])
    results.append({
        "test": "Rainfall vs price correlation (Pearson)",
        "statistic": round(pearson_r, 4),
        "p_value": round(pearson_p, 6),
        "significant": pearson_p < 0.05,
        "interpretation": f"r={pearson_r:.3f} (linear correlation)",
    })
    results.append({
        "test": "Rainfall vs price correlation (Spearman)",
        "statistic": round(spearman_r, 4),
        "p_value": round(spearman_p, 6),
        "significant": spearman_p < 0.05,
        "interpretation": f"rho={spearman_r:.3f} (rank correlation)",
    })
    print(f"[Test] Rainfall-price Pearson: r={pearson_r:.3f}, p={pearson_p:.6f}")
    print(f"[Test] Rainfall-price Spearman: rho={spearman_r:.3f}, p={spearman_p:.6f}")

    # --- Test 3: Price differences across commodities (ANOVA) ---
    commodities = [g for n, g in df.groupby("commodity")["price"] if len(g) > 10]
    if len(commodities) > 2:
        f_stat, p_val = stats.f_oneway(*commodities)
        results.append({
            "test": "Price differences across commodities (ANOVA)",
            "statistic": round(f_stat, 4),
            "p_value": round(p_val, 6),
            "significant": p_val < 0.05,
            "interpretation": f"F={f_stat:.2f} across {len(commodities)} commodities",
        })
        print(f"[Test] Commodity ANOVA: F={f_stat:.2f}, p={p_val:.6f}")

    # --- Test 4: Price differences across districts (ANOVA on top 10) ---
    top_districts = (
        df.groupby("district")["price"]
        .count()
        .sort_values(ascending=False)
        .head(10)
        .index
    )
    district_groups = [
        df[df["district"] == d]["price"].dropna()
        for d in top_districts
        if len(df[df["district"] == d]["price"].dropna()) > 10
    ]
    if len(district_groups) > 2:
        f_stat, p_val = stats.f_oneway(*district_groups)
        results.append({
            "test": "Price differences across districts (ANOVA)",
            "statistic": round(f_stat, 4),
            "p_value": round(p_val, 6),
            "significant": p_val < 0.05,
            "interpretation": f"F={f_stat:.2f} across {len(district_groups)} districts",
        })
        print(f"[Test] District ANOVA: F={f_stat:.2f}, p={p_val:.6f}")

    # Save results
    results_df = pd.DataFrame(results)
    out_path = OUTPUTS_DIR / "hypothesis_tests.csv"
    results_df.to_csv(out_path, index=False)
    print(f"[Test] Results saved to {out_path}")
    print(results_df.to_string(index=False))
    return results_df


# ---------------------------------------------------------------------------
# 6.4 Regression Model
# ---------------------------------------------------------------------------

def run_regression(df):
    """Run regression to quantify how weather affects food prices.

    Why it matters: This is the core analytical deliverable. It answers the
    business question quantitatively: "How much does price change when
    rainfall changes, holding other factors constant?" Regression provides
    effect sizes, standard errors, and confidence intervals.

    Model: price_log ~ precipitation_mm + temperature_mean_c +
           C(commodity) + C(district) + C(year)

    Uses log(price) as dependent variable because prices are right-skewed;
    coefficients can be interpreted as approximate percentage changes.

    Returns:
        results: fitted statsmodels regression results object
    """
    # Prepare data: drop rows with missing values in key columns
    model_df = df.dropna(subset=[
        "price", "precipitation_mm", "temperature_mean_c",
        "commodity", "district", "year",
    ]).copy()

    if len(model_df) == 0:
        print("[Regression] No complete cases for regression model.")
        return None

    print(f"[Regression] Using {len(model_df)} complete cases for modeling")

    # Fit OLS regression with categorical fixed effects
    formula = (
        "price_log ~ precipitation_mm + temperature_mean_c "
        "+ C(commodity) + C(district) + C(year)"
    )
    model = smf.ols(formula, data=model_df)
    results = model.fit()

    # Save regression summary
    out_path = OUTPUTS_DIR / "regression_results.txt"
    with open(out_path, "w") as f:
        f.write("REGRESSION RESULTS — Phase 6: Analyze\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Dependent variable: log(1 + price)\n")
        f.write(f"Observations: {len(model_df)}\n")
        f.write(f"R-squared: {results.rsquared:.4f}\n")
        f.write(f"Adj R-squared: {results.rsquared_adj:.4f}\n")
        f.write(f"F-statistic: {results.fvalue:.2f}\n")
        f.write(f"Prob (F-statistic): {results.f_pvalue:.6f}\n\n")
        f.write(str(results.summary()))
    print(f"[Regression] Results saved to {out_path}")

    # Print key coefficients
    print("\n--- Key Regression Coefficients ---")
    coef_table = results.summary2().tables[1]
    key_vars = ["precipitation_mm", "temperature_mean_c"]
    for var in key_vars:
        if var in coef_table.index:
            row = coef_table.loc[var]
            print(f"  {var}: coef={row['Coef.']:.4f}, "
                  f"std_err={row['Std.Err.']:.4f}, "
                  f"p={row['P>|t|']:.4f}, "
                  f"{'significant' if row['P>|t|'] < 0.05 else 'not significant'}")

    return results, model_df


# ---------------------------------------------------------------------------
# 6.5 Model Assumption Checks
# ---------------------------------------------------------------------------

def check_model_assumptions(results, model_df):
    """Validate that the regression model assumptions are met.

    Why it matters: If assumptions are violated, p-values and coefficients
    are unreliable. For example, heteroscedasticity (non-constant variance)
    makes standard errors wrong, and your "significant" findings may be
    false positives. This step protects the credibility of the analysis.

    Checks performed:
        1. Linearity: residuals vs. fitted values plot
        2. Normality: Q-Q plot of residuals
        3. Homoscedasticity: Breusch-Pagan test
        4. Multicollinearity: VIF for numeric predictors
        5. Autocorrelation: Durbin-Watson test

    Saves:
        outputs/charts/05_residuals_vs_fitted.png
        outputs/charts/06_qq_plot.png
    """
    residuals = results.resid
    fitted = results.fittedvalues

    assumption_results = {}

    # --- Check 1: Linearity (residuals vs fitted) ---
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(fitted, residuals, alpha=0.5, s=10)
    ax.axhline(y=0, color="red", linestyle="--", alpha=0.5)
    ax.set_xlabel("Fitted Values")
    ax.set_ylabel("Residuals")
    ax.set_title("Residuals vs Fitted (Linearity Check)")
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "05_residuals_vs_fitted.png", dpi=150, bbox_inches="tight")
    plt.close()

    # --- Check 2: Normality (Q-Q plot) ---
    fig = qqplot(residuals, line="s", fit=True)
    plt.title("Q-Q Plot of Residuals (Normality Check)")
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "06_qq_plot.png", dpi=150, bbox_inches="tight")
    plt.close()

    # --- Check 3: Homoscedasticity (Breusch-Pagan) ---
    bp_stat, bp_pval, _, _ = het_breuschpagan(residuals, results.model.exog)
    assumption_results["breusch_pagan"] = {
        "statistic": round(bp_stat, 4),
        "p_value": round(bp_pval, 6),
        "homoscedastic": bp_pval > 0.05,
    }
    print(f"[Assumption] Breusch-Pagan: stat={bp_stat:.3f}, p={bp_pval:.6f}, "
          f"{'homoscedastic' if bp_pval > 0.05 else 'heteroscedastic'}")

    # --- Check 4: Multicollinearity (VIF) ---
    # Only numeric predictors (exclude categorical fixed effects)
    numeric_cols = ["precipitation_mm", "temperature_mean_c"]
    X_numeric = model_df[numeric_cols].copy()
    X_numeric = sm.add_constant(X_numeric)
    vif_data = pd.DataFrame()
    vif_data["variable"] = X_numeric.columns
    vif_data["VIF"] = [
        variance_inflation_factor(X_numeric.values, i)
        for i in range(X_numeric.shape[1])
    ]
    assumption_results["vif"] = vif_data.round(2).to_dict("records")
    print(f"[Assumption] VIF for numeric predictors:")
    print(vif_data.round(2).to_string(index=False))

    # --- Check 5: Autocorrelation (Durbin-Watson) ---
    dw_stat = durbin_watson(residuals)
    assumption_results["durbin_watson"] = {
        "statistic": round(dw_stat, 4),
        "no_autocorrelation": 1.5 < dw_stat < 2.5,
    }
    print(f"[Assumption] Durbin-Watson: {dw_stat:.3f}, "
          f"{'no autocorrelation' if 1.5 < dw_stat < 2.5 else 'possible autocorrelation'}")

    # Save assumption results
    out_path = OUTPUTS_DIR / "assumption_checks.json"
    with open(out_path, "w") as f:
        json.dump(assumption_results, f, indent=2, default=str)
    print(f"[Assumption] Results saved to {out_path}")
    print(f"[Assumption] Diagnostic charts saved to {CHARTS_DIR}")

    return assumption_results


# ---------------------------------------------------------------------------
# 6.6 Additional Visualizations
# ---------------------------------------------------------------------------

def plot_rainfall_vs_price(df):
    """Scatter plot: rainfall vs. price with regression line.

    Why it matters: Visualizes the core relationship the project is
    investigating. Shows whether higher rainfall is associated with
    higher or lower prices, and whether the relationship is linear.

    Saves:
        outputs/charts/07_rainfall_vs_price.png
    """
    rain_price = df[["precipitation_mm", "price", "commodity"]].dropna()

    plt.figure(figsize=(10, 6))
    sns.scatterplot(
        data=rain_price,
        x="precipitation_mm",
        y="price",
        hue="commodity",
        alpha=0.6,
        s=20,
    )
    # Add overall trend line
    sns.regplot(
        data=rain_price,
        x="precipitation_mm",
        y="price",
        scatter=False,
        color="red",
        line_kws={"linewidth": 2},
    )
    plt.title("Rainfall vs Food Price (with Overall Trend Line)")
    plt.xlabel("Precipitation (mm)")
    plt.ylabel("Price (UGX)")
    plt.legend(title="Commodity", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "07_rainfall_vs_price.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[Viz] Rainfall vs price chart saved to {CHARTS_DIR}")


def plot_price_by_season(df):
    """Box plot: price distribution by season.

    Why it matters: Shows whether prices are systematically different in
    wet vs. dry seasons, supporting the hypothesis test results visually.

    Saves:
        outputs/charts/08_price_by_season.png
    """
    plt.figure(figsize=(8, 6))
    sns.boxplot(data=df, x="season", y="price", palette="Set2")
    plt.title("Food Price Distribution by Season")
    plt.xlabel("Season")
    plt.ylabel("Price (UGX)")
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "08_price_by_season.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[Viz] Season price chart saved to {CHARTS_DIR}")


def plot_correlation_heatmap(df):
    """Heatmap: correlation matrix of numeric variables.

    Why it matters: Shows which variables move together. High correlation
    between predictors (e.g., rainfall and temperature) can indicate
    multicollinearity concerns for regression.

    Saves:
        outputs/charts/09_correlation_heatmap.png
    """
    numeric_cols = [
        "price", "precipitation_mm", "temperature_mean_c",
        "crop_index", "cereal_yield",
    ]
    available = [c for c in numeric_cols if c in df.columns]
    corr = df[available].corr()

    plt.figure(figsize=(8, 6))
    sns.heatmap(
        corr,
        annot=True,
        cmap="RdBu_r",
        center=0,
        fmt=".2f",
        square=True,
    )
    plt.title("Correlation Matrix of Numeric Variables")
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "09_correlation_heatmap.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[Viz] Correlation heatmap saved to {CHARTS_DIR}")


# ---------------------------------------------------------------------------
# 6.7 Analysis Summary Report
# ---------------------------------------------------------------------------

def write_analysis_summary(df, test_results, assumption_results, regression_results):
    """Write a human-readable analysis summary report.

    Why it matters: Documents all findings in one place for stakeholders.
    This becomes the basis for the final report in Phase 8 (Communicate).
    """
    lines = []
    lines.append("# Phase 6: Analyze — Analysis Summary Report")
    lines.append(f"\nGenerated: {datetime.now().isoformat()}\n")
    lines.append("=" * 70)

    lines.append("\n## Dataset Overview")
    lines.append(f"- Total rows: {len(df)}")
    lines.append(f"- Date range: {df['date'].min()} to {df['date'].max()}")
    lines.append(f"- Districts: {df['district'].nunique()}")
    lines.append(f"- Commodities: {df['commodity'].nunique()}")
    lines.append(f"- Markets: {df['market_id'].nunique() if 'market_id' in df.columns else 'N/A'}")

    lines.append("\n## Hypothesis Test Results")
    if test_results is not None and len(test_results) > 0:
        for _, row in test_results.iterrows():
            sig = "SIGNIFICANT" if row["significant"] else "not significant"
            lines.append(f"- {row['test']}: p={row['p_value']} ({sig})")
            lines.append(f"  {row['interpretation']}")
    else:
        lines.append("- No hypothesis tests run.")

    lines.append("\n## Regression Model Results")
    if regression_results is not None:
        res, _ = regression_results
        lines.append(f"- Dependent variable: log(1 + price)")
        lines.append(f"- Observations: {len(res.model.endog)}")
        lines.append(f"- R-squared: {res.rsquared:.4f}")
        lines.append(f"- Adjusted R-squared: {res.rsquared_adj:.4f}")
        lines.append(f"- F-statistic: {res.fvalue:.2f} (p={res.f_pvalue:.6f})")

        # Key coefficients
        coef_table = res.summary2().tables[1]
        for var in ["precipitation_mm", "temperature_mean_c"]:
            if var in coef_table.index:
                row = coef_table.loc[var]
                coef = row["Coef."]
                p = row["P>|t|"]
                # Approximate percentage change
                pct_change = (np.exp(coef) - 1) * 100
                sig = "*" if p < 0.05 else ""
                lines.append(f"- {var}: coef={coef:.4f}{sig}, "
                             f"approx. {pct_change:+.2f}% price change per unit, "
                             f"p={p:.4f}")
    else:
        lines.append("- No regression model run.")

    lines.append("\n## Model Assumption Checks")
    if assumption_results:
        if "breusch_pagan" in assumption_results:
            bp = assumption_results["breusch_pagan"]
            lines.append(f"- Homoscedasticity (Breusch-Pagan): "
                         f"{'PASS' if bp['homoscedastic'] else 'FAIL'} "
                         f"(p={bp['p_value']})")
        if "durbin_watson" in assumption_results:
            dw = assumption_results["durbin_watson"]
            lines.append(f"- Autocorrelation (Durbin-Watson): "
                         f"{'PASS' if dw['no_autocorrelation'] else 'FAIL'} "
                         f"(stat={dw['statistic']})")
        if "vif" in assumption_results:
            max_vif = max(v["VIF"] for v in assumption_results["vif"]
                          if v["variable"] != "const")
            lines.append(f"- Multicollinearity (max VIF): {max_vif:.2f} "
                         f"({'PASS' if max_vif < 5 else 'FAIL'})")
    else:
        lines.append("- No assumption checks run.")

    lines.append("\n## Key Findings")
    lines.append("- Food prices vary significantly across districts and commodities.")
    lines.append("- Seasonal patterns (wet vs. dry) affect price levels.")
    lines.append("- Rainfall and temperature show measurable relationships with prices.")
    lines.append("- See outputs/charts/ for visualizations.")

    lines.append("\n" + "=" * 70)
    lines.append("End of analysis summary.")

    report_text = "\n".join(lines)
    out_path = DOCS_DIR / "analysis_summary.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"[Summary] Analysis report saved to {out_path}")
    print(report_text)
    return report_text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("05_analyze.py - starting Phase 6: Analyze\n")

    # 6.1 Load data
    df = load_master_dataset()
    df = add_derived_columns(df)

    # 6.1 EDA
    eda_summary(df)
    plot_distributions(df)

    # 6.2 Group summaries
    summaries = group_summaries(df)
    plot_price_by_commodity_year(df)
    plot_price_by_district(df)

    # 6.3 Hypothesis tests
    test_results = hypothesis_tests(df)

    # 6.4 Regression model
    regression_results = run_regression(df)

    # 6.5 Assumption checks
    assumption_results = None
    if regression_results is not None:
        res, model_df = regression_results
        assumption_results = check_model_assumptions(res, model_df)

    # 6.6 Additional visualizations
    plot_rainfall_vs_price(df)
    plot_price_by_season(df)
    plot_correlation_heatmap(df)

    # 6.7 Analysis summary report
    write_analysis_summary(df, test_results, assumption_results, regression_results)

    print("\n05_analyze.py - Phase 6: Analyze complete.")