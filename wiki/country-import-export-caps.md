# Country import and export caps

See [Polish allocation constraints](polish-allocation-constraints.md) for the Polish source contract and planned reserve tooltip. See [JAO constraint types](jao-constraint-types.md) for the complete classification problem and remaining metadata gaps.

### Country-cap

A limit on a bidding zone's aggregate [net position](core-day-ahead-capacity-calculation.md#net-position), rather than on one cable. For the map, a country outline represents this aggregate constraint. Country names in an interconnector constraint's label do not establish that meaning.

JAO distinguishes limits on Core net position, included among [external constraints](core-day-ahead-capacity-calculation.md#external-constraint), from limits on the whole Single Day-Ahead Coupling (SDAC) position, supplied as [allocation constraints](core-day-ahead-capacity-calculation.md#allocation-constraint). Its [Core handbook](literature/jao-core-publication-handbook.md) describes both mechanisms; its Netherlands/Belgium examples do not establish their use in 2026. The scope must match when comparing a position with its limit.

### Country-coverage

**As of 2026-10-09, Poland is the only country with an aggregate net-position cap in the published SDAC overview.** The [April 2026 overview, page 3](https://eepublicdownloads.blob.core.windows.net/public-cdn-container/clean-documents/Network%20codes%20documents/NC%20CACM/SDAC%202026/Allocation_Constraints_in_SDAC.pdf) lists Poland alone under net-position allocation constraints. This is Europe-wide source evidence; the app covers these twelve Core bidding zones:

| Country / bidding zone | Aggregate cap in the 2026 overview | Price attribution for the feature |
|---|---|---|
| Austria (AT) | None listed | Not applicable |
| Belgium (BE) | None listed | Not applicable for 2026; historical allocation caps require historical support |
| Czechia (CZ) | None listed | Not applicable |
| Germany–Luxembourg (DE) | None listed | Not applicable; Luxembourg shares this bidding zone |
| France (FR) | None listed | Not applicable |
| Croatia (HR) | None listed | Not applicable |
| Hungary (HU) | None listed | Not applicable |
| Netherlands (NL) | None listed | Not applicable for 2026; TenneT's country cap ended 2023-12-15 |
| Poland (PL) | Import/export net-position caps | Empirically validated `P_PL − PL_ALT`; see [Poland validation](#poland-validation) |
| Romania (RO) | None listed | Not applicable |
| Slovenia (SI) | None listed | Not applicable |
| Slovakia (SK) | None listed | Not applicable |

[TenneT's official phase-out notice](https://www.jao.eu/news/ttn-phase-out-external-constraint-nl-core-day) explicitly removes the Dutch upper/lower Core net-position bound from business day 2023-12-15. An older handbook describing Dutch and Belgian cap formulations must not turn their absence in 2026 into a missing-data problem.

The same 2026 overview lists cable ramping constraints and a combined flow constraint on Italy's borders with France, Austria and Slovenia. Those remain separate mechanisms, even when a country is named. A limit on interconnector flow or a line set is not automatically a cap on that country's aggregate net position. No other country is listed in the overview's net-position category; this conclusion does not claim that all countries have unrestricted trade.

For the stated security rationale and its evidential limits, see the [fourth-amendment explanatory document](literature/core-da-ccm-fourth-amendment-explanatory-document.md#poland). Its proposed Irish provisions do not establish a change to this dated operational inventory.

### Safeguards

Permission to use a cap does not by itself establish its necessity or efficiency in a particular interval. The [Core methodology’s safeguards](literature/core-da-ccm-allocation-constraint-safeguards.md) require analysis of security effectiveness, economic-surplus loss and more efficient alternatives.

The policy disagreement is documented. [CREG’s 2022 study](literature/creg-core-market-coupling-first-100-days.md) calls for discontinuation. The [EU Council recommendation of 10 July 2026, recital 33](https://eur-lex.europa.eu/eli/C/2026/3934/oj/eng/pdf) criticises Polish price decoupling and renewable curtailment linked to allocation constraints. Poland’s [regulator assessment, published 30 December 2025](https://ure.gov.pl/en/communication/news/492,Assessment-of-the-impact-of-the-balancing-market-reform-on-the-application-of-al.html), supports the security rationale while recommending broader reserve participation, better schedules and balancing incentives to reduce activation.

The [Q4 2025 PSE assessment](literature/pse-allocation-constraints-q4-2025.md) contains an actual market rerun and reserve-shortfall calculation. The [oversight evidence](literature/core-da-ccm-allocation-constraint-safeguards.md#oversight) distinguishes published review from independent replication and implementation follow-up.

The [Polish export-cap investigation](polish-export-cap-investigation.md) compares November 2026 interval limits with published reserve requirements, procurement and planning balances.


A defensible challenge asks for the interval’s input calculation, security benefit and assessment of alternatives. A price spread alone does not demonstrate protectionist intent. Nor does compliance with transmission-element capacity margins alone resolve the separate net-position constraint’s efficiency.

### Coverage-validation

The [annual active/allocation audit](jao-constraint-types.md#active-audit) covers 2025-10-09 00:00Z–2026-10-09 00:00Z. All 35,040 allocation quarter-hours publish Polish import/export limits; every Belgian limit is null. All 38,147 external FB rows constrain virtual hubs, with no single ±1 Core-country coefficient. This corroborates the official inventory across the full year rather than extrapolating from a few cached days.

The [arithmetic audit](flow-based-market-coupling.md#attribution-validation) checks all Core zone pairs over six sampled days. Their spreads are reproduced within €0.02/MWh by alpha-normalized physical terms plus Poland's country-cap component. That check cannot exclude a component common to every zone, and does not establish coverage for other SDAC mechanisms or α=0. Future country caps must be established from their published formulation, not a country-labelled cable name.

### Price-effect

With positive net position meaning exports, write the bounds as `−import_limit ≤ NP ≤ export_limit`. Let the non-negative [shadow prices](core-day-ahead-capacity-calculation.md#shadow-price) be `μ_import` and `μ_export`. Their signed component in the country's price is:

```
δ_country = μ_import − μ_export
P_adjusted = P_country − δ_country
```

Thus a selected import cap contributes `+μ_import` to `P_country − P_other`; an export cap contributes `−μ_export`. Reverse the signs for rays showing `P_other − P_country`. A cap on neither compared zone has zero direct term. For a selected Polish cap, its contribution to `P_other − P_PL` is therefore identical for every other country. Differences between those total spreads come from the remaining constraints. These signs follow Article 6 of the [all-TSOs congestion-income methodology amendment proposal, 30 June 2023](https://eepublicdownloads.entsoe.eu/clean-documents/nc-tasks/230630_CACM_CIDm%20Amendment.pdf); this citation establishes the algebra, not the proposal's subsequent legal status.

Use price-normalized duals in €/MWh; distinguish these from an interval's welfare sensitivity in euros per MW. The result attributes the cleared price spread, not the price change after rerunning the auction without the cap. Other constraints can offset it, so an individual contribution may exceed the observed spread. A published limit does not prove it binds; saturation alone does not prove a positive shadow price.

### Public-data

Direct public API inspection on **2026-10-09**, for delivery **2026-09-12 00:00–00:15 CEST** (`2026-09-11T22:00Z`):

| Source | Verified response | What it supports |
|---|---|---|
| Core `allocationConstraint` | PL import 3,999 MW; export 0 MW; BE limits null. Fields are `limitDown_*` and `limitUp_*`, with no shadow price or active flag. | Limits only; null is not zero. |
| Core `activeFbConstraints` | SwePol, COBRA and ALEGrO export rows have shadow prices 3.369034118, 0.194526339 and 0.099567984. Their only non-zero hub coefficients are respectively `PL_SE4_SwePol`, `NL_DK1_COBRA` and `ALBE`, each +1. | Cable/virtual-hub limits, not country caps. All Core-country coefficients are zero. |
| Cross-CCR `DA_PL_AC` | `border_PL_SDAC_NP` and `border_PL_ALT`; UI labels the latter “PL alt”. | Poland's cap-adjusted price, supported by the six-day empirical check below. No explicit dual field. |

Reproduce the first two through `https://publicationtool.jao.eu/core/api/data/{endpoint}` with `FromUtc=2026-09-11T22:00:00.000Z`, `ToUtc=2026-09-11T22:15:00.000Z`, `Take=100000`. The third uses `https://publicationtool.jao.eu/crossCCR/api/data/DA_PL_AC`.

[PSE's publication notice](https://www.pse.pl/redystrybucja-przychodow-wynikajacych-z-sdac) points to JAO Cross-CCR congestion-income data. The linked [Cross-CCR handbook v1.0](https://publicationtool.jao.eu/PublicationHandbook/Cross_CCR_Publication_Tool_Handbook_v1.0.pdf) does not define `PL_ALT`; the usable interpretation below is an empirical inference, not a documented API guarantee.

### Publication-coverage

**Documented start.** [PSE's SDAC congestion-income notice](https://www.pse.pl/web/pse-eng/redistribution-of-congestion-income-from-sdac) dates the optimized cross-CCR settlement process and publication through JAO to **2026-05-06**. Direct `DA_PL_AC` checks on 2026-11-03 match that boundary: May 4–5 return no rows; May 6–7 return 96 each. This supports a coverage cutoff, not an inference that Poland had no constraints before it. The model records the publication start; earlier days do not request this feed. A position safely inside both published bounds establishes that neither cap binds, even without an alternative price. At or near a bound, a missing alternative price leaves the contribution unavailable.

**Observed availability.** Across the initial sample and a stopped follow-up sweep on 2026-11-03, 127 distinct delivery dates from May 6 through November 3 returned data; none was empty. This covers about 70% of the 182-day range, not a random sample or proof of every date. The follow-up checked 112 dates for expected hour buckets, four records per hour, unique IDs and non-null Polish values, with no anomalies; the initial sample exposed the clock-change gap below. A 28-date initial sweep on 2026-11-03 found 96 rows on each of 20 sampled delivery dates from June 1 through November 3, and empty responses for November 4 plus seven sampled dates from September 2025 through May 1, 2026. All returned HTTP 200; no returned `border_PL_ALT` or `border_PL_SDAC_NP` value was null. Queries used local-midnight boundaries in Europe/Warsaw converted to UTC, with `Take=100000000`. An empty response establishes no observations for the query, not a zero cap contribution. November 4 publication being pending is plausible, not confirmed.

**Unresolved schedule.** The [Cross-CCR handbook v1.0, April 2026](https://publicationtool.jao.eu/PublicationHandbook/Cross_CCR_Publication_Tool_Handbook_v1.0.pdf) describes the publication pages but does not define `PL_ALT`, its release deadline, or empty-response semantics. Neither the existing [EUPHEMIA description](literature/euphemia-public-description.md) nor the official sources checked on 2026-11-03 established those details. Core or older CWE publication schedules do not establish this endpoint's schedule. [JAO's October 15 notice](https://www.jao.eu/news/publication-tool-publication-delayed) confirms a congestion-income publication delay for October 16, but does not explain November 4's empty Polish response.

**Clock-change gap.** For delivery 2026-10-25, both the app and the probe use `FromUtc=2026-10-24T22:00:00.000Z` and `ToUtc=2026-10-25T23:00:00.000Z`: 25 hours, or 100 quarter-hours. `DA_PL_AC` returns 96 rows, omitting the hour starting `2026-10-25T00:00:00Z` (02:00 CEST, the first local 02:00). A query for that hour alone also returns no rows; Core `netPos` returns all 100 quarters including that hour. This is an observed gap in the Polish API response, not a 24-hour request bug. Its upstream cause and any displacement of the remaining values remain unverified; no official explanation was found. Nonempty does not establish complete or correctly aligned data.

### Poland-validation

**Use `P_PL − PL_ALT` as Poland's signed cap contribution in €/MWh.** An audit on 2026-10-09 supports this across 576 quarter-hours, using cached Electricity Maps prices and physical-constraint/PTDF tables, plus public JAO cap, net-position, alternative-price and alpha feeds:

| Delivery day | Slack: difference zero | Export bound: difference negative | Import bound: difference positive |
|---|---:|---:|---:|
| 2026-09-10 | 46 | 50 | 0 |
| 2026-09-12 | 49 | 20 | 27 |
| 2026-09-30 | 72 | 22 | 2 |
| 2026-10-02 | 71 | 25 | 0 |
| 2026-10-07 | 42 | 54 | 0 |
| 2026-10-08 | 61 | 35 | 0 |
| **Total** | **341** | **206** | **29** |

No sign or slackness counterexamples. Position-to-limit tolerance was 0.11 MW to allow published rounding; price equality tolerance was €0.01/MWh. An older August 29 price cache was hourly and excluded rather than compared with quarter-hour data.

**June 2–9 consistency check (2026-11-09).** Fresh Core `netPos` and
`allocationConstraint` responses cover all 768 quarter-hours. No position is
within 0.11 MW of a bound: 687 are strictly inside, while 81 fall outside the
published bounds (June 4: 14; June 6: 6; June 7: 46; June 9: 15). Fresh limits
match retained annual responses. The out-of-bounds values leave scope or source
consistency unresolved; this comparison does not establish that Poland's cap
had no price effect. `DA_PL_AC` is also missing for these days. Independently,
[missing alpha](jao-availability.md#historical-gaps) prevents normalized physical
constraint attribution, regardless of the Polish cap's status.

**Publication precision:** `PL_ALT` and the displayed country prices can differ by one cent even without active physical rows. At 2026-09-12 03:15 CEST, JAO publishes `PL_ALT=189.83`, while the displayed other-Core price is 189.82 and Poland is 170.53 €/MWh. The inferred cap term in `P_other−P_PL` is therefore +19.30; the observed spread is +19.29, with a −0.01 remainder. Keep the source values and expose the remainder; do not replace the cap term with the observed spread to force agreement.

An independent magnitude check also passes **all 576 intervals within €0.02/MWh**:

```
PL_ALT − P_SK ≈ −Σ_physical_rows μ × (PTDF_PL − PTDF_SK) / α
```

The same comparison using the actual Polish price passes only the 341 slack intervals. All sampled α values were positive. This supports both the adjusted-price interpretation and its units; it does not establish a general FB/LTA decomposition for every zone or α=0. See [price contribution](flow-based-market-coupling.md#price-contribution).

`DA_PL_AC` truncates timestamps to the hour: 96 rows have only 24 timestamps. Within each hour, **ascending numeric row ID corresponds to :00, :15, :30, :45** in the sampled data. Match `border_PL_SDAC_NP` against Core `netPos.hub_PL` to check this independently: 506 intervals have a unique within-hour position match, all agreeing with ID order. All 576 positions agree after ordering; among the 24 possible fixed quarter-hour permutations, only chronological order fits each of the six days. Repeated positions account for the remaining 70 intervals.

The practical adapter can therefore fetch whole hours/days, require four unique IDs per hour, sort by ID, assign quarter-hours and cross-check against `netPos`. A disagreement should make attribution unavailable. This is an empirically validated workaround for truncated timestamps, not a guarantee that arbitrary future row IDs encode time. Do not infer intervals from network response order alone.

When the import bound is active, the positive difference gives its inferred shadow price; at the export bound, negate the negative difference. This identifies individual duals only when the active side is distinguishable. If both bounds coincide, the difference identifies the net signed component, not two separate duals. These six days establish the Polish price-source calculation; the [country inventory](#country-coverage) establishes which other countries need the aggregate-cap feature.

### Map-contract

Highlight a country only with evidence for the intended aggregate cap. Selecting it should show its signed contribution as above, capacity in MW and the exact delivery interval. Missing duals mean unavailable attribution, never a fallback to the observed spread. Virtual-hub constraints are outside the map’s scope. For physical constraints, see [price contribution and scaling](flow-based-market-coupling.md#price-contribution). Current behavior is described in [the app page](copper-sushi-app.md#the-cnec-page).
