# Data pipelines

[Product](../README.md) · [Power Flow](powerflow/README.md) · [Critical Elements](cnec/README.md) · [Grid](grid/README.md)

Owns Python calculations, typed external contracts and dataset materialization.
Power Flow preparation is deliberately rebuilt from solved networks. Critical Elements
fetches and publishes a complete market day on a schedule. Grid preparation supplies
located elements and geography to the daily job. Cadence is behavior, not a folder layer.

Each feature keeps its models and calculations with its external I/O under
`data_sources/`. Shared time types and data models remain at this level; shared storage,
configuration and credentials access live in `data_sources/`. A shared helper needs
actual callers in multiple features. No request-serving application is required for
published map data.

Tests sit beside source; fixtures live in the owning component’s `testdata/`. Run the root Pixi test
and typecheck tasks. Update this overview and the owning feature README when changing
responsibility or a publication boundary.
