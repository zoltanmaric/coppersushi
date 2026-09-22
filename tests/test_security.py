import numpy as np
import pandas as pd
import pypsa
import pytest
from pandera.typing import DataFrame

from coppersushi import REPO, security
from coppersushi.data_model.security import Outages
from coppersushi.data_sources import networks

FIXTURES = REPO / "tests" / "fixtures" / "security"


@pytest.fixture
def mesh() -> pypsa.Network:
    """A triangle A-B-C with a radial tail C-D; `lodf` mutates the network it is given."""
    return networks.load(FIXTURES / "mesh.nc")


@pytest.fixture
def tree() -> pypsa.Network:
    """A chain A-B-C-D, in which every branch is a bridge."""
    return networks.load(FIXTURES / "tree.nc")


def outages(*rows: tuple[str, int]) -> DataFrame[Outages]:
    return pd.DataFrame(
        [{"branch_type": "Line", "branch_id": branch_id, "circuits_out": circuits} for branch_id, circuits in rows]
    ).pipe(Outages.validate)


def factors_of(frame: pd.DataFrame, outaged_id: str) -> "pd.Series[float]":
    taken = frame[frame.outaged_id == outaged_id]
    return taken.set_index("branch_id").factor


def test_a_bridge_is_found_before_any_arithmetic(mesh, tree):
    assert security.bridges(mesh) == {("Line", "C-D")}
    assert security.bridges(tree) == {("Line", "A-B"), ("Line", "B-C"), ("Line", "C-D")}


def test_every_branch_of_a_tree_is_a_bridge_so_nothing_is_returned(tree):
    assert security.lodf(tree, outages(("A-B", 1), ("B-C", 1), ("C-D", 1))).empty


def test_a_bridge_outage_is_dropped_rather_than_returned_as_infinity(mesh):
    computed = security.lodf(mesh, outages(("A-B", 2), ("C-D", 2)))
    assert set(computed.outaged_id) == {"A-B"}
    assert np.isfinite(computed.factor).all()


def test_a_triangle_of_equal_reactances_reroutes_the_whole_flow(mesh):
    computed = factors_of(security.lodf(mesh, outages(("A-B", 2))), "A-B")
    # A→B has only the A→C→B path left, so all of it goes there; B-C runs C-ward, hence −1.
    assert computed["A-C"] == pytest.approx(1.0)
    assert computed["B-C"] == pytest.approx(-1.0)
    assert computed["A-B"] == pytest.approx(-1.0)  # the branch itself carries nothing


def test_a_radial_branch_is_untouched_by_an_outage_in_the_mesh(mesh):
    computed = factors_of(security.lodf(mesh, outages(("A-B", 2))), "A-B")
    assert computed["C-D"] == pytest.approx(0.0)


def test_the_factors_agree_with_pypsas_own_bodf(mesh):
    computed = security.lodf(mesh, outages(("A-B", 2), ("B-C", 1), ("A-C", 1)))
    mesh.sub_networks.obj.iloc[0].calculate_BODF()
    reference = pd.DataFrame(
        mesh.sub_networks.obj.iloc[0].BODF,
        index=[name for _, name in mesh.sub_networks.obj.iloc[0].branches_i()],
        columns=[name for _, name in mesh.sub_networks.obj.iloc[0].branches_i()],
    )
    for outaged_id in ("A-B", "B-C", "A-C"):
        pd.testing.assert_series_equal(
            factors_of(computed, outaged_id).sort_index(),
            reference[outaged_id].sort_index().rename("factor").rename_axis("branch_id"),
        )


def test_losing_one_circuit_of_two_is_a_reactance_change_not_an_outage(mesh):
    computed = factors_of(security.lodf(mesh, outages(("A-B", 1))), "A-B")
    # d = 2/3 and p = 1/3 on A-C, so s·p / (1 − s·d) = (1/6) / (2/3) = 1/4.
    assert computed["A-C"] == pytest.approx(0.25)
    assert computed["B-C"] == pytest.approx(-0.25)
    assert computed["A-B"] == pytest.approx(0.5)  # it keeps flowing, on half the circuits


def test_a_bridge_stays_computable_while_one_of_its_circuits_remains(mesh):
    computed = factors_of(security.lodf(mesh, outages(("C-D", 1))), "C-D")
    # d = 1 on a bridge, so the factor is s / (1 − s) = 1 with half the circuits gone.
    assert computed["C-D"] == pytest.approx(1.0)
    assert computed["A-B"] == pytest.approx(0.0)
    assert np.isfinite(computed).all()


def test_a_branch_the_network_has_not_got_is_ignored(mesh):
    assert security.lodf(mesh, outages(("Z-Y", 1))).empty


def test_no_factor_is_ever_infinite_or_missing(mesh):
    computed = security.lodf(mesh, outages(("A-B", 2), ("B-C", 1), ("A-C", 1), ("C-D", 1)))
    assert np.isfinite(computed.factor).all()


def test_a_separate_sub_network_gets_no_rows(mesh, tree):
    mesh.add("Bus", "X", v_nom=1.0)
    mesh.add("Bus", "Y", v_nom=1.0)
    mesh.add("Line", "X-Y", bus0="X", bus1="Y", x=1.0, r=0.0, s_nom=100.0)
    computed = security.lodf(mesh, outages(("A-B", 2)))
    assert "X-Y" not in set(computed.branch_id)
