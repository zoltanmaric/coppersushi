"""Flow computation on the European grid.

Currently only a zero-flow placeholder; measured injections and ``lpf()``
replace it as they land.
"""
import pandas as pd
import pypsa

DEMO_DAY_NOON = pd.Timestamp("2026-08-12 12:00", tz="Europe/Brussels")


def zero_placeholder(n: pypsa.Network, snapshot: pd.Timestamp = DEMO_DAY_NOON) -> pypsa.Network:
    """Fill flow outputs with zeros on a single snapshot, so a network without
    injection data runs through the same viz path as a computed one."""
    # PyPSA rejects tz-aware snapshots; they are stored naive and mean UTC.
    naive_utc = snapshot.tz_convert("UTC").tz_localize(None)
    n.set_snapshots(pd.DatetimeIndex([naive_utc], tz=None, name="snapshot"))
    n.buses_t.p = pd.DataFrame(0.0, index=n.snapshots, columns=n.buses.index)
    n.lines_t.p0 = pd.DataFrame(0.0, index=n.snapshots, columns=n.lines.index)
    n.links_t.p0 = pd.DataFrame(0.0, index=n.snapshots, columns=n.links.index)
    n.transformers_t.p0 = pd.DataFrame(0.0, index=n.snapshots, columns=n.transformers.index)
    return n
