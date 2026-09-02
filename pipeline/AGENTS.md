# Pipeline Guidelines

- **io-boundary** — Keep external I/O at the boundary. Put file, network, and database access in `sources/` or `sinks/`; transformations accept and return in-memory values. `tests/test_architecture.py` enforces only a finite set of direct I/O APIs, not universal purity.
