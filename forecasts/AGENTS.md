# Forecast agent guidelines

- Read the [forecast design](../wiki/price-forecasting/germany-luxembourg.md) and [implementation spec](../wiki/specs/day-ahead-price-forecast.md) before making changes.
- Preserve exact input and code provenance; keep forecasts reproducible with one command, as defined in the [infrastructure design](../wiki/price-forecasting/forecast-infrastructure.md#promise).
- Choose storage from required reads and writes. Add complexity only for a demonstrated requirement.
