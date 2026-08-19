---
name: grill
description: Interrogate the user before implementing a non-trivial or ambiguous ask, converging on shared intent. Use when the user says "grill me", when an ask admits multiple interpretations, or before any sizable piece of work whose intent isn't fully clear.
---

# grill — converge on intent before work

Intent: an agent that implements a half-understood ask wastes the user's time twice.
The deliverable of this skill is shared understanding, not code.

**Question zero — is this the right question?** Verdicts:

1. **Wrong question** — the ask, even done perfectly, wouldn't serve the actual goal.
   Stop, name the underlying problem, propose the question that would serve it.
2. **Right problem, misaimed ask** — the goal is sound but the requirement overshoots,
   undershoots, or aims at a symptom. Adjust it and confirm the adjusted version.
3. **Right question** — proceed silently.

An honest "this smells wrong because X, though I don't have a better formulation" is a
legitimate report.

Guardrails:

- One question at a time. Challenge, don't validate — your value is pressure-testing
  the user's judgment, not agreeing with it.
- Check the wiki first (llm-wiki skill) so settled decisions aren't re-litigated.
- No code yet. Scale depth to ambiguity: a nearly-clear ask needs one question or none.

Exit: a compact "here's what I understood — confirm" summary. For most tasks that
confirmed summary IS the spec — work from it directly. If the task looks large or
multi-session, offer the spec skill; create the file without asking when obviously needed.
