import pandas as pd
import pypsa
import pytest

from coppersushi import simplification

# Bus ids as PyPSA-Eur writes them under `clusters: all`: the OSM object, then the bus voltage.
SITES = ["relation/1", "relation/2", "relation/3"]


def _network(sites: list[str], levels: tuple[float, ...] = (380.0, 220.0)) -> pypsa.Network:
    """A network with one transformer per site, joining that site's two voltage buses."""
    n = pypsa.Network()
    for site in sites:
        for level in levels:
            n.add("Bus", f"{site}-{level:g}", v_nom=level)
        if len(levels) > 1:
            n.add("Transformer", site, bus0=f"{site}-{levels[0]:g}", bus1=f"{site}-{levels[1]:g}", x=0.1, s_nom=500)
    return n


def test_a_network_that_kept_its_transformers_passes():
    simplification.reject(_network(SITES), min_transformers=3)


def test_the_380_kv_lift_is_rejected_on_both_counts():
    """What `simplify_network_to_380` leaves: one voltage level and no transformers at all."""
    with pytest.raises(RuntimeError, match=r"no transformers at all; 1 voltage level \(380 kV\)"):
        simplification.reject(_network(SITES, levels=(380.0,)), min_transformers=3)


def test_a_network_that_kept_only_some_transformers_is_rejected():
    """The condition a bare `not empty` check would pass."""
    with pytest.raises(RuntimeError, match="1 transformers, fewer than the 3 expected"):
        simplification.reject(_network(SITES[:1]), min_transformers=3)


def test_the_minimum_is_the_base_networks_count_less_the_stub_headroom():
    assert simplification.expected_transformers(_network(SITES)) == 2
    assert simplification.expected_transformers(_network(SITES), tolerance=0.5) == 1


def test_stub_removal_of_an_unmonitored_transformer_passes():
    base, solved = _network(SITES), _network(SITES[:2])
    simplification.reject_removed_monitored(base, solved, pd.Series(["relation/1", None]))


def test_stub_removal_of_a_monitored_transformer_is_rejected():
    base, solved = _network(SITES), _network(SITES[:2])
    with pytest.raises(RuntimeError, match=r"deleted 1 JAO-monitored transformers of 1 removed — relation/3 at relation/3"):
        simplification.reject_removed_monitored(base, solved, pd.Series(["relation/3"]))


def test_a_network_nothing_was_removed_from_passes():
    base = _network(SITES)
    simplification.reject_removed_monitored(base, base, pd.Series(SITES))
