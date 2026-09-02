# Test Guidelines

- **checked-in-fixtures** — Test fixtures are checked-in files, never constructed in test code. Fixture data lives under `tests/fixtures/` as real files (e.g. `tests/fixtures/osm-tiny/`) — far more readable than string-building in fixtures, and inspectable/diffable on their own. Keep them minimal: the fewest rows that exercise the format's quirks.

- **hermetic-tests** — Tests never touch the network, downloaded data, or any manual step. A clean checkout runs the whole suite fast and green. Validating real datasets is the pipeline's job — assert invariants where the data is actually loaded, so they fail loudly in real runs, not in a test nobody executes.
