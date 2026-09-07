# Package Guidelines

- **io-boundary** — Keep external I/O at the boundary. Only `networks.py` (the shelf of solved networks) and `pypsa_eur.py` (the upstream workflow) touch files, processes or the network; every other module accepts and returns in-memory values. `tests/test_architecture.py` enforces it for a finite set of I/O APIs.
