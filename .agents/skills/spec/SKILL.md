---
name: spec
description: Maintain a concise HTML explainer spec as the working memory of a large or multi-session task. Use when work spans sessions, when the user asks for a spec or brief, or when a grill ends on a task too big to carry in a confirmed summary alone.
---

# spec — a task-scoped HTML explainer

Maintain one authoritative HTML explainer in top-level `specs/` for the task’s
remaining intent. Commit it for review. Do not create Markdown specs, parallel
copies, or specs in the wiki. Use the repository’s [html-explainer skill](../html-explainer/SKILL.md) for visual
teaching, project styling and rendered verification.

Lead with a short overview; put necessary implementation contracts in linked or
expandable detail. Preserve enough context for a fresh agent to act with the repo.
Suggested shape:

- **Problem** — a few sentences.
- **Approach** — including rejected alternatives, with reasons.
- **Acceptance criteria** — as runnable checks where possible. This is the load-bearing
  section: how will both of us know it's done?

Distinguish the verified baseline, agreed changes and parked ideas. Deferred ideas
do not enter implementation steps or completion criteria.

Guardrails:

- Link to owning READMEs and wiki pages rather than copying their facts.
- Reconcile with current code before handoff; remove work already landed and verified.
- Keep agreed boundaries and acceptance criteria explicit; detail near-term work and
  re-plan later steps as implementation changes what remains.

When acceptance criteria pass, move lasting architecture and operating facts to
their owning READMEs, domain knowledge and decisions to the wiki, then delete the
completed spec. Git keeps its history.
