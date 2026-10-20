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

The October 20, 2026 diagnostic review is recorded retrospectively in local MLflow experiment `germany-luxembourg-local`, research record `5136923c77484ace8c98dac6f843e308`, linked to accepted execution `8a4c692855fb42eba39d5a3bfc7d6762`. Its `research/records.json` links six candidate proposals; their costs, prerequisites and unresolved choices live in MLflow, not a duplicate wiki backlog. [Open local tracking](../forecasts/README.md#local-model-evaluation).

The agreed direction is to preserve the baseline and record the evidence before selecting further work. No candidate is selected or executed. January–September 2026 results inspected for these choices are development evidence; confirmation needs fresh, uninspected dates. Follow the [proposal and selection procedure](../.agents/skills/forecast-experiment/SKILL.md) before execution. The recorded numerical diagnostics are attributed to the [#105 review](https://github.com/zoltanmaric/coppersushi/pull/105#pullrequestreview-5583597223) and [#112 review](https://github.com/zoltanmaric/coppersushi/pull/112#pullrequestreview-5583599100); recording them does not constitute an independent rerun.
