---
name: forecast-experiment
description: Records hypotheses, evidence and decisions when proposing, running or evaluating forecast experiments, including backtests and feature or model comparisons. Excludes routine tests and unchanged forecast operation.
---

# Forecast experiments

Read the [evaluation contract](../../../wiki/price-forecasting/evaluation.md) and [point-in-time contract](../../../wiki/price-forecasting/data-sources.md#point-in-time) before designing a comparison.

## Before execution

Save a proposal with the MLflow experiment record before launching the run. Record:

- The hypothesis and intended change.
- Motivating experiment IDs and prior results inspected; use none for the first baseline.
- The comparison baseline, fixed evaluation dates and metrics, and what result would support the hypothesis.

Use saved artifacts for the proposal and conclusion, and tags for related experiment/run IDs. Link execution runs for folds, variants and retries to the research record; distinguish these from experiments that motivated the idea. If proposing only, save the proposal without launching work.

## During execution

Link the exact run manifests for inputs, code, environment, configuration and seeds; do not copy their contents into prose. Retain failed and interrupted attempts with their status. Preserve the original proposal; start a linked experiment when the hypothesis or evaluation protocol changes.

## After execution

Append the results, evidence links, limitations, conclusion and next decision: keep, reject or investigate further. Compare against the baseline on matching evaluation rows. Record losses and failures as well as gains. If reviewing an existing run without a prior proposal, mark the rationale as retrospective; do not invent a pre-run hypothesis.

Identify evaluation periods whose results informed experiment choices as development data, not untouched holdouts. Keep experiment history in MLflow; put durable accepted design decisions in the wiki with experiment IDs. Follow this procedure manually when automation is absent.
