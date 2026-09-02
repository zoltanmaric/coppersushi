# Spec: Copper Sushi 2 (burn-down)

Working memory. Architecture: [sushi-2.md](../sushi-2.md).

## Problem

A working v1-style optimal power flow for one 2024 day on the 2025 OSM grid, produced by today's PyPSA-Eur with HiGHS and drawn in the app. Deadline: **Sep 11**. Start small: a working OPF first; truing it up to measured data comes after.

Demo day is 2024 because upstream's data stack ends there (prebuilt cutout `europe-1940-2024-era5`, `nuclear_p_max_pu.csv` last column 2024, renewable capacity year 2024). Later years cost a CDS cutout build and a nuclear-series extension.

## Approach

- **PyPSA-Eur is a pinned sibling checkout** ([design](../pypsa-eur-sibling.md)): `pypsa-eur.pin` in this repo records URL + commit; a small runner checks the sibling out at the pin and runs Snakemake with `--configfile config/coppersushi.yaml`. One checkout, one data directory, shared by every worktree.
- **This repo owns** the pin, the runner, the config and the solved networks (`networks/opf-<day>.nc`, versioned with Git LFS; Zenodo for the published demo artifact). `pipeline/` OSM grid assembly stays until a solved network exists, then goes — redundant with PyPSA-Eur's `base_network`.
- **Config** is written against `config/schema.default.json`, not copied from `config/examples/config.validation.yaml`, which carries keys today's code ignores (`scenario.ll`, `clustering.simplify_network.exclude_carriers`; live: `electricity.transmission_limit`, `clustering.exclude_carriers`).
- Non-goals for this cut: true-up to actuals (calibration, measured constraints, validation), carbon layer, modelling of critical network elements and contingencies, forecasting, article copy, hosting.

## Next steps

1. **Solve 2013-07-17 (v1's day) on the OSM grid and draw it** — **done 2026-09-02** (pin + runner + config; three `clusters: all` bugs patched on the fork branch `fix/clusters-all`; load shedding on as insurance, none used; HiGHS 90 s). Config as landed: pin file + runner + `config/coppersushi.yaml`; the app loads the solved network alongside the two it draws today. Config: `clusters: all` (`simplify_network` always runs first — lifted to 380 kV, stubs removed — so this is the simplified bus set, as v1's was, not the raw 6864-bus OSM layer), `transmission_limit: v1.0` (genuinely fixed lines; `v1.01` sets every line extendable — use it, or `load_shedding`, only if `v1.0` is infeasible), HiGHS with `threads` raised from the profile's 1, `transmission_losses: 0`, `noisy_costs: false`, `dynamic_fuel_price: false` (the monthly-price reindex yields all-NaN costs for a window not starting on a month boundary — [ledgered](../upstream-contributions.md)). Temporal resolution: decide from the first solve time. If `all` will not solve within a day, drop to a few hundred clusters.
2. **The 2024 day**: same config, snapshots moved; plants filtered by commissioning date (`powerplants_filter`).

## Acceptance criteria

- [ ] One command here solves a given 2013 or 2024 day on the OSM grid with HiGHS via the pinned sibling.
- [ ] The app shows the 2024 day: net power nodes, branch loadings, direction arrows, tooltips, time slider.
- [ ] Spec burned to nothing; durable findings distilled; this file deleted.

## Future chapters (settled facts, not planned work)

True-up to actuals, in order: zonal per-type equality on renewable dispatch (ENTSO-E 16.1.B) via `custom_extra_functionality`; measured units ≥ 100 MW (16.1.A) fixed and HVDC pinned — `clustering.exclude_carriers` keeps them per-plant, matching by name/capacity/coordinates since the EIC does not survive PyPSA-Eur's generator naming, fixed-unit output netted out of zonal targets; validation against measured cross-border flows (12.1.G). Evidence: [nodal-disaggregation](../nodal-disaggregation.md). Then carbon layer, OPF counterfactuals, hosting.
