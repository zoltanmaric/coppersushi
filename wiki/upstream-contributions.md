# Upstream contributions — candidates and record

Bugs and gaps in dependencies that this project needs fixed. Fix locally when the deadline demands; upstream when the fix is small and clearly scoped. Precedent: the 2022 fork's ERA5/ERA5T workaround became atlite [#261](https://github.com/PyPSA/atlite/pull/261), and the solar time shift atlite [#257](https://github.com/PyPSA/atlite/pull/257).

## How we contribute

**Rehearse on the fork, publish from the same branch.** Each fix is one branch off upstream `master` in the sibling checkout, opened as a PR on the fork (`zoltanmaric/pypsa-eur`, base `master`, which mirrors upstream) for our own review — invisible upstream, never merged there. When approved, the upstream PR is opened from the same branch and the rehearsal PR is closed with a link. Issue and PR texts iterate as markdown in the gitignored `specs/upstream/` (one file per contribution: issue, PR title and body, release-note line). Our pin points at an integration branch that merges the fix branches until they land upstream.

**Before a PR, comment on the issue.** If an issue exists, say in prose what shape of fix you have and ask whether it is welcome; PyPSA-Eur asks for this ("let us know by opening an issue or a draft PR") and it costs a paragraph. Search issues by symptom *and* by mechanism — the first search here missed #2262 and #2192.

**PyPSA-Eur's rules** ([contributing](https://github.com/PyPSA/pypsa-eur/blob/master/doc/contributing.md), [PR template](https://github.com/PyPSA/pypsa-eur/blob/master/.github/pull_request_template.md)):
- AI-assisted contributions are allowed, but descriptions must read as written by the human, concise; any AI-generated text goes in a collapsed `<details>` block, never mixed with the prose. The author takes responsibility for content and quality. Code kept simple; one focused fix per PR; large contributions coordinated first. They may close AI-based PRs unreviewed if they bind maintainer time.
- Every PR: tested locally, documented, a line under "Upcoming Release" in `doc/release_notes.md` in their `* Fix: … ([#N](…))` format, the human-written checkbox ticked. Pre-commit with ruff runs in CI (`pixi run -e dev ruff format`). Four-eyes review, so expect a maintainer cycle.
- Unit tests live in `test/`; a fix to a function without coverage should bring a test that fails without it.

**Goldfish the patches before rehearsal.** A fresh critic on the three `clusters: all` fixes moved two of them to a different layer (producer instead of consumer; proxy instead of dropping data) and found the existing upstream issues — cheaper than a maintainer finding the same.

| Project | Need | Status | Notes |
|---|---|---|---|
| entsoe-py | `query_generation_per_plant` broken since an API change ([#480](https://github.com/EnergieID/entsoe-py/issues/480), open since 2025-11) | Candidate | Decide at point of contact: if the fix is a few lines in request or parser, patch a local checkout, pin to it, open the PR the same day; if the raw XML is needed anyway, keep a local parser and skip upstreaming. |
| entsoe-py | EIC column level silently dropped for single-unit windows ([#534](https://github.com/EnergieID/entsoe-py/pull/534), open PR) | Watch | `include_eic=True` otherwise works; guard against the edge case locally until merged. |
| PyPSA-Eur | Hindcast mode: fix reported units (16.1.A) to measured output, scale renewable availability to zonal actuals (16.1.B) | Candidate, post-demo | Extends upstream's validation track (`config/examples/config.validation.yaml`, `doc/validation.md`). Build it upstream-shaped in the fork (own rule + script, config under `electricity:`); open an upstream issue early to gauge interest. |
| PyPSA-Eur | `add_electricity.py` reindexes monthly fuel prices onto snapshots and forward-fills: a window not starting on a month boundary gets all-NaN marginal costs | Candidate | Small fix (`reindex(method='ffill')` or resample first). Verified in upstream `563f22f6`. |
| PyPSA-Eur | `data/nuclear_p_max_pu.csv` ends 2024; a later year raises `KeyError` past the `except (ValueError, TypeError)` in `add_electricity.py` | Candidate | Data extension plus a graceful fallback. Blocks any 2025/26 run. |
