# Day-ahead price forecasts

Forecast the DE–LU auction price for each quarter of tomorrow’s Berlin delivery day. Each issue contains five price quantiles from the fitted model and five from the seasonal reference. The information deadline is 11:00 Berlin on the preceding day. [Scientific contract](../wiki/price-forecasting/germany-luxembourg.md)

## Follow one forecast

| What you want to inspect | Where to start |
|---|---|
| Which price versions were eligible at the deadline? | [Inputs](inputs/README.md) |
| Which features enter the monthly fit and the daily prediction? | [Model](model/README.md) |

The product root holds the public commands and three shared contracts: [run settings](config.py), [Berlin delivery times](market.py), and [source fingerprints](provenance.py). The [registered settings](run-config.json) identify the fixed baseline.

## On-demand day-ahead forecast

From the repository root, use the [locked Pixi environment](../README.md#local-installation). The November fit needs a verified training snapshot covering the October 2025 warmup through October 31, 2026. Fit once for that delivery month. Issue each day from a snapshot with fresh price history. Use a new output path for each edition.

```sh
pixi run --locked python -m forecasts.monthly_fit --fit-day 2026-11-01 --snapshot "$TRAINING_SNAPSHOT" --output "$MONTHLY_FIT"
pixi run --locked python -m forecasts.daily --delivery-date 2026-11-25 --snapshot "$ISSUE_SNAPSHOT" --run "$MONTHLY_FIT" --output forecast-2026-11-25.json
```

[Monthly fitting](monthly_fit.py) publishes the bundle. [Daily issuance](daily.py) checks its identity, selects prices received by issue time, and writes the local edition by the deadline. A missing required input stops issuance. Add `--replay` for historical reconstruction under the recorded price availability assumptions.

## Development

```sh
pixi run --locked test-forecast
pixi run --locked typecheck
pixi run --locked component-imports
```

The [archive audit](source_audit/README.md) checks the retained price, weather and demand sources. Its recorded-year test needs `FORECAST_BASELINE_SNAPSHOT` set to the verified historical snapshot directory. [Infrastructure](infra/README.md) owns private S3 storage.
