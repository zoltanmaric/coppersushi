# Copper Sushi 2 — nodal flows from actual data

The in-place successor of [v1](copper-sushi-app.md). v1 visualized a *model's* optimal power flow on the 2013 GridKit grid ("the math is real, the data is not"). Sushi 2 inverts the caveat: **measured injections through grid physics on the 2025 OSM-based grid — the data is real too**. No optimization of dispatch, no predictions: with injections set, flows are determined.

## Architecture (settled 2026-08-19)

1. **Grid**: PyPSA-Eur's prebuilt OSM-based European network (Xiong et al., *Nature Scientific Data* 2025, Tom Brown's group).
2. **Injections**: ENTSO-E Actual Generation per Generating Unit (≥100 MW, hourly, via `entsoe-py`) geolocated with `powerplantmatching`; sub-100 MW remainder distributed by registry capacity layout × satellite irradiance actuals (CAMS/SARAH-3); load = zonal actuals split by NUTS3 population/GDP prior (kept until validation proves it the binding problem).
3. **Physics**: linear power flow (`network.lpf()`); refinement = reconciliation QP (HiGHS) — measured per-unit injections pinned, estimated splits constrained to zonal totals, minimize deviation from prior.
4. **Signal**: v1's family unchanged — net power per node, loaded-vs-easy branches, direction arrows, per-node tooltips — driven by actuals.
5. **Web tool**: Python core; viz stack deliberately open (pipeline first, viz decided from remaining time).

## Deliberately out (this phase)

Flow-traced nodal carbon intensity (first future chapter); OPF counterfactual mode; JAO CNEC/flow-based-domain modeling (spot-check validation only); forecasting; article copy; hosting (trivial, decided at the end).

Working state: [specs/sushi-2.md](specs/sushi-2.md). Validation commitments: [sushi-2-pre-registration.md](sushi-2-pre-registration.md).
