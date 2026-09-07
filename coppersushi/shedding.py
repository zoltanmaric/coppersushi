"""Load shedding in a solved PyPSA-Eur network: pseudo-generators with carrier ``load`` serve the demand nothing else could."""

import pandas as pd
import pypsa


def per_bus(n: pypsa.Network) -> pd.Series:
    """Energy served by the load-shedding pseudo-generators, in MWh per bus."""
    shedders = n.generators.index[n.generators.carrier == "load"]
    per_snapshot = n.generators_t.p.reindex(columns=shedders, fill_value=0.0)
    hours = n.snapshot_weightings.generators.reindex(per_snapshot.index, fill_value=1.0)
    return per_snapshot.mul(hours, axis=0).sum().groupby(n.generators.bus).sum()


def reject(n: pypsa.Network) -> None:
    """Fail loudly on any load shedding: a shed day is a misposed problem, not a result."""
    shed = per_bus(n)
    shed = shed[shed > 0].sort_values(ascending=False)
    if not shed.empty:
        worst = ", ".join(f"{bus}: {mwh:,.0f} MWh" for bus, mwh in shed.head(5).items())
        raise RuntimeError(f"load shed at {len(shed)} buses, {shed.sum():,.0f} MWh in total — worst: {worst}")
