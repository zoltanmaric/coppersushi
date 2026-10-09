# Germany–Luxembourg day-ahead price forecast

An independent, public-fundamentals forecast under `forecasts/`. The first version is one useful, reproducible model, with measured performance. It does not depend on the power-flow application.

## Contract

Agreed project design, 2026-10-09:

| Choice | Decision |
|---|---|
| Market | Germany–Luxembourg |
| Delivery resolution | Every quarter-hour of the next German local day |
| Information deadline | 11:00 Europe/Berlin on the preceding day |
| Model | One fixed CatBoost configuration, compared across three [feature sets](day-ahead-forecast-evaluation.md#controls) |
| Output | Five [price quantiles](day-ahead-forecast-evaluation.md#quantiles): 2.5%, 25%, 50%, 75%, 97.5% |
| Main score | [Weighted interval score](day-ahead-forecast-evaluation.md#wis) |
| Inputs | Past prices, calendar, weather and usable demand forecasts |
| Missing demand | Missing numerical value plus an availability indicator; whole-source failure follows the agreed [fallback rules](day-ahead-forecast-evaluation.md#defaults) |
| Evaluation | Chronological, all dates retained; overall, monthly and demand-availability results |
| Initial data budget | Free sources |

The median is the central price estimate. The other four outputs give 50% and 95% central prediction ranges. They describe uncertainty for each quarter-hour, not complete scenarios for a whole day's price path. CatBoost's [MultiQuantile objective](https://catboost.ai/docs/en/concepts/loss-functions-regression#MultiQuantile) supports this in one fitted model.

## Inputs

[Data contracts and evidence](day-ahead-forecast-data.md) define the price source, fixed-lead weather, coordinates and demand timing screen. The starting weather set is the twelve tested locations; no larger geographical search is required before the first build. This is an implementation default supported by the diagnostic, not a claim that twelve is optimal.

Earlier auction prices, generator-threshold models, outages, fuel/carbon feeds, neighbours and network constraints are outside the first build. Electricity Maps' price forecast is not a feature or target anchor. Its live data access does not establish historical forecast runs before the chosen deadline; [access findings](electricity-maps-api.md#forecast-history).

## Evidence

The preliminary point-model experiment found that broader geography mattered more than fresher weather: twelve locations improved absolute error roughly 5–6% over three in one matched repeat. Fresher weather improved average error only 0.68% across three repeats, with inconsistent direction. This is limited retrospective evidence, not proof of annual or commercial competitiveness. [Experiment results and limits](day-ahead-forecast-data.md#diagnostics).

## Start

Read the [implementation spec](specs/day-ahead-price-forecast.md), then the [evaluation contract](day-ahead-forecast-evaluation.md). Build the reproducible historical dataset first. Resolve and record the remaining mechanical defaults before fitting; do not reopen settled scope without contradictory evidence.

As of 2026-10-09, the handover and diagnostic evidence exist; the five-quantile model, production dataset pipeline and daily forecast runner do not. Competition entry, publishing forecasts and deployment are separate work.
