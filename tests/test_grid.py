from pathlib import Path

import pytest

from pipeline import grid
from pipeline.sources import osm

# Minimal checked-in dataset in the osm-prebuilt schema, exercising its quirks:
# single-quote-quoted multiline geometry, t/f booleans, meter lengths.
OSM_TINY = Path(__file__).parent / "fixtures" / "osm-tiny"


def test_build_network():
    n = grid.build_network(osm.load_tables(OSM_TINY))

    assert n.buses.carrier.to_dict() == {
        "b1": "AC", "b2": "AC", "b3": "AC", "d1": "DC", "d2": "DC"
    }
    assert n.buses.loc["b1", "country"] == "ES"

    # multiline quoted geometry must not break row parsing
    line = n.lines.loc["l1"]
    assert line.s_nom == 1787.0
    assert line.x == 2.0
    assert line.length == pytest.approx(90.0)  # meters converted to km

    # carriers are defined and assigned (PyPSA consistency)
    assert {"AC", "DC", "converter"} <= set(n.carriers.index)
    assert (n.lines.carrier == "AC").all()

    # HVDC links and converters are bidirectional
    assert (n.links.p_min_pu == -1).all()
    assert n.links.loc["dc1", "p_nom"] == 1000
    assert n.transformers.loc["t1", "s_nom"] == 500


def test_cross_border():
    n = grid.build_network(osm.load_tables(OSM_TINY))
    assert grid.cross_border(n, "Line", "ES", "FR").index.tolist() == ["l1"]
    assert grid.cross_border(n, "Line", "FR", "ES").index.tolist() == ["l1"]
    assert grid.cross_border(n, "Link", "ES", "FR").index.tolist() == ["dc1"]
    assert grid.cross_border(n, "Line", "ES", "DE").empty
