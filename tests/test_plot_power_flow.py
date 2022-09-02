import re

import pypsa
import pytest
from pytest import approx

import scripts.plot_power_flow as ppf


class TestPlotPowerFlow:
    @pytest.fixture
    def n(self):
        return pypsa.Network('networks/elec_s_all_ec_lv1.01_2H.nc')

    def test_get_line_info(self, n):
        line_info = ppf.get_line_info(n)
        line = line_info.loc['11274']
        assert line.bus0_x == approx(10.2997, abs=0.0001)
        assert line.bus0_y == approx(52.2867, abs=0.0001)

        assert line.bus1_x == approx(10.4521, abs=0.0001)
        assert line.bus1_y == approx(52.2589, abs=0.0001)

        # s_max should equal s_nom_opt * s_max_pu
        assert line.s_max == approx(3396.21 * 0.7, abs=0.01)

    def test_get_node_info_for_snapshot(self, n):
        node_info_t = ppf.get_node_info_for_snapshot(n, n.snapshots[6])
        node = node_info_t.loc['4977']
        assert node.x == approx(0.9586, abs=0.0001)
        assert node.y == approx(51.0595, abs=0.0001)
        assert node.p == approx(2636.09, abs=0.01)
        assert re.search(r'Nuclear.*750.40 MW', node.html) is not None
        assert re.search(r'Offshore Wind.*0.04 MW', node.html) is not None
        assert re.search(r'Onshore Wind.*0.69 MW', node.html) is not None
        assert re.search(r'Solar[^$]*37.73 MW', node.html) is not None
        assert re.search(r'Load[^$]*131.57 MW', node.html) is not None

    def test_colored_network_figure(self, n):
        fig = ppf.colored_network_figure(n, 'net_power')

        node_trace_index = 3
        node_powers = fig.data[node_trace_index].marker.color
        node_absolute_powers = fig.data[node_trace_index].marker.size

        first_negative_load_index = 2
        first_negative_load_tooltip = fig.data[node_trace_index].text[first_negative_load_index]

        assert node_powers[first_negative_load_index] == approx(-249.45, abs=0.01)
        assert node_absolute_powers[first_negative_load_index] == approx(249.45, abs=0.01)
        assert 'Net power: -249.45 MW' in first_negative_load_tooltip
