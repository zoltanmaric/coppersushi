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
  powerflow --> plot["Shared MapFrame and MapGraph"]
  cnec --> plot
```

`controls/map-controls.tsx` owns overlay composition and placement for both pages,
including loading and error messages in the grid row below help.
Pages supply legend units and range, help content, optional reference controls and
calendar capabilities. Power Flow uses a fixed day; Critical Elements supplies daily
availability. `IntervalControls` owns both pages’ date/time panel, interval buttons and slider. Domain fetching stays out of shared presentation components.

`map/` owns the measured map frame, render queue, Plotly lifecycle and tooltip gestures; feature-specific layers and calculations stay with
the page. Python shell assembly, browser schema generation (`contracts.py`) and asset
publication live in `packaging/`; they do
not fetch upstream market data or publish domain datasets.

From the repository root: `pixi run frontend-build`, `pixi run frontend-test` and
`pixi run frontend-contracts`. The latter regenerates browser contracts from Python
models. Tests are colocated. `scripts/build.mjs` builds into ignored `dist/`; source
assets live in `assets/`. The [deployment runbook](../infra/lambda/README.md) owns
production publication and rollback.
