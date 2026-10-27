# Copper Sushi 2 — optimal power flow on the 2025 grid

The in-place successor of [v1](copper-sushi-app.md). v1 visualized a *model's* optimal power flow on the 2013 GridKit grid ("the math is real, the data is not"). Sushi 2 keeps the OPF and moves it to **PyPSA-Eur as of 2026, on the 2025 OSM-based grid, for a 2024 day** — a working OPF first; truing it up to measured data comes after.

## Architecture (settled 2026-09-02)

1. **Grid**: PyPSA-Eur's OSM-based European network (Xiong et al., *Nature Scientific Data* 2025), built by PyPSA-Eur's own `base_network`.
2. **Workflow**: PyPSA-Eur as of 2026, run from a [pinned sibling checkout](pypsa-eur-sibling.md) with a config committed here, HiGHS as solver. Load disaggregation, plant matching and renewable profiles are upstream's (JRC Energy Atlas, powerplantmatching, atlite).
3. **Signal**: v1's family unchanged — net power per node, loaded-vs-easy branches, direction arrows, per-node tooltips.
4. **Web tool**: this repo, the viewer of the solved network; `Scattermapbox` pinned ([codebase-v1](codebase-v1.md)).
5. **Visual language** (settled 2026-09-10): one colourscale, Plotly's `tropic`, for every mapped value — node net power, zonal price — and purple reserved for market-binding elements. A second scale beside the purple was tried and rejected as a clash.

## Dataflow

Solid nodes and edges are implemented; **dashed (class `planned`) are planned** and turn solid in the PR that lands them. Node IDs are stable domain-artifact identities; each arrow means "required to produce." PyPSA-Eur's internal rule chain is upstream's topology and is drawn on [pypsa-eur-sibling](pypsa-eur-sibling.md), not here.

```mermaid
flowchart LR
    classDef planned stroke-dasharray: 5 5,stroke:#888,fill:none

    net_power_map["net_power_map<br/>go.Figure (Dash app)"]

    pypsa_eur_pin["pypsa_eur_pin<br/>pypsa-eur.pin + config/coppersushi.yaml"]
    pypsa_eur_run["pypsa_eur_run<br/>coppersushi.data_sources.pypsa_eur → Snakemake in ../pypsa-eur (HiGHS)"]
    solved_network["solved_network<br/>networks/opf-&lt;day&gt;.nc, Git LFS"]
    jao_active_constraints["jao_active_constraints<br/>post-auction binding constraints, shadow prices and zonal PTDFs by market time unit"]
    adjacent_attribution["adjacent_attribution<br/>selected interface: Nordic opposite-hub PTDFs and duals, adjacent published price"]
    jao_attribution["jao_attribution<br/>α, Polish allocation limits and net positions, guarded PL alternative prices"]
    jao_domain["jao_domain<br/>final flow-based domain: monitored elements with their substation names, PTDFs and RAM"]
    jao_endpoint_cache["jao_endpoint_cache<br/>validated seed bundled in the image; viewed-hour misses fetched and cached locally"]
    osm_locator["osm_locator<br/>core-tso-data's OSM-locator substation coordinates, unlicensed, fetched locally"]
    cnec_geometry["cnec_geometry<br/>each named element and publisher placed by its published substations; interim until jao_elements"]
    zone_shapes["zone_shapes<br/>Core bidding-zone polygons derived from solved_network at image build; small bundled GeoJSON read at runtime"]
    mapbox_basemap["mapbox_basemap<br/>Mapbox's dark style fetched per process, label layers removed"]

    jao_static_grid["jao_static_grid<br/>JAO's Core Static Grid Model, fetched per release: real ratings and R/X/B/G per element EIC"]

    unsimplified["unsimplified_build<br/>skip PyPSA-Eur's 380 kV lift: keep voltage levels and transformers"]:::planned
    jao_elements["jao_elements<br/>JAO data + OSM substations → JAO's Core elements matched to our lines and transformers, with PTDFs, limits and shadow prices"]:::planned
    day_ahead_prices["day_ahead_prices<br/>published zonal clearing prices by market time unit"]
    cnec_market_snapshot["cnec_market_snapshot<br/>one market time unit: zonal prices, active rows, selected relative contribution"]
    cnec_price_figure["cnec_price_figure<br/>go.Figure: zonal price choropleth, market-binding CNECs and the selected row's zonal influence"]
    jao_map["jao_map<br/>/cnec/&lt;day&gt;: cleared zonal prices, active CNECs and selected PTDF contribution"]
    trued_network["trued_network<br/>solved_network with JAO limits on matched lines and transformers, checked pairs attached"]:::planned

    pypsa_eur_pin --> pypsa_eur_run
    pypsa_eur_pin -.-> unsimplified
    unsimplified -.-> solved_network
    pypsa_eur_run --> solved_network
    opf_full["opf_full<br/>/opf-2024: OPF with app navigation"]
    opf_embed["opf_embed<br/>/embed/opf-2024: map and hourly controls"]
    article_iframe["article_iframe<br/>existing article iframe at app root; ROOT_VIEW=embed"]
    net_power_map --> opf_full
    net_power_map --> opf_embed
    opf_embed --> article_iframe
    solved_network --> net_power_map
    solved_network --> zone_shapes
    zone_shapes --> cnec_price_figure
    jao_domain --> jao_endpoint_cache
    jao_active_constraints --> jao_endpoint_cache
    jao_endpoint_cache --> cnec_geometry
    osm_locator --> cnec_geometry
    cnec_geometry --> cnec_price_figure
    mapbox_basemap --> cnec_price_figure
    solved_network -.-> jao_elements
    jao_static_grid -.-> jao_elements
    jao_static_grid -.-> trued_network
    jao_active_constraints -.-> jao_elements
    adjacent_attribution --> cnec_market_snapshot
    jao_attribution --> cnec_market_snapshot
    cnec_geometry --> cnec_market_snapshot
    zone_shapes --> cnec_market_snapshot
    jao_active_constraints --> cnec_market_snapshot
    day_ahead_prices --> cnec_market_snapshot
    jao_elements -.-> cnec_price_figure
    cnec_market_snapshot --> cnec_price_figure
    cnec_price_figure --> jao_map
    jao_elements -.-> trued_network
    solved_network -.-> trued_network
```

Code is one package, `coppersushi/`, organised by domain noun; `io-boundary` in `coppersushi/AGENTS.md` names the two modules that touch the world.

## Future chapters

True-up to actuals — renewable dispatch calibrated to zonal actuals, units ≥ 100 MW fixed to measured output, validation against measured cross-border flows ([nodal-disaggregation](nodal-disaggregation.md) for what is and is not measurable). Then flow-traced nodal carbon intensity, OPF counterfactuals, hosting. Working state: [specs/sushi-2.md](specs/sushi-2.md).

The OPF model has 4,390 buses and 24 hourly snapshots for 29 August 2024, displayed
in Europe/Brussels time. `/` uses the embed during the first rollout. The later root
switch to the full layout requires the article iframe to use `/embed/opf-2024` first;
that article edit and root switch remain pending. Both 2013 app models are removed.

The [Lambda trial](aws-lambda-hosting.md) adds an isolated hosting path: the same Dash
server behind AWS Web Adapter (OPF responses carry only the selected hour’s four traces), with complete dynamic-cache bundles in private S3 and
API keys read from a trial-specific secret. Trial rendering, S3 reuse and cross-origin framing are verified; measured startup
limits are recorded in the hosting page. Heroku remains production.
