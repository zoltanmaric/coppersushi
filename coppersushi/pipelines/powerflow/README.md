# Power Flow preparation

[Product pipelines](../README.md) · [Frontend](../../frontend/README.md)

Owns solved-network loading, snapshot calculations and typed data export.
`dataset.py` defines numeric topology and interval contracts; `export.py` reuses the
existing snapshot calculations. I/O stays in `data_sources/`.

```mermaid
flowchart LR
  network["Solved PyPSA network"] --> extraction["Snapshot calculations"]
  extraction --> export["Validated numeric dataset"]
  export --> files["Immutable metadata and interval files"]
  files --> manifest["Manifest published last"]
  manifest --> browser["Browser-built layers"]
```

Nodes carry WGS84 coordinates, country and voltage. Branch identity is component plus
name; positive signed flow follows bus0 to bus1. Intervals retain node generation,
available capacity and load for browser tooltips. Missing optional values are null.
Validation rejects incomplete intervals, duplicate identities and non-finite numbers.
The v2 publication contains numeric data for browser rendering. Candidate networks use the same export command with `--serve`; all map rendering
runs in the browser.

From the repository root:

```sh
python -m coppersushi.pipelines.powerflow.data_sources.dataset coppersushi/networks/opf-2024-08-29.nc coppersushi/data/browser/data/opf/v2/opf-2024
```

Add `--bucket` to publish data objects before their manifest. Deployment order and
rollback belong to the [runbook](../../infra/lambda/README.md). Tests are colocated;
run `pixi run test-app` from the root.
