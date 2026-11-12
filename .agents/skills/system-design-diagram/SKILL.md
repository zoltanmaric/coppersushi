---
name: system-design-diagram
description: Creates or revises README system-design diagrams at service and component level, with Mermaid and links to code ownership. Use for architecture overviews or simplifying a diagram that mixes abstraction levels.
---

# System design diagram

Establish the product boundary and revision to describe. Read its owning architecture
document and implementation; for a PR stack, inspect the cumulative implementation
at the requested tip.

Trace the main user journeys and background data paths. Draw the clients, services,
external systems and stores needed to explain them. Keep build-time preparation,
scheduled production and request-time serving distinguishable.

Choose boxes by responsibility and meaningful interfaces. Collapse internal files,
models, validation steps, caches and rendering effects into their owning component
unless their separation changes how the system works. Retain a store, queue or
cache when it explains a persistence, delivery or asynchronous boundary. Do not
invent distributed services to make the picture look like a system-design interview.

Put the whole-system overview in the root README. Label boxes with their role and
essential technology; label arrows with the request, data or trigger they carry.
Use brief text below the diagram for the few behaviors the picture cannot convey.

Give each owned component a folder README when its internal architecture needs
explaining. Expand only that component, preserving the parent diagram's interfaces.
Link parent and child READMEs in both directions and link collaborating components.
Make diagram nodes clickable with absolute GitHub links to component READMEs on
the default branch (GitHub renders Mermaid in an iframe); provide a
normal Markdown ownership list as a fallback and verify links in the rendered view.
Keep each architectural fact in its owning README; link to the wiki for domain
knowledge and decisions instead of copying them. Do not create empty component
pages or a diagram for every utility folder.

Update the affected parent and component diagrams in the implementation PR that
changes their boundaries or data paths. Describe that revision's implemented
system. Keep proposed dataflows in their spec until implemented.

Use the Mermaid skill for GitHub Markdown. Render the first working slice early,
then inspect it at README width. Shorten labels, combine internal steps or change
layout when readers must zoom to follow the main paths. Check arrows against the
implementation.

Generate the PR's Architecture delta section from committed README diagrams with
`python .agents/skills/system-design-diagram/scripts/architecture_delta.py --base <pr-base> --head <pr-head>`.
Use the PR's immediate base branch for a stack. Review the generated before/after
Mermaid blocks and replace the existing section, preserving the rest of the PR body.
The script reads Git only and prints Markdown; it does not publish or edit files.
Explain code architecture changes separately if the diagrams do not capture them;
unchanged diagrams alone do not prove there was no architecture change.
