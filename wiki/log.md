# Wiki Log

Append-only chronology of wiki operations (ingests, queries, lints).
Entry format: `## [YYYY-MM-DD] <operation> | <title>`

## [2026-09-10] query | Which way a published row binds

Checked on the 2026-09-11 final domain: `direction` is relative to the publishing TSO's own
`substationFrom`. APG's `Duernrohr 1 - Slavetice 437` and ČEPS's `Slavetice - Durnrohr - V437`
share one EIC and both have DIRECT rows, with PTDFs of opposite sign; TenneT's and APG's rows on
`Pirach - St. Peter 256`, published from the same end, agree. `activeFbConstraints` cannot orient a
row: its `hubFrom`/`hubTo` name the most constrained zone pair, not the element's ends (`Nosovice -
Varin`, a CZ–SK line, is CZ→HU there; every one of the day's 173 rows has two different hubs,
transformers included). Orientation therefore needs each TSO's own ends, kept per EIC and TSO.

## [2026-09-10] query | Electricity Maps' default price resolution

`price-day-ahead/actual` answers hourly unless `temporalGranularity=15_minutes` is asked for, and
its hourly value for a quarter-hourly day is the mean of the four cleared prices. The finding below
that the route "supplied hourly published prices" described that default, not the source's
resolution; the map at app.electricitymaps.com shows the quarter-hours.

## [2026-09-10] query | Active flow-based constraints and published prices

JAO's `activeFbConstraints` response on 2026-09-10 supplied quarter-hourly binding physical rows with
their shadow prices and all twelve Core PTDFs, plus non-spatial external constraints; it does not
require the full final-domain download for the price-influence calculation. Electricity Maps'
`price-day-ahead/actual` route supplied hourly published prices for all twelve zones on the same date.
The selected-row contribution is `-shadow price × (PTDF zone - PTDF reference)`.
The SDAC market-time-unit calendar is hourly through delivery day 2025-09-30 and quarter-hourly
from 2025-10-01, so the view generates the full day independently of JAO's sparse binding-row feed.

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
1.7 MB zip and reduced to 520 transformers (136 of them phase shifters) and 2,967 branches (2,633
lines, 334 tie-lines). Nothing derived from it is committed: JAO's terms reserve every right of
reproduction and permit only internal use, so `jao_static_grid.fetch` writes into a gitignored
`data/jao-static-grid/<release>/` and is the only way to obtain the tables. `EIC_Code` is the key the
publication feed already carries, and 103 of the day's 106 element EICs join, including all 17
monitored transformers and phase shifters.
Four quirks measured. The real column names are on the second row, under a merged banner. The current
rating is `Max`, falling back to `Fixed` then `Min` — only 339 of 520 rows have `Max`. A row is a
phase shifter when `Theta θ (°)` is populated (136), which the names do not tell you: 99 of those are
named `TR`, and JAO's own feed disagrees with the workbook in both directions. And `EIC_Code` is not a
key — two RTE pairs share one EIC while differing in rating and impedance, a tie-line appears once per
TSO owning an end, and 29 line rows carry none at all.
And a published reactance is not always a usable one: one transformer has x = −11.7 Ω and one line
has x = 0, which in a power flow is a short circuit rather than a small impedance. Neither is
repaired — the workbook says what it says — both are flagged `x_physical = False`.
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


## [2026-10-04] decision | Lambda hosting direction

Recorded the eventual Lambda and S3 direction in [copper-sushi-app](copper-sushi-app.md#hosting), separate from PR #95. The target is low idle cost and occasional visitors; roughly 30-second cache misses are acceptable, viral capacity and whole-day background fetching are not requirements. Migration still needs an end-to-end deployment check.


## [2026-10-09] decision | Independent day-ahead price forecast

Established the `forecasts/` project: Germany–Luxembourg quarter-hour prices at an 11:00 German-local information cutoff, one CatBoost model with five quantiles and weighted interval score. Public fundamentals, fixed-lead weather, demand availability handling and chronological all-date evaluation form the first build. Filed the data checks and light evaluation contract, brought reusable diagnostic evidence into the repository, and added the dataset/evaluation implementation spec. Raw downloads remain ignored local inputs. This is a design handover; no quantile-model performance, competition participation or daily service is claimed.

## [2026-10-09] ingest | Lovable CNEC interaction review

Inspected the public WelfMaxxing port in Chrome: border, transformer and line-interior clicks select constraints and show comparison rays. Reproduced a stale tooltip across interval changes, incorrect export-cap wording using €/MWh, and ray labels without units. Recorded the port candidates and regression cases in the [port-back spec](specs/cnec-constraint-selection.md); source arithmetic and the feature subset remain to be checked and agreed.

Agreed direct border/transformer/line selection, selected-border highlighting and comparison rays. The rays must isolate the selected constraint's signed contribution to the zonal price difference, including for border constraints; observed price spreads are not a substitute. Control layout and automatic versus explicit reference selection remain open. Captured the distinction between physical PTDFs and the coefficients of the actual border constraint, plus cancellation between contributions, in the spec.

Added previous/next market-time-unit buttons and minor timeline ticks to the port scope; deferred collapsible controls. Reference-zone behaviour remains open.

The border feature is defined by intent: highlight a country when its country-wide import/export cap binds, then show that cap's signed contribution to the price spread. Lovable's mapping of interconnector-labelled rows is not the specification. The remaining data question is availability of the intended cap and its published shadow price.

The supplied Lovable implementation report identifies `activeFbConstraints` rows 286719, 286718 and 286717 at 2026-09-11 22:00 UTC (delivery day 2026-09-12, 00:00 CEST): SwePol, COBRA and ALEGrO export limits, with coefficient +1 respectively on `PL_SE4_SwePol`, `NL_DK1_COBRA` and `ALBE`, and zero on the Core-country hubs. This raw-row report has not been independently fetched. The supplied code maps names to country outlines and computes border rays as `price_other − price_reference`; physical-row rays instead use `-shadowPrice × (PTDF_zone − PTDF_reference)`. The former is the wrong quantity for the agreed feature.

For those reported coefficient vectors, each row's direct contribution to a Core-country-pair spread is zero in this decomposition. That does not mean relaxing the cable cannot change the clearing outcome, nor that its shadow price alone is the complete cable-end country spread. [N-SIDE's AHC explanation](https://www.n-side.com/en/insights/introduction-of-advanced-hybrid-coupling-in-the-core-region-of-the-european-day-ahead-market/) distinguishes country-to-virtual-hub contributions from the interconnector and the other region's contributions. A row's signed coefficients must be verified before using an extra direction multiplier; the display's `OPPOSITE` label alone is not a reason to flip them again.

## [2026-10-09] query | Forecast implementation readiness

[Reviewed the forecast handover](price-forecasting/evaluation.md#limitations) against its diagnostic scripts and provider documentation. Recommended the bounded research build, with the historical availability claim narrowed to match its evidence, prospective input snapshots, and fixed controls to separate price/calendar skill from weather and demand value. Archive-induced demand missingness can differ from live availability. These are review recommendations, not amendments to the agreed spec.

## [2026-10-09] query | Country-cap duals and flow-based scaling

Independently fetched the September 12 JAO rows: the three external rows limit virtual hubs, while Poland's aggregate allocation feed supplies limits without shadow prices. Filed the cap-sign algebra and source audit in [country import/export caps](country-import-export-caps.md). Cross-CCR `DA_PL_AC` is a possible adjusted-price source, but its `PL_ALT` definition is unconfirmed and 96 daily rows share only 24 timestamps. No reliable quarter-hour cap attribution is established from it.

Corrected the earlier inference that the August 29 18:00 CEST spread lacked €113/MWh of published constraints: 595.318814 divided by JAO's α=0.8401168134 reproduces 708.61 €/MWh. This demonstrates the need to distinguish raw FB terms from normalized attribution; it does not establish a universal divide-by-α rule. Updated the fundamental pages and refocused the selection spec on intended behaviour, independent of the prototype implementation.

## [2026-10-09] query | Polish cap attribution established empirically

Compared cached quarter-hour prices and physical constraints against JAO feeds for six days: September 10, 12, 30 and October 2, 7, 8. Across 576 intervals, `market price − PL_ALT` is zero in all 341 slack intervals, negative in all 206 export-bound intervals and positive in all 29 import-bound intervals. Independently, `PL_ALT − Slovakia price` matches the alpha-normalized physical-constraint sum within €0.02/MWh in every interval. This supports using the difference as the Polish cap component without waiting for provider clarification.

Recovered the truncated quarter-hour timestamps by ascending within-hour row ID, independently checked through net positions: 506 unique matches, no contradictions; chronological order is the only fixed permutation fitting each day. Documented guarded reconstruction and the limit of the inference: Poland is covered, other country caps are not established. Raw and derived price data remain in the ignored local cache; the wiki records aggregate validation only.

## [2026-10-09] decision | Forecast defaults and feature comparisons

Recorded the agreed [evaluation defaults](price-forecasting/evaluation.md#defaults): local-clock price matching, missing weather, fixed calendar features, source-failure fallbacks and pooled training-error quantiles for the simple reference. Three fixed feature sets measure the added value of weather and demand. The implementation spec links these decisions; exact dates, remaining price features, model settings and minimum reference history remain to be frozen before fitting.

## [2026-10-09] decision | Forecast inputs in S3, local training first

The [forecast infrastructure design](price-forecasting/forecast-infrastructure.md) selects fixed Parquet input snapshots in S3, local Metaflow execution and local MLflow experiment tracking. Storage follows batch access and reproducibility needs. Cloud scheduling, shared tracking and a separate catalog remain later decisions. The first iteration can evaluate models without deploying cloud compute.

## [2026-10-09] decision | Forecast reproducibility and deployment principles

The [infrastructure design](price-forecasting/forecast-infrastructure.md) makes exact provenance and one-command reproduction the forecast promise. Storage selection follows required reads and writes, with complexity justified by demonstrated needs. The later deployment preference is Metaflow with Step Functions and AWS Batch on Fargate, using Terraform for infrastructure; an end-to-end deployment check precedes adoption. The first iteration remains local execution with inputs in S3.

## [2026-10-09] decision | Separate forecasting product architecture

The [forecast product overview](price-forecasting.md) owns its independent dataflow graph. The power-flow product page contains only its own pipeline. Architecture deltas belong to the affected product; the root rule now expresses that boundary.

## [2026-10-09] decision | Point-in-time correctness as a forecast promise

Elevated point-in-time correctness beside reproducibility in the forecast design. The input contract distinguishes valid time, source issue/update time and retrieval time, with explicit availability evidence. Acceptance now includes an adversarial leakage test against an enlarged candidate history, covering input selection, training labels and learned transformations. Historical timing assumptions remain visible in reports.
## [2026-10-09] ingest | SDAC 2026 country-cap inventory

The Market Coupling TSOs' April 2026 inventory lists Poland alone under net-position allocation constraints. TenneT's official notice ends the Dutch country cap on 2023-12-15. Corrected the interpretation of older handbook examples: absent Dutch/Belgian cap duals are not unexplained coverage gaps for 2026. Filed every Core bidding zone's status, including Luxembourg's shared zone with Germany, and distinguished cable ramping and Italy's line-set constraint from aggregate country caps.

Corroboration: all non-Polish zones' price differences against Slovakia match the physical-constraint reconstruction within €0.02/MWh across the six cached days; the reference comparison is an identity. A wider scan completed 101 UTC days, 9,696 allocation rows with no Belgian cap and 35,081 active FB rows with no aggregate country external constraint. The full-year attempt encountered rate limiting and is not claimed complete. Verified the API's two-day range limit. Updated the spec to use Polish attribution and leave countries without aggregate caps unhighlighted.

## [2026-10-09] query | Classifying every collected JAO row

Corrected the overly narrow country-cap-versus-lines/transformers taxonomy. A complete 19,904-row final-domain interval on September 12 also contains 22 virtual-hub bounds and four coupling equalities. After joining cached types by EIC, 128 rows still lack an asset subtype and another 68 lack usable EIC/type/endpoints. Filed the taxonomy, counts and unresolved cases in [JAO constraint types](jao-constraint-types.md), with local per-row audit CSVs.

Classified the 3,444 cached active physical rows: 114 rows across seven EICs retain subtype gaps. A separate October 8 active-LTA export has 42 of 49 rows with positive duals. The annual download attempt remains incomplete: bulk exports share the JSON API's two-day limit, and the earlier scan reached rate limiting. No full-year absence of unknown constraints is claimed.

## [2026-10-09] query | Arithmetic attribution checks

Checked all 38,016 Core zone-pair spreads across six cached days: alpha-normalized physical terms plus Poland's cap component agree within €0.02/MWh, maximum €0.01371/MWh. Seeded antisymmetry, additivity, reference/slack invariance and cap-complementarity checks pass. Removing the cap or alpha correction produces thousands of failures. Filed the empirical tolerance and the Polish-price dependency in [price attribution](flow-based-market-coupling.md#attribution-validation), rather than claiming a universal proof.

For October 8, 568 positive LTA facets agree with `(1−α)` times the adjusted directed spread within the observed integer publication precision; 15 virtual-hub facets remain unchecked without hub prices. This supports the scaling interpretation and warns against adding two normalized representations of the same spread.

## [2026-10-09] query | Complete paced annual constraint audit

Completed 549 sequential public API requests for 2025-10-09–2026-10-09 UTC, with zero rate-limit responses. Verified all 35,040 allocation quarter-hours, returned `totalRows`, absence of duplicate source rows and agreement between CSV and summary totals. The year contains 129,001 active FB rows, 35,040 allocation rows and 9,327 active LTA timestamp rows. Poland alone has aggregate country limits; the external FB rows are virtual-hub bounds.

Filed 287,354 classified rows/facets and the audit scope in [JAO constraint types](jao-constraint-types.md#active-audit). Retained 4,448 physical rows across 22 EICs with unresolved subtypes. Clarified that “separate” means separate feeds, not absent from the year, and that an annual active-feed audit is not an exhaustive download of non-binding final domains or all SDAC mechanisms.
