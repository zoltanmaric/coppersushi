---
name: forecast-experiment
description: Records hypotheses, evidence and decisions when proposing, selecting, running or evaluating forecast experiments, including backtests and feature or model comparisons. Excludes routine tests and unchanged forecast operation.
---

# Forecast experiments

Read the [evaluation contract](../../../wiki/price-forecasting/evaluation.md) and [point-in-time contract](../../../wiki/price-forecasting/data-sources.md#point-in-time) before designing a comparison.

## Propose

Save each candidate as a brief page under `wiki/price-forecasting/research/`. Maintain `index.md` there with linked proposals, their status, relationships and the recommended next choice with its reason. Record in each proposal:

- The hypothesis and intended change.
- Motivating proposal links, MLflow run IDs and prior results inspected; use none for the first baseline.
- Rough cost.

Keep proposals and selection decisions in the wiki. Create MLflow runs for computational executions, not for proposals or written reviews. If proposing only, save the proposal without launching work.

## Select before execution

Read existing proposals and conclusions before recommending the next experiment. Compare relevant candidates by what they would teach, expected value, cost and prerequisites.

Recommend a candidate for the user to choose before execution, unless the user has explicitly delegated selection within an agreed research budget. Honor an existing choice or delegation without asking again.

Save the selection decision on the chosen proposal before execution. Link the candidates considered, explain the choice and deferrals, and record the user's choice or delegated budget. Update the research index; keep deferred proposals available.

Before execution, complete and freeze the selected proposal's evaluation plan in Git: comparison baseline, fixed evaluation dates and metrics, and what result would support the hypothesis.

## During execution

At execution start, attach the frozen proposal, including its selection decision, to the MLflow run with its wiki path and Git revision. Copy it; keep the wiki original. Link folds, variants and retries to that proposal version; distinguish these executions from motivating runs.

Give runs descriptive human-readable names; retain stable IDs for links and storage. Link the exact run manifests for inputs, code, environment, configuration and seeds; do not copy their contents into prose. Retain failed and interrupted attempts with their status. Preserve each run's frozen proposal; use a revised proposal and new linked execution when the hypothesis or evaluation protocol changes.

## After execution

Attach a conclusion to the execution run with results, evidence links, limitations and the next decision: keep, reject or investigate further. Compare against the baseline on matching evaluation rows. Record losses and failures as well as gains. If reviewing an existing run without a prior proposal, mark the rationale as retrospective; do not invent a pre-run hypothesis.

Update the wiki proposal with a short outcome and links to its executions and conclusions; refresh the research index. Revisit deferred proposals in light of the results; link new proposals to their motivating evidence.

Identify evaluation periods whose results informed experiment choices as development data, not untouched holdouts. Keep execution evidence in MLflow and research synthesis in the wiki, linked by run IDs. Follow this procedure manually when automation is absent.
