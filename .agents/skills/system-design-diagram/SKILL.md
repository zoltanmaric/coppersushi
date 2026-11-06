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

Map owned components to existing folders with links. Treat one component per folder
as an ownership goal, not permission to reorganize code. When component detail is
requested, put it in that folder's README and expand only that component, preserving
its parent diagram's external interfaces. Keep the parent readable without opening it.

Use the Mermaid skill for GitHub Markdown. Render the first working slice early,
then inspect it at README width. Shorten labels, combine internal steps or change
layout when readers must zoom to follow the main paths. Check arrows against the
implementation and distinguish any explicitly requested plans from implemented parts.
