# Spec: architecture-first agent review (burn-down)

Working memory for a Copper Sushi 2 pilot. Domain architecture: [sushi-2.md](../sushi-2.md).

## Problem

Agent PRs can contain too much code for sustainable line-by-line human review. The primary review surface should instead expose architectural change: new data sources, artifacts, dependencies, branches, bypasses, cycles, and sinks. Tests and agent review remain responsible for logical correctness.

## Approach

Model Sushi 2 as a compact DAG whose nodes are stable domain artifacts and whose edges mean “required to produce.” Producer functions are pure; file, network, and database I/O exists only in declared source/sink adapters. The graph is extracted deterministically from the implementation and compared with a small, committed, default-deny architecture policy—the software-reflexion-model pattern. The policy is an enforceable allowlist, not a manually synchronized diagram.

Every GitHub PR gets a merge-base-versus-head graph delta with unchanged context muted and architectural changes emphasized. CI fails on any unapproved node or edge, forbidden dependency, cycle, undeclared I/O, or unmatched production component. A legitimate change updates the policy in the same PR, making the architecture decision explicit for human review. Changed nodes link back to their producer/contracts; private helpers stay below the default zoom level.

Scope is Python Sushi 2 only. `app.py` and the old `scripts/` implementation remain frozen legacy until replaced. No attempt at logical-error detection or a language-independent framework.

Rejected for the pilot: a documentation-only diagram (will drift); a raw function/file graph (too detailed); CodeSee alone (file-level rather than domain ontology); Dagster (operational orchestration beyond the review need). Do not assume Hamilton: compare it with Kedro and a minimal project-owned implementation first.

## Next step (detailed)

Build the same tiny vertical slice—`osm_grid_files → european_grid`—three ways: Hamilton, Kedro, and a lightweight typed node/adapter declaration plus extractor. For each, produce the default graph, a graph diff after adding a second source/branch, and a failing conformance check. Compare only what matters here: semantic granularity, collapsibility, source/sink visibility, type/schema metadata, merge-base diff support, GitHub rendering, enforceability, implementation ceremony, and dependency/maintenance cost. Choose the smallest option that satisfies the review workflow; delete the other spikes.

## Later (coarse; re-plan after the spike)

Define the initial approved Sushi 2 graph and ontology → enforce pure producers and declared adapters → publish graph deltas as a required GitHub check → exercise the system on real Sushi 2 work and adjust granularity once from evidence.

## Acceptance criteria

- [ ] One command deterministically emits both a human-readable graph and a machine-readable graph from Sushi 2 code.
- [ ] The default PR view remains readable without expansion and shows only domain artifacts, edges, sources/sinks, and changed context.
- [ ] An implementation-only change with identical topology produces no architectural delta.
- [ ] Adding or removing any top-level node or edge fails CI until the approved model is deliberately updated.
- [ ] A hidden I/O call, forbidden bypass, cycle, or unclassified production module fails CI with a useful explanation.
- [ ] The GitHub PR surface highlights added/removed nodes and edges and links changed nodes to their implementation and contract.
- [ ] A real Sushi 2 PR can be architecturally accepted or rejected from this surface without reading its full diff.
- [ ] Durable findings are distilled into the wiki and this spec is deleted.
