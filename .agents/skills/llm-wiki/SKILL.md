---
name: llm-wiki
description: Build and maintain a persistent, LLM-maintained markdown wiki following Andrej Karpathy's LLM Wiki pattern — the agent incrementally compiles raw sources into an interlinked knowledge base instead of re-deriving answers from scratch. Use this whenever the user wants to ingest a source (an article, paper, transcript, chapter, meeting notes), file knowledge or conversation findings into the wiki, query the accumulated knowledge base, lint or health-check the wiki, or mentions "the wiki", "knowledge base", "ingest this", "file this", "what do we know about X", or accumulating notes on a topic over time — even if they don't say "LLM Wiki" explicitly.
---

# LLM Wiki

This skill instantiates [Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
The verbatim source of the idea is bundled at
[references/karpathy-llm-wiki.md](references/karpathy-llm-wiki.md) — read it in full
the first time you use this skill in a session, and whenever you need to make a
design decision the summary below doesn't cover. It is the authority; this file
is only the operational digest.

## The core idea

Instead of retrieving from raw documents on every question (RAG), the agent
**incrementally builds and maintains a persistent wiki**: a structured,
interlinked collection of markdown files sitting between the user and the raw
sources. Knowledge is compiled once and kept current, not re-derived per query.
The wiki is a compounding artifact: cross-references already exist,
contradictions are already flagged, the synthesis already reflects everything
read so far.

The human curates sources, directs the analysis, and asks the questions.
The agent does all the bookkeeping: summarizing, cross-referencing, filing,
updating, flagging contradictions. The human never (or rarely) writes wiki
pages by hand.

## The three layers

1. **Raw sources** — the curated collection of source documents. Immutable:
   read from them, never modify them.
2. **The wiki** — agent-generated markdown: entity pages, concept pages,
   source summaries, comparisons, an overview/synthesis. The agent owns this
   layer entirely.
3. **The schema** — the conventions document (this skill, plus whatever
   per-wiki conventions get written down alongside the wiki itself) that makes
   the agent a disciplined wiki maintainer instead of a generic chatbot. Evolve
   it with the user as the domain reveals what works.

## Operations

**Ingest** — a new source lands in the raw collection: read it, discuss key
takeaways with the user, write a summary page, update the index, update every
entity/concept page it touches (a single source may touch 10–15 pages), and
append a log entry. Prefer one source at a time with the user involved, unless
they ask for a batch.

**Query** — answer questions from the wiki: read `index.md` first to find
relevant pages, drill in, synthesize with citations to wiki pages. When an
answer is valuable — a comparison, an analysis, a discovered connection — file
it back into the wiki as a new page so explorations compound instead of
vanishing into chat history.

**Lint** — periodically health-check: contradictions between pages, claims
superseded by newer sources, orphan pages, concepts mentioned but lacking a
page, missing cross-references, data gaps worth a web search. Suggest new
questions and sources.

## Special files

- **`index.md`** — content catalog: every page with a link and one-line
  summary, organized by category. Update on every ingest; read first on every
  query. Works to ~hundreds of pages without any search infrastructure.
- **`log.md`** — append-only chronology of ingests/queries/lints. Start each
  entry with a consistent, grep-able prefix:
  `## [2026-04-02] ingest | Article Title`

## Conciseness

Conciseness is of utmost importance. The human's attention is the bottleneck:
wiki pages exist to be read fast, so write only what carries knowledge — no
filler, no restating what a linked page or the README already says.

## This repo's wiki

The wiki lives in `wiki/` at the repo top level and is committed to git.
Before writing anything into it, read `wiki/AGENTS.md` and honor its rules —
most importantly its content policy: the wiki holds knowledge about this
codebase and project only, never personal information about the user. Raw
sources, when the wiki needs them, go in `wiki/raw/` (immutable — read, never
modify). The special files `wiki/index.md` and `wiki/log.md` exist and must be
kept current as described above.

## Instantiating a wiki

The pattern is intentionally abstract — directory layout, page formats, and
tooling depend on the domain. When setting up a new wiki with the user, decide
together: where raw sources and wiki pages live, what page categories exist,
what frontmatter/tags to use, and which optional pieces (search tooling like
`qmd`, Obsidian integration, image handling, output formats like Marp decks)
are actually needed. Everything optional stays out until the need is real.
Record the decisions in the wiki's own schema/conventions file so future
sessions inherit them.
