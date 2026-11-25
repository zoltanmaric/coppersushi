# Day-ahead forecast evaluation

The [forecast design](germany-luxembourg.md) fixes five price quantiles and weighted interval score as the main measure, agreed 2026-10-09. This page is the small evaluation contract; it does not require a general experiment platform.

### Quantiles

A price quantile at probability `q` is a price below which the outcome is predicted to fall with probability `q`. Output `q=[0.025, 0.25, 0.50, 0.75, 0.975]` per delivery quarter. The median is `q50`; `[q25,q75]` is the central 50% interval and `[q2.5,q97.5]` the central 95% interval.

Train the prices/calendar feature set with one CatBoost model using `MultiQuantile:alpha=0.025,0.25,0.5,0.75,0.975`. All outputs use the same input row. Sort each predicted vector into nondecreasing order before evaluation and publication; retain raw outputs and report the fraction that crossed before sorting. This is a fixed implementation rule, not a post-test correction. These five numbers do not specify arbitrary tail probabilities or the joint evolution of a day's prices. [CatBoost objective](https://catboost.ai/docs/en/concepts/loss-functions-regression#MultiQuantile).

### WIS

**Weighted interval score** rewards narrow intervals and penalises observations outside them. For an interval `[l,u]` with nominal coverage `1−α` and actual price `y`:

```text
interval_score(α) = (u−l) + (2/α) max(l−y,0) + (2/α) max(y−u,0)
weighted_interval_score =
  [0.5 |y−q50| + 0.25 interval_score(0.5) + 0.025 interval_score(0.05)] / 2.5
```

Lower is better, in €/MWh. Average per-quarter scores over the common target rows. The fixed five-quantile objective is aligned with this score: the score equals twice the mean pinball loss across those quantiles. Check the score against hand-calculated cases and an independent scoring implementation. [Energy-Arena definitions](https://energy-arena.org/faq).

Report median-price mean absolute error, root mean squared error of that same median, 50%/95% coverage and mean interval width. The squared-error diagnostic does not make the median a conditional-mean forecast. Break out results by month, with counts and forecast coverage.

[Energy-Arena](https://energy-arena.org/challenges) ranks quantile forecasts by weighted interval score, point forecasts by root mean squared error and ensembles by continuous ranked probability score. Match dates, target resolution and information cutoff before comparing scores. Entry is undecided; no submission is part of the initial build.

## Replay

Apply the [point-in-time contract](data-sources.md#point-in-time) to features, training-label versions, learned preprocessing and reference calibration at their respective issue or fit cutoffs. Later outcomes may enter scoring, but must never feed back into the historical forecast. Reports state which sources have witnessed availability and which rely on assumptions; a repeatable replay is not evidence of verified historical availability.

- Fix the data snapshot, transformations, locations, training dates, monthly refit schedule, settings, seed and references before fitting. Freeze them in a saved run manifest. No test-guided feature or parameter search.
- Train only on earlier dates and labels available by each fold's first forecast issue time. Recompute each day's price lags from information available by that day's 11:00 deadline, even while reusing a monthly fitted model. Any learned preprocessing uses training data only.
- Keep UTC timestamps internally; derive German calendar features explicitly. Include the actual 92/96/100 quarter-hours on clock-change days and apply the [agreed defaults](#defaults).
- Retain every registered delivery quarter. Training requires every eligible training label. Scoring requires every realised price and compares every method on the same complete delivery grid. A prediction can be reconstructed before realised prices are available.
- Stop on missing source data, failed fits, or failed predictions. Preserve the source, affected dates and error in the failed attempt. Diagnose missing inputs or upstream behaviour before retrying. Existing diagnostic exports can still show gaps and historic fallbacks.

### Defaults

Freeze these rules before fitting. The first baseline used the older fallback policy documented in its saved results.

| Choice | Rule |
|---|---|
| Past-price clock matching | Match the same German local quarter on the earlier date. Average both prices if that quarter occurred twice; mark it missing if it did not occur. Keep both delivery quarters on the autumn clock-change day. |
| Price coverage | Require every physical price-history quarter used by the baseline. |
| Calendar | Quarter of day, day of week, month and a Germany-wide public-holiday flag, identical across model comparisons. |
| Unexpected source failure | Stop fitting, prediction or scoring at the affected stage. A timeout, missing revision or incomplete source response does not establish structural unavailability. |

The spring clock change makes some same-clock lag quarters structurally nonexistent. They stay missing by definition even when the original physical delivery grid is complete. Any other upstream exclusion requires a separately recorded source and affected dates, evidence that recovery is impossible, and explicit approval before changing the registered comparison. No automatic exclusions apply.

### Controls

Fit the [registered prices/calendar model](research/prices-only-baseline.md) and compare it with the reference on the same quarters. Both methods must produce forecasts.

## Reference

[Energy-Arena history findings](energy-arena-benchmarks.md) identify a compatible external fundamentals forecast at our cutoff, with short coverage; the local reference below covers the full evaluation.

The simple price estimate is the equal-weight average of yesterday's and last week's same-local-quarter prices. Apply the clock-matching rule above. If one price is missing, use the other; if both are missing, use the training-history median for that local quarter.

Calculate historical errors as actual price minus that estimate, using training dates only. Replay the same missing-price rules; any median used for a historical estimate must use only earlier available history. Exclude initial rows with insufficient history from error estimation, not evaluation dates, and record their count.

Pool errors across all hours and days. Add their five empirical quantiles to the estimate to form the reference forecast. Recompute the error quantiles at each monthly fit from training data only, using linear quantile interpolation. This gives the reference the same interval widths at every delivery quarter within a fold. Require sufficient history for all reference outputs before the first evaluation date. Do not fit these offsets on evaluation outcomes.

## Evidence

The registered baseline uses paired resampling of contiguous seven-day blocks of whole German local days. For another configuration, report the block length recorded for that run. Do not treat quarter-hours as independent or stitch across missing dates/separate evaluation windows. Fix the resampling seed/count and recompute aggregate scores from the sampled rows. Show effect size and uncertainty; do not claim an established gain if its interval includes no improvement.

Preserve raw inputs or content hashes, request and retrieval metadata, row-level availability flags, configuration, library versions, raw/ordered quantiles, reference forecasts, per-quarter outcomes and the report. A change after looking at scores starts a new development experiment. Forecast-quality improvement does not establish trading profitability.

Proposal provenance and execution evidence follow the [research-record contract](forecast-infrastructure.md#research-history).

### Limitations

The fixed first fit uses October 15–December 31, 2025 to predict January 2026; October 1–14 provides feature warmup. Later monthly fits add the preceding months. This is a date choice, not a limit imposed by missing demand. More months can be used for initial training within the assembled year, leaving fewer months for evaluation. Earlier compatible data has not been established.

One annual cycle gives limited evidence about rare extreme prices. Many consecutive quarter-hours can describe a single storm or price event. A nominal 95% range is therefore not proof of reliable coverage during extremes. Recommended additional checks are separate counts below and above the predicted ranges, and coverage by delivery hour; these are review recommendations, not added first-build acceptance criteria.

Historical input timing remains subject to the [availability limits](data-sources.md#availability). Prospective forecasts made after settings are fixed provide fresh evidence. Acceptance of a reproducible report does not establish readiness for daily use; see the [continuation decision](germany-luxembourg.md#continuation).

## Freeze

The [registered configuration](../../forecasts/run-config.json) freezes dates, CatBoost settings, minimum reference history, resampling and numerical tolerance. [Implementation/setup](../../forecasts/README.md#local-model-evaluation) describes the fixed price features and explicit feature inventories saved before fitting. Changes after inspecting scores belong to a separate experiment.

Monthly expanding evaluation covers January–September 2026. This is retrospective evaluation: All January–September dates were inspected in the earlier three-model comparison. Do not call them an untouched final holdout. Prospective forecasts after freezing provide fresh evidence; the single historical year does not establish multi-year robustness.

## Result

The [frozen proposal](research/prices-only-baseline.md) kept the original dates and 11:00 Berlin information deadline. Across 273 days, the model improved median absolute error but lost on the registered interval score. Its central 95% band covered 60.1% of quarters, versus 92.2% for the reference. Retain the seasonal reference for subsequent comparisons. This result establishes reproducibility on previously inspected dates. [Run identities, scores and verification](../../forecasts/reports/evaluation.json).

The [retrospective review](research/baseline-review.md) covers the superseded three-feature-set experiment.

On 2026-11-24, replay through the accepted run's archived code and locked runtime
verified predictions and scores. The archive issuance implementation also
reproduced all 26,204 prediction rows and the full score report exactly using the
same frozen snapshot and saved models. [Reproduction command](../../forecasts/execution/README.md#run-and-reproduce)
