# Backtest scratch, 2024-08-29

The scripts that produced [wiki/backtest-2024-08-29.md](../../wiki/backtest-2024-08-29.md). Kept
because they are the only record of *how* those numbers were computed; the page records only what
came out.

**Not ready, and not on a path to being ready.** These ran from a session temp directory and were
never tidied:

- Absolute paths are hardcoded throughout — the scratch directory, the `.venv` interpreter, the
  candidate network. Nothing resolves relative to the repo.
- No tests, no error handling, no CLI. `backtest.py` picks the newest candidate by mtime and prints.
- Data is not here. `jao/` alone was 472 MB. The fetch scripts below re-download everything.

## What each one does

| | |
|---|---|
| `backtest.py` | The scorecard: binding lines vs JAO CNECs, zonal price bias/MAE, zone-pair Spearman, model line duals vs JAO shadow prices |
| `outage_check.py` | Per-carrier daily energy, model vs actual — how the French nuclear over-dispatch was found |
| `subset.py` | The same rank correlation over north-west vs south-east zone subsets |
| `model_side.py` | First pass on the 2013 network, before a 2024 solve existed |
| `fetch_jao.sh` | JAO `shadowPrices`, `maxNetPos`, and 24 hours of `finalComputation` (no key needed) |
| `fetch_prices.sh` | Settled day-ahead prices per Core zone from energy-charts (no key, rate-limited) |
| `fetch_gen.sh` | Actual generation per country from energy-charts (**lowercase** country codes, unlike the price endpoint) |
| `run_solve.sh` | Runs the solve from the worktree, so `python -m coppersushi.pypsa_eur` can import |
| `supervise_solve.sh` | Waits for a failed solve, waits for Zenodo, resumes. Bounded to 5 attempts |
| `smoke.sh` | Unit tests, then `app.render` on every route asserting traces come back |

`smoke.sh` is the one worth promoting into the repo proper: it is what verified the app still drew
`/v1`, `/opf-2013` and the 2024 candidates after each config and code change. The rest is a record.
