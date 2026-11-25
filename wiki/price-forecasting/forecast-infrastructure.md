# Forecast storage and execution

The [forecast contract](germany-luxembourg.md) defines the market and deadline. The [product overview](../price-forecasting.md) links to the implemented workflow.

## Promise

Every forecast can explain exactly which data and code produced it, and an agent can reproduce it with one command. The run records the exact inputs, code, configuration and environment. Engineering quality means clear contracts, reliable execution and fast experiments.

Every forecast uses only information available by its issue deadline. Historical evaluation follows the same rule; unverified availability is recorded as an assumption. Reproducing a result does not prove that it was free of future information. The [point-in-time contract](data-sources.md#point-in-time) defines eligibility.

### Selection-principle

Replaying an issued forecast uses its saved fit and input editions. Reconstructing at the deadline can select a correction that arrived after issuance. In the [archive issuance implementation](https://github.com/zoltanmaric/coppersushi/blob/692072b7/forecasts/daily.py#L73-L88), live selection starts at the issue attempt's cutoff and replay selects at the deadline. The [issued record](https://github.com/zoltanmaric/coppersushi/blob/692072b7/forecasts/daily.py#L176-L194) identifies the fit manifest, prediction code, input cutoff and selected evidence.

Choose storage from the reads and writes the system needs. Add complexity only for a demonstrated requirement.

For a single S3 object, a successful PUT makes the complete object available to subsequent authorized GET and LIST requests. A publisher reading it back witnesses access through the publisher’s credentials. To establish which inputs an issued forecast actually used, retain the edition identifiers from that forecast run. [Amazon S3 consistency model](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel) · [Google Cloud MLOps metadata management](https://docs.cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning#metadata_management)

## Automation-scope

The foundation runs locally and on demand, with checks in continuous integration. The [forecast runbook](../../forecasts/README.md) documents input selection, monthly fitting, daily issuance, evaluation and reproduction. The [evaluation receipt](../../forecasts/reports/evaluation.json) records the reproduced run and its agreement with daily issuance.

Continuous delivery (CD) and continuous training (CT) are goals for subsequent work. Revisit CD when a pipeline change needs a repeatable release to an identified operating environment. Revisit CT when fresh settled observations justify recurring fits and the team can say what evidence qualifies a candidate for use. Scheduling daily predictions is a separate decision. Set acceptance criteria for each capability in the spec for the stage that introduces it. [Google Cloud’s automation levels](https://docs.cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning#mlops_level_1_ml_pipeline_automation)

## First-stage

Researchers collect frozen training snapshots locally and store them in S3. For retrospective evaluation, Metaflow runs locally and MLflow stores models and reports locally. S3 is the only cloud service this workflow requires.

The shared market archive has a separate, opt-in collection schedule. EventBridge Scheduler invokes one Lambda per publisher to preserve responses and validated editions in private S3. See the [market archive rollout runbook](../../coppersushi/infra/lambda/README.md#market-archive-collection).

| Technology | Responsibility |
|---|---|
| S3 and Parquet | Original downloads and fixed, typed input tables |
| Metaflow | Local workflow execution, intermediate artifacts and run history |
| MLflow | Parameters, scores, predictions, reports and trained models; link back to the Metaflow run |

Metaflow's local metadata and artifacts stay on disk. Configure MLflow explicitly with a local SQLite tracking store and local artifact directory. These local records need preservation to reproduce a run; S3 input storage alone does not back them up. SQLite is internal experiment bookkeeping, not the input database. Keep generated files ignored by Git.

## Inputs

Training and retrospective evaluation use frozen snapshots. Live issuance selects recent prices from the [market data archive](../../coppersushi/pipelines/market_data/README.md) using the forecast's free-source policy. Its edition pins the price evidence and timestamps. The researcher read records first observed availability separately. The fixed historical snapshot also preserves weather and demand for independent investigations. [Daily issue and read](../../forecasts/README.md#on-demand-day-ahead-forecast)

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

The [Pandera models](../../forecasts/inputs/schemas.py) define field types, nullability, units and row keys. They generate the Arrow storage schemas and manifest descriptions. A [frozen v1 fixture](../../forecasts/inputs/tests/test_schemas.py) checks compatibility. Preserve the timestamps, revisions and evidence required by the [point-in-time contract](data-sources.md#point-in-time); apply that contract when constructing features.

One file per dataset per snapshot is the starting layout. At the initial data volume, prefer this to daily partitions and compaction jobs. Measure bytes and cold-load time before changing it. Snapshot and archive readers apply their own evidence rules, then supply eligible prices to the same feature functions.

The three dataset names, checked schemas and snapshot manifests provide the initial inventory. Metaflow and MLflow record the snapshot identifier. A separate catalog, input database, feature store and cache service are deferred until a concrete access or discovery need appears.

### Edition replay

Delta Lake supports reading a table at a retained version or timestamp. Historical feature joins in Feast search backwards from each example’s timestamp. For market editions these operations depend on knowing when the validated input became readable. A publisher’s update time can precede that event. The source policy and the delivery interval still determine which committed price observations the consumer may use. [Delta Lake, historical snapshots and retention](https://docs.delta.io/delta-batch/#query-an-older-snapshot-of-a-table-time-travel) · [Feast, point-in-time joins](https://docs.feast.dev/getting-started/concepts/point-in-time-joins) · [Market edition replay example](https://github.com/zoltanmaric/coppersushi/pull/337)

For an archive read directly through S3, an object-created notification carries the object key and the time S3 finished the write request. Retaining those events for raw and validated objects provides two storage timestamps. Collector receipt and downstream use require evidence from those components. SageMaker Feature Store provides a managed analogue for submitted records: it adds service invocation and offline write timestamps alongside the event time supplied by the caller. [S3 event fields](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html) · [SageMaker offline store fields](https://docs.aws.amazon.com/sagemaker/latest/dg/feature-store-offline.html)

## Iteration

Keep source collection, input loading, feature construction and model evaluation as ordinary Python functions with thin Metaflow steps. Small fixtures permit local checks without provider access. Accepted reproducible runs archive the committed repository and its Pixi definitions, then install the locked `runtime` environment from that archive. The Pixi forecast feature supplies the locked runtime and development environments. The Copper Sushi publisher has its own dependencies. Record that revision, environment, configuration, seed and snapshot identifier. Exploratory runs with uncommitted code are marked as such and do not satisfy the reproduction guarantee; patch capture and replay are outside the first iteration. MLflow links to the Metaflow run; Metaflow records the MLflow run identifier. Reuse the platform's artifact and retry mechanisms.

### Research-history

The research-record contract separates planning from execution. Proposal pages live under `wiki/price-forecasting/research/`; its `index.md` maps their status, relationships and recommended next choice. Proposals retain selection decisions and short outcomes linked to execution evidence.

MLflow retains accepted executions and scientifically informative failures. Setup checks and PR debugging use disposable stores. Each run retains the exact motivating proposal and selection decision as artifacts, identified by wiki path and Git revision, alongside its results and conclusion. One proposal can motivate multiple runs; later wiki edits do not change a run's frozen copy. Written reviews and unexecuted proposals are wiki records, not standalone MLflow runs. Saved run manifests identify exact inputs, code and configuration. Each comparison link identifies its parent execution. The offline viewer captures the review at export time. Re-export after a decision changes. A later review can invalidate or supersede that execution while its recorded scores stay fixed. [Run review](../../forecasts/execution/README.md).

The [forecast-experiment skill](../../.agents/skills/forecast-experiment/SKILL.md) owns the agent procedure. Agents maintain the records manually; workflow automation is planned. No separate research database or service is required.

## Later

After the local evaluation works, the preferred deployment is Metaflow workflows coordinated by AWS Step Functions, with container jobs on AWS Batch backed by Fargate. Terraform defines the AWS infrastructure; Metaflow deploys the workflow definitions. Keep the forecast package independent of the power-flow application.

Metaflow documents Fargate support through its Batch integration. Before adopting this deployment, run a small end-to-end check with pinned dependencies and container image: input loading, task resources, retries, outputs and deadline scheduling. Check CPU/memory combinations and temporary disk needs against Fargate limits; Fargate does not provide GPUs. Evaluate the existing Metaflow Terraform modules before writing infrastructure from scratch, and provision only the services this stage needs.

Decide shared metadata, MLflow hosting and artifact retention then. Verify live price retrieval and deadline handling before claiming daily readiness. This later stage is separate from acceptance of the first local research result.

## Basis

- [Hello Interview: data modeling](https://www.hellointerview.com/learn/system-design/core-concepts/data-modeling): choose storage around access patterns.
- [Metaflow: data access](https://docs.metaflow.org/scaling/data): separate loading from feature construction; prefer built-in artifacts between steps.
- [MLflow: local tracking](https://mlflow.org/docs/latest/ml/tracking/quickstart/): record experiments and inspect results locally.
- [MLflow: tracking concepts](https://mlflow.org/docs/latest/tracking/): runs represent code executions; artifacts hold output files and supporting documents.
- [Metaflow: AWS execution](https://docs.metaflow.org/production/scheduling-metaflow-flows/scheduling-with-aws-step-functions): deploy flows through an existing cloud integration.
- [Metaflow: Batch settings](https://docs.metaflow.org/api/step-decorators/batch) and [AWS: Fargate suitability](https://docs.aws.amazon.com/batch/latest/userguide/when-to-use-fargate.html): supported execution and resource limits.
- [Metaflow AWS Terraform modules](https://github.com/outerbounds/terraform-aws-metaflow): reusable infrastructure building blocks.
