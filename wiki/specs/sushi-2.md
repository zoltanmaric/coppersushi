# Spec: Copper Sushi 2 — hackathon cut (burn-down)

Working memory for the build. Architecture and rationale: [sushi-2.md](../sushi-2.md). Validation commitments: [sushi-2-pre-registration.md](../sushi-2-pre-registration.md).

## Problem

Build the smallest impressive cut of the nodal map: **August 12, 2026** (the eclipse price-divergence day — €274/MWh ES-vs-Core spread while the Pyrenees interconnector ran at 499 MW of 2.8 GW nominal), European grid scope, ES–FR validation focus. Target: **done in days**; Sep 11 (demo day) is the absolute deadline.

## Approach

In-place rewrite on main (v1 preserved as the `v1` release). Pipeline first, viz last. Date is a parameter, never hard-coded. Rejected for this cut: CNEC/flow-based modeling, OPF counterfactual, carbon layer, better-than-NUTS3 load split (revisit only if validation points at it), 15-min resolution (hourly acceptable, 15-min if free).

## Remaining work (burn down)

1. **Grid**: load PyPSA-Eur prebuilt OSM network; sanity-check ES–FR corridor topology/capacities against known 2.8 GW nominal.
2. **Injections, measured**: ENTSO-E per-unit actuals for 2026-08-12 via `entsoe-py`; geolocate with `powerplantmatching`; pin to nodes. Zonal per-type actuals for all EPEX-coupled zones.
3. **Injections, estimated**: sub-100 MW remainder by registry layout × CAMS/SARAH-3 irradiance; load by NUTS3 pop/GDP prior.
4. **Flows**: `lpf()` on full injections; then reconciliation QP (HiGHS).
5. **Validate**: evaluate pre-registration (a)/(b)/(c); calibrate per policy; report.
6. **Viz**: decide stack from remaining time; render the day with v1's signal family + hour slider; iframe-able page.

## Acceptance criteria

- [ ] One command computes the full day for a given date argument (laptop-scale).
- [ ] Pre-registration criteria evaluated and reported in the wiki (results page linked from the pre-registration page).
- [ ] Map of 2026-08-12 renders with net power nodes, branch loadings, direction arrows, tooltips, hour slider; usable in an iframe.
- [ ] Spec burned down to nothing; durable findings distilled into the wiki; this file deleted.
