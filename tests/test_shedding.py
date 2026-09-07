import pandas as pd
import pypsa
import pytest

from coppersushi import shedding


def _network_with_shedder(shed_mw: float) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2024-07-17", periods=2, freq="2h"))
    n.snapshot_weightings.loc[:, :] = 2.0
    n.add("Bus", "b1")
    n.add("Generator", "b1 load", bus="b1", carrier="load", p_nom=1e9)
    n.add("Generator", "b1 gas", bus="b1", carrier="gas", p_nom=100)
    n.generators_t.p = pd.DataFrame({"b1 load": [shed_mw, 0.0], "b1 gas": [50.0, 50.0]}, index=n.snapshots)
    return n


def test_reject_names_the_bus_with_weighted_mwh():
    with pytest.raises(RuntimeError, match="b1: 6 MWh"):
        shedding.reject(_network_with_shedder(3.0))
    shedding.reject(_network_with_shedder(0.0))
