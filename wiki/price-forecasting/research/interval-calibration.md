# Calibrate bands from earlier forecast errors

Status: proposed; not selected or executed. Evaluation plan is not frozen.

## Question

Earlier out-of-sample errors may improve interval calibration relative to unchanged bands without excessive width or interval-score cost.

## Change

Adjust bounds using only forecast errors whose outcomes were available at issue time; change no model settings.

## Evidence

Motivated by [diagnostics](training-future-diagnostics.md) and accepted MLflow execution `8a4c692855fb42eba39d5a3bfc7d6762`. January–September 2026 results and the October 20 review were inspected; these dates are development evidence, not an untouched holdout.

## Cost

Medium: chronological calibration replay and leakage checks; no model-family search.

## Prerequisites

Specify a strictly prior out-of-sample error stream and extend late-information tests.

## Open-plan

Calibration method, window, warmup, exact dates and decision threshold remain undecided; no training residuals or scored-period lookahead. Before execution, record the selection decision and freeze the comparison baseline, dates, metrics and decision rule in Git. No execution outcome exists.
