# Copper Sushi 2 — nodal flows from actual data

The in-place successor of [v1](copper-sushi-app.md). v1 visualized a *model's* optimal power flow on the 2013 GridKit grid ("the math is real, the data is not"). Sushi 2 inverts the caveat: **measured injections through grid physics on the 2025 OSM-based grid — the data is real too**. No optimization of dispatch, no predictions: with injections set, flows are determined.

## Architecture (settled 2026-08-19)

1. **Grid**: PyPSA-Eur's prebuilt OSM-based European network (Xiong et al., *Nature Scientific Data* 2025, Tom Brown's group).
2. **Injections**: ENTSO-E Actual Generation per Generating Unit (≥100 MW, hourly, via `entsoe-py`) geolocated with `powerplantmatching`; sub-100 MW remainder distributed by registry capacity layout × satellite irradiance actuals (CAMS/SARAH-3); load = zonal actuals split by NUTS3 population/GDP prior (kept until validation proves it the binding problem).
3. **Physics**: linear power flow (`network.lpf()`) for AC; HVDC link flows are *pinned to measured values* (lpf doesn't solve them — stated openly, so physics is genuinely tested only on AC corridors). Estimated splits reconciled to zonal totals by proportional rescaling.
4. **Signal**: v1's family unchanged — net power per node, loaded-vs-easy branches, direction arrows, per-node tooltips — driven by actuals.
5. **Web tool**: Python core; viz stack deliberately open (pipeline first, viz decided from remaining time).

## Deliberately out (this phase)

Flow-traced nodal carbon intensity (first future chapter); OPF counterfactual mode; JAO CNEC/flow-based-domain modeling (spot-check validation only); forecasting; article copy; hosting (trivial, decided at the end).

Validation is exploratory: computed flows vs ENTSO-E measured cross-border flows, FR–DE as the falsifiable AC comparison, ES–FR as the narrated case study, boring + eventful days mixed; discrepancies investigated and calibrations reported individually and honestly.

Working state: [specs/sushi-2.md](specs/sushi-2.md).
