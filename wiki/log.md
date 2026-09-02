# Wiki Log

Append-only chronology of wiki operations (ingests, queries, lints).
Entry format: `## [YYYY-MM-DD] <operation> | <title>`

## [2026-08-19] setup | Wiki instantiated at repo top level

## [2026-08-19] ingest | The Copper Plate Must Die + Copper Sushi blog posts
Both posts fetched from 121gigawatts.org (text via RSS, figures reviewed in browser) into raw/. Created copper-plate-problem, copper-sushi-app, codebase-v1 (session knowledge: architecture, 2026 modernization, milkshake lineage).

## [2026-08-19] lint | Goldfish review of the Sushi 2 spec → major revision
Three fresh reviewers. Kept: HVDC links pinned to measured values (lpf can't solve them) → FR–DE is the falsifiable AC comparison, ES–FR the case study; multi-day validation (boring + eventful); QP → proportional rescaling; 15-min resolution; irradiance layer deferred (satellite products likely eclipse-blind); entsoe-py #480 and no-prebuilt-nc schedule facts. Dropped: the pre-registration page entirely (tolerances/pass-fail = rigid frame on an open exploration); validation is now exploratory with honestly reported calibrations. Meta-lesson → spec/goldfish skills amended for iterative depth.

## [2026-08-19] ingest | Copper Sushi 2 spec (grilled from the vault note)
Grill settled: in-place rewrite on main (v1 tagged + GitHub-released), pipeline first / viz deferred, NUTS3 load prior kept, hosting out of spec, target days (Sep 11 absolute). Created sushi-2 (architecture), sushi-2-pre-registration (DRAFT — tolerances await sign-off), specs/sushi-2 (burn-down).

## [2026-08-19] ingest | Agent workflow design (grill/spec/goldfish)
Distilled the design conversation behind AGENTS.md rules 7–8 and the three new skills into agent-workflow-design. Sources (linked, not copied — copyrighted): Rensin's Elephant-Goldfish, Hirschfeld's lifetime layering, Cherny's YC talk (Jul 2026), Musk's five-step algorithm. Includes rejected alternatives per the design's own doctrine.

## [2026-08-19] decision | Specs may live in wiki/specs/
Large specs may burn down in committed wiki/specs/ (indexed as working memory, never as settled knowledge); gitignored specs/ stays the default. Skill + agent-workflow-design amended.

## [2026-08-19] decision | Lightweight architecture-review pilot begins
Added an implemented-only Mermaid dataflow to the Sushi 2 architecture page, an Architecture delta PR convention, and a finite direct-I/O boundary for source/sink adapters. Planned topology stays prose until it lands; automatic extraction and graph CI await evidence from three real PRs.

## [2026-09-01] ingest | Timezone handling: explicit-timezones rationale and the PyPSA boundary
PyPSA rejects tz-aware snapshots at every version — numpy datetime64 → xarray → netCDF/CF, none carry a zone — so snapshots are naive meaning UTC, converted only in pipeline/flows.py. Performance myth debunked (the zone is dtype metadata; tz_convert is O(1)); Arrow/Polars unsupported upstream (coerced away on import). Created timezone-handling.

## [2026-09-02] ingest | Map engine: plotly's MapLibre path is unusable at our volumes
Rendered v1 and the OSM topology through the same figure code on `Scattermap` + Carto Dark Matter: >45 s main-thread block on first render for both, instant on the Mapbox path; Carto look rejected. Recorded in codebase-v1 with deck.gl on Mapbox Dark as the keep-the-look exit; spec caution replaced.

## [2026-09-02] ingest | Nodal disaggregation survey
PyPSA-Eur's 60/40 GDP/population load split is superseded by its own JRC Energy Atlas adoption (v2026.02.0) and by Mu et al. 2026 (metered validation); ENTSO-E per-unit actuals need a JRC-PPDB-OPEN + GEM geolocation join because powerplantmatching yields no coordinates; no historical-dispatch mode exists in PyPSA-Eur. Created nodal-disaggregation; architecture item 2 and spec steps 1/3 revised.

## [2026-09-02] decision | Pivot: OPF constrained by measurements replaces measured injections + lpf
Load is unobservable below the bidding zone and the border check cannot separate load from generation errors, so Sushi 2 becomes a v1-style OPF on the OSM grid run from the refreshed PyPSA-Eur fork (HiGHS), with zonal actuals calibrating renewables and per-unit actuals fixed as constraints. Architecture page and spec rewritten; demo day = newest comfortably fetchable.

## [2026-09-02] setup | Upstream-contributions ledger
Started upstream-contributions: entsoe-py #480/#534, a PyPSA-Eur hindcast mode, and stale historical series as candidates; atlite #257/#261 as precedent.
