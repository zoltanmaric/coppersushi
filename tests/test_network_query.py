import pypsa
from scripts.network_query import *


class TestNodesQuery:
    def test_node_infos(self):
        n = pypsa.Network('../networks/elec_s_all_ec_lv1.01_2H.nc')
        node_infos = NodesQuery(n, n.snapshots[6]).node_infos
        assert len(node_infos) == 2496
