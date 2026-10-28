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

The input path stores three typed tables: `prices`, `weather` and `demand`. [Price contracts](prices.py) define price columns and checks and derive their Parquet schema; [other input schemas](schemas.py) define weather and demand contracts; validation runs before publication and after loading. Delivery/valid time, source update time and original retrieval time remain distinct. Unknown original timestamps remain null. Source versions and raw archive links are retained.

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

S3 keys follow the agreed layout:

```text
raw/<source>/<archive-sha256>/<archive-name>
raw/<source>/<archive-sha256>/retrieval.json
snapshots/<snapshot-id>/prices.parquet
snapshots/<snapshot-id>/weather.parquet
snapshots/<snapshot-id>/demand.parquet
snapshots/<snapshot-id>/manifest.json
```

The manifest records schemas, checksums, row counts, time coverage, exact file keys and raw retrieval metadata links. Its content determines the snapshot ID. Publication verifies local and remote bytes and writes the manifest last. Conditional object creation prevents retrying from replacing a published object; a conflicting existing object is rejected. Loading requires the manifest and verifies every selected file. `load-report.json` records input bytes and cold-load duration; no cache or partition service is required.

## Features

The shared `InputReader.features()` path applies historical or live eligibility before calling ordinary feature functions. Replay joins retrospective price truth afterwards. It retains all delivery quarters, negative prices, missing inputs and 92/100-quarter clock-change days. Same-clock lags average duplicate quarters and leave nonexistent quarters missing; weather hours repeat across quarters, with radiation aligned back one hour. Country demand uses the latest nonmissing eligible update by the preceding day's 11:00 Berlin deadline.

`forecasts.dataset --snapshot ...` writes a diagnostic `quarters.csv` and `report.json` under ignored `data/forecasts/dataset/`. These are feature/report outputs; the S3 input contract is the three Parquet tables. The raw-archive CLI remains available for evidence reconciliation. Targets, archive timestamps and audit metadata are not model features; explicit feature lists must be frozen before fitting.

Historical price publication/revision timing and original weather publication times remain unverified. Demand timing depends on the meaning of its update timestamp. The manifest/report state these assumptions. Live selection requires an explicit actual issue timestamp, no later than the deadline, and rejects inputs retrieved or updated after it. Selector tests append late source revisions, realised weather and new labels, and retain a future-valid forecast retrieved before cutoff. The fitting leakage test also checks learned transformations, reference calibration and predictions.

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
data/forecasts/venv/bin/python -m forecasts.evaluation --snapshot data/forecasts/loaded-snapshot --output data/forecasts/evaluations/baseline
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
FORECAST_BASELINE_SNAPSHOT=data/forecasts/loaded-snapshot data/forecasts/venv/bin/python -m unittest forecasts.tests.test_baseline -v
```

The test requires the snapshot ID recorded in its fixture. Ordinary dataset generation reports coverage without requiring it to match that historical year. Raw baseline archives belong at `data/forecasts/inputs/prices.zip`, `weather.zip` and `demand.zip`; existing saved S3 snapshots remain readable without relocating anything.
