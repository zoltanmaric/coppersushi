# Spec: Core congestion forecast (burn-down)

Working memory. Target: **Hack on the Grid** (Electricity Maps hackathon, Copenhagen, 2026-09-11), "Power markets" track. Domain: [copper-plate-problem](../copper-plate-problem.md). How the real thing works: [core-day-ahead-capacity-calculation](../core-day-ahead-capacity-calculation.md); "step n" below is that page's numbering. Background: [flow-based-market-coupling](../flow-based-market-coupling.md). Consumes [jao-grid](jao-grid.md)'s matched elements. Architecture: [sushi-2](../sushi-2.md).

## Goal

For one Core day, produce what we would have said at D-2 evening about which rows of the auction's domain bind in each hour and what price spreads they imply. Show it on a page beside what JAO published at 13:00 on D-1. Explain the difference. That is the whole deliverable: one day, one page, one explanation. No scoring, no baseline, no second day until this one has been read by eye.

The day is **2024-08-29**, the day [jao-grid](jao-grid.md) matches; the day is a parameter. It is a hindcast: every input is a stand-in for what a live run at D-2 evening would have, drawn from what is public, and named below. A 2026 day follows by swapping inputs and nothing else.

## What the auction sees, and what we substitute

The auction clears the zones' bids against about 120 rows per hour of "PTDF · net positions ≤ RAM" (step 11). Everything about the grid enters through those rows. So the forecast is: rebuild the rows for D a day early, then clear a cost-based market against them.

| Step | The real input | Our stand-in at D-2 evening |
|---|---|---|
| 1 aligned net positions | D2CF, published 10:30 D-1 | our base case's net positions |
| 2, 3 grid models | never published | PyPSA-Eur's solved day: OSM grid, plant registry, weather-driven availability, the day's load, cost dispatch; no outages, no phase-shifter taps |
| 4 the list, ratings, margins, factors | published 10:30 D-1 | D-1's rows, published 10:30 D-2: the same list, fixed and seasonal ratings, `frm`, `minRamFactor`; dynamic ratings a day old |
| 5 PTDFs and base flows | published 10:30 D-1 | PTDFs: D-1's. Base flow per row: our grid's DC flow on the matched element under its contingency at our dispatch; `fcore` from it through D-1's PTDFs and our net positions. Rows we cannot match keep D-1's `fcore` |
| 6 remedial actions | published 10:30 D-1 | D-1's `fnrao` |
| 7 minimum margin | published 10:30 D-1 | `amr` recomputed by the verified identity from our `fall` and D-1's factor |
| 8, 9 long-term rights, validation | published 10:30 D-1 | D-1's columns |
| 10 RAM and presolve | published 10:30 D-1 | RAM by the verified identity; no presolve, the solver carries redundant rows |
| 11 bids | sold, never published | supply steps per zone from PyPSA-Eur's plants at the day's fuel and carbon prices; demand inelastic at the zone's load; exchanges with zones outside Core fixed from our base case |

## The machine

One linear program per hour. Variables: each hub's net position (twelve zones and the two ALEGrO hubs) and each zone's output per supply step. Per zone, output minus load minus its fixed exchange with non-Core zones equals its net position; the Core net positions sum to zero; the ALEGrO hubs sum to zero and stay within ±1,000 MW, which is what the day's four external constraints say; every row of the domain holds. Minimise cost. Out come the net positions, the rows with a non-zero dual (the binding rows) and their duals (the shadow prices), and the zonal prices as the balances' duals. The implied spread between two zones is the shadow prices times the PTDF differences, the identity checked on [flow-based-market-coupling](../flow-based-market-coupling.md).

Three tables in, one out. In: the rows (per hour: identity, PTDFs, RAM), the bid steps (per zone and hour: capacity, cost), the non-Core exchanges (per zone and hour). Out: per hour, binding rows with shadow prices, net positions, zonal prices. About 11,800 rows and a few hundred variables per hour; HiGHS solves it in well under a second. Swap the rows table and the same program is a different run.

## Runs, in build order

1. **Replay.** The LP has two inputs, the rows and the bids. In the forecast both are ours, so a miss cannot be blamed on either. Replay runs the same LP on JAO's published rows for D with our bids. If replay matches 13:00, our bids are fine and any forecast miss is the grid's. If replay is already off, the bids are the problem before the grid enters. Same program, different table. It exists the moment the LP does, and on a live day it is a product by itself: at 10:30 it says what 13:00 will show.
2. **Yesterday's rows.** D-1's rows unchanged. Already a D-2 forecast, one that assumes the grid's constraints do not move overnight; needs no matching and no grid. The guaranteed deliverable.
3. **Yesterday's rows with our flows.** D-1's rows with `fcore`, `amr` and RAM rebuilt from our grid's flows on the matched elements. The nodal model's whole contribution. Run 2 is what it has to improve on; run 1 is its ceiling.

## Dataflow

```mermaid
flowchart LR

    rows_dm1[("JAO finalComputation for D-1<br/>all rows, all hours; committed")]
    rows_d[("JAO finalComputation for D<br/>the replay's rows; committed")]
    truth[("JAO shadowPrices and priceSpread for D<br/>committed")]
    grid[("solved_network<br/>networks/opf-‹day›.nc")]
    elements[("jao_elements (specs/jao-grid)<br/>the rows' elements and contingency branches on our lines")]

    bids["zonal_bids<br/>supply steps per zone and hour from the network's generators at the day's fuel and carbon prices; load per zone; exchanges with non-Core zones"]
    flows["row_flows<br/>DC flow on each matched element under its contingency at our dispatch → fcore, amr, RAM per row by the verified identities; unmatched rows keep D-1's"]
    lp["zonal_clearing<br/>HiGHS: min cost s.t. balances, ΣNP = 0, ALEGrO, every row → net positions, binding rows, shadow prices, zonal prices"]
    forecast["binding_forecast<br/>per run and hour: binding rows, shadow prices, implied spreads"]
    page["forecast_page<br/>/forecast/‹day›: JAO's binding elements on the left map, ours on the right, one hour slider, one colour scale; spread table beneath"]

    rows_dm1 --> flows
    grid --> flows
    elements --> flows
    flows --> lp
    rows_dm1 --> lp
    rows_d --> lp
    grid --> bids --> lp
    lp --> forecast --> page
    truth --> page
    elements --> page
```

The JAO fetch is jao-grid's adapter with three more pages. Transforms exchange frames; the LP is linopy or scipy on HiGHS, no PyPSA network in it.

## Next steps

1. **Fetch and commit the rows**: `finalComputation` for 2024-08-28 and 2024-08-29, every hour, and `shadowPrices` and `priceSpread` for 2024-08-29, under `data/jao/‹day›/`. About 280,000 rows a day: Parquet under Git LFS with only the columns the LP and the page need.
2. **Bids table** from `networks/opf-2024-08-29.nc`: generators grouped by country with marginal cost and the hour's available capacity; load per country; net exchange with non-Core countries from the solved flows.
3. **The LP, and run 1.** Binding rows and spreads next to 13:00, hour by hour. This is where we learn whether cost bids are good enough for the grid to matter.
4. **Run 2.** Look again.
5. **Matching** (jao-grid's steps 3 and 4) for the elements in D-1's rows, the row flows, **run 3**.
6. **The page.**

## Acceptance criteria

- [ ] One command runs the three runs for 2024-08-29 from committed inputs and writes each run's binding rows, shadow prices, net positions and zonal prices per hour.
- [ ] `/forecast/2024-08-29` shows two maps with one hour slider and one colour scale, JAO's binding elements on the left, a chosen run's on the right, and the spread table beneath.
- [ ] A written explanation of what matches and what does not, per run, on [backtest-2024-08-29](../backtest-2024-08-29.md) or a sibling page.
- [ ] Spec burned to nothing; findings distilled; this file deleted.

## Non-goals

Scoring and baselines; more than one day; price levels as a claim; our own PTDFs through a shift key (D-1's serve for now); redispatch after the auction, remedial actions, outages; a live loop; trading signals.

## Open

- Non-Core exchanges: our base case's or D-1's realised values; run 1 decides.
- The four equality rows in the domain and the allocation constraints EUPHEMIA receives outside it: what they are, whether the LP needs them.
- Transformers and phase shifters: the simplified network has none (jao-grid's precondition), so their rows keep D-1's flows in run 3; 19 of the 116 presolved rows at the first hour.
- Whether run 3's `fcore` is better as a level or as a change: our flow for D minus our flow for D-1, added to D-1's `fcore`, cancels the grid model's bias but needs D-1 solved too.
- Inelastic demand with a price cap may overstate spreads in scarce hours.
