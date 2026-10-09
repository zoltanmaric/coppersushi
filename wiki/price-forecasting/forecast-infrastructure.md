# Forecast storage and execution

Agreed direction, 2026-10-09. Typed S3 snapshots and the shared input/feature reader are implemented; local workflow/tracking and later cloud execution remain planned. This supports the [forecast design](germany-luxembourg.md); the [product overview](../price-forecasting.md) owns the architecture graph. Remaining work lives in the [implementation spec](../specs/day-ahead-price-forecast.md).

## Promise

Every forecast can explain exactly which data and code produced it, and an agent can reproduce it with one command. The run records the exact inputs, code, configuration and environment. Engineering quality means clear contracts, reliable execution and fast experiments.

Every forecast uses only information available by its issue deadline. Historical evaluation follows the same rule; unverified availability is recorded as an assumption. Reproducing a result does not prove that it was free of future information. The [point-in-time contract](data-sources.md#point-in-time) defines eligibility.

### Selection-principle

Choose storage from the reads and writes the system needs. Add complexity only for a demonstrated requirement.

## First-stage

Store inputs in Amazon S3. Run collection, training and evaluation locally through Metaflow. Use local MLflow Tracking to compare experiments and retain models and reports. S3 is the only required cloud service in this stage; no cloud scheduler or shared tracking server is required.

| Technology | Responsibility |
|---|---|
| S3 and Parquet | Original downloads and fixed, typed input tables |
| Metaflow | Local workflow execution, intermediate artifacts and run history |
| MLflow | Parameters, scores, predictions, reports and trained models; link back to the Metaflow run |

Metaflow's local metadata and artifacts stay on disk. Configure MLflow explicitly with a local SQLite tracking store and local artifact directory. These local records need preservation to reproduce a run; S3 input storage alone does not back them up. SQLite is internal experiment bookkeeping, not the input database. Keep generated files ignored by Git.

## Inputs

Access is mostly batch reads: months of history for training and recent history plus future weather/demand for prediction. Start with three named Parquet datasets: `prices`, `weather`, and `demand`. The [source contracts](data-sources.md) own units, locations, resolution and availability rules.

Use a small, explicit S3 layout:

```text
raw/<source>/<fetch-id>/...          original responses and retrieval metadata
snapshots/<snapshot-id>/prices.parquet
snapshots/<snapshot-id>/weather.parquet
snapshots/<snapshot-id>/demand.parquet
snapshots/<snapshot-id>/manifest.json
```

### Snapshot

A snapshot is a fixed set of input files. Write new object keys for each snapshot and never overwrite a published one. Write its manifest last, after validation and upload. Readers require that manifest; an interrupted upload is not a usable snapshot. The manifest records schema version, exact file keys and checksums, row counts, time coverage and links to raw retrieval records. Training receives an explicit snapshot identifier, never a changing `latest` folder.

Keep schemas in version-controlled Python: column types, nullability, units and row keys, checked before publication and after loading. Preserve the timestamps, revisions and evidence required by the [point-in-time contract](data-sources.md#point-in-time); apply that contract when constructing features.

One file per dataset per snapshot is the starting layout. At the initial data volume, prefer this to daily partitions and compaction jobs. Measure bytes and cold-load time before changing it. A reader loads the fixed files locally and then performs model-specific feature construction in Python. Training and prediction use the same reader and feature functions.

The three dataset names, checked schemas and snapshot manifests provide the initial inventory. Metaflow and MLflow record the snapshot identifier. A separate catalog, input database, feature store and cache service are deferred until a concrete access or discovery need appears.

## Iteration

Keep source collection, input loading, feature construction and model evaluation as ordinary Python functions with thin Metaflow steps. Small fixtures permit local checks without provider access. Accepted reproducible runs use a committed code revision and a frozen dependency environment. Record that revision, environment, configuration, seed and snapshot identifier. Exploratory runs with uncommitted code are marked as such and do not satisfy the reproduction guarantee; patch capture and replay are outside the first iteration. MLflow links to the Metaflow run; Metaflow records the MLflow run identifier. Reuse the platform's artifact and retry mechanisms.

### Research-history

Planned follow-up after the first local baseline: the research harness records why an experiment was proposed, which evidence informed it, and what was learned. This extends run reproducibility; it is not part of the first baseline's acceptance criteria.

Use an MLflow run as the experiment record, with searchable relationship tags and saved proposal/conclusion artifacts. One research experiment may contain several execution runs for folds or variants; link all of them. Parent/child runs group execution. Explicit links to motivating experiments and the comparison baseline record how research ideas connect; these are distinct relationships.

| When | Record |
|---|---|
| Before execution | Hypothesis, motivating experiment IDs (empty for the initial baseline), prior results inspected, comparison baseline, intended change, fixed evaluation protocol and decision criterion |
| Automatically | Exact run-manifest links: snapshot ID, committed code revision, frozen environment, configuration, seeds and Metaflow/MLflow execution IDs; retain failed attempts and their status |
| After execution | Evidence links, results against the baseline on matching evaluation rows, limitations, conclusion and decision: keep, reject or investigate further |

Save the proposal before execution and append the conclusion afterward. Preserve the original proposal; a changed hypothesis or evaluation protocol starts a linked experiment. Record corrections without replacing the earlier evidence. Searchable tags and notes help discovery; saved artifacts hold the proposal and conclusion. Do not duplicate input files or manifest contents in prose.

The harness is a thin extension of the existing local workflow, not a separate service. It requires these records and the existing point-in-time and evaluation checks. Repeated use of evaluation results to choose experiments makes those dates development data, even when no future information enters individual forecasts. Record that use; fresh prospective evaluation provides new evidence. A failed experiment or a measured loss remains part of the history.

MLflow is the home for experiment evidence and relationships. The wiki holds durable accepted design decisions, linked to the relevant experiment IDs. Preserve the local tracking store and artifacts together, as required for local runs above. No additional research database or platform is required. [MLflow tracking APIs](https://mlflow.org/docs/latest/tracking/tracking-api/) provide tags, notes, artifacts and nested runs; the harness supplies the research protocol.

## Later

After the local evaluation works, the preferred deployment is Metaflow workflows coordinated by AWS Step Functions, with container jobs on AWS Batch backed by Fargate. Terraform defines the AWS infrastructure; Metaflow deploys the workflow definitions. Keep the forecast package independent of the power-flow application.

Metaflow documents Fargate support through its Batch integration. Before adopting this deployment, run a small end-to-end check with pinned dependencies and container image: input loading, task resources, retries, outputs and deadline scheduling. Check CPU/memory combinations and temporary disk needs against Fargate limits; Fargate does not provide GPUs. Evaluate the existing Metaflow Terraform modules before writing infrastructure from scratch, and provision only the services this stage needs.

Decide shared metadata, MLflow hosting and artifact retention then. Verify the live demand retrieval route and deadline handling before claiming daily readiness. This later stage is separate from acceptance of the first local research result.

## Basis

- [Hello Interview: data modeling](https://www.hellointerview.com/learn/system-design/core-concepts/data-modeling): choose storage around access patterns.
- [Metaflow: data access](https://docs.metaflow.org/scaling/data): separate loading from feature construction; prefer built-in artifacts between steps.
- [MLflow: local tracking](https://mlflow.org/docs/latest/ml/tracking/quickstart/): record experiments and inspect results locally.
- [Metaflow: AWS execution](https://docs.metaflow.org/production/scheduling-metaflow-flows/scheduling-with-aws-step-functions): deploy flows through an existing cloud integration.
- [Metaflow: Batch settings](https://docs.metaflow.org/api/step-decorators/batch) and [AWS: Fargate suitability](https://docs.aws.amazon.com/batch/latest/userguide/when-to-use-fargate.html): supported execution and resource limits.
- [Metaflow AWS Terraform modules](https://github.com/outerbounds/terraform-aws-metaflow): reusable infrastructure building blocks.
