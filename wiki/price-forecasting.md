# Price forecasting

An independent forecasting product under `forecasts/`, with no dependency on the power-flow application. The first market is Germany–Luxembourg day-ahead electricity prices. As of 2026-10-28, typed S3 inputs and local training/evaluation are implemented; local execution tracking is implemented; cloud runs remain planned.

## Design

- [Product experience](../explainers/forecast-product.html): approved illustrated spec for results and system-level explanation.

- [Forecast contract](price-forecasting/germany-luxembourg.md): market, deadline, inputs and outputs.
- [Storage and execution](price-forecasting/forecast-infrastructure.md): reproducibility promise, selection principle, local first iteration and later AWS deployment.
- [Data sources](price-forecasting/data-sources.md): verified contracts and availability limits.
- [Evaluation](price-forecasting/evaluation.md): chronological comparisons and scoring.
- [Implementation spec](specs/day-ahead-price-forecast.md): remaining work and acceptance checks.

## Architecture

The forecast viewer’s **[How it works](../forecasts/web/index.html#trace)** is the canonical architecture explanation. [Export and open a saved run](../forecasts/README.md#forecast-observatory) to use it. Its readable source, [pipeline.json](../forecasts/web/pipeline.json), owns the stages, connections and explanations; the frontend renders that source.

Scientific contracts and decisions remain in the design pages linked above. The viewer links to their recorded revisions. Planned cloud execution is described in the [infrastructure decision](price-forecasting/forecast-infrastructure.md#later), separately from the implemented historical pipeline.

## Research

The [research index](price-forecasting/research/index.md) owns proposals, relationships, status and the recommended next choice. The [baseline review](price-forecasting/research/baseline-review.md) records the retrospective evidence and links to actual MLflow executions. No follow-up candidate is selected or executed. [Research-record contract](price-forecasting/forecast-infrastructure.md#research-history).
