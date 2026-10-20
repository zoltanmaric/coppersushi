# Forecasts

Independent Germany–Luxembourg price forecasting. The [implementation spec](../wiki/specs/day-ahead-price-forecast.md) lists remaining work; the [infrastructure design](../wiki/price-forecasting/forecast-infrastructure.md) owns the storage contract.

## Setup

Python 3.11+ with IANA timezone data, AWS CLI v2 and an authenticated **user-local AWS profile**. Profile configuration and credentials belong outside this repository, normally in the user's AWS configuration directory. Never check in credentials, profile files, bucket names, Terraform state or account-specific settings. Generated inputs, snapshots, reports and environments stay in ignored `data/forecasts/`.

From the repository root:

```sh
python3 -m venv data/forecasts/venv
data/forecasts/venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple -r forecasts/requirements.txt
data/forecasts/venv/bin/python -m unittest discover -s forecasts/tests -v
```

The Parquet dependency is pinned; snapshot manifests also record Python/PyArrow versions, the requirements hash, code revision and whether code was uncommitted. Exploratory snapshots are marked; they do not establish an accepted reproducible model run.

## S3 inputs

Collect or load immutable input snapshots. [Input and storage contracts](../wiki/price-forecasting/forecast-infrastructure.md#inputs).

To collect the recorded year, place the three exact archives at their [manifest paths](evidence/payload-manifest.json), under `data/forecasts/`. The [evidence instructions](evidence/README.md) describe their sources. `--data-root` can reuse another checkout's downloads. Recollection from mutable feeds may produce different bytes; the recorded experiment requires matching archives or access to the private S3 snapshot.

```sh
data/forecasts/venv/bin/python -m forecasts.snapshot --profile YOUR_LOCAL_PROFILE --bucket YOUR_PRIVATE_BUCKET collect --publish
```

Use the printed snapshot ID explicitly:

```sh
data/forecasts/venv/bin/python -m forecasts.snapshot --profile YOUR_LOCAL_PROFILE --bucket YOUR_PRIVATE_BUCKET load SNAPSHOT_ID
data/forecasts/venv/bin/python -m forecasts.dataset --snapshot data/forecasts/loaded-snapshot
```

`--region` defaults to `eu-west-1`. Collection/publication accept `--directory`; loading also accepts it. A fresh checkout can load the selected snapshot directly, without raw downloads or source-provider requests.

## Features

Build diagnostic feature outputs from a loaded snapshot:

```sh
data/forecasts/venv/bin/python -m forecasts.dataset --snapshot data/forecasts/loaded-snapshot
```

Outputs: `quarters.csv` and `report.json` under ignored `data/forecasts/dataset/`. The [input timing contract](../wiki/price-forecasting/data-sources.md#point-in-time) and [feature/evaluation contract](../wiki/price-forecasting/evaluation.md#defaults) define selection and transformations. See the viewer’s **How it works** for the pipeline.

## Infrastructure

[Terraform](infra/main.tf) manages one private S3 bucket and its controls: all public access blocked, ACLs disabled, AES256 encryption, versioning, TLS-only access and seven-day abort of incomplete multipart uploads. Bucket destruction is prevented. No cloud compute, scheduling or orchestration is provisioned.

Terraform 1.5+ and the user-local AWS profile are required. Keep state and variables local and ignored; preserve state to manage the same bucket later:

```sh
terraform -chdir=forecasts/infra init
terraform -chdir=forecasts/infra apply -state="$PWD/data/forecasts/terraform.tfstate" -var=profile=YOUR_LOCAL_PROFILE
terraform -chdir=forecasts/infra output -state="$PWD/data/forecasts/terraform.tfstate" -raw bucket_name
```

For an existing bucket, import the bucket and its public-access, ownership, encryption, versioning, lifecycle and policy resources before applying, with `-var=bucket_name=YOUR_PRIVATE_BUCKET`. Inspect the plan; adoption must not replace the bucket. [Terraform S3 import documentation](https://registry.terraform.io/providers/hashicorp/aws/5.100.0/docs/resources/s3_bucket).

Uploads and provider installation may exceed a minute; follow the repository's job-supervision workflow. As of 2026-10-09, typed inputs, local training/evaluation and accepted-run reproduction are implemented. Cloud execution remains planned.

## Local model evaluation

The [run configuration](run-config.json) fixes the training period, feature sets and model settings. The [evaluation contract](../wiki/price-forecasting/evaluation.md) owns the comparison, calibration, timing and scoring rules.

Use **Python 3.12.13** on the recorded platform for accepted reproduction. Install the complete dependency lock rather than just direct requirements:

```sh
data/forecasts/venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple -r forecasts/requirements-lock.txt
data/forecasts/venv/bin/python -m forecasts.run run --snapshot data/forecasts/loaded-snapshot
```

The snapshot must match the frozen configuration. Accepted runs require a clean, committed checkout. `--exploratory` permits development runs but disqualifies them from accepted reproduction. The command freezes the configuration, full feature lists, snapshot, code revision, Python/platform/packages and lock hash before starting local Metaflow. Each attempt gets a unique run identifier and directory at `data/forecasts/runs/RUN_ID/`. Repeat the same command to retry; prior attempts remain intact. The manifest and MLflow tag `experiment_fingerprint` identify identical frozen code, configuration and environment across attempts.

Metaflow saves local metadata/artifacts under `data/forecasts/metaflow/`. MLflow uses `data/forecasts/tracking/mlflow.db` and a local artifacts directory. A parent experiment links code, snapshot and Metaflow identifiers; child runs compare the three feature sets, reference and fallback system. The parent starts before input loading and evaluation, and finishes with the computation’s success, failure or interruption status. Comparison children summarize monthly fits; their durations measure result logging, not training. Historical runs retain their original timestamps and are labeled logging-only, with compute duration unknown. A forced process kill or tracking-store outage may require reconciling a still-running record. Preserve these ignored directories. They are local records, without cloud backup.

The run directory preserves predictions, fitted models, configuration, reports and checksum provenance. Keep it for reproduction and viewer export. [Artifact contract](../wiki/price-forecasting/forecast-infrastructure.md#iteration).

To inspect the local comparisons:

```sh
data/forecasts/venv/bin/mlflow ui --backend-store-uri "sqlite:///$PWD/data/forecasts/tracking/mlflow.db" --host 127.0.0.1
```

From a clean checkout, preserve the accepted run directory and access to its S3 snapshot. One command restores committed code into an ignored directory, creates the locked environment, reloads the fixed input from S3, restores the saved models, rebuilds features/reference calibration, and verifies predictions and scores:

```sh
data/forecasts/venv/bin/python -m forecasts.run reproduce RUN_ID --profile YOUR_LOCAL_PROFILE --bucket YOUR_PRIVATE_BUCKET
```

The caller must use the recorded Python version and platform. This command never calls source providers or switches the user's checkout. It writes `verification.json` under `data/forecasts/reproductions/RUN_ID/result/`. Numerical tolerance is absolute 1e-6 and relative 1e-9. Reproduction restores model artifacts; it does not claim binary-identical retraining. New input snapshots create new runs and cannot change earlier experiments.

The [verified baseline summary](reports/evaluation.json) records the accepted run identifier and public aggregate results. It is retrospective evidence with substantial interval under-coverage; further experiments follow the separate [continuation decision](../wiki/price-forecasting/germany-luxembourg.md#continuation).

The [research index](../wiki/price-forecasting/research/index.md) holds proposals and selection decisions. Actual MLflow executions retain evidence and conclusions. The baseline’s retrospective rationale explicitly records the absence of a pre-execution proposal; the interrupted execution is retained. New experiments must follow the [forecast-experiment skill](../.agents/skills/forecast-experiment/SKILL.md) before execution; the workflow does not automate that procedure.

## MLflow review

Start the local UI on port 5001, then install the checked-in [view definitions](review-views.json):

```sh
data/forecasts/venv/bin/mlflow ui --backend-store-uri "sqlite:///$PWD/data/forecasts/tracking/mlflow.db" --host 127.0.0.1 --port 5001
# In another terminal:
data/forecasts/venv/bin/python -m forecasts.review_views
```

The command prints **Forecast review**, our default entry link to the accepted baseline comparisons, and **Run history**. The views live with the experiment in the local tracking store, not only in browser preferences. Re-running setup updates the same two named views. Other saved views are untouched. This uses MLflow 3.17.0’s UI saved-view format; setup checks the installed version because that format is not a public configuration API. It does not replace MLflow’s global default Runs page.

- **Baseline review:** accepted parent’s five comparison children; Description, WIS, median MAE and 95% coverage; WIS ascending. The accepted run ID is explicit in the definition, so later baseline promotion requires a deliberate update.
- **Run history:** execution records, newest first; Description, creation date, evaluation start/end, snapshot ID and code revision. Empty Dataset/Models columns are hidden in both views. Historical Duration values measure logging only; compute time is unknown.

Open each printed link after setup to restore its filter, columns and sort. In the UI, **Views → Save as new view** keeps personal variations; overriding a shared view changes that saved layout until setup is rerun. The baseline and history links require this local tracking store; they are not hosted public results.

To publish a conclusion and derive the parent’s visible Notes from the same JSON:

```sh
data/forecasts/venv/bin/python -m forecasts.review --run MLFLOW_RUN_ID --conclusion PATH_TO_CONCLUSION_JSON --artifact-path research/conclusion.json
```

The conclusion contains `result`, `limitations`, `decision` and optional `evidence_artifacts` links. Keep full reasoning and retrospective status in that artifact; the command surfaces its summary and evidence links without altering frozen predictions, models or manifests. Re-run after editing the conclusion to keep Notes synchronized.

## Forecast observatory

Export a saved run as an offline website with daily forecasts, full-period/monthly comparisons, an illustrated WIS calculation, the forecast contract and a selectable system-level pipeline. No fitting, source-provider calls or new AWS resources are involved.

```sh
data/forecasts/venv/bin/python -m forecasts.explain --run data/forecasts/runs/RUN_ID --output data/forecasts/explainers/RUN_ID
```

Open the output's `index.html` in a browser. Keep the adjacent `data.js`, styles and scripts together. Use a new output directory for each export; existing exports are not overwritten. Generated files remain under ignored `data/forecasts/` and are not published by this command.

The exporter checks consumed artifact hashes and reconciles overall/monthly scores against the predictions. It retains missing outcomes, source fallbacks and Berlin clock-change quarters. The pipeline explains the system independently of the selected day, with saved-run provenance available as supporting detail.

The narrative's reviewed wiki hashes live in `forecasts/web/sources.json`. A changed source blocks export until the explanation is reviewed and its hash updated; referenced wiki bytes must be committed so source links identify the actual revision. The export records presentation hashes as well as run/code/snapshot identity. It validates consumed artifacts, not model files or source archives it does not load.

The viewer’s **How it works** is the canonical architecture explanation; edit its stages, connections and copy in [pipeline.json](web/pipeline.json). Scientific contracts remain in the linked wiki pages. The [design explainer](../explainers/forecast-product.html) records the approved experience. This viewer presents historical evidence; it does not establish calibration or live readiness.

For DOM integration checks (no rendering assertions), install the test-only dependency in ignored data and point the test at an export:

```sh
npm install --prefix data/forecasts/ui-test --no-save jsdom@26.1.0
NODE_PATH="$PWD/data/forecasts/ui-test/node_modules" node forecasts/tests/viewer.cjs data/forecasts/explainers/RUN_ID
```
