
import pandas as pd
import pypsa
import pytest
from pytest import approx

from coppersushi.pipelines.powerflow import power_flow as ppf


class TestPlotPowerFlow:
    @pytest.fixture
    def n(self):
        return pypsa.Network('coppersushi/pipelines/powerflow/testdata/networks/v1-sample.nc')

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

    def test_generator_totals_combine_technologies_on_each_bus(self, n):
        totals = ppf.sum_generators_t_attribute_by_bus(n, n.generators_t.p)
        wind = ppf.sum_generators_t_attribute_by_bus(n, n.generators_t.p, "wind")
        assert totals.index.equals(n.snapshots)
        assert totals.columns.is_unique
        assert totals.loc[n.snapshots[6], "5624"] == approx(312.710707, abs=1e-6)
        assert wind.loc[n.snapshots[6], "5624"] == approx(99.046965, abs=1e-6)
