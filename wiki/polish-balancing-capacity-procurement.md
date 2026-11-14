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

In the May 6–November 13 research collection, `wmb` returned no records for May 6–August 13. Comparable requirements start August 14. This is a retrieval gap, not evidence of zero requirements. The API's publication timestamp does not by itself provide a historical as-of archive. Fetching again may return revised values; these findings describe what was retrieved.

### Interpretation

Purchased capacity at least equal to the published requirement establishes no aggregate procurement shortfall in the eligible records. It does **not** establish physical deliverability, sufficient reserves at every location, an independently correct requirement, or that exports could safely increase. The original cap calculation and alternatives remain necessary to assess justification. Supplementary purchases and later operating plans must not silently replace the morning comparison.
