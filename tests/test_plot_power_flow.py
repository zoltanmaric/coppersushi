import pypsa
from pytest import approx
import scripts.plot_power_flow as ppf
from numpy.testing import assert_array_equal


class TestPlotPowerFlow:
    def test_colored_network_figure(self):
        n = pypsa.Network('networks/elec_s_all_ec_lv1.01_2H.nc')
        fig = ppf.colored_network_figure(n, 'net_power')

        node_powers = fig.data[3].marker.color
        node_absolute_powers = fig.data[3].marker.size

        first_tooltip = fig.data[3].text[0]

        assert node_powers[0] == approx(-59.50, abs=0.01)
        assert node_absolute_powers[0] == approx(59.50, abs=0.01)
        assert '<b>= Net power: -59.50 MW</b>' in first_tooltip

        assert_array_equal(
            n.buses_t.p.iloc[0].sort_index(),
            node_powers
        )

        assert_array_equal(
            abs(n.buses_t.p.iloc[0].sort_index()),
            node_absolute_powers
        )
