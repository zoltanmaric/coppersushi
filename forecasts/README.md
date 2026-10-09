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

Uploads and provider installation may exceed a minute; follow the repository's job-supervision workflow. As of 2026-10-09, input collection/storage and feature replay are implemented. Local Metaflow training, MLflow comparisons, quantile fitting and accepted-run reproduction remain in the next spec step.
