---
name: llm-wiki
description: Recalls and records project knowledge from research, literature, online posts and technical investigations, including when the user does not mention the wiki. Also handles explicit ingest, query and wiki maintenance requests.
---

# LLM Wiki

## Recall

Read `wiki/index.md`, then relevant pages before investigating the topic.
Use their source links and unresolved questions to continue from existing knowledge.
Verify time-sensitive claims against current evidence; stored knowledge can be stale.

## Record

Before answering with new project findings, read `wiki/AGENTS.md` and reconcile
those findings into the existing page that owns them. Save substantive corrections,
source-backed conclusions and settled decisions without asking whether to file them.
If nothing new was learned, leave the wiki unchanged.

Cite the original public source with its date or edition and relevant section.
For online posts, retain the author, date and direct link; attribute opinions and
claims rather than presenting them as established facts. Preserve uncertainty and
contradictions. Apply the wiki content policy to proposals and research records.

Prefer updating an existing page over creating one. For a new literature digest,
follow `wiki/literature/AGENTS.md`; link it from the concept page that uses it.
Keep facts in their owning page and link rather than repeat them. Follow the root
`information-home` rule for README responsibilities and task specs.

Update `wiki/index.md` when its catalog changes. Append changes in understanding
to `wiki/log.md` using `## [YYYY-MM-DD] ingest | Topic` (or `query`, `lint`,
`decision`). Link the owning page rather than duplicating its findings in the log.
Briefly link the updated page in the answer. If writing is blocked, report the
unsaved finding and the blocker rather than implying it was recorded.

## Maintain

When asked to lint or maintain the wiki, check stale claims, contradictions,
missing source links, duplicate facts and orphan pages. Reconcile against evidence;
keep suggested future investigations in the conversation.

Read [the LLM Wiki pattern](references/karpathy-llm-wiki.md) when making schema
changes. Keep any existing `wiki/raw/` sources immutable; literature digests link
to originals rather than copying them.
