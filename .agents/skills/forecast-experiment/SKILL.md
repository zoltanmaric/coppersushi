---
name: forecast-experiment
description: Records hypotheses, evidence and decisions when proposing, selecting, running or evaluating forecast experiments, including backtests and feature or model comparisons. Excludes routine tests and unchanged forecast operation.
---

# Forecast experiments

Read the [evaluation contract](../../../wiki/price-forecasting/evaluation.md) and [point-in-time contract](../../../wiki/price-forecasting/data-sources.md#point-in-time) before designing a comparison.

## Propose

Save each candidate as a brief proposal with its own MLflow research record, even when no execution is planned. Record:

- The hypothesis and intended change.
- Motivating experiment IDs and prior results inspected; use none for the first baseline.
- Rough cost.

Use saved artifacts for the proposal and conclusion, and tags for related experiment/run IDs. Link execution runs for folds, variants and retries to the research record; distinguish these from experiments that motivated the idea. If proposing only, save the proposal without launching work.

## Select before execution

Read existing proposals and conclusions before recommending the next experiment. Compare relevant candidates by what they would teach, expected value, cost and prerequisites.

Recommend a candidate for the user to choose before execution, unless the user has explicitly delegated selection within an agreed research budget. Honor an existing choice or delegation without asking again.

Save the selection decision as an artifact on the selected MLflow research record before execution. Link the candidate IDs considered, record why this candidate comes first and why alternatives are deferred, and record the user's choice or delegated budget. Keep deferred proposals available for later selection.

Before execution, complete and freeze the selected proposal's evaluation plan: comparison baseline, fixed evaluation dates and metrics, and what result would support the hypothesis.

## During execution

Link the exact run manifests for inputs, code, environment, configuration and seeds; do not copy their contents into prose. Retain failed and interrupted attempts with their status. Preserve the frozen proposal; start a linked experiment when the hypothesis or evaluation protocol changes.

## After execution

Append the results, evidence links, limitations, conclusion and next decision: keep, reject or investigate further. Compare against the baseline on matching evaluation rows. Record losses and failures as well as gains. If reviewing an existing run without a prior proposal, mark the rationale as retrospective; do not invent a pre-run hypothesis.

Revisit deferred proposals in light of the results; link any new proposals to the evidence that motivated them.

Identify evaluation periods whose results informed experiment choices as development data, not untouched holdouts. Keep experiment history in MLflow; put durable accepted design decisions in the wiki with experiment IDs. Follow this procedure manually when automation is absent.
