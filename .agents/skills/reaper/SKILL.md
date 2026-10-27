---
name: reaper
description: Finds and deletes unnecessary code, explainers, wiki content and agent instructions, delivers reviewed cleanup PRs, and improves its search methods from observed outcomes. Use for Reaper or a deliberate deletion sweep.
---

# Reaper

Reduce maintenance burden per unit of effort. Prefer removing a whole unnecessary
thing over polishing its parts; do not optimize for deleted line counts.

## Hunt and delete

- Work within the requested scope and budget. If unspecified, choose one bounded
  area for the first pass. Inspect existing work before editing; use an isolated
  branch or worktree when needed. Do not reap another agent's unfinished work.
- Read relevant prior outcomes in `wiki/rule-provenance.md`. Search cheaply for
  abandoned code, superseded explainers, completed specs and repeated knowledge.
  Investigate the strongest candidates first; age and absent references are clues,
  not sufficient reasons to delete.
- For code, trace callers, public entry points, configuration and indirect use.
  For prose, identify its remaining purpose and unique knowledge. Preserve useful
  knowledge in its canonical home before removing a duplicate. Honor local
  protections, including immutable raw sources.
- Delete coherent units and repair their references. If a generator or workflow
  recreates the waste, fix that source within scope or report it as follow-up.
  Verify affected behavior, links and rendered content as appropriate.
- Stop at the budget, when a coherent cleanup is ready, or when further hunting
  offers little likely value. Report a no-op honestly; do not manufacture deletions.

## Deliver and review

- Use the `pull-request` skill to open a draft cleanup PR. State what lost its
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

- Record consequential outcomes in `wiki/rule-provenance.md`: the search method,
  evidence of useful yield or wasted effort, false positives, and later restorations
  when known. Link the cleanup PR; do not create a second deletion ledger.
- Use these outcomes to change search order and remove ineffective instructions,
  including Reaper's own. Add or strengthen instructions only under the repository's
  ablation rule; do not infer success solely from passing checks or a quiet review.
- Include justified skill changes in the reviewed diff. Add reusable scripts only
  when repeated use demonstrates that they save effort. Do not expand deletion
  authority or weaken review requirements as a self-improvement.
