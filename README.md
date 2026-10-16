# Uganda Agriculture and Climate Data Pipeline

## Project Overview

**Business Question:** How do rainfall and other conditions relate to staple food prices across Uganda's districts and markets, and how reliable is that evidence once data quality is properly controlled?

**Time Period:** 2015–2024  
**Coverage:** Uganda, limited to districts common to all four data sources  
**Variables:** price, commodity, district, date, rainfall, temperature

## Repository Structure

```
uganda-agri-pipeline/
├── data/
│   ├── raw/           # Raw downloaded data (4 sources, timestamped)
│   ├── interim/       # Partially processed clean datasets
│   ├── clean/         # Final validated master dataset
│   └── quarantine/    # Rows that failed validation rules
├── docs/
│   ├── charter.md                 # Project charter & business question
│   ├── source_register.csv        # Data sources, URLs, licences
│   ├── cleaning_log.csv           # Every cleaning change logged
│   ├── profiling_report.txt       # Phase 3 data quality issues
│   ├── issues.csv                 # Issue list with sizes
│   ├── validation_report.txt      # Phase 5: 33 validation rules
│   ├── analysis_summary.md        # Phase 6: Analysis findings
│   ├── final_report.md            # Phase 8: Final comprehensive report
│   └── audit_log.csv              # Phase 7: Pipeline run history
├── outputs/
│   ├── group_summaries.csv        # Phase 6: Group-level aggregations
│   ├── hypothesis_tests.csv       # Phase 6: Statistical test results
│   ├── regression_results.txt     # Phase 6: Regression model output
│   ├── summary_stats.csv          # Phase 6: EDA summary statistics
│   ├── assumption_checks.json     # Phase 6: Model assumption results
│   ├── reconciliation.csv         # Phase 7: Row counts per stage
│   └── charts/                    # Phase 6: 9 visualization PNGs
├── src/
│   ├── 01_collect.py              # Phase 2: Data collection
│   ├── 02_profile.py              # Phase 3: Data profiling
│   ├── 03_clean.py                # Phase 4: Data cleaning
│   ├── 04_integrate.py            # Phase 5: Integration & validation
│   ├── 05_analyze.py              # Phase 6: Analysis
│   └── run_pipeline.py            # Phase 7: One-command pipeline runner
├── tests/
│   └── test_pipeline.py           # Phase 7: 24 unit tests
├── .venv/                         # Python virtual environment
├── .gitignore                     # Git ignore rules
└── requirements.txt               # Python dependencies

## Data Sources

| Source | Format | License | Access Method |
|--------|--------|---------|---------------|
| World Bank - Crop Production Index | JSON API | CC-BY 4.0 | API (no key required) |
| Open-Meteo - Historical Weather | JSON API | CC-BY 4.0 | API (no key required) |
| Our World in Data - Cereal Yield | CSV | CC-BY 4.0 | Direct download |
| WFP Food Prices - Uganda | CSV | CC-BY-IGO 3.0 | Direct download (via HDX) |

## Pipeline Phases

| Phase | Script | Description |
|-------|--------|-------------|
| 1 | Plan & Set Up | Charter, source register, repository structure |
| 2 | Collect | `01_collect.py` — downloads from 4 APIs, computes SHA256 checksums |
| 3 | Profile | `02_profile.py` — profiles each source, saves report + issues list |
| 4 | Clean | `03_clean.py` — fixes types, labels, duplicates, missing values, outliers |
| 5 | Integrate & Validate | `04_integrate.py` — joins sources, 33 validation rules, quarantines failures |
| 6 | Analyze | `05_analyze.py` — EDA, group summaries, hypothesis tests, regression |
| 7 | Integrity & Automation | `run_pipeline.py` — one-command runner, audit log, reconciliation, tests |
| 8 | Communicate | Final report, README, dashboard, GitHub |

## How to Run the Pipeline

### Prerequisites
- Python 3.10+
- `pip install -r requirements.txt`

### One-Command Pipeline (Recommended)
```bash
python src/run_pipeline.py
```

This runs all 5 executable phases in order and produces:
- `docs/audit_log.csv` — pipeline run history
- `outputs/reconciliation.csv` — row counts at each stage

### Run Individual Phases
```bash
python src/01_collect.py   # Download raw data
python src/02_profile.py   # Profile data quality
python src/03_clean.py     # Clean all 4 sources
python src/04_integrate.py # Join + validate (33 rules)
python src/05_analyze.py   # EDA, hypothesis tests, regression
```

### Run Unit Tests
```bash
python -m unittest tests.test_pipeline -v
```

## Key Findings

- **16,179 validated rows** from 34,328 total WFP observations (47.1% pass rate)
- **31 districts**, **37 commodities**, **32 markets** covered
- **Date range:** 2018-01-15 to 2024-12-15
- **Regression R-squared:** 0.8889 (model explains 89% of price variation)
- **Precipitation effect:** -0.25% price change per additional mm of rain (p < 0.001)
- **Temperature effect:** -1.29% price change per additional °C (p < 0.001)
- **Seasonal difference:** Not statistically significant (p = 0.616)
- **District differences:** Not statistically significant (p = 0.460)
- **Commodity differences:** Highly significant (p < 0.001)

## Model Assumptions

| Check | Test | Result |
|-------|------|--------|
| Linearity | Residuals vs fitted | PASS |
| Normality | Q-Q plot | PASS |
| Homoscedasticity | Breusch-Pagan | FAIL (p < 0.001) |
| Multicollinearity | VIF (max = 1.20) | PASS |
| Autocorrelation | Durbin-Watson (1.79) | PASS |

**Note:** Heteroscedasticity detected — standard errors may be slightly unreliable. Use robust standard errors for inference.

## Output Files

### Master Dataset
- `data/clean/master_dataset.csv` — 16,179 rows × 21 columns (validated data)
- `data/quarantine/quarantined.csv` — 18,149 rows (failed validation)

### Visualizations (`outputs/charts/`)
1. `01_price_distribution.png` — Price histogram (raw + log)
2. `02_weather_distribution.png` — Precipitation + temperature histograms
3. `03_price_trend_by_commodity.png` — Price trends by year for top 8 commodities
4. `04_price_by_district.png` — Top/bottom 15 districts by average price
5. `05_residuals_vs_fitted.png` — Regression linearity check
6. `06_qq_plot.png` — Residual normality check
7. `07_rainfall_vs_price.png` — Rainfall vs price scatter + trend line
8. `08_price_by_season.png` — Price distribution by wet/dry season
9. `09_correlation_heatmap.png` — Correlation matrix of numeric variables

## License

Data sources are under their respective licenses (CC-BY 4.0, CC-BY-IGO 3.0).  
Pipeline code is provided for research and educational purposes.

## Contact

Project repository: https://github.com/posianooruru45-eng/Uganda-Agri-Pipeline.git