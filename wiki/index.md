# Wiki Index

## Concepts
- [copper-plate-problem.md](copper-plate-problem.md) — the EU market-design argument motivating this project (copper plate, redispatch, co-optimisation, locational pricing)
- [flow-based-market-coupling.md](flow-based-market-coupling.md) — how cross-zonal capacity reaches the day-ahead market: NTC pipes versus Core's flow-based CNEC constraints, PTDF, RAM, shadow prices, and what a nodal OPF does and does not reproduce
- [core-capacity-calculation.md](core-capacity-calculation.md) — who computes Core's flow-based domain and when: TSO models merged by Coreso, one central DC load flow by the coordination centres, TSO validation, JAO, EUPHEMIA
- [agent-workflow-design.md](agent-workflow-design.md) — rationale and sources behind the `design-first` and `ablation` rules and the grill/spec/goldfish skills
- [rule-provenance.md](rule-provenance.md) — the observed stumble behind each `AGENTS.md` rule and skill line; the `ablation` rule's lookup table
- [nodal-disaggregation.md](nodal-disaggregation.md) — survey: splitting measured national load and generation into per-node injections; what superseded PyPSA-Eur's approach
- [upstream-contributions.md](upstream-contributions.md) — how we contribute upstream (fork rehearsal, PyPSA-Eur's rules) and the ledger of dependency bugs we need fixed
- [timezone-handling.md](timezone-handling.md) — the `explicit-timezones` convention, its rationale, and the PyPSA naive-UTC boundary

## Entities
- [sushi-2.md](sushi-2.md) — Copper Sushi 2: optimal power flow on the 2025 OSM grid via PyPSA-Eur as of 2026; architecture
- [backtest-2024-08-29.md](backtest-2024-08-29.md) — one solved day scored against JAO's binding CNECs and settled prices: what each config change bought, and what to fix next
- [pypsa-eur-sibling.md](pypsa-eur-sibling.md) — PyPSA-Eur as a pinned sibling checkout: why not a submodule, fork refs and rules, the 2026-09-02 refresh record
- [copper-sushi-app.md](copper-sushi-app.md) — what the app shows, the OPF behind it, data provenance and caveats
- [codebase-v1.md](codebase-v1.md) — v1 architecture, known weaknesses (v2 targets), lineage 2022→2026

## Specs (working memory — burn-down state, not settled knowledge)
- [specs/sushi-2.md](specs/sushi-2.md) — the Sep 11 cut: next steps and acceptance criteria
- [specs/jao-grid.md](specs/jao-grid.md) — JAO's Core elements matched to our OSM grid: a map of what limited trade on a day, and true line and transformer limits from JAO's own numbers
- [specs/architecture-review-graph.md](specs/architecture-review-graph.md) — lightweight architecture-review experiment: manual DAG, PR deltas, and an I/O-boundary test

## Literature (one digest per authoritative document, link only)
- [literature/core-da-ccm-explanatory-note.md](literature/core-da-ccm-explanatory-note.md) — Core TSOs' explanatory note on the flow-based capacity calculation methodology, June 2018, with what the amendments changed
- [literature/jao-core-publication-handbook.md](literature/jao-core-publication-handbook.md) — JAO's Core publication tool handbook v1.8, Dec 2022: pages, columns, publication times
- [literature/euphemia-public-description.md](literature/euphemia-public-description.md) — the NEMOs' EUPHEMIA public description, Dec 2025: objective, network models, order types, algorithm

## Raw sources (immutable)
- [raw/the-copper-plate-must-die.md](raw/the-copper-plate-must-die.md) — blog post, Jun 2022
- [raw/copper-sushi-power-flow-european-grid.md](raw/copper-sushi-power-flow-european-grid.md) — blog post, Aug 2022
