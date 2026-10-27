import re

import pypsa
import pytest
from pytest import approx

from coppersushi import power_flow as ppf


class TestPlotPowerFlow:
    @pytest.fixture
    def n(self):
        return pypsa.Network('tests/fixtures/networks/v1-sample.nc')

    def test_get_branch_info_for_snapshot(self, n):
        branch_info = ppf.get_branch_info(n)
        snapshot = n.snapshots[6]  # Midday
        branch_info_t = ppf.get_branch_info_for_snapshot(n, branch_info, snapshot)

        line = branch_info_t.loc['Line', '11274']
        assert line.bus0_x == approx(10.2997, abs=0.0001)
        assert line.bus0_y == approx(52.2867, abs=0.0001)

        assert line.bus1_x == approx(10.4521, abs=0.0001)
        assert line.bus1_y == approx(52.2589, abs=0.0001)

        # p_max should equal s_nom_opt * s_max_pu for lines,
        # and p_nom_opt * p_max_pu for links
        assert line.p_max == approx(3396.21 * 0.7, abs=0.01)

        link = branch_info_t.loc['Link', 'T22']
        assert link.bus0_x == approx(0.7636, abs=0.0001)
        assert link.bus0_y == approx(51.4035, abs=0.0001)

        assert link.bus1_x == approx(8.0008, abs=0.0001)
        assert link.bus1_y == approx(53.5558, abs=0.0001)

        # p_max should equal s_nom_opt * s_max_pu for lines,
        # and p_nom_opt * p_max_pu for links
        assert link.p_max == approx(0.0002 * 1.0, abs=0.0001)

    def test_get_node_info_for_snapshot(self, n):
        node_info_t = ppf.get_node_info_for_snapshot(n, n.snapshots[6])
        node = node_info_t.loc['5624']

        assert node.x == approx(11.3187, abs=0.0001)
        assert node.y == approx(55.5504, abs=0.0001)
        assert node.p == approx(485.24, abs=0.01)

        assert re.search(r'Coal.*127.35/147.0 MW', node.html) is not None
        assert re.search(r'Offshore Wind \(AC\).*1.93/1.93 MW', node.html) is not None
        assert re.search(r'Offshore Wind \(DC\).*1.92/1.92 MW', node.html) is not None
        assert re.search(r'Onshore Wind.*95.2/95.2 MW', node.html) is not None
        assert re.search(r'Solar.*86.32/86.32 MW', node.html) is not None

        assert re.search(r'Load.*204.94 MW', node.html) is not None

        assert re.search(r'Net power.*485.24 MW', node.html) is not None

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

    def test_show_snapshot_sends_only_the_viewed_hour_without_mutating_the_cache(self, n):
        fig = ppf.colored_network_figure(n, 'net_power')
        before = fig.to_json()
        selected = ppf.show_snapshot(fig, 6)
        assert len(selected.data) == ppf.NUM_TRACES_PER_SNAPSHOT
        assert all(trace.visible for trace in selected.data)
        assert list(selected.data[3].text) == list(fig.data[6 * ppf.NUM_TRACES_PER_SNAPSHOT + 3].text)
        assert selected.layout.to_plotly_json() == fig.layout.to_plotly_json()
        assert len(ppf.show_snapshot(fig, 0).data) == ppf.NUM_TRACES_PER_SNAPSHOT
        assert fig.to_json() == before

    @pytest.mark.parametrize('index', [-1, 12])
    def test_snapshot_selection_rejects_an_hour_outside_the_solved_day(self, n, index):
        fig = ppf.colored_network_figure(n, 'net_power')
        with pytest.raises(IndexError, match='outside the solved day'):
            ppf.show_snapshot(fig, index)
