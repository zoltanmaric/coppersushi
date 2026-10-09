# JAO constraint types

### Classification

The published Core constraints do not reduce to country caps plus lines/transformers. Classify the actual row formulation; distinguish [aggregate country caps](country-import-export-caps.md#country-cap) from virtual-hub bounds, and published domain rows from constraints active in the cleared outcome. A row's country-labelled name is not sufficient evidence for a country cap.

| Category | Source/evidence | Interpretation |
|---|---|---|
| Line / tie-line | Domain `elementType=Line/TieLine` | Physical element, with or without a contingency |
| Transformer | Domain `elementType=Transformer` | Physical transformer |
| Phase-shifting transformer | Domain `elementType=PST` | Physical phase shifter; retain its published subtype |
| Virtual-hub bound | External row with a single ±1 coefficient on a virtual hub | Interconnector/interface flow bound; some hubs represent an AC interface rather than one HVDC cable |
| Aggregate country cap | ±1 coefficient on a country position, or separate allocation feed | Poland's import/export caps in the 2026 inventory; see the [country coverage](country-import-export-caps.md#country-coverage) |
| Coupling equality | Domain `Equality Constraint…`, opposite coefficient vectors, RAM zero | Core position balance / matching virtual-hub positions; not a scarce line capacity |
| LTA constraint | Separate `activeLtaConstraint` feed | Long-term-allocation-domain facet, with its own shadow-price columns |
| Unresolved metadata | Missing type, identifier or formulation evidence | Retain the row and explain what cannot be classified |

The [Core handbook](literature/jao-core-publication-handbook.md) owns publication schemas and timing. The [2026 SDAC overview](literature/sdac-allocation-constraints-2026.md) additionally lists cable ramping and Italy-border line-set constraints. Those are distinct mechanisms and are not all carried by `activeFbConstraints`; downloading that endpoint alone is not downloading every constraint in the coupled market.

### Domain-audit

Direct audit on **2026-10-09**, delivery **2026-09-12 00:00–00:15 CEST**, endpoint `finalComputation`. All **19,904** returned rows were retained; `totalRows` confirms completeness for this interval. Counts below use published types, supplemented only by an unambiguous type for the same EIC in cached domain rows. Names alone do not set the type.

| Classification | Row count |
|---|---:|
| Line | 13,583 |
| Tie-line | 4,594 |
| Transformer | 841 |
| Phase-shifting transformer | 664 |
| Physical element with EIC, subtype unresolved | 128 |
| Asset metadata unresolved: no usable EIC/type/endpoints | 68 |
| Virtual-hub bounds | 22 |
| Coupling-equality rows | 4 |
| **Total** | **19,904** |

These are published rows, not distinct assets or binding constraints. Contingencies, directions and remedial-action variants repeat assets; most rows are not presolved. No aggregate country cap is inside this domain sample; Poland's caps arrive through the separate allocation feed.

The 128 subtype gaps cover 16 EICs. The 68 wider metadata gaps cover nine names, including `Audorf/S - Handewitt HAND BL`, `Y-Ensdorf (-Diefflen - Uchtelfangen) ENSDF S` and `Herrenwijk Transformer T411`. They have grid-element names, but their missing identifiers and types prevent a verified asset classification. They are not evidence for new country caps. They are also not safely discarded.

Reproduce using `https://publicationtool.jao.eu/core/api/data/finalComputation?FromUtc=2026-09-11T22:00:00.000Z&ToUtc=2026-09-11T22:15:00.000Z&Take=100000`. Local ignored evidence: `data/research/country-caps/final-domain-classification-2026-09-12-0000.csv`, with every row ID, name, EIC, category, published type and presolved flag; `classify_collected.py` creates it.

### Active-audit

A complete paced audit on **2026-10-09** covers **2025-10-09 00:00Z–2026-10-09 00:00Z**, in 183 windows of at most two days. All 549 requests succeeded without a rate-limit response. The three feeds return 129,001 active FB rows, 35,040 allocation rows and 9,327 active LTA timestamp rows. FB counts match published `totalRows`; allocation completeness is independently checked against every expected quarter-hour. Allocation and LTA responses omit `totalRows`, so LTA counts describe the successfully retrieved responses, without an independent completeness check. No source row is duplicated across windows.

| Classified row/facet | Count |
|---|---:|
| Physical line | 37,800 |
| Physical tie-line | 34,280 |
| Transformer | 4,569 |
| Phase-shifting transformer | 9,757 |
| Physical element, subtype unresolved | 4,448 |
| Virtual-hub bound | 38,147 |
| Aggregate country-cap limit | 70,080 |
| Positive LTA facet | 88,273 |
| **Classified rows/facets** | **287,354** |

All aggregate limits are Poland's import/export pair, each published in all 35,040 quarter-hours. Their presence does not imply they bind. Every external FB row has a single ±1 virtual-hub coefficient, with no Core-country coefficient. There are 22 distinct external names, including ALEGrO, SwePol, COBRA, NorNed and other interfaces. No aggregate country-cap FB row, coupling-equality row or unresolved external formulation occurs in this active-feed audit. The [domain audit](#domain-audit) does contain equalities, which need not appear among active rows.

The 4,448 unresolved physical rows cover 22 EICs and 25 names. Most are `PST MEE 2` (3,692 rows), but the name alone does not verify its subtype. All retain their IDs and EICs; none is silently forced into a line/transformer category. There are no rows lacking a usable asset identifier in this annual active sample. That does not remove the wider metadata gaps in the full-domain sample.

Local ignored evidence: `data/research/country-caps/annual-constraint-classification.csv` records each classification; `annual-json/` retains every raw response, including null allocation fields and zero LTA facets. `paced_annual_audit.py` requests sequentially at no more than 40 starts/minute, caches responses and backs off on HTTP 429. `verify_annual_audit.py` checks allocation coverage, duplication, FB published totals and classification totals; its results are in `annual-verification.json`. [Arithmetic checks](flow-based-market-coupling.md#attribution-validation) test selected price outcomes separately.

### Limits

This is a complete annual audit of the three named **Core active/allocation feeds**, not every final-domain row or every constraint in SDAC. The active FB feed has rows in 32,207 quarter-hours; the sparse active feeds do not contain a row for every possible constraint in every quarter-hour. Successful window retrieval establishes completeness of what the API returned, not independent proof that the publisher omitted nothing. Non-binding final-domain rows were exhaustively classified only for the single interval above. Other capacity-calculation regions and mechanisms require their own feeds. Asset subtypes remain unresolved where published metadata does not establish them.
