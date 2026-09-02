# Spec: Copper Sushi 2 (burn-down)

Working memory. Architecture: [sushi-2.md](../sushi-2.md).

## Problem

The smallest impressive cut of the nodal-flows-from-actuals map. Demo day: **2026-08-12** (eclipse day; headline figures from the Electricity Maps newsletter — verify against ENTSO-E/OMIE before using them anywhere). Target: days; Sep 11 absolute deadline.

## Approach

In-place rewrite on main (v1 = the `v1` release). Iterative: only the next steps are detailed; later items stay coarse and are re-planned after each landing. 15-min resolution (native since the Oct 2025 MTU switch). Validation is exploratory, not pre-registered: compute, compare to measured flows, investigate discrepancies, report calibrations honestly. HVDC links are pinned to measured values (stated openly) — physics is genuinely tested only on AC corridors, so **FR–DE is the falsifiable comparison; ES–FR is the narrated case study**. Validation days: a small smart mix — a few boring high-flow days + a couple of eventful ones incl. the demo day. Rejected for this cut: CNEC modeling, OPF counterfactual, carbon layer, load keys beyond the JRC Energy Atlas raster (EUBUCCO/DBSM floor area, night-time lights), reconciliation QP (proportional rescaling suffices until a bound binds), irradiance-weighted small-solar split (capacity-pro-rata first; CAMS/SARAH likely don't model eclipse obscuration — check before investing).

## Next steps (detailed)

1. **Injections, measured**: per-unit actuals for 2026-08-12 via `entsoe-py` (token in `.secrets/.entsoe_api_token`; `query_generation_per_plant` broken upstream since Nov 2025 — issue #480, budget a workaround); geolocate via JRC-PPDB-OPEN's unit EIC → coordinates, backfilled from Global Energy Monitor for post-2019 units (`powerplantmatching` sets ENTSO-E lat/lon to NaN — budget real effort here); measure per-unit coverage vs zonal totals as a diagnostic (known gaps, e.g. French run-of-river). First probe which zones return 15-min resolution for the day.
2. **Zonal actuals**: per-type generation + load per zone for the day (needed for the remainder split and coverage diagnostic).

## Later (coarse, re-plan after each landing)

3. Remainder injections (zonal per-type totals minus per-unit actuals, pro-rata over geolocated registries; measured sub-national feed-in where available) + load split by the JRC Energy Atlas raster (validate against éCO2mix régional) → 4. `lpf()`, decide slack/imbalance handling from what the first run shows → 5. Compare to measured cross-border flows (12.1.G), explore, calibrate, report → 6. Viz (deferred decision; default: v1's Dash path on `Scattermapbox`. plotly's MapLibre path is ruled out and deck.gl is the upgrade path — see [codebase-v1](../codebase-v1.md) § Known weaknesses) → 7. Host (trivial, last).

## Acceptance criteria

- [ ] One command computes a given day (laptop-scale).
- [ ] Flow-vs-measured comparison for the validation days written up in the wiki, calibrations individually reported.
- [ ] Map of 2026-08-12: net power nodes, branch loadings, direction arrows, tooltips, time slider.
- [ ] Spec burned to nothing; durable findings distilled to the wiki; this file deleted.
