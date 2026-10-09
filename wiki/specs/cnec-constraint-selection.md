# Spec: CNEC constraint selection

Working memory, 2026-10-09. [App semantics](../copper-sushi-app.md), [country-cap research](../country-import-export-caps.md), [price attribution](../flow-based-market-coupling.md#price-contribution).

## Problem

Let users select the constraint they see on the map and understand its signed contribution to a zonal price spread. A country outline represents a country-wide import/export cap, not an individual interconnector.

## Approach

Agreed: direct selection of country outlines, transformer markers and existing purple constrained lines along their length; selected-border highlighting; comparison rays; previous/next market-time-unit buttons and minor timeline ticks. Keep the selector synchronized with map selection.

Deferred: collapsible map controls. Reference selection follows the [reference-zone rule](#reference-zone). The 2026 country-cap inventory is complete: Poland has an aggregate cap; the other Core zones have none listed. For Poland, use the empirically validated market-price minus `PL_ALT` calculation and guarded quarter-hour reconstruction described in the research page. Missing attribution remains unavailable, never an observed-spread fallback.

Scope includes physical constraints, Poland’s aggregate cap and [virtual-hub interconnectors/interfaces](../virtual-hub-interconnectors.md). Equality and standalone LTA selection remain outside this layer. Physical-row attribution must explicitly handle the documented FB/LTA scaling distinction; at α=0, show attribution as unavailable rather than requiring LTA reconstruction. Hosting and forecasting are separate work. Main includes concurrent zone-price fetching and staged loading feedback ([PR #100](https://github.com/zoltanmaric/coppersushi/pull/100)).

### Reference-zone

Choose the reference automatically for the selected constraint and interval: a transformer or line wholly within one bidding zone uses that zone; a physical or virtual-hub interconnector uses the bidding zone at the sending end of the binding constraint. Poland's country cap uses PL. Recompute the reference when the selected row or its binding direction changes.

Resolve physical endpoints from the selected TSO's element orientation: DIRECT starts at its `substation_from`; OPPOSITE starts at its `substation_to`. Use mapped endpoint bidding zones, not the active feed's `hubFrom`/`hubTo` (maximum PTDF-sensitivity exchange), cheaper-country selection or the sign of forecast `fref`. The reference describes the binding row's direction under its contingency, not a claim about observed base-case flow. Unknown endpoints, ambiguous orientation or an unsupported reference zone make attribution unavailable; do not silently substitute another country. This reference choice does not apply an extra sign flip to published PTDF coefficients.

Virtual-hub references use the [published interface mapping](../virtual-hub-interconnectors.md#hub-mapping) and validated signed flow convention. Adjacent bidding zones such as DK1, NO2 and SE4 can be reference/target endpoints; retain their identity. A virtual-hub label alone does not establish which country is sending.

## Acceptance criteria

- [x] Validate a usable Polish cap-price source and interval mapping: six days, 576 intervals, independent FB-price reconstruction within €0.02/MWh.
- [x] Establish country-cap coverage for every Core zone using the 2026 SDAC inventory, phase-out notice and cache/API checks.
- [x] Agree automatic reference selection: in-zone location for transformers/lines, oriented sending end for interconnectors, PL for the country cap.
- [ ] Implement the reference-zone rule and Polish adapter with data checks. Countries with no aggregate cap remain unhighlighted; any historical cap support must be explicit. Use the [audited taxonomy](../jao-constraint-types.md): distinguish physical assets, aggregate caps, virtual hubs, equalities and LTA facets; preserve unresolved metadata rather than guessing from names.
- [ ] Define and validate physical-row attribution for α>0 against published spreads, including α<1; do not double-count or present raw FB terms as an exhaustive decomposition. At α=0, attribution is unavailable. LTA-facet reconstruction is not required for this layer.
- [ ] Map all audited virtual hubs to explicit interfaces and make them selectable, with binding direction, MW capacity and published shadow price. Preserve row identity and group paired ALEGrO ends as one asset without counting a bound twice; combined/AC interfaces must not masquerade as one cable or whole-country caps.
- [ ] Validate virtual-hub endpoint attribution on sampled intervals for ALEGrO and newer interfaces, covering signs, paired hubs and FB/LTA scaling. Compare the reconstructed endpoint spread with observed prices; show only the selected bound’s validated component, never the full spread. Missing data or unsupported attribution leaves selection available with an explicit unavailable contribution.
- [ ] Previous/next moves one interval and disables at day boundaries. Minor ticks and exact selected time work for hourly/quarter-hourly data and daylight-saving transition days.
- [ ] Country outlines, transformer points, line interiors and virtual-hub interfaces select the intended row and update the selector. Day/interval changes update or clear selection, tooltip and rays together.
- [ ] Labels state the selected constraint, reference, signed €/MWh contribution and MW capacity separately. Cover offsetting contributions and unavailable data; reject raw-spread fallback.
- [ ] Verify in Chrome with country caps, transformers, lines and virtual-hub interfaces where verified data exists. Retain loading/retry behaviour; rays must not imply physical power-flow paths.

Burn down as changes land; move surviving knowledge into the app page and delete this spec when complete.
