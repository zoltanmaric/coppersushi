import pypsa
from pytest import approx

from scripts.network_snapshot import NetworkSnapshot


class TestNetworkSnapshot:
    def test_node_infos(self):
        n = pypsa.Network('../networks/elec_s_all_ec_lv1.01_2H.nc')
        node_infos = NetworkSnapshot(n, n.snapshots[6]).node_infos
        assert len(node_infos) == 3534

        float_tolerance = 0.01
        assert node_infos['1004'].load_info.p == approx(86.04, abs=float_tolerance)
        # p_max should equal p_max_pu * p_nom_opt
        assert node_infos['1005'].generator_info['Onshore Wind'].p_max ==\
               approx(0.08724 * 33.99428, abs=float_tolerance)
