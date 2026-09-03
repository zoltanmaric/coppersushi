import pypsa
from pytest import approx

from scripts.network_snapshot import NetworkSnapshot


class TestNetworkSnapshot:
    def test_node_infos(self):
        n = pypsa.Network('tests/fixtures/networks/v1-sample.nc')
        ns = NetworkSnapshot(n, n.snapshots[6])
        assert len(ns.buses) == 13

        float_tolerance = 0.01
        assert ns.loads.loc['1004'].p_load == approx(86.04, abs=float_tolerance)
        # p_max should equal p_max_pu * p_nom_opt
        assert ns.generators.loc['1005', 'Onshore Wind'].p_max ==\
               approx(0.08724 * 33.99428, abs=float_tolerance)
