# Spec: Price anatomy (burn-down)

Working memory. Target: **Hack on the Grid** (Electricity Maps hackathon, Copenhagen, 2026-09-11), "Power markets" track — *tools that turn complex market data into something anyone can read*. Everything is built before the day; the day is for the Electricity Maps wiring, the pitch and the jury (product and venture people, not market experts). Domain: [copper-plate-problem](../copper-plate-problem.md). Architecture: [sushi-2](../sushi-2.md).

## Problem

A bidding zone's day-ahead price is one number, EUPHEMIA's dual of the zone's balance constraint. Copper Sushi's OPF has a price per node (`buses_t.marginal_price`). Show what the one number hides: for a chosen zone and hour, the actual price (Electricity Maps), the price the model's own copper-plate market would print, and the spread of nodal prices inside the zone, with the technology that sets each. Readable by anyone: "Germany paid X. A market that saw the grid would have paid −25 in the windy north and 68 in the south, because the line between them is full."

Evidence there is something to show, from the 2013-07-17 solve at noon (€/MWh): DE −25 to 68, FR −129 to 152, ES −30 to 219; EUPHEMIA prints one price for each.

## Approach

- **Day**: **2024-08-29**, [sushi-2 spec](sushi-2.md) step 2. Electricity Maps history reaches back ten years; 2013 has no actual price. Rejected: showing 2013 with no actual column — the comparison *is* the feature.
- **Nodal**: the solved network as is. `plot_power_flow` already colors by `marginal_price`.
- **Zonal model**: cluster the solved network by `buses.country` (PyPSA busmap), one link per border with the border's summed thermal capacity as the pipe — the NTC-style transport idealization EUPHEMIA uses outside the flow-based Core region — and re-solve with HiGHS (36 buses × 12 snapshots, seconds). Zonal price = the zone bus's dual. Rejected: a second PyPSA-Eur run at country resolution (hours, a second data path, and its clustering is not one bus per country). Rejected: flow-based constraints (hourly TSO-published PTDF and margins; the gap is the point, not fidelity to EUPHEMIA). Stretch: ENTSO-E NTCs for the pipes instead of thermal sums.
- **Actual**: `pipeline/sources/electricity_maps.py`, day-ahead price `past-range`, hourly, per zone, for the day; result committed beside the network so the demo needs no network. Zones = countries; for DK, IT, NO and SE the bidding zone containing the capital. Stretch: bidding-zone geometry.
- **Price-setting technology**: per bus and hour, the generator dispatched strictly inside its bounds sets the price; a bus with none takes its price from elsewhere ("imported"); price ≤ 0 means curtailment. Per zone, the carrier whose cost matches the zonal price.
- **View**: one page. Map colored by nodal price for the slider's hour, a zone picker, a panel with the hour's three numbers, a day chart (actual line, model-zonal line, nodal min–max band). Reuses the existing app, slider and loading.
- **Non-goals**: reproducing EUPHEMIA (bids, blocks), flow-based coupling, redispatch cost estimates, live or forecast data.

## Next steps

1. **Launch the 2024 solve first** (hours; `job-supervision`), the day settled beforehand.
2. **Zonal re-solve** on the 2013 network, tested on the checked-in fixture — independent of 1.
3. **Electricity Maps client** and the committed prices — needs a key with price access.
4. **Page and chart**; pitch rehearsed on one zone with the real numbers.

## Acceptance criteria

- [ ] `networks/opf-2024-08-29.nc` promoted; the app draws it.
- [ ] One function turns a solved network into zonal prices (zones × snapshots) in under a minute; tested on the fixture.
- [ ] Day-ahead prices for the day, every zone, committed beside the network.
- [ ] `/price`: pick zone and hour → actual, model-zonal, nodal min/median/max, price-setting technology; day chart.
- [ ] A two-minute pitch on one zone, numbers from the page.
- [ ] Spec burned to nothing; findings distilled; this file deleted.

## Open

- Electricity Maps key with price access before Friday — the full API opens at the event. Fallback: ENTSO-E day-ahead prices via `entsoe-py` (not yet a dependency).
