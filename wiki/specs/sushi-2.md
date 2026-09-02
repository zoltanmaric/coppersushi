# Spec: Copper Sushi 2 (burn-down)

Working memory. Architecture: [sushi-2.md](../sushi-2.md).

## Problem

A v1-style optimal power flow for one recent day on the 2025 OSM grid, produced by today's PyPSA-Eur, with measured data calibrating and constraining it. Demo day: **a 2024 day** — upstream's data stack ends there (prebuilt cutout `europe-1940-2024-era5`, `nuclear_p_max_pu.csv` last column 2024, renewable capacity year 2024, demand archive to 2026-02); 2025/26 would cost a CDS cutout build, a nuclear-series extension and `entsoe_electricity_demand.source: build`. Stretch only. Deadline: **Sep 11**.

Scrapped 2026-09-02: the measured-injections + `lpf()` statement. Load has no sub-zonal measurement anywhere, and the cross-border check cannot separate a load-spreading error from a generation-spreading error. An OPF with measured constraints keeps what was measurable and lets the optimiser fill what was not.

## Approach

- **Pipeline lives in the fork** ([zoltanmaric/pypsa-eur](https://github.com/zoltanmaric/pypsa-eur)): `master` mirrors upstream; branch `coppersushi-opf` carries `config/coppersushi.yaml` plus the enhancement scripts; solver HiGHS. Template: upstream's `config/examples/config.validation.yaml` (fixed capacities, no CO₂ cap, plants filtered by commissioning date).
- **Coppersushi is the viewer** of the solved `.nc`, as v1 was, plus thin post-processing. Solved networks are copied into `networks/` and committed like v1's (fall back to a release asset if over GitHub's size limit). `pipeline/` OSM grid assembly stays until after Sep 11 — deleting it is a refactor with no demo value; it is then redundant with PyPSA-Eur's `base_network`, which builds the same grid from the same CSVs.
- Resolution: 2-hourly throughout, as v1 (12 snapshots). Hourly is available (ERA5, ENTSO-E) but adds solve risk for no demo value.
- Validation exploratory: computed vs measured cross-border flows, FR–DE falsifiable, ES–FR narrated. HVDC is *not* pinned before step 5 — an OPF dispatches links; pinning them to actuals is one of the measured constraints, and only AC flows are compared.
- Config is written against `config/schema.default.json`, not copied from `config/examples/config.validation.yaml`, which is stale (`scenario.ll` and `clustering.simplify_network.exclude_carriers` are silently ignored today; the live keys are `electricity.transmission_limit` and `clustering.exclude_carriers`).
- Out: carbon layer, CNEC modelling, forecasting, article copy; hosting last.

## Steps

1. **Fork refresh**: old master → `legacy-2022`; master = upstream; branch `coppersushi-opf` off master; pixi env. No 2022 commits are carried (the cherry-pick experiment showed 41 of 46 conflict and the rest are trivia). *(Sep 2–3)*
2. **2013-07-17 (v1's day) on the OSM grid**: `clusters: all` (note: `simplify_network` always runs first — lifted to 380 kV, stubs removed — so this is the simplified bus set, as v1's was, not the raw 6864-bus OSM layer), 2H, `transmission_limit: v1.0` (genuinely fixed lines; `v1.01` sets every line extendable — use it, or `load_shedding`, only if `v1.0` is infeasible), HiGHS with `threads` raised from the profile's 1, `transmission_losses: 0`, `noisy_costs: false`, `dynamic_fuel_price: false` (the monthly-price reindex yields all-NaN costs for a window not starting on a month boundary — ledgered upstream). Prebuilt cutout. Proves the toolchain; the app draws it as a third network. **Guaranteed demo fallback**; if `all` will not solve within a day, drop to a few hundred clusters. *(Sep 3–4)*
3. **Demo day (2024)**: same config, snapshots moved; prebuilt cutout and demand archive cover it; plants filtered by commissioning date (`powerplants_filter`). *(Sep 4–5)*
4. **Renewable calibration**: per zone and type, constrain dispatch to *equal* ENTSO-E's zonal actuals (16.1.B) via `custom_extra_functionality` — scaling availability alone only moves an upper bound and leaves the OPF free to curtail below the measured total. Scale `p_max_pu` up first where modelled availability falls short of the target, else the equality is infeasible (upstream's own validation reports over-estimated wind/solar, so shortfalls should be rare). Nodal placement within the zone stays with the optimiser, so line limits can still bind. *(Sep 5–6)*
5. **Measured units as constraints**: fix every reported unit ≥ 100 MW (16.1.A) to its actual output; OPF dispatches the rest; HVDC links pinned to measured flows. Mechanics: `clustering.exclude_carriers` keeps the fixed carriers as per-plant generators (no aggregate to carve capacity out of, so nothing is dispatched twice); match ENTSO-E units to them by name, capacity and coordinates — the EIC does not survive PyPSA-Eur's generator naming; apply via the supported `solving.options.custom_extra_functionality` hook, no core edits. Units that are also renewable (offshore wind, large hydro) appear in both 16.1.A and the 16.1.B totals: subtract their fixed output from the step-4 zonal targets, or the zone is counted twice. entsoe-py: `include_eic=True` keeps EICs; per-plant query broken upstream ([ledger](../upstream-contributions.md)). *(Sep 6–9)*
6. **Validation** vs measured cross-border flows (12.1.G); calibrations reported individually. *(Sep 9–10)*
7. **Hosting** (viz landed in step 2; `Scattermapbox` pinned, [codebase-v1](../codebase-v1.md)). *(Sep 10–11)*

## Acceptance criteria

- [ ] One command in the fork solves a given 2013 or 2024 day on the OSM grid with HiGHS.
- [ ] The app shows the demo day: net power nodes, branch loadings, direction arrows, tooltips, time slider.
- [ ] Units ≥ 100 MW dispatch at measured output, HVDC at measured flows; zonal renewables match measured totals.
- [ ] Flow-vs-measured comparison written up in the wiki.
- [ ] Spec burned to nothing; durable findings distilled; this file deleted.
