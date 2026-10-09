# Spec: CNEC constraint selection

Working memory, 2026-10-09. [App semantics](../copper-sushi-app.md), [country-cap research](../country-import-export-caps.md), [price attribution](../flow-based-market-coupling.md#price-contribution).

## Problem

Let users select the constraint they see on the map and understand its signed contribution to a zonal price spread. A country outline represents a country-wide import/export cap, not an individual interconnector.

## Approach

Agreed: direct selection of country outlines, transformer markers and existing purple constrained lines along their length; selected-border highlighting; comparison rays; previous/next market-time-unit buttons and minor timeline ticks. Keep the selector synchronized with map selection.

Deferred: collapsible map controls. Open: reference-zone behaviour. The 2026 country-cap inventory is complete: Poland has an aggregate cap; the other Core zones have none listed. For Poland, use the empirically validated market-price minus `PL_ALT` calculation and guarded quarter-hour reconstruction described in the research page. Missing attribution remains unavailable, never an observed-spread fallback.

Physical-row attribution must explicitly handle the documented FB/LTA scaling distinction. Hosting and forecasting are separate work. Main includes concurrent zone-price fetching and staged loading feedback ([PR #100](https://github.com/zoltanmaric/coppersushi/pull/100)).

## Acceptance criteria

- [x] Validate a usable Polish cap-price source and interval mapping: six days, 576 intervals, independent FB-price reconstruction within €0.02/MWh.
- [x] Establish country-cap coverage for every Core zone using the 2026 SDAC inventory, phase-out notice and cache/API checks.
- [ ] Resolve reference-zone behaviour and implement the Polish adapter with data checks. Countries with no aggregate cap remain unhighlighted; any historical cap support must be explicit. Use the [audited taxonomy](../jao-constraint-types.md): distinguish physical assets, aggregate caps, virtual hubs, equalities and LTA facets; preserve unresolved metadata rather than guessing from names.
- [ ] Define and validate FB/LTA attribution against published spreads; handle α=0 and α<1 without double-counting or presenting raw FB terms as an exhaustive decomposition.
- [ ] Previous/next moves one interval and disables at day boundaries. Minor ticks and exact selected time work for hourly/quarter-hourly data and daylight-saving transition days.
- [ ] Country outlines, transformer points and line interiors select the intended row and update the selector. Day/interval changes update or clear selection, tooltip and rays together.
- [ ] Labels state the selected constraint, reference, signed €/MWh contribution and MW capacity separately. Cover offsetting contributions and unavailable data; reject raw-spread fallback.
- [ ] Verify in Chrome with country caps, transformers and lines where verified data exists. Retain loading/retry behaviour; rays must not imply physical power-flow paths.

Burn down as changes land; move surviving knowledge into the app page and delete this spec when complete.
