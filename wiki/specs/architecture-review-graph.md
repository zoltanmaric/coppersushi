# Spec: lightweight architecture review experiment (burn-down)

Working memory for a Copper Sushi 2 pilot. Domain architecture: [sushi-2.md](../sushi-2.md).

## Problem

Large agent PRs have been costly to review elsewhere, but Copper Sushi has not yet exhibited that failure. Test the cheapest useful form of architectural review compression on real Sushi 2 work without delaying the Sep 11 cut. This surface covers architectural shape only; tests and independent agent review cover implementation correctness.

## Approach

Keep one small, explicit Mermaid DAG in the durable Sushi 2 architecture page. Nodes are domain artifacts; an edge means “required to produce.” Since 2026-09-02 the graph also carries **planned** parts, dashed (`classDef planned`): a plan PR adds or removes them, a feature PR turns them solid, so a review reads as “which dashed parts got fleshed out” rather than a fresh drawing each time. The diagram is deliberately human-maintained: its small diff, plus an **Architecture delta** section in every PR body (`None` is valid), is the review surface. No framework, extractor, policy language, graph bot, or required graph check until real use proves those costs worthwhile.

Add one narrow enforcement mechanism now: external I/O belongs in the boundary modules the architecture test names (`networks`, `pypsa_eur`), while every other module accepts and returns in-memory values. Enforce a documented finite set of imports/calls with a small AST-based test. This is not a claim to detect dynamic or transitive I/O, nor to prove referential transparency; PyPSA's in-memory mutation remains allowed.

Scope is the `coppersushi/` package; `app.py`, the composition root, sits outside the test and is where the Mapbox token is read.

## Deliberately deferred

- **Hamilton, Kedro, or Dagster:** no framework until execution needs or repeated manifest maintenance justify one; none supplies the whole review workflow.
- **Automatic extraction and exact-graph CI:** reconsider only if a pilot PR omits or misstates an architectural change. An agent can update a graph lock alongside its code, so extraction proves correspondence but does not replace review.
- **Automatic PR rendering or a bot:** reconsider only if the Mermaid page plus PR-body section proves too hard to find or use.
- **Universal hidden-I/O or purity detection:** dropped as unsound for dynamic Python. Enforce only the finite, documented boundary above.

## Next steps

Use the surface on the next three real Sushi 2 PRs that add or rewire sources or transformations. The user reviews the diagram/delta without reading the full diff; an independent agent audits the full diff for omitted architectural facts.

## Pilot PRs

1. #19 (PyPSA-Eur runner, OSM assembly deleted, package fold): delta stated; a goldfish pass found it omitted the planned-to-solid transition of three nodes, recorded and fixed before merge. The architecture test caught a file read inside the plotting code the first time it covered that module.

## Acceptance criteria

- [x] The rendered DAG is readable at GitHub's default view and its source gives each artifact and dependency one stable, reviewable identity.
- [ ] Every pilot PR states its architecture delta and updates the DAG when topology changes.
- [x] The finite I/O-boundary test passes on adapters and demonstrably fails for a covered I/O operation in a transformation.
- [ ] Across three qualifying PRs, the architecture-only verdict survives the independent full-diff audit in at least two; every omission is recorded.
- [ ] After the third PR, explicitly choose to discard the experiment, retain the manual surface, or spec automation from the observed failures.
- [ ] Durable findings are distilled into the wiki and this spec is deleted.
