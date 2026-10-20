# Measure incremental value of weather and demand

Status: proposed; not selected or executed. Evaluation plan is not frozen.

## Question

Weather may improve price-only forecasts while demand may contribute little or depend on availability.

## Change

Compare weather versus prices/calendar and demand versus weather on common delivery rows, with whole-day block resampling and demand-present/missing subsets.

## Evidence

Motivated by [baseline review](baseline-review.md) and accepted MLflow execution `8a4c692855fb42eba39d5a3bfc7d6762`. January–September 2026 results and the October 20 review were inspected; these dates are development evidence, not an untouched holdout.

## Cost

Low: aggregate saved predictions and resample paired whole-day blocks; no retraining.

## Prerequisites

Fix paired comparisons and uncertainty protocol; retain common target rows.

## Open-plan

Exact comparison dates, bootstrap settings and decision rule remain to be frozen; inspected dates are development evidence. Before execution, record the selection decision and freeze the comparison baseline, dates, metrics and decision rule in Git. No execution outcome exists.
