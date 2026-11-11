# Copper Sushi 2 — optimal power flow on the 2025 grid

[System overview](../README.md) · [OPF component](../coppersushi/opf/README.md) · [Grid catalog component](../coppersushi/grid_catalog/README.md)
The in-place successor of [v1](copper-sushi-app.md). v1 visualized a *model's* optimal power flow on the 2013 GridKit grid ("the math is real, the data is not"). Sushi 2 keeps the OPF and moves it to **PyPSA-Eur as of 2026, on the 2025 OSM-based grid, for a 2024 day** — a working OPF first; truing it up to measured data comes after.

## Architecture (settled 2026-09-02)

1. **Grid**: PyPSA-Eur's OSM-based European network (Xiong et al., *Nature Scientific Data* 2025), built by PyPSA-Eur's own `base_network`.
2. **Workflow**: PyPSA-Eur as of 2026, run from a [pinned sibling checkout](pypsa-eur-sibling.md) with a config committed here, HiGHS as solver. Load disaggregation, plant matching and renewable profiles are upstream's (JRC Energy Atlas, powerplantmatching, atlite).
3. **Signal**: v1's family unchanged — net power per node, loaded-vs-easy branches, direction arrows, per-node tooltips.
4. **Web tool**: this repo, the viewer of the solved network; `Scattermapbox` pinned ([codebase-v1](codebase-v1.md)).
5. **Visual language** (settled 2026-09-10): one colourscale, Plotly's `tropic`, for every mapped value — node net power, zonal price — and purple reserved for market-binding elements. A second scale beside the purple was tried and rejected as a clash.

## Dataflow

The [root system diagram](../README.md#system-design) owns runtime components and
serving boundaries. Component details live with [OPF](../coppersushi/opf/README.md),
[grid catalog](../coppersushi/grid_catalog/README.md),
[publication](../coppersushi/publication/README.md) and the [browser](../frontend/README.md).


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

The [production Lambda deployment](../infra/lambda/README.md) runs the OPF Dash server behind AWS Web Adapter. OPF responses carry only the
selected hour’s four traces; API keys come from a dedicated secret. Rendering, S3 reuse and cross-origin framing are verified; measured startup
limits are recorded in the deployment README.

The OPF page first displays its basemap and camera, then adds the network when the
figure is ready. A small loading label leaves the map visible during that request.
The page owns the map layout. Every hour load, including the first, replaces only
the network traces, preserving the user's zoom and camera.

Image preparation precomputes each OPF hour into a token-free compressed figure.
Runtime reads the selected hour and supplies the Mapbox token; local checkouts
without the bundle retain on-demand figure construction.

An optional CloudFront hostname fronts the Lambda deployment, with an ACM certificate
and externally managed DNS; see [hosting](../infra/lambda/README.md#delivery).

For external-input resilience, see [JAO availability and response retention](jao-availability.md).
