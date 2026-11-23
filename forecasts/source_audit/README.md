# Archived-source audit

[Forecasts](../README.md) · [Input snapshots](../inputs/README.md)

[The audit](dataset.py) checks weather, demand, and price coverage from the full historical archive. It writes `quarters.csv` and `report.json` to `data/forecasts/dataset/` by default.

```sh
pixi run --locked python -m forecasts.dataset --snapshot data/forecasts/loaded-snapshot
```

Omit `--snapshot` to use verified raw archives. Set `FORECAST_BASELINE_SNAPSHOT` to the recorded snapshot directory to include the [historical coverage regression](tests/test_baseline.py) in the forecast test suite.

The [verified snapshot receipt](verified-snapshot.json) records the retained archive's coverage counts and the successful S3 publish and download checks. [Historical evaluation](../evaluation/README.md) documents the price-model comparison.
