# Spec: Germany–Luxembourg price forecast

Implementation working memory, 2026-10-09. Authoritative scope: [forecast design](../price-forecasting/germany-luxembourg.md). Implementation home: `forecasts/`, independent of the map/power-flow application.

## Problem

Build one useful public-fundamentals model for next-day quarter-hour prices, issued by 11:00 German local time, with five uncertainty quantiles and a reproducible historical evaluation.

## Next

1. Assemble a reproducible dataset from the [verified sources and local evidence](../price-forecasting/data-sources.md). Reuse saved inputs and audit scripts. Keep downloaded payloads in ignored `data/forecasts/`; keep source, small configuration and reports in `forecasts/`. Diagnose new contradictions rather than restarting completed source research.
2. Freeze exact dates, remaining price features, model settings and minimum reference history in a run manifest; implement the [evaluation contract](../price-forecasting/evaluation.md), including the agreed [simple defaults](../price-forecasting/evaluation.md#defaults) and [three feature-set comparisons](../price-forecasting/evaluation.md#controls). Fit one CatBoost MultiQuantile configuration across those feature sets on successive chronological folds and publish the local report. Subsequent daily collection/inference can follow once this path works.

No broader hyperparameter search, foundation-model comparison, network-constraint model, dashboard, paid data procurement or competition submission is required for this first result.

The [input-availability limits](../price-forecasting/data-sources.md#availability) remain unresolved: distinguish verified timing from assumptions before claiming a faithful historical replay. Additional [review recommendations](../price-forecasting/evaluation.md#limitations) are separate from the agreed acceptance criteria.

## Acceptance

- [ ] Dataset replay respects the cutoff, excludes later revisions, flags missing inputs and retains clock-change dates; its counts reconcile with the supplied evidence.
- [ ] Five ordered, finite prices per evaluation quarter, with the agreed clock-change, missing-weather, calendar and fallback rules applied; failures/fallbacks explicit and negative prices permitted.
- [ ] Training never uses later labels or evaluation-fitted calibration; demand gaps do not select the test population.
- [ ] Weighted interval score verified on known cases and a reference implementation; median error, interval coverage/width and daily coverage reported on identical rows for all three feature sets, the fallback system and the distributional reference.
- [ ] Monthly and demand-availability breakdowns, paired seven-day-block comparison uncertainty and limitations accompany the headline result.
- [ ] Inputs, configuration, dependencies and predictions reproduce the report from documented commands; no secrets, provider-restricted payloads or machine-specific private paths in tracked files.

A measured loss is a valid research result; acceptance does not require beating the reference. Uncertainty calibration is measured, not assumed from nominal interval labels. No first-build performance result is available as of the handover.
