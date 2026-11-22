# Polish export caps: protectionism investigation

**Question:** Are Poland’s binding export caps justified by reserve needs, or do they unnecessarily keep cheaper electricity inside Poland? Protectionism is a hypothesis, not an established motive. Evidence checked on 2026-11-12.

## Findings

The map selects binding effects, so cheaper Polish prices in those intervals are not independent evidence that PSE selectively sets caps when Poland is cheap. The relevant question is whether reserve needs and feasible alternatives justify the cap level.

The 2026-11-13 evening caps are confirmed, but their original reserve calculation has not been recovered. Public PSE plans published after clearing show substantial reserve headroom. Pre-auction procurement matches the published upward-reserve requirements for 19:00–20:00. Neither observation alone proves that the cap was unnecessary.

The [Q4 2025 assessment](literature/pse-allocation-constraints-q4-2025.md) removes both import and export caps. Its renewable-curtailment result concerns downward reserves and cannot justify these export restrictions. The [binding safeguards](literature/core-da-ccm-allocation-constraint-safeguards.md) require assessment of security effectiveness, welfare and alternatives; legal permission does not establish necessity for an individual interval.

## Public-criticism

Public sources checked on 2026-11-16 establish longstanding criticism of price insulation, not an established deliberate-abuse motive or an attributable “open secret” description:

- [Nico Schoutteet, 28 November 2023](https://www.linkedin.com/pulse/allocation-constraints-core-da-fbmc-project-nico-schoutteet-cs7he), section on debate, describes Poland's 2022 price separation as interference with European market coupling and says constraints kept Polish prices below their unconstrained level. He explicitly leaves the validity of security reasons outside scope and notes the price spread subsequently reversed. He quotes [CREG's call to discontinue the constraints](literature/creg-core-market-coupling-first-100-days.md).
- [ACER, 17 February 2025](https://acer.europa.eu/news/acer-suggests-better-reflecting-benefits-europes-internal-electricity-market-polands-national-resource-adequacy-assessment), findings, says constraints sometimes prevent Polish exports when neighbours need them and stop Polish prices reflecting regional shortages. Its example is 12 December 2024, 16:00–17:00, with Poland at €165/MWh.
- [Mateusz Gibała, BiznesAlert, 18 February 2025](https://biznesalert.pl/eksport-polskiej-energii-moze-obnizyc-ceny-w-regionie/), credited to Montel News, reports that criticism and compares Poland's €165/MWh with Germany's €936/MWh. This establishes press coverage of the effects, not independent proof of intent.

## November-13

All delivery times below are **CET**, interval starts. PSE’s `dtime` is the interval **end**; use `period` to avoid shifting the comparison by 15 or 60 minutes. JAO’s allocation-constraint timestamps are UTC interval starts.

| Delivery interval | JAO export cap, MW | PSE afternoon reserve above demand, MW |
|---|---:|---:|
| 19:00–19:15 | 0 | 4,643 |
| 19:15–19:30 | 0 | 4,589 |
| 19:30–19:45 | 84 | 4,528 |
| 19:45–20:00 | 311 | 4,419 |

Sources: [JAO allocation constraints](https://publicationtool.jao.eu/core/api/data/allocationConstraint?FromUtc=2026-11-12T23%3A00%3A00.000Z&ToUtc=2026-11-13T23%3A00%3A00.000Z&Take=100000000) and [PSE daily plan](https://api.raporty.pse.pl/api/pdgopkd?%24filter=business_date%20eq%20%272026-11-13%27&%24first=1000), field `rez_over_demand`, published **2026-11-12 15:43 CET**. Both returned 96 intervals without pagination. This is a post-clearing plan, not the morning input used to set the cap.

PSE’s [hourly planning balance](https://api.raporty.pse.pl/api/pk5l-wp?%24filter=business_date%20eq%20%272026-11-13%27&%24first=1000), published **2026-11-12 20:02 CET**, reports for 19:00–20:00:

- Capacity surplus available to the operator: **4,164 MW**.
- Required reserve: **2,347 MW**.
- Surplus above required reserve: **1,817 MW**.

These are PSE’s own fields, not an estimate obtained by applying 9% to a different demand series. The [field definitions](https://www.pse.pl/dane-systemowe/plany-pracy-kse/plan-koordynacyjny-5-letni/wielkosci-podstawowe/opis) account for planned exchanges, network unavailability and generator startup characteristics. Additional feasible exports cannot simply be equated to this surplus: the reserve requirement and dispatch can change with exports.

## Procurement

The [procurement source page](polish-balancing-capacity-procurement.md) owns endpoint definitions, eligible publication versions and time alignment. The comparison uses basic purchases and published requirements, not supplementary purchases or later operational forecasts.

For **2026-11-13 19:00–20:00 CET**, the [requirements](https://api.raporty.pse.pl/api/wmb?%24filter=business_date%20eq%20%272026-11-13%27&%24first=1000) published at **07:06 CET on November 12** and [primary procurement](https://api.raporty.pse.pl/api/mbp-tp?%24filter=business_date%20eq%20%272026-11-13%27&%24first=1000) published at **09:10 CET** match:

| Upward reserve product | Requirement, MW | Procured, MW |
|---|---:|---:|
| Frequency containment | 197 | 197 |
| Automatic frequency restoration | 400 | 400 |
| Additional frequency restoration / procured direct manual restoration | 581 | 581 |
| Replacement | 1,169 | 1,169 |
| **Total** | **2,347** | **2,347** |

The portal defines the additional restoration requirement as above the automatic requirement; these are not overlapping totals. The procurement-demand feed `zmb` matches `wmb` for this hour. This establishes no observed upward procurement-volume shortfall in these reports. The [December 2025 explanatory document, printed p. 3](https://www.acer.europa.eu/sites/default/files/documents/Media/News/Documents/Explanatory-document-DA-CCM-CCR-2026.pdf), explicitly says bought capacity should no longer be offered in day-ahead coupling. Its generic explanation that the primary auction cannot buy enough upward reserve therefore does not match the published volumes for this hour. Extra requirements, forecast revisions, location or delivery constraints remain possible explanations, not verified facts.

## Comparison

The preceding three days provide a useful countercheck. For **19:00–20:00 CET**, all four export caps were zero, and upward procurement matched the published requirements. However, their later daily-plan reserve figures were much lower than November 13:

| Delivery date | Upward requirement and procurement, MW | Afternoon-plan reserve range, MW |
|---|---:|---:|
| 2026-11-10 | 2,114 | 1,122–1,174 |
| 2026-11-11 | 1,811 | 1,865–1,992 |
| 2026-11-12 | 2,115 | 1,123–1,231 |
| 2026-11-13 | 2,347 | 4,419–4,643 |

Procurement is a contractual volume; the later plan is an operational forecast. They must not be treated as identical measurements. The low November 10/12 planned margins are consistent with reserve pressure, even after procurement, while November 13 needs a different reconciliation. This comparison checks cap values, not their price impact: foreign prices and cap shadow prices have not been matched for November 10–12.

## Retrieval

The November 10–13 case evidence was fetched on **2026-11-12**. Source publication times are stated separately above. Fetching the same queries again may return revised values; the findings describe the responses observed on that date.

For PSE, query `https://api.raporty.pse.pl/api/{endpoint}` with `$filter=business_date eq 'YYYY-MM-DD'` and follow pagination. The cases use `wmb`, `mbp-tp`, `zmb`, `pdgopkd`, `pdgobpkd` and `pk5l-wp`. For JAO `allocationConstraint`, query the delivery day's local-midnight boundaries converted to UTC, as in the November 13 source link above. Raw API dumps are not part of the wiki.

## Missing-evidence

The export formula is available capacity minus unavailable capacity and adjustments, plus non-central generation, minus demand and upward reserve. See [country caps](country-import-export-caps.md). The exact morning values and their publication version are missing; later plans are not substitutes.

The [official API schema](https://api.raporty.pse.pl/api/openapi) exposes publication timestamps but no documented as-of parameter for `pk5l-wp`, `pdgopkd` or `pdgobpkd`. Filtering the November 13 planning balance to publications before November 12 noon returned no rows. This establishes failure to retrieve that version, not proof that no archive exists elsewhere.

Remaining checks: recover the morning export calculation and any revisions; reconcile purchased reserves with the later operational plan; match preceding days to prices and binding status; distinguish necessary reserves from the efficiency of procuring them domestically. The quarterly ex-post assessment for Q4 2026 cannot yet cover November 13 as of November 12.

## Analysis

**Scope: 14 August–13 November 2026 inclusive, 92 delivery days and 8,836 quarter-hour MTUs.** All analysis populations start on August 14. The earlier missing requirements form one continuous period (May 6–August 13); excluding it gives complete caps, reserve comparisons, neighbour prices and inferred binding classifications in this collection. Future extensions must check completeness rather than assume it.

Run `python -m scripts.polish_export_caps --start 2026-08-14 --end 2026-11-13`. Both reserve publications must be strictly before 10:30 Europe/Brussels on D−1, the normal submission target. This is not proof of availability at PSE’s actual internal cap-setting time. See the [source and time contract](polish-balancing-capacity-procurement.md#time).

| Measure | Numerator / denominator | Share |
|---|---:|---:|
| Published export cap, zero or positive | 8,836 / 8,836 | 100% |
| Aggregate procurement shortfall | 1,076 / 8,836 | 12.2% |
| No aggregate procurement shortfall | 7,760 / 8,836 | 87.8% |
| Binding export cap | 2,262 / 8,836 | 25.6% |
| Procurement shortfall among binding MTUs | 180 / 2,262 | 8.0% |
| No procurement shortfall among binding MTUs | 2,082 / 2,262 | 92.0% |
| Binding among no-shortfall MTUs | 2,082 / 7,760 | 26.8% |

### Extension

The cap/procurement graphic extends through **17 November 2026 inclusive: 96 delivery days, 9,220 quarter-hour MTUs**, with no missing or duplicate intervals. **2,359 MTUs bind (25.6%)**; among those, **197 have an aggregate procurement shortfall (8.4%)** and **2,162 do not (91.6%)**. There are 1,136 shortfall MTUs in the full population. This extension does not update the earlier cap-size buckets or imbalance-price episode analysis.

Retrieved on **17 November 2026** from immutable prepared Critical Elements snapshots because direct JAO requests timed out. Immutable daily metadata: [November 14](https://coppersushi.121gigawatts.org/data/cnec/v3/2026-11-14/8c874787825dc69645deb3e9/metadata.json), [15](https://coppersushi.121gigawatts.org/data/cnec/v3/2026-11-15/1156efb6a67d1c5d060f2dd0/metadata.json), [16](https://coppersushi.121gigawatts.org/data/cnec/v3/2026-11-16/a80dee859a393c71f5b862c8/metadata.json), [17](https://coppersushi.121gigawatts.org/data/cnec/v3/2026-11-17/21257b63345cc5173ed26735/metadata.json). Each added day has all 96 intervals, complete attribution and eligible purchase/requirement observations. The snapshots retain publication timestamps and four product contributions; all totals reconcile and both publications precede the existing 10:30 D−1 cutoff. Applying the same >€0.01/MWh dual threshold preserves the research binding definition. A full overlapping November 13 check matches the original series in all 96 quarters for binding status, purchased/required MW and both publication timestamps. These are retained source-derived publications, not fresh direct JAO responses or independent measurements. The original August 14–November 13 observations remain unchanged.

The added days contain respectively 4, 18, 61 and 14 binding MTUs; 0, 9, 4 and 4 also have procurement shortfalls. Local reproducibility inputs, retrieval URLs/hashes, scripts and the combined comparison are under ignored `data/polish-cap-graphic/`. Procurement sufficiency remains distinct from operational reserve adequacy.

### Reporting-threshold

Recounted the episode explainer's `intervals.csv` on 2026-11-16: 2,262/8,836 inferred binding export intervals (25.6%). Split by calendar quarter, the observed Q3 subset (14 August–30 September) has 822/4,608 (17.84%), and the Q4 subset (1 October–13 November) has 1,440/4,228 (34.06%). Even counting every unobserved quarter-hour as nonbinding, these represent 9.31% of full Q3 and 16.30% of full Q4 duration (2,208 and 2,209 hours respectively, including the autumn clock change). Directly checked the application's cap shadow-price definition (`country_caps`: export shadow price = `PL_ALT − P_PL`) against all classified intervals: Q3 822/822 positive, range €0.10–193.37/MWh; Q4 1,440/1,440 positive, range €0.04–245.35/MWh. No binding-classification mismatches. Thus the tracked cap dual is already part of the binding criterion, not an outstanding independent condition. This checks the same published-price-derived dual used by the application, not a second independent shadow-price feed. The [Article 7 reporting threshold](literature/core-da-ccm-allocation-constraint-safeguards.md#transparency) is exceeded by a wide margin in each quarter on that established attribution; a sample spanning quarters is not itself a calendar-quarter compliance statistic.

### Cap-levels

All shares below use the same 8,836-MTU complete-data population. Exact zero is separate; positive intervals have exclusive lower and inclusive upper bounds.

| Export limit | MTUs | Share of all MTUs | Binding MTUs | Binding within bucket |
|---|---:|---:|---:|---:|
| 0 MW | 3,881 | 43.9% | 1,112 | 28.7% |
| >0–500 MW | 608 | 6.9% | 408 | 67.1% |
| >500–1,000 MW | 479 | 5.4% | 256 | 53.4% |
| >1,000–2,000 MW | 837 | 9.5% | 300 | 35.8% |
| >2,000–4,000 MW | 1,460 | 16.5% | 182 | 12.5% |
| >4,000 MW | 1,571 | 17.8% | 4 | 0.3% |

The positive-cap median is 2,645 MW and maximum 12,307 MW. Finer low-cap bands distinguish small export allowances; wider upper bands keep the distribution readable. These are descriptive thresholds, not operational-security categories. Cap size does not establish whether it binds. Rounded shares may not sum to exactly 100%.

Zero caps occur in 3,881 MTUs and positive caps in 4,955. Binding effects are inferred in 2,262 MTUs; 6,574 are nonbinding and none unresolved. Among binding MTUs, Poland is strictly cheaper than Germany–Luxembourg in 2,142, Czechia in 2,175, Slovakia in 2,228, and all three in 2,049. These conditional price comparisons do not establish selective cap setting or motive.

Binding requires the position at the export limit within the shared 0.11 MW publication-rounding tolerance and an alternative-price effect exceeding €0.01/MWh. This uses the [empirical adapter](country-import-export-caps.md#poland-validation), not an independently published binding flag. Neighbour price comparisons use strictly `<`, with no tolerance.

The local `cases.html` table contains all 7,760 no-shortfall MTUs, including equality. It retains exact cap values, publication timestamps and filters. A matching purchase total is a reconciliation case, not proof the cap was unjustified. The [reserve cross-check](polish-balancing-capacity-procurement.md#reconciliation) tests whether the product sum equals PSE’s separately reported required margin. Generated price-derived results remain local under source terms.

## ACER-monitoring

The [4 November 2026 ACER monitoring report](literature/acer-electricity-market-integration-monitoring-report.md), section 2.4.4, confirms material price-decoupling effects and falling binding frequency. Its paragraph 168 says pre-day-ahead balancing-capacity procurement does not exist, conflicting with URE’s account of the June 2024 reform and observed procurement. This appears to be an outdated explanation; it is not evidence that reserve requirements themselves are fictitious. The section does not supply the missing interval-level justification.

The August 14–November 13 analysis covers 92 delivery days with zero failed days. Full local results are in ignored `data/polish-export-caps/`.

## Imbalance-prices

[Episode explainer](https://coppersushi.121gigawatts.org/assets/previews/polish-balancing-episodes/d8b35dcf9360/index.html) · [matched quarter-hour CSV](https://coppersushi.121gigawatts.org/assets/previews/polish-balancing-episodes/d8b35dcf9360/intervals.csv). Scope: 2026-08-14–2026-11-13; all 8,836 quarters match PSE prices, contracting balance, activation and existing JAO cap data. PSE `energy-prices` and `eb-rozl` fetched 2026-11-16, with URLs and retrieval times cached. Original cap-cache retrieval dates remain incompletely documented. PSE interval-end UTC timestamps are shifted back 15 minutes; October 25 has 100 quarters. Latest returned publication wins for duplicate intervals.

The episode screen uses CEN minus day-ahead price by default, with an absolute-CEN alternative. Surplus requires a price measure below the negative threshold and SK > 0; shortage requires a price measure above the positive threshold and SK < 0. Consecutive qualifying quarters form an episode; any intervening non-qualifying quarter ends it. Prices use a fixed 4.4113 PLN/€ (ECB, 2026-11-13), not historical daily FX settlement. Thresholds are illustrative, not official scarcity criteria.

| Gap from day-ahead | Direction | Episodes | Hours | Net contracting mismatch, GWh | Quarters overlapping binding export cap |
|---|---|---:|---:|---:|---:|
| Below −€250/MWh | Surplus | 55 | 44 | 28.16 | 7/176 |
| Above €250/MWh | Shortage | 62 | 35.25 | 43.81 | 12/141 |
| Below −€500/MWh | Surplus | 31 | 26.75 | 20.88 | 5/107 |
| Above €500/MWh | Shortage | 20 | 8.25 | 13.30 | 2/33 |

At the €250 gap, event energy is 12.4% of all surplus SK energy and 4.8% of all shortage SK energy in the window. Downward supplier activation during surplus episodes totals approximately 24.0 GWh; upward activation during shortage episodes totals 55.6 GWh. These activation totals add the separately published outside-platform and aFRR components; they are not SK, gross participant imbalances, settlement costs, or measurements of reserve exhaustion. Domestic aFRR delivery can serve foreign demand. See the [source contract](polish-balancing-capacity-procurement.md#episodes).

The result changes with the definition of extreme. Under absolute CEN thresholds of ±€250/MWh, surplus has 39 episodes, 34.25 hours and 24.33 GWh, versus shortage's 308 episodes, 383.75 hours and 267.65 GWh. A high positive price can also reflect an already-high day-ahead price; it is not necessarily an exceptional balancing premium. At the far tails, surplus can dominate duration and energy. Peak price magnitude alone cannot settle which direction is the larger problem.

A concrete overlap is 2026-10-16 14:15–15:00 CEST: three consecutive surplus quarters with a binding day-ahead export cap, 691.515 MWh of SK surplus, and 813.1 MWh of downward supplier activation. CEN is approximately −€545.55, −€563.83 and −€564.27/MWh; cap/scheduled exports are 1,355, 1,006 and 639 MW. These are candidate intervals for a counterfactual test, not proof the earlier cap caused the later surplus. The deepest negative-price episode, on August 15, has no inferred binding export cap.

The export-cap comparison uses **day-ahead scheduled net position**, not real-time measured flows. Binding is inferred using the investigation's position tolerance and alternative-price predicate. Overlap does not establish intraday feasibility, the counterfactual export response, or the necessity or harm of a cap. Neither episode energy nor quarter-hour activation reveals instantaneous reserve-power peaks.

### November-20

For delivery 20 November 2026, subtracting the [network contribution](flow-based-market-coupling.md#attribution-validation) from each neighbor’s cleared price minus Poland’s price gives the implied export-cap shadow price. The German, Czech and Slovak estimates agree within €0.009/MWh across 96 quarters. Each of the 24 quarters at the export limit has a positive estimate (€1.26–105.02/MWh). The other 72 clear below the limit. Nine of the 24 have an upward procurement shortfall, of 6, 18 or 45 MW. This reconstruction uses auction spreads independently of PL_ALT. [JAO spreads](https://publicationtool.jao.eu/core/api/data/priceSpread?FromUtc=2026-11-19T23:00Z&ToUtc=2026-11-20T23:00Z&Take=100000) · [JAO shadow prices](https://publicationtool.jao.eu/core/api/data/shadowPrices?FromUtc=2026-11-19T23:00Z&ToUtc=2026-11-20T23:00Z&Take=100000) · [PSE reserve sources](polish-balancing-capacity-procurement.md#procurement)
