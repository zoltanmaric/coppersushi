---
name: goldfish
description: Review a design artifact (spec, plan, PR packet) with fresh, memoryless subagents. Invoke when the user asks — "goldfish this", "fresh eyes", "tear this apart" — or after suggesting it for a spec that has grown load-bearing and the user agrees.
---

# goldfish — fresh-context review

Intent: an artifact written in a context-rich session always reads complete *to that
session*. The test is whether a reader with zero session context can act on it.

A goldfish is a fresh subagent given only the artifact plus what any fresh context can
legitimately reach: the repo, the wiki, linked sources. Session context is out of
bounds — don't paste in your intent or the answer you hope for.

Facets — a menu, not a mandate; pick by stakes. Run the deleter before critic and
readiness: optimizing a thing that shouldn't exist is the classic mistake.

1. **Requirement deleter** — whole before parts: should this task exist at all? Is it
   the right question? Only then: which individual requirements can be cut?
2. **Comprehension** — can you explain the goal and the touched system from what you
   can read?
3. **Simplifier** — of what survives, is there a simpler approach?
4. **Critic** — assume defects exist; verify claims against reality (open the code, run
   the command), not against the artifact's account of it.
5. **Readiness** — does this contain what the next action needs? Missing implementation
   detail is NOT a finding.

Sandbox (non-negotiable): reviewers never mutate a checkout they don't own. Read-only
subagents by default; a reviewer that must build or run gets its own disposable worktree.

Exit: findings filtered by you — a finding survives if acting on it would change what
gets built or what risk is visible. Done when a fresh reader can act on the artifact
without rediscovering intent. If substantive findings persist after a couple of rounds,
the artifact needs rethinking, not more polish.
