# Spec: Copper Sushi 2 (burn-down)

Working memory. Architecture: [sushi-2.md](../sushi-2.md).

## Problem

A v1-style optimal power flow for one recent day on the 2025 OSM grid, produced by today's PyPSA-Eur, with measured data calibrating and constraining it. Demo day: the newest day whose data fetches comfortably — 2025 or 2026, chosen while fetching, not researched. Deadline: **Sep 11**.

Scrapped 2026-09-02: the measured-injections + `lpf()` statement. Load has no sub-zonal measurement anywhere, and the cross-border check cannot separate a load-spreading error from a generation-spreading error. An OPF with measured constraints keeps what was measurable and lets the optimiser fill what was not.

## Approach

- **Pipeline lives in the fork** ([zoltanmaric/pypsa-eur](https://github.com/zoltanmaric/pypsa-eur)): `master` mirrors upstream; branch `coppersushi-opf` carries `config/coppersushi.yaml` plus the enhancement scripts; solver HiGHS. Template: upstream's `config/examples/config.validation.yaml` (fixed capacities, no CO₂ cap, plants filtered by commissioning date).
- **Coppersushi is the viewer** of the solved `.nc`, as v1 was, plus thin post-processing. `pipeline/` OSM grid assembly is deleted once the fork produces a network — PyPSA-Eur's `base_network` builds the same grid from the same CSVs.
- Resolution: 2-hourly for the smoke run; hourly for the demo day if solve time allows (ERA5 is hourly, so 15-min is out).
- Validation exploratory: computed vs measured cross-border flows, FR–DE falsifiable, ES–FR narrated; HVDC pinned to measured values.
- Out: carbon layer, CNEC modelling, forecasting, article copy; hosting last.

## Steps

1. **Fork refresh**: old master → `legacy-2022`; master = upstream; pixi env; HiGHS. *(Sep 2–3)*
2. **2013 day on the OSM grid**: `clusters: all`, 2H, `transmission_limit: v1.01`, prebuilt cutout. Proves the toolchain; the app draws it as a third network. **Guaranteed demo fallback.** *(Sep 3–4)*
3. **Demo day**: new ERA5 cutout via CDS; load via upstream's ENTSO-E retrieval; check fuel-price and nuclear-availability series reach the day, else static fallbacks. *(Sep 4–6)*
4. **Renewable calibration**: scale each zone's per-type availability so the modelled sum matches ENTSO-E zonal per-type actuals (16.1.B) — upstream's own validation reports over-estimated wind/solar. *(Sep 6–7)*
5. **Measured units as constraints**: fix every reported unit ≥ 100 MW (16.1.A) to its actual output; OPF dispatches the rest. Geolocation join: JRC-PPDB-OPEN + Global Energy Monitor ([survey](../nodal-disaggregation.md)). *(Sep 7–9)*
6. **Validation** vs measured cross-border flows (12.1.G); calibrations reported individually. *(Sep 9–10)*
7. **Viz + hosting**: `Scattermapbox` pinned ([codebase-v1](../codebase-v1.md)); host last. *(Sep 10–11)*

## Acceptance criteria

- [ ] One command in the fork solves a given day on the OSM grid with HiGHS.
- [ ] The app shows the demo day: net power nodes, branch loadings, direction arrows, tooltips, time slider.
- [ ] Units ≥ 100 MW dispatch at measured output; zonal renewables match measured totals.
- [ ] Flow-vs-measured comparison written up in the wiki.
- [ ] Spec burned to nothing; durable findings distilled; this file deleted.
