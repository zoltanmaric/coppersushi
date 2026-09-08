---
name: mermaid
description: Guides writing and editing Mermaid diagrams in GitHub-rendered Markdown so they remain readable across themes and preserve placeholder labels.
---

# Mermaid diagrams

- Leave Mermaid's `theme` unset, including in frontmatter and `%%{init}%%`.
- Pair every explicit non-transparent `fill` with a contrasting `color`; inspect both GitHub themes.
- Write placeholders as `‹x›`, not `<x>` or `&lt;x&gt;`.
