# Baseline diagnostic review

Retrospective synthesis, 2026-10-20. Motivating execution: `8a4c692855fb42eba39d5a3bfc7d6762`; forecast run: `d24461d3be8c819d9310ea55`. This is a written review, not a new computation or a preregistered experiment.

## Evidence

The [PR #105 review](https://github.com/zoltanmaric/coppersushi/pull/105#pullrequestreview-5583597223) reports:

- Weather-model 95% band coverage: January training 95.5% versus future 52.3%; September 95.3% versus 63.0%. Median absolute errors rise from 5.65 to 17.78 €/MWh and from 10.47 to 35.76 respectively.
- System 95% coverage is 63.7%, with 18.4% below and 17.9% above the band. Its 50% band covers 24.3%. Sorting alone does not explain the under-coverage.
- Weighted interval scores are 21.06 for prices/calendar, 16.35 with weather, 16.42 with demand and 16.34 for the selected system. Tiny differences do not establish improvement.

The [PR #112 review](https://github.com/zoltanmaric/coppersushi/pull/112#pullrequestreview-5583599100) reports signed predicted-minus-actual error around +10.20 €/MWh at 13:00–13:45 and −19.74 at 20:00–20:45; April and September have opposite average bias.

These numbers are attributed to the reviewers, not independently recomputed during record migration. They motivate investigation but do not separate overfitting from changing conditions or establish a code defect. All inspected January–September results are development evidence.

## Decision

Preserve the accepted baseline. Investigate further through the [candidate index](index.md); no candidate is selected and no execution is authorized by this review. Keep model changes separate from calibration, retain failures, and use fresh uninspected dates for confirmation after choices are fixed.

Preserve independent score and late-information checks. Before learned calibration, test that later outcomes and revisions cannot alter earlier calibration or predictions. Audit an ordinary day, a clock-change day and missing demand from source to features.

## Execution-history

The baseline had no proposal saved before execution. Its rationale and conclusion are explicitly retrospective. Actual executions remain in local MLflow:

| Execution | MLflow run ID | Role |
|---|---|---|
| Quantile baseline | `a3149d4e7c624c46a4320fa95d2132db` | Accepted timed rerun; 445.963 seconds |
| Initial complete baseline | `71e7d7162c0d4947af5d2a48e3b39ed6` | Initial complete scores |
| Integration smoke check | `79cfbd0937c24755931e12f3c9f2eeb9` | Integration check |
| Interrupted exploratory baseline | `dba3c0f32c9f4fe38e552b8592de8d20` | Interrupted; retained as KILLED |

The accepted execution reruns the unchanged baseline: predictions and scores match the motivating execution, and fresh-environment reproduction from S3 passes. Its forecast run is `3db10bdf199fdbaa012525ce`. The review findings above remain attributed to the original review, not independently recomputed diagnostics.

The accepted run retains `research/baseline/retrospective-rationale.json`, `research/baseline/conclusion.json`, and `research/review-2026-10-20/retrospective-review.json` with the original review comments and links. Frozen configuration, environment and input identities remain in its original `run/manifest.json`. No retrospective document is presented as a pre-execution proposal. [Open local MLflow](../../../forecasts/README.md#local-model-evaluation).
