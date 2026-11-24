# Polish balancing capacity before the day-ahead auction

This page owns the source contract for comparing upward balancing capacity with the [Polish export cap](polish-allocation-constraints.md). Evidence comes from the [November case queries fetched on 2026-11-12](polish-export-cap-investigation.md#retrieval) and the sources below. The [CNEC pipeline](../coppersushi/pipelines/cnec/README.md) prepares these observations for the export-cap tooltip.

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

### Downward

The [requirements](https://api.raporty.pse.pl/api/wmb?%24filter=business_date%20eq%20%272026-08-14%27) and [basic purchases](https://api.raporty.pse.pl/api/mbp-tp?%24filter=business_date%20eq%20%272026-08-14%27) also separate downward capacity. For 14 August–19 November 2026 all 2,353 delivery hours had 197 MW containment, 400 MW automatic restoration, 90 MW additional restoration and zero replacement requirement. Downward replacement purchases were null throughout. The import comparison sums the three required product families: `fcrd + afrrd + frrd` against `fcr_d + afrr_d + mfrrd_d`. It makes no assumption about unreported replacement purchases. Of 542 confirmed import-cap quarters, 119 fell below 687 MW and 423 met it.

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

A six-date arithmetic check found `fcrg + afrrg + frrg + rrg = pk5l-wp.req_pow_res` in **145/145 hours**, with an exact difference of 0 MW. Dates: August 14 (24 hours), October 25 (25), and November 10–13 (24 each), 2026. Purchases matched that margin in 137 hours and fell short in eight. Shortfalls occurred on October 25 (two hours), November 11 (three), November 12 (two) and November 13 (one). This is a sampled cross-check, not a full-period identity test.

Join `wmb.dtime_utc` and `mbp-tp.dtime_utc` to `pk5l-wp.plan_dtime_utc`, all hour-end timestamps, one-to-one. Query each endpoint by `business_date`. Planning records were fetched on 2026-11-14 and published on the delivery days; requirements/purchases came from the existing research cache, whose original per-file retrieval dates are unknown. These late plans validate the numerical relationship but cannot replace pre-submission evidence. An earlier November 12 evening plan also matched all 24 November 13 requirement sums.

For November 13, 19:00–20:00 CET: `197 + 400 + 581 + 1,169 = 2,347 MW`, equal to the reported margin and purchases. The later plan’s net grid demand is 22,461 MW; 9% gives 2,021.49 MW, a 325.51 MW difference. [PSE’s field definition, sections 3–4](https://www.pse.pl/dane-systemowe/plany-pracy-kse/plan-koordynacyjny-5-letni/wielkosci-podstawowe/opis), uses demand to be covered by domestic plants, including plant own-use and net exchanges, rather than net grid demand alone. The implied denominator is 26,077.78 MW; its components have not been independently reconstructed.

Both reserve sources are PSE feeds. JAO supplies caps, positions and alternative-price evidence. Equality with the published planning margin does not establish which margin/version entered the original cap calculation, physical deliverability or whether alternatives made the cap avoidable.

### Interpretation

Purchased capacity at least equal to the published requirement establishes no aggregate procurement shortfall in the eligible records. It does **not** establish physical deliverability, sufficient reserves at every location, an independently correct requirement, or that exports could safely increase. The original cap calculation and alternatives remain necessary to assess justification. Supplementary purchases and later operating plans must not silently replace the morning comparison.

For fully procured, binding intervals, test the [documented additional mechanisms](literature/core-da-ccm-allocation-constraint-safeguards.md#beyond-procurement): which limitation remained, how many MW did it justify, and did the cap calculation incorporate completed procurement? Obtain the original cap inputs and timestamps, including generation availability adjustments, demand/renewables forecasts and the reserve margin. Aggregate procurement equality alone neither reproduces nor disproves that calculation.

### Activation

PSE publishes settlement activation in `eb-rozl` and balancing demand covered in the Polish balancing area in `zeb-rozl`. The [endpoint map](https://api.raporty.pse.pl/EndpointsMap.pdf), pp. 14–15, lists their fields. [Balancing-rule amendment 3/2025, p. 12](https://www.pse.pl/documents/20182/6226308997/Zmiany_3_2025_WDB.pdf/eb1baec1-4379-4697-a113-0e5c3455d4e5) defines ZEBpp as demand covered outside European balancing platforms and PZEBaFRR as demand covered through the aFRR platform, in MWh. The map’s older reference to the RR platform alone should not define the current scope.

Fetched both endpoints for `business_date eq '2026-11-13'` on 2026-11-16: 96 unique quarter-hour records each, no continuation link. `dtime_utc` marks interval end; `period` confirms the interval. Activation fields are `eb_d_pp`, `eb_w_pp`, `eb_afrrg`, `eb_afrrd`; demand fields are `zebpp`, `pzeb_afrrg_cost`, `pzeb_afrrd_cost`. The two aFRR series differ: domestic provider activation must not be treated as Poland’s own covered demand.

At 19:00–19:15 CET, upward aFRR covered demand is 15.951 MWh (63.804 MW averaged over the quarter), while the activation feed reports 20.595 MWh (82.380 MW). The [morning procurement](#evidence) includes 400 MW upward aFRR for that hour. This sample establishes joinability and distinct series, not the frequency of reserve exceedance. Settlement publications were 2026-11-14 at 13:01 UTC.

For comparison with purchased MW, divide quarter-hour MWh by 0.25 hours and repeat the hourly procurement capacity over its four quarters. Keep directions separate; `zebpp` is signed/net and cannot recover gross opposing activations. Compare matched products: the existing total includes FCR, which this activation feed does not identify separately. Average MW cannot reveal brief within-quarter peaks. Morning procurement and final capacity after supplementary procurement answer different questions. Do not label the result a complete PSE reserve-exhaustion test without reconciling product scope, cross-border exchanges and later purchases.

PSE also directly asserts that large imbalances can exceed available domestic reserves in its [July 2026 commercial-balancing report announcement](https://www.pse.pl/-/bilansowanie-handlowe-kse-w-lipcu-2026), published 2026-08-31. That operational claim is distinct from exceeding the morning procurement volume.

### Resolution

A quarter-hour average below purchased capacity cannot rule out a brief exceedance. Conversely, an average above a constant matched capacity implies an exceedance somewhere in that interval; it does not identify its timing or duration. Requested power, delivered power and the capacity available at dispatch are distinct quantities.

Public-source review on 2026-11-16 found these publication contracts, but did not obtain a Polish seconds-resolution dispatch series:

- ENTSO-E [aggregated balancing energy bids, GL EB 12.3.E](https://transparencyplatform.zendesk.com/hc/en-us/articles/12826644599572-Aggregated-Balancing-Energy-Bids-GL-EB-12-3-E), updated 2026-06-12: activated volumes are **average MW per imbalance settlement period**. MW units alone do not establish instantaneous power. Central and local aFRR selections are reported separately; FCR is excluded.
- ENTSO-E [aFRR exchanged volumes](https://transparencyplatform.zendesk.com/hc/en-us/articles/12826567169684-Netted-and-Exchanged-Volumes-IN-IFs-3-10-aFRR-IFs-3-16-mFRR-IFs-3-17), updated 2025-08-27: operational-cycle resolution, initially four seconds. The [CSV schema](https://transparencyplatform.zendesk.com/hc/en-us/articles/47909673071505-NettedAndExchangedVolumesAfrr-IFs-aFRR3-16-r3-1), dated 2026-06-19, has cycle timestamps, PT1S/PT4S resolution, area, direction and MWh quantity. These are cross-border exchanges from the activation optimisation function, not total domestic activation or total Polish demand. Converting cycle energy to cycle-average MW preserves much more timing detail than quarter-hour settlement, but does not fill the missing domestic dispatch series. Polish coverage was not verified.
- ENTSO-E [current balancing state, GL EB 12.3.A](https://transparencyplatform.zendesk.com/hc/en-us/articles/12824861339924-Current-Balancing-State-GL-EB-12-3-A), updated 2025-08-26: one-minute mean open-loop area control error in MW. This describes imbalance, not product-specific reserve dispatch; Polish coverage was not verified.

The inspected [PSE API schema](https://api.raporty.pse.pl/api/openapi) did not identify a seconds-resolution aFRR demand, activation-setpoint or measured-delivery endpoint. This is a search limit, not proof that PSE publishes none. Grid frequency in Hz is not itself a Polish reserve-dispatch measurement.

### Incentives

BRPs bear financial responsibility for their portfolio imbalances: [Regulation (EU) 2019/943, Article 5](https://eur-lex.europa.eu/eli/reg/2019/943/oj), and PSE's [2026-08-31 announcement](https://www.pse.pl/-/bilansowanie-handlowe-kse-w-lipcu-2026) explicitly confirm this. Consumer pass-through does not remove the BRP's settlement liability. The [podcast's two cost channels](literature/pse-stepien-commercial-balancing-podcast.md#behaviour) distinguish operator costs recovered through tariffs from costs borne by BRPs and subsequently passed to customers. It supplies neither the tariff reconciliation nor customer contracts needed to establish who bears an additional euro of imbalance cost; guaranteed reimbursement and weak marginal incentives cannot be inferred from it.

PSE's [July 2026 commercial-balancing report](literature/pse-commercial-balancing-july-2026.md) attributes persistent imbalances to insufficient corrective trading and proposes stronger imbalance-pricing incentives. Its examples distinguish surplus/downward pressure from shortage/upward pressure; its savings estimates are counterfactual rather than audited losses. The digest owns the page-specific evidence. A high realised price alone cannot establish adequate expected incentives before delivery.

The [full March 2026 Stępień interview](literature/pse-stepien-commercial-balancing-podcast.md) adds an attributed organisational explanation for slow adaptation and describes a predictable alpha pricing incentive. It discusses consumer cost pass-through but does not establish that this causes participants to remain unbalanced. The video labels its expert opinions educational rather than the official company position.

This strengthens the documented operational rationale for reserves. It does not quantify the additional reserve requirement or establish the necessity or size of a specific day-ahead export cap. The [methodology safeguards](literature/core-da-ccm-allocation-constraint-safeguards.md) still require security effectiveness and comparison with alternatives; completed reserve procurement must not be counted twice as a separate reason to withhold export capability.

### Prices

PSE publishes the imbalance settlement price (CEN, cena energii niezbilansowania) in PLN/MWh as `price-cost.cen_cost`. The [endpoint map](https://api.raporty.pse.pl/EndpointsMap.pdf), pp. 1–2, separates settlement data (`price-cost`) from forecasts (`price-fcst.cen_fcst`). CEN must not be substituted with marginal balancing-offer price `ckoeb_cost` or average balancing-energy price `ceb_sr_cost`.

A public API query for `business_date eq '2026-11-13'`, `$first=2`, fetched 2026-11-16, returned CEN 433.39 PLN/MWh for 00:00–00:15 CET and 392.51 for 00:15–00:30. Both were published 2026-11-14 at 13:01:47.666 UTC. These records establish quarter-hour settlement-price availability; the two-row sample does not establish full historical coverage. Follow `nextLink` for complete days and preserve publication timestamps for revisions.

### Episodes

The [episode analysis](polish-export-cap-investigation.md#imbalance-prices) uses PSE `energy-prices.sk_cost` (aggregate contracting balance, SK, MWh) to distinguish long/surplus from short/shortage. It must not substitute `balance` or `price-cost.imb_energy`: those are net settled imbalance energy and can have the opposite sign. For example, 2026-08-15 11:45–12:00 CEST has SK +194.142 MWh but net settled imbalance energy −245.914 MWh. The [endpoint map](https://api.raporty.pse.pl/EndpointsMap.pdf), pp. 2, 14 and 21, maps contracting state from SK and defines the separate energy fields; its MW fields are simply MWh × 4, not high-resolution measurements.

[WDB amendment 3/2025](https://www.pse.pl/documents/20182/6226308997/Zmiany_3_2025_WDB.pdf/eb1baec1-4379-4697-a113-0e5c3455d4e5), pp. 4 and 15, defines EBpp as activation outside European platforms and separates it from platform aFRR energy (section 14.4.1). This supports adding the corresponding same-direction supplier-energy components while keeping them distinct from Poland's covered demand. Across the 92-day fetch, delivered fields are nonnegative and withdrawn fields nonpositive; displayed downward magnitudes use the latter's absolute values.
