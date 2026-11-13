# Polish export caps: protectionism investigation

**Question:** Are Poland’s binding export caps justified by reserve needs, or do they unnecessarily keep cheaper electricity inside Poland? Protectionism is a hypothesis, not an established motive. Evidence checked on 2026-11-12.

## Findings

The map selects binding effects, so cheaper Polish prices in those intervals are not independent evidence that PSE selectively sets caps when Poland is cheap. The relevant question is whether reserve needs and feasible alternatives justify the cap level.

The 2026-11-13 evening caps are confirmed, but their original reserve calculation has not been recovered. Public PSE plans published after clearing show substantial reserve headroom. Pre-auction procurement matches the published upward-reserve requirements for 19:00–20:00. Neither observation alone proves that the cap was unnecessary.

The [Q4 2025 assessment](literature/pse-allocation-constraints-q4-2025.md) removes both import and export caps. Its renewable-curtailment result concerns downward reserves and cannot justify these export restrictions. The [binding safeguards](literature/core-da-ccm-allocation-constraint-safeguards.md) require assessment of security effectiveness, welfare and alternatives; legal permission does not establish necessity for an individual interval.

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

The reproducible entry point is `python -m scripts.polish_export_caps --start 2026-05-06 --end 2026-11-13`. The local HTML explainer counts active export caps, compares Poland strictly against Germany–Luxembourg, Czechia and Slovakia, and joins morning upward-reserve procurement. The start follows [PSE’s documented JAO publication boundary](country-import-export-caps.md#poland-validation), not the April handbook date.

An active export cap requires the position at the export limit within the shared 0.11 MW publication-rounding tolerance and a positive alternative-price effect exceeding €0.01/MWh. This inherits the [empirical alternative-price adapter](country-import-export-caps.md); it is not an independently published shadow-price flag. Positions safely below the export cap establish inactivity even without an alternative price. Other missing attribution remains unresolved. Neighbour comparisons use strictly `<`, with no tolerance.

For May 6–November 13 inclusive: 18,436 MTUs, 2,599 confirmed active export caps (14.1%), 15,753 classified inactive, 84 unresolved. During active MTUs Poland is cheaper than Germany–Luxembourg in 2,462, Czechia in 2,484, Slovakia in 2,565, and all three in 2,349 (90.4%). All active MTUs have all three comparison prices.

The retrieved `wmb` feed is empty for delivery May 6–August 13 (100 days, 9,600 MTUs). Eligible requirements begin August 14; no retrieved requirement record was excluded by the publication-time filter in this run. The early procurement-difference gap therefore reflects absent requirement records, not zero shortfalls or later revisions. This does not establish that PSE lacked a requirement at the time. Across all observed MTUs, cap publication coverage is 100%: 15,753 are classified nonbinding, 2,599 binding, and 84 unresolved. The nonzero comparison scatter contains 896 nonbinding and 180 binding MTUs; zero comparisons and unavailable pairs are omitted from the plot but retained in population denominators.

The local `cases.html` table lists all 7,760 published-cap MTUs where eligible morning upward purchases meet or exceed the published aggregate requirement, including equality: 3,728 have zero caps and 2,082 have inferred binding effects (overlapping subsets). It excludes 1,076 shortfall MTUs and 9,600 unavailable comparisons. This is a case list for reconciling PSE’s explanation, not a finding that all listed caps were unjustified. The filter and CSV retain individual MTUs, exact cap values and publication timestamps.

The separate zero-export-cap cohort contains 4,621 MTUs (25.1% of all MTUs), independent of market outcome. Poland is strictly cheaper than all three Core neighbours in 1,169 (25.3%). Morning upward procurement is available for every zero-cap MTU: median 1,914 MW, range 1,286–2,403 MW. Of 3,881 with comparable requirements, 3,728 have purchased total at least equal to required total. The cohorts overlap in 1,221 MTUs; another 3 zero-cap MTUs have unresolved binding status. A zero export cap permits net imports, so it need not bind.

PSE primary procurement (`mbp-tp`) is available before clearing for all 2,599 active MTUs: upward capacity median 1,779 MW, range 1,205–2,487 MW. Of 2,262 active MTUs with comparable pre-clearing requirement publications (`wmb`), 2,082 have purchased total at least equal to the required total. This is not a product-by-product or physical-deliverability test. Hourly observations repeat across their four quarters; statistics weight active MTUs. Missing products and publication versions at or after noon Warsaw time on D−1 are excluded, not zero-filled. Generated price-derived files remain local under source terms.

## ACER-monitoring

The [4 November 2026 ACER monitoring report](literature/acer-electricity-market-integration-monitoring-report.md), section 2.4.4, confirms material price-decoupling effects and falling binding frequency. Its paragraph 168 says pre-day-ahead balancing-capacity procurement does not exist, conflicting with URE’s account of the June 2024 reform and observed procurement. This appears to be an outdated explanation; it is not evidence that reserve requirements themselves are fictitious. The section does not supply the missing interval-level justification.

The May 6–November 13 collection covers 192 delivery days with zero failed days. Full local results are in ignored `data/polish-export-caps/`.
