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

The input path stores three typed tables: `prices`, `weather` and `demand`. [Python schemas](schemas.py) define column types, nullability, units and row keys; validation runs before publication and after loading. Delivery/valid time, source update time and original retrieval time remain distinct. Unknown original timestamps remain null. Source versions and raw archive links are retained.

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

Historical price publication/revision timing and original weather publication times remain unverified. Demand timing depends on the meaning of its update timestamp. The manifest/report state these assumptions. Live selection requires an explicit actual issue timestamp, no later than the deadline, and rejects inputs retrieved or updated after it. Selector tests append late source revisions, realised weather and new labels, and retain a future-valid forecast retrieved before cutoff. The full test covering fitting, learned transformations, reference calibration and predictions remains part of the model step.

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

The fixed [run configuration](run-config.json) uses October 1–14, 2025 for feature warmup, trains from October 15, and evaluates January–September 2026 with monthly expanding fits. The first fold uses eligible labels from October 15–December 31. Price inputs are same-clock lags at 1/2/7/14 days, yesterday/last-week mean/min/max, and their missing flags. Calendar features are quarter, weekday, month and nationwide holiday. The weather/demand comparisons add the fixed twelve-location weather inventory and country demand with availability indicators. Targets and audit fields never enter model matrices.

One CPU CatBoost configuration fits all three feature sets: 400 trees, depth 6, learning rate 0.05, seed 20261009, one thread, no bootstrap, early stopping or parameter search. Native missing-value handling and training-only quantization replace learned imputation. Quantiles are sorted; raw outputs and crossing counts remain available. Training labels use the fold's first issue cutoff; each training day's features use its historical issue cutoff.

The reference averages yesterday/last-week prices, using one when the other is absent. When both are absent, its same-quarter median requires 14 earlier days. Historical fallback medians use only history available at that historical issue. Each fold needs at least 1,344 calibration errors and sufficient history for all 96 local quarters. Its five pooled error offsets use linear interpolation and training labels only. No evaluation day is removed for missing demand.

Use **Python 3.12.13** on the recorded platform for accepted reproduction. Install the complete dependency lock rather than just direct requirements:

```sh
data/forecasts/venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple -r forecasts/requirements-lock.txt
data/forecasts/venv/bin/python -m forecasts.run run --snapshot data/forecasts/loaded-snapshot
```

The snapshot must match the frozen configuration. Accepted runs require a clean, committed checkout. `--exploratory` permits development runs but disqualifies them from accepted reproduction. The command freezes the configuration, full feature lists, snapshot, code revision, Python/platform/packages and lock hash before starting local Metaflow. A run identifier names `data/forecasts/runs/RUN_ID/`; an existing run cannot be overwritten.

Metaflow saves local metadata/artifacts under `data/forecasts/metaflow/`. MLflow uses `data/forecasts/tracking/mlflow.db` and a local artifacts directory. A parent experiment links code, snapshot and Metaflow identifiers; child runs compare the three feature sets, reference and fallback system. Preserve these ignored directories. They are local records, without cloud backup.

Run artifacts include selected features and audit flags, raw/ordered predictions, per-fold CatBoost models, reference medians/error offsets, configuration, dependency lock and a checksum manifest. The report includes WIS, median MAE/RMSE, interval widths and coverage, equal-day-weighted coverage, monthly/demand breakdowns, failures, source fallbacks and paired seven-day-block score differences with 95% intervals. All methods use common available truth rows; missing truth is disclosed. Whole-source failures choose demand → weather → prices → reference according to availability and execution success. Partial gaps remain missing. An individual model execution failure is explicitly counted and its reference fallback is scored.

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
