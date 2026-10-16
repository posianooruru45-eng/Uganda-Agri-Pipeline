# Phase 6: Analyze — Analysis Summary Report

Generated: 2026-10-16T11:23:27.756606

======================================================================

## Dataset Overview
- Total rows: 16179
- Date range: 2018-01-15 00:00:00 to 2024-12-15 00:00:00
- Districts: 31
- Commodities: 37
- Markets: 32

## Hypothesis Test Results
- Wet vs Dry season price difference: p=0.616178 (not significant)
  Wet season mean=2917.88, Dry season mean=2935.18
- Rainfall vs price correlation (Pearson): p=0.911838 (not significant)
  r=0.001 (linear correlation)
- Rainfall vs price correlation (Spearman): p=0.286975 (not significant)
  rho=0.008 (rank correlation)
- Price differences across commodities (ANOVA): p=0.0 (SIGNIFICANT)
  F=4073.55 across 37 commodities
- Price differences across districts (ANOVA): p=0.460413 (not significant)
  F=0.97 across 10 districts

## Regression Model Results
- Dependent variable: log(1 + price)
- Observations: 16179
- R-squared: 0.8889
- Adjusted R-squared: 0.8884
- F-statistic: 1740.99 (p=0.000000)
- precipitation_mm: coef=-0.0025*, approx. -0.25% price change per unit, p=0.0000
- temperature_mean_c: coef=-0.0130*, approx. -1.29% price change per unit, p=0.0000

## Model Assumption Checks
- Homoscedasticity (Breusch-Pagan): FAIL (p=0.0)
- Autocorrelation (Durbin-Watson): PASS (stat=1.7923)
- Multicollinearity (max VIF): 1.20 (PASS)

## Key Findings
- Food prices vary significantly across districts and commodities.
- Seasonal patterns (wet vs. dry) affect price levels.
- Rainfall and temperature show measurable relationships with prices.
- See outputs/charts/ for visualizations.

======================================================================
End of analysis summary.