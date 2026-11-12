# Pipeline Guidelines

- **io-boundary** — Keep external I/O at the boundary. Only modules under a component’s `data_sources/` directory touch files, processes or the network; every other module accepts and returns in-memory values. `test_architecture.py` enforces it for a finite set of I/O APIs.

- **explicit-timezones** — No timestamp without a named zone. Every local time is local *to a timezone*: require an explicit zone in timestamp types and constructors (`tz=`/`tzinfo=`/`utc=`), and reject naive inputs inside the application. `tz=None` is permitted only where a third party forces naiveness (PyPSA snapshots — naive, meaning UTC), declared at the single conversion point. `test_architecture.py` enforces a finite set of constructors. Rationale and evidence: `wiki/timezone-handling.md`.

Read [README.md](README.md) for responsibilities, architectural decisions and commands.
