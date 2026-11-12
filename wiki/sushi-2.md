# Copper Sushi 2 — optimal power flow on the 2025 grid

[System overview](../README.md) · [OPF component](../coppersushi/pipelines/powerflow/README.md) · [Grid catalog component](../coppersushi/pipelines/grid/README.md)
The in-place successor of [v1](copper-sushi-app.md). v1 visualized a *model's* optimal power flow on the 2013 GridKit grid ("the math is real, the data is not"). Sushi 2 keeps the OPF and moves it to **PyPSA-Eur as of 2026, on the 2025 OSM-based grid, for a 2024 day** — a working OPF first; truing it up to measured data comes after.

## Architecture (settled 2026-09-02)

1. **Grid**: PyPSA-Eur's OSM-based European network (Xiong et al., *Nature Scientific Data* 2025), built by PyPSA-Eur's own `base_network`.
2. **Workflow**: PyPSA-Eur as of 2026, run from a [pinned sibling checkout](pypsa-eur-sibling.md) with a config committed here, HiGHS as solver. Load disaggregation, plant matching and renewable profiles are upstream's (JRC Energy Atlas, powerplantmatching, atlite).
3. **Signal**: v1's family unchanged — net power per node, loaded-vs-easy branches, direction arrows, per-node tooltips.
4. **Web tool**: this repo, the viewer of the solved network; `Scattermapbox` pinned ([codebase-v1](codebase-v1.md)).
5. **Visual language** (settled 2026-09-10): one colourscale, Plotly's `tropic`, for every mapped value — node net power, zonal price — and purple reserved for market-binding elements. A second scale beside the purple was tried and rejected as a clash.

## Dataflow

The [root system diagram](../README.md#system-design) owns runtime components and
serving boundaries. Component details live with [OPF](../coppersushi/pipelines/powerflow/README.md),
[grid catalog](../coppersushi/pipelines/grid/README.md),
[publication](../coppersushi/pipelines/cnec/README.md) and the [browser](../coppersushi/frontend/README.md).

The catalog keeps source evidence, endpoint identity and orientation assessments
separate from price attribution. Unknown locations remain explicit. Publication
resolves missing endpoints before writing the day; browser navigation does not
fetch upstream data or ask Python to render figures. The browser applies the chosen
reference country and constraint to the published coefficients.

## Future chapters

True-up to actuals — renewable dispatch calibrated to zonal actuals, units ≥ 100 MW fixed to measured output, validation against measured cross-border flows ([nodal-disaggregation](nodal-disaggregation.md) for what is and is not measurable). Then flow-traced nodal carbon intensity and OPF counterfactuals.

The OPF model has 4,390 buses and 24 hourly snapshots for 29 August 2024, displayed
in Europe/Brussels time. `/opf-2024` shows both product links;
`/embed/opf-2024` shows the map without navigation. The homepage and Critical
Elements embed routes are documented in the [README](../README.md). Both 2013 app models are removed.

The [static production hosting](../coppersushi/infra/lambda/README.md) serves both browser views
and published data through CloudFront and private S3. OPF preparation writes typed network metadata, numeric interval values and UTC timestamps; the browser validates the manifest and selected
hour, supplies the public Mapbox token and keeps camera state across hour changes.
Candidate networks use the same numeric export and browser preview. The market-data publisher
Lambda and its workflow are independent of public page delivery.

For external-input resilience, see [JAO availability and response retention](jao-availability.md).
