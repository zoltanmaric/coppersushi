---
name: spec
description: Maintain a one-page burn-down spec as the working memory of a large or multi-session task. Use when work spans sessions, when the user asks for a spec or brief, or when a grill ends on a task too big to carry in a confirmed summary alone.
---

# spec — a task-scoped burn-down file

Intent: one markdown file holding the task's *remaining* intent, so any fresh session
re-bootstraps by reading it. It is working memory, not documentation.

Shape (suggested, not enforced), hard cap ~1 page:

- **Problem** — a few sentences.
- **Approach** — including rejected alternatives, with reasons.
- **Acceptance criteria** — as runnable checks where possible. This is the load-bearing
  section: how will both of us know it's done?

No file-by-file implementation plan — that lives in the working session and dies with it.

Guardrails:

- Two homes, chosen by weight. Default: `specs/` (gitignored, dies with the task,
  never lands on main). A spec big enough that its burn-down history or surviving
  slivers have long-term value lives in `wiki/specs/` instead — committed, and listed
  in the wiki index under a separate "Specs (working memory)" section so queries never
  mistake burn-down state for settled knowledge.
- Link to the wiki rather than restating it — divergent copies rot.
- Burn it down: as pieces land and verify, delete them from the spec.

Exit: when the acceptance criteria verify, distill anything worth keeping into the
wiki (the llm-wiki skill decides what and in what shape), then delete the spec file —
git keeps the history; a wiki-resident sliver may survive as (or merge into) a durable
page. A leftover spec is a visible signal of an unfinished task.
