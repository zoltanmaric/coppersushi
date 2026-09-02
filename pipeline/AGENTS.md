# Pipeline Guidelines

- **io-boundary** — Keep external I/O at the boundary. Put file, network, and database access in `sources/` or `sinks/`; transformations accept and return in-memory values. `tests/test_architecture.py` enforces only a finite set of direct I/O APIs, not universal purity.

- **narrate-slow-ops** — Slow operations narrate themselves. Anything that can run beyond a few seconds — downloads, solves — logs its start, coarse progress milestones, and completion via `logging`, so whoever watches the terminal always knows what is running.

- **explicit-timezones** — No timestamp without a named zone. Every local time is local *to a timezone*, so time constructors always state it (`tz=`/`tzinfo=`/`utc=`). `tz=None` is permitted only where a third party forces naiveness (PyPSA snapshots — naive, meaning UTC), declared at the single conversion point. `tests/test_architecture.py` enforces a finite set of constructors. Rationale and evidence: `wiki/timezone-handling.md`.
