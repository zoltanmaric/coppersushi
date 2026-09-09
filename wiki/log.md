# Wiki Log

Append-only chronology of wiki operations (ingests, queries, lints).
Entry format: `## [YYYY-MM-DD] <operation> | <title>`

## [2026-09-10] query | What the Electricity Maps API provides

The first inventory probed legacy v3 route names and mistook their 401 responses for product
entitlements. The current v4 API separates electricity mix, flows, total and reported load, net
load, European day-ahead prices, US locational prices and carbon signals. With the project key,
day-ahead price forecasts returned 24 hourly points for all twelve Core zones; electricity mix,
flows, total load, net load and carbon intensity returned the present hour plus 24 ahead for
Germany. Their rolling histories worked, while arbitrary `past` and `past-range` requests remained
denied. The price-specific `actual` route still returned all 24 hours of 2024-08-29 for every Core
zone, so Electricity Maps can provide the backtest's settled prices but not its historical grid
signals. The catalog contains no bids or bid curves. A same-hour check also found the mix's
aggregate flows and the dedicated neighbour-flow forecast implying opposite German net-position
signs, so that input is unsafe until clarified or guarded by an invariant. Created
electricity-maps-api and corrected the backtest source decision. No credential or authenticated
response value was retained.

## [2026-09-10] change | JAO's Static Grid Model: real transformer ratings and impedances
The Core Static Grid Model (5th release, 2024-03-29 — the one in force on 2024-08-29) fetched as one
1.7 MB zip and reduced to `data/jao-static-grid/2024-03-29/`: 520 transformers (136 of them phase
shifters) and 2,967 branches (2,633 lines, 334 tie-lines), 449 KB. `EIC_Code` is the key the
publication feed already carries, and 103 of the day's 106 element EICs join, including all 17
monitored transformers and phase shifters.
Four quirks measured. The real column names are on the second row, under a merged banner. The current
rating is `Max`, falling back to `Fixed` then `Min` — only 339 of 520 rows have `Max`. A row is a
phase shifter when `Theta θ (°)` is populated (136), which the names do not tell you: 99 of those are
named `TR`, and JAO's own feed disagrees with the workbook in both directions. And `EIC_Code` is not a
key — two RTE pairs share one EIC while differing in rating and impedance, a tie-line appears once per
TSO owning an end, and 29 line rows carry none at all.
The headline number: JAO's real transformer ratings have a median of 790 MVA where PyPSA-Eur's
placeholder (`build_osm_network.py:1245`, the summed line capacity at the busier bus) has 4,425 MVA.

## [2026-09-10] change | No JAO bytes in a public repository

JAO's [terms](https://www.jao.eu/terms-conditions) reserve all reproduction rights, limit use to
internal information purposes and forbid Content being disseminated, copied, extracted or
distributed without written authorisation. This repository is public, so `data/jao/2024-08-29/`
(the four CSVs) and the three captured API responses under `tests/fixtures/jao/` are deleted and
both paths gitignored. Reproducibility is unharmed: the endpoints are public and keyless, and
`python -m coppersushi.data_sources.jao fetch 2024-08-29` rebuilds the tables byte for byte.

The tests now run on `tests/fixtures/synthetic-jao/`, written to JAO's response shape with invented
TSOs, EICs, substations and numbers, and carrying every quirk the real capture was kept for: two
TSOs publishing different `fmax` on one tie-line, trailing whitespace on names and substations, a
contingency branch published wholly as `"NA"`, the four external and two equality constraints, a
non-presolved row, prices in hours the domain feed does not cover, and the untyped element — an
EIC and a limit with `elementType: null` and `"NA"` everywhere else.
The real measurements those stand for stay here and in the entry above, not in the tree.

## [2026-09-09] change | JAO's two feeds land as four tables
2024-08-29's Core domain and shadow prices fetched hour by hour on the CET market day and reduced to
`data/jao/2024-08-29/` (gitignored; see the 2026-09-10 entry): 1,738 element rows over 106 EICs, 4,169 contingency rows, 78 shadow prices on
13 binding elements, 192 external constraints, 145 distinct substation names, 1.0 MB. `coppersushi/cnecs.py`
owns every quirk of the feeds; `coppersushi/data_sources/jao.py` owns only HTTP and CSV.
Four quirks measured rather than assumed. Names carry trailing whitespace (105 of 113 `cneName` values),
so nothing joins until stripped. One tie-line monitored by two TSOs carries two `fmax` values
(Cirkovce-Heviz: ELES 1109 MW, MAVIR 1386 MW) — the tighter one binds, flagged, and a differing `fmax`
without a differing TSO raises. Contingencies come structured, one entry per outaged branch, not parsed
from `contName`. And **a missing `elementType` does not mean a row is not an element**: JAO publishes real
elements with real EICs and real limits whose location metadata is absent — `St. Peter 2 - Salzburg 455`
(EIC 14T-220-0-00455F, 220 kV APG, fmax 624) was being dropped from `elements` and misfiled as an external
constraint, including in the four hours JAO actually presolved it. Non-physical now means what the handbook
says: an External or Equality Constraint name, or the literal `"NA"` EIC.

## [2026-09-09] change | Snapshots follow the Core market day, hourly
The shelf solved UTC days at 2-hour resolution; JAO publishes hourly on the CET market day, so a JAO hour had no snapshot to land on without a mapping rule. Config now runs 24 hourly snapshots from 22:00Z to 22:00Z (23 or 25 across a clock change), derived by `coppersushi/market_day.py` rather than hand-typed. Both OPF networks re-solved and re-promoted; `opf-2013-07-17-v1.nc` is left alone, being a 2022-fork artefact that cannot be reproduced. Also corrected pypsa-eur-sibling: the checkout has one remote, `origin`, pointing at the fork — upstream is not a remote at all, so the documented `master` sync was a no-op against itself.

## [2026-09-08] backtest | One day scored against JAO and settled prices
2024-08-29 solved on the OSM grid and compared with JAO's 78 binding CNECs and settled Core prices. Zone-pair rank correlation went -0.03 -> +0.29 and price bias -119 -> -60 EUR/MWh across four runs; the whole gain came from pricing CO2 (Instrat daily EUA), with dynamic fuel prices and the 2025 cost vintage worth about a point each. Congestion *location* never correlated (rho ~0) — that is jao-grid's lever, not a cost one. New page backtest-2024-08-29; two upstream bugs found and patched on the fork.
## [2026-09-08] lint | Cutout naming corrected: the weather year follows the day
`europe-1940-2024-era5` appeared in pypsa-eur-sibling and the sushi-2 spec as the prebuilt cutout in play. It is neither: it names a CDS build recipe in upstream's `cutouts:` map (404 as a file), while `atlite.default_cutout` is `europe-2013-sarah3-era5`. Cutouts are one calendar year, so the 2024-08-29 day needs `europe-2024-sarah3-era5`. Upstream already rejects a mismatch (`sel(time=...)` raises), but only after the 6.7 GB download and without naming the cause, so a config test now checks the two years agree up front. Found by dry-running the 2024 day: the DAG resolved `retrieve_cutout` to the 2013 file. Sushi-2 step 2 gains the cutout as its third change.

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

## [2026-09-08] decision | Fork layout: pristine master, `coppersushi` integration branch, tagged pins
The fork's `master` stays a mirror of upstream so each rehearsal PR shows one fix; the pin is a tested head of the `coppersushi` branch — upstream `master` plus the not-yet-merged fixes cherry-picked on top, nothing else, rebuilt whenever either moves; the fork's open rehearsal PRs are the record of the layers, in PR-number order. Rebasing orphans old pinned SHAs, so every pin gets an immutable `pin/<YYYY-MM-DD>-<what is new>` tag on the fork; a rule, not a check in the runner. Rejected: fixes on the fork's `master` (breaks the rehearsal PRs' base and wins nothing, the runner is branch-blind) and merge-sync (a merged integration branch cannot absorb a topic branch amended during review without duplicating its commits).

## [2026-09-09] decision | The pin moves only with a promotion
A pin bump for two inert layers was drafted and withdrawn: the pin is provenance for the sanctioned networks, not a latest-tested pointer, so it moves only in a commit that also promotes a network — as the first pin did. Pinning on every branch expansion was weighed and rejected: each promotion is a permanent LFS object, and a re-solve without a model change swaps in an equal-cost but different vertex (the withdrawn solve matched the sanctioned result in objective and every nodal price yet differed in flow on 1,723 of 7,371 lines), a visible change with no cause.

## [2026-09-09] query | Zonal spreads are shadow prices times PTDF differences
Checked on JAO's own numbers for 2024-08-29: the shadow-price page's PTDFs times its shadow prices, summed per hour, reproduce the price-spread page across 874 zone-pair hours (correlation 0.997, right sign on all 202 spreads above 20 €/MWh; within 2 % in ten hours, off by up to half in the others by an hour-varying factor, so constraints missing from the page rather than a scaling error; which ones is open). Recorded on flow-based-market-coupling as the bridge from binding elements to prices that needs no nodal price. Same check surfaced web-service facts the handbook lacks, now on its digest: a structured `contingencies` list per row, `hub_` PTDF columns on the shadow-price page, the price-spread sign convention, the page names. specs/jao-grid corrected accordingly: contingencies need matching, not parsing; the shelf holds no 2024 day yet; one transformer among the day's thirteen binding elements.

## [2026-09-09] ingest | Aggregated bid curves, and the carbon price in the bid proxy
The exchanges publish each zone's aggregated curves, all NEMOs combined, since October 2021, as paid internal-use subscriptions: EPEX per market area via the EEX webshop, Nord Pool per region; seven Core zones covered, none of CZ, HU, HR, SI, SK. Recorded on flow-based-market-coupling with why the cost proxy must carry the day's allowance price: at about €70 a tonne it re-orders coal and gas.

## [2026-09-09] query | The day-ahead chain step by step, and one row of the domain
Every heading another page links, not only vocabulary entries, is one token so GitHub and Obsidian resolve the same link. New wiki rule `term-anchors`, after D2CF was met cold in the spec and ordinary multi-word headings then failed the same cross-viewer check.

Review follow-up: the standard median of first-hour slack is 768 MW, the average of the two middle rows, not the previously reported upper-middle value of 775 MW. The page now quotes JAO's full contingency name, links the Core-versus-whole-market constraint distinction, and restores Lixhe–Gramme's 12 % Belgium–Netherlands sensitivity and −0.421 ALEGrO coefficient. The post-nomination 20 % floor remains: Equation 19 applies it to final RAM and the following paragraph permits a lower TSO factor only for operational security. The explanatory-note diagram now distinguishes presolve and the 08:00 pre-final publication from nominations and the 10:30 final publication; its Central Europe note records that the cited decisions establish the merger but do not establish its application date.

core-capacity-calculation restructured and renamed core-day-ahead-capacity-calculation as the reference for the August 2024 process. An actor map leads into the vocabulary; one row, APG's Obersielach–Podlog tie-line under the outage of Maribor–Kainachtal 1, is read in dependency order on 2024-08-28 and 29, then carried through all fourteen net-position terms to binding, its shadow price and the exact €31.61/MWh Austria–Slovenia spread at 00:00. The eleven steps use a fixed actor, input, work, publication order; dataset-wide checks follow them. Lixhe–Gramme remains the worked minimum-margin lift. Verified on JAO's rows: `ram = fmax − frm − fcore + amr − cva − iva − fltn + ltaMargin` on all 116 presolved rows of the first hour; the minimum-RAM lift in its two-floor form, `minRamTarget = max(0.20, minRamFactor / 100 − fuaf / fmax)`, on all 11,560 non-equality rows; `fref = frefInit − fnrao` on all 7,019 rows with a remedial-action effect, with 3,512 negative and 3,507 positive values; `fmax = √3 · 400 kV · imax` on all 10,080 rows of the 380 kV level; `fcore = fref − Σ ptdf · NP` at D2CF's net positions with ALEGrO at its 713 MW reference flow, within 15 MW on all element rows. The 220 kV label is not one calculation voltage: 662 of 918 rows match 225 kV and 256 match 400 kV, but the page does not infer an unpublished calculation voltage from that pattern. Day to day: 479 of 487 elements, 97 % of rows and 89 of 108 presolved element rows shared between the two days. Goldfish reviews found what the first draft missed: the 116 presolved rows include four equality rows beside ALEGrO's four bounds; `fnrao` is signed relief; `ltaMargin` was zero everywhere and its exact role remains unstated; a binding facet outside the flow-based shadow-price feed has no published row; `frm` is the flat 10 % default; Poland's whole-market net position was capped every hour through the allocation-constraint feed; Coreso is the merging agent. The final pass also separated Core capacity calculation from Europe-wide zonal clearing, scoped the page explicitly to the hourly 2024 process, qualified the shadow price as a dual after order selection, and distinguished publication ownership: exchanges publish zonal prices; JAO publishes net positions, shadow prices and price spreads. New wiki rule `page-names`, after two generic names in one day.
