import re

import pandas as pd
import pypsa
import pytest
from pytest import approx

from coppersushi import REPO
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


class TestBusLabels:
    """A bus reads as its substation name; the id follows, and stands alone where there is no name."""

    @pytest.fixture
    def buses(self):
        sample = pd.read_csv(REPO / "tests" / "fixtures" / "substations" / "bus-names-sample.csv")
        return sample.set_index("bus_id")

    def test_a_named_bus_leads_with_its_name(self, buses):
        labels = ppf.bus_labels(buses)
        assert labels["relation/10047998-380"] == "Horta (relation/10047998-380)"

    def test_an_unnamed_bus_is_just_its_id(self, buses):
        assert ppf.bus_labels(buses)["way/9999999-380"] == "way/9999999-380"

    def test_every_label_still_carries_the_id(self, buses):
        labels = ppf.bus_labels(buses)
        assert all(bus_id in labels[bus_id] for bus_id in buses.index)

    def test_a_network_without_the_column_falls_back_to_ids(self, buses):
        assert list(ppf.bus_labels(buses.drop(columns="osm_name"))) == list(buses.index)
