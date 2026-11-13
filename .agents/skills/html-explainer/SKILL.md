---
name: html-explainer
description: Create or iterate on a standalone HTML explainer that visually teaches concepts to people. Use for explanatory HTML articles, not generic websites or inline chart-only responses.
---

Design a beautiful visual explanation for a human reader, not an HTML transcription of a document. Identify what the reader should understand, then build the narrative around visuals that explain relationships, mechanisms or comparisons: annotated diagrams, timelines, worked examples or interactive demonstrations. Use prose to connect and interpret them. Choose visuals for explanatory value, not decoration; keep implementation detail secondary and expandable.

Build a small working slice first and immediately open it in the user's side panel using the available preview tool (in Codex, open_in_codex with a browser target). Verify the local URL responds before opening it. Keep that preview current as sections are added; do not wait for the whole artifact or final QA. If opening is queued or unsupported, say so and provide the working link without claiming it is visible.

When a reference series is supplied, read the full series before choosing the narrative. Introduce concrete building blocks with inspectable numbers, then combine them; distinguish teaching examples from observations. Prefer a single editable HTML file for quick iteration. Keep initial polish proportional to the user's requested pace.

For explainers about an existing project, inspect its owning stylesheet, fonts, design tokens and a representative page before styling. Reuse that visual identity and CSS conventions unless the user requests another style; do not invent a parallel palette.

Adapt source material to the visual narrative rather than mechanically porting Markdown. Preserve meaning and state: render checklists with semantic checkbox controls and explicit labels, keeping completed and pending items distinct. Make read-only status non-interactive; do not imply that changes persist unless they do.

Inspect the rendered result against the design reference, including narrow layouts, diagrams and control states. Verify that the visuals teach the main concept and that checkboxes and other interactions behave as labelled. If browser inspection is unavailable, report visual verification as incomplete; source inspection alone does not establish rendering quality.
