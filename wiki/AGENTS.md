# Wiki Guidelines

- **codebase-only** — Codebase knowledge only — never personal information. This wiki documents the Copper Sushi codebase and project: its architecture, history, design decisions, dependencies, domain concepts, and plans *for the codebase*. Never file personal information about the user or their personal plans and activities into the wiki, even when they come up in conversation while working on the project. If a conversation mixes both, distill only the codebase-relevant knowledge.

- **agent-owned** — The agent owns this folder. Wiki pages are written and maintained by the agent following the `llm-wiki` skill — keep `index.md` (content catalog) and `log.md` (append-only chronology) current. The log chronicles changes in *understanding* (ingests, queries, lints, decisions), never changes in repository state: pages that mirror the code — spec burn-downs, the implemented dataflow graph — update without log entries, because git is already their chronology.

- **name-mystery** — Never explain the project's name prominently. The mystery is part of the intrigue: no etymology in the README, the wiki index, or the app itself. A discreet note deep in a wiki page is acceptable.

- **what-is** — Pages state what is. What was, what changed and why live in `log.md` and git — no "scrapped", "formerly" or "superseded" narratives on pages. Spell out acronyms on first use.
