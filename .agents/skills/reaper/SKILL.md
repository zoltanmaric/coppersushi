---
name: reaper
description: Finds and deletes unnecessary code, tests, explainers, wiki content, agent instructions and abandoned worktrees, delivers reviewed cleanup PRs, and improves its search methods from observed outcomes. Use for Reaper, a deliberate deletion sweep, or deletion discovery during PR review.
---

# Reaper

Reduce maintenance burden per unit of effort. Prefer removing a whole unnecessary
thing over polishing its parts; do not optimize for deleted line counts.

## Choose the workflow

When called from another workflow, run **Discover** within the caller's scope and
return candidates; let the caller choose reporting, edits or cleanup PRs within
its authorization. Do not start standalone delivery or worktree cleanup implicitly.
For a standalone sweep, discover, execute, deliver and review, then improve from use.

## Discover

- Work within the requested scope and budget. If unspecified, choose one bounded
  area for the first pass. Inspect existing work and ownership; do not propose
  reaping another agent's unfinished work.
- Read relevant prior outcomes in `wiki/rule-provenance.md`. Search cheaply for
  abandoned code, superseded explainers, completed or obsolete specs and repeated knowledge.
  Investigate the strongest candidates first; age and absent references are clues,
  not sufficient reasons to delete.
- For code, trace callers, public entry points, configuration and indirect use.
  For prose, identify its remaining purpose and unique knowledge. Identify useful
  knowledge that must move to its canonical home before removing a duplicate. Honor local
  protections, including immutable raw sources. Route agent procedures and task-local
  steps according to `information-home`; do not preserve expired instructions as
  wiki knowledge merely because they were unique to the deleted artifact.
- For unfinished specs, compare their assumptions and intended outcome with later
  decisions and implemented behavior. Open checkboxes do not establish continuing
  value. Propose deletion when the direction is obsolete; if remaining intent is
  unclear, ask whether it is still wanted rather than carrying it forward by default.
- For tests, identify the meaningful failure each catches. Scrutinize tests that
  mirror implementation, assert incidental details or duplicate coverage. Propose deleting
  tests without a useful purpose or simplifying setup and assertions while preserving
  valuable regression checks. Explain what protection remains or is deliberately
  retired; a passing reduced suite alone does not establish adequate coverage.
- Return concrete candidates with evidence, remaining users or knowledge, required
  reference repairs and checks. Separate supported deletions from unresolved intent
  questions. Identify generators or workflows that would recreate the waste.
- Stop at the budget, when a coherent cleanup is identified, or when further hunting
  offers little likely value. Report a no-op honestly; do not manufacture deletions.

## Execute

- Use the caller's chosen delivery route; for standalone sweeps, use a cleanup PR.
  Inspect existing changes and isolate conflicting work before editing. Delete
  coherent units, preserve identified knowledge and repair references. Fix generators
  within scope or report follow-up. Verify affected behavior, links and rendered content.
- Have an independent agent review implemented cleanup, including cleanup made by
  a reviewer. Follow **Deliver and review** for that check without requiring a new PR
  when the caller chose edits to an existing one.

## Worktrees

- When worktrees are in scope, inventory them and check owning chat/agent activity, running jobs, PR state,
  uncommitted and untracked work, unpushed commits and valuable ignored files.
  Treat age or a merged branch as a lead, not proof of abandonment; leave uncertain
  ownership for clarification. Exclude the active checkout and primary worktree.
- Have the review agent check proposed cleanup and recovery evidence before acting.
  Ensure unique work is recoverable, including needed ignored files that archive
  snapshots omit. Prefer the host's recoverable archive operation for managed
  worktrees; use normal Git removal for others. Do not force removal to bypass
  unexplained state. Verify archival/removal succeeded.
- Keep local paths and recovery details in chat, not the public PR. Describe the
  proposed operation and review outcome alongside the PR; distinguish that operation
  from its Git diff. During discovery validation, defer archival until the evaluator
  accepts the result so fresh runs can inspect the same worktrees.

## Deliver and review

- For a standalone sweep, use the `pull-request` skill to open a draft cleanup PR. State what lost its
  purpose, the supporting evidence and the checks performed.
- Have an independent review agent inspect the actual diff and surrounding repo,
  with the requested scope and verification results. Ask it to look for lost
  behavior or knowledge, missed indirect users, broken references and unsupported
  deletion claims. Require concrete findings; no findings is a valid result.
- Address findings and have the reviewer check the revised diff when fixes change
  its conclusions. Keep the PR draft if material questions remain or independent
  review is unavailable. Mark ready only after verification and review; report
  their limits and leave merging to the user. Keep agent findings in chat unless
  posting review comments is explicitly authorized.

## Improve from use

- Validate discovery with fresh runs from the skill and the same scope, without
  prior candidate lists or hoped-for deletions in the agent's context. Keep expected
  targets with the evaluator; compare them with the result afterward. Improve the
  general method and rerun from the same baseline rather than coaching the cleanup
  agent toward individual targets. Keep correctness fixes from review distinct from
  evidence that Reaper discovered something independently.

- Record consequential outcomes in `wiki/rule-provenance.md`: the search method,
  evidence of useful yield or wasted effort, false positives, and later restorations
  when known. Link the cleanup PR; do not create a second deletion ledger.
- Use these outcomes to change search order and remove ineffective instructions,
  including Reaper's own. Add or strengthen instructions only under the repository's
  ablation rule; do not infer success solely from passing checks or a quiet review.
- Include justified skill changes in the reviewed diff. Add reusable scripts only
  when repeated use demonstrates that they save effort. Do not expand deletion
  authority or weaken review requirements as a self-improvement.
