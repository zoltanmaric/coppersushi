# Copper Sushi 2 — optimal power flow on the 2025 grid

The in-place successor of [v1](copper-sushi-app.md). v1 visualized a *model's* optimal power flow on the 2013 GridKit grid ("the math is real, the data is not"). Sushi 2 keeps the OPF and moves it to **today's PyPSA-Eur on the 2025 OSM-based grid, for a 2024 day** — first a working OPF; truing it up to measured data comes after.

## Architecture (settled 2026-09-02; supersedes the 2026-08-19 measured-injections design)

1. **Grid**: PyPSA-Eur's OSM-based European network (Xiong et al., *Nature Scientific Data* 2025), built by PyPSA-Eur's own `base_network`.
2. **Workflow**: today's PyPSA-Eur, run from a [pinned sibling checkout](pypsa-eur-sibling.md) with a config committed here, HiGHS as solver. Load disaggregation, plant matching and renewable profiles are upstream's (JRC Energy Atlas, powerplantmatching, atlite).
3. **Signal**: v1's family unchanged — net power per node, loaded-vs-easy branches, direction arrows, per-node tooltips.
4. **Web tool**: this repo, the viewer of the solved network; `Scattermapbox` pinned ([codebase-v1](codebase-v1.md)).
5. **Later**: true-up to actuals — renewable dispatch calibrated to zonal actuals, units ≥ 100 MW fixed to measured output, validation against measured flows ([nodal-disaggregation](nodal-disaggregation.md) for what is and is not measurable).

Why the pivot: load has no sub-zonal measurement anywhere, so "measured injections" were always going to be zonal measurements spread by static keys, and the cross-border check could not separate load errors from generation errors. Full rationale in [specs/sushi-2.md](specs/sushi-2.md).

## Dataflow

Solid nodes and edges are implemented; **dashed (class `planned`) are planned** and turn solid in the PR that lands them. Node IDs are stable domain-artifact identities; each arrow means "required to produce." PyPSA-Eur's internal rule chain is upstream's topology and is drawn on [pypsa-eur-sibling](pypsa-eur-sibling.md), not here.

```mermaid
flowchart LR
    classDef planned stroke-dasharray: 5 5,stroke:#888,color:#888,fill:none

    zenodo_osm_prebuilt[("zenodo_osm_prebuilt<br/>external CSV dataset")]
    osm_grid_tables["osm_grid_tables<br/>GridTables"]
    european_grid["european_grid<br/>pypsa.Network"]
    net_power_map["net_power_map<br/>go.Figure (Dash app)"]

    pypsa_eur_pin["pypsa_eur_pin<br/>pypsa-eur.pin + config/coppersushi.yaml"]:::planned
    pypsa_eur_run["pypsa_eur_run<br/>Snakemake in ../pypsa-eur (HiGHS)"]:::planned
    solved_network["solved_network<br/>networks/*.nc"]:::planned

    zenodo_osm_prebuilt --> osm_grid_tables
    osm_grid_tables --> european_grid
    european_grid --> net_power_map

    pypsa_eur_pin -.-> pypsa_eur_run
    pypsa_eur_run -.-> solved_network
    solved_network -.-> net_power_map
```

The `zenodo_osm_prebuilt → european_grid` path is deleted after Sep 11, once `solved_network` exists: PyPSA-Eur's `base_network` builds the same grid from the same CSVs. External I/O belongs in `pipeline/sources/` or `pipeline/sinks/`; transformations exchange in-memory values. The architecture test checks a finite set of direct I/O APIs and deliberately does not claim to detect dynamic or transitive I/O.

## Deliberately out (this phase)

Flow-traced nodal carbon intensity (first future chapter); OPF counterfactual mode; JAO CNEC/flow-based-domain modeling (spot-check validation only); forecasting; article copy; hosting (trivial, decided at the end).

Validation is exploratory: computed flows vs ENTSO-E measured cross-border flows, FR–DE as the falsifiable AC comparison, ES–FR as the narrated case study, boring + eventful days mixed; discrepancies investigated and calibrations reported individually and honestly.

Working state: [specs/sushi-2.md](specs/sushi-2.md).
