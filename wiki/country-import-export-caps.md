# Country import and export caps

See [JAO constraint types](jao-constraint-types.md) for the complete classification problem and remaining metadata gaps.

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

Highlight a country only with evidence for the intended aggregate cap. Selecting it should show its signed contribution as above, capacity in MW and the exact delivery interval. Missing duals mean unavailable attribution, never a fallback to the observed spread. Virtual-hub constraints require their own identity and geography. For physical constraints, see [price contribution and scaling](flow-based-market-coupling.md#price-contribution). Implementation work is tracked in the [constraint-selection spec](specs/cnec-constraint-selection.md).
