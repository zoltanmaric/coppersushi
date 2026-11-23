# Germany–Luxembourg day-ahead price forecast

An independent, public-fundamentals forecast under `forecasts/`. The first version is one useful, reproducible model, with measured performance. It does not depend on the power-flow application.

## Contract

Current project design:

| Choice | Decision |
|---|---|
| Market | Germany–Luxembourg |
| Delivery resolution | Every quarter-hour of the next German local day |
| Information deadline | 11:00 Europe/Berlin on the preceding day |
| Model | One fixed CatBoost configuration, compared with the [seasonal price reference](evaluation.md#reference) |
| Output | Five [price quantiles](evaluation.md#quantiles): 2.5%, 25%, 50%, 75%, 97.5% |
| Main score | [Weighted interval score](evaluation.md#wis) |
| Inputs | Past prices and German calendar |
| Complete inputs | Require complete eligible price history for fitting and issuance. Training and scoring require complete labels at their respective cutoffs. [Evaluation rules](evaluation.md#defaults). |
| Evaluation | Chronological, all dates retained; overall and monthly results |
| Initial data budget | Free sources |

The median is the central price estimate. The other four outputs give 50% and 95% central prediction ranges. They describe uncertainty for each quarter-hour, not complete scenarios for a whole day's price path. CatBoost's [MultiQuantile objective](https://catboost.ai/docs/en/concepts/loss-functions-regression#MultiQuantile) supports this in one fitted model.

## Inputs

The [price contract](data-sources.md) governs this baseline. Weather and demand are [deferred research candidates](research/incremental-input-value.md).

Earlier auction prices, generator-threshold models, outages, fuel/carbon feeds, neighbours and network constraints are outside the first build. Electricity Maps' price forecast is not a feature or target anchor. Its live data access does not establish historical forecast runs before the chosen deadline; [access findings](../electricity-maps-api.md#forecast-history).

## Evidence

The preliminary point-model experiment found that broader geography mattered more than fresher weather: twelve locations improved absolute error roughly 5–6% over three in one matched repeat. Fresher weather improved average error only 0.68% across three repeats, with inconsistent direction. This is limited retrospective evidence, not proof of annual or commercial competitiveness. [Experiment results and limits](data-sources.md#diagnostics).

## Start

Read the [implementation spec](../../specs/day-ahead-price-forecast.html), then the [evaluation contract](evaluation.md). The [infrastructure design](forecast-infrastructure.md) starts with S3 inputs and local Metaflow/MLflow runs. Build the reproducible historical dataset first. Resolve and record the remaining mechanical defaults before fitting; do not reopen settled scope without contradictory evidence.

Typed inputs, local evaluation, execution tracking and a daily forecast command are available. Competition entry, public forecast publishing and cloud deployment are separate work.

### Continuation

The first build is a bounded research experiment. A measured loss is a useful result. Further investment needs a separate decision based on usable pre-deadline inputs, credible improvement over the prices/calendar model, and acceptable missing forecasts and uncertainty ranges for the intended use. The performance threshold and intended daily use remain open; this is a review recommendation, not an additional acceptance condition.

The five per-quarter quantiles do not describe how prices move together across a day. They are insufficient on their own for assessing daily spread risk or battery scheduling under uncertainty.
