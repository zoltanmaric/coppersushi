# Forecasts

Independent Germany–Luxembourg price forecasting. The [implementation spec](../wiki/specs/day-ahead-price-forecast.md) lists remaining work; the [infrastructure design](../wiki/price-forecasting/forecast-infrastructure.md) owns the storage contract.

## Setup

Use the repository's [Pixi setup](../README.md#local-installation) and default Python interpreter.
S3 commands also need AWS CLI v2 and an authenticated **user-local AWS profile**.
Credentials, profile files, bucket names, Terraform state and generated inputs stay outside Git.

```sh
pixi run --locked test-forecast
```

New snapshot manifests record Python/PyArrow versions, root project and Pixi lockfile
hashes, code revision and whether code or dependency definitions were uncommitted.
Existing manifests retain their recorded provenance. Historical reproduction uses the
recorded revision and its original environment; the current development lock is not a
replacement for a historical environment.

## S3 inputs

Collect or load immutable input snapshots. [Input and storage contracts](../wiki/price-forecasting/forecast-infrastructure.md#inputs). Price table contracts: [prices.py](prices.py).

To collect the recorded year, place the three exact archives at their [baseline input inventory](data/baseline-inputs.json), under `data/forecasts/`. The [source contracts](../wiki/price-forecasting/data-sources.md) describe their sources. `--data-root` can reuse another checkout's downloads. Recollection from mutable feeds may produce different bytes; the recorded experiment requires matching archives or access to the private S3 snapshot.

```sh
pixi run --locked python -m forecasts.snapshot --profile YOUR_LOCAL_PROFILE --bucket YOUR_PRIVATE_BUCKET collect --publish
```

Use the printed snapshot ID explicitly:

```sh
pixi run --locked python -m forecasts.snapshot --profile YOUR_LOCAL_PROFILE --bucket YOUR_PRIVATE_BUCKET load SNAPSHOT_ID
pixi run --locked python -m forecasts.dataset --snapshot data/forecasts/loaded-snapshot
```

`--region` defaults to `eu-west-1`. Collection/publication accept `--directory`; loading also accepts it. A fresh checkout can load the selected snapshot directly, without raw downloads or source-provider requests.

## Features

Build diagnostic feature outputs from a loaded snapshot:

```sh
pixi run --locked python -m forecasts.dataset --snapshot data/forecasts/loaded-snapshot
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

Uploads and provider installation may exceed a minute; follow the repository's job-supervision workflow.

## Local model evaluation

[`evaluation.evaluate()`](evaluation.py) runs the fixed [scientific configuration](run-config.json): eligible features, monthly fitting, daily prediction and scoring. The [table contracts](tables.py) declare each stage's inputs and outputs. The [evaluation contract](../wiki/price-forecasting/evaluation.md) owns the method and limitations.

```sh
pixi run --locked python -m forecasts.evaluation --snapshot data/forecasts/loaded-snapshot --output data/forecasts/evaluations/baseline
```

Choose a new output directory. The command checks the snapshot identity and writes features, models, predictions and a report. This command does not preserve an execution environment or register a tracking run.

## Type checks

Check the entire forecast tree, including tests and evidence scripts:

```sh
pixi run --locked typecheck
```

The normal test suite also rejects missing function annotations anywhere under `forecasts/`. Missing third-party stubs remain an explicit limitation of static checking.

## Historical input regression

The recorded year's coverage is a regression fixture, not a constraint on newly collected data. To check the exact baseline snapshot explicitly:

```sh
FORECAST_BASELINE_SNAPSHOT=data/forecasts/loaded-snapshot pixi run --locked python -m unittest forecasts.tests.test_baseline -v
```

The test requires the snapshot ID recorded in its fixture. Ordinary dataset generation reports coverage without requiring it to match that historical year. Raw baseline archives belong at `data/forecasts/inputs/prices.zip`, `weather.zip` and `demand.zip`; existing saved S3 snapshots remain readable without relocating anything.

## Tracked execution and reproduction

Run accepted execution from the normal development environment:

```sh
pixi run --locked python -m forecasts.run run --snapshot data/forecasts/loaded-snapshot
```

The command requires committed code. It freezes the repository, `pyproject.toml`, `pixi.lock` and configuration, then restores a fresh Pixi `runtime` environment before running Metaflow. The manifest records the actual Python and installed packages, definition hashes, Pixi version, code and snapshot identity. Development-only packages are excluded. Runtime installation can use cached packages; it requires package-network access when the cache is incomplete.

Execution directories live under `data/forecasts/runs/`; each retry gets a new identifier. Set `FORECAST_DATA_ROOT` to use another output/tracking root. `--exploratory` uses the mutable checkout and current interpreter; these runs cannot satisfy accepted reproduction. Inputs remain in S3, while execution artifacts must be retained locally. For smoke tests and PR verification, set `FORECAST_DATA_ROOT` to a temporary directory so validation does not enter research history.

```sh
pixi run --locked python -m forecasts.run reproduce RUN_ID --profile YOUR_LOCAL_PROFILE --bucket YOUR_PRIVATE_BUCKET
```

Reproduction uses the saved code and Pixi definitions on the recorded operating system and architecture, reloads the S3 snapshot, and compares saved-model predictions and scores. Each attempt lives under `data/forecasts/reproductions/RUN_ID/ATTEMPT_ID/`, with status in `attempt.json` and successful verification in `result/verification.json`. Retry with the same command; failed and successful attempts remain intact. The preserved lock must still be supported by the installed Pixi version. It does not claim binary-identical retraining. [Scientific limits](../wiki/price-forecasting/evaluation.md#result) remain unchanged.

## Forecast observatory

Export a saved run as an offline website with daily forecasts, full-period/monthly comparisons, an illustrated WIS calculation, the forecast contract and a selectable system-level pipeline. No fitting, source-provider calls or new AWS resources are involved.

```sh
pixi run --locked python -m forecasts.explain --run data/forecasts/runs/RUN_ID --output data/forecasts/explainers/RUN_ID
```

Open the output's `index.html` in a browser. Keep the adjacent `data.js`, styles and scripts together. Use a new output directory for each export; existing exports are not overwritten. Generated files remain under ignored `data/forecasts/` and are not published by this command.

The exporter checks consumed artifact hashes and reconciles overall/monthly scores against the predictions. It retains missing outcomes, source fallbacks and Berlin clock-change quarters. The pipeline explains the system independently of the selected day, with saved-run provenance available as supporting detail.

The narrative's reviewed wiki hashes live in `forecasts/web/sources.json`. A changed source blocks export until the explanation is reviewed and its hash updated; referenced wiki bytes must be committed so source links identify the actual revision. The export records presentation hashes as well as run/code/snapshot identity. It validates consumed artifacts, not model files or source archives it does not load.

The viewer’s **How it works** is the canonical architecture explanation; edit its stages, connections and copy in [pipeline.json](web/pipeline.json). Scientific contracts remain in the linked wiki pages. This viewer presents historical evidence; it does not establish calibration or live readiness.

For DOM integration checks (no rendering assertions), install the test-only dependency in ignored data and point the test at an export:

```sh
npm install --prefix data/forecasts/ui-test --no-save jsdom@26.1.0
NODE_PATH="$PWD/data/forecasts/ui-test/node_modules" node forecasts/tests/viewer.cjs data/forecasts/explainers/RUN_ID
```
