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

## [2026-09-02] ingest | PyPSA-Eur fork layout and hygiene
Fork master becomes a pristine upstream mirror (superseded the same day by the pinned-sibling decision below); 2022 history archived as `legacy-2022` and the `coppersushi-v1` tag. Created pypsa-eur-sibling.

## [2026-09-02] decision | Working OPF first; true-up to actuals later; PyPSA-Eur as pinned sibling
Review (Ljube): drop validation and all true-up steps from the Sep 11 cut — a working OPF for a 2024 day, drawn and hosted. PyPSA-Eur runs from a sibling checkout pinned by a file in this repo (submodule rejected: per-worktree clones and data).

## [2026-09-02] decision | Dataflow graph carries planned parts, dashed
The architecture graph was implemented-only; plans lived in prose. It now holds planned nodes and edges as dashed `planned`-class parts that feature PRs turn solid. Rule `architecture-delta` and the review-graph spec amended.

## [2026-09-02] ingest | How we contribute upstream
Digested PyPSA-Eur's contributing guide and PR template (AI-contribution rule, release notes, pre-commit) and the fork-rehearsal process settled while preparing three `clusters: all` fixes; added to upstream-contributions.

## [2026-09-03] decision | Rule provenance as the ablation lookup
Rule and skill lines record the observed stumble that earned them in rule-provenance, kept out of the rules and skills so those stay imperative; the `ablation` rule points there.

## [2026-09-07] decision | One package, boundary as a module list
`pipeline/` (sources, sinks) and `scripts/` folded into `coppersushi/`, modules named by domain noun. The dataflow that justified role folders is PyPSA-Eur's; this repo specifies the model, shelves its results and works on the network in memory. The I/O boundary is now the two modules the architecture test names. Retired `narrate-slow-ops` (the one slow step delegates narration to snakemake); `explicit-timezones` stays although nothing constructs a timestamp today, because its stumble was observed and true-up brings timestamps back; the goldfish pass also restored the "How we contribute" section a rebase had dropped from upstream-contributions.

## [2026-09-08] ingest | Flow-based versus NTC capacity calculation
Distilled how cross-zonal capacity reaches EUPHEMIA: NTC pipes per border on most European borders, flow-based CNEC constraints (PTDF, RAM, shadow price) in Core since 2022 and the Nordics since 2024, the 70 % minimum-RAM rule, and JAO's publication timeline. Framed the nodal OPF as the full-information version of flow-based coupling and listed what it does not reproduce. New page flow-based-market-coupling.

## [2026-09-08] decision | JAO's elements on our grid as a separate task
JAO's finalComputation carries substation names, element types and the TSOs' own limits per element and hour; OpenStreetMap carries the coordinates PyPSA-Eur's extract drops. Matching the two gives a map of what limited Core trade on a day and true limits for our lines and transformers (PyPSA-Eur's 2000 MVA transformer default against real 555–607 MW units). Split out as specs/jao-grid because it needs nothing from the OPF; the congestion forecast consumes its outputs.

## [2026-09-08] ingest | How Core's capacity is computed: three documents
Digested the Core TSOs' 2018 explanatory note, JAO's publication handbook and the EUPHEMIA public description into a new `literature/` folder, one link-only page per document, and synthesised them in core-capacity-calculation: each TSO models its own grid and sets its own elements, limits, margins and shift key; Coreso merges; Coreso and TSCNET run one DC load flow with contingency analysis on the merged model; TSOs may only cut; JAO publishes; the exchanges clear. The 2018 note predates the 70 % rule, advanced hybrid coupling and the Central Europe merger, recorded on its page. The flow-based page's NTC section now points there instead of repeating the process. Decided in the grill: the folder holds every authoritative document the wiki draws on, added sparingly; link only, no raw copies, because EUPHEMIA's notice forbids reproduction and one rule beats two. A goldfish critic caught a wrong 70 % reading (the 20 % floor stays, the larger applies), a wrong nuclear-exclusion list, a CWE figure attributed to Core, and actors the documents never name.
