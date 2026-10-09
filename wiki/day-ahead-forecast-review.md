# Day-ahead forecast implementation review

Assessment dated 2026-10-09 of the [implementation spec](specs/day-ahead-price-forecast.md), [design](day-ahead-price-forecast.md), [data evidence](day-ahead-forecast-data.md) and [evaluation contract](day-ahead-forecast-evaluation.md). Recommendations here are proposed changes, not agreed scope.

## Verdict

Implement the bounded research experiment. Its output is evidence about forecast quality; deployment or competitive usefulness needs a separate decision. One tabular model, explicit uncertainty, chronological evaluation and scored fallbacks are appropriate scope. The weighted interval score formula agrees with [the published definition](https://energy-arena.org/faq); no scoring redesign is needed.

## Findings

1. **The replay acceptance claim exceeds the evidence.** The spec requires excluding later revisions, but historical weather publication times and price-feed latency are unaudited. [Open-Meteo](https://open-meteo.com/en/docs/previous-runs-api) documents the 48-hour lead, which supports a conservative timing assumption, not proof of historical retrieval. The weather compatibility check happened after the deadline. [ENTSO-E's schema](https://transparencyplatform.zendesk.com/hc/en-us/articles/36492900251281-DayAheadTotalLoadForecast-6-1-B-r3) lists `UpdateTime` without establishing original public availability. Separate verified availability from assumed availability in the manifest and report. Start pre-deadline input snapshots alongside research; a full daily forecasting service is unnecessary for that check.

2. **Demand missingness may encode archive revisions rather than operational absence.** All October 1–November 11 demand is rejected by the retrospective timestamp screen. A later replacement can hide a forecast that was available on time. Retaining those dates is correct, but identical missing-value code cannot establish identical historical and live input distributions. The availability indicator may also act as a date/regime proxy. Label this distinction and compare with an otherwise identical model excluding demand; availability subgroup scores alone cannot isolate its contribution.

3. **The reference cannot isolate the value of fundamentals.** Beating a yesterday/week-ago blend could reflect nonlinear price/calendar modelling alone. Add one fixed price-and-calendar-only MultiQuantile control with the same folds and settings. Together with the no-demand control, this separates the incremental value of weather and demand without a model search. Keep the simple distributional reference as the minimum benchmark.

4. **Cold-start and tail evidence are weak.** The suggested first fit has only the final quarter of 2025, minus lag warmup; the evidence has one annual cycle. Thousands of correlated quarter-hours are not thousands of independent weather or price regimes. Treat January as a cold-start fold, show lower- and upper-tail miss rates separately, and inspect coverage by delivery hour as well as month. A nominal 95% interval is not yet demonstrated reliable protection against rare price events. Historical improvements need prospective confirmation; the inspected months are already correctly labelled retrospective.

5. **Several unresolved defaults materially affect the result.** Freeze exact feature definitions, holiday treatment, daylight-saving lag mapping, missing-weather handling, complete-input fallback, reference residual pooling and minimum history before fitting. These are small decisions, but not interchangeable: pooled residuals give every delivery quarter the same interval offsets, whereas conditioning changes the benchmark. The reused diagnostic's complete-day filtering and missing clock-change lags are unsuitable as production defaults, as its README already warns.

6. **There is no decision rule after the report.** Accepting a measured loss is scientifically sound. Define a separate continuation gate: usable pre-deadline inputs, a meaningful and credible score improvement over the stronger control, and acceptable coverage/failure behaviour for the intended use. Neither a universal percentage threshold nor a trading-profit claim follows from this spec. If the goal is battery scheduling or daily spread risk, marginal quarter-hour quantiles do not supply the necessary joint price paths; the design acknowledges this limitation.

## Next

Resolve the replay claim and freeze the remaining defaults; then implement dataset, references, fixed controls and report. Begin timestamped input collection in parallel. Retain the twelve locations and CatBoost choice for this experiment. More algorithms, paid feeds, network constraints and a dashboard do not resolve the principal uncertainties above.
