import pytest

from sushi import grid


@pytest.fixture(scope="module")
def n():
    return grid.build_network()


def test_network_shape(n):
    assert len(n.buses) > 6000
    assert len(n.lines) > 9000
    assert (n.buses.carrier == "DC").sum() > 0
    # every branch endpoint resolves to a known bus
    for c in ("lines", "links", "transformers"):
        df = getattr(n, c)
        assert df.bus0.isin(n.buses.index).all(), c
        assert df.bus1.isin(n.buses.index).all(), c


def test_es_fr_corridor(n):
    ac = grid.cross_border(n, "Line", "ES", "FR")
    # Arkale-Argia + Hernani-Argia (400), Biescas-Pragneres (220), Vic-Baixas (400)
    assert 3 <= len(ac) <= 6, ac.index.tolist()

    dc = grid.cross_border(n, "Link", "ES", "FR")
    # INELFE Baixas-Santa Llogaia: 2 x 1000 MW VSC
    assert dc.p_nom.sum() == pytest.approx(2000, rel=0.1), dc[["p_nom"]]


def test_single_connected_ac_component(n):
    n.determine_network_topology()
    # Continental Europe + islands/GB/Nordics: a handful of synchronous areas, not confetti
    sizes = n.buses.sub_network.value_counts()
    assert sizes.iloc[0] > 4000, "largest synchronous area suspiciously small"
