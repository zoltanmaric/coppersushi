# Expose research diagnostics in the observatory

Status: proposed; not selected or executed. Evaluation plan is not frozen.

## Question

Linked hour/month diagnostics can help choose research from broad evidence rather than a dramatic day.

## Change

Display quantile hit rates, directional misses, widths and bias, plus per-fold training/future metrics when exported; link slices to daily curves while retaining all dates.

## Evidence

Motivated by [diagnostics](training-future-diagnostics.md) and accepted MLflow execution `8a4c692855fb42eba39d5a3bfc7d6762`. January–September 2026 results and the October 20 review were inspected; these dates are development evidence, not an untouched holdout.

## Cost

Medium: exporter and UI changes; no fitting.

## Prerequisites

Diagnostic artifact schema and reviewed HTML spec; label training fit as distinct from forecast skill.

## Open-plan

Exact UI and exported fields remain to be designed; this is a product-support proposal, not a model experiment. Before execution, record the selection decision and freeze the comparison baseline, dates, metrics and decision rule in Git. No execution outcome exists.
