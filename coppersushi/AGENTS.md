# Package Guidelines

- **io-boundary** — Keep external I/O at the boundary. Only modules under `data_sources/` — `networks.py` (the shelf of solved networks), `pypsa_eur.py` (the upstream workflow) — touch files, processes or the network; every other module accepts and returns in-memory values. `tests/test_architecture.py` enforces it for a finite set of I/O APIs.

- **explicit-timezones** — No timestamp without a named zone. Every local time is local *to a timezone*, so time constructors always state it (`tz=`/`tzinfo=`/`utc=`). `tz=None` is permitted only where a third party forces naiveness (PyPSA snapshots — naive, meaning UTC), declared at the single conversion point. `tests/test_architecture.py` enforces a finite set of constructors. Rationale and evidence: `wiki/timezone-handling.md`.
