# Forecast inputs

[Forecasts](../README.md) · [Model](../model/README.md)

[Snapshot collection](snapshot.py) validates and hashes provider archives, writes typed Parquet tables, and publishes the manifest last. Loading verifies the snapshot ID, hashes, row counts, and [normalized input models](schemas.py). Each model supplies its Parquet schema and manifest description. The [v1 compatibility test](tests/test_schemas.py) checks both against the frozen format. The manifest records the code revision, environment, and source retrieval evidence.

[InputReader.price_history()](selection.py) selects earlier delivery days and revisions available by the issue cutoff. Live selection also requires retrieval by the actual issue time. Historical selection permits recorded timing assumptions. See the [point-in-time contract](../../wiki/price-forecasting/data-sources.md#point-in-time).

## Refresh price history

Run from the repository root. For November 25 delivery, require every Berlin quarter on November 11, 18, 23 and 24 (lags of 14, 7, 2 and 1 days). A missing quarter on a required date stops collection. Use `--start` and `--end-exclusive` for contiguous training history. Choose new paths for the raw archives and snapshot.

```sh
pixi run --locked python -m forecasts.snapshot refresh \
  --delivery-date 2026-11-25 \
  --data-root data/forecasts/new-raw --directory data/forecasts/new-snapshot
```

## Publish or load a fixed snapshot

Use AWS CLI v2, an authenticated local profile, and the [private input bucket](../infra/README.md). To collect the recorded year, put the three archives from the [baseline inventory](baseline-inputs.json) under `data/forecasts/`. Use `--data-root` to reuse archives from another checkout.

```sh
pixi run --locked python -m forecasts.snapshot --profile YOUR_LOCAL_PROFILE --bucket YOUR_PRIVATE_BUCKET collect --publish
pixi run --locked python -m forecasts.snapshot --profile YOUR_LOCAL_PROFILE --bucket YOUR_PRIVATE_BUCKET load SNAPSHOT_ID
```

Replace `SNAPSHOT_ID` with the ID printed at collection. The default region is `eu-west-1`. Use `--directory` on the subcommand to select a different snapshot path. Loading uses the published S3 objects directly.

[Audit archived weather, demand, and price coverage](../source_audit/README.md).
