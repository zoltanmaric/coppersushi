---
name: spec
description: Maintain a concise burn-down spec as the working memory of a large or multi-session task. Use when work spans sessions, when the user asks for a spec or brief, or when a grill ends on a task too big to carry in a confirmed summary alone.
---

# spec — a task-scoped burn-down file

Keep one authoritative artifact for the task’s remaining intent. Use the requested
format; an HTML explainer can be the spec without a parallel Markdown copy.

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

- Two homes, chosen by weight. Default: `specs/` (gitignored, dies with the task,
  never lands on main). A spec big enough that its burn-down history or surviving
  slivers have long-term value lives in `wiki/specs/` instead — committed, and listed
  in the wiki index under a separate "Specs (working memory)" section so queries never
  mistake burn-down state for settled knowledge.
- Link to owning READMEs and wiki pages rather than copying their facts.
- Reconcile with current code before handoff; remove work already landed and verified.
- Keep agreed boundaries and acceptance criteria explicit; detail near-term work and
  re-plan later steps as implementation changes what remains.

When acceptance criteria pass, move lasting architecture and operating facts to
their owning READMEs, domain knowledge and decisions to the wiki, then delete the
completed spec. Git keeps its history.
