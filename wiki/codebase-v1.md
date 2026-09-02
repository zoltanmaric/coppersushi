# Codebase v1 — architecture & state

Dash/Plotly app, ~400 lines of Python across three modules. Written 2022, modernized to 2026 deps in Aug 2026 (green tests, working app). Being superseded **in place** by [Copper Sushi 2](sushi-2.md); this v1 state is preserved as the `v1` GitHub release.

## Structure

- `app.py` — Dash app: loads one solved PyPSA network (`networks/*.nc`), builds the full figure at startup, snapshot slider toggles trace visibility.
- `scripts/plot_power_flow.py` — builds the map figure: 4 traces per snapshot (nodes, loaded lines >99%, easy lines, direction triangles at geodesic branch midpoints via pyproj). Node color/size = net power, IQR-clamped colorscale. Also supports coloring by load/generation/marginal price (never exposed in UI).
- `scripts/network_snapshot.py` — extracts per-snapshot bus/load/generator DataFrames, joins static + time-varying quantities.

## Known weaknesses (v2 targets)

- **All-snapshots-precomputed mega-figure**: 12 × 4 traces built eagerly and shipped to the browser at once → ~10s+ first paint; `NUM_TRACES_PER_SNAPSHOT` coupling is brittle.
- **Map engine** (measured 2026-09-01): plotly deprecates its Mapbox integration, not Mapbox. Its MapLibre path (`Scattermap`) blocks the browser's main thread for >45 s on first render for *both* v1 (3.5k nodes, 48 traces) and the OSM topology (10k segments, 4 traces), then runs at ~61 fps; the Mapbox path renders the same figures instantly. Token-free Carto Dark Matter also looks flat next to Mapbox Dark. So: stay on `Scattermapbox` with plotly pinned (drift costs occasional one-liners, e.g. plotly.js 3 dropped `mapbox` from default `scrollZoom`). The keep-the-look, WebGL-fast exit is deck.gl (pydeck / dash-deck) on the Mapbox Dark basemap: trace builders rewritten as layers, data prep reusable.
- Chained-assignment warnings remain in `network_snapshot.py` under pandas Copy-on-Write.

## Lineage

- 2022: built on PyPSA-Eur output; deployed via Docker/gunicorn to Heroku, embedded at 121gigawatts.org.
- Oct 2022: forked as *milkshake* (load-siting tool: add a load at a bus, re-solve, paint the line-flow diff on this map — violet = increased, mint = decreased). Scenario diffing proved valuable and is a v2 feature candidate.
- Aug 2026: dead code purged; pandas/Plotly/Dash API drift fixed (`fillna` CoW no-op, `ColorBar.titleside`, `app.run_server`).
