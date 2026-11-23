# Forecast research

The [price-history baseline](prices-only-baseline.md) has a [recorded result](../evaluation.md#result). The earlier candidates remain deferred. [Retrospective baseline review](baseline-review.md) owns the observations and execution links. The [research-record contract](../forecast-infrastructure.md#research-history) separates wiki planning from MLflow execution evidence.

## Candidates

| Proposal | Status | What it teaches / expected value | Rough cost | Relationship |
|---|---|---|---|---|
| [Training versus future diagnostics](training-future-diagnostics.md) | Recommended; unselected | Locate calibration and bias patterns before choosing a mechanism | Low–medium; saved-model prediction | Informs simpler models, calibration and viewer |
| [Simpler model](simpler-model.md) | Unselected | Test whether one complexity reduction improves future performance | Medium; monthly fitting | Choose the change after diagnostics |
| [Interval calibration](interval-calibration.md) | Unselected | Test correction using earlier out-of-sample errors | Medium; replay and leakage checks | Separate from model changes |
| [Incremental input value](incremental-input-value.md) | Unselected | Quantify weather and demand improvements with paired uncertainty | Low; saved forecasts | Can inform later input investment |
| [Prospective validation](prospective-validation.md) | Unselected | Witness actual availability and fresh forecast performance | High; runner and operating period | Requires deployment and budget decisions |
| [Viewer diagnostics](viewer-diagnostics.md) | Unselected | Make diagnostics understandable and linked to daily curves | Medium; exporter and interface | Requires diagnostic schema and reviewed design |

The [October–November replay](autumn-replay.md) was invalidated after incomplete demand collection. Revisit it when a demand study is selected.
