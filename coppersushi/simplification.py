"""Guards on a solved network's structure: what PyPSA-Eur deletes before we ever see the network.

Two upstream steps take transformers away, and JAO monitors transformers and phase shifters as
grid elements in their own right — an element with no branch in our network can never be matched,
can never carry a limit, and can never be predicted to bind.

1. `simplify_network_to_380` lifts every bus to one 380 kV layer and deletes all 878 transformers.
   `reject` refuses such a network: no transformers, one voltage level, or a transformer count that
   fell well below the base network's.
2. `remove_stubs` deletes the transformers of dead-end sites. That is kept on the evidence that none
   of the ones it deletes is JAO-monitored, which `reject_removed_monitored` turns from a one-hour
   sample into an assertion made on every sanction.

Design: `wiki/specs/jao-grid.md`.
"""

import pandas as pd
import pypsa

from coppersushi.substations import osm_id

STUB_TOLERANCE = 0.1  # Share of `base`'s transformers `remove_stubs` may take; it took 6.5% on 2026-09-08


def expected_transformers(base: pypsa.Network, tolerance: float = STUB_TOLERANCE) -> int:
    """The fewest transformers a solve of `base` may keep.

    Derived from `base` at every run rather than fixed at a number, which would be one
    measurement of one grid and would rot the moment OSM or the config moved; the only
    constant is the headroom stub removal is allowed.
    """
    return int(len(base.transformers) * (1 - tolerance))


def reject(n: pypsa.Network, min_transformers: int) -> None:
    """Fail loudly on a network the 380 kV lift flattened: its transformers are gone and JAO monitors them."""
    levels = sorted(n.buses.v_nom.unique())
    faults = []
    if n.transformers.empty:
        faults.append("no transformers at all")
    elif len(n.transformers) < min_transformers:
        faults.append(f"{len(n.transformers)} transformers, fewer than the {min_transformers} expected")
    if len(levels) < 2:
        faults.append(f"{len(levels)} voltage level ({', '.join(f'{v:g} kV' for v in levels)})")
    if faults:
        raise RuntimeError(f"simplified network: {'; '.join(faults)} — solve with `to_380: false`")


def reject_removed_monitored(base: pypsa.Network, solved: pypsa.Network, monitored_sites: pd.Series) -> None:
    """Fail if stub removal deleted a transformer JAO monitors: it could never be matched."""
    removed = base.transformers.index.difference(solved.transformers.index)
    monitored = set(monitored_sites.dropna())
    sites = base.transformers.loc[removed, ["bus0", "bus1"]].map(osm_id)
    struck = {name: sorted({ends.bus0, ends.bus1} & monitored) for name, ends in sites.iterrows()}
    struck = {name: hit for name, hit in struck.items() if hit}
    if struck:
        worst = ", ".join(f"{name} at {'/'.join(hit)}" for name, hit in sorted(struck.items())[:5])
        raise RuntimeError(
            f"stub removal deleted {len(struck)} JAO-monitored transformers of {len(removed)} removed"
            f" — {worst}; solve with `remove_stubs: false`"
        )
