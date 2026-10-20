# Compare a simpler model

Status: proposed; not selected or executed. Evaluation plan is not frozen.

## Question

Reducing model complexity may improve future error and coverage despite worse training fit.

## Change

Change one predeclared complexity setting while holding inputs, dates and scoring fixed.

## Evidence

Motivated by [diagnostics](training-future-diagnostics.md) and accepted MLflow execution `8a4c692855fb42eba39d5a3bfc7d6762`. January–September 2026 results and the October 20 review were inspected; these dates are development evidence, not an untouched holdout.

## Cost

Medium: one full monthly comparison plus verification; runtime not yet estimated.

## Prerequisites

Review training/future diagnostics; select the single complexity change.

## Open-plan

Parameter, value, fixed dates and acceptance threshold remain undecided. Before execution, record the selection decision and freeze the comparison baseline, dates, metrics and decision rule in Git. No execution outcome exists.
