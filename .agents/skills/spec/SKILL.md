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

- Lives in `specs/` (gitignored). Never lands on main; committing one into a PR branch
  is an explicit opt-in, and it still dies before merge.
- Link to the wiki rather than restating it — divergent copies rot.
- Burn it down: as pieces land and verify, delete them from the spec.

Exit: when the acceptance criteria verify, offer to distill anything worth keeping into
the wiki (the llm-wiki skill decides what and in what shape), then delete the file.
A leftover file in `specs/` is a visible signal of an unfinished task.
