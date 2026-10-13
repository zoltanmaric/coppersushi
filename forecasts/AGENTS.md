# Forecast agent guidelines

- Read the [product overview](../wiki/price-forecasting.md), [forecast design](../wiki/price-forecasting/germany-luxembourg.md) and [implementation spec](../wiki/specs/day-ahead-price-forecast.md) before making changes.
- Preserve exact input and code provenance; keep forecasts reproducible with one command, as defined in the [infrastructure design](../wiki/price-forecasting/forecast-infrastructure.md#promise).
- Choose storage from required reads and writes. Add complexity only for a demonstrated requirement.
- Enforce the [point-in-time contract](../wiki/price-forecasting/data-sources.md#point-in-time) in training and prediction; reproducibility alone does not prevent future-data leakage.
- Use the [forecast-experiment skill](../.agents/skills/forecast-experiment/SKILL.md) when proposing, running or evaluating forecast experiments.
