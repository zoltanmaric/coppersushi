# Forecasts

[Forecast overview](../README.md) · [Tracked execution](../execution/README.md)

To read the computation in a fresh checkout, open the [stage and connection definitions](pipeline.json). To explore them with results, export a saved run from the repository root. The exporter reads the run’s latest decision from its MLflow store. Set `FORECAST_DATA_ROOT` to the directory containing `tracking/` when that store lives outside the default data root.

```sh
pixi run --locked python -m forecasts.explain --run data/forecasts/runs/RUN_ID --output data/forecasts/explainers/RUN_ID
```

Open the exported `index.html` in a browser. Keep it with the adjacent scripts, styles and `data.js` for offline use. Choose a new directory for each export. Re-export after a review decision changes.

The viewer shows individual delivery days, model and reference quantiles, full-period and monthly scores, and run provenance. **How it works** owns the forecast architecture. Edit its stages and explanations in [pipeline.json](pipeline.json). The [exporter](explain.py) verifies consumed artifact hashes and reconciles scores against predictions. When a linked wiki page changes, review the narrative and update [sources.json](sources.json). The forecast CI suite checks each recorded SHA-256 against the wiki file and its committed bytes using the export validator.

Run the DOM integration check against an export.

```sh
npm install --prefix data/forecasts/ui-test --no-save jsdom@26.1.0
NODE_PATH="$PWD/data/forecasts/ui-test/node_modules" node forecasts/web/tests/viewer.cjs data/forecasts/explainers/RUN_ID
```
