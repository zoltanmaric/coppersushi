# Archived-source audit

[Forecasts](../README.md) · [Input snapshots](../inputs/README.md)

[The audit](dataset.py) checks weather, demand, and price coverage from the full historical archive. It writes `quarters.csv` and `report.json` to `data/forecasts/dataset/` by default.

```sh
pixi run --locked python -m forecasts.dataset --snapshot data/forecasts/loaded-snapshot
```

Omit `--snapshot` to use verified raw archives. Set `FORECAST_BASELINE_SNAPSHOT` to the recorded snapshot directory to include the [historical coverage regression](tests/test_baseline.py) in the forecast test suite.

The [verified snapshot receipt](verified-snapshot.json) records the retained archive's coverage counts and the successful S3 publish and download checks. [Historical evaluation](../evaluation/README.md) documents the price-model comparison.

## Compare cleared auction prices

Compare the saved SMARD archive with direct Electricity Maps observations for the DE–LU bidding zone. Each requested day reports native delivery quarters, source coverage, overlap and disagreements in €/MWh. The receipt time belongs to this comparison. A later check cannot establish what was available at a previous forecast deadline.

```sh
pixi run --locked python -m forecasts.source_audit.smard_vs_electricity_maps_auction_prices path/to/prices.zip 2026-11-20 2026-11-21 2026-11-24
```

Supply the existing `ELECTRICITY_MAPS_API_KEY` credential. The comparison uses the [shared price reader](../../coppersushi/pipelines/data_sources/electricity_maps_auction_prices.py). Critical Elements owns its cache and recovery from JAO spreads. Forecast issuance still reads its registered SMARD snapshot.
