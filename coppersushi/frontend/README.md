# Map frontend

[Product](../README.md) · [Pipelines](../pipelines/README.md)

Owns the React map pages and their browser presentation. `pages/powerflow/` constructs
network layers and tooltips from numeric snapshots; `pages/cnec/` owns market selection,
contributions and reference-country behavior. Both use shared `controls/` and `map/` primitives. Data loading and contracts
live with each page. There is no intermediate source directory.

```mermaid
flowchart LR
  files["Published manifests and intervals"] --> powerflow["Power Flow: loading and rendering"]
  files --> cnec["Critical Elements: loading and rendering"]
  powerflow --> controls["Shared MapControls overlay"]
  cnec --> controls
  powerflow --> plot["Shared Plot lifecycle"]
  cnec --> plot
```

`controls/map-controls.tsx` owns overlay composition and placement for both pages.
Pages supply legend units and range, help content, optional reference controls and
calendar capabilities. Power Flow uses a fixed day; Critical Elements supplies daily
availability. Domain fetching stays out of shared presentation components.

`map/` owns plotting primitives; feature-specific layers and calculations stay with
the page. Python shell assembly, browser schema generation (`contracts.py`) and asset
publication live in `packaging/`; they do
not fetch upstream market data or publish domain datasets.

From the repository root: `pixi run frontend-build`, `pixi run frontend-test` and
`pixi run frontend-contracts`. The latter regenerates browser contracts from Python
models. Tests are colocated. `scripts/build.mjs` builds into ignored `dist/`; source
assets live in `assets/`. The [deployment runbook](../infra/lambda/README.md) owns
production publication and rollback.
