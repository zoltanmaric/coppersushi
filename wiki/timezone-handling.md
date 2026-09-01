# Timezone handling

**Convention** (`explicit-timezones` in `pipeline/AGENTS.md`): no timestamp without a named zone. Time constructors always pass `tz=`/`tzinfo=`/`utc=`; `tz=None` only where a third party forces naiveness, declared at the conversion point. Enforced by a finite AST check in `tests/test_architecture.py`.

**Principle:** the zone must live somewhere — in the dtype, or in a convention declared at a boundary — never in someone's head.

## The PyPSA boundary

PyPSA raises `ValueError` on tz-aware snapshots (`pypsa/network/index.py`; verified identical in installed 1.2.4, release 1.3.0, and master, 2026-09). Snapshots are therefore naive and **mean UTC**; `pipeline/flows.py` owns the aware→naive conversion.

Cause chain: numpy `datetime64` is bare int64 ticks with no metadata slot for a zone (numpy's half-built tz handling was deprecated in 1.11 and never rebuilt) → xarray stores raw numpy arrays → netCDF/CF has no timezone concept at all. PyPSA sits on all three.

## Performance is not the reason

tz-aware pandas stores the same int64 UTC ticks, with the zone held once in dtype metadata: identical storage and arithmetic, `tz_convert` is an O(1) metadata swap. Arrow and Polars likewise carry the zone in type metadata at full speed. Naiveness buys nothing in this workload.

## PyPSA is a stable numpy island

No Polars or Arrow-dtype support upstream; Arrow-backed strings (the pandas 3.0 default) are *coerced back to numpy* on import (PyPSA #1585, #1687, #1690). The naive-UTC boundary is a contract to keep, not a wart to wait out. Anything Arrow/Polars would live on our side of that same boundary.
