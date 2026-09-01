---
name: pull-request
description: Use when splitting work into stacked pull requests or managing an existing stack — creating layers, restacking after changes, merging.
---

# Pull request stacks

GitHub-native stacked PRs (public preview since 2026-07): an ordered chain of branches where each PR targets the branch below it and shows reviewers only its own layer's diff.

## Facts

- The bottom branch targets the trunk (`main`); every other branch targets the one below.
- Merging the **top** PR merges the whole stack in one click. Merging a **mid-stack** PR merges it and everything below; PRs above stay open and auto-retarget the trunk, with remaining branches auto-rebased by GitHub.
- Squash, rebase, and merge-commit methods all work; stacks are merge-queue aware, and branch protections still apply.
- Limitations: all branches must live in the same repository (no cross-fork); not supported in GitHub Desktop.
- `gh stack` metadata lives in `.git/gh-stack` (local JSON, never committed); interrupted rebase state in `.git/gh-stack-rebase-state`.

## Command map (`gh stack`, official extension `github/gh-stack`)

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

## Recipes

- **Chop an oversized PR into a stack**: create layer branches off the trunk, distribute the existing commits bottom→top (atomic commits are the pre-cut fault lines; entangled commits need re-slicing), `gh stack init <b1> <b2> …` to adopt them, then `gh stack submit` — it retargets the existing PR's base onto its new lower layer.
- **Fix a lower layer**: `gh stack checkout <layer>`, commit, `gh stack rebase`, `gh stack push`.
- **After a partial merge**: `gh stack sync --prune`.

Every layer's PR body still carries its own "Architecture delta" section per the root `AGENTS.md` rule.
