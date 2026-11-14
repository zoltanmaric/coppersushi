# Polish balancing capacity before the day-ahead auction

This page owns the source contract for comparing upward balancing capacity with the [Polish export cap](polish-allocation-constraints.md). Evidence comes from the [November case queries fetched on 2026-11-12](polish-export-cap-investigation.md#retrieval) and the sources below.

### Procurement

PSE's basic procurement is separate from supplementary procurement. The [Core TSOs' December 2025 explanatory document](literature/core-da-ccm-fourth-amendment-explanatory-document.md#poland), printed page 3, places the basic process at 08:30 on D−1 and supplementary procurement from that afternoon through delivery. Bought capacity should no longer be offered into day-ahead coupling. Procurement volume is contractual capacity in MW, not delivered balancing energy or an operational reserve forecast.

### Sources

Use the public [PSE API](https://api.raporty.pse.pl/api/openapi), with endpoint meanings in its [endpoint map](https://api.raporty.pse.pl/EndpointsMap.pdf). Request each delivery date using `business_date eq 'YYYY-MM-DD'`, follow `nextLink`, and record the query and retrieval time. Pagination must stay on the PSE API host.

| Endpoint | Meaning | Upward fields used |
|---|---|---|
| `wmb` | Required balancing capacity | `fcrg`, `afrrg`, `frrg`, `rrg` |
| `mbp-tp` | Capacity purchased in the basic process | `fcr_g`, `afrr_g`, `mfrrd_g`, `rr_g` |
| `mbu-tu` | Supplementary purchases | Excluded from the pre-day-ahead comparison |
| `zmb` | Procurement demand | Distinct from required capacity; not a replacement for `wmb` |

For each endpoint separately, retain `dtime_utc` and `publication_ts_utc`. Required total is `fcrg + afrrg + frrg + rrg`; purchased total is `fcr_g + afrr_g + mfrrd_g + rr_g`. The PSE portal describes `frrg` as additional frequency restoration above automatic frequency restoration, avoiding double counting. Retain the product components to make the totals auditable. Additional restoration requirement and procured direct manual restoration are not identical product labels; matching aggregate totals does not establish product-level sufficiency.

### Time

The observed records are hourly and `dtime_utc` marks the delivery hour's **end**. Subtract one hour in UTC, then join to the four quarter-hour starts. Repeat capacity levels; do not divide or sum them across quarters. This preserves both repeated autumn hours. Validate the hourly source period rather than assuming every future feed retains this granularity.

For the cap-submission comparison, select only publications strictly before 10:30 Europe/Brussels on D−1. This is the normal SDAC target, not PSE’s verified internal cap-setting deadline. The [SDAC submission procedure (pp. 4 and 8)](https://eepublicdownloads.entsoe.eu/clean-documents/Network%20codes%20documents/NC%20CACM/SDAC%202022/SDAC_NOR_01%20-%20CZCs%20and%20Allocation%20Constraints%20Submission.pdf) allows earlier regional targets. Select the latest eligible version independently for requirements and purchases; never combine components from different versions. Conflicting records with the same delivery hour and publication time are ambiguous. Missing components make the total unavailable, not zero. If only a later revision is retrievable, no eligible earlier value is established.

Store UTC instants. Display delivery and publication timestamps in **Europe/Brussels**, with full date, time and CET/CEST (or explicit UTC offset). This matches the app's `MarketDay` and frontend time convention and avoids the viewer's machine timezone. Publication before the normal submission target does not prove the information was available at the earlier cap-setting deadline.

### Evidence

For delivery **13 November 2026, 19:00–20:00 CET**, the [requirement response](https://api.raporty.pse.pl/api/wmb?%24filter=business_date%20eq%20%272026-11-13%27&%24first=1000) was published **12 November at 07:06 CET** and the [basic-purchase response](https://api.raporty.pse.pl/api/mbp-tp?%24filter=business_date%20eq%20%272026-11-13%27&%24first=1000) at **09:10 CET**. Both sum to **2,347 MW**: 197 containment, 400 automatic restoration, 581 additional/direct manual restoration, and 1,169 replacement. The [investigation](polish-export-cap-investigation.md#comparison) compares adjacent days and later operational plans.

The [analysis](polish-export-cap-investigation.md#analysis) begins on 14 August 2026, the first date with complete comparisons. Earlier missing requirements do not mean zero requirements. Refetching may return revised values; retrieval dates and publication dates are distinct.

### Rationale

The connection is explicit at the metric level. The [Core TSOs’ explanatory document](literature/core-da-ccm-fourth-amendment-explanatory-document.md), printed p. 3, Figure 1, calls its measure “Scarcity of total upward reserve offers in primary procurement (volume procured - volume required).” It cites PSE’s reporting portal. URE separately identifies upward balancing capacity as a purpose of export constraints. This supports testing basic purchases against requirements; the figure does not identify API field names or publish its underlying rows, so exact reproduction of its historical series remains unverified.

Do not conflate this with the [Q4 2025 simulation](literature/pse-allocation-constraints-q4-2025.md): it compares operational reserve levels with and without both cap directions, using intervention thresholds of 1,000 MW upward and 500 MW downward. Those thresholds are not our procurement totals. The [ACER monitoring report’s](literature/acer-electricity-market-integration-monitoring-report.md) claim that pre-day-ahead procurement does not exist conflicts with the documented basic process; it does not validate our field mapping.

### Reconciliation

A six-date arithmetic check found `fcrg + afrrg + frrg + rrg = pk5l-wp.req_pow_res` in **145/145 hours**, with an exact difference of 0 MW. Dates: August 14 (24 hours), October 25 (25), and November 10–13 (24 each), 2026. Purchases matched that margin in 137 hours and fell short in eight. This is a sampled cross-check, not a full-period identity test.

Join `wmb.dtime_utc` and `mbp-tp.dtime_utc` to `pk5l-wp.plan_dtime_utc`, all hour-end timestamps, one-to-one. Query each endpoint by `business_date`. Planning records were fetched on 2026-11-14 and published on the delivery days; requirements/purchases came from the existing research cache, whose original per-file retrieval dates are unknown. These late plans validate the numerical relationship but cannot replace pre-submission evidence. An earlier November 12 evening plan also matched all 24 November 13 requirement sums.

For November 13, 19:00–20:00 CET: `197 + 400 + 581 + 1,169 = 2,347 MW`, equal to the reported margin and purchases. The later plan’s net grid demand is 22,461 MW; 9% gives 2,021.49 MW, a 325.51 MW difference. [PSE’s field definition, sections 3–4](https://www.pse.pl/dane-systemowe/plany-pracy-kse/plan-koordynacyjny-5-letni/wielkosci-podstawowe/opis), uses demand to be covered by domestic plants, including plant own-use and net exchanges, rather than net grid demand alone. The implied denominator is 26,077.78 MW; its components have not been independently reconstructed.

Both reserve sources are PSE feeds. JAO supplies caps, positions and alternative-price evidence. Equality with the published planning margin does not establish which margin/version entered the original cap calculation, physical deliverability or whether alternatives made the cap avoidable.

### Interpretation

Purchased capacity at least equal to the published requirement establishes no aggregate procurement shortfall in the eligible records. It does **not** establish physical deliverability, sufficient reserves at every location, an independently correct requirement, or that exports could safely increase. The original cap calculation and alternatives remain necessary to assess justification. Supplementary purchases and later operating plans must not silently replace the morning comparison.

For fully procured, binding intervals, test the [documented additional mechanisms](literature/core-da-ccm-allocation-constraint-safeguards.md#beyond-procurement): which limitation remained, how many MW did it justify, and did the cap calculation incorporate completed procurement? Obtain the original cap inputs and timestamps, including generation availability adjustments, demand/renewables forecasts and the reserve margin. Aggregate procurement equality alone neither reproduces nor disproves that calculation.
