# Price forecasting

Start with the [forecasting system design principles](forecasting-system-design.md#principles). For a worked introduction, open [Reading Google’s MLOps guide for power forecasting](../lessons/forecasting-systems/index.html). The [operational cases](price-forecasting/operational-forecasting.md) work through the evidence for the 11:00 DE–LU forecast.

The Germany–Luxembourg day-ahead forecast has its own [product package](../forecasts/README.md).

## Design

- [Forecast contract](price-forecasting/germany-luxembourg.md): market, deadline, inputs and outputs.
- [Storage and execution](price-forecasting/forecast-infrastructure.md), including [foundation scope and when to revisit CD and CT](price-forecasting/forecast-infrastructure.md#automation-scope).
- [Data sources](price-forecasting/data-sources.md): verified contracts and availability limits.
- [Evaluation](price-forecasting/evaluation.md): chronological comparisons and scoring.
- [Implementation spec](../specs/day-ahead-price-forecast.html): remaining work and acceptance checks.

