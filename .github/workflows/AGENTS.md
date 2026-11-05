# Workflow guidance

Read [CI design](README.md) before changing workflows.

- **measure-first** — Inspect timestamped logs within steps before choosing an optimization. Compare equivalent work; separate controlled measurements from estimates and runner variation.
- **amortize-setup** — Remove repeated work before adding jobs, workers or caches. Overlap independent work when it shortens the workflow's longest dependent path after setup, downloads, extraction and cache publication; group short checks when separate setup costs more than it saves.
