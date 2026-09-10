# Wiki Guidelines

- **codebase-only** — Codebase knowledge only — never personal information. This wiki documents the Copper Sushi codebase and project: its architecture, history, design decisions, dependencies, domain concepts, and plans *for the codebase*. Never file personal information about the user or their personal plans and activities into the wiki, even when they come up in conversation while working on the project. If a conversation mixes both, distill only the codebase-relevant knowledge.

- **agent-owned** — The agent owns this folder. Wiki pages are written and maintained by the agent following the `llm-wiki` skill — keep `index.md` (content catalog) and `log.md` (append-only chronology) current. The log chronicles changes in *understanding* (ingests, queries, lints, decisions), never changes in repository state: pages that mirror the code — spec burn-downs, the implemented dataflow graph — update without log entries, because git is already their chronology.

- **name-mystery** — Never explain the project's name prominently. The mystery is part of the intrigue: no etymology in the README, the wiki index, or the app itself. A discreet note deep in a wiki page is acceptable.

- **page-names** — Name a page so a reader who has forgotten the project knows what it is from the file name alone: the domain's own term for the thing, or a specific noun phrase, never a string of generic words. Rename when a name proves unclear; git keeps the history.

- **relative-time** — No relative time — "today", "currently", "recently", "soon" — anchor it: "as of 2026-09-08" (Wikipedia's [MOS:RELTIME](https://en.wikipedia.org/wiki/Wikipedia:Manual_of_Style/Words_to_watch#Relative_time_references)).

- **term-anchors** — Define a domain term once, under its own `###` heading on the page that owns it, and link that heading from every other page at the term's first use, expansion in the link text. Every heading another page links is one token: the domain's acronym or identifier where it has one (`D2CF`, `GSK`), one short word (`Binding`), or hyphenated words otherwise (`Net-position`, `Fork-refs`); the link uses its exact lowercase text. GitHub resolves a heading's lowercase slug while Obsidian matches its text ignoring case, so this is the one form both accept. A gloss repeated on a second page is a copy that rots.

- **what-is** — Pages state what is. What was, what changed and why live in `log.md` and git — no "scrapped", "formerly" or "superseded" narratives on pages. Spell out acronyms on first use.
