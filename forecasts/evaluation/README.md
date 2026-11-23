# Historical evaluation

[Forecasts](../README.md) · [Inputs](../inputs/README.md) · [Model](../model/README.md) · [Tracked execution](../execution/README.md)

[evaluate()](workflow.py) builds point-in-time features, calls [forecast_months()](backtest.py) to fit and predict in expanding monthly windows, then passes fixed predictions and realised prices to [score_forecasts()](scoring.py). The score compares the five-quantile price model and seasonal reference over the same delivery quarters. See the [evaluation contract and result](../../wiki/price-forecasting/evaluation.md) for metrics and interpretation.

```sh
pixi run --locked python -m forecasts.evaluation --snapshot data/forecasts/loaded-snapshot --output data/forecasts/evaluations/baseline
```

Use a new output directory. `--config` defaults to the [registered run settings](../run-config.json), which specify the required snapshot ID and evaluation period. The command writes `features.parquet`, fitted models, `predictions.parquet`, and `report.json`. Missing eligible price history, fit labels, or scoring truth stops the run before it publishes a score. Use [tracked execution](../execution/README.md) to retain the run’s environment and register its outputs with MLflow.
