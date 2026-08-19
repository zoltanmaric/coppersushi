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
