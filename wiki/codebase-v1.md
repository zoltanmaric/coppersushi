# Codebase v1 — architecture & state

Dash/Plotly app, ~400 lines of Python across three modules. Written 2022, modernized to 2026 deps in Aug 2026 (green tests, working app). A ground-up **v2 rewrite is planned** in a `v2/` folder, to eventually replace v1.

## Structure

- `app.py` — Dash app: loads one solved PyPSA network (`networks/*.nc`), builds the full figure at startup, snapshot slider toggles trace visibility.
- `scripts/plot_power_flow.py` — builds the map figure: 4 traces per snapshot (nodes, loaded lines >99%, easy lines, direction triangles at geodesic branch midpoints via pyproj). Node color/size = net power, IQR-clamped colorscale. Also supports coloring by load/generation/marginal price (never exposed in UI).
- `scripts/network_snapshot.py` — extracts per-snapshot bus/load/generator DataFrames, joins static + time-varying quantities.

## Known weaknesses (v2 targets)

- **All-snapshots-precomputed mega-figure**: 12 × 4 traces built eagerly and shipped to the browser at once → ~10s+ first paint; `NUM_TRACES_PER_SNAPSHOT` coupling is brittle.
- `Scattermapbox` is deprecated → MapLibre-based `Scattermap` would drop the Mapbox token requirement.
- Chained-assignment warnings remain in `network_snapshot.py` under pandas Copy-on-Write.

## Lineage

- 2022: built on PyPSA-Eur output; deployed via Docker/gunicorn to Heroku, embedded at 121gigawatts.org.
- Oct 2022: forked as *milkshake* (load-siting tool: add a load at a bus, re-solve, paint the line-flow diff on this map — violet = increased, mint = decreased). Scenario diffing proved valuable and is a v2 feature candidate.
- Aug 2026: dead code purged; pandas/Plotly/Dash API drift fixed (`fillna` CoW no-op, `ColorBar.titleside`, `app.run_server`).
