---
name: pull-request
description: Use when creating a pull request, when scope grows inside an open one, when readying one for review, or when splitting work into a stacked-PR chain.
---

# Pull requests

## The principle

**A PR is a unit of review attention, not a unit of work.** The reviewer's attention is the scarcest resource on this project. Scope blowup while working is healthy — it's how exploration happens; the discipline belongs at the review boundary, where the blown-up working set gets refactored into digestible layers. Write big, ship small.

`commit-cadence` is the enabler: atomic, cohesive commits are pre-cut fault lines, so chopping a PR is mostly distributing existing commits across stacked branches.

## Lifecycle protocol

- **At PR creation** and **before marking ready for review**, apply the fission tests:
  - *The and-test*: if one plain title cannot cover every commit without "and", it is at least two PRs.
  - *The piggyback test*: any change that entered as "while we're at it" is a candidate layer.
- **When scope grows inside an open PR** (a piggyback lands), record it immediately in a "Piggybacks" ledger in the PR body, one line per item **stating the verdict**: "rides — must be understood with the feature: <reason>" or "separable — chop offered". The fission decision at ready-time then reads off the ledger instead of anyone's memory.
- When a test fires, **offer the chop** into a stack (mechanics below); the user decides. Layers split by "must be understood together", never by file type: a rule or doc whose evidence is the feature's code rides with the feature.
- Every PR body carries an "Architecture delta" section (root `architecture-delta` rule).
- When a goldfish reviews a PR touching `.agents/` or any `AGENTS.md`, the critic reads `.agents/skills/AGENTS.md` and the vendor guidelines it links before the diff.

## Stacks

GitHub-native stacked PRs (public preview since 2026-07): an ordered chain of branches where each PR targets the branch below it and shows reviewers only its own layer's diff.

### Facts

- The bottom branch targets the trunk (`main`); every other branch targets the one below.
- Merging the **top** PR merges the whole stack in one click. Merging a **mid-stack** PR merges it and everything below; PRs above stay open and auto-retarget the trunk, with remaining branches auto-rebased by GitHub.
- Squash, rebase, and merge-commit methods all work; stacks are merge-queue aware, and branch protections still apply.
- Limitations: all branches must live in the same repository (no cross-fork); not supported in GitHub Desktop.
- `gh stack` metadata lives in `.git/gh-stack` (local JSON, never committed); interrupted rebase state in `.git/gh-stack-rebase-state`.

### Command map (`gh stack`, official extension `github/gh-stack`)

Prerequisite: `gh extension install github/gh-stack` — official, but not bundled with `gh`.
`submit`, `push`, `sync`, `link`, and `merge` write to the remote: the root `no-push` rule applies — ask the user first.

- `init [branches...] [--base <trunk>]` — start a stack, or adopt existing branches listed bottom→top.
- `add <branch>` / `add -Am "<msg>"` — new layer on top; `-Am` stages, commits, and creates the branch in one step.
- `submit` — push all branches and create/update PRs with correct bases (opens an editor; `--auto` skips it but creates new PRs as drafts; `--open` marks them ready).
- `sync` — fetch, cascade-rebase, push, and prune merged layers; offers resolutions when local and remote stacks diverge.
- `rebase` — cascade-rebase after editing a lower layer; pauses on conflicts (`--continue` / `--abort`).
- `modify` — interactive restructure: reorder, fold, drop, insert, rename (needs a clean tree and linear history).
- `link` — declare a stack from existing PR numbers without local tracking.
- `merge` — all-or-nothing merge of the stack from the CLI.
- `view`, `up`/`down`/`top`/`bottom`/`trunk`, `checkout` — inspect and navigate.

### Recipes

- **Chop an oversized PR into a stack**: create layer branches off the trunk, distribute the existing commits bottom→top (entangled commits need re-slicing), `gh stack init <b1> <b2> …` to adopt them, then `gh stack submit` — it retargets the existing PR's base onto its new lower layer.
- **New layer on an existing stack**: `gh stack add <branch>`, commit, `gh stack submit`. Never `gh pr create` or a hand `git rebase --onto` inside a stack: the PR gets the right base but joins no stack, and the tracking desyncs — repair with `gh stack link <bottom> … <top>`.
- **Fix a lower layer**: `gh stack checkout <layer>`, commit, `gh stack rebase`, `gh stack push`.
- **After a partial merge**: `gh stack sync --prune`.
