---
name: spec
description: Creates and maintains beautiful, wiki-backed HTML spec explainers for human review before implementation. Use when the user asks for a spec or brief, work spans sessions, or a grill establishes a task needing a spec.
---

# Spec explainers

1. Establish the reader's question, intended experience, scope and unresolved decisions. Read the owning wiki pages before proposing changes.
2. Create the actual review artifact at `explainers/<topic>.html`. Make it a carefully designed explanation with clear typography, visual hierarchy, diagrams and examples suited to the subject. Do not substitute a Markdown page or a prose dump inside an HTML wrapper.
3. Explain the problem, proposed experience, reasoning and acceptance criteria. For a computational pipeline, show meaningful connected stages and explain where inputs come from, what each transformation does and means, and how its output is used. Configuration and provenance support that explanation.
4. Prefer standalone, offline HTML with embedded CSS and SVG; add JavaScript only where interaction teaches something. Keep core explanatory text readable without JavaScript. Choose the presentation for the subject rather than forcing a fixed template.
5. Link to the wiki for durable knowledge and decisions. Show source revisions, date, limitations, open choices and review status. Clearly label illustrative data and proposed behaviour.
6. Inspect the rendered page at desktop and narrow widths, exercise interactions and source links, and independently check numerical examples. Have a fresh-context reviewer assess whether the intended reader can understand the proposal without the author's explanation. Fix material comprehension barriers without expanding the agreed scope; disclose unavailable checks.
7. Present the HTML artifact for human review and wait for approval before implementing the proposed product changes. A reviewer-agent verdict does not replace human approval. Re-present material changes to the agreed direction before implementing them.
8. Keep the explainer aligned with accepted decisions and implementation status. Commit the HTML itself with the relevant work. Keep transient task bookkeeping in ignored `specs/` when useful; it does not replace the review artifact. Preserve durable knowledge in the wiki and revise or retire obsolete explainers; git is the archive.
