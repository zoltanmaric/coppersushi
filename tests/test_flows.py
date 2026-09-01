from pathlib import Path

from pipeline import flows, grid
from pipeline.sources import osm

OSM_TINY = Path(__file__).parent / "fixtures" / "osm-tiny"


def test_zero_placeholder():
    n = flows.zero_placeholder(grid.build_network(osm.load_tables(OSM_TINY)))

    assert len(n.snapshots) == 1
    assert (n.buses_t.p.columns == n.buses.index).all()
    assert (n.buses_t.p == 0).all().all()
    assert (n.lines_t.p0 == 0).all().all()
    assert (n.links_t.p0 == 0).all().all()
    assert (n.transformers_t.p0 == 0).all().all()
