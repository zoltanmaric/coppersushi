# Test Guidelines

- **checked-in-fixtures** — Test fixtures are checked-in files, never constructed in test code: far more readable than string-building, and inspectable/diffable on their own. Keep them minimal — the fewest rows that exercise the format's quirks. Where a source's licence forbids redistribution the file is synthesised rather than captured, reproducing every quirk of the real format with invented names and values, and the real measurements it stands for are recorded in the PR body or the wiki.

- **hermetic-tests** — Tests never touch the network, downloaded data, or any manual step. A clean checkout runs the whole suite fast and green. Validating real datasets is the job of the code that loads them — assert invariants where the data is actually loaded, so they fail loudly in real runs, not in a test nobody executes.
