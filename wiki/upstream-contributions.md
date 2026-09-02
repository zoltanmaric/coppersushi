# Upstream contributions — candidates and record

Bugs and gaps in dependencies that this project needs fixed. Fix locally when the deadline demands; upstream when the fix is small and clearly scoped. Precedent: the 2022 fork's ERA5/ERA5T workaround became atlite [#261](https://github.com/PyPSA/atlite/pull/261), and the solar time shift atlite [#257](https://github.com/PyPSA/atlite/pull/257).

| Project | Need | Status | Notes |
|---|---|---|---|
| entsoe-py | `query_generation_per_plant` broken since an API change ([#480](https://github.com/EnergieID/entsoe-py/issues/480), open since 2025-11) | Candidate | Decide at point of contact: if the fix is a few lines in request or parser, patch a local checkout, pin to it, open the PR the same day; if the raw XML is needed anyway, keep a local parser and skip upstreaming. |
| entsoe-py | EIC column level silently dropped for single-unit windows ([#534](https://github.com/EnergieID/entsoe-py/pull/534), open PR) | Watch | `include_eic=True` otherwise works; guard against the edge case locally until merged. |
| PyPSA-Eur | Hindcast mode: fix reported units (16.1.A) to measured output, scale renewable availability to zonal actuals (16.1.B) | Candidate, post-demo | Extends upstream's validation track (`config/examples/config.validation.yaml`, `doc/validation.md`). Build it upstream-shaped in the fork (own rule + script, config under `electricity:`); open an upstream issue early to gauge interest. |
| PyPSA-Eur | `add_electricity.py` reindexes monthly fuel prices onto snapshots and forward-fills: a window not starting on a month boundary gets all-NaN marginal costs | Candidate | Small fix (`reindex(method='ffill')` or resample first). Verified in upstream `563f22f6`. |
| PyPSA-Eur | `data/nuclear_p_max_pu.csv` ends 2024; a later year raises `KeyError` past the `except (ValueError, TypeError)` in `add_electricity.py` | Candidate | Data extension plus a graceful fallback. Blocks any 2025/26 run. |
