# Day-ahead forecast evaluation

The [forecast design](germany-luxembourg.md) fixes five price quantiles and weighted interval score as the main measure, agreed 2026-10-09. This page is the small evaluation contract; it does not require a general experiment platform.

### Quantiles

A price quantile at probability `q` is a price below which the outcome is predicted to fall with probability `q`. Output `q=[0.025, 0.25, 0.50, 0.75, 0.975]` per delivery quarter. The median is `q50`; `[q25,q75]` is the central 50% interval and `[q2.5,q97.5]` the central 95% interval.

Train each feature set with one CatBoost model using `MultiQuantile:alpha=0.025,0.25,0.5,0.75,0.975`. All outputs use the same input row. Sort each predicted vector into nondecreasing order before evaluation and publication; retain raw outputs and report the fraction that crossed before sorting. This is a fixed implementation rule, not a post-test correction. These five numbers do not specify arbitrary tail probabilities or the joint evolution of a day's prices. [CatBoost objective](https://catboost.ai/docs/en/concepts/loss-functions-regression#MultiQuantile).

### WIS

**Weighted interval score** rewards narrow intervals and penalises observations outside them. For an interval `[l,u]` with nominal coverage `1−α` and actual price `y`:

```text
interval_score(α) = (u−l) + (2/α) max(l−y,0) + (2/α) max(y−u,0)
weighted_interval_score =
  [0.5 |y−q50| + 0.25 interval_score(0.5) + 0.025 interval_score(0.05)] / 2.5
```

Lower is better, in €/MWh. Average per-quarter scores over the common target rows. The fixed five-quantile objective is aligned with this score: the score equals twice the mean pinball loss across those quantiles. Verify implementation against hand-calculated cases and an established scoring implementation before the first model comparison. [Energy-Arena definitions](https://energy-arena.org/faq).

Report median-price mean absolute error, root mean squared error of that same median, 50%/95% coverage and mean interval width. The squared-error diagnostic does not make the median a conditional-mean forecast. Break out results by month and demand availability, with counts and forecast coverage. These subgroup comparisons are descriptive, not proof of demand's causal contribution.

[Energy-Arena](https://energy-arena.org/challenges) ranks quantile forecasts by weighted interval score, point forecasts by root mean squared error and ensembles by continuous ranked probability score. Match dates, target resolution and information cutoff before comparing scores. Entry is undecided; no submission is part of the initial build.

## Replay

- Fix the data snapshot, transformations, locations, training dates, monthly refit schedule, settings, seed and references before fitting. Freeze them in a saved run manifest. No test-guided feature or parameter search.
- Train only on earlier dates and labels available by each fold's first forecast issue time. Recompute each day's price lags from information available by that day's 11:00 deadline, even while reusing a monthly fitted model. Any learned preprocessing uses training data only.
- Keep UTC timestamps internally; derive German calendar features explicitly. Include the actual 92/96/100 quarter-hours on clock-change days and apply the [agreed defaults](#defaults).
- Retain every evaluation day and use identical target rows for model and reference. Missing demand uses the agreed missing value and indicator. Never fill future features with realised observations or later revisions.
- Save every prediction failure and report total delivery coverage. A fallback is part of the forecasting system and is scored as such. Missing target truth cannot be fabricated: disclose it for all models together.

### Defaults

Agreed 2026-10-09; save these rules in the run manifest before fitting.

| Choice | Rule |
|---|---|
| Past-price clock matching | Match the same German local quarter on the earlier date. Average both prices if that quarter occurred twice; mark it missing if it did not occur. Keep both delivery quarters on the autumn clock-change day. |
| Weather gaps | Leave individual values missing for CatBoost and retain missing-value flags in the dataset. Do not fill with observed weather or later revisions. |
| Calendar | Quarter of day, day of week, month and a Germany-wide public-holiday flag, identical across model comparisons. |
| Source failure | When an entire source is unavailable for the delivery day, use the first applicable option: full model → model without demand → prices/calendar model → simple reference. Weather failure skips both weather-dependent models. Choose from input availability and execution success, never predicted prices or test scores. Record the selected fallback and reason. |

Partial gaps remain missing inputs. The simple reference can use retained training history when current input retrieval fails. Every fallback produces the same five quantiles and is included in the system score.

### Controls

Fit three fixed feature sets with the same CatBoost settings, seed, training dates and calendar features: prices/calendar; prices/calendar/weather; prices/calendar/weather/demand. Compare them on identical dates to measure what weather and demand each add. Report each model separately as well as the system with its fallback rules. This is a fixed comparison, not a parameter search.

## Reference

The simple price estimate is the equal-weight average of yesterday's and last week's same-local-quarter prices. Apply the clock-matching rule above. If one price is missing, use the other; if both are missing, use the training-history median for that local quarter.

Calculate historical errors as actual price minus that estimate, using training dates only. Replay the same missing-price rules; any median used for a historical estimate must use only earlier available history. Exclude initial rows with insufficient history from error estimation, not evaluation dates, and record their count.

Pool errors across all hours and days. Add their five empirical quantiles to the estimate to form the reference forecast. Recompute the error quantiles at each monthly fit from training data only, using linear quantile interpolation. This gives the reference the same interval widths at every delivery quarter within a fold. Require sufficient history for all reference outputs before the first evaluation date. Do not fit these offsets on evaluation outcomes.

## Evidence

Report the score difference against the reference with paired resampling of contiguous seven-day blocks of whole German local days. Do not treat quarter-hours as independent or stitch across missing dates/separate evaluation windows. Fix the resampling seed/count and recompute aggregate scores from the sampled rows. Show effect size and uncertainty; do not claim an established gain if its interval includes no improvement.

Preserve raw inputs or content hashes, request and retrieval metadata, row-level availability flags, configuration, library versions, raw/ordered quantiles, reference forecasts, per-quarter outcomes and the report. A change after looking at scores starts a new development experiment. Forecast-quality improvement does not establish trading profitability.

### Limitations

The proposed first fit uses October–December 2025 to predict January 2026; later monthly fits add the preceding months. This is a date choice, not a limit imposed by missing demand. More months can be used for initial training within the assembled year, leaving fewer months for evaluation. Earlier compatible data has not been established.

One annual cycle gives limited evidence about rare extreme prices. Many consecutive quarter-hours can describe a single storm or price event. A nominal 95% range is therefore not proof of reliable coverage during extremes. Recommended additional checks are separate counts below and above the predicted ranges, and coverage by delivery hour; these are review recommendations, not added first-build acceptance criteria.

Historical input timing remains subject to the [availability limits](data-sources.md#availability). Prospective forecasts made after settings are fixed provide fresh evidence. Acceptance of a reproducible report does not establish readiness for daily use; see the [continuation decision](germany-luxembourg.md#continuation).

## Freeze

As of 2026-10-09, quantile output, scoring, [defaults](#defaults), [controls](#controls) and reference construction are settled. Exact train/test dates, remaining price-feature definitions, fixed model settings and minimum reference-history counts still need to be recorded before fitting. Changes after inspecting scores belong to a separate experiment.

A practical candidate is initial training in the final quarter of 2025 followed by monthly expanding-window evaluation during January–September 2026, allowing the necessary price-lag warmup. Confirm the assembled data supports it before freezing. This is retrospective evaluation: August–September 2026 were already inspected in the point-model diagnostic. Do not call them an untouched final holdout. Prospective forecasts after freezing provide fresh evidence; the single historical year does not establish multi-year robustness.
