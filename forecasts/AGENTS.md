# Forecast agent guidelines

- Read the [product overview](../wiki/price-forecasting.md), [forecast design](../wiki/price-forecasting/germany-luxembourg.md) and [implementation spec](../wiki/specs/day-ahead-price-forecast.md) before making changes.
- Preserve exact input and code provenance; keep forecasts reproducible with one command, as defined in the [infrastructure design](../wiki/price-forecasting/forecast-infrastructure.md#promise).
- Choose storage from required reads and writes. Add complexity only for a demonstrated requirement.
- Enforce the [point-in-time contract](../wiki/price-forecasting/data-sources.md#point-in-time) in training and prediction; reproducibility alone does not prevent future-data leakage.
- Use the [forecast-experiment skill](../.agents/skills/forecast-experiment/SKILL.md) when proposing, running or evaluating forecast experiments, or reviewing their saved records.

- Make Python modules readable from their public entry points downward: put the main workflow first, then public operations, then `_`-prefixed internal helpers. Use names and explicit stages that expose the data path.
- Annotate function parameters and return values, including internal helpers; let obvious local types be inferred. Give public functions concise contract docstrings, including time cutoffs and side effects where relevant. Use named results for multi-part stage outputs. Parse and validate external representations at the boundary; use domain types (such as dates and validated identifiers) inside the computation, not JSON-shaped dictionaries with annotations. Keep fixed choices as constants, not pretend configuration.
