---
name: mermaid
description: Use when writing or editing a Mermaid diagram in Markdown rendered by GitHub (wiki pages, specs, PR bodies): keeps it readable in light and dark themes and stops labels from being swallowed.
---

# Mermaid diagrams

GitHub renders Mermaid in the viewer's theme and picks the palette itself. Let it.

- **No `theme` in an `%%{init}%%` block.** It switches the theme sync off and one mode goes unreadable.
- **No colour unless it carries meaning.** Shapes carry roles: cylinders for external sources and stores, plain boxes for transforms and artifacts.
- **A `fill` always comes with a `color`.** A fill alone takes the theme's text colour. Prefer mid-tone fills or stroke-only styling; hex values only; check both modes before pushing.
- **The one sanctioned class is `planned`**: `classDef planned stroke-dasharray: 5 5,stroke:#888,color:#888,fill:none`, used for dashed planned parts of the architecture graph (root rule `architecture-delta`).
- **No `<x>` placeholders or HTML entities in labels.** They are parsed as tags and vanish. Write `‹x›`.
- **Wide diagrams go `flowchart LR`; long chains `TB`.** Labels use `<br/>` for a second line.
