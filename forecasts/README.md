# DE–LU day-ahead forecast inputs

[Input collection and selection](inputs/README.md) preserves source versions in fixed, verifiable snapshots. Its reader selects the versions eligible for each Berlin delivery day under the [point-in-time contract](../wiki/price-forecasting/data-sources.md#point-in-time).

- [Historical coverage](source_audit/README.md) replays a snapshot and reports missing weather, demand, and prices.
- [Input storage](infra/README.md) owns the private S3 bucket.
- [Implementation spec](../specs/day-ahead-price-forecast.html) records the forecasting scope.

Use the repository's [Pixi setup](../README.md#local-installation). Run `pixi run --locked test-forecast`, `pixi run --locked typecheck`, and `pixi run --locked component-imports` to check the package.
