# Price forecasting

An independent forecasting product under `forecasts/`, with no dependency on the power-flow application. The first market is Germany–Luxembourg day-ahead electricity prices. As of 2026-10-09, typed S3 inputs, local training/evaluation and experiment tracking are implemented; cloud execution remains planned.

## Design

- [Forecast contract](price-forecasting/germany-luxembourg.md): market, deadline, inputs and outputs.
- [Storage and execution](price-forecasting/forecast-infrastructure.md): reproducibility promise, selection principle, local first iteration and later AWS deployment.
- [Data sources](price-forecasting/data-sources.md): verified contracts and availability limits.
- [Evaluation](price-forecasting/evaluation.md): chronological comparisons and scoring.
- [Implementation spec](specs/day-ahead-price-forecast.md): remaining work and acceptance checks.

## Dataflow

Solid nodes and edges represent implemented parts; dashed nodes and edges (`planned`) represent planned parts. Each arrow means "required to produce." Cloud execution is a later stage, subject to deployment validation.

```mermaid
flowchart LR
    classDef planned stroke-dasharray: 5 5,stroke:#888,fill:none

    forecast_raw_inputs["forecast_raw_inputs<br/>S3 source responses and retrieval metadata"]
    forecast_input_snapshot["forecast_input_snapshot<br/>S3 validated Parquet tables and fixed manifest"]
    forecast_local_run["forecast_local_run<br/>local Metaflow training and evaluation"]
    forecast_experiment["forecast_experiment<br/>local MLflow scores, models and reports<br/>research history maintained by agents"]

    forecast_raw_inputs --> forecast_input_snapshot
    forecast_input_snapshot --> forecast_local_run
    forecast_local_run --> forecast_experiment

    forecast_aws_infra["forecast_aws_infra<br/>Terraform-managed AWS resources, later stage"]:::planned
    forecast_cloud_run["forecast_cloud_run<br/>Metaflow / Step Functions / AWS Batch on Fargate, deployment validation pending"]:::planned
    forecast_daily_output["forecast_daily_output<br/>daily quantiles with input, code and model provenance"]:::planned

    forecast_aws_infra -.-> forecast_cloud_run
    forecast_input_snapshot -.-> forecast_cloud_run
    forecast_experiment -.-> forecast_cloud_run
    forecast_cloud_run -.-> forecast_daily_output
```
