# Diagnose training versus future performance

Status: proposed; not selected or executed. Evaluation plan is not frozen.

## Question

The training-to-future gap and time-dependent bias can narrow the next research question, without identifying their cause by themselves.

## Change

Export per-fold training and future coverage/errors, quantile hit rates, lower/upper misses, interval widths and signed median errors by delivery hour/month; label training fit explicitly.

## Evidence

Motivated by [baseline review](baseline-review.md) and accepted MLflow execution `8a4c692855fb42eba39d5a3bfc7d6762`. January–September 2026 results and the October 20 review were inspected; these dates are development evidence, not an untouched holdout.

## Cost

Low–medium: saved-model prediction and aggregation; no retraining.

## Prerequisites

Requires saved inputs/models and a source-to-feature audit.

## Open-plan

Exact diagnostic scope and treatment of raw versus sorted predictions remain to be frozen. Before execution, record the selection decision and freeze the comparison baseline, dates, metrics and decision rule in Git. No execution outcome exists.
