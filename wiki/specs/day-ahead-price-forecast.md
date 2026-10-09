# Spec: Germany–Luxembourg price forecast

Implementation working memory, 2026-10-09. Authoritative scope: [forecast design](../price-forecasting/germany-luxembourg.md). Implementation home: `forecasts/`, independent of the map/power-flow application.

## Problem

Build one useful public-fundamentals model for next-day quarter-hour prices, issued by 11:00 German local time, with five uncertainty quantiles and a reproducible historical evaluation.

## Next

1. Assemble inputs from the [verified sources and local evidence](../price-forecasting/data-sources.md), reusing saved inputs and audit scripts. Follow the [storage and execution design](../price-forecasting/forecast-infrastructure.md): raw downloads and validated Parquet snapshots in S3, explicit schemas and a manifest published last. Keep local downloads in ignored `data/forecasts/`. Resolve the AWS account, region and bucket at implementation time. Diagnose new contradictions rather than restarting completed source research.
2. Run training and evaluation locally with Metaflow and local MLflow Tracking. Freeze exact dates, remaining price features, model settings and minimum reference history in a run manifest; implement the [evaluation contract](../price-forecasting/evaluation.md), including the [simple defaults](../price-forecasting/evaluation.md#defaults) and [three feature-set comparisons](../price-forecasting/evaluation.md#controls). Fit one CatBoost MultiQuantile configuration across those feature sets on successive chronological folds and save the local report, predictions and model artifacts. Link experiment records to their fixed input snapshot and code/environment versions.

Later: scheduled collection and daily inference through Metaflow, Step Functions and AWS Batch on Fargate, with infrastructure in Terraform; validate this deployment before adoption. Shared MLflow hosting and retention follow then. Re-plan after the local result. No cloud compute, scheduler, input database, feature store or separate catalog is required for the first iteration.

No broader hyperparameter search, foundation-model comparison, network-constraint model, dashboard, paid data procurement or competition submission is required for this first result.

The [input-availability limits](../price-forecasting/data-sources.md#availability) remain unresolved: distinguish verified timing from assumptions before claiming a faithful historical replay. Additional [review recommendations](../price-forecasting/evaluation.md#limitations) are separate from the agreed acceptance criteria.

## Acceptance

- [ ] A local collection run publishes a validated S3 snapshot. Partial uploads are rejected; retrying cannot change a published snapshot. Schemas, source metadata, checksums and file locations are discoverable from its manifest.
- [ ] A clean local run loads the selected snapshot from S3 without calling source providers. Record input size and cold-load time before adding performance infrastructure.
- [ ] Dataset replay respects the cutoff, excludes later revisions, flags missing inputs and retains clock-change dates; its counts reconcile with the supplied evidence.
- [ ] Leakage test: select inputs and fit/predict at a historical cutoff, then append post-cutoff source revisions, realised weather and newly available labels to the candidate history and rerun selection and fitting with fixed settings. Selected versions, fitted transformations/reference calibration and predictions remain unchanged (within the declared numerical tolerance). Exercise the selector on the enlarged history, not merely a reload of the frozen snapshot. Include a forecast valid after the cutoff but available before it, which must remain eligible.
- [ ] The report exposes each source's timing-evidence status and assumptions under the [point-in-time contract](../price-forecasting/data-sources.md#point-in-time); unknown historical availability is never presented as verified.
- [ ] Five ordered, finite prices per evaluation quarter, with the agreed clock-change, missing-weather, calendar and fallback rules applied; failures/fallbacks explicit and negative prices permitted.
- [ ] Training never uses later labels or evaluation-fitted calibration; demand gaps do not select the test population.
- [ ] Weighted interval score verified on known cases and a reference implementation; median error, interval coverage/width and daily coverage reported on identical rows for all three feature sets, the fallback system and the distributional reference.
- [ ] Monthly and demand-availability breakdowns, paired seven-day-block comparison uncertainty and limitations accompany the headline result.
- [ ] From a clean checkout with documented setup and input access, one command taking an accepted run identifier restores its committed code revision, frozen dependency environment, configuration, model and input snapshot, then reproduces predictions and scores within a declared numerical tolerance, without source-provider calls or manual file selection. No secrets, provider-restricted payloads or machine-specific private paths in tracked files.
- [ ] Metaflow executes locally; MLflow shows the three feature-set comparisons and reference scores with linked run/snapshot identifiers. A new source revision leaves the earlier experiment's inputs unchanged.

A measured loss is a valid research result; acceptance does not require beating the reference. Uncertainty calibration is measured, not assumed from nominal interval labels. No first-build performance result is available as of the handover.
