# Tracked forecast execution

[Forecast overview](../README.md) · [Reproducibility contract](../../wiki/price-forecasting/forecast-infrastructure.md#promise)

[Runner](run.py) freezes the repository, run configuration, proposal and Pixi definitions. [Metaflow](flow.py) runs the [shared evaluator](../evaluation/workflow.py) in one step. A retry of this step repeats feature construction, monthly fitting and scoring. [Tracking](tracking.py) records the execution, method comparisons and final manifest in local MLflow.

## Run and reproduce

Run from a clean checkout at the repository root with a committed research proposal.

```sh
pixi run --locked python -m forecasts.run run --snapshot "$BASELINE_SNAPSHOT" --proposal wiki/price-forecasting/research/prices-only-baseline.md
pixi run --locked python -m forecasts.run reproduce RUN_ID --snapshot "$BASELINE_SNAPSHOT"
```

The runner installs the locked Pixi `runtime` from the archived code. Package downloads require network access when the cache is incomplete. Reproduction verifies saved-model predictions and scores on the recorded platform. Supply `--profile` and `--bucket` together in place of `--snapshot` to load the archived snapshot from S3.

The data root defaults to `data/forecasts/`. Keep `runs/` to preserve code, environment, configuration and model artifacts. Each reproduction attempt has its own directory under `reproductions/RUN_ID/`, with its status in `attempt.json` and successful verification in `result/verification.json`. Set `FORECAST_DATA_ROOT` consistently for execution, reproduction and review to use a separate store. For smoke tests, use a temporary store and `run --exploratory` to execute the current checkout.

## Review in MLflow

```sh
pixi run --locked mlflow ui --backend-store-uri "sqlite:///${FORECAST_DATA_ROOT:-$PWD/data/forecasts}/tracking/mlflow.db" --host 127.0.0.1 --port 5001
# In another terminal:
pixi run --locked python -m forecasts.review_views --run MLFLOW_RUN_ID
```

Use the parent execution’s MLflow ID. The command installs the versioned [shared views](review-views.json) and prints links to its method comparisons, ordered by weighted interval score, and the experiment’s execution history. Comparison durations measure result logging. The parent duration spans orchestration and computation.

```sh
pixi run --locked python -m forecasts.review --run MLFLOW_RUN_ID --conclusion "$CONCLUSION_JSON"
```

The conclusion provides `result`, `limitations`, `decision` and optional `evidence_artifacts` or `evidence_status`. The command saves it under `research/conclusion.json` by default and updates the run’s Notes. Use the [viewer](../web/README.md) to explore a saved run.
