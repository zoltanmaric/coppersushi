# Nodal load and generation from measured data — literature survey (2026-09-02)

What is known about splitting national measurements into per-node injections, and how it changes the Sushi 2 plan. Written for the measured-injections design; after the [2026-09-02 pivot](specs/sushi-2.md) the load findings are covered by PyPSA-Eur itself and the geolocation join serves the measured-unit constraints. Web survey; items marked *unverified* were not checked against primary data.

## Load: the GDP/population split is superseded

- **PyPSA-Eur itself** dropped the 60/40 GDP/population NUTS3 split for the EU in v2026.02.0, in favour of the [JRC Energy Atlas](https://data.jrc.ec.europa.eu/dataset/76a6b550-253c-44a4-9a4c-d22079e7bf62) 1 km consumption raster (reference year 2019; [PR #1829](https://github.com/PyPSA/pypsa-eur/pull/1829)). The old split survives only as a non-EU fallback, and a bug ignored its population weight until Jul 2026 ([PR #2241](https://github.com/PyPSA/pypsa-eur/pull/2241)).
- **Mu et al. 2026 (KIT)** is the first validation of allocation keys against *metered* sub-national demand: 1,891 GB primary substations, error reduced 41–43 % by night-time lights + substation proximity; a static land-use pipeline beat the best learned model, and corrections must be *additive* (multiplicative ones increased error). [arXiv:2605.24491](https://arxiv.org/abs/2605.24491)
- **No open EU-wide sub-national historical 15-min demand series exists.** Candidates are annual ([Patil 2025](https://www.nature.com/articles/s41597-025-05938-1)), scenario-year ([FfE eXtremOS](https://opendata.ffe.de/dataset/load-curves-of-the-private-household-sector-extremos-solideu-scenario-europe-nuts-3/)), or Germany-only ([DemandRegio](https://github.com/DemandRegioTeam/disaggregator), natively 15-min; [eGon](https://egon-data.readthedocs.io), building-level).
- **Consequence**: shape from ENTSO-E national load, split by a static key (JRC Energy Atlas first; building floor area from [EUBUCCO](https://eubucco.com/)/[JRC DBSM](https://data.jrc.ec.europa.eu/dataset/a601a4a8-9289-4fc4-983a-25d54f957f3a) as a refinement). Validate against [RTE éCO2mix régional](https://odre.opendatasoft.com/explore/dataset/eco2mix-regional-tr/), measured 15-min regional data.

## Generation: geolocation is the unsolved piece

- ENTSO-E per-unit actuals (16.1.A, ≥100 MW) carry **no coordinates**, and `powerplantmatching`'s ENTSO-E loader sets lat/lon to NaN. The join is [JRC-PPDB-OPEN](https://data.jrc.ec.europa.eu/dataset/9810feeb-f062-49cd-8e76-8d8cfd488a05) (unit EIC → coordinates, frozen 2019-07), backfilled from the [Global Energy Monitor tracker](https://globalenergymonitor.org/projects/global-integrated-power-tracker/) (Aug 2026) for newer units.
- **Remainder (< 100 MW)**: zonal totals per production type (16.1.B) minus per-unit actuals, allocated pro-rata over registries *with coordinates*: [MaStR](https://open-mastr.readthedocs.io/en/latest/dataset/) (DE, exact coordinates ≥ 30 kW), [osm-powerplants](https://github.com/open-energy-transition/osm-powerplants), GEM; run-of-river typed via the [JRC hydro database](https://github.com/energy-modelling-toolkit/hydro-power-database). Where measured sub-national feed-in exists — [SMARD](https://www.smard.de/en/downloadcenter/download-market-data) control areas, éCO2mix régional, [Elia](https://opendata.elia.be/explore/dataset/ods032/) — allocate against that instead of the zonal total. Do not use atlite for this: ERA5 is hourly at 0.25°, and it models rather than measures.
- Satellite PV inventories are too stale (≤ 2022) and give area, not MW.

## PyPSA-Eur has no "historical day with actual dispatch" mode

`solve_operations_network` is *optimal* dispatch at fixed capacities, hourly. `config/examples/config.validation.yaml` optimises 2019 and then compares against ENTSO-E; [doc/validation.md](https://github.com/PyPSA/pypsa-eur/blob/master/doc/validation.md) lists the misses (wind/solar overestimated, nuclear outages missed, run-of-river misclassified). Fixing measured dispatch inside the OPF would be new here ([ledger](upstream-contributions.md)).

## Unverified

No published work reconstructs European nodal flows from JAO flow-based data validated against measured flows.
