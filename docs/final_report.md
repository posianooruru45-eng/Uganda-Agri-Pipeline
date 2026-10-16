# Final Report — Uganda Agriculture and Climate Data Pipeline

**Date:** 16 October 2026  
**Project:** Uganda Agri-Pipeline (Phases 1–8 Complete)  
**Repository:** https://github.com/posianooruru45-eng/Uganda-Agri-Pipeline.git

---

## Executive Summary

This project built a complete data pipeline to answer: **How do rainfall and other conditions relate to staple food prices across Uganda's districts and markets, and how reliable is that evidence once data quality is properly controlled?**

The pipeline collected data from 4 sources (World Bank, Open-Meteo, Our World in Data, WFP), cleaned and validated all 34,328 WFP price observations, integrated them with weather and crop data, and produced a validated master dataset of **16,179 rows** spanning 31 districts, 37 commodities, and 32 markets from 2018–2024.

**Key finding:** Weather conditions (rainfall and temperature) have a statistically significant negative relationship with food prices when controlling for commodity, district, and year — each additional mm of rainfall is associated with approximately 0.25% lower prices, and each additional °C with approximately 1.29% lower prices. However, the simple correlation between rainfall and price is near zero, meaning this relationship only emerges when controlling for other factors.

---

## 1. Project Charter

**Business Question:** How do rainfall and other conditions relate to staple food prices across Uganda's districts and markets, and how reliable is that evidence once data quality is properly controlled?

**Variables needed:** price, commodity, district, date, rainfall, temperature  
**Time period:** 2015–2024  
**Coverage:** Uganda, limited to districts common to all four data sources

---

## 2. Data Collection (Phase 2)

Four data sources were collected and saved with SHA256 checksums:

| Source | Format | License | Records | Date Range |
|--------|--------|---------|---------|------------|
| World Bank - Crop Production Index | JSON API | CC-BY 4.0 | 66 rows | 1960–2025 |
| Open-Meteo - Historical Weather | JSON API | CC-BY 4.0 | 2,557 rows | 2018–2024 |
| Our World in Data - Cereal Yield | CSV | CC-BY 4.0 | 2 rows (Uganda only) | 2015, 2024 |
| WFP Food Prices - Uganda | CSV | CC-BY-IGO 3.0 | 34,328 rows | 2006–2024 |

**Note:** FAOSTAT API was attempted but returned repeated HTTP 521 errors; Our World in Data was used as a substitute for cereal yield data.

All raw files are stored in `data/raw/` with checksums in `data/raw/manifest.csv`.

---

## 3. Data Profiling (Phase 3)

Each source was profiled for shape, columns, data types, missing values, duplicates, and summary statistics. Key issues identified:

| Dataset | Issue | Size | % Missing |
|---------|-------|------|-----------|
| World Bank | `value` column missing | 4 rows | 6.1% |
| OWID | `Original Year` column missing | 357 rows | 99.7% |

Full profiling report saved to `docs/profiling_report.txt`; issues list saved to `docs/issues.csv`.

---

## 4. Data Cleaning (Phase 4)

All 4 sources were cleaned. Changes logged to `docs/cleaning_log.csv`:

| Source | Cleaning Actions | Output File |
|--------|-----------------|-------------|
| OWID | Filtered to Uganda (358 → 2 rows), removed duplicates, renamed columns, converted types | `data/interim/owid_clean.csv` (2 rows) |
| World Bank | Dropped 6 redundant columns, converted date→year, value→float, removed duplicates, capped 2 outliers | `data/interim/worldbank_clean.csv` (66 rows) |
| Weather | Parsed dates, renamed columns, removed duplicates, capped 117 precipitation + 8 temperature outliers | `data/interim/weather_clean.csv` (2,557 rows) |
| WFP | Parsed dates, standardized column names, converted price to numeric, removed duplicates, capped 3,417 price outliers | `data/interim/wfp_clean.csv` (34,328 rows) |

Outliers were capped using the IQR method (k=1.5 winsorization). Raw files were never modified.

---

## 5. Integration and Validation (Phase 5)

All 4 clean sources were joined into a master dataset:

**Join Strategy:**
- Grain: WFP market-day-commodity row (most granular)
- Weather joined on `date` (Kampala weather applied to all rows that date)
- World Bank crop_index joined on `year`
- OWID cereal_yield joined on `year`

**Master Dataset:** 34,328 rows × 21 columns before validation

### 33 Validation Rules (7 Categories)

| Category | Count | Example Rules |
|----------|-------|---------------|
| Completeness | 6 | price, date, district not null |
| Uniqueness | 2 | No duplicate market-date-commodity rows |
| Range | 9 | price ≥ 0, temperature 10–40°C, lat/long within Uganda bounds |
| Referential Integrity | 5 | District is recognized Uganda district, currency is UGX/USD |
| Cross-Field | 6 | usdprice ≥ 0, priceflag/pricetype valid values |
| Temporal | 4 | Date within 2015–2024, no future dates |

**Validation Results:**
- **Passed:** 16,179 rows (47.1%)
- **Quarantined:** 18,149 rows (52.9%)

**Top reasons for quarantine:**
1. Date before 2015 (10,790 rows) — outside project charter period
2. Duplicate market-date-commodity-priceflag rows (7,936 rows)
3. Unrecognized/unmapped district (4,897 rows)

Quarantined rows saved to `data/quarantine/quarantined.csv`; validation report saved to `docs/validation_report.txt`.

---

## 6. Analysis (Phase 6)

### 6.1 Exploratory Data Analysis

Summary statistics computed for all numeric variables. Key observations:
- Price is right-skewed (mean: 2,924 UGX, median: 2,200 UGX)
- Precipitation is heavily right-skewed (most days have little/no rain)
- Temperature is fairly symmetric around 21–22°C

### 6.2 Group Summaries

| Metric | Value |
|--------|-------|
| Average price (all) | 2,924 UGX |
| Average price (Dry season) | 2,935 UGX |
| Average price (Wet season) | 2,918 UGX |
| Price range | 2.00 – 7,107.50 UGX |
| Districts covered | 31 |
| Commodities covered | 37 |
| Markets covered | 32 |

### 6.3 Hypothesis Tests

| Test | Statistic | p-value | Significant? |
|------|-----------|---------|--------------|
| Wet vs Dry season price (t-test) | t = -0.50 | 0.616 | No |
| Rainfall vs price (Pearson) | r = 0.001 | 0.912 | No |
| Rainfall vs price (Spearman) | ρ = 0.008 | 0.287 | No |
| Price across commodities (ANOVA) | F = 4,074 | < 0.001 | Yes |
| Price across districts (ANOVA) | F = 0.97 | 0.460 | No |

### 6.4 Regression Model

**Model:** `log(1 + price) ~ precipitation + temperature + commodity + district + year`  
**Observations:** 16,179  
**R-squared:** 0.8889  
**Adjusted R-squared:** 0.8884  
**F-statistic:** 1,740.99 (p < 0.001)

| Variable | Coefficient | p-value | Approx. Effect |
|----------|-------------|---------|----------------|
| precipitation_mm | -0.0025 | < 0.001 | -0.25% price per mm |
| temperature_mean_c | -0.0130 | < 0.001 | -1.29% price per °C |

### 6.5 Model Assumption Checks

| Check | Test | Result |
|-------|------|--------|
| Linearity | Residuals vs fitted | PASS |
| Normality | Q-Q plot | PASS |
| Homoscedasticity | Breusch-Pagan | FAIL (p < 0.001) |
| Multicollinearity | VIF (max 1.20) | PASS |
| Autocorrelation | Durbin-Watson (1.79) | PASS |

**Note:** Heteroscedasticity detected — use robust standard errors for inference.

### 6.6 Visualizations

9 charts generated in `outputs/charts/`:
1. Price distribution (raw + log-transformed)
2. Weather distribution (precipitation + temperature)
3. Price trend by commodity over years
4. Price by district (top/bottom 15)
5. Residuals vs fitted (linearity check)
6. Q-Q plot (normality check)
7. Rainfall vs price scatter with trend line
8. Price by season box plot
9. Correlation heatmap

---

## 7. Integrity and Automation (Phase 7)

### Pipeline Runner
`src/run_pipeline.py` — one-command execution of all 5 phases with error handling and timeouts.

### Audit Log
`docs/audit_log.csv` — records every pipeline run with run_id, phase, status, duration, row counts, and errors.

### Reconciliation Table
`outputs/reconciliation.csv` — tracks row counts at each stage to catch silent data loss.

### Unit Tests
`tests/test_pipeline.py` — **24 tests, all passing**, covering all phases.

### Reproducibility
The full pipeline was rerun end-to-end, producing identical results (16,179 rows, R² = 0.8889, same coefficients).

---

## 8. Limitations

1. **Weather data is Kampala-only:** Applied to all districts, which may not reflect local conditions in rural areas.
2. **Heteroscedasticity:** Regression standard errors may be slightly unreliable; robust standard errors recommended.
3. **OWID cereal yield:** Only 2 years of data (2015, 2024) for Uganda; limited analytical value.
4. **WFP data starts 2006:** Project charter limits analysis to 2015–2024, so 10,790 pre-2015 rows were quarantined.
5. **District mapping:** Some market names and refugee settlements required manual alias mapping to canonical districts.

---

## 9. Recommendations

1. **Collect district-level weather data** rather than using Kampala-only weather for all districts.
2. **Use robust standard errors** (e.g., HC3) to address heteroscedasticity in regression inference.
3. **Investigate pre-2015 WFP data** if the project scope is extended beyond 2015–2024.
4. **Add more districts** to the canonical district list as WFP expands coverage.
5. **Consider time-series models** (e.g., SARIMA) to capture seasonal price cycles more explicitly.

---

## 10. Conclusion

The pipeline successfully integrated 4 data sources into a validated master dataset and demonstrated that weather conditions (rainfall and temperature) are statistically significant predictors of food prices in Uganda when controlling for commodity, district, and year. The negative relationship suggests that better weather conditions (more rain, moderate temperatures) are associated with lower food prices — consistent with the economic logic that good harvests increase supply and reduce prices.

All code, data, documentation, and tests are available in the repository for reproduction and extension.