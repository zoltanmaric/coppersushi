# Forecasts

Germany–Luxembourg day-ahead price forecasting. Start with the [wiki handover](../wiki/price-forecasting/germany-luxembourg.md) and [implementation spec](../wiki/specs/day-ahead-price-forecast.md).

## Dataset

Python 3.11 or newer with system IANA timezone data; no Python packages required. Run from the repository root:

```sh
python3 -m forecasts.dataset
python3 -m unittest discover -s forecasts/tests -v
```

The builder reads three immutable archives listed in the [payload manifest](evidence/payload-manifest.json): the bounded diagnostic's `inputs.zip`, weather compatibility's `responses.zip`, and `entsoe-files.zip`. Place them at their manifest paths under ignored `data/forecasts/`. A fresh clone needs the saved downloads; the [evidence instructions](evidence/README.md) describe the source collectors and demand access. Re-downloading mutable feeds may yield different hashes; the builder rejects that snapshot rather than silently changing the experiment.

To reuse downloads from another checkout:

```sh
python3 -m forecasts.dataset --data-root /absolute/path/to/other/checkout/data/forecasts
```

Outputs stay under `data/forecasts/dataset/` (`--output` can override it): `quarters.csv` and `report.json`. Empty CSV cells are missing values. The report records source hashes, the weather request/retrieval, transformations, implementation hash, Python version, columns and output hash. [Verified counts](reports/dataset.json) reconcile with the evidence, including every day's demand screen. Prices are attributed to Bundesnetzagentur | SMARD.de.

Every delivery quarter is retained, including negative prices, missing features and the 92/100-quarter clock-change days. Local-clock lags average duplicated quarters and leave nonexistent quarters missing. Weather hours repeat across quarters; radiation moves back one hour. Country demand uses the latest retained nonmissing version updated by the preceding day's 11:00 German cutoff. Rejected versions retain their latest archived timestamp and version count for audit; their values never enter features. Missing flags and whole-day source availability support the later evaluation's fallback rules.

Targets, archive timestamps/version counts, and retrieval/clock metadata are audit fields, not model features. The next step must freeze explicit feature lists and training/evaluation dates before fitting.

Historical price publication/revision timing and original weather publication times remain unverified. Demand availability is conditional on the meaning of its update timestamp. Row flags and the report preserve these limits; this dataset does not establish a witnessed historical replay.

## Private storage

AWS CLI v2 and an authenticated **user-local AWS profile** are required. Keep profile configuration and credentials outside the repository, normally in the user's AWS configuration directory. Never check in credentials, profile files, account identifiers or account-specific resource state. The profile needs CloudFormation deployment and S3 bucket/object permissions for this stack. Local dataset builds do not need AWS.

```sh
python3 -m forecasts.storage --profile YOUR_LOCAL_PROFILE provision
python3 -m forecasts.storage --profile YOUR_LOCAL_PROFILE upload
```

Provisioning can exceed a minute; use the repository's job-supervision workflow. The region defaults to `eu-west-1`; set `--region` before `provision` to override it. The [CloudFormation template](storage.json) creates one private S3 bucket: all public access blocked, ACLs disabled, AES256 encryption, versioning and a TLS-only policy. It retains the bucket on stack deletion and aborts incomplete multipart uploads after seven days. [AWS S3 CLI guidance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/GettingStartedS3CLI.html).

Provisioning verifies the deployed controls and saves the bucket name in ignored `data/forecasts/aws-storage.json`. Upload verifies inputs against the manifest and the dataset against its report, then uses content-hash keys under `inputs/` and `datasets/`. Conditional writes prevent overwrites; remote SHA-256 checksums and sizes are verified. Version IDs and keys go in ignored `data/forecasts/aws-upload.json`. No provider payloads or account-specific state are tracked. Upload also accepts `--data-root` and `--dataset-root`.

An authorized fresh checkout can restore the exact input snapshots without provisioning another bucket. Obtain its private bucket name from the owner or the ignored local state:

```sh
python3 -m forecasts.storage --profile YOUR_LOCAL_PROFILE restore --bucket YOUR_PRIVATE_BUCKET
python3 -m forecasts.dataset
```

Restore checks each downloaded file against the tracked manifest before replacing a local input. It also accepts `--data-root`. Transfers may exceed a minute; use job supervision. Access to the owner's private bucket, or independently supplied matching snapshots, is required for this recorded experiment; AWS access and bucket names are not public repository assets.

[Evidence](evidence/README.md) contains reusable collection/audit scripts and compact results. Downloaded inputs are under ignored `data/forecasts/`. The agreed model produces five price quantiles in one CatBoost fit; the wiki owns its design and evaluation contract.

As of 2026-10-09, the dataset pipeline and private storage exist. Quantile fitting, its evaluation report and a daily runner remain separate steps.
