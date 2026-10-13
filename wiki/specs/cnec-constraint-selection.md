# Spec: CNEC constraint selection

Working memory, 2026-10-13. [App semantics](../copper-sushi-app.md), [country-cap research](../country-import-export-caps.md), [price attribution](../flow-based-market-coupling.md#price-contribution).

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

## Remaining acceptance criteria

- [ ] Validate loss-aware selected-dual scaling for NorNed, NordLink and Baltic Cable, using documented market loss factors and direction conventions. Lossless matches alone do not authorize these rays.
- [ ] Account for remaining inter-temporal ramping or other coupling terms on the six other new interfaces. The [40-case audit](../virtual-hub-interconnectors.md#adjacent-validation) records which candidate reconstructions fail. Find independently published terms; do not derive them from the spread or widen the €0.02 tolerance.

The next implementation supports per-interval checks for the six lossless candidates using Core terms, Nordic opposite endpoints where applicable, Poland's cap effect and observed adjacent-zone prices. Passing intervals show only the selected bound's normalized component. Failing or missing inputs retain selection and explicit unavailable attribution. Keep adjacent fetching optional and limited to the selected interval/interface.

Implemented: automatic references; guarded Polish cap adapter; normalized physical attribution with α=0 unavailable; schematic mapping of every audited virtual hub; shared ALEGrO geometry with distinct row IDs; synchronized map/dropdown selection; previous/next, minor ticks and exact timestamps. Unit tests cover cap signs, reference direction, scaling, paired hubs, unavailable data and DST intervals. Chrome checks cover Poland’s outline, a physical line, a Romanian PST and ALEGrO selection. App behaviour lives in [the app page](../copper-sushi-app.md#the-cnec-page).

Burn down as changes land; delete this spec once the remaining coverage verifies.
